"""
Notification Service for Main-Domain Users
Handles creation and management of notifications for tenants and property managers
"""
from datetime import datetime
from app import db
from app.models.notification import Notification, NotificationType


class NotificationService:
    """Service for creating and managing notifications for tenants and property managers."""
    
    @staticmethod
    def create_notification(
        user_id,
        notification_type,
        title,
        message,
        related_id=None,
        related_type=None
    ):
        """
        Create a new notification for a tenant.
        
        Args:
            user_id: ID of the user to notify
            notification_type: NotificationType enum value
            title: Notification title
            message: Notification message
            related_id: Optional ID of related entity (inquiry_id, property_id, etc.)
            related_type: Optional type of related entity ('inquiry', 'property', etc.)
        
        Returns:
            Notification object or None if creation failed
        """
        try:
            # Explicitly set created_at to current UTC time
            from datetime import datetime, timezone
            from sqlalchemy import text
            
            # Use raw SQL to ensure we use the correct column names (related_entity_id, related_entity_type)
            # The database schema uses related_entity_id/related_entity_type, not related_id/related_type
            notification_type_value = notification_type.value if hasattr(notification_type, 'value') else str(notification_type)
            
            insert_sql = text("""
                INSERT INTO notifications (
                    user_id, notification_type, title, message, 
                    related_entity_id, related_entity_type,
                    is_read, is_deleted, created_at
                ) VALUES (
                    :user_id, :notification_type, :title, :message,
                    :related_entity_id, :related_entity_type,
                    :is_read, :is_deleted, NOW()
                )
            """)
            
            result = db.session.execute(insert_sql, {
                'user_id': user_id,
                'notification_type': notification_type_value,
                'title': title,
                'message': message,
                'related_entity_id': related_id,
                'related_entity_type': related_type,
                'is_read': False,
                'is_deleted': False
            })
            
            db.session.commit()
            
            # Fetch the created notification using raw SQL to match column names
            notification_id = result.lastrowid
            fetch_sql = text("""
                SELECT id, user_id, notification_type, title, message, is_read,
                       related_entity_id, related_entity_type, created_at, read_at, is_deleted
                FROM notifications
                WHERE id = :notification_id
            """)
            notification_row = db.session.execute(fetch_sql, {'notification_id': notification_id}).mappings().first()
            
            if notification_row:
                # Create a simple dict representation since we're using raw SQL
                return {
                    'id': notification_row['id'],
                    'user_id': notification_row['user_id'],
                    'type': notification_row['notification_type'],
                    'title': notification_row['title'],
                    'message': notification_row['message'],
                    'is_read': notification_row['is_read'],
                    'related_entity_id': notification_row['related_entity_id'],
                    'related_entity_type': notification_row['related_entity_type'],
                    'created_at': notification_row['created_at'],
                    'read_at': notification_row['read_at'],
                    'is_deleted': notification_row['is_deleted']
                }
            return None
        except Exception as e:
            db.session.rollback()
            from flask import current_app
            current_app.logger.error(f'Error creating notification: {str(e)}')
            return None
    
    @staticmethod
    def notify_inquiry_response(tenant_id, inquiry_id, property_name, manager_name):
        """Notify tenant when property manager responds to their inquiry."""
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.INQUIRY_RESPONSE,
            title="New Response to Your Inquiry",
            message=f"Property Manager {manager_name} responded to your inquiry about {property_name}.",
            related_id=inquiry_id,
            related_type="inquiry"
        )
    
    @staticmethod
    def notify_inquiry_status_change(tenant_id, inquiry_id, property_name, old_status, new_status):
        """Notify tenant when inquiry status changes."""
        status_messages = {
            "assigned": f"Your inquiry about {property_name} has been assigned to a property manager.",
            "responded": f"Your inquiry about {property_name} has been responded to.",
            "closed": f"Your inquiry about {property_name} has been closed.",
            "spam": f"Your inquiry about {property_name} was marked as spam."
        }
        
        message = status_messages.get(new_status, f"Your inquiry about {property_name} status changed from {old_status} to {new_status}.")
        
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.INQUIRY_STATUS_CHANGE,
            title="Inquiry Status Updated",
            message=message,
            related_id=inquiry_id,
            related_type="inquiry"
        )
    
    @staticmethod
    def notify_property_available(tenant_id, property_id, property_name, location=None):
        """Notify tenant when a property becomes available."""
        location_text = f" in {location}" if location else ""
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.PROPERTY_AVAILABLE,
            title="New Property Available",
            message=f"New property available: {property_name}{location_text}. Check it out!",
            related_id=property_id,
            related_type="property"
        )
    
    @staticmethod
    def notify_property_update(tenant_id, property_id, property_name, update_type="details"):
        """Notify tenant when property details are updated."""
        update_messages = {
            "price": f"{property_name} price has been updated.",
            "amenities": f"{property_name} amenities have been updated.",
            "photos": f"New photos have been added to {property_name}.",
            "details": f"{property_name} details have been updated."
        }
        
        message = update_messages.get(update_type, f"{property_name} has been updated.")
        
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.PROPERTY_UPDATE,
            title="Property Updated",
            message=message,
            related_id=property_id,
            related_type="property"
        )
    
    @staticmethod
    def notify_viewing_confirmed(tenant_id, inquiry_id, property_name, action="confirmed", date_time=None):
        """Notify tenant when viewing appointment is confirmed/rescheduled/cancelled."""
        action_messages = {
            "confirmed": f"Your viewing request for {property_name} has been confirmed.",
            "rescheduled": f"Your viewing appointment for {property_name} has been rescheduled.",
            "cancelled": f"Your viewing appointment for {property_name} has been cancelled."
        }
        
        message = action_messages.get(action, f"Your viewing request for {property_name} has been updated.")
        if date_time and action in ["confirmed", "rescheduled"]:
            message += f" Scheduled for {date_time}."
        
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.VIEWING_CONFIRMED,
            title="Viewing Appointment Update",
            message=message,
            related_id=inquiry_id,
            related_type="inquiry"
        )
    
    @staticmethod
    def notify_account_update(tenant_id, update_type="profile"):
        """Notify tenant when account/profile is updated."""
        update_messages = {
            "profile": "Your profile has been updated successfully.",
            "password": "Your password has been changed successfully.",
            "email": "Your email has been updated successfully.",
            "settings": "Your account settings have been updated."
        }
        
        message = update_messages.get(update_type, "Your account has been updated.")
        
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.ACCOUNT_UPDATE,
            title="Account Updated",
            message=message,
            related_id=tenant_id,
            related_type="account"
        )
    
    @staticmethod
    def notify_system(tenant_id, title, message):
        """Notify tenant with system message."""
        return NotificationService.create_notification(
            user_id=tenant_id,
            notification_type=NotificationType.SYSTEM,
            title=title,
            message=message,
            related_id=None,
            related_type="system"
        )
    
    # ==================== PROPERTY MANAGER NOTIFICATIONS ====================
    
    @staticmethod
    def notify_new_inquiry(manager_id, inquiry_id, tenant_name, property_name, unit_name=None):
        """Notify property manager when a new inquiry is received."""
        unit_text = f" for {unit_name}" if unit_name else ""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.NEW_INQUIRY,
            title="New Inquiry Received",
            message=f"{tenant_name} has submitted a new inquiry about {property_name}{unit_text}.",
            related_id=inquiry_id,
            related_type="inquiry"
        )
    
    @staticmethod
    def notify_property_approved(manager_id, property_id, property_name):
        """Notify property manager when their property is approved."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.PROPERTY_APPROVED,
            title="Property Approved",
            message=f"Your property '{property_name}' has been approved and is now active.",
            related_id=property_id,
            related_type="property"
        )
    
    @staticmethod
    def notify_property_rejected(manager_id, property_id, property_name, reason=None):
        """Notify property manager when their property is rejected."""
        reason_text = f" Reason: {reason}" if reason else ""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.PROPERTY_REJECTED,
            title="Property Rejected",
            message=f"Your property '{property_name}' has been rejected.{reason_text}",
            related_id=property_id,
            related_type="property"
        )
    
    @staticmethod
    def notify_unit_status_change(manager_id, unit_id, unit_name, old_status, new_status):
        """Notify property manager when unit status changes."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.UNIT_STATUS_CHANGE,
            title="Unit Status Changed",
            message=f"Unit '{unit_name}' status changed from {old_status} to {new_status}.",
            related_id=unit_id,
            related_type="unit"
        )
    
    @staticmethod
    def notify_tenant_assigned(manager_id, unit_id, unit_name, tenant_name):
        """Notify property manager when a tenant is assigned to a unit."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.TENANT_ASSIGNED,
            title="Tenant Assigned",
            message=f"{tenant_name} has been assigned to unit '{unit_name}'.",
            related_id=unit_id,
            related_type="unit"
        )
    
    @staticmethod
    def notify_tenant_unassigned(manager_id, unit_id, unit_name, tenant_name):
        """Notify property manager when a tenant is unassigned from a unit."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.TENANT_UNASSIGNED,
            title="Tenant Unassigned",
            message=f"{tenant_name} has been unassigned from unit '{unit_name}'. The unit is now vacant.",
            related_id=unit_id,
            related_type="unit"
        )
    
    @staticmethod
    def notify_subscription_expiring(manager_id, property_id, property_name, days_remaining):
        """Notify property manager when subscription is expiring soon."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRING,
            title="Subscription Expiring Soon",
            message=f"Your subscription for '{property_name}' expires in {days_remaining} day(s). Please renew to continue using the service.",
            related_id=property_id,
            related_type="subscription"
        )
    
    @staticmethod
    def notify_subscription_expired(manager_id, property_id, property_name):
        """Notify property manager when subscription has expired."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRED,
            title="Subscription Expired",
            message=f"Your subscription for '{property_name}' has expired. Please renew to continue using the service.",
            related_id=property_id,
            related_type="subscription"
        )
    
    @staticmethod
    def notify_manager_account_update(manager_id, update_type="profile"):
        """Notify property manager when account/profile is updated."""
        update_messages = {
            "profile": "Your profile has been updated successfully.",
            "password": "Your password has been changed successfully.",
            "email": "Your email has been updated successfully.",
            "settings": "Your account settings have been updated."
        }
        
        message = update_messages.get(update_type, "Your account has been updated.")
        
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.ACCOUNT_UPDATE,
            title="Account Updated",
            message=message,
            related_id=manager_id,
            related_type="account"
        )
    
    # ==================== ADMIN ACTION NOTIFICATIONS (for property managers) ====================
    
    @staticmethod
    def notify_billing_created(manager_id, bill_id, amount, plan_name, due_date=None):
        """Notify property manager when admin creates a billing entry."""
        due_text = f" Due date: {due_date}" if due_date else ""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.BILLING_CREATED,
            title="New Billing Entry Created",
            message=f"A new billing entry for {plan_name} plan (₱{amount:,.2f}) has been created.{due_text}",
            related_id=bill_id,
            related_type="billing"
        )
    
    @staticmethod
    def notify_billing_status_updated(manager_id, bill_id, old_status, new_status, plan_name=None):
        """Notify property manager when admin updates billing status."""
        plan_text = f" for {plan_name}" if plan_name else ""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.BILLING_STATUS_UPDATED,
            title="Billing Status Updated",
            message=f"Your billing{plan_text} status has been updated from {old_status} to {new_status}.",
            related_id=bill_id,
            related_type="billing"
        )
    
    @staticmethod
    def notify_payment_verified(manager_id, transaction_id, status, amount=None, plan_name=None):
        """Notify property manager when admin verifies their payment transaction."""
        amount_text = f" (₱{amount:,.2f})" if amount else ""
        plan_text = f" for {plan_name} plan" if plan_name else ""
        status_messages = {
            "Verified": f"Your payment{amount_text}{plan_text} has been verified and your subscription is now active. You can now enjoy all the features of your selected plan!",
            "Rejected": f"Your payment{amount_text}{plan_text} has been rejected. Please contact support or upload a new proof of payment.",
            "Pending": f"Your payment{amount_text}{plan_text} is still pending verification."
        }
        message = status_messages.get(status, f"Your payment{amount_text}{plan_text} status has been updated to {status}.")
        
        title = "Payment Verified - Subscription Activated" if status == "Verified" else "Payment Verification Update"
        
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.PAYMENT_VERIFIED,
            title=title,
            message=message,
            related_id=transaction_id,
            related_type="payment_transaction"
        )
    
    @staticmethod
    def notify_document_approved(manager_id, property_id, property_name, document_type):
        """Notify property manager when admin approves their document."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.DOCUMENT_APPROVED,
            title="Document Approved",
            message=f"Your {document_type} document for '{property_name}' has been approved by admin.",
            related_id=property_id,
            related_type="document"
        )
    
    @staticmethod
    def notify_document_rejected(manager_id, property_id, property_name, document_type, reason=None):
        """Notify property manager when admin rejects their document."""
        reason_text = f" Reason: {reason}" if reason else ""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.DOCUMENT_REJECTED,
            title="Document Rejected",
            message=f"Your {document_type} document for '{property_name}' has been rejected.{reason_text}",
            related_id=property_id,
            related_type="document"
        )
    
    @staticmethod
    def notify_portal_toggled(manager_id, property_id, property_name, is_enabled):
        """Notify property manager when admin toggles their portal status."""
        status_text = "enabled" if is_enabled else "disabled"
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.PORTAL_TOGGLED,
            title="Portal Status Changed",
            message=f"Your portal for '{property_name}' has been {status_text} by admin.",
            related_id=property_id,
            related_type="portal"
        )
    
    @staticmethod
    def notify_subscription_plan_created(manager_id, plan_id, plan_name):
        """Notify property manager when admin creates a new subscription plan (informational)."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.SUBSCRIPTION_PLAN_CREATED,
            title="New Subscription Plan Available",
            message=f"A new subscription plan '{plan_name}' is now available. You can upgrade your plan anytime.",
            related_id=plan_id,
            related_type="subscription_plan"
        )
    
    @staticmethod
    def notify_subscription_plan_updated(manager_id, plan_id, plan_name):
        """Notify property manager when admin updates a subscription plan they're subscribed to."""
        return NotificationService.create_notification(
            user_id=manager_id,
            notification_type=NotificationType.SUBSCRIPTION_PLAN_UPDATED,
            title="Subscription Plan Updated",
            message=f"Your subscription plan '{plan_name}' has been updated. Please review the changes.",
            related_id=plan_id,
            related_type="subscription_plan"
        )

