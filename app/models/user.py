"""
User Model
"""
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from app import db, bcrypt
import enum

class UserRole(enum.Enum):
    """User role enumeration."""
    TENANT = "tenant"
    MANAGER = "manager"
    ADMIN = "admin"

class UserStatus(enum.Enum):
    """User status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"

class User(db.Model):
    """User model for authentication and profile management."""
    
    __tablename__ = 'users'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Authentication fields
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.TENANT)
    status = db.Column(db.Enum(UserStatus), nullable=False, default=UserStatus.PENDING_VERIFICATION)
    
    # Profile fields
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    phone_number = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    profile_image_url = db.Column(db.String(255))
    # Manager profile fields removed: location, bio (not needed)
    
    # Address fields
    address = db.Column(db.Text)  # Single address field (consolidated from address_line1 and address_line2)
    city = db.Column(db.String(100))
    province = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(100), default='Philippines')
    
    # Bio field for user description
    bio = db.Column(db.Text)
    
    # Verification fields
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))
    # phone_verified removed - not used in system
    
    # Security fields
    last_login = db.Column(db.DateTime)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    password_reset_token = db.Column(db.String(255))
    password_reset_expires = db.Column(db.DateTime)
    # Two-factor authentication (email-based)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    # two_factor_secret removed - system uses email-based 2FA, not TOTP
    # Two-factor via email code
    two_factor_email_code = db.Column(db.String(8))
    two_factor_email_expires = db.Column(db.DateTime)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # created_by removed - not critical for audit trail
    # updated_by removed - not critical for audit trail
    
    # Relationships
    properties = db.relationship('Property', foreign_keys='Property.owner_id', backref='owner', lazy='dynamic')
    sent_inquiries = db.relationship('Inquiry', foreign_keys='Inquiry.tenant_id', backref='inquiry_tenant', lazy='dynamic')
    received_inquiries = db.relationship('Inquiry', foreign_keys='Inquiry.property_manager_id', backref='inquiry_manager', lazy='dynamic')
    subscription = db.relationship('Subscription', backref='user', uselist=False)
    
    def __init__(self, email, password, first_name, last_name, role=UserRole.TENANT):
        """Initialize user with required fields."""
        self.email = email.lower().strip()
        self.first_name = first_name.strip()
        self.last_name = last_name.strip()
        self.role = role
        self.set_password(password)
    
    def set_password(self, password):
        """Hash and set password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Check if provided password matches hash."""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def is_account_locked(self):
        """Check if account is locked due to failed login attempts."""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False
    
    def increment_failed_login(self):
        """Increment failed login attempts and lock account if necessary."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            # Lock account for 30 minutes after 5 failed attempts
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    def reset_failed_login(self):
        """Reset failed login attempts after successful login."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
    
    def get_full_name(self):
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}"
    
    def get_display_name(self):
        """Get display name for UI."""
        return self.get_full_name()
    
    def is_admin(self):
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN
    
    def is_manager(self):
        """Check if user has manager role."""
        return self.role == UserRole.MANAGER
    
    def is_tenant(self):
        """Check if user has tenant role."""
        return self.role == UserRole.TENANT
    
    def is_active_user(self):
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE and not self.is_account_locked()
    
    def can_manage_properties(self):
        """Check if user can manage properties."""
        return self.role in [UserRole.MANAGER, UserRole.ADMIN]
    
    def generate_email_verification_token(self):
        """Generate a secure email verification token."""
        import secrets
        self.email_verification_token = secrets.token_urlsafe(32)
        return self.email_verification_token
    
    def verify_email(self):
        """Mark email as verified and activate account."""
        self.email_verified = True
        self.email_verification_token = None
        if self.status == UserStatus.PENDING_VERIFICATION:
            self.status = UserStatus.ACTIVE
    
    def is_email_verification_token_valid(self, token):
        """Check if the provided token matches the stored verification token."""
        return (self.email_verification_token and 
                self.email_verification_token == token and 
                not self.email_verified)
    
    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary representation. Be resilient to inconsistent DB data."""
        # Handle Enum or string values gracefully
        role_value = getattr(self.role, 'value', self.role)
        status_value = getattr(self.status, 'value', self.status)

        # Normalize dates safely
        def safe_iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return str(dt) if dt else None

        if isinstance(self.date_of_birth, str):
            dob_value = self.date_of_birth
        else:
            dob_value = safe_iso(self.date_of_birth)

        data = {
            'id': self.id,
            'email': self.email,
            'role': role_value,
            'status': status_value,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.get_full_name(),
            'phone_number': self.phone_number,
            'date_of_birth': dob_value,
            'profile_image_url': self.profile_image_url,
            'two_factor_enabled': bool(self.two_factor_enabled),
            # location and bio removed - not needed for managers
            'address': self.address,
            'city': self.city,
            'province': self.province,
            'postal_code': self.postal_code,
            'country': self.country,
            'bio': self.bio,
            'email_verified': self.email_verified,
            # phone_verified removed - not used
            'created_at': safe_iso(self.created_at),
            'updated_at': safe_iso(self.updated_at),
            'last_login': safe_iso(self.last_login)
        }
        
        if include_sensitive:
            data.update({
                'failed_login_attempts': self.failed_login_attempts,
                'is_locked': self.is_account_locked()
            })
        
        return data
    
    def generate_password_reset_token(self):
        """Generate a password reset token."""
        import secrets
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        self.updated_at = datetime.utcnow()
    
    def is_password_reset_token_valid(self, token):
        """Check if password reset token is valid and not expired."""
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        if self.password_reset_token != token:
            return False
        if datetime.utcnow() > self.password_reset_expires:
            return False
        return True
    
    def clear_password_reset_token(self):
        """Clear password reset token after use."""
        self.password_reset_token = None
        self.password_reset_expires = None
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        """String representation of user."""
        return f'<User {self.email} ({self.role.value})>'
