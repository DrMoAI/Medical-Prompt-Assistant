@echo off
title 🛑 Shutting Down Medical Prompt Assistant

echo Killing Ollama (port 11434)...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":11434" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo Killing Celery worker processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Celery Worker*" >nul 2>&1

echo Killing Flask app processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Flask App*" >nul 2>&1

echo 🔁 Optional: Also killing all Python processes tied to CMD titles...
for /f "tokens=2 delims=," %%a in ('tasklist /v /fi "imagename eq python.exe" /fo csv ^| findstr /i "Celery Flask"') do taskkill /PID %%a /F >nul 2>&1

echo 🧹 Cleanup complete.
pause
