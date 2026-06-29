"""
Password Reset Routes
"""
import secrets
import string
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app, render_template_string
from flask_mail import Message
from app import db, mail
from app.models.user import User
from app.utils.error_handlers import handle_api_error
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Create blueprint
password_reset_bp = Blueprint('password_reset', __name__)

# Rate limiter for password reset requests
limiter = Limiter(key_func=get_remote_address)

def generate_reset_token():
    """Generate a secure random token for password reset."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(32))

def send_reset_email(user, reset_token):
    """Send password reset email to user."""
    try:
        # Create reset URL (you can customize this based on your frontend routing)
        reset_url = f"http://localhost:3000/reset-password?token={reset_token}&email={user.email}"
        
        # Email template
        email_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset - JACS Property Management</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: linear-gradient(135deg, #1f2937 0%, #374151 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                .content { background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }
                .button { display: inline-block; background: #1f2937; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                .footer { text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }
                .warning { background: #fef3cd; border: 1px solid #fde68a; color: #92400e; padding: 15px; border-radius: 5px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏠 JACS Property Management</h1>
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <p>Hello <strong>{{ user_name }}</strong>,</p>
                    
                    <p>We received a request to reset your password for your JACS Property Management account.</p>
                    
                    <p>Click the button below to reset your password:</p>
                    
                    <div style="text-align: center;">
                        <a href="{{ reset_url }}" class="button">Reset My Password</a>
                    </div>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; background: #e5e7eb; padding: 10px; border-radius: 5px;">{{ reset_url }}</p>
                    
                    <div class="warning">
                        <strong>⚠️ Important:</strong>
                        <ul>
                            <li>This link will expire in <strong>1 hour</strong></li>
                            <li>If you didn't request this reset, please ignore this email</li>
                            <li>For security, never share this link with anyone</li>
                        </ul>
                    </div>
                    
                    <p>If you're having trouble with the button above, you can also reset your password by logging into your account and going to Settings.</p>
                </div>
                <div class="footer">
                    <p>© 2024 JACS Property Management. All rights reserved.</p>
                    <p>This is an automated message, please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Render template with user data
        html_content = render_template_string(
            email_template,
            user_name=f"{user.first_name} {user.last_name}".strip() or user.email,
            reset_url=reset_url
        )
        
        # Create and send email
        msg = Message(
            subject='Password Reset - JACS Property Management',
            recipients=[user.email],
            html=html_content,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        return True
        
    except Exception as e:
        current_app.logger.error(f'Failed to send reset email: {e}')
        return False

# Note: /forgot-password route is now handled by auth_controller_v2.py
# This route has been removed to avoid conflicts with the newer service-based implementation

@password_reset_bp.route('/reset-password', methods=['POST'])
@limiter.limit("10 per minute")  # Limit to 10 attempts per minute per IP
def reset_password():
    """Reset password using token."""
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "Request data is required")
        
        email = data.get('email', '').lower().strip()
        token = data.get('token', '').strip()
        new_password = data.get('password', '')
        
        if not all([email, token, new_password]):
            return handle_api_error(400, "Email, token, and new password are required")
        
        if len(new_password) < 6:
            return handle_api_error(400, "Password must be at least 6 characters long")
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        if not user:
            return handle_api_error(400, "Invalid reset token")
        
        # Check if token is valid and not expired
        if (not user.password_reset_token or 
            user.password_reset_token != token or
            not user.password_reset_expires or
            user.password_reset_expires < datetime.utcnow()):
            return handle_api_error(400, "Invalid or expired reset token")
        
        # Update password
        from app import bcrypt
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # Clear reset token
        user.password_reset_token = None
        user.password_reset_expires = None
        
        # Reset failed login attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Password has been reset successfully',
            'success': True
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Reset password error: {e}')
        return handle_api_error(500, "Failed to reset password")

@password_reset_bp.route('/verify-reset-token', methods=['POST'])
def verify_reset_token():
    """Verify if a reset token is valid."""
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "Request data is required")
        
        email = data.get('email', '').lower().strip()
        token = data.get('token', '').strip()
        
        if not all([email, token]):
            return handle_api_error(400, "Email and token are required")
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        if not user:
            return handle_api_error(400, "Invalid reset token")
        
        # Check if token is valid and not expired
        if (not user.password_reset_token or 
            user.password_reset_token != token or
            not user.password_reset_expires or
            user.password_reset_expires < datetime.utcnow()):
            return handle_api_error(400, "Invalid or expired reset token")
        
        return jsonify({
            'message': 'Reset token is valid',
            'success': True,
            'user_name': f"{user.first_name} {user.last_name}".strip() or user.email
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Verify reset token error: {e}')
        return handle_api_error(500, "Failed to verify reset token")
