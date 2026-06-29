"""
Request/Response logging middleware
Logs all API requests and responses with masking of sensitive data
"""
import time
import uuid
from flask import request, g, current_app
from functools import wraps


# Fields to mask in logs
SENSITIVE_FIELDS = {
    'password', 'password_hash', 'current_password', 'new_password', 'confirm_password',
    'access_token', 'refresh_token', 'token', 'authorization',
    'secret_key', 'api_key', 'api_secret',
    'credit_card', 'card_number', 'cvv', 'cvc'
}


def mask_sensitive_data(data, depth=0, max_depth=3):
    """
    Recursively mask sensitive fields in data structures.
    
    Args:
        data: Data structure to mask (dict, list, or primitive)
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        
    Returns:
        Masked data structure
    """
    if depth > max_depth:
        return '[max depth reached]'
    
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            # Check if key contains sensitive field name
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                masked[key] = '[REDACTED]'
            else:
                masked[key] = mask_sensitive_data(value, depth + 1, max_depth)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item, depth + 1, max_depth) for item in data]
    else:
        return data


def generate_request_id():
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())


def log_request():
    """Log incoming request."""
    g.request_id = generate_request_id()
    g.request_start_time = time.time()
    
    # Get request data
    request_data = None
    if request.is_json:
        try:
            request_data = request.get_json(silent=True)
        except Exception:
            request_data = None
    
    # Mask sensitive data
    masked_data = mask_sensitive_data(request_data) if request_data else None
    
    # Log request
    log_data = {
        'request_id': g.request_id,
        'method': request.method,
        'path': request.path,
        'query_string': request.query_string.decode() if request.query_string else None,
        'remote_addr': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'content_type': request.content_type,
        'data': masked_data
    }
    
    current_app.logger.info(f'Request: {request.method} {request.path}', extra=log_data)


def log_response(response):
    """Log outgoing response."""
    # Calculate response time
    response_time = None
    if hasattr(g, 'request_start_time'):
        response_time = (time.time() - g.request_start_time) * 1000  # Convert to milliseconds
    
    # Get response data
    response_data = None
    try:
        if response.is_json:
            response_data = response.get_json()
    except Exception:
        pass
    
    # Mask sensitive data
    masked_data = mask_sensitive_data(response_data) if response_data else None
    
    # Log response
    log_data = {
        'request_id': getattr(g, 'request_id', None),
        'status_code': response.status_code,
        'response_time_ms': round(response_time, 2) if response_time else None,
        'data': masked_data
    }
    
    log_level = 'info' if response.status_code < 400 else 'warning' if response.status_code < 500 else 'error'
    getattr(current_app.logger, log_level)(
        f'Response: {response.status_code} ({response_time:.2f}ms)' if response_time else f'Response: {response.status_code}',
        extra=log_data
    )
    
    # Add request ID to response headers
    if hasattr(g, 'request_id'):
        response.headers['X-Request-ID'] = g.request_id
    
    return response


def init_request_logging(app):
    """
    Initialize request/response logging middleware.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def before_request():
        # Only log API routes
        if request.path.startswith('/api/'):
            log_request()
    
    @app.after_request
    def after_request(response):
        # Only log API routes
        if request.path.startswith('/api/'):
            log_response(response)
        return response

