from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# Camera Section Schemas
class CameraSectionBase(BaseModel):
    name: str
    zone_name: str
    description: Optional[str] = ""
    is_active: bool = True
    coverage_bounds: Optional[str] = "[]"


class CameraSectionCreate(CameraSectionBase):
    id: Optional[str] = None


class CameraSectionUpdate(BaseModel):
    name: Optional[str] = None
    zone_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    coverage_bounds: Optional[str] = None


class CameraSectionResponse(CameraSectionBase):
    id: str
    created_at: datetime
    updated_at: datetime
    seat_count: int = 0
    active_media_filename: Optional[str] = None
    active_media_url: Optional[str] = None
    annotated_preview_url: Optional[str] = None
    last_processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Chair-Table Mapping Schemas
class BoundingBox(BaseModel):
    x: float  # Normalized 0..1 (top-left)
    y: float
    w: float
    h: float


class ChairTableMappingBase(BaseModel):
    seat_id: str
    camera_id: str
    chair_bbox: Dict[str, float]  # {x, y, w, h}
    table_bbox: Dict[str, float]  # {x, y, w, h}
    reference_media_id: Optional[str] = None


class ChairTableMappingCreate(ChairTableMappingBase):
    pass


class ChairTableMappingResponse(ChairTableMappingBase):
    id: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Library Table Schemas
class LibraryTableBase(BaseModel):
    id: str
    name: str
    zone: str
    camera_id: Optional[str] = None
    map_x: float
    map_y: float
    width: float = 140.0
    height: float = 70.0
    rotation: float = 0.0
    orientation: str = "horizontal"  # horizontal, vertical, angled
    notes: Optional[str] = ""


class LibraryTableCreate(LibraryTableBase):
    pass


class LibraryTableUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    camera_id: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    rotation: Optional[float] = None
    orientation: Optional[str] = None
    notes: Optional[str] = None


class LibraryTableResponse(LibraryTableBase):
    created_at: datetime
    seat_count: int = 8

    model_config = ConfigDict(from_attributes=True)


# Seating Spot Schemas
class SeatingSpotBase(BaseModel):
    id: str
    camera_id: str
    table_id: str
    zone: str
    map_x: float
    map_y: float
    map_rotation: float = 0.0
    notes: Optional[str] = ""


class SeatingSpotCreate(SeatingSpotBase):
    pass


class SeatingSpotUpdate(BaseModel):
    camera_id: Optional[str] = None
    table_id: Optional[str] = None
    zone: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    map_rotation: Optional[float] = None
    notes: Optional[str] = None


class OccupancyResultDetail(BaseModel):
    status: str  # OCCUPIED, PARTIALLY_OCCUPIED, EMPTY, UNKNOWN
    chair_status: str
    table_status: str
    detected_belongings: List[str] = []
    confidence: float = 0.0
    evidence_summary: str = ""
    annotated_preview_url: Optional[str] = None
    timestamp: Optional[datetime] = None


class SeatingSpotResponse(SeatingSpotBase):
    created_at: datetime
    mapping: Optional[ChairTableMappingResponse] = None
    latest_occupancy: Optional[OccupancyResultDetail] = None

    model_config = ConfigDict(from_attributes=True)


# Media Upload Schemas
class MediaUploadResponse(BaseModel):
    id: str
    camera_id: str
    filename: str
    media_type: str
    file_size_bytes: int
    uploaded_at: datetime
    url: str

    model_config = ConfigDict(from_attributes=True)


# Detection & Processing Schemas
class ProcessCameraRequest(BaseModel):
    media_id: Optional[str] = None  # If omitted, uses latest upload
    confidence_threshold: Optional[float] = 0.25
    sample_interval_sec: Optional[float] = 1.0


class DetectionDetail(BaseModel):
    class_name: str
    confidence: float
    bbox: Dict[str, float]
    frame_index: int = 0
    timestamp_sec: float = 0.0


class DetectionJobResponse(BaseModel):
    id: str
    camera_id: str
    media_id: str
    status: str
    confidence_threshold: float
    frames_processed: int
    error_message: Optional[str] = None
    annotated_media_url: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    detections_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# Common Map Schemas
class MapSummary(BaseModel):
    total_seats: int
    occupied: int
    partially_occupied: int
    empty: int
    unknown: int


class MapLayoutResponse(BaseModel):
    id: str
    name: str
    summary: MapSummary
    zones: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    seats: List[SeatingSpotResponse]
    cameras: List[CameraSectionResponse]
    blueprint_metadata: Optional[Dict[str, Any]] = None
