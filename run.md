# Quick Run Guide — Occulus Occupancy Mapping System

This guide contains the direct commands to run the backend, frontend, and tests.

---

## ⚡ Option 1: 1-Click Launch (Recommended)

Double-click or run either script from the project root:

### Windows Batch (CMD):
```cmd
run.bat
```

### Windows PowerShell:
```powershell
.\run.ps1
```

*(This automatically starts both the FastAPI backend and Vite frontend in dedicated terminal windows).*

---

## 🖥️ Option 2: Run Manually in Separate Terminals

If you prefer running the servers in separate terminals:

### Terminal 1 — Backend (FastAPI + YOLO)
```powershell
# 1. Ensure Python 3.12 is in PATH (if not already set globally)
$env:PATH = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python312;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Scripts;$env:PATH"

# 2. Start Backend Server with Auto-Reload
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
> **Backend URL**: [http://localhost:8000](http://localhost:8000)  
> **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Terminal 2 — Frontend (React + Vite + Swiss Grid UI)
```powershell
# 1. Ensure Node.js LTS is in PATH (if not already set globally)
$env:PATH = "C:\Program Files\nodejs;$env:PATH"

# 2. Enter frontend directory and start dev server
cd frontend
npm.cmd run dev
```
> **Frontend Web App**: [http://localhost:5173](http://localhost:5173)  
> **Camera Sections & Detection Page**: [http://localhost:5173/cameras](http://localhost:5173/cameras)

---

## 🧪 Option 3: Run Automated Tests & Verification

### Run Backend Pytest Suite (11 Tests):
```powershell
$env:PATH = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python312;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Scripts;$env:PATH"
python -m pytest backend/tests -v
```

### Run Frontend Production Build:
```powershell
$env:PATH = "C:\Program Files\nodejs;$env:PATH"
cd frontend
npm.cmd run build
```

---

## 🚀 Option 4: Trigger Detection on Testing Camera (`cam-test`) via CLI

To re-run YOLO inference and seat occupancy mapping on the uploaded CCTV footage directly from the terminal:

### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/cameras/cam-test/process" -Method Post -ContentType "application/json" -Body "{}"
```

### cURL:
```bash
curl -X POST http://localhost:8000/api/cameras/cam-test/process -H "Content-Type: application/json" -d "{}"
```

---

## 📋 Summary of Access Points

| Component | URL | Notes |
| :--- | :--- | :--- |
| **Frontend UI** | [http://localhost:5173](http://localhost:5173) | Interactive 12-column Swiss Grid seating map |
| **Camera Hub** | [http://localhost:5173/cameras](http://localhost:5173/cameras) | Live CCTV feeds, upload footage & preview HUD |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | FastAPI server |
| **API Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive Swagger UI |
