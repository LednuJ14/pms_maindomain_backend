"""
Auth controller (v2): Thin layer that delegates to AuthServiceV2
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db, limiter
from app.utils.decorators import validate_json_content_type
from app.services.auth_service_v2 import AuthServiceV2, AuthValidationError, AuthDomainError

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
@validate_json_content_type
@limiter.limit("20 per minute")
def register():
    """
    Register a new user
    ---
    tags:
      - Authentication
    summary: Register a new user account
    description: Creates a new user account with email, password, and user details
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
            - first_name
            - last_name
            - role
          properties:
            email:
              type: string
              format: email
            password:
              type: string
              format: password
            first_name:
              type: string
            last_name:
              type: string
            role:
              type: string
              enum: [tenant, property_manager]
            phone:
              type: string
    responses:
      201:
        description: User registered successfully
        schema:
          type: object
          properties:
            message:
              type: string
            user:
              type: object
      400:
        description: Validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.register(request.get_json() or {})
        return jsonify(data), 201
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except AuthDomainError as e:
        # domain errors on register should be surfaced with 400 to help UI
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Registration error: {e}')
        return jsonify({'error': 'Registration failed', 'message': 'An error occurred during registration'}), 500


@auth_bp.route('/login', methods=['POST'])
@validate_json_content_type
def login():
    """
    User login
    ---
    tags:
      - Authentication
    summary: Authenticate user and get access token
    description: Login with email and password to receive JWT tokens
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
            password:
              type: string
              format: password
    responses:
      200:
        description: Login successful
        schema:
          type: object
          properties:
            access_token:
              type: string
            refresh_token:
              type: string
            user:
              type: object
      401:
        description: Invalid credentials
      423:
        description: Account locked
      403:
        description: Account suspended or inactive
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.login(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        # Handle failed login attempts
        if str(e) == 'Invalid credentials':
            payload = request.get_json() or {}
            from app.repositories.user_repository import UserRepository
            user = UserRepository().get_by_email(payload.get('email', ''))
            service.handle_failed_login(user)
        # Return error based on type
        code = 401 if str(e) in ['Invalid credentials'] else 423 if 'locked' in str(e).lower() else 403 if 'suspended' in str(e).lower() or 'inactive' in str(e).lower() else 400
        return jsonify({'error': str(e), **e.details}), code
    except Exception as e:
        current_app.logger.error(f'Login error: {e}')
        return jsonify({'error': 'Login failed', 'message': 'An error occurred during login'}), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    """
    Refresh access token
    ---
    tags:
      - Authentication
    summary: Get a new access token using refresh token
    description: Use a valid refresh token to obtain a new access token
    security:
      - Bearer: []
    responses:
      200:
        description: Token refreshed successfully
        schema:
          type: object
          properties:
            access_token:
              type: string
      401:
        description: Invalid or expired refresh token
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.refresh(get_jwt_identity())
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 401
    except Exception as e:
        current_app.logger.error(f'Token refresh error: {e}')
        return jsonify({'error': 'Token refresh failed', 'message': 'Unable to refresh access token'}), 500


@auth_bp.route('/verify-2fa', methods=['POST'])
@validate_json_content_type
def verify_two_factor():
    """
    Verify two-factor authentication
    ---
    tags:
      - Authentication
    summary: Verify 2FA code
    description: Verify the two-factor authentication code after initial login
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - code
          properties:
            email:
              type: string
              format: email
            code:
              type: string
              description: 2FA verification code
    responses:
      200:
        description: 2FA verified successfully
        schema:
          type: object
          properties:
            access_token:
              type: string
            refresh_token:
              type: string
      400:
        description: Invalid code or validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.verify_two_factor(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'2FA verify error: {e}')
        return jsonify({'error': 'Verification failed'}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    User logout
    ---
    tags:
      - Authentication
    summary: Logout and invalidate tokens
    description: Logout the current user and blacklist their tokens
    security:
      - Bearer: []
    responses:
      200:
        description: Logout successful
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Server error
    """
    try:
        token = get_jwt()
        service = AuthServiceV2()
        data = service.logout(
            jti=token['jti'],
            token_type=token['type'],
            expires_at=datetime.fromtimestamp(token['exp']),
            current_user_id=get_jwt_identity()
        )
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Logout error: {e}')
        return jsonify({'error': 'Logout failed', 'message': 'An error occurred during logout'}), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get current user info
    ---
    tags:
      - Authentication
    summary: Get authenticated user information
    description: Returns the currently authenticated user's profile information
    security:
      - Bearer: []
    responses:
      200:
        description: User information retrieved successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            email:
              type: string
            first_name:
              type: string
            last_name:
              type: string
            role:
              type: string
      404:
        description: User not found
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.me(get_jwt_identity())
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 404
    except Exception as e:
        current_app.logger.error(f'Get current user error: {e}')
        return jsonify({'error': 'Failed to get user info', 'message': 'Unable to retrieve current user information'}), 500


@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
@validate_json_content_type
def change_password():
    """
    Change user password
    ---
    tags:
      - Authentication
    summary: Change the authenticated user's password
    description: Update the password for the currently authenticated user
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - current_password
            - new_password
          properties:
            current_password:
              type: string
              format: password
            new_password:
              type: string
              format: password
    responses:
      200:
        description: Password changed successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Validation error or incorrect current password
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.change_password(get_jwt_identity(), request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Change password error: {e}')
        return jsonify({'error': 'Password change failed', 'message': 'Unable to change password'}), 500


# Email verification endpoints
@auth_bp.route('/verify-email', methods=['POST'])
@validate_json_content_type
@limiter.limit("10 per minute")
def verify_email():
    """
    Verify email address
    ---
    tags:
      - Authentication
    summary: Verify user email with token
    description: Verify an email address using a verification token sent to the user
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - token
          properties:
            email:
              type: string
              format: email
            token:
              type: string
              description: Email verification token
    responses:
      200:
        description: Email verified successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Invalid token or validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.verify_email(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Email verification error: {e}')
        return jsonify({'error': 'Email verification failed', 'message': 'An error occurred during email verification'}), 500


@auth_bp.route('/check-verification-status', methods=['GET'])
@limiter.limit("30 per minute")
def check_verification_status():
    """
    Check email verification status
    ---
    tags:
      - Authentication
    summary: Check if an email has been verified
    description: Poll this endpoint to check if an email verification has been completed
    parameters:
      - in: query
        name: email
        type: string
        format: email
        required: true
        description: Email address to check
    responses:
      200:
        description: Verification status retrieved
        schema:
          type: object
          properties:
            verified:
              type: boolean
            email:
              type: string
      400:
        description: Email parameter missing
      500:
        description: Server error
    """
    try:
        email = request.args.get('email')
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        service = AuthServiceV2()
        data = service.check_verification_status({'email': email})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Check verification status error: {e}')
        return jsonify({'error': 'Failed to check verification status', 'message': 'An error occurred'}), 500


@auth_bp.route('/resend-verification', methods=['POST'])
@validate_json_content_type
@limiter.limit("5 per minute")
def resend_verification_email():
    """
    Resend verification email
    ---
    tags:
      - Authentication
    summary: Resend email verification link
    description: Request a new email verification link to be sent
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
          properties:
            email:
              type: string
              format: email
    responses:
      200:
        description: Verification email sent successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.resend_verification_email(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except AuthDomainError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        current_app.logger.error(f'Resend verification email error: {e}')
        return jsonify({'error': 'Failed to resend verification email', 'message': 'An error occurred while sending verification email'}), 500


# Password reset endpoints
@auth_bp.route('/forgot-password', methods=['POST'])
@validate_json_content_type
@limiter.limit("5 per minute")
def forgot_password():
    """
    Request password reset
    ---
    tags:
      - Authentication
    summary: Request password reset email
    description: Send a password reset link to the user's email address
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
          properties:
            email:
              type: string
              format: email
    responses:
      200:
        description: Password reset email sent successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.forgot_password(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Forgot password error: {e}')
        return jsonify({'error': 'Failed to send reset email', 'message': 'An error occurred while sending the reset email'}), 500


@auth_bp.route('/verify-reset-token', methods=['POST'])
@validate_json_content_type
@limiter.limit("20 per minute")
def verify_reset_token():
    """
    Verify password reset token
    ---
    tags:
      - Authentication
    summary: Verify password reset token validity
    description: Check if a password reset token is valid before allowing password reset
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - token
          properties:
            token:
              type: string
              description: Password reset token
    responses:
      200:
        description: Token is valid
        schema:
          type: object
          properties:
            valid:
              type: boolean
      400:
        description: Invalid or expired token
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.verify_reset_token(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Verify reset token error: {e}')
        return jsonify({'error': 'Token verification failed', 'message': 'An error occurred during token verification'}), 500


@auth_bp.route('/reset-password', methods=['POST'])
@validate_json_content_type
@limiter.limit("10 per minute")
def reset_password():
    """
    Reset password
    ---
    tags:
      - Authentication
    summary: Reset password using token
    description: Reset user password using a valid reset token
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - token
            - new_password
          properties:
            token:
              type: string
              description: Password reset token
            new_password:
              type: string
              format: password
    responses:
      200:
        description: Password reset successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Invalid token or validation error
      500:
        description: Server error
    """
    try:
        service = AuthServiceV2()
        data = service.reset_password(request.get_json() or {})
        return jsonify(data), 200
    except AuthValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Reset password error: {e}')
        return jsonify({'error': 'Password reset failed', 'message': 'An error occurred during password reset'}), 500


# Health check endpoint
@auth_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check
    ---
    tags:
      - Authentication
    summary: Check authentication service health
    description: Returns the health status of the authentication service
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
            service:
              type: string
            timestamp:
              type: string
    """
    return jsonify({
        'status': 'healthy',
        'service': 'authentication',
        'timestamp': datetime.utcnow().isoformat()
    }), 200