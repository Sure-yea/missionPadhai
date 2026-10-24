import pytest
from backend.app.services.occupancy.classifier import (
    OccupancyClassifier,
    RegionState,
    SeatStatus,
    compute_box_intersection_ratio,
    check_region_association,
)


def test_box_overlap_calculation():
    # Box A and Box B completely overlapping
    box_a = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    box_b = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    overlap, center_in = compute_box_intersection_ratio(box_a, box_b)
    assert overlap >= 0.99
    assert center_in is True

    # Box A and Box C far apart
    box_c = {"x": 0.8, "y": 0.8, "w": 0.1, "h": 0.1}
    overlap, center_in = compute_box_intersection_ratio(box_a, box_c)
    assert overlap == 0.0
    assert center_in is False


def test_classify_empty_seat():
    chair_box = {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.2}
    table_box = {"x": 0.2, "y": 0.2, "w": 0.15, "h": 0.2}
    detections = []  # No detections

    result = OccupancyClassifier.classify_single_frame(chair_box, table_box, detections)
    assert result["status"] == SeatStatus.EMPTY
    assert result["chair_status"] == RegionState.EMPTY
    assert result["table_status"] == RegionState.EMPTY
    assert len(result["detected_belongings"]) == 0


def test_classify_occupied_seat_person():
    chair_box = {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.2}
    table_box = {"x": 0.2, "y": 0.2, "w": 0.15, "h": 0.2}

    # Person detected in chair
    detections = [
        {
            "class_name": "person",
            "confidence": 0.88,
            "bbox": {"x": 0.21, "y": 0.38, "w": 0.14, "h": 0.22},
        }
    ]

    result = OccupancyClassifier.classify_single_frame(chair_box, table_box, detections)
    assert result["status"] == SeatStatus.OCCUPIED
    assert result["chair_status"] == RegionState.OCCUPIED


def test_classify_partially_occupied_belonging():
    chair_box = {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.2}
    table_box = {"x": 0.2, "y": 0.2, "w": 0.15, "h": 0.2}

    # Backpack placed on table
    detections = [
        {
            "class_name": "backpack",
            "confidence": 0.79,
            "bbox": {"x": 0.22, "y": 0.21, "w": 0.08, "h": 0.10},
        }
    ]

    result = OccupancyClassifier.classify_single_frame(chair_box, table_box, detections)
    assert result["status"] == SeatStatus.PARTIALLY_OCCUPIED
    assert result["table_status"] == RegionState.BELONGING
    assert "backpack" in result["detected_belongings"]


def test_video_frames_smoothing():
    chair_box = {"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.2}
    table_box = {"x": 0.2, "y": 0.2, "w": 0.15, "h": 0.2}

    # 4 frames: frame 0, 1, 2 have person, frame 3 has temporary occlusion (empty)
    detections = [
        {"class_name": "person", "confidence": 0.85, "bbox": {"x": 0.21, "y": 0.39, "w": 0.14, "h": 0.2}, "frame_index": 0},
        {"class_name": "person", "confidence": 0.86, "bbox": {"x": 0.21, "y": 0.39, "w": 0.14, "h": 0.2}, "frame_index": 1},
        {"class_name": "person", "confidence": 0.83, "bbox": {"x": 0.21, "y": 0.39, "w": 0.14, "h": 0.2}, "frame_index": 2},
    ]

    result = OccupancyClassifier.classify_video_frames(chair_box, table_box, detections)
    # The temporary missed detection should not flip the seat to empty
    assert result["status"] == SeatStatus.OCCUPIED
