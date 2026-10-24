import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.models.database import init_db, SessionLocal
from backend.app.services.mapping.seed_data import seed_database
from backend.app.services.media.sample_media import ensure_sample_media
from backend.app.services.detection.yolo_service import YOLODetectionService
from backend.app.api.endpoints import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("occulus.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Occulus Database...")
    init_db()

    db = SessionLocal()
    try:
        logger.info("Checking seed data...")
        seed_database(db)
        logger.info("Checking sample media...")
        ensure_sample_media(db)
    finally:
        db.close()

    logger.info("Initializing YOLO Detection Service...")
    YOLODetectionService.get_instance()
    logger.info("Occulus Backend started successfully.")

    yield

    # Shutdown
    logger.info("Occulus Backend shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-Powered Table & Chair Occupancy Mapping System for Libraries",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse
from fastapi import HTTPException
from sqlalchemy import desc
from backend.app.models.database import MediaUpload

# Static and database fallback file serving for uploads and annotated media
@app.get("/storage/uploads/{file_name:path}")
async def get_storage_upload_file(file_name: str):
    # 1. Direct match on disk
    target = settings.UPLOADS_PATH / file_name
    if target.exists() and target.is_file():
        return FileResponse(str(target))

    # 2. Match by original filename in database (e.g. user requested 1.jpeg when stored as up-xxxx_1.jpeg)
    db = SessionLocal()
    try:
        media = (
            db.query(MediaUpload)
            .filter(
                (MediaUpload.filename == file_name) |
                (MediaUpload.id == file_name.split(".")[0])
            )
            .order_by(desc(MediaUpload.uploaded_at))
            .first()
        )
        if media and os.path.exists(media.file_path):
            return FileResponse(media.file_path)

        # 3. Check if any file in storage/uploads ends with _{file_name}
        matches = list(settings.UPLOADS_PATH.glob(f"*_{file_name}"))
        if matches and matches[0].is_file():
            return FileResponse(str(matches[0]))
    finally:
        db.close()

    raise HTTPException(status_code=404, detail=f"File {file_name} not found in uploads")


@app.get("/storage/annotated/{file_name:path}")
async def get_storage_annotated_file(file_name: str):
    target = settings.ANNOTATED_PATH / file_name
    if target.exists() and target.is_file():
        return FileResponse(str(target))
    raise HTTPException(status_code=404, detail=f"Annotated file {file_name} not found")

# API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


frontend_dist = settings.STORAGE_PATH.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "system": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs_url": "/docs",
            "api_prefix": settings.API_V1_PREFIX,
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
