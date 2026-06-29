"""
Subscription Models
"""
from datetime import datetime, timedelta
from decimal import Decimal
from app import db
import enum

class SubscriptionStatus(enum.Enum):
    """Subscription status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    TRIAL = "trial"

class BillingInterval(enum.Enum):
    """Billing interval enumeration."""
    MONTHLY = "monthly"
    YEARLY = "yearly"

class SubscriptionPlan(db.Model):
    """Subscription plan model."""
    
    __tablename__ = 'subscription_plans'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Plan details
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    
    # Pricing
    monthly_price = db.Column(db.Numeric(10, 2), nullable=False)
    yearly_price = db.Column(db.Numeric(10, 2)) 
    
    # Limits and features
    max_properties = db.Column(db.Integer, nullable=False)
    analytics_enabled = db.Column(db.Boolean, default=False)
    priority_support = db.Column(db.Boolean, default=False)
    api_access = db.Column(db.Boolean, default=False)
    advanced_reporting = db.Column(db.Boolean, default=False)
    # Extra feature flags to match database schema
    staff_management_enabled = db.Column(db.Boolean, default=False)
    subdomain_access = db.Column(db.Boolean, default=False)
    
    # Plan settings
    is_active = db.Column(db.Boolean, default=True)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    subscriptions = db.relationship('Subscription', backref='plan', lazy='dynamic')
    
    def __init__(self, name, monthly_price, max_properties, **kwargs):
        """Initialize subscription plan with required fields."""
        self.name = name
        self.monthly_price = monthly_price
        self.max_properties = max_properties
        
        # Set optional fields from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def get_yearly_discount_percentage(self):
        """Calculate yearly discount percentage."""
        if not self.yearly_price:
            return 0
        monthly_yearly = float(self.monthly_price) * 12
        yearly = float(self.yearly_price)
        if monthly_yearly > yearly:
            return round(((monthly_yearly - yearly) / monthly_yearly) * 100, 1)
        return 0
    
    def get_effective_price(self, billing_interval):
        """Get effective price based on billing interval."""
        if billing_interval == BillingInterval.YEARLY and self.yearly_price:
            return float(self.yearly_price)
        return float(self.monthly_price)
    
    def to_dict(self, include_stats=False):
        """Convert subscription plan to dictionary representation."""
        def safe_datetime_format(dt_field):
            """Safely format datetime field to ISO string"""
            if dt_field is None:
                return None
            if hasattr(dt_field, 'isoformat'):
                return dt_field.isoformat()
            # If it's already a string, return as is
            return str(dt_field)
        
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            # Flatten pricing fields for frontend compatibility
            'monthly_price': float(self.monthly_price) if self.monthly_price else 0.0,
            'yearly_price': float(self.yearly_price) if self.yearly_price else None,
            'yearly_discount_percentage': self.get_yearly_discount_percentage(),
            # Flatten limits for frontend compatibility
            'max_properties': self.max_properties,
            # Flatten features for frontend compatibility
            'analytics_enabled': bool(self.analytics_enabled),
            'priority_support': bool(self.priority_support),
            'api_access': bool(self.api_access),
            'advanced_reporting': bool(self.advanced_reporting),
            'staff_management_enabled': bool(self.staff_management_enabled),
            'subdomain_access': bool(self.subdomain_access),
            # Other fields
            'is_active': bool(self.is_active),
            'created_at': safe_datetime_format(self.created_at),
            'updated_at': safe_datetime_format(self.updated_at)
        }
        
        if include_stats:
            try:
                # Add subscriber count for frontend display
                subscriber_count = self.subscriptions.filter_by(status=SubscriptionStatus.ACTIVE).count()
                data['subscriber_count'] = subscriber_count
                data['total_subscriptions'] = self.subscriptions.count()
                data['active_subscriptions'] = subscriber_count
            except Exception as e:
                # If there's an error getting stats, set defaults
                data['subscriber_count'] = 0
                data['total_subscriptions'] = 0
                data['active_subscriptions'] = 0
        
        return data
    
    def __repr__(self):
        """String representation of subscription plan."""
        return f'<SubscriptionPlan {self.name}>'

class Subscription(db.Model):
    """User subscription model."""
    
    __tablename__ = 'subscriptions'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    
    # Subscription details
    # Persist enum "values" (lowercase strings) to match existing DB schema
    status = db.Column(
        db.Enum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SubscriptionStatus.TRIAL
    )
    billing_interval = db.Column(
        db.Enum(BillingInterval, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BillingInterval.MONTHLY
    )
    
    # Dates
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    trial_end_date = db.Column(db.DateTime)
    next_billing_date = db.Column(db.DateTime)
    
    # Usage tracking
    properties_used = db.Column(db.Integer, default=0)
    
    # Stripe-related fields removed

    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __init__(self, user_id, plan_id, billing_interval=BillingInterval.MONTHLY):
        """Initialize subscription with required fields."""
        self.user_id = user_id
        self.plan_id = plan_id
        self.billing_interval = billing_interval
        self.setup_trial()
    
    def setup_trial(self):
        """Set up subscription (no trial period)."""
        self.status = SubscriptionStatus.ACTIVE
        self.next_billing_date = self.calculate_next_billing_date()
    
    def calculate_next_billing_date(self):
        """Calculate next billing date based on billing interval."""
        start_date = self.start_date or datetime.utcnow()
        if self.billing_interval == BillingInterval.YEARLY:
            return start_date + timedelta(days=365)
        else:
            return start_date + timedelta(days=30)
    
    def is_active(self):
        """Check if subscription is active."""
        return self.status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
    
    def is_trial(self):
        """Check if subscription is in trial period."""
        return (self.status == SubscriptionStatus.TRIAL and 
                self.trial_end_date and 
                self.trial_end_date > datetime.utcnow())
    
    def days_until_trial_end(self):
        """Get days remaining in trial period."""
        if not self.is_trial():
            return 0
        delta = self.trial_end_date - datetime.utcnow()
        return max(0, delta.days)
    
    def can_add_property(self):
        """Check if user can add another property."""
        if not self.is_active():
            return False
        if not self.plan:
            return False
        return self.properties_used < self.plan.max_properties
    
    def get_properties_remaining(self):
        """Get number of properties remaining in plan."""
        if not self.plan:
            return 0
        return max(0, self.plan.max_properties - self.properties_used)
    
    def update_properties_used(self):
        """Update the count of properties used."""
        if self.user:
            from app.models.property import Property, PropertyStatus
            self.properties_used = self.user.properties.filter(
                Property.status.in_([PropertyStatus.ACTIVE, PropertyStatus.INACTIVE])
            ).count()
            db.session.commit()
    
    def cancel(self):
        """Cancel the subscription (mark status only)."""
        self.status = SubscriptionStatus.CANCELLED
        db.session.commit()
    
    def reactivate(self):
        """Reactivate a cancelled subscription."""
        if self.status == SubscriptionStatus.CANCELLED:
            self.status = SubscriptionStatus.ACTIVE
            self.next_billing_date = self.calculate_next_billing_date()
            db.session.commit()
    
    def upgrade_plan(self, new_plan_id):
        """Upgrade to a different plan."""
        old_plan = self.plan
        self.plan_id = new_plan_id
        # In a real implementation, you'd handle prorating and payment here
        db.session.commit()
    
    def to_dict(self, include_plan=True):
        """Convert subscription to dictionary representation."""
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'status': self.status.value,
            'billing_interval': self.billing_interval.value,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'next_billing_date': self.next_billing_date.isoformat() if self.next_billing_date else None,
            'usage': {
                'properties_used': self.properties_used,
                'properties_remaining': self.get_properties_remaining(),
                'can_add_property': self.can_add_property()
            },
            'trial': {
                'is_trial': self.is_trial(),
                'trial_end_date': self.trial_end_date.isoformat() if self.trial_end_date else None,
                'days_remaining': self.days_until_trial_end()
            },
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        if include_plan and self.plan:
            data['plan'] = self.plan.to_dict()
        
        return data
    
    def __repr__(self):
        """String representation of subscription."""
        return f'<Subscription {self.user.email} - {self.plan.name}>'
