import os
import cv2
import numpy as np
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.app.core.config import settings
from backend.app.models.database import MediaUpload, CameraSection


def create_sample_scene(
    filename: str,
    title: str,
    people_positions: list,
    belongings_positions: list,
    empty_chairs: list,
) -> Path:
    """
    Creates a realistic test image with geometric furniture, simulated persons,
    backpacks, and books.
    """
    target = settings.UPLOADS_PATH / filename
    if target.exists():
        return target

    # 1280 x 720 image
    img = np.ones((720, 1280, 3), dtype=np.uint8) * 240  # Light background

    # Library Floor Wood Texture (subtle stripes)
    for y in range(0, 720, 40):
        cv2.line(img, (0, y), (1280, y), (225, 225, 225), 1)

    # Header banner
    cv2.rectangle(img, (0, 0), (1280, 50), (40, 40, 40), -1)
    cv2.putText(
        img,
        f"OCCULUS CCTV FEED SIMULATION - {title.upper()}",
        (30, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # Tables: Draw 2 big study tables
    # Table 1: x: 140..580, y: 140..420
    cv2.rectangle(img, (140, 140), (580, 420), (180, 195, 210), -1)
    cv2.rectangle(img, (140, 140), (580, 420), (120, 130, 140), 2)
    cv2.putText(img, "TABLE 1", (160, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 110, 120), 2)

    # Table 2: x: 700..1140, y: 140..420
    cv2.rectangle(img, (700, 140), (1140, 420), (180, 195, 210), -1)
    cv2.rectangle(img, (700, 140), (1140, 420), (120, 130, 140), 2)
    cv2.putText(img, "TABLE 2", (720, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 110, 120), 2)

    # Empty chairs
    for cx, cy in empty_chairs:
        cv2.circle(img, (cx, cy), 35, (160, 160, 160), -1)
        cv2.circle(img, (cx, cy), 35, (90, 90, 90), 2)
        cv2.putText(img, "CHAIR", (cx - 24, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (50, 50, 50), 1)

    # Belongings (backpacks, books, bottles)
    for bx, by, btype in belongings_positions:
        if btype == "backpack":
            cv2.rectangle(img, (bx - 25, by - 30), (bx + 25, by + 30), (50, 80, 160), -1)
            cv2.putText(img, "BACKPACK", (bx - 30, by - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (30, 50, 120), 1)
        elif btype == "book":
            cv2.rectangle(img, (bx - 20, by - 15), (bx + 20, by + 15), (40, 130, 50), -1)
            cv2.putText(img, "BOOK", (bx - 18, by + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        elif btype == "bottle":
            cv2.rectangle(img, (bx - 10, by - 25), (bx + 10, by + 25), (200, 120, 40), -1)
            cv2.putText(img, "BOTTLE", (bx - 15, by - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 90, 30), 1)

    # People (Head + Torso)
    for px, py in people_positions:
        # Head
        cv2.circle(img, (px, py - 40), 28, (190, 160, 140), -1)
        # Shoulders / Torso
        cv2.ellipse(img, (px, py + 20), (50, 45), 0, 0, 360, (70, 70, 170), -1)
        cv2.putText(img, "PERSON", (px - 28, py + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    cv2.imwrite(str(target), img)
    return target


def ensure_sample_media(db: Session):
    """Generates sample test footage files and links them to the default cameras if none exist."""
    cameras = db.query(CameraSection).all()
    for cam in cameras:
        existing_upload = db.query(MediaUpload).filter(MediaUpload.camera_id == cam.id).first()
        if existing_upload:
            continue

        if cam.id == "cam-01":
            # 2 People, 1 Backpack, 5 empty chairs
            sample_file = create_sample_scene(
                filename="sample_camera_01.jpg",
                title=cam.name,
                people_positions=[(240, 300), (450, 300)],
                belongings_positions=[(800, 260, "backpack"), (830, 220, "book")],
                empty_chairs=[(240, 500), (450, 500), (800, 500), (1010, 300), (1010, 500)],
            )
        elif cam.id == "cam-02":
            # 4 People, busy reading zone
            sample_file = create_sample_scene(
                filename="sample_camera_02.jpg",
                title=cam.name,
                people_positions=[(240, 300), (450, 300), (800, 300), (1010, 300)],
                belongings_positions=[(260, 240, "book"), (470, 240, "bottle")],
                empty_chairs=[(240, 500), (450, 500), (800, 500), (1010, 500)],
            )
        elif cam.id == "cam-test":
            # Testing section real CCTV camera image
            cctv_target = settings.UPLOADS_PATH / "cctv_testing_real.png"
            sample_file = cctv_target
        elif cam.id == "cam-03":
            # 1 Person, 2 Belongings (partially occupied)
            sample_file = create_sample_scene(
                filename="sample_camera_03.jpg",
                title=cam.name,
                people_positions=[(240, 300)],
                belongings_positions=[(450, 260, "backpack"), (800, 250, "bottle")],
                empty_chairs=[(450, 500), (240, 500), (800, 300), (800, 500), (1010, 300), (1010, 500)],
            )
        else:
            # Mostly empty or quiet study
            sample_file = create_sample_scene(
                filename=f"sample_{cam.id}.jpg",
                title=cam.name,
                people_positions=[(450, 300)] if "Room" in cam.name else [],
                belongings_positions=[(1010, 260, "backpack")],
                empty_chairs=[(240, 300), (240, 500), (450, 300), (450, 500), (800, 300), (800, 500), (1010, 300), (1010, 500)],
            )

        upload = MediaUpload(
            id=f"up-sample-{cam.id}",
            camera_id=cam.id,
            filename=sample_file.name,
            file_path=str(sample_file),
            media_type="image",
            file_size_bytes=os.path.getsize(sample_file),
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(upload)

    db.commit()
