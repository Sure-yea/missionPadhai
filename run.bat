@echo off
set "PATH=C:\Program Files\nodejs;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Scripts;%PATH%"

echo ========================================================
echo Starting Occulus Occupancy Mapping System...
echo Backend:  http://localhost:8000 (API ^& UI)
echo Frontend: http://localhost:5173 (Vite Dev Server)
echo ========================================================

start "Occulus Backend" cmd /k "title Occulus Backend && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
start "Occulus Frontend" cmd /k "title Occulus Frontend && cd frontend && npm.cmd run dev"

echo Servers started in separate windows!
