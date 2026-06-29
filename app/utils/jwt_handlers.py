"""
JWT token handlers and callbacks
"""
from flask import jsonify
from flask_jwt_extended import get_jwt
from app.models.blacklisted_token import BlacklistedToken

def register_jwt_handlers(app, jwt_manager):
    """Register JWT handlers with Flask-JWT-Extended."""
    
    @jwt_manager.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Check if JWT token is blacklisted.

        Our DB stores the JWT ID in column 'jti'. Older code used 'token'.
        Query defensively for compatibility.
        """
        jti = jwt_payload['jti']
        # prefer jti column
        try:
            if hasattr(BlacklistedToken, 'jti'):
                return BlacklistedToken.query.filter_by(jti=jti).first() is not None
            # fallback for legacy schemas
            if hasattr(BlacklistedToken, 'token'):
                return BlacklistedToken.query.filter_by(token=jti).first() is not None
        except Exception:
            # if table missing or mismatched, assume not blacklisted
            return False
        return False
    
    @jwt_manager.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Handle expired tokens."""
        return jsonify({
            'error': 'Token expired',
            'message': 'The JWT token has expired',
            'status_code': 401
        }), 401
    
    @jwt_manager.invalid_token_loader
    def invalid_token_callback(error):
        """Handle invalid tokens."""
        return jsonify({
            'error': 'Invalid token',
            'message': 'The JWT token is invalid',
            'status_code': 401
        }), 401
    
    @jwt_manager.unauthorized_loader
    def missing_token_callback(error):
        """Handle missing tokens."""
        return jsonify({
            'error': 'Authorization required',
            'message': 'JWT token is required to access this endpoint',
            'status_code': 401
        }), 401
    
    @jwt_manager.needs_fresh_token_loader
    def token_not_fresh_callback(jwt_header, jwt_payload):
        """Handle non-fresh tokens when fresh token is required."""
        return jsonify({
            'error': 'Fresh token required',
            'message': 'A fresh JWT token is required for this action',
            'status_code': 401
        }), 401
    
    @jwt_manager.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        """Handle revoked/blacklisted tokens."""
        return jsonify({
            'error': 'Token revoked',
            'message': 'The JWT token has been revoked',
            'status_code': 401
        }), 401
    
    @jwt_manager.user_identity_loader
    def user_identity_lookup(user):
        """Convert user object to JSON serializable identity."""
        if hasattr(user, 'id'):
            return str(user.id)  # Convert to string for JWT compatibility
        return str(user)
    
    @jwt_manager.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        """Load user from JWT token identity."""
        from app.models.user import User
        identity = jwt_data["sub"]
        # Convert identity back to integer for database lookup
        try:
            user_id = int(identity) if isinstance(identity, str) else identity
            return User.query.filter_by(id=user_id).one_or_none()
        except (ValueError, TypeError):
            return None
    
    @jwt_manager.additional_claims_loader
    def add_claims_to_jwt(identity):
        """Add additional claims to JWT token."""
        from app.models.user import User
        # Convert identity to integer for database lookup
        try:
            user_id = int(identity) if isinstance(identity, str) else identity
            user = User.query.get(user_id)
            if user:
                return {
                    'role': user.role.value,
                    'email': user.email,
                    'is_admin': user.is_admin(),
                    'is_manager': user.is_manager()
                }
        except (ValueError, TypeError):
            pass
        return {}
    
    @jwt_manager.token_verification_failed_loader
    def token_verification_failed_callback(jwt_header, jwt_payload):
        """Handle token verification failures."""
        return jsonify({
            'error': 'Token verification failed',
            'message': 'The JWT token could not be verified',
            'status_code': 401
        }), 401
