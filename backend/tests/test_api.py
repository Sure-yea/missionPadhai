import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.database import init_db, SessionLocal
from backend.app.services.mapping.seed_data import seed_database
from backend.app.services.media.sample_media import ensure_sample_media

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    db = SessionLocal()
    seed_database(db, force_reset=True)
    ensure_sample_media(db)
    db.close()


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["cameras_configured"] >= 8
    assert data["seats_configured"] >= 160


def test_list_cameras():
    response = client.get("/api/cameras")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 8
    camera_ids = [c["id"] for c in data]
    for cid in ["cam-01", "cam-02", "cam-03", "cam-04", "cam-05", "cam-06", "cam-07", "cam-08"]:
        assert cid in camera_ids


def test_get_map_layout():
    response = client.get("/api/map")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["summary"]["total_seats"] >= 160
    assert "tables" in data
    assert len(data["tables"]) >= 20
    assert len(data["seats"]) >= 160
    assert data["blueprint_metadata"] is not None


def test_camera_seat_isolation():
    # Verify seats are strictly associated with their camera
    response = client.get("/api/seats?camera_id=cam-01")
    assert response.status_code == 200
    cam1_seats = response.json()
    # Cam 01 covers 2 tables (T12, T13) = 16 seats
    assert len(cam1_seats) == 16
    for s in cam1_seats:
        assert s["camera_id"] == "cam-01"


def test_list_tables():
    response = client.get("/api/tables")
    assert response.status_code == 200
    tables = response.json()
    assert len(tables) >= 20
    # Every table has 8 seats
    for t in tables:
        assert t["seat_count"] == 8


def test_table_crud_and_seat_generation():
    # Create test table
    payload = {
        "id": "T99",
        "name": "Test Table 99",
        "zone": "Reading Hall",
        "camera_id": "cam-01",
        "map_x": 500,
        "map_y": 500,
        "width": 140,
        "height": 64,
        "rotation": 0.0,
        "orientation": "horizontal",
        "notes": "Testing auto-seat generation",
    }
    create_res = client.post("/api/tables", json=payload)
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["id"] == "T99"
    assert created["seat_count"] == 8

    # Verify 8 seats were automatically created
    seats_res = client.get("/api/seats")
    table_seats = [s for s in seats_res.json() if s["table_id"] == "T99"]
    assert len(table_seats) == 8

    # Update table position
    patch_res = client.patch("/api/tables/T99", json={"map_x": 550, "map_y": 550})
    assert patch_res.status_code == 200
    updated_seats = [s for s in client.get("/api/seats").json() if s["table_id"] == "T99"]
    assert len(updated_seats) == 8

    # Delete test table
    del_res = client.delete("/api/tables/T99")
    assert del_res.status_code == 200
    remaining_seats = [s for s in client.get("/api/seats").json() if s["table_id"] == "T99"]
    assert len(remaining_seats) == 0
