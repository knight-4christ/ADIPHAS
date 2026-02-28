# Run Local Demo (No Docker)
Write-Host "Starting GraceTech ADIS-PHAS MVP (Local Mode)..."

# Function to check if a port is in use
function Test-PortInUse {
    param($Port)
    $con = Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet
    return $con
}

if (Test-PortInUse -Port 8000) {
    Write-Warning "Port 8000 is already in use. The backend might already be running."
}

if (Test-PortInUse -Port 8501) {
    Write-Warning "Port 8501 is already in use. The UI might already be running."
}

# Run from Project Root
Set-Location "$PSScriptRoot/.."

# Start Backend
Write-Host "Starting Backend Service (FastAPI)..."
$backendProcess = Start-Process -FilePath "python" -ArgumentList "-m uvicorn backend.main:app --reload" -PassThru -NoNewWindow
Write-Host "Backend started with PID $($backendProcess.Id)"

# Wait a moment for backend to initialize
Start-Sleep -Seconds 5

# Start UI
Write-Host "Starting UI Service (Streamlit)..."
$uiProcess = Start-Process -FilePath "python" -ArgumentList "-m streamlit run ui/app.py --server.headless true" -PassThru -NoNewWindow
Write-Host "UI started with PID $($uiProcess.Id)"

Write-Host "Services are running!"
Write-Host "Backend API: http://localhost:8000/docs"
Write-Host "Streamlit UI: http://localhost:8501"
Write-Host "Press Ctrl+C to stop this script (Note: You may need to manually stop the python processes if they persist)."
