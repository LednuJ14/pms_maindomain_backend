"""
Property Models
"""
from datetime import datetime
from decimal import Decimal
from app import db
import enum

class PropertyType(enum.Enum):
    """Property type enumeration."""
    BED_SPACE = "bed_space"
    DORMITORY = "dormitory"
    BOARDING_HOUSE = "boarding_house"
    STUDIO_APARTMENT = "studio_apartment"
    ROOM_FOR_RENT = "room_for_rent"

class PropertyStatus(enum.Enum):
    """Property status enumeration."""
    ACTIVE = "active"
    APPROVED = "approved"  # Added to match database values
    INACTIVE = "inactive"
    RENTED = "rented"
    MAINTENANCE = "maintenance"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"

class FurnishingType(enum.Enum):
    """Furnishing type enumeration."""
    UNFURNISHED = "UNFURNISHED"
    SEMI_FURNISHED = "SEMI_FURNISHED"
    FURNISHED = "FURNISHED"

class ManagementStatus(enum.Enum):
    """Management status enumeration."""
    NOT_MANAGED = "not_managed"
    MANAGED = "managed"

class Property(db.Model):
    """Property model for rental listings."""
    
    __tablename__ = 'properties'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic property information
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    property_type = db.Column(db.String(50), nullable=False)  # Changed from Enum to String
    furnishing = db.Column(db.String(50), nullable=True)  # Changed from Enum to String
    contact_person = db.Column(db.String(255))
    management_status = db.Column(db.String(50), default='managed')  # Changed from Enum to String
    status = db.Column(db.String(50), nullable=True)
    
    # Location
    address = db.Column(db.String(255), nullable=False)
    street = db.Column(db.String(255), nullable=True)
    barangay = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=False)
    province = db.Column(db.String(100), nullable=True, default='Cebu')
    postal_code = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Numeric(10, 8), nullable=True)
    longitude = db.Column(db.Numeric(11, 8), nullable=True)
    building_name = db.Column(db.String(255))
    # contact_person removed from here (duplicate - already defined above)
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(120))
    amenities = db.Column(db.Text)
    images = db.Column(db.Text)
    legal_documents = db.Column(db.Text)
    additional_notes = db.Column(db.Text)
    monthly_rent = db.Column(db.Numeric(10, 2))
    total_units = db.Column(db.Integer, default=0)
    portal_enabled = db.Column(db.Boolean, default=False)
    portal_subdomain = db.Column(db.String(100))
    display_settings = db.Column(db.Text)  # JSON string for sub-domain display settings
    
    # Property details - bedrooms field removed (not in database schema)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # approved_by and approved_at fields removed (not in database schema)
    
    # Relationships
    inquiries = db.relationship('Inquiry', lazy='dynamic')
    
    def __init__(self, title, property_type, address, city, monthly_rent, owner_id):
        """Initialize property with required fields."""
        self.title = title.strip()
        self.property_type = property_type
        self.address = address.strip()
        self.city = city.strip()
        self.monthly_rent = monthly_rent
        self.owner_id = owner_id
    
    
    
    def approve_property(self, approved_by_user_id):
        """Approve property."""
        self.status = PropertyStatus.ACTIVE
        self.approved_by = approved_by_user_id
        self.approved_at = datetime.utcnow()
        
        db.session.commit()
    
    
    
    def is_available(self):
        """Check if property is available for rent."""
        return self.status == PropertyStatus.ACTIVE
    
    
    def to_dict(self, include_owner=False, include_stats=False):
        """Convert property to dictionary representation."""
        # Helpers to safely serialize enums and dates
        def safe_enum_value(value):
            try:
                return getattr(value, 'value', value)
            except Exception:
                return value
        def safe_iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return str(dt) if dt else None

        data = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'property_type': self.property_type,  # Now a string, no need for safe_enum_value
            'status': self.status,  # Now a string, no need for safe_enum_value
            'address': self.address,
            'street': getattr(self, 'street', None),
            'barangay': getattr(self, 'barangay', None),
            'city': self.city,
            'province': self.province,
            'postal_code': getattr(self, 'postal_code', None),
            'latitude': float(self.latitude) if hasattr(self, 'latitude') and self.latitude else None,
            'longitude': float(self.longitude) if hasattr(self, 'longitude') and self.longitude else None,
            'building_name': getattr(self, 'building_name', None),
            'contact_person': getattr(self, 'contact_person', None),
            'contact_phone': getattr(self, 'contact_phone', None),
            'contact_email': getattr(self, 'contact_email', None),
            'amenities': self.amenities,
            'images': self.images,
            'legal_documents': self.legal_documents,
            'additional_notes': self.additional_notes,
            'monthly_rent': float(self.monthly_rent) if self.monthly_rent else None,
            'total_units': self.total_units,
            'furnishing': self.furnishing,  # Now a string, no need for safe_enum_value
            'portal_enabled': self.portal_enabled,
            'portal_subdomain': self.portal_subdomain,
            'subdomain': self.portal_subdomain,  # Add alias for frontend compatibility
            'management_status': self.management_status,  # Now a string, no need for safe_enum_value
            'display_settings': getattr(self, 'display_settings', None),  # For sub-domain customization
            'created_at': safe_iso(self.created_at),
            'updated_at': safe_iso(self.updated_at),
            'owner_id': self.owner_id,
            # approved_by and approved_at fields removed (not in database schema)
        }
        
        if include_owner and hasattr(self, 'owner') and self.owner:
            data['owner'] = {
                'id': self.owner.id,
                'name': f"{self.owner.first_name} {self.owner.last_name}",
                'email': self.owner.email,
                'phone': self.owner.phone_number
            }
        
        return data
    
    def __repr__(self):
        """String representation of property."""
        return f'<Property {self.title} - {self.city}>'
