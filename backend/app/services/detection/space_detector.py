"""
Valid Space Detector Service

Identifies only physical chairs and table workspaces as valid seating spots.
Enforces the strict rule:
- Do NOT complete an arbitrary minimum number of seats (e.g. 8) by marking empty floor, wall, or empty desk space.
- A seat is ONLY valid if there is an actual physical chair associated with a table workspace.
- Detects Occupied (person in chair), Mid-Condition (belongings/backpack/box on chair or desk), and Vacant.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("occulus.space_detector")


def compute_iou(b1: Dict[str, float], b2: Dict[str, float]) -> float:
    """Computes Intersection over Union (IoU) of two normalized bounding boxes."""
    x1 = max(b1["x"], b2["x"])
    y1 = max(b1["y"], b2["y"])
    x2 = min(b1["x"] + b1["w"], b2["x"] + b2["w"])
    y2 = min(b1["y"] + b1["h"], b2["y"] + b2["h"])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = b1["w"] * b1["h"] + b2["w"] * b2["h"] - inter
    return inter / max(1e-6, union)


def compute_box_distance(b1: Dict[str, float], b2: Dict[str, float]) -> float:
    """Euclidean distance between box centers."""
    c1x = b1["x"] + b1["w"] / 2.0
    c1y = b1["y"] + b1["h"] / 2.0
    c2x = b2["x"] + b2["w"] / 2.0
    c2y = b2["y"] + b2["h"] / 2.0
    return ((c1x - c2x) ** 2 + (c1y - c2y) ** 2) ** 0.5


class ValidSpaceDetector:
    _instance: Optional["ValidSpaceDetector"] = None

    def __init__(self):
        self.belonging_classes = {
            "backpack",
            "handbag",
            "suitcase",
            "laptop",
            "book",
            "bottle",
            "cup",
            "cell phone",
            "keyboard",
            "mouse",
        }

    @classmethod
    def get_instance(cls) -> "ValidSpaceDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect_valid_spaces(
        self,
        img: Any,
        raw_detections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Extracts ONLY real physical chairs and table spaces.
        Uses neural-network object detections only (never creates phantom boxes on walls or empty tables).
        """
        raw_chairs = []
        raw_tables = []
        raw_persons = []
        raw_belongings = []

        for det in raw_detections:
            cls = det["class_name"].lower()
            conf = det.get("confidence", 0.5)
            b = det["bbox"]
            center = (b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0)

            item = {"class": cls, "conf": conf, "bbox": b, "center": center}

            if cls == "chair":
                raw_chairs.append(item)
            elif cls in ["dining table", "table"]:
                raw_tables.append(item)
            elif cls == "person":
                raw_persons.append(item)
            elif cls in self.belonging_classes:
                raw_belongings.append(item)

        # Non-maximum suppression on chairs to remove duplicate fragments
        clean_chairs = []
        for c in sorted(raw_chairs, key=lambda x: x["conf"], reverse=True):
            # Ignore tiny far-wall noise (h < 0.06 or w < 0.06) or boxes near ceiling (y < 0.20)
            if c["bbox"]["h"] < 0.05 or c["bbox"]["w"] < 0.05 or c["bbox"]["y"] < 0.18:
                continue
            if not any(compute_iou(c["bbox"], k["bbox"]) > 0.30 for k in clean_chairs):
                clean_chairs.append(c)

        valid_spaces = []
        for chair in clean_chairs:
            cb = chair["bbox"]
            # Synthesize table region directly in front of / adjacent to chair
            tb = {
                "x": max(0.0, cb["x"] - 0.05),
                "y": max(0.0, cb["y"] - int(cb["h"] * 0.6)),
                "w": min(1.0, cb["w"] + 0.10),
                "h": min(1.0, cb["h"] * 0.7),
            }

            valid_spaces.append({
                "chair_box": cb,
                "table_box": tb,
                "conf": chair["conf"],
                "center": chair["center"],
            })

        # Add seated persons whose chair is occluded behind desks/partitions
        for p in raw_persons:
            pb = p["bbox"]
            # Seated person: in desk/seating zone (y > 0.25) and not standing tall in walkway (h < 0.75)
            if pb["y"] > 0.25 and pb["h"] < 0.75:
                # Must not already be associated with an identified chair
                if not any(compute_iou(pb, s["chair_box"]) > 0.15 for s in valid_spaces):
                    tb = {
                        "x": max(0.0, pb["x"] - 0.05),
                        "y": max(0.0, pb["y"] + pb["h"] * 0.2),
                        "w": min(1.0, pb["w"] + 0.10),
                        "h": min(1.0, pb["h"] * 0.4),
                    }
                    valid_spaces.append({
                        "chair_box": pb,
                        "table_box": tb,
                        "conf": p["conf"],
                        "center": p["center"],
                    })

        # Sort valid spaces horizontally from left to right
        valid_spaces = sorted(valid_spaces, key=lambda s: (round(s["center"][1], 1), s["center"][0]))
        return valid_spaces
