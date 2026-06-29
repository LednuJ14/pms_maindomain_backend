"""
Admin repository: encapsulates admin statistics queries
"""
from typing import Dict
from app.models.user import User, UserRole
from app.models.property import Property
from app.models.subscription import Subscription
from app import db
from sqlalchemy import text


class AdminRepository:
    def totals(self) -> Dict:
        try:
            # Get users count
            users_count = User.query.count()
            
            # Get properties count
            properties_count = Property.query.count()
            
            # Get subscriptions count (with fallback)
            subscriptions_count = 0
            try:
                subscriptions_count = Subscription.query.count()
            except Exception:
                # Fallback: check if table exists using raw SQL
                try:
                    result = db.session.execute(text("SELECT COUNT(*) FROM subscriptions"))
                    subscriptions_count = result.scalar()
                except Exception:
                    subscriptions_count = 0
            
            return {
                'users': users_count,
                'properties': properties_count,
                'subscriptions': subscriptions_count,
            }
        except Exception as e:
            # Return safe defaults if anything fails
            return {
                'users': 0,
                'properties': 0,
                'subscriptions': 0,
            }

    def user_role_breakdown(self) -> Dict:
        try:
            return {role.value: User.query.filter_by(role=role).count() for role in UserRole}
        except Exception:
            # Return safe defaults if anything fails
            return {role.value: 0 for role in UserRole}

    def get_pending_properties_count(self) -> int:
        """Get count of properties pending approval"""
        try:
            from app.models.property import PropertyStatus
            return Property.query.filter_by(status=PropertyStatus.PENDING_APPROVAL).count()
        except Exception:
            try:
                result = db.session.execute(text("SELECT COUNT(*) FROM properties WHERE status = 'pending_approval'"))
                return result.scalar() or 0
            except Exception:
                return 0

    def get_tenants_count(self) -> int:
        """Get count of tenant users"""
        try:
            return User.query.filter_by(role=UserRole.TENANT).count()
        except Exception:
            try:
                result = db.session.execute(text("SELECT COUNT(*) FROM users WHERE role = 'tenant'"))
                return result.scalar() or 0
            except Exception:
                return 0

    def get_total_revenue(self) -> float:
        """Get total revenue from active subscriptions"""
        try:
            result = db.session.execute(text("""
                SELECT COALESCE(SUM(tu.monthly_rent), 0) as total_revenue
                FROM tenant_units tu
                INNER JOIN units u ON u.id = tu.unit_id
                WHERE (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
            """))
            row = result.fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0

    def get_recent_activities(self, admin_user_id: int, limit: int = 10) -> list:
        """Get recent activities from notifications for a specific admin user"""
        try:
            result = db.session.execute(text("""
                SELECT 
                    n.id,
                    n.type,
                    n.title,
                    n.message,
                    n.created_at,
                    n.related_id,
                    n.related_type,
                    u.first_name,
                    u.last_name,
                    u.email
                FROM notifications n
                LEFT JOIN users u ON n.user_id = u.id
                WHERE n.is_deleted = 0 AND n.user_id = :admin_user_id
                ORDER BY n.created_at DESC
                LIMIT :limit
            """), {'admin_user_id': admin_user_id, 'limit': limit})
            
            activities = []
            for row in result:
                # Handle notification type - it might be an enum or a string
                activity_type = str(row.type)
                if hasattr(row.type, 'value'):
                    activity_type = row.type.value
                elif isinstance(row.type, str):
                    activity_type = row.type
                
                activities.append({
                    'id': row.id,
                    'type': activity_type,
                    'title': row.title or 'Activity',
                    'message': row.message or '',
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'related_id': row.related_id,
                    'related_type': row.related_type,
                    'user_name': f"{row.first_name or ''} {row.last_name or ''}".strip() or row.email or 'System'
                })
            return activities
        except Exception:
            return []