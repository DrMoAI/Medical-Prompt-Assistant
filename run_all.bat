@echo off
title Medical Prompt Assistant Launcher
cd /d %~dp0

echo Activating virtual environment...
CALL .\venv\Scripts\activate

:: Ollama is only needed for the local model. Comment these two lines out if you use the API only.
echo Starting Ollama (port 11434)...
START "Ollama Server" cmd /k "ollama serve"
timeout /t 2 >nul

echo Launching Flask app...
START "Flask App" cmd /k "python app.py"

echo Done. Open http://localhost:5000
