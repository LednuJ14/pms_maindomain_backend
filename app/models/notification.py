"""
Notification Model
"""
from datetime import datetime
from app import db
import enum

class NotificationType(enum.Enum):
    """Notification type enumeration for main-domain users (tenants and property managers)."""
    # Inquiry-related notifications (for tenants)
    INQUIRY_RESPONSE = "inquiry_response"  # Property manager responds to inquiry
    INQUIRY_STATUS_CHANGE = "inquiry_status_change"  # Inquiry status changes
    
    # Property-related notifications (for tenants)
    PROPERTY_AVAILABLE = "property_available"  # New property/unit available
    PROPERTY_UPDATE = "property_update"  # Property details updated
    
    # Viewing-related notifications (for tenants)
    VIEWING_CONFIRMED = "viewing_confirmed"  # Viewing appointment confirmed/rescheduled
    
    # Account-related notifications (for all users)
    ACCOUNT_UPDATE = "account_update"  # Profile/account changes
    
    # System notifications (for all users)
    SYSTEM = "system"  # System messages, maintenance, etc.
    
    # Property Manager-specific notifications
    NEW_INQUIRY = "new_inquiry"  # New tenant inquiry received
    PROPERTY_APPROVED = "property_approved"  # Property approved by admin
    PROPERTY_REJECTED = "property_rejected"  # Property rejected by admin
    UNIT_STATUS_CHANGE = "unit_status_change"  # Unit status changed (vacant/occupied)
    TENANT_ASSIGNED = "tenant_assigned"  # Tenant assigned to unit
    TENANT_UNASSIGNED = "tenant_unassigned"  # Tenant unassigned from unit
    SUBSCRIPTION_EXPIRING = "subscription_expiring"  # Subscription expiring soon
    SUBSCRIPTION_EXPIRED = "subscription_expired"  # Subscription expired
    
    # Admin-specific notifications (for property managers)
    BILLING_CREATED = "billing_created"  # Admin created a billing entry
    BILLING_STATUS_UPDATED = "billing_status_updated"  # Admin updated billing status
    PAYMENT_VERIFIED = "payment_verified"  # Admin verified payment transaction
    DOCUMENT_APPROVED = "document_approved"  # Admin approved document
    DOCUMENT_REJECTED = "document_rejected"  # Admin rejected document
    PORTAL_TOGGLED = "portal_toggled"  # Admin toggled portal status
    SUBSCRIPTION_PLAN_CREATED = "subscription_plan_created"  # Admin created subscription plan
    SUBSCRIPTION_PLAN_UPDATED = "subscription_plan_updated"  # Admin updated subscription plan

class Notification(db.Model):
    """Notification model for user notifications."""
    
    __tablename__ = 'notifications'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Notification details
    type = db.Column(db.Enum(NotificationType), nullable=False, default=NotificationType.SYSTEM)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Related entity IDs (optional, for linking to specific items)
    related_id = db.Column(db.Integer, nullable=True)  # Can link to inquiry_id, bill_id, etc.
    related_type = db.Column(db.String(50), nullable=True)  # 'inquiry', 'bill', etc.
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    def to_dict(self):
        """Convert notification to dictionary."""
        # Safely handle enum conversion
        def safe_enum_value(value):
            try:
                if isinstance(value, enum.Enum):
                    return value.value
                elif isinstance(value, str):
                    # If it's already a string, try to validate it's a valid enum
                    try:
                        NotificationType(value)  # Validate it exists
                        return value
                    except (ValueError, LookupError):
                        # If it's an old/invalid value, return as string
                        return value
                else:
                    return str(value) if value else None
            except (AttributeError, LookupError, ValueError) as e:
                # If enum lookup fails, return as string
                return str(value) if value else None
        
        # Safely format datetime
        def safe_iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return str(dt) if dt else None
        
        return {
            'id': self.id,
            'type': safe_enum_value(self.type),
            'title': self.title,
            'message': self.message,
            'is_read': self.is_read,
            'related_id': self.related_id,
            'related_type': self.related_type,
            'created_at': safe_iso(self.created_at),
            'read_at': safe_iso(self.read_at)
        }
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.title}>'

