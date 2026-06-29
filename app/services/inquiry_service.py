"""
Inquiry service for property portals.
"""
from datetime import datetime
from typing import Dict, List
from app import db
from app.models.inquiry import Inquiry, InquiryType
from app.utils.subdomain_helpers import get_current_property
from app.services.portal_service import PortalNotFound


class InquiryService:
    class ValidationError(Exception):
        def __init__(self, missing_fields: List[str]):
            self.missing_fields = missing_fields
            super().__init__('Missing required fields')

    def create_inquiry_for_portal(self, payload: Dict) -> Dict:
        property_obj = get_current_property()
        if not property_obj:
            raise PortalNotFound('No property associated with this subdomain')

        required = ['tenant_name', 'tenant_email', 'message']
        missing = [f for f in required if not payload.get(f)]
        if missing:
            raise self.ValidationError(missing)

        inquiry = Inquiry(
            property_id=property_obj.id,
            tenant_id=None,
            property_manager_id=property_obj.owner_id,
            message=payload['message'],
            tenant_name=payload['tenant_name'],
            tenant_email=payload['tenant_email'],
        )

        # Set unit_id if provided (for specific unit inquiries)
        if payload.get('unit_id'):
            inquiry.unit_id = payload['unit_id']

        if payload.get('tenant_phone'):
            inquiry.tenant_phone = payload['tenant_phone']

        if payload.get('preferred_viewing_date'):
            try:
                inquiry.preferred_viewing_date = datetime.strptime(
                    payload['preferred_viewing_date'], '%Y-%m-%d %H:%M'
                )
            except ValueError:
                # keep field empty if invalid; caller can validate earlier if needed
                pass

        if payload.get('inquiry_type'):
            try:
                inquiry.inquiry_type = InquiryType(payload['inquiry_type'])
            except ValueError:
                pass

        db.session.add(inquiry)
        property_obj.increment_inquiry_count()
        db.session.commit()

        return {
            'message': 'Inquiry submitted successfully',
            'inquiry': inquiry.to_dict(include_property=True),
            'next_steps': [
                'The property manager will review your inquiry',
                'You will receive a response via email',
                'Check your email for further communication',
            ],
        }
