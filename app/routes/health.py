"""
Health check endpoints for monitoring and system status
"""
from flask import Blueprint, jsonify, current_app
from datetime import datetime
from app import db
from sqlalchemy import text

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
@health_bp.route('/health/liveness', methods=['GET'])
def health_check():
    """
    Basic liveness probe - indicates if the application is running.
    ---
    tags:
      - Health
    summary: Liveness probe
    description: Returns 200 if the application is running
    responses:
      200:
        description: Application is alive
        schema:
          type: object
          properties:
            status:
              type: string
              example: "healthy"
            timestamp:
              type: string
              example: "2024-01-01T00:00:00Z"
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'service': 'jacs-property-platform'
    }), 200


@health_bp.route('/health/readiness', methods=['GET'])
def readiness_check():
    """
    Readiness probe - checks if the application is ready to serve traffic.
    Checks database connectivity.
    ---
    tags:
      - Health
    summary: Readiness probe
    description: Returns 200 if the application is ready (database connected)
    responses:
      200:
        description: Application is ready
      503:
        description: Application is not ready
    """
    try:
        # Check database connectivity
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        
        return jsonify({
            'status': 'ready',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'checks': {
                'database': 'connected'
            }
        }), 200
    except Exception as e:
        current_app.logger.error(f'Readiness check failed: {str(e)}')
        return jsonify({
            'status': 'not_ready',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'checks': {
                'database': 'disconnected'
            },
            'error': str(e) if current_app.config.get('DEBUG') else 'Database connection failed'
        }), 503


@health_bp.route('/health/status', methods=['GET'])
def detailed_status():
    """
    Detailed system status - includes database, configuration, and system info.
    ---
    tags:
      - Health
    summary: Detailed system status
    description: Returns detailed system status including database connectivity
    security:
      - Bearer: []
    responses:
      200:
        description: System status
        schema:
          type: object
          properties:
            status:
              type: string
            timestamp:
              type: string
            version:
              type: string
            environment:
              type: string
            checks:
              type: object
    """
    status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'version': '1.0.0',
        'environment': current_app.config.get('FLASK_ENV', 'unknown'),
        'checks': {}
    }
    
    # Check database
    try:
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        status['checks']['database'] = {
            'status': 'connected',
            'type': 'mysql'
        }
    except Exception as e:
        status['status'] = 'degraded'
        status['checks']['database'] = {
            'status': 'disconnected',
            'error': str(e) if current_app.config.get('DEBUG') else 'Connection failed'
        }
    
    # Check configuration
    required_config = ['SECRET_KEY', 'JWT_SECRET_KEY', 'SQLALCHEMY_DATABASE_URI']
    missing_config = []
    for key in required_config:
        if not current_app.config.get(key):
            missing_config.append(key)
    
    if missing_config:
        status['status'] = 'degraded'
        status['checks']['configuration'] = {
            'status': 'incomplete',
            'missing': missing_config
        }
    else:
        status['checks']['configuration'] = {
            'status': 'complete'
        }
    
    http_status = 200 if status['status'] == 'healthy' else 503
    return jsonify(status), http_status

