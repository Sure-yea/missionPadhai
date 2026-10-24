$env:PATH = "C:\Program Files\nodejs;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312;C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Scripts;$env:PATH"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Occulus Occupancy Mapping System..." -ForegroundColor Green
Write-Host "Backend API & UI: http://localhost:8000" -ForegroundColor Yellow
Write-Host "Vite Dev Server:  http://localhost:5173" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PATH='$($env:PATH)'; python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PATH='$($env:PATH)'; cd frontend; npm.cmd run dev"

Write-Host "Both servers launched in dedicated windows." -ForegroundColor Green
