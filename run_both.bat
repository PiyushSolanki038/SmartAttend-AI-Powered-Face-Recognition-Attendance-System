@echo off
echo Starting SmartAttend Admin App and Student Portal...

start "SmartAttend - Admin App" "%~dp0venv\Scripts\python.exe" "%~dp0main.py"
start "SmartAttend - Student Portal" "%~dp0venv\Scripts\python.exe" -m uvicorn webportal.main:app --host 0.0.0.0 --port 8000

echo Both apps launched in separate windows.
echo Admin App: desktop window
echo Student Portal: http://localhost:8000
