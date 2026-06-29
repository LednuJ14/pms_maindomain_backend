# JACS Cebu Property Management - Backend Setup (PowerShell)

Write-Host "===============================================" -ForegroundColor Green
Write-Host "JACS Cebu Property Management - Backend Setup" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""

# Check if Python is installed
$pythonCheck = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ and try again" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
} else {
    Write-Host "Python found: $pythonCheck" -ForegroundColor Green
}

# Check if we're in the right directory
if (-not (Test-Path "requirements.txt")) {
    Write-Host "❌ Error: requirements.txt not found" -ForegroundColor Red
    Write-Host "Please make sure you're in the backend directory" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "[1/7] Checking virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error: Failed to create virtual environment" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "✓ Virtual environment already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/7] Activating virtual environment..." -ForegroundColor Cyan
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Host "⚠️  Using system Python (virtual environment activation failed)" -ForegroundColor Yellow
}
Write-Host "✓ Virtual environment activated" -ForegroundColor Green

Write-Host ""
Write-Host "[3/7] Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Failed to install dependencies" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green

Write-Host ""
Write-Host "[4/7] Checking environment configuration..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    if (Test-Path "env.example") {
        Write-Host "Creating .env file from template..." -ForegroundColor Yellow
        Copy-Item "env.example" ".env"
        Write-Host "✓ .env file created from template" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  IMPORTANT: Please edit .env file with your database settings" -ForegroundColor Yellow
        Write-Host "    - Update MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE" -ForegroundColor Yellow
        Write-Host "    - Change SECRET_KEY and JWT_SECRET_KEY for security" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Continuing with default settings..." -ForegroundColor Yellow
    } else {
        Write-Host "❌ Error: No .env file found and no env.example template" -ForegroundColor Red
        Write-Host "Please create a .env file with your configuration" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "✓ .env file exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "[5/6] Skipping database connection test..." -ForegroundColor Cyan
Write-Host "Database connection will be tested during initialization." -ForegroundColor Yellow

Write-Host ""
Write-Host "[6/6] Initializing database..." -ForegroundColor Cyan
python init_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Database initialization failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "Starting Flask application..." -ForegroundColor Cyan
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "🚀 Backend server starting..." -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "API will be available at: http://localhost:5000" -ForegroundColor White
Write-Host ""
Write-Host "Default accounts:" -ForegroundColor White
Write-Host "👤 Admin: admin@jacs-cebu.com / Admin123!" -ForegroundColor White
Write-Host "🏢 Manager: manager@example.com / Manager123!" -ForegroundColor White
Write-Host "🏠 Tenant: tenant@example.com / Tenant123!" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""

# Set environment variable for development
$env:FLASK_ENV = "development"

# Start the Flask application
python app.py

Write-Host ""
Write-Host "Server stopped." -ForegroundColor Yellow