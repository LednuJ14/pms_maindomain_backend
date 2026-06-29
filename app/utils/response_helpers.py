"""
Unified API response helpers for consistent response format across all routes
"""
from flask import jsonify
from typing import Any, Optional, Dict


def success_response(data: Any = None, message: Optional[str] = None, meta: Optional[Dict] = None, status: int = 200):
    """
    Create a standardized success response.
    
    Args:
        data: Response data (can be any JSON-serializable type)
        message: Optional success message
        meta: Optional metadata (pagination, etc.)
        status: HTTP status code (default: 200)
        
    Returns:
        tuple: (jsonify response, status code)
        
    Example:
        return success_response(
            data={'user': user_data},
            message='User retrieved successfully',
            meta={'page': 1, 'total': 100}
        )
    """
    response = {
        'success': True,
        'data': data,
        'error': None
    }
    
    if message:
        response['message'] = message
    
    if meta:
        response['meta'] = meta
    
    return jsonify(response), status


def error_response(message: str, status_code: int = 400, error_code: Optional[str] = None, 
                  details: Optional[Dict] = None, data: Any = None):
    """
    Create a standardized error response.
    
    Args:
        message: Error message
        status_code: HTTP status code (default: 400)
        error_code: Optional error code for programmatic handling
        details: Optional additional error details
        data: Optional data to include (e.g., validation errors)
        
    Returns:
        tuple: (jsonify response, status code)
        
    Example:
        return error_response(
            message='Validation failed',
            status_code=422,
            error_code='VALIDATION_ERROR',
            details={'field': 'email', 'reason': 'Invalid format'}
        )
    """
    response = {
        'success': False,
        'data': data,
        'error': {
            'message': message,
            'status_code': status_code
        }
    }
    
    if error_code:
        response['error']['code'] = error_code
    
    if details:
        response['error']['details'] = details
    
    return jsonify(response), status_code


def paginated_response(data: list, page: int, per_page: int, total: int, 
                      message: Optional[str] = None):
    """
    Create a standardized paginated response.
    
    Args:
        data: List of items for current page
        page: Current page number (1-indexed)
        per_page: Items per page
        total: Total number of items
        message: Optional message
        
    Returns:
        tuple: (jsonify response, status code)
        
    Example:
        return paginated_response(
            data=items,
            page=1,
            per_page=10,
            total=100
        )
    """
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    
    meta = {
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'next_page': page + 1 if page < total_pages else None,
            'prev_page': page - 1 if page > 1 else None
        }
    }
    
    return success_response(data=data, message=message, meta=meta, status=200)


# Convenience functions for common HTTP status codes
def bad_request(message: str = 'Bad Request', details: Optional[Dict] = None):
    """400 Bad Request"""
    return error_response(message, 400, 'BAD_REQUEST', details)


def unauthorized(message: str = 'Authentication required', details: Optional[Dict] = None):
    """401 Unauthorized"""
    return error_response(message, 401, 'UNAUTHORIZED', details)


def forbidden(message: str = 'Access forbidden', details: Optional[Dict] = None):
    """403 Forbidden"""
    return error_response(message, 403, 'FORBIDDEN', details)


def not_found(message: str = 'Resource not found', details: Optional[Dict] = None):
    """404 Not Found"""
    return error_response(message, 404, 'NOT_FOUND', details)


def conflict(message: str = 'Resource conflict', details: Optional[Dict] = None):
    """409 Conflict"""
    return error_response(message, 409, 'CONFLICT', details)


def validation_error(message: str = 'Validation failed', details: Optional[Dict] = None):
    """422 Unprocessable Entity"""
    return error_response(message, 422, 'VALIDATION_ERROR', details)


def internal_error(message: str = 'Internal server error', details: Optional[Dict] = None):
    """500 Internal Server Error"""
    return error_response(message, 500, 'INTERNAL_ERROR', details)

