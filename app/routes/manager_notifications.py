"""
Property Manager Notifications API Routes
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from app import db
from app.models.notification import Notification, NotificationType
from app.utils.decorators import manager_required
from app.utils.error_handlers import handle_api_error

manager_notifications_bp = Blueprint('manager_notifications', __name__)

def safe_iso(dt):
    """Safely format datetime to ISO string with UTC timezone."""
    if not dt:
        return None
    try:
        # Check if timezone info is already present
        if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
            return dt.isoformat()
        else:
            # Assume UTC if no timezone info, append 'Z'
            return dt.isoformat() + 'Z'
    except Exception:
        return str(dt) if dt else None

@manager_notifications_bp.route('', methods=['GET'], strict_slashes=False)
@manager_notifications_bp.route('/', methods=['GET'], strict_slashes=False)
@manager_required
def get_manager_notifications(current_user):
    """
    Get manager notifications
    ---
    tags:
      - Manager Notifications
    summary: Get all notifications for the property manager
    description: Retrieve all notifications for the authenticated property manager
    security:
      - Bearer: []
    parameters:
      - in: query
        name: limit
        type: integer
        description: Maximum number of notifications to return
      - in: query
        name: offset
        type: integer
        description: Number of notifications to skip
      - in: query
        name: unread_only
        type: boolean
        description: Return only unread notifications
    responses:
      200:
        description: Notifications retrieved successfully
        schema:
          type: object
          properties:
            notifications:
              type: array
              items:
                type: object
            total:
              type: integer
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        # Get query parameters
        limit = request.args.get('limit', type=int, default=50)
        offset = request.args.get('offset', type=int, default=0)
        unread_only = request.args.get('unread_only', type=bool, default=False)
        
        # Use raw SQL to avoid enum conversion issues
        from sqlalchemy import text
        
        # Build WHERE clause using parameterized queries (safe - no user input in WHERE clause)
        where_conditions = ["user_id = :user_id", "is_deleted = 0"]
        query_params = {
            'user_id': current_user.id,
            'limit': limit,
            'offset': offset
        }
        
        if unread_only:
            where_conditions.append("is_read = 0")
        
        where_sql = " AND ".join(where_conditions)
        
        # Get notifications - using parameterized query (where_sql is safe - only hardcoded conditions)
        notifications_query = text(f"""
            SELECT id, user_id, notification_type, title, message, is_read, 
                   related_entity_id, related_entity_type, created_at, read_at
            FROM notifications
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        notifications_rows = db.session.execute(notifications_query, query_params).mappings().all()
        
        # Get total count - using parameterized query
        count_query = text(f"""
            SELECT COUNT(*) as total
            FROM notifications
            WHERE {where_sql}
        """)
        total_result = db.session.execute(count_query, {'user_id': current_user.id}).mappings().first()
        total = total_result.get('total', 0) if total_result else 0
        
        # Get unread count
        unread_query = text("""
            SELECT COUNT(*) as unread
            FROM notifications
            WHERE user_id = :user_id AND is_read = 0 AND is_deleted = 0
        """)
        unread_result = db.session.execute(unread_query, {
            'user_id': current_user.id
        }).mappings().first()
        unread_count = unread_result.get('unread', 0) if unread_result else 0
        
        # Format notifications
        notifications = []
        for row in notifications_rows:
            # Safely handle enum conversion
            notification_type = row.get('notification_type')
            try:
                if isinstance(notification_type, str):
                    # Try to validate it's a valid enum
                    try:
                        NotificationType(notification_type)
                        type_value = notification_type
                    except (ValueError, LookupError):
                        type_value = notification_type
                else:
                    type_value = notification_type.value if hasattr(notification_type, 'value') else str(notification_type)
            except Exception:
                type_value = str(notification_type) if notification_type else None
            
            notifications.append({
                'id': row.get('id'),
                'type': type_value,
                'title': row.get('title'),
                'message': row.get('message'),
                'is_read': bool(row.get('is_read')),
                'related_id': row.get('related_entity_id'),
                'related_type': row.get('related_entity_type'),
                'created_at': safe_iso(row.get('created_at')),
                'read_at': safe_iso(row.get('read_at'))
            })
        
        return jsonify({
            'notifications': notifications,
            'total': total,
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get manager notifications error: {e}')
        return handle_api_error(500, f"Failed to retrieve notifications: {str(e)}")

@manager_notifications_bp.route('/unread-count', methods=['GET'], strict_slashes=False)
@manager_required
def get_unread_count(current_user):
    """Get unread notification count for the current property manager."""
    try:
        from sqlalchemy import text
        
        result = db.session.execute(text("""
            SELECT COUNT(*) as unread
            FROM notifications
            WHERE user_id = :user_id AND is_read = 0 AND is_deleted = 0
        """), {
            'user_id': current_user.id
        }).mappings().first()
        
        unread_count = result.get('unread', 0) if result else 0
        
        return jsonify({
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get unread count error: {e}')
        return handle_api_error(500, f"Failed to retrieve unread count: {str(e)}")

@manager_notifications_bp.route('/<int:notification_id>/read', methods=['PUT'], strict_slashes=False)
@manager_required
def mark_notification_as_read(current_user, notification_id):
    """Mark a specific notification as read."""
    try:
        from sqlalchemy import text
        
        # Verify notification belongs to current user
        notification_row = db.session.execute(text("""
            SELECT id, user_id, is_read
            FROM notifications
            WHERE id = :nid AND user_id = :uid AND is_deleted = 0
        """), {
            'nid': notification_id,
            'uid': current_user.id
        }).mappings().first()
        
        if not notification_row:
            return handle_api_error(404, "Notification not found")
        
        if notification_row.get('is_read'):
            # Already read, return success
            return jsonify({
                'success': True,
                'message': 'Notification already marked as read'
            }), 200
        
        # Mark as read
        db.session.execute(text("""
            UPDATE notifications
            SET is_read = 1, read_at = NOW()
            WHERE id = :nid
        """), {
            'nid': notification_id
        })
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Mark notification as read error: {e}')
        return handle_api_error(500, f"Failed to mark notification as read: {str(e)}")

@manager_notifications_bp.route('/read-all', methods=['PUT'], strict_slashes=False)
@manager_required
def mark_all_as_read(current_user):
    """Mark all notifications as read for the current property manager."""
    try:
        from sqlalchemy import text
        
        db.session.execute(text("""
            UPDATE notifications
            SET is_read = 1, read_at = NOW()
            WHERE user_id = :uid AND is_read = 0 AND is_deleted = 0
        """), {
            'uid': current_user.id
        })
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'All notifications marked as read'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Mark all as read error: {e}')
        return handle_api_error(500, f"Failed to mark all notifications as read: {str(e)}")

@manager_notifications_bp.route('/<int:notification_id>', methods=['DELETE'], strict_slashes=False)
@manager_required
def delete_notification(current_user, notification_id):
    """Delete a specific notification (soft delete)."""
    try:
        from sqlalchemy import text
        
        # Verify notification belongs to current user
        notification_row = db.session.execute(text("""
            SELECT id, user_id
            FROM notifications
            WHERE id = :nid AND user_id = :uid AND is_deleted = 0
        """), {
            'nid': notification_id,
            'uid': current_user.id
        }).mappings().first()
        
        if not notification_row:
            return handle_api_error(404, "Notification not found")
        
        # Soft delete
        db.session.execute(text("""
            UPDATE notifications
            SET is_deleted = 1
            WHERE id = :nid
        """), {
            'nid': notification_id
        })
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification deleted'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Delete notification error: {e}')
        return handle_api_error(500, f"Failed to delete notification: {str(e)}")

