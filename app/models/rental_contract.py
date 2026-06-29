from datetime import datetime, timezone, date, timedelta
from app import db
from sqlalchemy import Numeric
import enum
import uuid


class ContractType(enum.Enum):
    """Contract duration types."""
    QUARTERLY = 'quarterly'  # 6 months
    YEARLY = 'yearly'  # 12 months


class ContractStatus(enum.Enum):
    """Contract status types."""
    DRAFT = 'draft'
    ACTIVE = 'active'
    EXPIRED = 'expired'
    RENEWED = 'renewed'
    TERMINATED = 'terminated'
    CANCELLED = 'cancelled'


class RentalContract(db.Model):
    """Rental contract model for managing tenant rental agreements."""
    
    __tablename__ = 'rental_contracts'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Contract Identification
    contract_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Relationships - tenant_unit_id can be NULL initially (created before assignment)
    tenant_unit_id = db.Column(db.Integer, nullable=True)
    tenant_id = db.Column(db.Integer, nullable=True)
    unit_id = db.Column(db.Integer, nullable=False)  # Foreign key constraint added via SQL migration
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id'), nullable=True)  # Link to inquiry (for pre-assignment contracts)
    
    # Contract Type and Duration
    contract_type = db.Column(db.String(20), nullable=False)  # 'quarterly' or 'yearly'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    
    # Financial Terms
    monthly_rent = db.Column(Numeric(10, 2), nullable=False)
    security_deposit = db.Column(Numeric(10, 2), nullable=True)
    total_contract_value = db.Column(Numeric(10, 2), nullable=True)
    
    # Contract Status
    status = db.Column(db.String(20), default='draft', nullable=False)
    
    # Contract Terms and Conditions
    terms_and_conditions = db.Column(db.Text, nullable=True)
    special_conditions = db.Column(db.Text, nullable=True)
    
    # Renewal Information
    is_renewal = db.Column(db.Boolean, default=False, nullable=False)
    parent_contract_id = db.Column(db.Integer, db.ForeignKey('rental_contracts.id'), nullable=True)
    renewal_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Signatures and Approval
    tenant_signed = db.Column(db.Boolean, default=False, nullable=False)
    tenant_signed_date = db.Column(db.DateTime, nullable=True)
    landlord_signed = db.Column(db.Boolean, default=False, nullable=False)
    landlord_signed_date = db.Column(db.DateTime, nullable=True)
    landlord_signed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Termination Information
    termination_date = db.Column(db.Date, nullable=True)
    termination_reason = db.Column(db.Text, nullable=True)
    terminated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Document References
    contract_document_path = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __init__(self, unit_id, property_id, contract_type, start_date, monthly_rent, 
                 tenant_id=None, tenant_unit_id=None, inquiry_id=None, security_deposit=None, 
                 end_date=None, **kwargs):
        """Initialize a rental contract (can be created before tenant assignment)."""
        self.unit_id = unit_id
        self.property_id = property_id
        self.contract_type = contract_type
        self.start_date = start_date
        self.monthly_rent = monthly_rent
        self.tenant_id = tenant_id
        self.tenant_unit_id = tenant_unit_id
        self.inquiry_id = inquiry_id
        self.security_deposit = security_deposit
        
        # Generate contract number if not provided
        if 'contract_number' not in kwargs:
            self.contract_number = self._generate_contract_number()
        
        # Calculate end_date if not provided
        if end_date is None:
            self.end_date = self._calculate_end_date(start_date, contract_type)
        else:
            self.end_date = end_date
        
        # Calculate total contract value
        self.total_contract_value = self._calculate_total_value()
        
        # Set default status
        if 'status' not in kwargs:
            self.status = 'draft'
        
        # Set other kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def _generate_contract_number(self):
        """Generate a unique contract number."""
        date_str = date.today().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"CONTRACT-{date_str}-{unique_id}"
    
    def _calculate_end_date(self, start_date, contract_type):
        """Calculate end date based on contract type."""
        if contract_type == 'quarterly':
            return start_date + timedelta(days=180)
        elif contract_type == 'yearly':
            return start_date + timedelta(days=365)
        else:
            return start_date + timedelta(days=30)
    
    def _calculate_total_value(self):
        """Calculate total contract value based on duration and monthly rent."""
        if not self.start_date or not self.end_date or not self.monthly_rent:
            return None
        delta = self.end_date - self.start_date
        months = delta.days / 30.44
        return float(self.monthly_rent) * months
    
    @property
    def is_expired(self):
        """Check if contract is expired."""
        if self.end_date:
            return self.end_date < date.today()
        return False
    
    @property
    def days_until_expiry(self):
        """Get days until contract expiry."""
        if self.end_date:
            delta = self.end_date - date.today()
            return delta.days
        return None
    
    @property
    def is_active(self):
        """Check if contract is currently active."""
        return (self.status == 'active' and 
                self.start_date <= date.today() <= self.end_date and
                not self.is_expired)
    
    @property
    def is_fully_signed(self):
        """Check if both parties have signed."""
        return self.tenant_signed and self.landlord_signed
    
    @property
    def duration_months(self):
        """Get contract duration in months."""
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            return round(delta.days / 30.44, 1)
        return None
    
    def link_to_tenant_unit(self, tenant_unit_id, tenant_id):
        """Link contract to tenant_unit after tenant assignment."""
        self.tenant_unit_id = tenant_unit_id
        self.tenant_id = tenant_id
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def link_to_tenant_unit(self, tenant_unit_id, tenant_profile_id):
        """Link contract to tenant_unit after tenant assignment."""
        self.tenant_unit_id = tenant_unit_id
        self.tenant_id = tenant_profile_id  # This is the tenant profile ID (from tenants table)
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def activate(self):
        """Activate the contract."""
        self.status = 'active'
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def sign_by_tenant(self):
        """Mark contract as signed by tenant."""
        self.tenant_signed = True
        self.tenant_signed_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        # Auto-activate if both parties have signed
        if self.tenant_signed and self.landlord_signed:
            self.activate()
        
        db.session.commit()
    
    def sign_by_landlord(self, landlord_user_id):
        """Mark contract as signed by landlord."""
        self.landlord_signed = True
        self.landlord_signed_by = landlord_user_id
        self.landlord_signed_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        # Auto-activate if both parties have signed
        if self.tenant_signed and self.landlord_signed:
            self.activate()
        
        db.session.commit()
    
    def to_dict(self, include_tenant=False, include_unit=False):
        """Convert contract to dictionary."""
        return {
            'id': self.id,
            'contract_number': self.contract_number,
            'tenant_unit_id': self.tenant_unit_id,
            'tenant_id': self.tenant_id,
            'unit_id': self.unit_id,
            'property_id': self.property_id,
            'inquiry_id': self.inquiry_id,
            'contract_type': self.contract_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'monthly_rent': float(self.monthly_rent) if self.monthly_rent else None,
            'security_deposit': float(self.security_deposit) if self.security_deposit else None,
            'total_contract_value': float(self.total_contract_value) if self.total_contract_value else None,
            'status': self.status,
            'terms_and_conditions': self.terms_and_conditions,
            'special_conditions': self.special_conditions,
            'is_renewal': self.is_renewal,
            'parent_contract_id': self.parent_contract_id,
            'renewal_count': self.renewal_count,
            'tenant_signed': self.tenant_signed,
            'tenant_signed_date': self.tenant_signed_date.isoformat() if self.tenant_signed_date else None,
            'landlord_signed': self.landlord_signed,
            'landlord_signed_date': self.landlord_signed_date.isoformat() if self.landlord_signed_date else None,
            'landlord_signed_by': self.landlord_signed_by,
            'termination_date': self.termination_date.isoformat() if self.termination_date else None,
            'termination_reason': self.termination_reason,
            'terminated_by': self.terminated_by,
            'contract_document_path': self.contract_document_path,
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
            'is_active': self.is_active,
            'is_fully_signed': self.is_fully_signed,
            'duration_months': self.duration_months,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f'<RentalContract {self.contract_number} - {self.contract_type} - {self.status}>'

