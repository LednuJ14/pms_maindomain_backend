"""
Admin controller (v2): delegates to AdminService
"""
from flask import Blueprint, jsonify, request, current_app
from app.utils.decorators import admin_required
from app.services.admin_service import AdminService
from app.services.subscriptions_service import SubscriptionsService

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def get_dashboard_stats(current_user):
    """
    Get admin dashboard statistics
    ---
    tags:
      - Admin
    summary: Get dashboard statistics (Admin only)
    description: Retrieve comprehensive statistics for the admin dashboard
    security:
      - Bearer: []
    responses:
      200:
        description: Dashboard statistics retrieved successfully
        schema:
          type: object
          properties:
            total_users:
              type: integer
            total_properties:
              type: integer
            total_subscriptions:
              type: integer
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        data = AdminService().dashboard_stats(admin_user_id=current_user.id)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get dashboard stats error: {e}')
        return jsonify({'error': 'Failed to retrieve dashboard statistics', 'message': 'An error occurred while fetching dashboard data'}), 500


@admin_bp.route('/health', methods=['GET'])
def health_check():
    """
    Admin service health check
    ---
    tags:
      - Admin
    summary: Check admin service health
    description: Returns the health status of the admin service
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
            service:
              type: string
    """
    return jsonify({'status': 'healthy', 'service': 'admin'}), 200


# Subscription Management Endpoints
@admin_bp.route('/subscription-plans', methods=['GET'])
@admin_required
def get_subscription_plans(current_user):
    """
    Get all subscription plans (Admin)
    ---
    tags:
      - Admin
    summary: List all subscription plans (Admin only)
    description: Retrieve all subscription plans with statistics. Admin access required.
    security:
      - Bearer: []
    responses:
      200:
        description: Subscription plans retrieved successfully
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  monthly_price:
                    type: number
                  is_active:
                    type: boolean
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        current_app.logger.info('Fetching subscription plans...')
        
        # Try to get plans directly from repository first
        from app.repositories.subscription_repository import SubscriptionRepository
        repo = SubscriptionRepository()
        plans = repo.list_all_plans()
        
        current_app.logger.info(f'Found {len(plans)} plans in database')
        
        # Convert to dict without stats first to isolate the issue
        plans_data = []
        for plan in plans:
            try:
                plan_dict = plan.to_dict(include_stats=False)
                plans_data.append(plan_dict)
                current_app.logger.info(f'Successfully converted plan: {plan.name}')
            except Exception as e:
                current_app.logger.error(f'Error converting plan {plan.name}: {e}')
                # Add a basic version if conversion fails
                plans_data.append({
                    'id': plan.id,
                    'name': plan.name,
                    'slug': plan.slug,
                    'monthly_price': float(plan.monthly_price) if plan.monthly_price else 0.0,
                    'is_active': bool(plan.is_active),
                    'subscriber_count': 0
                })
        
        data = {'data': plans_data}
        current_app.logger.info(f'Retrieved {len(plans_data)} plans successfully')
        return jsonify(data), 200
        
    except Exception as e:
        current_app.logger.error(f'Get subscription plans error: {e}', exc_info=True)
        return jsonify({'error': 'Failed to retrieve subscription plans', 'message': str(e)}), 500


@admin_bp.route('/subscription-plans', methods=['POST'])
@admin_required
def create_subscription_plan(current_user):
    """
    Create subscription plan
    ---
    tags:
      - Admin
    summary: Create a new subscription plan (Admin only)
    description: Create a new subscription plan with pricing and features
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - monthly_price
          properties:
            name:
              type: string
            slug:
              type: string
            monthly_price:
              type: number
            description:
              type: string
            features:
              type: object
    responses:
      201:
        description: Subscription plan created successfully
        schema:
          type: object
          properties:
            data:
              type: object
      400:
        description: Validation error
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        plan_data = request.get_json()
        data = SubscriptionsService().admin_create_plan(plan_data)
        
        # Notify all property managers about new subscription plan (informational)
        try:
            from app.services.notification_service import NotificationService
            from sqlalchemy import text
            from app import db
            
            created_plan = data.get('data', {})
            plan_id = created_plan.get('id')
            plan_name = plan_data.get('name') or created_plan.get('name') or 'New Plan'
            
            if plan_id:
                # Get all property managers (users with role 'manager' or 'property_manager')
                managers = db.session.execute(
                    text("""
                        SELECT id FROM users
                        WHERE role IN ('manager', 'property_manager', 'admin')
                        AND is_active = 1
                    """)
                ).fetchall()
                
                # Notify each manager (limit to avoid overwhelming the system)
                for manager_row in managers[:100]:  # Limit to first 100 managers
                    try:
                        NotificationService.notify_subscription_plan_created(
                            manager_id=manager_row[0],
                            plan_id=plan_id,
                            plan_name=plan_name
                        )
                    except Exception:
                        # Continue with next manager if one fails
                        pass
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send subscription plan creation notifications: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify(data), 201
    except Exception as e:
        current_app.logger.error(f'Create subscription plan error: {e}')
        return jsonify({'error': 'Failed to create subscription plan', 'message': str(e)}), 500


@admin_bp.route('/subscription-plans/<int:plan_id>', methods=['PUT'])
@admin_required
def update_subscription_plan(current_user, plan_id):
    """
    Update subscription plan
    ---
    tags:
      - Admin
    summary: Update an existing subscription plan (Admin only)
    description: Update subscription plan details including pricing and features
    security:
      - Bearer: []
    parameters:
      - in: path
        name: plan_id
        type: integer
        required: true
        description: The subscription plan ID
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            monthly_price:
              type: number
            description:
              type: string
            is_active:
              type: boolean
    responses:
      200:
        description: Subscription plan updated successfully
        schema:
          type: object
          properties:
            data:
              type: object
      400:
        description: Validation error
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      404:
        description: Plan not found
      500:
        description: Server error
    """
    try:
        plan_data = request.get_json()
        data = SubscriptionsService().admin_update_plan(plan_id, plan_data)
        
        # Notify property managers subscribed to this plan
        try:
            from app.services.notification_service import NotificationService
            from sqlalchemy import text
            from app import db
            
            updated_plan = data.get('data', {})
            plan_name = plan_data.get('name') or updated_plan.get('name') or 'Subscription Plan'
            
            # Get all managers subscribed to this plan
            subscribed_managers = db.session.execute(
                text("""
                    SELECT DISTINCT s.user_id
                    FROM subscriptions s
                    WHERE s.plan_id = :plan_id
                    AND s.status = 'active'
                """),
                {'plan_id': plan_id}
            ).fetchall()
            
            # Notify each subscribed manager
            for manager_row in subscribed_managers:
                try:
                    NotificationService.notify_subscription_plan_updated(
                        manager_id=manager_row[0],
                        plan_id=plan_id,
                        plan_name=plan_name
                    )
                except Exception:
                    # Continue with next manager if one fails
                    pass
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send subscription plan update notifications: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Update subscription plan error: {e}')
        return jsonify({'error': 'Failed to update subscription plan', 'message': str(e)}), 500


@admin_bp.route('/subscription-plans/<int:plan_id>', methods=['DELETE'])
@admin_required
def delete_subscription_plan(current_user, plan_id):
    """
    Delete subscription plan
    ---
    tags:
      - Admin
    summary: Delete a subscription plan (Admin only)
    description: Delete a subscription plan. Cannot delete plans with active subscriptions.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: plan_id
        type: integer
        required: true
        description: The subscription plan ID
    responses:
      200:
        description: Subscription plan deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Cannot delete plan with active subscriptions
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      404:
        description: Plan not found
      500:
        description: Server error
    """
    try:
        data = SubscriptionsService().admin_delete_plan(plan_id)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Delete subscription plan error: {e}')
        return jsonify({'error': 'Failed to delete subscription plan', 'message': str(e)}), 500


@admin_bp.route('/subscription-plans/<int:plan_id>/features', methods=['PUT'])
@admin_required
def update_subscription_plan_features(current_user, plan_id):
    try:
        features_data = request.get_json()
        data = SubscriptionsService().admin_update_plan_features(plan_id, features_data)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Update subscription plan features error: {e}')
        return jsonify({'error': 'Failed to update subscription plan features', 'message': str(e)}), 500


@admin_bp.route('/subscription-stats', methods=['GET'])
@admin_required
def get_subscription_stats(current_user):
    try:
        data = SubscriptionsService().admin_get_subscription_stats()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get subscription stats error: {e}')
        return jsonify({'error': 'Failed to retrieve subscription stats', 'message': str(e)}), 500


@admin_bp.route('/subscribers', methods=['GET'])
@admin_required
def get_subscribers(current_user):
    try:
        data = SubscriptionsService().admin_get_subscribers()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get subscribers error: {e}')
        return jsonify({'error': 'Failed to retrieve subscribers', 'message': str(e)}), 500


@admin_bp.route('/subscriptions/<int:subscription_id>', methods=['PUT'])
@admin_required
def update_subscription(current_user, subscription_id):
    try:
        data = request.get_json() or {}
        plan_id = data.get('plan_id')
        status = data.get('status')
        
        if plan_id is None and status is None:
            return jsonify({'error': 'Either plan_id or status must be provided'}), 400
        
        result = SubscriptionsService().admin_update_subscription(subscription_id, plan_id, status)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Update subscription error: {e}')
        if hasattr(e, 'status_code'):
            return jsonify({'error': str(e)}), e.status_code
        return jsonify({'error': 'Failed to update subscription', 'message': str(e)}), 500


@admin_bp.route('/billing-history', methods=['GET'])
@admin_required
def get_billing_history(current_user):
    try:
        data = SubscriptionsService().admin_get_billing_history()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get billing history error: {e}')
        return jsonify({'error': 'Failed to retrieve billing history', 'message': str(e)}), 500


@admin_bp.route('/billing', methods=['POST'])
@admin_required
def create_billing_entry(current_user):
    try:
        bill_data = request.get_json()
        
        # Validate required fields
        required_fields = ['customer_name', 'customer_email', 'plan_name', 'amount']
        for field in required_fields:
            if not bill_data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Set defaults
        from datetime import datetime, timedelta
        if not bill_data.get('due_date'):
            bill_data['due_date'] = datetime.now().date()
        if not bill_data.get('status'):
            bill_data['status'] = 'pending'
        if not bill_data.get('payment_method'):
            bill_data['payment_method'] = 'Credit Card'
        if not bill_data.get('bill_type'):
            bill_data['bill_type'] = 'subscription'
        
        data = SubscriptionsService().admin_create_billing(bill_data)
        
        # Notify property manager about billing creation
        try:
            from app.services.notification_service import NotificationService
            from sqlalchemy import text
            from app import db
            
            # Get user_id from created bill
            created_bill = data.get('data', {})
            bill_id = created_bill.get('id')
            user_id = bill_data.get('user_id')
            
            # If user_id not in bill_data, try to get it from email
            if not user_id and bill_data.get('customer_email'):
                user_row = db.session.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {'email': bill_data['customer_email']}
                ).fetchone()
                if user_row:
                    user_id = user_row[0]
            
            if user_id and bill_id:
                amount = float(bill_data.get('amount', 0))
                plan_name = bill_data.get('plan_name', 'Subscription')
                due_date = bill_data.get('due_date')
                
                NotificationService.notify_billing_created(
                    manager_id=user_id,
                    bill_id=bill_id,
                    amount=amount,
                    plan_name=plan_name,
                    due_date=due_date.isoformat() if hasattr(due_date, 'isoformat') else str(due_date) if due_date else None
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send billing notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify(data), 201
    except Exception as e:
        current_app.logger.error(f'Create billing entry error: {e}')
        return jsonify({'error': 'Failed to create billing entry', 'message': str(e)}), 500


@admin_bp.route('/billing/<int:bill_id>/status', methods=['PUT'])
@admin_required
def update_billing_status(current_user, bill_id):
    try:
        data = request.get_json()
        status = data.get('status')
        payment_date = data.get('payment_date')
        
        if not status:
            return jsonify({'error': 'Status is required'}), 400
        
        # Get old status and user info before updating
        try:
            from sqlalchemy import text
            from app import db
            
            bill_info = db.session.execute(
                text("""
                    SELECT user_id, status, plan_id, amount
                    FROM subscription_bills
                    WHERE id = :bill_id
                """),
                {'bill_id': bill_id}
            ).mappings().first()
            
            old_status = bill_info['status'] if bill_info else None
            user_id = bill_info['user_id'] if bill_info else None
            plan_id = bill_info['plan_id'] if bill_info else None
            
            # Get plan name if plan_id exists
            plan_name = None
            if plan_id:
                plan_row = db.session.execute(
                    text("SELECT name FROM subscription_plans WHERE id = :pid"),
                    {'pid': plan_id}
                ).fetchone()
                if plan_row:
                    plan_name = plan_row[0]
        except Exception as info_error:
            current_app.logger.warning(f"Failed to get bill info for notification: {str(info_error)}")
            old_status = None
            user_id = None
            plan_name = None
        
        result = SubscriptionsService().admin_update_billing_status(bill_id, status, payment_date)
        
        # Notify property manager about billing status update
        try:
            from app.services.notification_service import NotificationService
            if user_id and old_status and old_status != status:
                NotificationService.notify_billing_status_updated(
                    manager_id=user_id,
                    bill_id=bill_id,
                    old_status=old_status,
                    new_status=status,
                    plan_name=plan_name
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send billing status notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Update billing status error: {e}')
        return jsonify({'error': 'Failed to update billing status', 'message': str(e)}), 500


# --- Manual payment transactions (proofs) ---
@admin_bp.route('/payment-transactions', methods=['GET', 'OPTIONS'])
@admin_required
def list_payment_transactions(current_user):
    try:
        if request.method == 'OPTIONS':
            return jsonify({'ok': True}), 200
        # Soft implementation: return empty list if table not wired yet
        from sqlalchemy import text
        from app import db
        try:
            rows = db.session.execute(text("""
                SELECT 
                    pt.id, pt.subscription_id, pt.user_id, pt.plan_id,
                    pt.payment_reference, pt.payment_method, pt.amount,
                    pt.proof_of_payment, pt.remarks,
                    COALESCE(pt.payment_status, 'Pending') AS payment_status,
                    pt.uploaded_at, pt.verified_by, pt.verified_at,
                    u.email as user_email,
                    u.first_name, u.last_name,
                    sp.name as plan_name
                FROM payment_transactions pt
                LEFT JOIN users u ON pt.user_id = u.id
                LEFT JOIN subscription_plans sp ON pt.plan_id = sp.id
                ORDER BY pt.uploaded_at DESC
            """)).mappings().all()
            data = []
            for r in rows:
                customer_name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip() or r.get('user_email', '') or f"User #{r.get('user_id', 'N/A')}"
                data.append({
                    'id': r.get('id'),
                    'subscription_id': r.get('subscription_id'),
                    'user_id': r.get('user_id'),
                    'plan_id': r.get('plan_id'),
                    'plan_name': r.get('plan_name'),
                    'payment_reference': r.get('payment_reference'),
                    'payment_method': r.get('payment_method'),
                    'amount': float(r.get('amount') or 0),
                    'proof_of_payment': r.get('proof_of_payment'),
                    'remarks': r.get('remarks'),
                    'payment_status': r.get('payment_status'),
                    'status': r.get('payment_status'),  # Alias for frontend compatibility
                    'uploaded_at': r.get('uploaded_at').isoformat() if r.get('uploaded_at') else None,
                    'verified_by': r.get('verified_by'),
                    'verified_at': r.get('verified_at').isoformat() if r.get('verified_at') else None,
                    'user_email': r.get('user_email'),
                    'customer_name': customer_name,
                    'email': r.get('user_email')
                })
        except Exception:
            data = []
        return jsonify({'data': data}), 200
    except Exception as e:
        current_app.logger.error(f'List payment transactions error: {e}')
        return jsonify({'data': []}), 200


@admin_bp.route('/payment-transactions', methods=['POST','OPTIONS'])
def create_payment_transaction(current_user=None):
    try:
        if request.method == 'OPTIONS':
            return jsonify({'ok': True}), 200
        payload = request.get_json() or {}
        from sqlalchemy import text
        from app import db
        ins = text("""
            INSERT INTO payment_transactions
            (subscription_id, user_id, plan_id, payment_reference, payment_method,
             amount, proof_of_payment, remarks, payment_status, uploaded_at)
            VALUES (:sid, :uid, :pid, :ref, :method, :amt, :proof, :remarks, 'Pending', NOW())
        """)
        db.session.execute(ins, {
            'sid': payload.get('subscription_id'),
            'uid': payload.get('user_id'),
            'pid': payload.get('plan_id'),
            'ref': payload.get('payment_reference'),
            'method': payload.get('payment_method', 'GCash'),
            'amt': payload.get('amount', 0),
            'proof': payload.get('proof_of_payment'),
            'remarks': payload.get('remarks', '')
        })
        db.session.commit()
        return jsonify({'message': 'Created', 'status': 'Pending'}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Create payment transaction error: {e}', exc_info=True)
        return jsonify({'error': 'Failed to create'}), 500


@admin_bp.route('/payment-transactions/<int:pt_id>/verify', methods=['POST','OPTIONS'])
@admin_required
def verify_payment_transaction(current_user, pt_id):
    try:
        if request.method == 'OPTIONS':
            return jsonify({'ok': True}), 200
        status = (request.get_json() or {}).get('status', 'Verified')
        from sqlalchemy import text
        from app import db
        if status not in ['Verified', 'Rejected', 'Pending']:
            status = 'Verified'
        
        # Get user_id and amount before updating
        transaction_info = db.session.execute(
            text("SELECT user_id, amount FROM payment_transactions WHERE id=:pid"),
            {'pid': pt_id}
        ).fetchone()
        user_id = transaction_info[0] if transaction_info else None
        amount = float(transaction_info[1]) if transaction_info and transaction_info[1] else None
        
        # 1) Update payment transaction status
        db.session.execute(
            text("""
                UPDATE payment_transactions
                SET payment_status = :st, verified_by = :vb, verified_at = NOW()
                WHERE id = :pid
            """), {'st': status, 'vb': (getattr(current_user, 'id', None) or 0), 'pid': pt_id}
        )
        
        # 2) If verified, also mark latest pending bill paid and activate subscription
        if status == 'Verified':
            # Get payment transaction details including payment_method
            row = db.session.execute(text("""
                SELECT user_id, plan_id, subscription_id, payment_method 
                FROM payment_transactions 
                WHERE id=:pid
            """), {'pid': pt_id}).fetchone()
            
            if row:
                user_id = row[0]
                plan_id = row[1]
                subscription_id = row[2]
                payment_method = row[3] or 'GCash'
                
                # Try to find billing entry by subscription_id first (more accurate), then by user_id/plan_id
                latest_bill = None
                if subscription_id:
                    latest_bill = db.session.execute(text("""
                        SELECT id FROM subscription_bills
                        WHERE subscription_id=:sid AND status='pending'
                        ORDER BY id DESC LIMIT 1
                    """), {'sid': subscription_id}).fetchone()
                
                # Fallback to user_id and plan_id if subscription_id match didn't work
                if not latest_bill:
                    latest_bill = db.session.execute(text("""
                        SELECT id FROM subscription_bills
                        WHERE user_id=:uid AND plan_id=:plid AND status='pending'
                        ORDER BY id DESC LIMIT 1
                    """), {'uid': user_id, 'plid': plan_id}).fetchone()
                
                bill_id = None
                if latest_bill:
                    bill_id = latest_bill[0]
                    # Mark latest pending bill as paid and update payment method
                    db.session.execute(text("""
                        UPDATE subscription_bills
                        SET status='paid', payment_date=NOW(), payment_method=:pmethod
                        WHERE id=:bid
                    """), {'bid': bill_id, 'pmethod': payment_method})

                # Check if subscription exists
                existing_sub = db.session.execute(text("""
                    SELECT id FROM subscriptions WHERE user_id=:uid
                """), {'uid': user_id}).fetchone()
                
                final_subscription_id = None
                if existing_sub:
                    final_subscription_id = existing_sub[0]
                    # Update existing subscription to target plan and activate
                    sub_update = db.session.execute(text("""
                        UPDATE subscriptions
                        SET plan_id=:plid, status='active', next_billing_date=DATE_ADD(CURDATE(), INTERVAL 30 DAY), updated_at=NOW()
                        WHERE user_id=:uid
                    """), {'uid': user_id, 'plid': plan_id})
                    subscription_activated = sub_update.rowcount > 0
                else:
                    # Create new subscription if it doesn't exist
                    from datetime import datetime, timedelta
                    sub_insert = db.session.execute(text("""
                        INSERT INTO subscriptions 
                        (user_id, plan_id, status, billing_interval, start_date, next_billing_date, created_at, updated_at)
                        VALUES (:uid, :plid, 'active', 'monthly', NOW(), DATE_ADD(CURDATE(), INTERVAL 30 DAY), NOW(), NOW())
                    """), {'uid': user_id, 'plid': plan_id})
                    final_subscription_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                    subscription_activated = True
                
                # Update billing entry's subscription_id if it was set incorrectly or is NULL
                if latest_bill and final_subscription_id:
                    db.session.execute(text("""
                        UPDATE subscription_bills
                        SET subscription_id=:sid
                        WHERE id=:bid AND (subscription_id IS NULL OR subscription_id != :sid)
                    """), {'bid': bill_id, 'sid': final_subscription_id})
                
                # Return info about what was updated
                result_info = {
                    'payment_transaction_id': pt_id,
                    'status': status,
                    'billing_updated': latest_bill is not None,
                    'subscription_activated': subscription_activated,
                    'subscription_created': not existing_sub if 'existing_sub' in locals() else False,
                    'user_id': user_id,
                    'plan_id': plan_id
                }
            else:
                result_info = {'payment_transaction_id': pt_id, 'status': status, 'error': 'No user/plan found in payment transaction'}
        else:
            result_info = {'payment_transaction_id': pt_id, 'status': status}

        db.session.commit()
        
        # Notify property manager about payment verification
        try:
            from app.services.notification_service import NotificationService
            if status == 'Verified' and 'user_id' in locals() and user_id:
                # Get plan name for notification
                plan_name = None
                plan_row = db.session.execute(
                    text("SELECT name FROM subscription_plans WHERE id = (SELECT plan_id FROM payment_transactions WHERE id = :pt_id)"),
                    {'pt_id': pt_id}
                ).fetchone()
                plan_name = plan_row[0] if plan_row else None
                
                NotificationService.notify_payment_verified(
                    manager_id=user_id,
                    transaction_id=pt_id,
                    status=status,
                    amount=amount,
                    plan_name=plan_name
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send payment verification notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': f'Payment transaction {status}',
            'result': result_info if 'result_info' in locals() else {'payment_transaction_id': pt_id, 'status': status}
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Verify payment transaction error: {e}')
        return jsonify({'error': 'Failed to update'}), 500