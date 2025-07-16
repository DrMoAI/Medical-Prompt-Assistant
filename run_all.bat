@echo off
title Medical Prompt Assistant Launcher
cd /d %~dp0

echo 🔄 Activating virtual environment...
CALL .\venv\Scripts\activate

echo 🧠 Starting Ollama (port 11434)...
START "Ollama Server" cmd /k "ollama serve"

:: Wait a bit to avoid port race
timeout /t 2 >nul

echo ⚙️ Starting Celery worker (Redis backend)...
START "Celery Worker" cmd /k "celery -A celery_worker.celery worker --loglevel=info --pool=solo"

:: Optional wait before Flask
timeout /t 1 >nul

echo 🚀 Launching Flask app...
START "Flask App" cmd /k "python app.py"

echo ✅ All services launched in separate windows.
