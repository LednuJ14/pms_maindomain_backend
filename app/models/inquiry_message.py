"""
Inquiry Message Model
"""
from datetime import datetime
from app import db

class InquiryMessage(db.Model):
    """Model for threaded inquiry messages (conversation)."""
    
    __tablename__ = 'inquiry_messages'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Message content
    message = db.Column(db.Text, nullable=False)
    
    # Read status
    is_read = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    inquiry = db.relationship('Inquiry', backref='messages', lazy='select')
    sender = db.relationship('User', foreign_keys=[sender_id], lazy='select')
    
    def to_dict(self):
        """Convert message to dictionary representation."""
        return {
            'id': self.id,
            'inquiry_id': self.inquiry_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.get_full_name() if self.sender else 'Unknown',
            'sender_email': self.sender.email if self.sender else '',
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def mark_as_read(self):
        """Mark message as read."""
        self.is_read = True
        db.session.commit()
    
    def __repr__(self):
        """String representation of message."""
        return f'<InquiryMessage {self.id} - Inquiry {self.inquiry_id}>'

