import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
ANNOTATED_DIR = STORAGE_DIR / "annotated"
DB_DIR = STORAGE_DIR / "db"

# Ensure directories exist
for directory in [STORAGE_DIR, UPLOADS_DIR, ANNOTATED_DIR, DB_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


class Settings(BaseModel):
    PROJECT_NAME: str = "Occulus Occupancy Mapping System"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"
    
    # Storage
    STORAGE_PATH: Path = STORAGE_DIR
    UPLOADS_PATH: Path = UPLOADS_DIR
    ANNOTATED_PATH: Path = ANNOTATED_DIR
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR / 'occulus.db'}")
    
    # YOLO & CV Settings
    YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", str(BASE_DIR / "yolo11n.pt"))
    DEFAULT_CONFIDENCE_THRESHOLD: float = float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.25"))
    VIDEO_SAMPLE_INTERVAL_SEC: float = float(os.getenv("VIDEO_SAMPLE_INTERVAL_SEC", "1.0"))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "150"))
    
    # Target COCO Classes
    PERSON_CLASS: str = "person"
    CHAIR_CLASS: str = "chair"
    TABLE_CLASSES: list[str] = ["dining table"]
    BELONGING_CLASSES: list[str] = [
        "backpack", "handbag", "suitcase", "bottle", "cell phone", "book", "laptop"
    ]
    
    # Spatial overlap IoU / IoA thresholds
    OVERLAP_THRESHOLD: float = 0.20


settings = Settings()
