import os
import json
import uuid
import time
import shutil
import logging
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core.config import settings
from backend.app.models.database import (
    get_db,
    CameraSection,
    LibraryTable,
    SeatingSpot,
    ChairTableMapping,
    MediaUpload,
    DetectionJob,
    Detection,
    OccupancyResult,
    MapLayout,
)
from backend.app.schemas.schemas import (
    CameraSectionCreate,
    CameraSectionUpdate,
    CameraSectionResponse,
    LibraryTableCreate,
    LibraryTableUpdate,
    LibraryTableResponse,
    SeatingSpotCreate,
    SeatingSpotUpdate,
    SeatingSpotResponse,
    ChairTableMappingCreate,
    ChairTableMappingResponse,
    MediaUploadResponse,
    DetectionJobResponse,
    ProcessCameraRequest,
    MapLayoutResponse,
    MapSummary,
    OccupancyResultDetail,
)
from backend.app.services.detection.yolo_service import YOLODetectionService
from backend.app.services.occupancy.classifier import OccupancyClassifier, SeatStatus
from backend.app.services.mapping.seed_data import calculate_seats_for_table, seed_database
from backend.app.services.detection.space_detector import ValidSpaceDetector

logger = logging.getLogger("occulus.api")
router = APIRouter()


def get_latest_occupancy_for_seat(seat_id: str, db: Session) -> Optional[OccupancyResultDetail]:
    result = (
        db.query(OccupancyResult)
        .filter(OccupancyResult.seat_id == seat_id, OccupancyResult.is_active == True)
        .first()
    )
    if not result:
        return OccupancyResultDetail(
            status=SeatStatus.UNKNOWN,
            chair_status="unknown",
            table_status="unknown",
            detected_belongings=[],
            confidence=0.0,
            evidence_summary="Not yet analyzed. Upload footage to process.",
            annotated_preview_url=None,
            timestamp=None,
        )

    belongings = []
    if result.detected_belongings:
        try:
            belongings = json.loads(result.detected_belongings)
        except Exception:
            belongings = []

    return OccupancyResultDetail(
        status=result.status,
        chair_status=result.chair_status,
        table_status=result.table_status,
        detected_belongings=belongings,
        confidence=result.confidence,
        evidence_summary=result.evidence_summary,
        annotated_preview_url=result.annotated_preview_url,
        timestamp=result.timestamp,
    )


# -------------------------------------------------------------
# System & Health
# -------------------------------------------------------------
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    yolo = YOLODetectionService.get_instance()
    camera_count = db.query(CameraSection).count()
    seat_count = db.query(SeatingSpot).count()

    return {
        "status": "healthy",
        "yolo_ready": yolo.is_ready(),
        "device": yolo.device,
        "cameras_configured": camera_count,
        "seats_configured": seat_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# -------------------------------------------------------------
# Cameras Endpoints
# -------------------------------------------------------------
@router.get("/cameras", response_model=List[CameraSectionResponse])
def list_cameras(db: Session = Depends(get_db)):
    cameras = db.query(CameraSection).all()
    results = []
    for cam in cameras:
        seat_count = db.query(SeatingSpot).filter(SeatingSpot.camera_id == cam.id).count()
        latest_upload = (
            db.query(MediaUpload)
            .filter(MediaUpload.camera_id == cam.id)
            .order_by(desc(MediaUpload.uploaded_at))
            .first()
        )
        latest_job = (
            db.query(DetectionJob)
            .filter(DetectionJob.camera_id == cam.id, DetectionJob.status == "completed")
            .order_by(desc(DetectionJob.completed_at))
            .first()
        )

        active_media_url = (
            f"/storage/uploads/{Path(latest_upload.file_path).name}"
            if latest_upload
            else None
        )
        annotated_preview_url = (
            f"/storage/annotated/{Path(latest_job.annotated_media_path).name}"
            if (latest_job and latest_job.annotated_media_path)
            else None
        )

        results.append(
            CameraSectionResponse(
                id=cam.id,
                name=cam.name,
                zone_name=cam.zone_name,
                description=cam.description or "",
                is_active=cam.is_active,
                coverage_bounds=cam.coverage_bounds or "[]",
                created_at=cam.created_at,
                updated_at=cam.updated_at,
                seat_count=seat_count,
                active_media_filename=latest_upload.filename if latest_upload else None,
                active_media_url=active_media_url,
                annotated_preview_url=annotated_preview_url,
                last_processed_at=latest_job.completed_at if latest_job else None,
            )
        )
    return results


@router.post("/cameras", response_model=CameraSectionResponse)
def create_camera(payload: CameraSectionCreate, db: Session = Depends(get_db)):
    cam_id = payload.id or f"cam-{uuid.uuid4().hex[:6]}"
    existing = db.query(CameraSection).filter(CameraSection.id == cam_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Camera with ID {cam_id} already exists")

    camera = CameraSection(
        id=cam_id,
        name=payload.name,
        zone_name=payload.zone_name,
        description=payload.description or "",
        is_active=payload.is_active,
        coverage_bounds=payload.coverage_bounds or "[]",
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)

    return CameraSectionResponse(
        id=camera.id,
        name=camera.name,
        zone_name=camera.zone_name,
        description=camera.description,
        is_active=camera.is_active,
        coverage_bounds=camera.coverage_bounds,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        seat_count=0,
        active_media_filename=None,
        active_media_url=None,
        annotated_preview_url=None,
        last_processed_at=None,
    )


@router.get("/cameras/{camera_id}", response_model=CameraSectionResponse)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    seat_count = db.query(SeatingSpot).filter(SeatingSpot.camera_id == cam.id).count()
    latest_upload = (
        db.query(MediaUpload)
        .filter(MediaUpload.camera_id == cam.id)
        .order_by(desc(MediaUpload.uploaded_at))
        .first()
    )
    latest_job = (
        db.query(DetectionJob)
        .filter(DetectionJob.camera_id == cam.id, DetectionJob.status == "completed")
        .order_by(desc(DetectionJob.completed_at))
        .first()
    )

    active_media_url = (
        f"/storage/uploads/{Path(latest_upload.file_path).name}"
        if latest_upload
        else None
    )
    annotated_preview_url = (
        f"/storage/annotated/{Path(latest_job.annotated_media_path).name}"
        if (latest_job and latest_job.annotated_media_path)
        else None
    )

    return CameraSectionResponse(
        id=cam.id,
        name=cam.name,
        zone_name=cam.zone_name,
        description=cam.description or "",
        is_active=cam.is_active,
        coverage_bounds=cam.coverage_bounds or "[]",
        created_at=cam.created_at,
        updated_at=cam.updated_at,
        seat_count=seat_count,
        active_media_filename=latest_upload.filename if latest_upload else None,
        active_media_url=active_media_url,
        annotated_preview_url=annotated_preview_url,
        last_processed_at=latest_job.completed_at if latest_job else None,
    )


@router.patch("/cameras/{camera_id}", response_model=CameraSectionResponse)
def update_camera(camera_id: str, payload: CameraSectionUpdate, db: Session = Depends(get_db)):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    if payload.name is not None:
        cam.name = payload.name
    if payload.zone_name is not None:
        cam.zone_name = payload.zone_name
    if payload.description is not None:
        cam.description = payload.description
    if payload.is_active is not None:
        cam.is_active = payload.is_active
    if payload.coverage_bounds is not None:
        cam.coverage_bounds = payload.coverage_bounds

    cam.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cam)

    return get_camera(camera_id, db)


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    db.delete(cam)
    db.commit()
    return {"status": "deleted", "camera_id": camera_id}


# -------------------------------------------------------------
# Media Uploads
# -------------------------------------------------------------
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".avi", ".mkv", ".webm"}


@router.post("/cameras/{camera_id}/uploads", response_model=MediaUploadResponse)
async def upload_camera_media(
    camera_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Determine media type
    media_type = "video" if file_ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"} else "image"

    upload_id = f"up-{uuid.uuid4().hex[:8]}"
    safe_name = f"{upload_id}_{Path(file.filename).name}"
    target_path = settings.UPLOADS_PATH / safe_name

    # Save file with size limit check
    total_bytes = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    with open(target_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum upload size limit of {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            buffer.write(chunk)

    media = MediaUpload(
        id=upload_id,
        camera_id=camera_id,
        filename=file.filename,
        file_path=str(target_path),
        media_type=media_type,
        file_size_bytes=total_bytes,
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    return MediaUploadResponse(
        id=media.id,
        camera_id=media.camera_id,
        filename=media.filename,
        media_type=media.media_type,
        file_size_bytes=media.file_size_bytes,
        uploaded_at=media.uploaded_at,
        url=f"/storage/uploads/{target_path.name}",
    )


# -------------------------------------------------------------
# Detection & Processing
# -------------------------------------------------------------
@router.post("/cameras/{camera_id}/process", response_model=DetectionJobResponse)
def process_camera_media(
    camera_id: str,
    payload: ProcessCameraRequest = ProcessCameraRequest(),
    db: Session = Depends(get_db),
):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    # Select media
    if payload.media_id:
        media = (
            db.query(MediaUpload)
            .filter(MediaUpload.id == payload.media_id, MediaUpload.camera_id == camera_id)
            .first()
        )
    else:
        media = (
            db.query(MediaUpload)
            .filter(MediaUpload.camera_id == camera_id)
            .order_by(desc(MediaUpload.uploaded_at))
            .first()
        )

    if not media:
        raise HTTPException(
            status_code=400,
            detail=f"No media uploaded for {cam.name}. Please upload a photo or video first.",
        )

    # Create DetectionJob
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    conf_threshold = payload.confidence_threshold or settings.DEFAULT_CONFIDENCE_THRESHOLD
    sample_interval = payload.sample_interval_sec or settings.VIDEO_SAMPLE_INTERVAL_SEC

    job = DetectionJob(
        id=job_id,
        camera_id=camera_id,
        media_id=media.id,
        status="processing",
        confidence_threshold=conf_threshold,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()

    yolo = YOLODetectionService.get_instance()
    if not yolo.is_ready():
        job.status = "failed"
        job.error_message = "YOLO model failed to initialize on server"
        db.commit()
        raise HTTPException(status_code=500, detail=job.error_message)

    try:
        if media.media_type == "image":
            raw_detections, annotated_path = yolo.detect_image(
                media.file_path, conf_threshold=conf_threshold
            )
            frames_processed = 1
        else:
            raw_detections, annotated_path, frames_processed = yolo.detect_video(
                media.file_path,
                conf_threshold=conf_threshold,
                sample_interval_sec=sample_interval,
            )

        # Store detections in database
        for det in raw_detections:
            detection_record = Detection(
                id=f"det-{uuid.uuid4().hex[:8]}",
                job_id=job.id,
                frame_index=det.get("frame_index", 0),
                timestamp_sec=det.get("timestamp_sec", 0.0),
                class_name=det["class_name"],
                confidence=det["confidence"],
                bbox_x=det["bbox"]["x"],
                bbox_y=det["bbox"]["y"],
                bbox_w=det["bbox"]["w"],
                bbox_h=det["bbox"]["h"],
            )
            db.add(detection_record)

        # Map detections to seats mapped to THIS camera
        # Requirement 8: "Camera-specific results must not overwrite unrelated seats."
        camera_seats = db.query(SeatingSpot).filter(SeatingSpot.camera_id == camera_id).all()

        # Mark previous results for these seats as not active
        for seat in camera_seats:
            db.query(OccupancyResult).filter(
                OccupancyResult.seat_id == seat.id,
                OccupancyResult.is_active == True,
            ).update({"is_active": False})

        # Relative annotated URL
        annotated_preview_url = None
        if annotated_path:
            annotated_filename = Path(annotated_path).name
            annotated_preview_url = f"/storage/annotated/{annotated_filename}"

        # Collect seat mappings for this camera
        seat_mappings_dict = {}
        has_matching_calibration = True

        if not camera_seats:
            has_matching_calibration = False

        for seat in camera_seats:
            mapping = db.query(ChairTableMapping).filter(ChairTableMapping.seat_id == seat.id).first()
            if mapping:
                try:
                    cb = json.loads(mapping.chair_bbox)
                    tb = json.loads(mapping.table_bbox)
                    seat_mappings_dict[seat.id] = {
                        "chair_box": cb,
                        "table_box": tb,
                    }
                    # If this mapping does not match the active media upload, it is stale
                    if mapping.reference_media_id != media.id:
                        has_matching_calibration = False
                except Exception as e:
                    logger.error(f"Failed to parse mapping for seat {seat.id}: {e}")
                    has_matching_calibration = False
            else:
                has_matching_calibration = False

        # Dynamic Real Space Adaptation:
        # If camera has no matching calibration for this specific media upload,
        # dynamically detect the REAL physical chairs and workspaces!
        # Strict user rule: "identfiy the chair and tables only as valid space for it, no need to complete the minimum no of seats"
        if not seat_mappings_dict or not has_matching_calibration or camera_id == "cam-test":
            base_img_frame = None
            if media.media_type == "image" and media.file_path and os.path.exists(media.file_path):
                import cv2
                base_img_frame = cv2.imread(str(media.file_path))
            elif annotated_path and os.path.exists(annotated_path):
                import cv2
                base_img_frame = cv2.imread(annotated_path)

            if base_img_frame is not None:
                detector = ValidSpaceDetector.get_instance()
                detected_valid_spaces = detector.detect_valid_spaces(base_img_frame, raw_detections)

                if detected_valid_spaces:
                    table = db.query(LibraryTable).filter(LibraryTable.camera_id == camera_id).first()
                    table_id = table.id if table else f"T-{camera_id.upper()}"

                    # Clean up previous seats and mappings for this camera
                    for old_s in camera_seats:
                        db.query(ChairTableMapping).filter(ChairTableMapping.seat_id == old_s.id).delete()
                        db.query(OccupancyResult).filter(OccupancyResult.seat_id == old_s.id).delete()
                        db.delete(old_s)
                    db.flush()

                    camera_seats = []
                    seat_mappings_dict = {}

                    for idx, sp in enumerate(detected_valid_spaces):
                        seat_code = f"S{idx+1:02d}"
                        seat_id = f"{table_id}-{seat_code}"

                        spot = SeatingSpot(
                            id=seat_id,
                            camera_id=camera_id,
                            table_id=table_id,
                            zone=cam.zone_name,
                            map_x=table.map_x + (idx * 20) if table else 100.0 + (idx * 20),
                            map_y=table.map_y if table else 100.0,
                            notes=f"Auto-calibrated physical space {seat_code}",
                        )
                        db.add(spot)
                        camera_seats.append(spot)

                        mapping = ChairTableMapping(
                            id=f"map-{uuid.uuid4().hex[:8]}",
                            seat_id=seat_id,
                            camera_id=camera_id,
                            chair_bbox=json.dumps(sp["chair_box"]),
                            table_bbox=json.dumps(sp["table_box"]),
                            reference_media_id=media.id,
                            updated_at=datetime.now(timezone.utc),
                        )
                        db.add(mapping)
                        seat_mappings_dict[seat_id] = {
                            "chair_box": sp["chair_box"],
                            "table_box": sp["table_box"],
                        }
                    db.commit()

        # Simultaneous mutual-exclusion classification for single image
        if media.media_type == "image":
            batch_class_results = OccupancyClassifier.classify_camera_seats(
                seat_mappings_dict, raw_detections
            )
        else:
            batch_class_results = {}
            for seat in camera_seats:
                if seat.id in seat_mappings_dict:
                    boxes = seat_mappings_dict[seat.id]
                    batch_class_results[seat.id] = OccupancyClassifier.classify_video_frames(
                        boxes["chair_box"], boxes["table_box"], raw_detections
                    )

        # Classify and persist each seat in this camera section
        for seat in camera_seats:
            if seat.id not in batch_class_results:
                continue

            class_res = batch_class_results[seat.id]
            occupancy = OccupancyResult(
                id=f"occ-{uuid.uuid4().hex[:8]}",
                seat_id=seat.id,
                job_id=job.id,
                camera_id=camera_id,
                status=class_res["status"],
                chair_status=class_res["chair_status"],
                table_status=class_res["table_status"],
                detected_belongings=json.dumps(class_res["detected_belongings"]),
                confidence=class_res["confidence"],
                evidence_summary=class_res["evidence_summary"],
                annotated_preview_url=annotated_preview_url,
                is_active=True,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(occupancy)

        # Draw seat occupancy overlays & HUD percentage banner onto annotated preview image
        if annotated_path and os.path.exists(annotated_path):
            try:
                import cv2
                # Start with a pristine frame (clean raw image if available, else annotated_path)
                base_img = None
                if media.media_type == "image" and media.file_path and os.path.exists(media.file_path):
                    base_img = cv2.imread(str(media.file_path))
                if base_img is None:
                    base_img = cv2.imread(annotated_path)

                if base_img is not None:
                    img_h, img_w = base_img.shape[:2]
                    status_colors = {
                        "OCCUPIED": (38, 38, 220),           # Red (BGR)
                        "PARTIALLY_OCCUPIED": (0, 165, 255), # Amber (BGR)
                        "EMPTY": (34, 197, 94),              # Green (BGR)
                    }

                    # Compute occupancy percentage metrics for this camera
                    total_mapped = len(camera_seats)
                    occ_count = sum(1 for s in camera_seats if batch_class_results.get(s.id, {}).get("status") == "OCCUPIED")
                    part_count = sum(1 for s in camera_seats if batch_class_results.get(s.id, {}).get("status") == "PARTIALLY_OCCUPIED")
                    emp_count = sum(1 for s in camera_seats if batch_class_results.get(s.id, {}).get("status") == "EMPTY")

                    occ_pct = round(((occ_count + part_count) / max(1, total_mapped)) * 100)
                    strict_occ_pct = round((occ_count / max(1, total_mapped)) * 100)

                    annotated_img = base_img.copy()
                    overlay = base_img.copy()
                    banner_h = 50

                    # 1. Draw each seat bounding box identified by the model (or zone if vacant)
                    for seat in camera_seats:
                        if seat.id not in batch_class_results or seat.id not in seat_mappings_dict:
                            continue

                        res = batch_class_results[seat.id]
                        st = res.get("status", "EMPTY")
                        seat_num = seat.id.split("-")[-1]

                        occupants = res.get("occupant_detections", [])
                        belongings = res.get("belonging_detections", [])

                        cb = seat_mappings_dict[seat.id]["chair_box"]
                        tb = seat_mappings_dict[seat.id]["table_box"]

                        if st == "OCCUPIED":
                            color = status_colors["OCCUPIED"]
                            if len(occupants) > 0:
                                # Identified by YOLO model: occupant person bounding box
                                p_bbox = occupants[0]["bbox"]
                                bx1 = int(p_bbox["x"] * img_w)
                                by1 = int(p_bbox["y"] * img_h)
                                bx2 = bx1 + int(p_bbox["w"] * img_w)
                                by2 = by1 + int(p_bbox["h"] * img_h)
                            else:
                                bx1 = int(cb["x"] * img_w)
                                by1 = int(cb["y"] * img_h)
                                bx2 = bx1 + int(cb["w"] * img_w)
                                by2 = by1 + int(cb["h"] * img_h)

                            bx1, by1 = max(0, bx1), max(0, by1)
                            bx2, by2 = min(img_w - 1, bx2), min(img_h - 1, by2)

                            # Translucent Red fill over occupant
                            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), color, -1)
                            # Solid Red box around occupant
                            cv2.rectangle(annotated_img, (bx1, by1), (bx2, by2), color, 3)

                            # Sleek discrete seat tag (no noisy text like 'OCCUPIED 85%' or 'PERSON')
                            badge_y = max(banner_h + 18, by1)
                            cv2.rectangle(annotated_img, (bx1, badge_y - 18), (bx1 + 38, badge_y), color, -1)
                            cv2.putText(annotated_img, seat_num, (bx1 + 4, badge_y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

                        elif st == "PARTIALLY_OCCUPIED":
                            color = status_colors["PARTIALLY_OCCUPIED"]
                            if len(belongings) > 0:
                                # Identified by YOLO model: belonging bounding box
                                i_bbox = belongings[0]["bbox"]
                                ix1 = int(i_bbox["x"] * img_w)
                                iy1 = int(i_bbox["y"] * img_h)
                                ix2 = ix1 + int(i_bbox["w"] * img_w)
                                iy2 = iy1 + int(i_bbox["h"] * img_h)

                                # Combine with table zone for neat enclosure
                                tx1 = int(tb["x"] * img_w)
                                ty1 = int(tb["y"] * img_h)
                                tx2 = tx1 + int(tb["w"] * img_w)
                                ty2 = ty1 + int(tb["h"] * img_h)
                                bx1, by1 = min(ix1, tx1), min(iy1, ty1)
                                bx2, by2 = max(ix2, tx2), max(iy2, ty2)
                            else:
                                bx1 = int(tb["x"] * img_w)
                                by1 = int(tb["y"] * img_h)
                                bx2 = bx1 + int(tb["w"] * img_w)
                                by2 = by1 + int(tb["h"] * img_h)

                            bx1, by1 = max(0, bx1), max(0, by1)
                            bx2, by2 = min(img_w - 1, bx2), min(img_h - 1, by2)

                            # Translucent Amber fill
                            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), color, -1)
                            # Solid Amber box around belongings / reserved desk
                            cv2.rectangle(annotated_img, (bx1, by1), (bx2, by2), color, 3)

                            # Sleek discrete seat tag
                            badge_y = max(banner_h + 18, by1)
                            cv2.rectangle(annotated_img, (bx1, badge_y - 18), (bx1 + 38, badge_y), color, -1)
                            cv2.putText(annotated_img, seat_num, (bx1 + 4, badge_y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

                        else:  # EMPTY
                            color = status_colors["EMPTY"]
                            bx1 = int(cb["x"] * img_w)
                            by1 = int(cb["y"] * img_h)
                            bx2 = bx1 + int(cb["w"] * img_w)
                            by2 = by1 + int(cb["h"] * img_h)

                            bx1, by1 = max(0, bx1), max(0, by1)
                            bx2, by2 = min(img_w - 1, bx2), min(img_h - 1, by2)

                            # Translucent Green fill
                            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), color, -1)
                            # Solid Green box
                            cv2.rectangle(annotated_img, (bx1, by1), (bx2, by2), color, 2)

                            # Sleek discrete seat tag
                            badge_y = max(banner_h + 18, by1)
                            cv2.rectangle(annotated_img, (bx1, badge_y - 18), (bx1 + 38, badge_y), color, -1)
                            cv2.putText(annotated_img, seat_num, (bx1 + 4, badge_y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

                    # Blend translucent overlay (alpha=0.22)
                    cv2.addWeighted(overlay, 0.22, annotated_img, 0.78, 0, annotated_img)

                    # 2. Draw Top HUD Banner for Occupancy Percentage
                    cv2.rectangle(annotated_img, (0, 0), (img_w, banner_h), (18, 18, 18), -1)
                    cv2.line(annotated_img, (0, banner_h), (img_w, banner_h), (50, 50, 50), 2)

                    # Red signal indicator
                    cv2.rectangle(annotated_img, (14, 12), (24, 38), (38, 38, 220), -1)

                    # Main Title: OCCUPANCY: XX%
                    hud_title = f"OCCUPANCY: {occ_pct}%"
                    cv2.putText(annotated_img, hud_title, (34, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)

                    # Sub metrics breakdown
                    hud_sub = f"[{occ_count} OCCUPIED (RED) | {part_count} MID (AMBER) | {emp_count} VACANT (GREEN) | TOTAL {total_mapped} SEATS]"
                    (sw, sh), _ = cv2.getTextSize(hud_sub, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                    sub_x = max(img_w - sw - 14, 280)
                    cv2.putText(annotated_img, hud_sub, (sub_x, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 200, 200), 1, cv2.LINE_AA)

                    cv2.imwrite(annotated_path, annotated_img)
            except Exception as e:
                logger.error(f"Failed to overlay seat boxes on annotated image: {e}")

        job.status = "completed"
        job.frames_processed = frames_processed
        job.annotated_media_path = annotated_path
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)

        return DetectionJobResponse(
            id=job.id,
            camera_id=job.camera_id,
            media_id=job.media_id,
            status=job.status,
            confidence_threshold=job.confidence_threshold,
            frames_processed=job.frames_processed,
            error_message=None,
            annotated_media_url=annotated_preview_url,
            started_at=job.started_at,
            completed_at=job.completed_at,
            detections_count=len(raw_detections),
        )

    except Exception as e:
        logger.error(f"Inference error during processing: {e}", exc_info=True)
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


@router.get("/cameras/{camera_id}/results")
def get_camera_results(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(CameraSection).filter(CameraSection.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera section not found")

    latest_job = (
        db.query(DetectionJob)
        .filter(DetectionJob.camera_id == camera_id, DetectionJob.status == "completed")
        .order_by(desc(DetectionJob.completed_at))
        .first()
    )

    if not latest_job:
        return {
            "camera_id": camera_id,
            "has_results": False,
            "message": "No detection jobs completed yet for this camera.",
            "seats": [],
        }

    # Retrieve all seats for this camera
    seats = db.query(SeatingSpot).filter(SeatingSpot.camera_id == camera_id).all()
    seat_details = []
    for s in seats:
        seat_details.append({
            "id": s.id,
            "table_id": s.table_id,
            "zone": s.zone,
            "occupancy": get_latest_occupancy_for_seat(s.id, db),
        })

    annotated_url = None
    if latest_job.annotated_media_path:
        annotated_url = f"/storage/annotated/{Path(latest_job.annotated_media_path).name}"

    return {
        "camera_id": camera_id,
        "has_results": True,
        "job_id": latest_job.id,
        "confidence_threshold": latest_job.confidence_threshold,
        "frames_processed": latest_job.frames_processed,
        "completed_at": latest_job.completed_at,
        "annotated_preview_url": annotated_url,
        "seats": seat_details,
    }


# -------------------------------------------------------------
# Seating Spots Endpoints
# -------------------------------------------------------------
@router.get("/seats", response_model=List[SeatingSpotResponse])
def list_seats(
    camera_id: Optional[str] = None,
    zone: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(SeatingSpot)
    if camera_id:
        query = query.filter(SeatingSpot.camera_id == camera_id)
    if zone:
        query = query.filter(SeatingSpot.zone == zone)

    seats = query.all()
    results = []
    for s in seats:
        mapping = db.query(ChairTableMapping).filter(ChairTableMapping.seat_id == s.id).first()
        mapping_resp = None
        if mapping:
            try:
                chair_box = json.loads(mapping.chair_bbox)
                table_box = json.loads(mapping.table_bbox)
                mapping_resp = ChairTableMappingResponse(
                    id=mapping.id,
                    seat_id=mapping.seat_id,
                    camera_id=mapping.camera_id,
                    chair_bbox=chair_box,
                    table_bbox=table_box,
                    reference_media_id=mapping.reference_media_id,
                    updated_at=mapping.updated_at,
                )
            except Exception:
                pass

        results.append(
            SeatingSpotResponse(
                id=s.id,
                camera_id=s.camera_id,
                table_id=s.table_id,
                zone=s.zone,
                map_x=s.map_x,
                map_y=s.map_y,
                map_rotation=s.map_rotation or 0.0,
                notes=s.notes or "",
                created_at=s.created_at,
                mapping=mapping_resp,
                latest_occupancy=get_latest_occupancy_for_seat(s.id, db),
            )
        )
    return results


@router.post("/seats", response_model=SeatingSpotResponse)
def create_seat(payload: SeatingSpotCreate, db: Session = Depends(get_db)):
    existing = db.query(SeatingSpot).filter(SeatingSpot.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Seat ID '{payload.id}' already exists")

    seat = SeatingSpot(
        id=payload.id,
        camera_id=payload.camera_id,
        table_id=payload.table_id,
        zone=payload.zone,
        map_x=payload.map_x,
        map_y=payload.map_y,
        map_rotation=payload.map_rotation,
        notes=payload.notes or "",
    )
    db.add(seat)
    db.commit()
    db.refresh(seat)

    # Default mapping
    mapping = ChairTableMapping(
        id=f"map-{seat.id}",
        seat_id=seat.id,
        camera_id=seat.camera_id,
        chair_bbox=json.dumps({"x": 0.2, "y": 0.4, "w": 0.15, "h": 0.2}),
        table_bbox=json.dumps({"x": 0.2, "y": 0.2, "w": 0.15, "h": 0.2}),
    )
    db.add(mapping)
    db.commit()

    return list_seats(camera_id=seat.camera_id, db=db)[0]


@router.patch("/seats/{seat_id}", response_model=SeatingSpotResponse)
def update_seat(seat_id: str, payload: SeatingSpotUpdate, db: Session = Depends(get_db)):
    seat = db.query(SeatingSpot).filter(SeatingSpot.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    if payload.camera_id is not None:
        seat.camera_id = payload.camera_id
    if payload.table_id is not None:
        seat.table_id = payload.table_id
    if payload.zone is not None:
        seat.zone = payload.zone
    if payload.map_x is not None:
        seat.map_x = payload.map_x
    if payload.map_y is not None:
        seat.map_y = payload.map_y
    if payload.map_rotation is not None:
        seat.map_rotation = payload.map_rotation
    if payload.notes is not None:
        seat.notes = payload.notes

    db.commit()
    return [s for s in list_seats(db=db) if s.id == seat_id][0]


@router.delete("/seats/{seat_id}")
def delete_seat(seat_id: str, db: Session = Depends(get_db)):
    seat = db.query(SeatingSpot).filter(SeatingSpot.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    db.delete(seat)
    db.commit()
    return {"status": "deleted", "seat_id": seat_id}


# -------------------------------------------------------------
# Chair & Table Mappings
# -------------------------------------------------------------
@router.get("/mappings/{camera_id}", response_model=List[ChairTableMappingResponse])
def get_camera_mappings(camera_id: str, db: Session = Depends(get_db)):
    mappings = db.query(ChairTableMapping).filter(ChairTableMapping.camera_id == camera_id).all()
    results = []
    for m in mappings:
        try:
            results.append(
                ChairTableMappingResponse(
                    id=m.id,
                    seat_id=m.seat_id,
                    camera_id=m.camera_id,
                    chair_bbox=json.loads(m.chair_bbox),
                    table_bbox=json.loads(m.table_bbox),
                    reference_media_id=m.reference_media_id,
                    updated_at=m.updated_at,
                )
            )
        except Exception as e:
            logger.error(f"Error parsing mapping {m.id}: {e}")
    return results


@router.post("/mappings", response_model=ChairTableMappingResponse)
def save_chair_table_mapping(payload: ChairTableMappingCreate, db: Session = Depends(get_db)):
    mapping = db.query(ChairTableMapping).filter(ChairTableMapping.seat_id == payload.seat_id).first()
    if mapping:
        mapping.camera_id = payload.camera_id
        mapping.chair_bbox = json.dumps(payload.chair_bbox)
        mapping.table_bbox = json.dumps(payload.table_bbox)
        mapping.reference_media_id = payload.reference_media_id
        mapping.updated_at = datetime.now(timezone.utc)
    else:
        mapping = ChairTableMapping(
            id=f"map-{payload.seat_id}",
            seat_id=payload.seat_id,
            camera_id=payload.camera_id,
            chair_bbox=json.dumps(payload.chair_bbox),
            table_bbox=json.dumps(payload.table_bbox),
            reference_media_id=payload.reference_media_id,
        )
        db.add(mapping)

    db.commit()
    db.refresh(mapping)

    return ChairTableMappingResponse(
        id=mapping.id,
        seat_id=mapping.seat_id,
        camera_id=mapping.camera_id,
        chair_bbox=json.loads(mapping.chair_bbox),
        table_bbox=json.loads(mapping.table_bbox),
        reference_media_id=mapping.reference_media_id,
        updated_at=mapping.updated_at,
    )


@router.post("/mappings/auto-suggest/{camera_id}")
def auto_suggest_mappings(camera_id: str, db: Session = Depends(get_db)):
    """
    Runs YOLO on the latest camera upload and returns detected chairs and tables
    to assist the user in manual mapping calibration.
    """
    media = (
        db.query(MediaUpload)
        .filter(MediaUpload.camera_id == camera_id)
        .order_by(desc(MediaUpload.uploaded_at))
        .first()
    )
    if not media:
        raise HTTPException(
            status_code=400,
            detail="No media uploaded for this camera. Please upload an image first to auto-suggest regions.",
        )

    yolo = YOLODetectionService.get_instance()
    if not yolo.is_ready():
        raise HTTPException(status_code=500, detail="YOLO model not ready")

    if media.media_type == "image":
        detections, annotated_path = yolo.detect_image(media.file_path, conf_threshold=0.20)
    else:
        detections, annotated_path, _ = yolo.detect_video(
            media.file_path, conf_threshold=0.20, sample_interval_sec=1.0
        )

    # Filter detected furniture & occupants for calibration assistance
    suggested_chairs = [d for d in detections if d["class_name"] in ["chair", "person"]]
    suggested_tables = [d for d in detections if d["class_name"] in ["dining table", "table", "laptop", "keyboard"]]

    return {
        "camera_id": camera_id,
        "media_url": f"/storage/uploads/{Path(media.file_path).name}",
        "suggested_chairs": suggested_chairs,
        "suggested_tables": suggested_tables,
        "all_detections": detections,
    }


# -------------------------------------------------------------
# Library Tables Endpoints
# -------------------------------------------------------------
@router.get("/tables", response_model=List[LibraryTableResponse])
def list_tables(db: Session = Depends(get_db)):
    tables = db.query(LibraryTable).all()
    results = []
    for t in tables:
        seat_count = db.query(SeatingSpot).filter(SeatingSpot.table_id == t.id).count()
        results.append(
            LibraryTableResponse(
                id=t.id,
                name=t.name,
                zone=t.zone,
                camera_id=t.camera_id,
                map_x=t.map_x,
                map_y=t.map_y,
                width=t.width,
                height=t.height,
                rotation=t.rotation,
                orientation=t.orientation,
                notes=t.notes or "",
                created_at=t.created_at,
                seat_count=seat_count if seat_count > 0 else 8,
            )
        )
    return results


@router.post("/tables", response_model=LibraryTableResponse)
def create_table(payload: LibraryTableCreate, db: Session = Depends(get_db)):
    existing = db.query(LibraryTable).filter(LibraryTable.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Table ID '{payload.id}' already exists")

    table = LibraryTable(
        id=payload.id,
        name=payload.name,
        zone=payload.zone,
        camera_id=payload.camera_id,
        map_x=payload.map_x,
        map_y=payload.map_y,
        width=payload.width,
        height=payload.height,
        rotation=payload.rotation,
        orientation=payload.orientation,
        notes=payload.notes or "",
    )
    db.add(table)
    db.commit()
    db.refresh(table)

    # Automatically generate and persist 8 seats for this table
    table_data = {
        "id": table.id,
        "camera_id": table.camera_id or "cam-01",
        "zone": table.zone,
        "map_x": table.map_x,
        "map_y": table.map_y,
        "width": table.width,
        "height": table.height,
        "rotation": table.rotation,
        "orientation": table.orientation,
    }
    calculated_seats = calculate_seats_for_table(table_data)
    for s in calculated_seats:
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

    db.commit()

    return LibraryTableResponse(
        id=table.id,
        name=table.name,
        zone=table.zone,
        camera_id=table.camera_id,
        map_x=table.map_x,
        map_y=table.map_y,
        width=table.width,
        height=table.height,
        rotation=table.rotation,
        orientation=table.orientation,
        notes=table.notes or "",
        created_at=table.created_at,
        seat_count=8,
    )


@router.patch("/tables/{table_id}", response_model=LibraryTableResponse)
def update_table(table_id: str, payload: LibraryTableUpdate, db: Session = Depends(get_db)):
    table = db.query(LibraryTable).filter(LibraryTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if payload.name is not None:
        table.name = payload.name
    if payload.zone is not None:
        table.zone = payload.zone
    if payload.camera_id is not None:
        table.camera_id = payload.camera_id
    if payload.map_x is not None:
        table.map_x = payload.map_x
    if payload.map_y is not None:
        table.map_y = payload.map_y
    if payload.width is not None:
        table.width = payload.width
    if payload.height is not None:
        table.height = payload.height
    if payload.rotation is not None:
        table.rotation = payload.rotation
    if payload.orientation is not None:
        table.orientation = payload.orientation
    if payload.notes is not None:
        table.notes = payload.notes

    db.commit()

    # Recalculate coordinates for all seats linked to this table
    table_data = {
        "id": table.id,
        "camera_id": table.camera_id or "cam-01",
        "zone": table.zone,
        "map_x": table.map_x,
        "map_y": table.map_y,
        "width": table.width,
        "height": table.height,
        "rotation": table.rotation,
        "orientation": table.orientation,
    }
    calculated_seats = calculate_seats_for_table(table_data)
    for s in calculated_seats:
        seat = db.query(SeatingSpot).filter(SeatingSpot.id == s["id"]).first()
        if seat:
            seat.map_x = s["map_x"]
            seat.map_y = s["map_y"]
            seat.map_rotation = s["map_rotation"]
            seat.zone = s["zone"]
            if payload.camera_id is not None:
                seat.camera_id = payload.camera_id
                mapping = db.query(ChairTableMapping).filter(ChairTableMapping.seat_id == seat.id).first()
                if mapping:
                    mapping.camera_id = payload.camera_id

    db.commit()
    db.refresh(table)

    seat_count = db.query(SeatingSpot).filter(SeatingSpot.table_id == table.id).count()
    return LibraryTableResponse(
        id=table.id,
        name=table.name,
        zone=table.zone,
        camera_id=table.camera_id,
        map_x=table.map_x,
        map_y=table.map_y,
        width=table.width,
        height=table.height,
        rotation=table.rotation,
        orientation=table.orientation,
        notes=table.notes or "",
        created_at=table.created_at,
        seat_count=seat_count if seat_count > 0 else 8,
    )


@router.delete("/tables/{table_id}")
def delete_table(table_id: str, db: Session = Depends(get_db)):
    table = db.query(LibraryTable).filter(LibraryTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    db.delete(table)
    db.commit()
    return {"status": "deleted", "table_id": table_id}


# -------------------------------------------------------------
# Common Digital Map
# -------------------------------------------------------------
@router.get("/map", response_model=MapLayoutResponse)
def get_map_layout(db: Session = Depends(get_db)):
    # Auto-seed if needed
    seed_database(db=db, force_reset=False)

    layout = db.query(MapLayout).filter(MapLayout.id == "default-layout").first()
    if not layout:
        raise HTTPException(status_code=404, detail="Map layout not found")

    layout_data = json.loads(layout.layout_json)
    seats = list_seats(db=db)
    cameras = list_cameras(db=db)

    # Dynamic tables from database
    db_tables = db.query(LibraryTable).all()
    tables_list = []
    for t in db_tables:
        seat_count = sum(1 for s in seats if s.table_id == t.id)
        tables_list.append({
            "id": t.id,
            "name": t.name,
            "zone": t.zone,
            "camera_id": t.camera_id,
            "x": t.map_x,
            "y": t.map_y,
            "w": t.width,
            "h": t.height,
            "rotation": t.rotation,
            "orientation": t.orientation,
            "notes": t.notes or "",
            "seat_count": seat_count,
        })

    if not tables_list and "tables" in layout_data:
        tables_list = layout_data["tables"]

    # Compute Occupancy Summary
    counts = {
        SeatStatus.OCCUPIED: 0,
        SeatStatus.PARTIALLY_OCCUPIED: 0,
        SeatStatus.EMPTY: 0,
        SeatStatus.UNKNOWN: 0,
    }
    for s in seats:
        st = s.latest_occupancy.status if s.latest_occupancy else SeatStatus.UNKNOWN
        counts[st] = counts.get(st, 0) + 1

    summary = MapSummary(
        total_seats=len(seats),
        occupied=counts[SeatStatus.OCCUPIED],
        partially_occupied=counts[SeatStatus.PARTIALLY_OCCUPIED],
        empty=counts[SeatStatus.EMPTY],
        unknown=counts[SeatStatus.UNKNOWN],
    )

    return MapLayoutResponse(
        id=layout.id,
        name=layout.name,
        summary=summary,
        zones=layout_data.get("zones", []),
        tables=tables_list,
        seats=seats,
        cameras=cameras,
        blueprint_metadata=layout_data.get("blueprint_metadata"),
    )


@router.post("/map/reset-blueprint")
def reset_map_blueprint(db: Session = Depends(get_db)):
    seed_database(db=db, force_reset=True)
    return get_map_layout(db=db)


# -------------------------------------------------------------
# History Endpoints
# -------------------------------------------------------------
@router.get("/history")
def get_detection_history(
    camera_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(DetectionJob).order_by(desc(DetectionJob.started_at))
    if camera_id:
        query = query.filter(DetectionJob.camera_id == camera_id)

    jobs = query.limit(limit).all()
    results = []
    for j in jobs:
        media = db.query(MediaUpload).filter(MediaUpload.id == j.media_id).first()
        cam = db.query(CameraSection).filter(CameraSection.id == j.camera_id).first()

        annotated_url = None
        if j.annotated_media_path:
            annotated_url = f"/storage/annotated/{Path(j.annotated_media_path).name}"

        # Get count of occupied/empty for this job
        job_results = db.query(OccupancyResult).filter(OccupancyResult.job_id == j.id).all()
        status_breakdown = {}
        for r in job_results:
            status_breakdown[r.status] = status_breakdown.get(r.status, 0) + 1

        results.append({
            "id": j.id,
            "camera_id": j.camera_id,
            "camera_name": cam.name if cam else j.camera_id,
            "media_filename": media.filename if media else "unknown",
            "media_type": media.media_type if media else "unknown",
            "media_url": f"/storage/uploads/{Path(media.file_path).name}" if media else None,
            "status": j.status,
            "confidence_threshold": j.confidence_threshold,
            "frames_processed": j.frames_processed,
            "annotated_preview_url": annotated_url,
            "started_at": j.started_at,
            "completed_at": j.completed_at,
            "status_breakdown": status_breakdown,
            "error_message": j.error_message,
        })
    return results
