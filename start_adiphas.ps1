# ============================================
# ADIPHAS Startup Script
# Autonomous Disease Intelligence Platform
# ============================================

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ADIPHAS - Autonomous Intelligence Engine  " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[0/4] Cleaning up previous instances on ports 8000, 8501..." -ForegroundColor Yellow

function Kill-StaleProcesses {
    $staleConns = Get-NetTCPConnection -LocalPort 8000, 8501 -State Listen -ErrorAction SilentlyContinue
    if ($staleConns) {
        foreach ($conn in $staleConns) {
            $pidToKill = $conn.OwningProcess
            if ($pidToKill -gt 0 -and $pidToKill -ne $PID) {
                Write-Host "      Killing stale process ID: $pidToKill (Port $($conn.LocalPort))" -ForegroundColor DarkGray
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 2
    }
}

Kill-StaleProcesses

# Activate virtual environment
$venvActivate = Join-Path $PSScriptRoot "myenv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    Write-Host "[1/4] Activating virtual environment..." -ForegroundColor Yellow
    & $venvActivate
} else {
    Write-Host "[ERROR] Virtual environment not found at: $venvActivate" -ForegroundColor Red
    exit 1
}

# Check .env
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
    Write-Host "[2/4] .env file found." -ForegroundColor Green
} else {
    Write-Host "[WARNING] No .env file found. AI features may be disabled." -ForegroundColor DarkYellow
}

# Start Backend as a background process (NOT Start-Job, which swallows output)
Write-Host "[3/4] Starting Backend API on port 8000..." -ForegroundColor Yellow
$backendProc = Start-Process -FilePath "$PSScriptRoot\myenv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $PSScriptRoot `
    -PassThru -NoNewWindow `
    -RedirectStandardError "$PSScriptRoot\logs\backend_stderr.log"

# Wait for backend to finish cold-starting (spaCy + Gemini init takes ~15-20s)
Write-Host "[...] Waiting for backend cold start (up to 30s)..." -ForegroundColor Gray
$healthy = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/healthcheck" -TimeoutSec 3 -ErrorAction Stop
        if ($response.status -eq "ok") {
            $healthy = $true
            Write-Host "[OK]  Backend is ONLINE (v$($response.version))" -ForegroundColor Green
            Write-Host "      spaCy: $($response.spacy_loaded) | Gemini: $($response.gemini_active)" -ForegroundColor Gray
            break
        }
    } catch {
        Write-Host "      ...still loading ($($i*2)s)" -ForegroundColor DarkGray
    }
}

if (-not $healthy) {
    Write-Host "[WARNING] Backend did not respond to healthcheck within 30s." -ForegroundColor Red
    Write-Host "      Check: logs\adiphas_agent.log and logs\backend_stderr.log" -ForegroundColor Red
}

# Start Streamlit UI
Write-Host "[4/4] Starting Streamlit UI on port 8501..." -ForegroundColor Yellow
$uiProc = Start-Process -FilePath "$PSScriptRoot\myenv\Scripts\python.exe" `
    -ArgumentList "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501", "--server.headless", "true" `
    -WorkingDirectory $PSScriptRoot `
    -PassThru -NoNewWindow

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ADIPHAS IS RUNNING                        " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend API:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  Streamlit UI: http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Autonomous agents cycle every 15 minutes." -ForegroundColor Gray
Write-Host "  Logs: logs\adiphas_agent.log (tailed below)" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

# Open browser
Start-Process "http://localhost:8501"

# STREAM THE LIVE LOG FILE (this is what the user sees)
Write-Host "--- Live Agent Log Stream ---" -ForegroundColor DarkYellow
Get-Content -Path "$PSScriptRoot\logs\adiphas_agent.log" -Wait -Tail 20
