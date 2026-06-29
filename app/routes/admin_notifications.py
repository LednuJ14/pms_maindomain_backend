"""
Admin Notifications API Routes
"""
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from app import db
from app.utils.decorators import admin_required
from app.utils.error_handlers import handle_api_error

admin_notifications_bp = Blueprint('admin_notifications', __name__)


@admin_notifications_bp.route('', methods=['GET'])
@admin_notifications_bp.route('/', methods=['GET'])
@admin_required
def get_admin_notifications(current_user):
    """
    Get admin notifications
    ---
    tags:
      - Admin Notifications
    summary: Get all notifications for the admin
    description: Retrieve all notifications for the authenticated admin user
    security:
      - Bearer: []
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
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        # For now, admins see system notifications and activity logs
        # In the future, this could be expanded to show notifications about actions they've taken
        
        # Get system notifications (notifications where type is SYSTEM or related to admin actions)
        query = text("""
            SELECT id, notification_type, title, message, is_read, related_entity_id, related_entity_type, created_at, read_at
            FROM notifications
            WHERE user_id = :user_id
            AND is_deleted = 0
            ORDER BY created_at DESC
            LIMIT 50
        """)
        
        result = db.session.execute(query, {'user_id': current_user.id}).mappings().all()
        
        notifications = []
        for row in result:
            # Safely handle enum conversion
            notification_type = row.get('notification_type')
            try:
                if isinstance(notification_type, str):
                    type_value = notification_type
                else:
                    type_value = notification_type.value if hasattr(notification_type, 'value') else str(notification_type)
            except Exception:
                type_value = str(notification_type) if notification_type else None
            
            # Safely format datetime
            def safe_iso(dt):
                if not dt:
                    return None
                try:
                    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
                        return dt.isoformat()
                    else:
                        return dt.isoformat() + 'Z'
                except Exception:
                    return str(dt) if dt else None
            
            notifications.append({
                'id': row['id'],
                'type': type_value,
                'title': row['title'],
                'message': row['message'],
                'is_read': bool(row['is_read']),
                'related_id': row['related_entity_id'],
                'related_type': row['related_entity_type'],
                'created_at': safe_iso(row['created_at']),
                'read_at': safe_iso(row['read_at'])
            })
        
        return jsonify({
            'notifications': notifications,
            'unread_count': len([n for n in notifications if not n['is_read']])
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get admin notifications error: {e}')
        return handle_api_error(500, "Failed to retrieve notifications")


@admin_notifications_bp.route('/unread-count', methods=['GET'])
@admin_required
def get_unread_count(current_user):
    """Get unread notification count for admin."""
    try:
        query = text("""
            SELECT COUNT(*) as count
            FROM notifications
            WHERE user_id = :user_id
            AND is_read = 0
            AND is_deleted = 0
        """)
        
        result = db.session.execute(query, {'user_id': current_user.id}).fetchone()
        unread_count = result[0] if result else 0
        
        return jsonify({'unread_count': unread_count}), 200
        
    except Exception as e:
        current_app.logger.error(f'Get admin unread count error: {e}')
        return jsonify({'unread_count': 0}), 200  # Return safe default


@admin_notifications_bp.route('/<int:notification_id>/read', methods=['PUT', 'POST'])
@admin_required
def mark_as_read(current_user, notification_id):
    """Mark a notification as read."""
    try:
        # Verify notification belongs to current user
        check_query = text("""
            SELECT id FROM notifications
            WHERE id = :nid AND user_id = :user_id
        """)
        check_result = db.session.execute(check_query, {
            'nid': notification_id,
            'user_id': current_user.id
        }).fetchone()
        
        if not check_result:
            return handle_api_error(404, "Notification not found")
        
        # Update notification
        update_query = text("""
            UPDATE notifications
            SET is_read = 1, read_at = NOW()
            WHERE id = :nid AND user_id = :user_id
        """)
        
        db.session.execute(update_query, {
            'nid': notification_id,
            'user_id': current_user.id
        })
        db.session.commit()
        
        return jsonify({'message': 'Notification marked as read'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Mark notification as read error: {e}')
        return handle_api_error(500, "Failed to mark notification as read")


@admin_notifications_bp.route('/read-all', methods=['PUT', 'POST'])
@admin_required
def mark_all_as_read(current_user):
    """Mark all notifications as read for the current admin."""
    try:
        update_query = text("""
            UPDATE notifications
            SET is_read = 1, read_at = NOW()
            WHERE user_id = :user_id AND is_read = 0 AND is_deleted = 0
        """)
        
        db.session.execute(update_query, {'user_id': current_user.id})
        db.session.commit()
        
        return jsonify({'message': 'All notifications marked as read'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Mark all notifications as read error: {e}')
        return handle_api_error(500, "Failed to mark all notifications as read")


@admin_notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@admin_required
def delete_notification(current_user, notification_id):
    """Delete a notification (soft delete)."""
    try:
        # Verify notification belongs to current user
        check_query = text("""
            SELECT id FROM notifications
            WHERE id = :nid AND user_id = :user_id
        """)
        check_result = db.session.execute(check_query, {
            'nid': notification_id,
            'user_id': current_user.id
        }).fetchone()
        
        if not check_result:
            return handle_api_error(404, "Notification not found")
        
        # Soft delete notification
        delete_query = text("""
            UPDATE notifications
            SET is_deleted = 1
            WHERE id = :nid AND user_id = :user_id
        """)
        
        db.session.execute(delete_query, {
            'nid': notification_id,
            'user_id': current_user.id
        })
        db.session.commit()
        
        return jsonify({'message': 'Notification deleted'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Delete notification error: {e}')
        return handle_api_error(500, "Failed to delete notification")

