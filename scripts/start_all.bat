@echo off

REM Activate Virtual Environment
CALL .\venv\Scripts\activate

REM Start Ollama server (LLaMA3 model)
START cmd /k "ollama serve"

REM Start Celery worker
START cmd /k "celery -A celery_worker.celery worker --loglevel=info --pool=solo"

REM Start Flask App
START cmd /k "python app.py"