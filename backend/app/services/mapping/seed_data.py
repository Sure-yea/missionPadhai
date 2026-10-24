import json
import math
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from backend.app.models.database import (
    CameraSection,
    LibraryTable,
    SeatingSpot,
    ChairTableMapping,
    MapLayout,
    OccupancyResult,
)

logger = logging.getLogger("occulus.seed")

# 8 CAMERA SECTORS (Strictly max 3 tables each; dedicated cameras for Room A & Room B)
DEFAULT_CAMERAS = [
    {
        "id": "cam-01",
        "name": "Camera 01 — Upper Entrance Side",
        "zone_name": "Reading Hall",
        "description": "Ceiling-mounted high-angle camera covering entrance vestibule and study tables T12 & T13",
        "coverage_bounds": json.dumps([
            {"x": 680, "y": 40},
            {"x": 1340, "y": 40},
            {"x": 1340, "y": 240},
            {"x": 680, "y": 240},
        ]),
    },
    {
        "id": "cam-02",
        "name": "Camera 02 — Upper West & Corner",
        "zone_name": "Reading Hall",
        "description": "Wide-angle camera monitoring angled corner desk T09 and north desks T10 & T11",
        "coverage_bounds": json.dumps([
            {"x": 60, "y": 40},
            {"x": 680, "y": 40},
            {"x": 680, "y": 240},
            {"x": 60, "y": 240},
        ]),
    },
    {
        "id": "cam-03",
        "name": "Camera 03 — Left Perimeter North",
        "zone_name": "Reading Hall",
        "description": "Wall-mounted camera overseeing left-hand window study stations T07 & T08",
        "coverage_bounds": json.dumps([
            {"x": 60, "y": 240},
            {"x": 320, "y": 240},
            {"x": 320, "y": 520},
            {"x": 60, "y": 520},
        ]),
    },
    {
        "id": "cam-04",
        "name": "Camera 04 — Left Perimeter South",
        "zone_name": "Reading Hall",
        "description": "High-angle camera covering south-west perimeter study tables T04, T05 & T06",
        "coverage_bounds": json.dumps([
            {"x": 60, "y": 520},
            {"x": 320, "y": 520},
            {"x": 320, "y": 840},
            {"x": 60, "y": 840},
        ]),
    },
    {
        "id": "cam-05",
        "name": "Camera 05 — Lower Perimeter",
        "zone_name": "Reading Hall",
        "description": "Panoramic camera monitoring bottom perimeter study desks T01, T02 & T03",
        "coverage_bounds": json.dumps([
            {"x": 320, "y": 660},
            {"x": 1000, "y": 660},
            {"x": 1000, "y": 850},
            {"x": 320, "y": 850},
        ]),
    },
    {
        "id": "cam-06",
        "name": "Camera 06 — Right Seating Hall",
        "zone_name": "Reading Hall",
        "description": "Wall-mounted camera monitoring east side study tables T14, T15 & T16",
        "coverage_bounds": json.dumps([
            {"x": 1000, "y": 320},
            {"x": 1340, "y": 320},
            {"x": 1340, "y": 840},
            {"x": 1000, "y": 840},
        ]),
    },
    {
        "id": "cam-07",
        "name": "Camera 07 — Room A (Study Room 1)",
        "zone_name": "Internal Room A",
        "description": "Dedicated overhead fish-eye camera inside Study Room A covering tables T17 & T18",
        "coverage_bounds": json.dumps([
            {"x": 340, "y": 260},
            {"x": 640, "y": 260},
            {"x": 640, "y": 640},
            {"x": 340, "y": 640},
        ]),
    },
    {
        "id": "cam-08",
        "name": "Camera 08 — Room B (Study Room 2)",
        "zone_name": "Internal Room B",
        "description": "Dedicated overhead fish-eye camera inside Study Room B covering tables T19 & T20",
        "coverage_bounds": json.dumps([
            {"x": 700, "y": 260},
            {"x": 1000, "y": 260},
            {"x": 1000, "y": 640},
            {"x": 700, "y": 640},
        ]),
    },
    {
        "id": "cam-test",
        "name": "Camera Testing — Table Calibration",
        "zone_name": "Testing",
        "description": "Dedicated testing camera section for exact 8-seat calibration",
        "coverage_bounds": json.dumps([
            {"x": 1060, "y": 80},
            {"x": 1360, "y": 80},
            {"x": 1360, "y": 340},
            {"x": 1060, "y": 340},
        ]),
    },
]

# 20 TABLES FROM USER BLUEPRINT
# Lower: T01..T03 | Left: T04..T08 | Upper: T09..T13 | Right: T14..T16 | Room A: T17..T18 | Room B: T19..T20
DEFAULT_TABLES_CONFIG = [
    # Lower Perimeter (horizontal) - Camera 05
    {"id": "T01", "name": "Table T01", "zone": "Reading Hall", "camera_id": "cam-05", "map_x": 380, "map_y": 750, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Lower perimeter window table"},
    {"id": "T02", "name": "Table T02", "zone": "Reading Hall", "camera_id": "cam-05", "map_x": 580, "map_y": 750, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Lower perimeter central table"},
    {"id": "T03", "name": "Table T03", "zone": "Reading Hall", "camera_id": "cam-05", "map_x": 780, "map_y": 750, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Lower perimeter east table"},

    # Left Perimeter South (vertical) - Camera 04
    {"id": "T04", "name": "Table T04", "zone": "Reading Hall", "camera_id": "cam-04", "map_x": 130, "map_y": 740, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Left perimeter south corner"},
    {"id": "T05", "name": "Table T05", "zone": "Reading Hall", "camera_id": "cam-04", "map_x": 130, "map_y": 590, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Left perimeter mid-south"},
    {"id": "T06", "name": "Table T06", "zone": "Reading Hall", "camera_id": "cam-04", "map_x": 130, "map_y": 440, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Left perimeter central west"},

    # Left Perimeter North (vertical) - Camera 03
    {"id": "T07", "name": "Table T07", "zone": "Reading Hall", "camera_id": "cam-03", "map_x": 130, "map_y": 290, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Left perimeter mid-north"},
    {"id": "T08", "name": "Table T08", "zone": "Reading Hall", "camera_id": "cam-03", "map_x": 130, "map_y": 140, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Left perimeter north desk"},

    # Upper Perimeter (T09 angled along corner chamfer, T10-T13 horizontal) - Cameras 02 & 01
    {"id": "T09", "name": "Table T09", "zone": "Reading Hall", "camera_id": "cam-02", "map_x": 230, "map_y": 100, "width": 140, "height": 64, "rotation": -35.0, "orientation": "angled", "notes": "Angled corner table along diagonal architectural wall"},
    {"id": "T10", "name": "Table T10", "zone": "Reading Hall", "camera_id": "cam-02", "map_x": 390, "map_y": 110, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Upper perimeter west desk"},
    {"id": "T11", "name": "Table T11", "zone": "Reading Hall", "camera_id": "cam-02", "map_x": 570, "map_y": 110, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Upper perimeter center desk"},
    {"id": "T12", "name": "Table T12", "zone": "Reading Hall", "camera_id": "cam-01", "map_x": 750, "map_y": 110, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Upper perimeter east desk near foyer"},
    {"id": "T13", "name": "Table T13", "zone": "Reading Hall", "camera_id": "cam-01", "map_x": 930, "map_y": 110, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "Entrance corridor adjacent table"},

    # Right Seating Hall (horizontal) - Camera 06
    {"id": "T14", "name": "Table T14", "zone": "Reading Hall", "camera_id": "cam-06", "map_x": 1180, "map_y": 400, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "East hall upper table"},
    {"id": "T15", "name": "Table T15", "zone": "Reading Hall", "camera_id": "cam-06", "map_x": 1180, "map_y": 550, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "East hall center table"},
    {"id": "T16", "name": "Table T16", "zone": "Reading Hall", "camera_id": "cam-06", "map_x": 1180, "map_y": 700, "width": 140, "height": 64, "rotation": 0.0, "orientation": "horizontal", "notes": "East hall lower table"},

    # Room A (Study Room 1) - Camera 07 (vertical)
    {"id": "T17", "name": "Table T17", "zone": "Internal Room A", "camera_id": "cam-07", "map_x": 420, "map_y": 440, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Room A West Study Pod"},
    {"id": "T18", "name": "Table T18", "zone": "Internal Room A", "camera_id": "cam-07", "map_x": 540, "map_y": 440, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Room A East Study Pod"},

    # Room B (Study Room 2) - Camera 08 (vertical)
    {"id": "T19", "name": "Table T19", "zone": "Internal Room B", "camera_id": "cam-08", "map_x": 780, "map_y": 440, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Room B West Study Pod"},
    {"id": "T20", "name": "Table T20", "zone": "Internal Room B", "camera_id": "cam-08", "map_x": 900, "map_y": 440, "width": 64, "height": 140, "rotation": 0.0, "orientation": "vertical", "notes": "Room B East Study Pod"},

    # Section Testing - Camera Testing (vertical)
    {"id": "T-TEST", "name": "Table T-TEST (Calibration)", "zone": "Testing", "camera_id": "cam-test", "map_x": 1210, "map_y": 270, "width": 60, "height": 84, "rotation": 0.0, "orientation": "vertical", "notes": "Testing table with 8 calibrated seats from hand-drawn plan"},
]


def calculate_seats_for_table(table_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Computes precise coordinates for 8 individual seats (4 per side)
    based on table center, dimensions, orientation, and rotation.
    Returns 8 seat records ready for database storage.
    """
    table_id = table_data["id"]
    camera_id = table_data["camera_id"]
    zone = table_data["zone"]
    cx = table_data["map_x"]
    cy = table_data["map_y"]
    width = table_data.get("width", 140.0)
    height = table_data.get("height", 64.0)
    rotation_deg = table_data.get("rotation", 0.0)
    orientation = table_data.get("orientation", "horizontal")

    rot_rad = math.radians(rotation_deg)
    cos_a = math.cos(rot_rad)
    sin_a = math.sin(rot_rad)

    seats = []

    # Calibrated sketch boxes for T-TEST from actual camera perspective
    SKETCH_BOXES = {
        1: ({"x": 0.16, "y": 0.42, "w": 0.16, "h": 0.08}, {"x": 0.30, "y": 0.44, "w": 0.20, "h": 0.08}),
        2: ({"x": 0.16, "y": 0.48, "w": 0.18, "h": 0.15}, {"x": 0.24, "y": 0.50, "w": 0.18, "h": 0.12}),
        3: ({"x": 0.01, "y": 0.52, "w": 0.22, "h": 0.25}, {"x": 0.16, "y": 0.58, "w": 0.22, "h": 0.16}),
        4: ({"x": 0.00, "y": 0.78, "w": 0.18, "h": 0.20}, {"x": 0.04, "y": 0.76, "w": 0.32, "h": 0.22}),
        5: ({"x": 0.52, "y": 0.43, "w": 0.14, "h": 0.06}, {"x": 0.48, "y": 0.44, "w": 0.14, "h": 0.06}),
        6: ({"x": 0.58, "y": 0.47, "w": 0.18, "h": 0.12}, {"x": 0.48, "y": 0.50, "w": 0.18, "h": 0.10}),
        7: ({"x": 0.62, "y": 0.52, "w": 0.22, "h": 0.18}, {"x": 0.50, "y": 0.56, "w": 0.20, "h": 0.14}),
        8: ({"x": 0.70, "y": 0.62, "w": 0.28, "h": 0.34}, {"x": 0.56, "y": 0.64, "w": 0.24, "h": 0.24}),
    }

    # 4 seats on side A (S01..S04), 4 seats on side B (S05..S08)
    if orientation == "vertical":
        # Table runs vertically: 4 seats on West side (Side A), 4 seats on East side (Side B)
        # Spaced along height
        h_step = (height - 24) / 3.0  # 4 seats across height
        base_y_offsets = [-(height - 24) / 2.0 + i * h_step for i in range(4)]
        dist_x = width / 2.0 + 18.0

        for i, y_off in enumerate(base_y_offsets, start=1):
            # Side A (Left/West)
            dx = -dist_x
            dy = y_off
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            c_box = SKETCH_BOXES[i][0] if table_id == "T-TEST" else {"x": 0.15 + (i - 1) * 0.18, "y": 0.40, "w": 0.14, "h": 0.22}
            t_box = SKETCH_BOXES[i][1] if table_id == "T-TEST" else {"x": 0.15 + (i - 1) * 0.18, "y": 0.20, "w": 0.14, "h": 0.18}
            seats.append({
                "id": f"{table_id}-S0{i}",
                "table_id": table_id,
                "camera_id": camera_id,
                "zone": zone,
                "map_x": round(rx, 1),
                "map_y": round(ry, 1),
                "map_rotation": rotation_deg,
                "notes": f"{table_id} Seat {i} (Side A)",
                "chair_bbox": c_box,
                "table_bbox": t_box,
            })

        for i, y_off in enumerate(base_y_offsets, start=5):
            # Side B (Right/East)
            dx = dist_x
            dy = y_off
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            c_box = SKETCH_BOXES[i][0] if table_id == "T-TEST" else {"x": 0.15 + (i - 5) * 0.18, "y": 0.70, "w": 0.14, "h": 0.22}
            t_box = SKETCH_BOXES[i][1] if table_id == "T-TEST" else {"x": 0.15 + (i - 5) * 0.18, "y": 0.48, "w": 0.14, "h": 0.18}
            seats.append({
                "id": f"{table_id}-S0{i}",
                "table_id": table_id,
                "camera_id": camera_id,
                "zone": zone,
                "map_x": round(rx, 1),
                "map_y": round(ry, 1),
                "map_rotation": rotation_deg,
                "notes": f"{table_id} Seat {i} (Side B)",
                "chair_bbox": c_box,
                "table_bbox": t_box,
            })

    else:
        # Table runs horizontally or angled: 4 seats on North side (Side A), 4 seats on South side (Side B)
        w_step = (width - 24) / 3.0  # 4 seats across width
        base_x_offsets = [-(width - 24) / 2.0 + i * w_step for i in range(4)]
        dist_y = height / 2.0 + 18.0

        for i, x_off in enumerate(base_x_offsets, start=1):
            # Side A (North/Top)
            dx = x_off
            dy = -dist_y
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            seats.append({
                "id": f"{table_id}-S0{i}",
                "table_id": table_id,
                "camera_id": camera_id,
                "zone": zone,
                "map_x": round(rx, 1),
                "map_y": round(ry, 1),
                "map_rotation": rotation_deg,
                "notes": f"{table_id} Seat {i} (Side A)",
                "chair_bbox": {"x": 0.15 + (i - 1) * 0.18, "y": 0.35, "w": 0.14, "h": 0.22},
                "table_bbox": {"x": 0.15 + (i - 1) * 0.18, "y": 0.15, "w": 0.14, "h": 0.18},
            })

        for i, x_off in enumerate(base_x_offsets, start=5):
            # Side B (South/Bottom)
            dx = x_off
            dy = dist_y
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            seats.append({
                "id": f"{table_id}-S0{i}",
                "table_id": table_id,
                "camera_id": camera_id,
                "zone": zone,
                "map_x": round(rx, 1),
                "map_y": round(ry, 1),
                "map_rotation": rotation_deg,
                "notes": f"{table_id} Seat {i} (Side B)",
                "chair_bbox": {"x": 0.15 + (i - 5) * 0.18, "y": 0.70, "w": 0.14, "h": 0.22},
                "table_bbox": {"x": 0.15 + (i - 5) * 0.18, "y": 0.48, "w": 0.14, "h": 0.18},
            })

    return seats


# BLUEPRINT ARCHITECTURAL METADATA
# Outer irregular walls, room A and B boundaries, entrance foyer with door swing
BLUEPRINT_METADATA = {
    "viewBox": "0 0 1400 900",
    "width": 1400,
    "height": 900,
    "outer_walls": [
        # Outer irregular perimeter polygon points (chamfered upper-left corner, upper entrance foyer)
        {"x": 60, "y": 240},
        {"x": 240, "y": 50},
        {"x": 1100, "y": 50},
        {"x": 1100, "y": 40},
        {"x": 1340, "y": 40},   # Upper right entrance foyer
        {"x": 1340, "y": 850},
        {"x": 60, "y": 850},
    ],
    "entrance": {
        "x": 1100,
        "y": 40,
        "width": 240,
        "height": 130,
        "door_x": 1220,
        "door_y": 40,
        "label": "MAIN LIBRARY ENTRANCE",
    },
    "rooms": [
        {
            "id": "room-a",
            "name": "Internal Room A (Study Room 1)",
            "camera_id": "cam-07",
            "x": 340,
            "y": 270,
            "w": 300,
            "h": 360,
            "chamfer_size": 35,
            "door": {"x": 640, "y": 440, "swing": "east"},
            "table_ids": ["T17", "T18"],
        },
        {
            "id": "room-b",
            "name": "Internal Room B (Study Room 2)",
            "camera_id": "cam-08",
            "x": 700,
            "y": 270,
            "w": 300,
            "h": 360,
            "chamfer_size": 35,
            "door": {"x": 700, "y": 440, "swing": "west"},
            "table_ids": ["T19", "T20"],
        },
    ],
    "walkways": [
        {"name": "Central Aisle", "x": 640, "y": 220, "w": 60, "h": 460},
        {"name": "North Walkway", "x": 260, "y": 180, "w": 820, "h": 70},
        {"name": "South Walkway", "x": 260, "y": 645, "w": 820, "h": 70},
        {"name": "West Perimeter Walkway", "x": 220, "y": 180, "w": 90, "h": 535},
        {"name": "East Perimeter Walkway", "x": 1025, "y": 180, "w": 90, "h": 535},
    ],
}


def seed_database(db: Session, force_reset: bool = False):
    """
    Initializes the database with the authentic 20-table, 160-seat, 8-camera
    blueprint floor plan adapted from the user's hand-drawn sketch.
    """
    existing_cameras = db.query(CameraSection).count()
    existing_tables = db.query(LibraryTable).count()

    # If already seeded with 20 tables and not forcing reset, return
    if not force_reset and existing_tables == 20 and existing_cameras == 8:
        logger.info("Database already seeded with 20 tables and 8 cameras.")
        return

    if force_reset:
        logger.info("Force resetting library blueprint to initial layout...")
        # Clear existing seats, mappings, tables, layout
        db.query(ChairTableMapping).delete()
        db.query(OccupancyResult).delete()
        db.query(SeatingSpot).delete()
        db.query(LibraryTable).delete()
        db.query(CameraSection).delete()
        db.query(MapLayout).delete()
        db.commit()

    # 1. Seed or update Cameras
    logger.info("Seeding 8 camera sections...")
    for cam_data in DEFAULT_CAMERAS:
        cam = db.query(CameraSection).filter(CameraSection.id == cam_data["id"]).first()
        if not cam:
            cam = CameraSection(
                id=cam_data["id"],
                name=cam_data["name"],
                zone_name=cam_data["zone_name"],
                description=cam_data["description"],
                coverage_bounds=cam_data["coverage_bounds"],
            )
            db.add(cam)
        else:
            cam.name = cam_data["name"]
            cam.zone_name = cam_data["zone_name"]
            cam.description = cam_data["description"]
            cam.coverage_bounds = cam_data["coverage_bounds"]
    db.commit()

    # 2. Seed 20 Tables
    logger.info("Seeding 20 library tables...")
    for t_data in DEFAULT_TABLES_CONFIG:
        table = db.query(LibraryTable).filter(LibraryTable.id == t_data["id"]).first()
        if not table:
            table = LibraryTable(
                id=t_data["id"],
                name=t_data["name"],
                zone=t_data["zone"],
                camera_id=t_data["camera_id"],
                map_x=t_data["map_x"],
                map_y=t_data["map_y"],
                width=t_data["width"],
                height=t_data["height"],
                rotation=t_data["rotation"],
                orientation=t_data["orientation"],
                notes=t_data["notes"],
            )
            db.add(table)
        else:
            table.name = t_data["name"]
            table.zone = t_data["zone"]
            table.camera_id = t_data["camera_id"]
            table.map_x = t_data["map_x"]
            table.map_y = t_data["map_y"]
            table.width = t_data["width"]
            table.height = t_data["height"]
            table.rotation = t_data["rotation"]
            table.orientation = t_data["orientation"]
            table.notes = t_data["notes"]
    db.commit()

    # 3. Seed 160 Seats (8 per table)
    logger.info("Generating and seeding 160 seating spots...")
    for t_data in DEFAULT_TABLES_CONFIG:
        calculated_seats = calculate_seats_for_table(t_data)
        for s in calculated_seats:
            seat = db.query(SeatingSpot).filter(SeatingSpot.id == s["id"]).first()
            if not seat:
                seat = SeatingSpot(
                    id=s["id"],
                    camera_id=s["camera_id"],
                    table_id=s["table_id"],
                    table_ref_id=s["table_id"],
                    zone=s["zone"],
                    map_x=s["map_x"],
                    map_y=s["map_y"],
                    map_rotation=s["map_rotation"],
                    notes=s["notes"],
                )
                db.add(seat)
                db.flush()

                mapping = ChairTableMapping(
                    id=f"map-{s['id']}",
                    seat_id=s["id"],
                    camera_id=s["camera_id"],
                    chair_bbox=json.dumps(s["chair_bbox"]),
                    table_bbox=json.dumps(s["table_bbox"]),
                )
                db.add(mapping)
            else:
                seat.camera_id = s["camera_id"]
                seat.table_id = s["table_id"]
                seat.table_ref_id = s["table_id"]
                seat.zone = s["zone"]
                seat.map_x = s["map_x"]
                seat.map_y = s["map_y"]
                seat.map_rotation = s["map_rotation"]
                seat.notes = s["notes"]

    db.commit()

    # 4. Seed or Update Map Layout
    layout = db.query(MapLayout).filter(MapLayout.id == "default-layout").first()
    layout_data = {
        "width": 1400,
        "height": 900,
        "blueprint_metadata": BLUEPRINT_METADATA,
        "tables": DEFAULT_TABLES_CONFIG,
    }
    if not layout:
        layout = MapLayout(
            id="default-layout",
            name="Occulus Central Library - Ground Floor Blueprint",
            layout_json=json.dumps(layout_data),
        )
        db.add(layout)
    else:
        layout.name = "Occulus Central Library - Ground Floor Blueprint"
        layout.layout_json = json.dumps(layout_data)

    db.commit()
    logger.info("Successfully seeded 20 tables, 160 seats, and 8 camera sectors.")
