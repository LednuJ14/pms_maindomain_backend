"""
Main Flask Application Entry Point
"""
import os
from app import create_app, db
from flask_migrate import upgrade

# Create Flask application
app = create_app()

if __name__ == '__main__':
    # Auto-create tables if they don't exist
    with app.app_context():
        # Always create missing tables first
        db.create_all()
        print("✓ Database base tables verified/created.")

    # Run the application
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
