"""
Dashboard service for tenant portal dashboard.
"""
from typing import Dict
from app.models.inquiry import Inquiry
from app.utils.subdomain_helpers import get_current_property, validate_tenant_access
from app.services.portal_service import PortalNotFound


class DashboardService:
    class Forbidden(Exception):
        pass

    def tenant_dashboard_for_portal(self, current_user) -> Dict:
        if not current_user.is_tenant():
            raise self.Forbidden('Only tenants can access this dashboard')

        property_obj = get_current_property()
        if not property_obj:
            raise PortalNotFound('No property associated with this subdomain')

        access_validation = validate_tenant_access(current_user, property_obj)
        if not access_validation['allowed']:
            raise self.Forbidden(access_validation['reason'])

        inquiries = Inquiry.query.filter_by(
            tenant_id=current_user.id,
            property_id=property_obj.id
        ).order_by(Inquiry.created_at.desc()).all()

        return {
            'property': property_obj.to_dict(include_owner=True),
            'tenant': current_user.to_dict(),
            'inquiries': [i.to_dict() for i in inquiries],
            'access_info': access_validation,
            'dashboard_stats': {
                'total_inquiries': len(inquiries),
                'pending_inquiries': len([i for i in inquiries if i.is_pending()]),
                'responded_inquiries': len([i for i in inquiries if i.is_responded()]),
            },
        }
