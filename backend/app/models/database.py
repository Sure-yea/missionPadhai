from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from backend.app.core.config import settings

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class CameraSection(Base):
    __tablename__ = "camera_sections"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    zone_name = Column(String(100), nullable=False)
    description = Column(String(255), default="")
    is_active = Column(Boolean, default=True)
    # Stored as JSON string list of points for floor plan coverage
    coverage_bounds = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    seats = relationship("SeatingSpot", back_populates="camera", cascade="all, delete-orphan")
    tables = relationship("LibraryTable", back_populates="camera")
    uploads = relationship("MediaUpload", back_populates="camera", cascade="all, delete-orphan")
    mappings = relationship("ChairTableMapping", back_populates="camera", cascade="all, delete-orphan")


class LibraryTable(Base):
    __tablename__ = "library_tables"

    id = Column(String(50), primary_key=True, index=True)  # e.g. "T01"
    name = Column(String(100), nullable=False)
    zone = Column(String(100), nullable=False)  # "Reading Hall", "Internal Room A", "Internal Room B"
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="SET NULL"), nullable=True)
    map_x = Column(Float, nullable=False, default=0.0)
    map_y = Column(Float, nullable=False, default=0.0)
    width = Column(Float, default=140.0)
    height = Column(Float, default=70.0)
    rotation = Column(Float, default=0.0)
    orientation = Column(String(20), default="horizontal")  # horizontal, vertical, angled
    notes = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    camera = relationship("CameraSection", back_populates="tables")
    seats = relationship("SeatingSpot", back_populates="table", cascade="all, delete-orphan")


class SeatingSpot(Base):
    __tablename__ = "seating_spots"

    id = Column(String(50), primary_key=True, index=True)
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="CASCADE"), nullable=False)
    table_id = Column(String(50), nullable=False)
    table_ref_id = Column(String(50), ForeignKey("library_tables.id", ondelete="CASCADE"), nullable=True)
    zone = Column(String(100), nullable=False)
    map_x = Column(Float, nullable=False, default=0.0)
    map_y = Column(Float, nullable=False, default=0.0)
    map_rotation = Column(Float, default=0.0)
    notes = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    camera = relationship("CameraSection", back_populates="seats")
    table = relationship("LibraryTable", back_populates="seats")
    mapping = relationship("ChairTableMapping", back_populates="seat", uselist=False, cascade="all, delete-orphan")
    occupancy_results = relationship("OccupancyResult", back_populates="seat", cascade="all, delete-orphan")


class ChairTableMapping(Base):
    __tablename__ = "chair_table_mappings"

    id = Column(String(50), primary_key=True, index=True)
    seat_id = Column(String(50), ForeignKey("seating_spots.id", ondelete="CASCADE"), nullable=False, unique=True)
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="CASCADE"), nullable=False)
    # Normalized [0..1] coordinates: {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2} or polygon list
    chair_bbox = Column(Text, nullable=False)
    table_bbox = Column(Text, nullable=False)
    reference_media_id = Column(String(50), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    seat = relationship("SeatingSpot", back_populates="mapping")
    camera = relationship("CameraSection", back_populates="mappings")


class MediaUpload(Base):
    __tablename__ = "media_uploads"

    id = Column(String(50), primary_key=True, index=True)
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    media_type = Column(String(20), nullable=False)  # 'image' or 'video'
    file_size_bytes = Column(Integer, default=0)
    uploaded_at = Column(DateTime(timezone=True), default=utc_now)

    camera = relationship("CameraSection", back_populates="uploads")
    detection_jobs = relationship("DetectionJob", back_populates="media", cascade="all, delete-orphan")


class DetectionJob(Base):
    __tablename__ = "detection_jobs"

    id = Column(String(50), primary_key=True, index=True)
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="CASCADE"), nullable=False)
    media_id = Column(String(50), ForeignKey("media_uploads.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default="pending")  # pending, processing, completed, failed
    confidence_threshold = Column(Float, default=0.25)
    frames_processed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    annotated_media_path = Column(String(500), nullable=True)
    started_at = Column(DateTime(timezone=True), default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    media = relationship("MediaUpload", back_populates="detection_jobs")
    detections = relationship("Detection", back_populates="job", cascade="all, delete-orphan")
    occupancy_results = relationship("OccupancyResult", back_populates="job", cascade="all, delete-orphan")


class Detection(Base):
    __tablename__ = "detections"

    id = Column(String(50), primary_key=True, index=True)
    job_id = Column(String(50), ForeignKey("detection_jobs.id", ondelete="CASCADE"), nullable=False)
    frame_index = Column(Integer, default=0)
    timestamp_sec = Column(Float, default=0.0)
    class_name = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    # Normalized bbox [x, y, w, h]
    bbox_x = Column(Float, nullable=False)
    bbox_y = Column(Float, nullable=False)
    bbox_w = Column(Float, nullable=False)
    bbox_h = Column(Float, nullable=False)

    job = relationship("DetectionJob", back_populates="detections")


class OccupancyResult(Base):
    __tablename__ = "occupancy_results"

    id = Column(String(50), primary_key=True, index=True)
    seat_id = Column(String(50), ForeignKey("seating_spots.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String(50), ForeignKey("detection_jobs.id", ondelete="CASCADE"), nullable=False)
    camera_id = Column(String(50), ForeignKey("camera_sections.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), nullable=False)  # OCCUPIED, PARTIALLY_OCCUPIED, EMPTY, UNKNOWN
    chair_status = Column(String(30), default="unknown")  # occupied, empty, belonging, unknown
    table_status = Column(String(30), default="unknown")  # occupied, empty, belonging, unknown
    detected_belongings = Column(Text, default="[]")  # JSON list
    confidence = Column(Float, default=0.0)
    evidence_summary = Column(Text, default="")
    annotated_preview_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)  # True if current active result for seat
    timestamp = Column(DateTime(timezone=True), default=utc_now)

    seat = relationship("SeatingSpot", back_populates="occupancy_results")
    job = relationship("DetectionJob", back_populates="occupancy_results")


class MapLayout(Base):
    __tablename__ = "map_layouts"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    layout_json = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# Engine and session creation
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
