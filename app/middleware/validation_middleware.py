"""
Input validation middleware using Marshmallow schemas
"""
from functools import wraps
from flask import request, jsonify, current_app
from marshmallow import Schema, ValidationError as MarshmallowValidationError
from app.utils.input_validators import sanitize_string, sanitize_email, sanitize_integer


def validate_request(schema_class, location='json'):
    """
    Decorator to validate request data using Marshmallow schema.
    
    Args:
        schema_class: Marshmallow Schema class
        location: Where to get data from ('json', 'form', 'args', 'headers')
        
    Usage:
        @validate_request(UserSchema)
        def create_user():
            data = request.validated_data
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Get schema instance
                schema = schema_class()
                
                # Get data based on location
                if location == 'json':
                    data = request.get_json(silent=True) or {}
                elif location == 'form':
                    data = request.form.to_dict()
                elif location == 'args':
                    data = request.args.to_dict()
                elif location == 'headers':
                    data = dict(request.headers)
                else:
                    data = {}
                
                # Validate and deserialize
                validated_data = schema.load(data)
                
                # Store validated data in request for easy access
                request.validated_data = validated_data
                
                return f(*args, **kwargs)
                
            except MarshmallowValidationError as err:
                current_app.logger.warning(f'Validation error: {err.messages}')
                return jsonify({
                    'success': False,
                    'error': {
                        'message': 'Validation failed',
                        'code': 'VALIDATION_ERROR',
                        'status_code': 422,
                        'details': err.messages
                    }
                }), 422
            except Exception as e:
                current_app.logger.error(f'Validation middleware error: {str(e)}', exc_info=True)
                return jsonify({
                    'success': False,
                    'error': {
                        'message': 'Request validation error',
                        'code': 'VALIDATION_ERROR',
                        'status_code': 400
                    }
                }), 400
        
        return decorated_function
    return decorator


def sanitize_request_data(fields_to_sanitize=None):
    """
    Decorator to sanitize request data using input validators.
    
    Args:
        fields_to_sanitize: Dict mapping field names to sanitizer functions
                           Example: {'email': sanitize_email, 'name': sanitize_string}
    
    Usage:
        @sanitize_request_data({'email': sanitize_email, 'name': lambda x: sanitize_string(x, max_length=100)})
        def update_profile():
            data = request.sanitized_data
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Get request data
                data = request.get_json(silent=True) or request.form.to_dict() or {}
                
                # Sanitize fields
                sanitized_data = {}
                for key, value in data.items():
                    if key in (fields_to_sanitize or {}):
                        sanitizer = fields_to_sanitize[key]
                        sanitized_value = sanitizer(value) if value is not None else None
                        sanitized_data[key] = sanitized_value
                    else:
                        # Default: sanitize strings
                        if isinstance(value, str):
                            sanitized_data[key] = sanitize_string(value)
                        else:
                            sanitized_data[key] = value
                
                # Store sanitized data in request
                request.sanitized_data = sanitized_data
                
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f'Sanitization error: {str(e)}', exc_info=True)
                return jsonify({
                    'success': False,
                    'error': {
                        'message': 'Request sanitization error',
                        'code': 'SANITIZATION_ERROR',
                        'status_code': 400
                    }
                }), 400
        
        return decorated_function
    return decorator


# Example usage schemas (can be moved to separate schemas file)
class PaginationSchema(Schema):
    """Schema for pagination parameters."""
    from marshmallow import fields
    
    page = fields.Integer(load_default=1, validate=lambda x: x > 0)
    per_page = fields.Integer(load_default=10, validate=lambda x: 1 <= x <= 100)

