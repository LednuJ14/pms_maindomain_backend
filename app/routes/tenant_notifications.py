"""
Tenant Notifications API Routes
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from app import db
from app.models.notification import Notification, NotificationType
from app.utils.decorators import tenant_required
from app.utils.error_handlers import handle_api_error

tenant_notifications_bp = Blueprint('tenant_notifications', __name__)

@tenant_notifications_bp.route('', methods=['GET'], strict_slashes=False)
@tenant_notifications_bp.route('/', methods=['GET'], strict_slashes=False)
@tenant_required
def get_tenant_notifications(current_user):
    """
    Get tenant notifications
    ---
    tags:
      - Tenant Notifications
    summary: Get all notifications for the tenant
    description: Retrieve all notifications for the authenticated tenant
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
        # All conditions are hardcoded or use parameters
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
        total = db.session.execute(count_query, {'user_id': current_user.id}).scalar()
        
        # Get unread count
        unread_query = text("""
            SELECT COUNT(*) as unread_count
            FROM notifications
            WHERE user_id = :user_id AND is_read = 0 AND is_deleted = 0
        """)
        unread_count = db.session.execute(unread_query, {
            'user_id': current_user.id
        }).scalar()
        
        # Convert to dictionaries
        notifications_data = []
        for row in notifications_rows:
            try:
                # Safely format datetime - ensure UTC timezone is included with 'Z' suffix
                def safe_iso(dt):
                    try:
                        if dt:
                            # If datetime is timezone-naive, assume UTC
                            if dt.tzinfo is None:
                                from datetime import timezone
                                dt = dt.replace(tzinfo=timezone.utc)
                            # Return ISO format with 'Z' suffix for UTC
                            iso_str = dt.isoformat()
                            # Ensure it ends with 'Z' if it's UTC
                            if dt.tzinfo and dt.tzinfo.utcoffset(dt) is not None and dt.tzinfo.utcoffset(dt).total_seconds() == 0:
                                if not iso_str.endswith('Z'):
                                    iso_str = iso_str.replace('+00:00', 'Z').replace('-00:00', 'Z')
                            elif not iso_str.endswith('Z') and '+' not in iso_str and '-' not in iso_str[-6:]:
                                # If no timezone info, append Z to indicate UTC
                                iso_str = iso_str + 'Z'
                            return iso_str
                        return None
                    except Exception:
                        return str(dt) if dt else None
                
                # Safely handle enum type
                notification_type = row.get('notification_type')
                if notification_type:
                    # Try to validate it's a valid enum, otherwise use as string
                    try:
                        NotificationType(notification_type)
                        type_value = notification_type
                    except (ValueError, LookupError):
                        # If it's an old/invalid enum value, use as string
                        type_value = str(notification_type)
                else:
                    type_value = 'system'
                
                notifications_data.append({
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
            except Exception as dict_error:
                current_app.logger.error(f'Error converting notification {row.get("id")} to dict: {str(dict_error)}')
                # Skip problematic notifications but continue processing others
                continue
        
        return jsonify({
            'notifications': notifications_data,
            'total': total,
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Error fetching tenant notifications: {str(e)}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, f'Failed to fetch notifications: {str(e)}')

@tenant_notifications_bp.route('/<int:notification_id>/read', methods=['PUT'])
@tenant_required
def mark_notification_as_read(current_user, notification_id):
    """Mark a specific notification as read."""
    try:
        # Use raw SQL to avoid enum conversion issues
        from sqlalchemy import text
        
        # Check if notification exists and belongs to user
        check_query = text("""
            SELECT id, is_read, notification_type, title, message, related_entity_id, related_entity_type, created_at, read_at
            FROM notifications
            WHERE id = :nid AND user_id = :uid AND is_deleted = 0
        """)
        notification_row = db.session.execute(check_query, {
            'nid': notification_id,
            'uid': current_user.id
        }).mappings().first()
        
        if not notification_row:
            return jsonify({'error': 'Notification not found'}), 404
        
        # Update if not already read
        if not notification_row.get('is_read'):
            update_query = text("""
                UPDATE notifications
                SET is_read = 1, read_at = NOW()
                WHERE id = :nid AND user_id = :uid
            """)
            db.session.execute(update_query, {
                'nid': notification_id,
                'uid': current_user.id
            })
            db.session.commit()
        
        # Return updated notification data
        updated_row = db.session.execute(check_query, {
            'nid': notification_id,
            'uid': current_user.id
        }).mappings().first()
        
        # Safely format datetime
        def safe_iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return str(dt) if dt else None
        
        # Safely handle enum type
        notification_type = updated_row.get('notification_type')
        if notification_type:
            try:
                NotificationType(notification_type)
                type_value = notification_type
            except (ValueError, LookupError):
                type_value = str(notification_type)
        else:
            type_value = 'system'
        
        notification_data = {
            'id': updated_row.get('id'),
            'type': type_value,
            'title': updated_row.get('title'),
            'message': updated_row.get('message'),
            'is_read': bool(updated_row.get('is_read')),
            'related_id': updated_row.get('related_entity_id'),
            'related_type': updated_row.get('related_entity_type'),
            'created_at': safe_iso(updated_row.get('created_at')),
            'read_at': safe_iso(updated_row.get('read_at'))
        }
        
        return jsonify({
            'message': 'Notification marked as read',
            'notification': notification_data
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error marking notification as read: {str(e)}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, f'Failed to mark notification as read: {str(e)}')

@tenant_notifications_bp.route('/mark-all-read', methods=['PUT'])
@tenant_required
def mark_all_notifications_as_read(current_user):
    """Mark all notifications as read for the current tenant."""
    try:
        # Use raw SQL to avoid enum conversion issues
        from sqlalchemy import text
        
        update_query = text("""
            UPDATE notifications
            SET is_read = 1, read_at = NOW()
            WHERE user_id = :uid AND is_read = 0 AND is_deleted = 0
        """)
        
        result = db.session.execute(update_query, {
            'uid': current_user.id
        })
        updated = result.rowcount
        db.session.commit()
        
        return jsonify({
            'message': 'All notifications marked as read',
            'updated_count': updated
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error marking all notifications as read: {str(e)}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, f'Failed to mark all notifications as read: {str(e)}')

@tenant_notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@tenant_required
def delete_notification(current_user, notification_id):
    """Delete (soft delete) a specific notification."""
    try:
        # Use raw SQL to avoid enum conversion issues
        from sqlalchemy import text
        
        # Check if notification exists and belongs to user
        check_query = text("""
            SELECT id FROM notifications
            WHERE id = :nid AND user_id = :uid AND is_deleted = 0
        """)
        notification_row = db.session.execute(check_query, {
            'nid': notification_id,
            'uid': current_user.id
        }).first()
        
        if not notification_row:
            return jsonify({'error': 'Notification not found'}), 404
        
        # Soft delete
        delete_query = text("""
            UPDATE notifications
            SET is_deleted = 1
            WHERE id = :nid AND user_id = :uid
        """)
        db.session.execute(delete_query, {
            'nid': notification_id,
            'uid': current_user.id
        })
        db.session.commit()
        
        return jsonify({
            'message': 'Notification deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting notification: {str(e)}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, f'Failed to delete notification: {str(e)}')

