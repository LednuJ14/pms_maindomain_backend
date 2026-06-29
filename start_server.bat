@echo off
echo Starting JACS Backend Server...
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Set environment variables
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_DEBUG=1

REM Start the server
echo.
echo Starting Flask server on http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
python app.py

pause
