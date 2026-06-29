"""
Admin service: dashboard stats
"""
from typing import Dict
from app.repositories.admin_repository import AdminRepository


class AdminService:
    def __init__(self, repo: AdminRepository | None = None):
        self.repo = repo or AdminRepository()

    def dashboard_stats(self, admin_user_id: int) -> Dict:
        totals = self.repo.totals()
        user_roles = self.repo.user_role_breakdown()
        pending_properties = self.repo.get_pending_properties_count()
        tenants_count = self.repo.get_tenants_count()
        total_revenue = self.repo.get_total_revenue()
        recent_activities = self.repo.get_recent_activities(admin_user_id=admin_user_id, limit=10)
        
        return {
            'totals': {
                **totals,
                'pending_properties': pending_properties,
                'tenants': tenants_count,
                'revenue': total_revenue,
            },
            'user_breakdown': user_roles,
            'recent_activities': recent_activities,
        }
