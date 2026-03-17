#!/bin/bash
# ============================================
# ADIPHAS Startup Script (Unix/macOS)
# Autonomous Disease Intelligence Platform
# ============================================

echo -e "\n\033[0;36m============================================\033[0m"
echo -e "\033[0;36m  ADIPHAS - Autonomous Intelligence Engine  \033[0m"
echo -e "\033[0;36m============================================\033[0m\n"

echo -e "\033[0;33m[0/4] Cleaning up previous instances on ports 8000, 8501...\033[0m"
# Kill anything on port 8000 (backend) or 8501 (UI)
fuser -k 8000/tcp 2>/dev/null
fuser -k 8501/tcp 2>/dev/null
sleep 2

# Activate virtual environment
if [ -f "myenv/bin/activate" ]; then
    echo -e "\033[0;33m[1/4] Activating virtual environment...\033[0m"
    source myenv/bin/activate
elif [ -f "myenv/Scripts/activate" ]; then
    echo -e "\033[0;33m[1/4] Activating virtual environment (Windows bash)...\033[0m"
    source myenv/Scripts/activate
else
    echo -e "\033[0;31m[ERROR] Virtual environment 'myenv' not found.\033[0m"
    exit 1
fi

# Check .env
if [ -f ".env" ]; then
    echo -e "\033[0;32m[2/4] .env file found.\033[0m"
else
    echo -e "\033[0;33m[WARNING] No .env file found. AI features may be disabled.\033[0m"
fi

# Ensure log directory exists
mkdir -p logs

# Start Backend as a background process
echo -e "\033[0;33m[3/4] Starting Backend API on port 8000...\033[0m"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to finish cold-starting
echo -e "\033[0;37m[...] Waiting for backend cold start (up to 30s)...\033[0m"
healthy=false
for i in {1..15}; do
    sleep 2
    if curl -s http://localhost:8000/healthcheck | grep -q '"status":"ok"'; then
        healthy=true
        echo -e "\033[0;32m[OK]  Backend is ONLINE\033[0m"
        break
    else
        echo -e "\033[1;30m      ...still loading ($((i*2))s)\033[0m"
    fi
done

if [ "$healthy" = false ]; then
    echo -e "\033[0;31m[WARNING] Backend did not respond to healthcheck within 30s.\033[0m"
    echo -e "\033[0;31m      Check: logs/adiphas.log for details\033[0m"
fi

# Start Streamlit UI
echo -e "\033[0;33m[4/4] Starting Streamlit UI on port 8501...\033[0m"
python -m streamlit run ui/app.py --server.port 8501 --server.headless true &
UI_PID=$!

sleep 3

echo -e "\n\033[0;32m============================================\033[0m"
echo -e "\033[0;32m  ADIPHAS IS RUNNING                        \033[0m"
echo -e "\033[0;32m============================================\033[0m\n"
echo -e "\033[0;36m  Backend API:  http://localhost:8000/docs\033[0m"
echo -e "\033[0;36m  Streamlit UI: http://localhost:8501\033[0m\n"
echo -e "\033[0;37m  Autonomous agents cycle every 15 minutes.\033[0m"
echo -e "\033[0;37m  Press Ctrl+C to stop.\033[0m\n"

# Open browser if possible
if command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8501"
elif command -v open &> /dev/null; then
    open "http://localhost:8501"
fi

echo -e "\033[0;33m--- Live Agent Log Stream ---\033[0m"
touch logs/adiphas.log
tail -f logs/adiphas.log

# Cleanup on exit
trap "kill $BACKEND_PID $UI_PID 2>/dev/null; exit 0" SIGINT SIGTERM
