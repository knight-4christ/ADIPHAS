# Run Local Demo 
Write-Host "Starting GraceTech ADIS-PHAS MVP Demo..."

# Create log file
$logFile = "gracetech_adis.log"
"==== Script run at $(Get-Date) ====" | Out-File -FilePath $logFile -Append

# Log and progress helper
function Write-Activity {
    param($Message)
    $Message | Out-File -FilePath $logFile -Append
}

# Checking Docker Status
Write-Host "Checking Docker status..."
Write-Activity "Checking Docker status..."

for ($i = 0; $i -le 30; $i += 10) {
    Write-Progress -Activity "Detecting Docker..." -Status "$i% complete" -PercentComplete $i
    Start-Sleep -Milliseconds 300
}

$dockerStatus = docker info --format '{{.ServerVersion}}' 2>$null
Write-Activity "Docker status result: $dockerStatus"

# Check if Docker is running
if (-not $dockerStatus) {
    Write-Warning "Docker is not running. Please start Docker Desktop."
    Write-Activity "Docker is NOT running. Script terminated."
    exit 1
}
else {
    Write-Host "Docker is running. Version: $dockerStatus"
    Write-Activity "Docker is running. Version: $dockerStatus"
}

# Build and Run with progress
Write-Host "Starting services..."
Write-Activity "Starting docker-compose build and up..."

for ($i = 0; $i -le 100; $i += 20) {
    Write-Progress -Activity "Launching ADIS-PHAS Services..." -Status "$i% complete" -PercentComplete $i
    Start-Sleep -Milliseconds 500
}

docker-compose up --build -d | Out-File -FilePath $logFile -Append

Write-Host "Services started!"
Write-Activity "Services started successfully."

Write-Host "Backend API: http://localhost:8000/docs"
Write-Host "Streamlit UI: http://localhost:8501"
Write-Host "To stop: docker-compose down"

# Automatically open API and UI in default browser
Start-Sleep -Seconds 2  # allow services a moment to start

Write-Host "Opening Backend API documentation..."
Start-Process "http://localhost:8000/docs"

Write-Host "Opening Streamlit UI..."
Start-Process "http://localhost:8501"

Write-Activity "Backend: http://localhost:8000/docs"
Write-Activity "UI: http://localhost:8501"
Write-Activity "=== Script completed ==="
