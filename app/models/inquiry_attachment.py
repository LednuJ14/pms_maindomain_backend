"""
Inquiry Attachment Model
"""
from datetime import datetime
from app import db
import enum

class FileType(enum.Enum):
    """File type enumeration."""
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    OTHER = "other"

class InquiryAttachment(db.Model):
    """Model for inquiry file attachments (images, videos, documents)."""
    
    __tablename__ = 'inquiry_attachments'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='CASCADE'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # File information
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    # Use String instead of Enum to avoid database enum issues - validate in application code
    file_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # Size in bytes
    mime_type = db.Column(db.String(100), nullable=False)  # e.g., image/jpeg, video/mp4
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    inquiry = db.relationship('Inquiry', backref='attachments', lazy='select')
    uploader = db.relationship('User', foreign_keys=[uploaded_by], lazy='select')
    
    def to_dict(self):
        """Convert attachment to dictionary representation."""
        # Handle file_type as string (not enum)
        file_type_value = self.file_type
        if isinstance(file_type_value, enum.Enum):
            file_type_value = file_type_value.value
        elif file_type_value and not isinstance(file_type_value, str):
            file_type_value = str(file_type_value)
        
        return {
            'id': self.id,
            'inquiry_id': self.inquiry_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_type': file_type_value.lower() if file_type_value else 'other',
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'uploaded_by': self.uploaded_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_deleted': self.is_deleted
        }
    
    def __repr__(self):
        """String representation of attachment."""
        return f'<InquiryAttachment {self.id} - {self.file_name} for Inquiry {self.inquiry_id}>'

