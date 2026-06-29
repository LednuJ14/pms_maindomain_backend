"""
Inquiry Model
"""
from datetime import datetime
from app import db
import enum

class InquiryStatus(enum.Enum):
    """Inquiry status enumeration."""
    PENDING = "pending"
    READ = "read"
    RESPONDED = "responded"
    CLOSED = "closed"
    SPAM = "spam"
    ASSIGNED = "assigned"

class InquiryType(enum.Enum):
    """Inquiry type enumeration."""
    VIEWING_REQUEST = "viewing_request"
    RENTAL_INQUIRY = "rental_inquiry"
    INFORMATION_REQUEST = "information_request"
    COMPLAINT = "complaint"
    OTHER = "other"

class Inquiry(db.Model):
    """Inquiry model for tenant-property manager communication."""
    
    __tablename__ = 'inquiries'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    unit_id = db.Column(db.Integer, nullable=True)  # Foreign key constraint managed externally
    tenant_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    property_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Inquiry details
    inquiry_type = db.Column(db.Enum(InquiryType), nullable=False, default=InquiryType.RENTAL_INQUIRY)
    status = db.Column(db.Enum(InquiryStatus), nullable=False, default=InquiryStatus.PENDING)
    message = db.Column(db.Text, nullable=False)
    
    # Priority and flags
    is_urgent = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    read_at = db.Column(db.DateTime)
    
    # Relationships
    property = db.relationship('Property', lazy='select')
    tenant = db.relationship('User', foreign_keys=[tenant_id], lazy='select')
    property_manager = db.relationship('User', foreign_keys=[property_manager_id], lazy='select')
    # Note: attachments backref is automatically created by InquiryAttachment model
    # Note: messages backref is automatically created by InquiryMessage model
    
    def __init__(self, property_id, tenant_id, property_manager_id, message):
        """Initialize inquiry with required fields."""
        self.property_id = property_id
        self.tenant_id = tenant_id
        self.property_manager_id = property_manager_id
        self.message = message.strip()
    
    def mark_as_read(self):
        """Mark inquiry as read."""
        if self.status == InquiryStatus.PENDING:
            self.status = InquiryStatus.READ
            self.read_at = datetime.utcnow()
            db.session.commit()
    
    def respond(self, response_message, sender_id):
        """Add response to inquiry via message."""
        # Import here to avoid circular import
        from app.models.inquiry_message import InquiryMessage
        # Create a message for the response
        msg = InquiryMessage(
            inquiry_id=self.id,
            sender_id=sender_id,
            message=response_message.strip()
        )
        db.session.add(msg)
        self.status = InquiryStatus.RESPONDED
        if not self.read_at:
            self.read_at = datetime.utcnow()
        db.session.commit()
    
    def close(self):
        """Close the inquiry."""
        self.status = InquiryStatus.CLOSED
        db.session.commit()
    
    def mark_as_spam(self):
        """Mark inquiry as spam."""
        self.status = InquiryStatus.SPAM
        db.session.commit()
    
    def archive(self):
        """Archive the inquiry."""
        self.is_archived = True
        db.session.commit()
    
    def unarchive(self):
        """Unarchive the inquiry."""
        self.is_archived = False
        db.session.commit()
    
    def is_responded(self):
        """Check if inquiry has been responded to."""
        # Check if there are any messages from the property manager
        # messages is a backref list, not a query object
        return self.status == InquiryStatus.RESPONDED and any(
            msg.sender_id == self.property_manager_id for msg in self.messages
        )
    
    def is_pending(self):
        """Check if inquiry is still pending."""
        return self.status == InquiryStatus.PENDING
    
    def get_age_in_days(self):
        """Get age of inquiry in days."""
        delta = datetime.utcnow() - self.created_at
        return delta.days
    
    def to_dict(self, include_property=False, include_tenant=False, include_messages=False, include_attachments=False):
        """Convert inquiry to dictionary representation."""
        # Get tenant info from relationship
        tenant_name = self.tenant.get_full_name() if self.tenant else 'Unknown'
        tenant_email = self.tenant.email if self.tenant else ''
        tenant_phone = self.tenant.phone_number if self.tenant else None
        
        data = {
            'id': self.id,
            'property_id': self.property_id,
            'unit_id': self.unit_id,
            'tenant_id': self.tenant_id,
            'property_manager_id': self.property_manager_id,
            'inquiry_type': self.inquiry_type.value if isinstance(self.inquiry_type, enum.Enum) else str(self.inquiry_type),
            'status': self.status.value if isinstance(self.status, enum.Enum) else str(self.status),
            'message': self.message,
            'tenant_contact': {
                'name': tenant_name,
                'email': tenant_email,
                'phone': tenant_phone
            },
            'flags': {
                'is_urgent': self.is_urgent,
                'is_archived': self.is_archived
            },
            'timestamps': {
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'read_at': self.read_at.isoformat() if self.read_at else None,
                'age_in_days': self.get_age_in_days()
            }
        }
        
        if include_property and self.property:
            data['property'] = {
                'id': self.property.id,
                'title': self.property.title,
                'address': self.property.get_full_address() if hasattr(self.property, 'get_full_address') else None,
                'monthly_rent': float(self.property.monthly_rent) if self.property.monthly_rent else None,
                'property_type': self.property.property_type.value if hasattr(self.property, 'property_type') else None
            }
        
        if include_tenant and self.tenant:
            data['tenant'] = {
                'id': self.tenant.id,
                'name': tenant_name,
                'email': tenant_email,
                'phone': tenant_phone
            }
        
        if include_messages:
            # messages is a backref list, not a query object
            data['messages'] = [msg.to_dict() for msg in self.messages]
        
        if include_attachments:
            # attachments is a backref list, not a query object
            data['attachments'] = [att.to_dict() for att in self.attachments if not att.is_deleted]
        
        return data
    
    def __repr__(self):
        """String representation of inquiry."""
        tenant_name = self.tenant.get_full_name() if self.tenant else 'Unknown'
        return f'<Inquiry {self.id} - {tenant_name} for Property {self.property_id}>'
