#!/bin/bash

echo "==============================================="
echo "JACS Cebu Property Management - Backend Setup"
echo "==============================================="
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found"
    echo "Please make sure you're in the backend directory"
    exit 1
fi

echo "[1/7] Checking virtual environment..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment"
        exit 1
    fi
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

echo
echo "[2/7] Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi
echo "✓ Virtual environment activated"

echo
echo "[3/7] Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi
echo "✓ Dependencies installed"

echo
echo "[4/7] Checking environment configuration..."
if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        echo "Creating .env file from template..."
        cp env.example .env
        echo "✓ .env file created from template"
        echo
        echo "⚠️  IMPORTANT: Please edit .env file with your database settings"
        echo "    - Update MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE"
        echo "    - Change SECRET_KEY and JWT_SECRET_KEY for security"
        echo
        echo "Press Enter to continue after updating .env file..."
        read
    else
        echo "Error: No .env file found and no env.example template"
        echo "Please create a .env file with your configuration"
        exit 1
    fi
else
    echo "✓ .env file exists"
fi

echo
echo "[5/7] Testing database connection..."
python3 -c "
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        from app import db
        db.engine.connect()
    print('✓ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    print('Please check your database settings in .env file')
    exit(1)
"
if [ $? -ne 0 ]; then
    echo
    echo "Database connection failed. Please check:"
    echo "- MySQL server is running"
    echo "- Database credentials in .env file are correct"
    echo "- Database exists (create it if needed)"
    exit 1
fi

echo
echo "[6/7] Initializing database..."
python3 init_db.py
if [ $? -ne 0 ]; then
    echo "Error: Database initialization failed"
    exit 1
fi

echo
echo "[7/7] Starting Flask application..."
echo
echo "==============================================="
echo "🚀 Backend server starting..."
echo "==============================================="
echo
echo "API will be available at: http://localhost:5000"
echo
echo "Default accounts:"
echo "👤 Admin: admin@jacs-cebu.com / Admin123!"
echo "🏢 Manager: manager@example.com / Manager123!"
echo "🏠 Tenant: tenant@example.com / Tenant123!"
echo
echo "Press Ctrl+C to stop the server"
echo "==============================================="
echo

python3 app.py
