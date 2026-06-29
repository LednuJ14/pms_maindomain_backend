@echo off
echo ===============================================
echo JACS Cebu Property Management - Backend Setup
echo ===============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist "requirements.txt" (
    echo Error: requirements.txt not found
    echo Please make sure you're in the backend directory
    pause
    exit /b 1
)

echo [1/7] Checking virtual environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✓ Virtual environment created
) else (
    echo ✓ Virtual environment already exists
)

echo.
echo [2/7] Activating virtual environment...
call venv\Scripts\activate
if %errorlevel% neq 0 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)
echo ✓ Virtual environment activated

echo.
echo [3/7] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)
echo ✓ Dependencies installed

echo.
echo [4/7] Checking environment configuration...
if not exist ".env" (
    if exist "env.example" (
        echo Creating .env file from template...
        copy env.example .env >nul
        echo ✓ .env file created from template
        echo.
        echo ⚠️  IMPORTANT: Please edit .env file with your database settings
        echo    - Update MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
        echo    - Change SECRET_KEY and JWT_SECRET_KEY for security
        echo.
        echo Continuing with default settings...
    ) else (
        echo Error: No .env file found and no env.example template
        echo Please create a .env file with your configuration
        pause
        exit /b 1
    )
) else (
    echo ✓ .env file exists
)

echo.
echo [5/6] Skipping database connection test...
echo Database connection will be tested during initialization.

echo.
echo [6/6] Initializing database...
python init_db.py
if %errorlevel% neq 0 (
    echo Error: Database initialization failed
    pause
    exit /b 1
)

echo.
echo Starting Flask application...
echo.
echo ===============================================
echo 🚀 Backend server starting...
echo ===============================================
echo.
echo API will be available at: http://localhost:5000
echo.
echo Default accounts:
echo 👤 Admin: admin@jacs-cebu.com / Admin123!
echo 🏢 Manager: manager@example.com / Manager123!
echo 🏠 Tenant: tenant@example.com / Tenant123!
echo.
echo Press Ctrl+C to stop the server
echo ===============================================
echo.

echo Starting Python app.py...
python app.py
set app_exit_code=%errorlevel%

echo.
echo Server stopped with exit code: %app_exit_code%
if %app_exit_code% neq 0 (
    echo Error occurred! Press any key to see details...
    pause
) else (
    echo Server stopped normally.
)
