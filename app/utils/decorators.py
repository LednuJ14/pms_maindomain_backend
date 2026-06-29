"""
Authentication and authorization decorators
"""
from functools import wraps
from flask import jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.user import User, UserRole
from app.models.blacklisted_token import BlacklistedToken

def auth_required(f):
    """
    Decorator that requires valid JWT authentication.
    Allows OPTIONS requests to pass through for CORS preflight.
    """
    @wraps(f)
    @jwt_required(optional=True)
    def decorated_function(*args, **kwargs):
        from flask import request
        
        # Allow OPTIONS requests to pass through for CORS preflight
        if request.method == 'OPTIONS':
            return f(None, *args, **kwargs)
        
        # For non-OPTIONS requests, require authentication
        try:
            current_user_id = get_jwt_identity()
        except Exception:
            current_user_id = None
        
        # If no token provided for non-OPTIONS request, require authentication
        if not current_user_id:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please provide a valid authentication token'
            }), 401
        
        # Check if token is blacklisted (if blacklist functionality is implemented)
        try:
            from app.models.blacklist import BlacklistedToken
            jti = get_jwt()['jti']
            if BlacklistedToken.check_blacklist(jti):
                return jsonify({
                    'error': 'Token has been revoked',
                    'message': 'Please log in again'
                }), 401
        except (ImportError, KeyError):
            # Blacklist functionality not implemented or JTI not available
            pass
        
        # Get current user
        # Convert identity to integer if it's a string
        try:
            user_id = int(current_user_id) if isinstance(current_user_id, str) else current_user_id
            current_user = User.query.get(user_id)
        except (ValueError, TypeError):
            current_user = None
        
        if not current_user:
            return jsonify({
                'error': 'User not found',
                'message': 'Invalid user token'
            }), 401
        
        if not current_user.is_active_user():
            return jsonify({
                'error': 'Account inactive',
                'message': 'Your account has been deactivated'
            }), 401
        
        # Check email verification for tenants and managers
        if (hasattr(current_user, 'role') and current_user.role in [UserRole.TENANT, UserRole.MANAGER]):
            email_not_verified = (hasattr(current_user, 'email_verified') and not current_user.email_verified)
            status_pending = (hasattr(current_user, 'status') and 
                            hasattr(current_user.status, 'value') and 
                            current_user.status.value == 'PENDING_VERIFICATION')
            
            if email_not_verified or status_pending:
                return jsonify({
                    'error': 'Email verification required',
                    'message': 'Please verify your email address to access this resource',
                    'verification_required': True
                }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def admin_required(f):
    """
    Decorator that requires admin role.
    Allows OPTIONS requests to pass through for CORS preflight.
    """
    @wraps(f)
    @auth_required
    def decorated_function(current_user, *args, **kwargs):
        from flask import request
        
        # Allow OPTIONS requests to pass through for CORS preflight
        if request.method == 'OPTIONS' or current_user is None:
            return f(current_user, *args, **kwargs)
        
        if not current_user.is_admin():
            return jsonify({
                'error': 'Insufficient permissions',
                'message': 'Admin access required'
            }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def manager_required(f):
    """
    Decorator that requires manager or admin role.
    """
    @wraps(f)
    @auth_required
    def decorated_function(current_user, *args, **kwargs):
        if not current_user.can_manage_properties():
            return jsonify({
                'error': 'Insufficient permissions',
                'message': 'Property manager or admin access required'
            }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def tenant_required(f):
    """
    Decorator that requires tenant role or allows admin access.
    """
    @wraps(f)
    @auth_required
    def decorated_function(current_user, *args, **kwargs):
        if not (current_user.is_tenant() or current_user.is_admin()):
            return jsonify({
                'error': 'Insufficient permissions',
                'message': 'Tenant access required'
            }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def owner_or_admin_required(f):
    """
    Decorator that allows access to resource owner or admin.
    Expects 'user_id' parameter in the route.
    """
    @wraps(f)
    @auth_required
    def decorated_function(current_user, *args, **kwargs):
        # Get user_id from kwargs (route parameter)
        target_user_id = kwargs.get('user_id')
        
        # Allow admin access or owner access
        if not (current_user.is_admin() or current_user.id == target_user_id):
            return jsonify({
                'error': 'Insufficient permissions',
                'message': 'You can only access your own resources'
            }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def subscription_required(f):
    """
    Decorator that requires active subscription for property managers.
    """
    @wraps(f)
    @manager_required
    def decorated_function(current_user, *args, **kwargs):
        # Admin users bypass subscription check
        if current_user.is_admin():
            return f(current_user, *args, **kwargs)
        
        # Check if user has active subscription
        if not current_user.subscription or not current_user.subscription.is_active():
            return jsonify({
                'error': 'Subscription required',
                'message': 'Active subscription required to access this feature'
            }), 402  # Payment Required
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def property_limit_check(f):
    """
    Decorator that checks if user can add more properties based on subscription.
    """
    @wraps(f)
    @subscription_required
    def decorated_function(current_user, *args, **kwargs):
        # Admin users bypass property limits
        if current_user.is_admin():
            return f(current_user, *args, **kwargs)
        
        # Check property limits
        if not current_user.subscription.can_add_property():
            return jsonify({
                'error': 'Property limit reached',
                'message': f'Your current plan allows up to {current_user.subscription.plan.max_properties} properties. Please upgrade your subscription.',
                'current_usage': current_user.subscription.properties_used,
                'limit': current_user.subscription.plan.max_properties
            }), 403
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function

def rate_limit_exempt(f):
    """
    Decorator to exempt routes from rate limiting.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    
    # Mark function as rate limit exempt
    decorated_function._rate_limit_exempt = True
    return decorated_function

def validate_json_content_type(f):
    """
    Decorator that validates Content-Type is application/json for POST/PUT requests.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request
        
        if request.method in ['POST', 'PUT', 'PATCH']:
            if not request.is_json:
                return jsonify({
                    'error': 'Invalid content type',
                    'message': 'Content-Type must be application/json'
                }), 400
        
        return f(*args, **kwargs)
    
    return decorated_function
