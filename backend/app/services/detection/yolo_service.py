import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import cv2
import numpy as np
from ultralytics import YOLO

from backend.app.core.config import settings

logger = logging.getLogger("occulus.yolo")

# Relevant COCO classes to detect
RELEVANT_CLASSES = {
    0: "person",
    56: "chair",
    60: "dining table",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    39: "bottle",
    67: "cell phone",
    73: "book",
    63: "laptop",
}


class YOLODetectionService:
    _instance: Optional["YOLODetectionService"] = None

    def __init__(self):
        self.model: Optional[YOLO] = None
        self.device: str = "cpu"
        self._load_model()

    @classmethod
    def get_instance(cls) -> "YOLODetectionService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        model_path = Path(settings.YOLO_MODEL_PATH)
        if not model_path.exists():
            # If not in local path, load yolo11n.pt default
            model_path_str = "yolo11n.pt"
        else:
            model_path_str = str(model_path)

        logger.info(f"Loading YOLO model from: {model_path_str}")
        try:
            self.model = YOLO(model_path_str)
            # Detect device (GPU if available, else CPU)
            import torch
            if torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
            logger.info(f"YOLO model loaded successfully on device: {self.device}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}", exc_info=True)
            self.model = None

    def is_ready(self) -> bool:
        return self.model is not None

    def detect_image(
        self,
        image_path: str,
        conf_threshold: float = 0.25,
        render_raw_boxes: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Runs YOLO inference on an image.
        Returns:
            Tuple of (list_of_detections, annotated_image_path)
            Each detection contains:
            {
                "class_name": str,
                "confidence": float,
                "bbox": {"x": float, "y": float, "w": float, "h": float}, # normalized 0..1
                "frame_index": 0,
                "timestamp_sec": 0.0
            }
        """
        if not self.is_ready():
            raise RuntimeError("YOLO model is not initialized")

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found at {image_path}")

        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Could not decode image file at {image_path}. File may be corrupt.")

        orig_h, orig_w = img.shape[:2]
        if orig_h == 0 or orig_w == 0:
            raise ValueError("Invalid image dimensions")

        # Run inference
        results = self.model.predict(
            source=img,
            conf=conf_threshold,
            device=self.device,
            verbose=False,
        )

        detections: List[Dict[str, Any]] = []
        annotated_img = img.copy()

        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            for box in boxes:
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                class_name = self.model.names.get(cls_id, f"class_{cls_id}")

                # Normalized coordinates
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = xyxy
                norm_x = max(0.0, min(1.0, float(x1 / orig_w)))
                norm_y = max(0.0, min(1.0, float(y1 / orig_h)))
                norm_w = max(0.0, min(1.0, float((x2 - x1) / orig_w)))
                norm_h = max(0.0, min(1.0, float((y2 - y1) / orig_h)))

                detections.append({
                    "class_name": class_name,
                    "confidence": round(confidence, 4),
                    "bbox": {
                        "x": round(norm_x, 4),
                        "y": round(norm_y, 4),
                        "w": round(norm_w, 4),
                        "h": round(norm_h, 4),
                    },
                    "frame_index": 0,
                    "timestamp_sec": 0.0,
                })

                if render_raw_boxes:
                    # Draw bounding box and label on annotated image
                    self._draw_annotated_box(
                        annotated_img,
                        int(x1), int(y1), int(x2), int(y2),
                        class_name, confidence
                    )

        # Save annotated image
        timestamp = int(time.time() * 1000)
        annotated_filename = f"annotated_{timestamp}_{path.name}"
        annotated_path = settings.ANNOTATED_PATH / annotated_filename
        cv2.imwrite(str(annotated_path), annotated_img)

        return detections, str(annotated_path)

    def detect_video(
        self,
        video_path: str,
        conf_threshold: float = 0.25,
        sample_interval_sec: float = 1.0,
        render_raw_boxes: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """
        Samples frames from video at intervals and runs inference.
        Returns:
            Tuple of (all_detections, annotated_first_sampled_frame_path, total_frames_processed)
        """
        if not self.is_ready():
            raise RuntimeError("YOLO model is not initialized")

        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found at {video_path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file at {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or np.isnan(fps):
            fps = 25.0

        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(1, int(fps * sample_interval_sec))

        detections: List[Dict[str, Any]] = []
        annotated_frame_path = ""
        frames_processed = 0
        frame_idx = 0

        first_annotated_saved = False

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_interval == 0:
                    orig_h, orig_w = frame.shape[:2]
                    timestamp_sec = round(frame_idx / fps, 2)

                    results = self.model.predict(
                        source=frame,
                        conf=conf_threshold,
                        device=self.device,
                        verbose=False,
                    )

                    annotated_frame = frame.copy()

                    if results and len(results) > 0:
                        boxes = results[0].boxes
                        for box in boxes:
                            cls_id = int(box.cls[0].item())
                            confidence = float(box.conf[0].item())
                            class_name = self.model.names.get(cls_id, f"class_{cls_id}")

                            xyxy = box.xyxy[0].cpu().numpy()
                            x1, y1, x2, y2 = xyxy
                            norm_x = max(0.0, min(1.0, float(x1 / orig_w)))
                            norm_y = max(0.0, min(1.0, float(y1 / orig_h)))
                            norm_w = max(0.0, min(1.0, float((x2 - x1) / orig_w)))
                            norm_h = max(0.0, min(1.0, float((y2 - y1) / orig_h)))

                            detections.append({
                                "class_name": class_name,
                                "confidence": round(confidence, 4),
                                "bbox": {
                                    "x": round(norm_x, 4),
                                    "y": round(norm_y, 4),
                                    "w": round(norm_w, 4),
                                    "h": round(norm_h, 4),
                                },
                                "frame_index": frame_idx,
                                "timestamp_sec": timestamp_sec,
                            })

                            if render_raw_boxes:
                                self._draw_annotated_box(
                                    annotated_frame,
                                    int(x1), int(y1), int(x2), int(y2),
                                    class_name, confidence
                                )

                    if not first_annotated_saved:
                        timestamp = int(time.time() * 1000)
                        annotated_filename = f"annotated_frame_{timestamp}_{path.stem}.jpg"
                        target_annotated = settings.ANNOTATED_PATH / annotated_filename
                        cv2.imwrite(str(target_annotated), annotated_frame)
                        annotated_frame_path = str(target_annotated)
                        first_annotated_saved = True

                    frames_processed += 1

                frame_idx += 1
        finally:
            cap.release()

        return detections, annotated_frame_path, frames_processed

    def _draw_annotated_box(
        self,
        img: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        class_name: str,
        confidence: float,
    ):
        """Draws clean, Swiss-style annotations on preview images."""
        # Distinguish person, furniture, and belongings by color
        if class_name == "person":
            color = (38, 38, 220)  # Red BGR
        elif class_name in ["chair", "dining table"]:
            color = (80, 80, 80)   # Neutral dark grey BGR
        else:
            color = (6, 119, 217)  # Amber BGR for belongings

        # Bounding box
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        # Label background
        label = f"{class_name.upper()} {int(confidence * 100)}%"
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x1, max(0, y1 - 20)), (x1 + w + 6, max(0, y1)), color, -1)
        cv2.putText(
            img,
            label,
            (x1 + 3, max(14, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
