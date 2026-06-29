"""
Global error handlers for Flask application
"""
from flask import jsonify
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from marshmallow import ValidationError

def handle_api_error(status_code, message, details=None):
    """Helper function to create consistent API error responses."""
    error_response = {
        'error': get_error_name(status_code),
        'message': message,
        'status_code': status_code
    }
    
    if details:
        error_response['details'] = details
    
    return jsonify(error_response), status_code

def get_error_name(status_code):
    """Get error name based on status code."""
    error_names = {
        400: 'Bad Request',
        401: 'Unauthorized', 
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        409: 'Conflict',
        422: 'Unprocessable Entity',
        429: 'Too Many Requests',
        500: 'Internal Server Error'
    }
    return error_names.get(status_code, 'Error')

from app.errors import AppError

def register_error_handlers(app):
    """Register error handlers with Flask app."""
    
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify({
            'error': type(error).__name__,
            'message': str(error),
            'status_code': getattr(error, 'status_code', 400),
            'details': getattr(error, 'details', {})
        }), getattr(error, 'status_code', 400)

    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors."""
        return jsonify({
            'error': 'Bad Request',
            'message': 'The request could not be understood by the server',
            'status_code': 400
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 Unauthorized errors."""
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required',
            'status_code': 401
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors."""
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource',
            'status_code': 403
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors."""
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found',
            'status_code': 404
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        return jsonify({
            'error': 'Method Not Allowed',
            'message': 'The method is not allowed for the requested URL',
            'status_code': 405
        }), 405
    
    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        """Handle 429 Too Many Requests errors."""
        return jsonify({
            'error': 'Too Many Requests',
            'message': 'Rate limit exceeded. Please try again later',
            'status_code': 429,
            'retry_after': getattr(error, 'retry_after', None)
        }), 429
    
    @app.errorhandler(500)
    def internal_server_error(error):
        """Handle 500 Internal Server Error."""
        app.logger.error(f'Server Error: {error}')
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An internal server error occurred',
            'status_code': 500
        }), 500
    
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        """Handle Marshmallow validation errors."""
        return jsonify({
            'error': 'Validation Error',
            'message': 'Request data validation failed',
            'details': error.messages,
            'status_code': 400
        }), 400
    
    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        """Handle database integrity errors."""
        app.logger.error(f'Database Integrity Error: {error}')
        
        # Check for common integrity violations
        error_message = str(error.orig)
        
        if 'Duplicate entry' in error_message:
            if 'email' in error_message:
                message = 'Email address already exists'
            elif 'phone' in error_message:
                message = 'Phone number already exists'
            else:
                message = 'Duplicate entry detected'
        elif 'foreign key constraint' in error_message.lower():
            message = 'Referenced record does not exist'
        else:
            message = 'Database constraint violation'
        
        return jsonify({
            'error': 'Database Error',
            'message': message,
            'status_code': 409
        }), 409
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected errors."""
        app.logger.error(f'Unexpected Error: {error}', exc_info=True)
        
        # Don't expose internal error details in production
        if app.config.get('DEBUG'):
            message = str(error)
        else:
            message = 'An unexpected error occurred'
        
        return jsonify({
            'error': 'Unexpected Error',
            'message': message,
            'status_code': 500
        }), 500
