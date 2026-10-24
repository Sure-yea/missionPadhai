import json
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel

from backend.app.core.config import settings


class RegionState:
    EMPTY = "empty"
    OCCUPIED = "occupied"
    BELONGING = "belonging"
    UNKNOWN = "unknown"


class SeatStatus:
    OCCUPIED = "OCCUPIED"
    PARTIALLY_OCCUPIED = "PARTIALLY_OCCUPIED"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


def compute_box_intersection_ratio(
    box_a: Dict[str, float], box_b: Dict[str, float]
) -> Tuple[float, bool]:
    """
    Computes overlap ratio between box_a and box_b.
    Returns:
        (overlap_ratio_relative_to_smaller, is_center_contained)
    """
    ax1, ay1 = box_a["x"], box_a["y"]
    ax2, ay2 = ax1 + box_a["w"], ay1 + box_a["h"]
    area_a = max(1e-6, box_a["w"] * box_a["h"])

    bx1, by1 = box_b["x"], box_b["y"]
    bx2, by2 = bx1 + box_b["w"], by1 + box_b["h"]
    area_b = max(1e-6, box_b["w"] * box_b["h"])

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    if inter_x2 > inter_x1 and inter_y2 > inter_y1:
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    else:
        inter_area = 0.0

    # Ratio relative to smaller box (or target region)
    min_area = min(area_a, area_b)
    overlap_ratio = inter_area / min_area

    # Center of box_a inside box_b or vice versa
    center_a_x, center_a_y = ax1 + box_a["w"] / 2.0, ay1 + box_a["h"] / 2.0
    center_b_x, center_b_y = bx1 + box_b["w"] / 2.0, by1 + box_b["h"] / 2.0

    center_contained = (
        (bx1 <= center_a_x <= bx2 and by1 <= center_a_y <= by2) or
        (ax1 <= center_b_x <= ax2 and ay1 <= center_b_y <= ay2)
    )

    return overlap_ratio, center_contained


def check_region_association(
    det_box: Dict[str, float], region_box: Dict[str, float], threshold: float = 0.15
) -> bool:
    """Checks if detection box is associated with a chair or table region."""
    overlap, center_in = compute_box_intersection_ratio(det_box, region_box)
    return center_in or (overlap >= threshold)


class OccupancyClassifier:
    """
    Modular Rule-Based Occupancy Classifier.
    Evaluates Chair State and Table State separately, then derives the overall Seat Status.
    """

    @staticmethod
    def classify_single_frame(
        chair_box: Dict[str, float],
        table_box: Dict[str, float],
        detections: List[Dict[str, Any]],
        overlap_threshold: float = 0.18,
    ) -> Dict[str, Any]:
        """
        Evaluates chair and table status for a single frame of detections.
        """
        # Internal states
        chair_state = RegionState.EMPTY
        table_state = RegionState.EMPTY

        chair_person_count = 0
        table_person_count = 0
        chair_belongings: List[str] = []
        table_belongings: List[str] = []
        highest_conf = 0.0

        for det in detections:
            cls_name = det["class_name"].lower()
            conf = det.get("confidence", 0.0)
            bbox = det["bbox"]

            is_person = cls_name == "person"
            is_belonging = cls_name in settings.BELONGING_CLASSES

            # Check overlap with Chair
            if check_region_association(bbox, chair_box, overlap_threshold):
                if is_person:
                    chair_person_count += 1
                    highest_conf = max(highest_conf, conf)
                elif is_belonging:
                    chair_belongings.append(cls_name)
                    highest_conf = max(highest_conf, conf)

            # Check overlap with Table
            if check_region_association(bbox, table_box, overlap_threshold):
                if is_person:
                    table_person_count += 1
                    highest_conf = max(highest_conf, conf)
                elif is_belonging:
                    table_belongings.append(cls_name)
                    highest_conf = max(highest_conf, conf)

        # 1. Determine Chair State
        if chair_person_count > 0:
            chair_state = RegionState.OCCUPIED
        elif len(chair_belongings) > 0:
            chair_state = RegionState.BELONGING
        else:
            chair_state = RegionState.EMPTY

        # 2. Determine Table State
        if table_person_count > 0:
            table_state = RegionState.OCCUPIED
        elif len(table_belongings) > 0:
            table_state = RegionState.BELONGING
        else:
            table_state = RegionState.EMPTY

        # 3. Derive Combined Seat Status per rules:
        # - OCCUPIED: Both chair and table occupied, OR chair occupied by person
        # - PARTIALLY OCCUPIED / UNSURE: Only one has person/belonging, or reserved with belongings
        # - EMPTY: Both chair and table are clear
        all_belongings = list(set(chair_belongings + table_belongings))

        if chair_state == RegionState.OCCUPIED and table_state == RegionState.OCCUPIED:
            status = SeatStatus.OCCUPIED
            evidence = "Person detected at chair and table."
        elif chair_state == RegionState.OCCUPIED:
            # Person seated in chair
            status = SeatStatus.OCCUPIED
            evidence = "Person detected seated in chair."
        elif chair_state == RegionState.BELONGING or table_state == RegionState.BELONGING:
            # Belonging on chair or table (reserved)
            status = SeatStatus.PARTIALLY_OCCUPIED
            evidence = f"Spot temporarily reserved with belongings: {', '.join(all_belongings)}."
        elif table_state == RegionState.OCCUPIED and chair_state == RegionState.EMPTY:
            # Person leaning/standing at table but chair empty
            status = SeatStatus.PARTIALLY_OCCUPIED
            evidence = "Person detected near table, chair empty."
        else:
            status = SeatStatus.EMPTY
            evidence = "Chair and table regions are clear of detected occupants and items."
            highest_conf = max(highest_conf, 0.90)

        return {
            "status": status,
            "chair_status": chair_state,
            "table_status": table_state,
            "detected_belongings": all_belongings,
            "confidence": round(highest_conf if highest_conf > 0 else 0.85, 2),
            "evidence_summary": evidence,
        }

    @classmethod
    def classify_video_frames(
        cls,
        chair_box: Dict[str, float],
        table_box: Dict[str, float],
        frame_detections: List[Dict[str, Any]],
        overlap_threshold: float = 0.18,
    ) -> Dict[str, Any]:
        """
        Aggregates evidence across multiple sampled video frames.
        Avoids momentary false negatives (e.g. 1 frame occlusion) by voting/smoothing.
        """
        if not frame_detections:
            return {
                "status": SeatStatus.EMPTY,
                "chair_status": RegionState.EMPTY,
                "table_status": RegionState.EMPTY,
                "detected_belongings": [],
                "confidence": 0.80,
                "evidence_summary": "No objects detected across sampled frames; clear.",
            }

        # Group detections by frame_index
        frames: Dict[int, List[Dict[str, Any]]] = {}
        for det in frame_detections:
            idx = det.get("frame_index", 0)
            if idx not in frames:
                frames[idx] = []
            frames[idx].append(det)

        frame_results = [
            cls.classify_single_frame(chair_box, table_box, dets, overlap_threshold)
            for dets in frames.values()
        ]

        if not frame_results:
            return cls.classify_single_frame(chair_box, table_box, frame_detections, overlap_threshold)

        # Count occurrences of each status
        status_counts = {
            SeatStatus.OCCUPIED: 0,
            SeatStatus.PARTIALLY_OCCUPIED: 0,
            SeatStatus.EMPTY: 0,
        }
        all_belongings = set()
        conf_sum = 0.0

        for res in frame_results:
            st = res["status"]
            status_counts[st] = status_counts.get(st, 0) + 1
            for b in res["detected_belongings"]:
                all_belongings.add(b)
            conf_sum += res["confidence"]

        avg_conf = round(conf_sum / len(frame_results), 2)
        total_frames = len(frame_results)

        # Majority vote / evidence retention:
        # If occupied in >= 30% of frames, retain occupied/partially occupied (avoids flickering)
        if status_counts[SeatStatus.OCCUPIED] >= max(1, total_frames * 0.3):
            final_status = SeatStatus.OCCUPIED
            final_chair = RegionState.OCCUPIED
            final_table = RegionState.OCCUPIED
            evidence = f"Occupant consistently detected across {status_counts[SeatStatus.OCCUPIED]}/{total_frames} sampled frames."
        elif (
            status_counts[SeatStatus.PARTIALLY_OCCUPIED] >= max(1, total_frames * 0.25)
            or len(all_belongings) > 0
        ):
            final_status = SeatStatus.PARTIALLY_OCCUPIED
            final_chair = RegionState.BELONGING if all_belongings else RegionState.EMPTY
            final_table = RegionState.BELONGING if all_belongings else RegionState.OCCUPIED
            evidence = f"Belongings or transient occupancy detected across {status_counts[SeatStatus.PARTIALLY_OCCUPIED]}/{total_frames} frames."
        else:
            final_status = SeatStatus.EMPTY
            final_chair = RegionState.EMPTY
            final_table = RegionState.EMPTY
            evidence = f"Consistent empty state verified across {status_counts[SeatStatus.EMPTY]}/{total_frames} sampled frames."

        return {
            "status": final_status,
            "chair_status": final_chair,
            "table_status": final_table,
            "detected_belongings": list(all_belongings),
            "confidence": avg_conf,
            "evidence_summary": evidence,
        }

    @classmethod
    def classify_camera_seats(
        cls,
        seat_mappings: Dict[str, Dict[str, Any]],
        detections: List[Dict[str, Any]],
        overlap_threshold: float = 0.12,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Classifies all seats under a camera section simultaneously using mutual exclusion.
        Each detected person is assigned to their best matching seat (preventing shoulder/perspective bleed across adjacent chairs),
        and belongings are assigned to their closest/most overlapping table.
        """
        seat_occupants: Dict[str, List[Dict[str, Any]]] = {sid: [] for sid in seat_mappings}
        seat_belongings: Dict[str, List[str]] = {sid: [] for sid in seat_mappings}
        seat_belonging_detections: Dict[str, List[Dict[str, Any]]] = {sid: [] for sid in seat_mappings}
        seat_confidences: Dict[str, float] = {sid: 0.85 for sid in seat_mappings}

        belonging_classes = set(settings.BELONGING_CLASSES) | {
            "cup",
            "keyboard",
            "bottle",
            "laptop",
            "book",
            "backpack",
            "handbag",
            "suitcase",
            "mouse",
            "cell phone",
        }

        for det in detections:
            cls_name = det["class_name"].lower()
            b = det["bbox"]
            conf = det.get("confidence", 0.85)
            is_person = (cls_name == "person")
            is_belonging = (cls_name in belonging_classes)

            if not (is_person or is_belonging):
                continue

            best_sid = None
            best_score = 0.0

            for sid, boxes in seat_mappings.items():
                cb = boxes.get("chair_box", boxes.get("chair", {}))
                tb = boxes.get("table_box", boxes.get("table", {}))

                ov_c, in_c = compute_box_intersection_ratio(b, cb)
                ov_t, in_t = compute_box_intersection_ratio(b, tb)

                if is_person:
                    score = (ov_c * 2.0 + (1.0 if in_c else 0.0)) + (ov_t * 0.5 + (0.2 if in_t else 0.0))
                else:
                    score = (ov_t * 2.0 + (1.0 if in_t else 0.0)) + (ov_c * 0.5 + (0.2 if in_c else 0.0))

                if score > best_score and (score >= overlap_threshold or in_c or in_t):
                    best_score = score
                    best_sid = sid

            if best_sid:
                seat_confidences[best_sid] = max(seat_confidences[best_sid], conf)
                if is_person:
                    seat_occupants[best_sid].append(det)
                elif is_belonging:
                    seat_belongings[best_sid].append(cls_name)
                    seat_belonging_detections[best_sid].append(det)

        results = {}
        for sid in seat_mappings:
            has_person = len(seat_occupants[sid]) > 0
            items = list(set(seat_belongings[sid]))

            if has_person:
                status = SeatStatus.OCCUPIED
                chair_st = RegionState.OCCUPIED
                table_st = RegionState.OCCUPIED
                evidence = f"Person detected seated at spot ({len(seat_occupants[sid])} detection)."
            elif items:
                status = SeatStatus.PARTIALLY_OCCUPIED
                chair_st = RegionState.EMPTY
                table_st = RegionState.BELONGING
                evidence = f"Spot temporarily reserved with belongings: {', '.join(items)}."
            else:
                status = SeatStatus.EMPTY
                chair_st = RegionState.EMPTY
                table_st = RegionState.EMPTY
                evidence = "Chair and table regions are clear of detected occupants and items."

            results[sid] = {
                "status": status,
                "chair_status": chair_st,
                "table_status": table_st,
                "detected_belongings": items,
                "confidence": round(seat_confidences[sid], 2),
                "evidence_summary": evidence,
                "occupant_detections": seat_occupants[sid],
                "belonging_detections": seat_belonging_detections[sid],
            }

        return results
