"""
Auth service: refactor of core auth endpoints (register, login, refresh, me, change_password, logout)
"""
from datetime import datetime, timedelta
import random
from typing import Dict, Tuple
from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from app import db, mail
from app.models.user import User, UserRole, UserStatus
from app.models.blacklisted_token import BlacklistedToken
from app.models.subscription import Subscription, SubscriptionPlan
from app.repositories.user_repository import UserRepository
from app.utils.validators import validate_email, validate_password_strength, validate_required_fields
from flask_mail import Message


class AuthDomainError(Exception):
    pass


from app.errors import ValidationAppError

class AuthValidationError(ValidationAppError):
    def __init__(self, message: str, details: Dict | None = None):
        super().__init__(message)
        self.details = details or {}


class AuthServiceV2:
    def __init__(self, users: UserRepository | None = None):
        self.users = users or UserRepository()

    # Registration
    def register(self, payload: Dict) -> Dict:
        # Required fields
        ok, missing = validate_required_fields(payload, ['email', 'password', 'first_name', 'last_name', 'role'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})

        # Email
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        if self.users.get_by_email(normalized_email):
            raise AuthValidationError('Email already exists')

        # Password
        valid_pwd, pwd_errors, strength_score = validate_password_strength(payload['password'])
        if not valid_pwd:
            raise AuthValidationError('Weak password', {'details': pwd_errors, 'strength_score': strength_score})

        # Role - accept multiple spellings/cases (e.g., 'property_manager')
        def normalize_role(value: str) -> UserRole:
            s = str(value or '').strip().lower()
            if s in ('manager', 'property_manager', 'property-manager', 'pm'):
                return UserRole.MANAGER
            if s in ('admin', 'administrator'):
                return UserRole.ADMIN
            # default and for 'tenant'
            return UserRole.TENANT

        role = normalize_role(payload.get('role'))

        # Create user
        user = User(
            email=normalized_email,
            password=payload['password'],
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            role=role,
        )
        if 'phone_number' in payload:
            user.phone_number = payload['phone_number']
        if 'date_of_birth' in payload and payload['date_of_birth']:
            try:
                user.date_of_birth = datetime.strptime(payload['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                raise AuthValidationError('Invalid date format', {'message': 'Date of birth must be in YYYY-MM-DD format'})
        if 'address' in payload and payload['address']:
            user.address = payload['address'].strip()

        user.status = UserStatus.PENDING_VERIFICATION
        
        # Generate verification token BEFORE creating user (for tenants and managers)
        if role in [UserRole.TENANT, UserRole.MANAGER]:
            user.generate_email_verification_token()
        
        self.users.create(user)
        self.users.flush()  # obtain user.id

        # Setup subscription for managers (best-effort, resilient if plans table is missing)
        if role == UserRole.MANAGER:
            try:
                # Look for "Free Plan" by name (case-insensitive)
                from sqlalchemy import func
                free_plan = SubscriptionPlan.query.filter(
                    func.lower(SubscriptionPlan.name) == 'free plan'
                ).first()
                if free_plan:
                    subscription = Subscription(user.id, free_plan.id)
                    db.session.add(subscription)
                else:
                    # Fallback: try to find any plan with $0 monthly price
                    free_plan = SubscriptionPlan.query.filter(
                        SubscriptionPlan.monthly_price == 0
                    ).first()
                    if free_plan:
                        subscription = Subscription(user.id, free_plan.id)
                        db.session.add(subscription)
            except Exception as e:
                # Do not block registration if subscription tables are absent or misconfigured
                current_app.logger.error(f"Subscription setup skipped for user {user.id}: {e}")

        try:
            self.users.commit()
        except Exception as e:
            self.users.rollback()
            current_app.logger.error(f"Failed to commit user registration: {e}")
            raise AuthDomainError('Registration failed')

        # Send verification email for tenants and managers
        if role in [UserRole.TENANT, UserRole.MANAGER]:
            try:
                # Token is already generated, just send the email
                self.send_verification_email(user)
            except Exception as e:
                current_app.logger.error(f"Failed to send verification email to {user.email if user else 'unknown'}: {e}")
                # Don't fail registration if email fails, just log it

        return {
            'message': 'User registered successfully',
            'user': user.to_dict(),
            'next_steps': ['Verify your email address', 'Complete your profile', 'Start using the platform'],
        }

    # Login
    def login(self, payload: Dict) -> Dict:
        ok, missing = validate_required_fields(payload, ['email', 'password'])
        if not ok:
            raise AuthValidationError('Missing credentials', {'missing_fields': missing})

        user = self.users.get_by_email(payload['email'])
        if not user or not user.check_password(payload['password']):
            raise AuthValidationError('Invalid credentials', {'message': 'Email or password is incorrect'})

        if user.is_account_locked():
            raise AuthValidationError('Account locked', {
                'message': 'Account is temporarily locked due to too many failed login attempts',
                'locked_until': user.locked_until.isoformat() if user.locked_until else None,
            })

        if user.status == UserStatus.SUSPENDED:
            raise AuthValidationError('Account suspended')
        if user.status == UserStatus.INACTIVE:
            raise AuthValidationError('Account inactive')

        # If 2FA via email is enabled, send code and return pending state
        if getattr(user, 'two_factor_enabled', False):
            code = str(random.randint(100000, 999999))
            user.two_factor_email_code = code
            user.two_factor_email_expires = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            try:
                msg = Message(
                    subject="Your verification code",
                    recipients=[user.email],
                    body=f"Your verification code is {code}. It expires in 10 minutes."
                )
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(f"2FA email send error: {e}")
                raise AuthDomainError('Failed to send verification code')

            return {
                'status': 'pending_2fa',
                'message': 'Verification code sent to your email.'
            }

        # Check email verification for tenants and managers
        if (hasattr(user, 'role') and user.role in [UserRole.TENANT, UserRole.MANAGER]):
            # Check both email_verified field and status
            email_not_verified = (hasattr(user, 'email_verified') and not user.email_verified)
            status_pending = (hasattr(user, 'status') and user.status == UserStatus.PENDING_VERIFICATION)
            
            if email_not_verified or status_pending:
                raise AuthValidationError('Email verification required', {
                    'message': 'Please verify your email address before logging in',
                    'verification_required': True,
                    'email': user.email if hasattr(user, 'email') else None
                })

        # Normal login success
        user.reset_failed_login()
        db.session.commit()

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        # Avoid touching subscriptions table/relationship if schema is not present
        subscription_info = None

        return {
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'subscription': subscription_info,
            'expires_in': current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds(),
        }

    def verify_two_factor(self, payload: Dict) -> Dict:
        ok, missing = validate_required_fields(payload, ['email', 'code'])
        if not ok:
            raise AuthValidationError('Missing fields', {'missing_fields': missing})
        user = self.users.get_by_email(payload['email'])
        if not user:
            raise AuthValidationError('User not found')
        if not getattr(user, 'two_factor_enabled', False) or not user.two_factor_email_code:
            raise AuthValidationError('2FA not pending')
        if not user.two_factor_email_expires or user.two_factor_email_expires < datetime.utcnow():
            raise AuthValidationError('Code expired')
        if str(user.two_factor_email_code) != str(payload['code']).strip():
            raise AuthValidationError('Invalid code')

        # Clear and issue tokens
        user.two_factor_email_code = None
        user.two_factor_email_expires = None
        user.reset_failed_login()
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
            user.email_verified = True
        db.session.commit()

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        subscription_info = None
        return {
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'subscription': subscription_info,
            'expires_in': current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds(),
        }

    def handle_failed_login(self, user: User | None):
        if user:
            user.increment_failed_login()
            db.session.commit()

    # Refresh
    def refresh(self, current_user_id: int) -> Dict:
        user = self.users.get_by_id(current_user_id)
        if not user or not user.is_active_user():
            raise AuthValidationError('Invalid user', {'message': 'User account is not active'})
        new_access_token = create_access_token(identity=user.id)
        return {
            'access_token': new_access_token,
            'expires_in': current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds(),
        }

    # Me
    def me(self, current_user_id: int) -> Dict:
        user = self.users.get_by_id(current_user_id)
        if not user:
            raise AuthValidationError('User not found')
        subscription_info = None
        return {
            'user': user.to_dict(),
            'subscription': subscription_info,
        }

    # Change password
    def change_password(self, current_user_id: int, payload: Dict) -> Dict:
        user = self.users.get_by_id(current_user_id)
        if not user:
            raise AuthValidationError('User not found')

        ok, missing = validate_required_fields(payload, ['current_password', 'new_password'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})

        if not user.check_password(payload['current_password']):
            raise AuthValidationError('Invalid current password', {'message': 'Current password is incorrect'})

        valid_pwd, pwd_errors, strength_score = validate_password_strength(payload['new_password'])
        if not valid_pwd:
            raise AuthValidationError('Weak password', {'details': pwd_errors, 'strength_score': strength_score})

        user.set_password(payload['new_password'])
        db.session.commit()
        return {'message': 'Password changed successfully'}

    # Logout
    def logout(self, jti: str, token_type: str, expires_at: datetime, current_user_id: int) -> Dict:
        BlacklistedToken.add_token_to_blacklist(jti, expires_at, current_user_id)
        return {'message': 'Successfully logged out'}

    # Email Verification
    def send_verification_email(self, user: User) -> Dict:
        """Send email verification email to user."""
        if user.email_verified:
            raise AuthValidationError('Email already verified')
        
        # Generate verification token if it doesn't exist
        if not user.email_verification_token:
            token = user.generate_email_verification_token()
            db.session.commit()
        else:
            token = user.email_verification_token
        
        # Create verification URL
        frontend_url = current_app.config.get('FRONTEND_URL', 'http://localhost:3000')
        verification_url = f"{frontend_url}/verify-email?token={token}&email={user.email}"
        
        # Send email
        try:
            msg = Message(
                subject="Verify Your Email - JACS Cebu Property Management",
                recipients=[user.email],
                html=f"""
                <html>
                <body>
                    <h2>Welcome to JACS Cebu Property Management!</h2>
                    <p>Hello {user.first_name},</p>
                    <p>Thank you for registering with us. Please verify your email address by clicking the link below:</p>
                    <p><a href="{verification_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Verify Email Address</a></p>
                    <p>Or copy and paste this link into your browser:</p>
                    <p>{verification_url}</p>
                    <p>This link will expire in 24 hours.</p>
                    <p>If you didn't create this account, please ignore this email.</p>
                    <br>
                    <p>Best regards,<br>JACS Cebu Property Management Team</p>
                </body>
                </html>
                """,
                body=f"""
                Welcome to JACS Cebu Property Management!
                
                Hello {user.first_name},
                
                Thank you for registering with us. Please verify your email address by visiting this link:
                
                {verification_url}
                
                This link will expire in 24 hours.
                
                If you didn't create this account, please ignore this email.
                
                Best regards,
                JACS Cebu Property Management Team
                """
            )
            mail.send(msg)
            return {'message': 'Verification email sent successfully'}
        except Exception as e:
            current_app.logger.error(f"Failed to send verification email: {e}")
            raise AuthDomainError('Failed to send verification email')

    def verify_email(self, payload: Dict) -> Dict:
        """Verify user email with token."""
        ok, missing = validate_required_fields(payload, ['email', 'token'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        
        user = self.users.get_by_email(normalized_email)
        if not user:
            raise AuthValidationError('User not found')
        
        if user.email_verified:
            # If already verified, return success instead of error
            return {
                'message': 'Email already verified',
                'user': user.to_dict()
            }
        
        # Check if token exists
        if not user.email_verification_token:
            current_app.logger.warning(f"No verification token found for user {user.email}")
            raise AuthValidationError('Invalid or expired verification token', {
                'message': 'No verification token found. Please request a new verification email.'
            })
        
        # Check if token matches (use direct comparison for better debugging)
        if user.email_verification_token != payload['token']:
            current_app.logger.warning(f"Token mismatch for user {user.email}. Stored token exists: {bool(user.email_verification_token)}")
            raise AuthValidationError('Invalid or expired verification token', {
                'message': 'The verification token is invalid. Please request a new verification email.'
            })
        
        # Verify email and activate account
        user.verify_email()
        db.session.commit()
        
        return {
            'message': 'Email verified successfully',
            'user': user.to_dict()
        }

    def check_verification_status(self, payload: Dict) -> Dict:
        """Check if an email has been verified."""
        ok, missing = validate_required_fields(payload, ['email'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        
        user = self.users.get_by_email(normalized_email)
        if not user:
            return {
                'verified': False,
                'message': 'User not found'
            }
        
        return {
            'verified': user.email_verified,
            'user': user.to_dict() if user.email_verified else None,
            'message': 'Email is verified' if user.email_verified else 'Email not yet verified'
        }

    def resend_verification_email(self, payload: Dict) -> Dict:
        """Resend verification email to user."""
        ok, missing = validate_required_fields(payload, ['email'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        user = self.users.get_by_email(payload['email'])
        if not user:
            raise AuthValidationError('User not found')
        
        if user.email_verified:
            raise AuthValidationError('Email already verified')
        
        return self.send_verification_email(user)

    def forgot_password(self, payload: Dict) -> Dict:
        """Send password reset email to user."""
        ok, missing = validate_required_fields(payload, ['email'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        
        user = self.users.get_by_email(normalized_email)
        
        # Always return success message for security (don't reveal if email exists)
        if not user:
            return {
                'message': 'If an account with that email exists, we have sent a password reset link.'
            }
        
        # Generate password reset token
        user.generate_password_reset_token()
        db.session.commit()
        
        # Send password reset email
        try:
            self.send_password_reset_email(user)
        except Exception as e:
            current_app.logger.error(f'Failed to send password reset email: {e}')
            # Don't reveal email sending errors to user for security
        
        return {
            'message': 'If an account with that email exists, we have sent a password reset link.'
        }

    def verify_reset_token(self, payload: Dict) -> Dict:
        """Verify if reset token is valid without resetting password."""
        ok, missing = validate_required_fields(payload, ['token', 'email'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        
        user = self.users.get_by_email(normalized_email)
        if not user:
            raise AuthValidationError('Invalid reset token')
        
        # Verify reset token
        if not user.is_password_reset_token_valid(payload['token']):
            raise AuthValidationError('Invalid or expired reset token')
        
        return {
            'valid': True,
            'user_name': f"{user.first_name} {user.last_name}",
            'message': 'Reset token is valid'
        }

    def reset_password(self, payload: Dict) -> Dict:
        """Reset user password using reset token."""
        ok, missing = validate_required_fields(payload, ['token', 'email', 'new_password'])
        if not ok:
            raise AuthValidationError('Missing required fields', {'missing_fields': missing})
        
        valid_email, normalized_email, email_error = validate_email(payload['email'])
        if not valid_email:
            raise AuthValidationError('Invalid email', {'message': email_error})
        
        # Validate new password
        valid_pwd, pwd_errors, strength_score = validate_password_strength(payload['new_password'])
        if not valid_pwd:
            raise AuthValidationError('Password does not meet requirements', {'password_errors': pwd_errors})
        
        user = self.users.get_by_email(normalized_email)
        if not user:
            raise AuthValidationError('Invalid reset token')
        
        # Verify reset token
        if not user.is_password_reset_token_valid(payload['token']):
            raise AuthValidationError('Invalid or expired reset token')
        
        # Reset password
        user.set_password(payload['new_password'])
        user.clear_password_reset_token()
        user.failed_login_attempts = 0  # Clear any failed attempts
        user.locked_until = None  # Unlock account if locked
        db.session.commit()
        
        return {
            'message': 'Password reset successfully. You can now log in with your new password.'
        }

    def send_password_reset_email(self, user: User) -> None:
        """Send password reset email to user."""
        try:
            reset_url = f"{current_app.config.get('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={user.password_reset_token}&email={user.email}"
            
            msg = Message(
                subject='Reset Your Password - JACS Property Management',
                sender=current_app.config['MAIL_DEFAULT_SENDER'],
                recipients=[user.email]
            )
            
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #1f2937 0%, #374151 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">JACS Property Management</h1>
                    <p style="color: #d1d5db; margin: 5px 0 0 0;">Password Reset Request</p>
                </div>
                
                <div style="padding: 40px 30px; background: white;">
                    <h2 style="color: #1f2937; margin-bottom: 20px;">Reset Your Password</h2>
                    
                    <p style="color: #4b5563; line-height: 1.6; margin-bottom: 25px;">
                        Hi {user.first_name},
                    </p>
                    
                    <p style="color: #4b5563; line-height: 1.6; margin-bottom: 25px;">
                        We received a request to reset your password for your JACS Property Management account. 
                        If you made this request, click the button below to reset your password:
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" 
                           style="background: linear-gradient(135deg, #1f2937 0%, #374151 100%); 
                                  color: white; 
                                  padding: 12px 30px; 
                                  text-decoration: none; 
                                  border-radius: 8px; 
                                  font-weight: bold;
                                  display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin-top: 25px;">
                        If the button doesn't work, copy and paste this link into your browser:<br>
                        <a href="{reset_url}" style="color: #1f2937; word-break: break-all;">{reset_url}</a>
                    </p>
                    
                    <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin-top: 25px;">
                        This link will expire in 1 hour for security reasons.
                    </p>
                    
                    <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin-top: 25px;">
                        If you didn't request this password reset, please ignore this email. Your password will remain unchanged.
                    </p>
                </div>
                
                <div style="background: #f9fafb; padding: 20px 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                    <p style="color: #6b7280; font-size: 12px; margin: 0;">
                        © 2025 JACS Property Management. All rights reserved.
                    </p>
                </div>
            </div>
            """
            
            mail.send(msg)
            current_app.logger.info(f'Password reset email sent to {user.email}')
            
        except Exception as e:
            current_app.logger.error(f'Failed to send password reset email to {user.email}: {e}')
            raise
