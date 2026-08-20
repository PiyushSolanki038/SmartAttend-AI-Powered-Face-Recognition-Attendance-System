@echo off
"%~dp0venv\Scripts\python.exe" -m uvicorn webportal.main:app --host 0.0.0.0 --port 8000
