"""
Subscription repository: encapsulates plan and subscription queries
"""
from typing import Optional, List
from sqlalchemy.orm import joinedload
from app import db
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus, BillingInterval


class SubscriptionRepository:
    def list_active_plans(self) -> List[SubscriptionPlan]:
        return SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.id).all()

    def get_by_user_id(self, user_id: int) -> Optional[Subscription]:
        return Subscription.query.options(joinedload(Subscription.plan)).filter_by(user_id=user_id).first()

    def get_plan_by_slug(self, slug: str) -> Optional[SubscriptionPlan]:
        """Back-compat: treat slug as plan name after slug removal."""
        return SubscriptionPlan.query.filter_by(name=slug).first()

    # Admin methods
    def list_all_plans(self) -> List[SubscriptionPlan]:
        """Get all subscription plans (including inactive ones)"""
        return SubscriptionPlan.query.order_by(SubscriptionPlan.id).all()

    def get_plan_by_id(self, plan_id: int) -> Optional[SubscriptionPlan]:
        """Get a subscription plan by ID (admin-safe: include inactive)."""
        return SubscriptionPlan.query.get(plan_id)

    def create_plan(self, plan_data: dict) -> SubscriptionPlan:
        """Create a new subscription plan"""
        plan = SubscriptionPlan(**plan_data)
        db.session.add(plan)
        db.session.commit()
        return plan

    def update_plan(self, plan_id: int, plan_data: dict) -> Optional[SubscriptionPlan]:
        """Update an existing subscription plan"""
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None
        
        for key, value in plan_data.items():
            if hasattr(plan, key):
                setattr(plan, key, value)
        
        db.session.commit()
        return plan

    def delete_plan(self, plan_id: int) -> bool:
        """Delete a subscription plan"""
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False
        
        db.session.delete(plan)
        db.session.commit()
        return True

    def update_plan_features(self, plan_id: int, features_data: dict) -> Optional[SubscriptionPlan]:
        """Update plan features"""
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None
        
        # Update only feature-related fields
        feature_fields = [
            'max_properties', 'analytics_enabled',
            'priority_support', 'api_access', 'advanced_reporting',
            'staff_management_enabled', 'subdomain_access'
        ]
        
        for key, value in features_data.items():
            if key in feature_fields and hasattr(plan, key):
                setattr(plan, key, value)
        
        db.session.commit()
        return plan

    def get_subscription_stats(self) -> dict:
        """Get subscription statistics"""
        from sqlalchemy import func
        
        # Count total subscribers
        total_subscribers = db.session.query(func.count(Subscription.id)).scalar() or 0
        
        # Import the enum
        from app.models.subscription import SubscriptionStatus
        
        # Count active subscriptions
        active_subscriptions = db.session.query(func.count(Subscription.id)).filter_by(status=SubscriptionStatus.ACTIVE).scalar() or 0
        
        # Calculate monthly revenue (sum of all active subscription plan prices)
        monthly_revenue = db.session.query(
            func.sum(SubscriptionPlan.monthly_price)
        ).join(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE).scalar() or 0
        
        # Count pending renewals (subscriptions expiring soon)
        from datetime import datetime, timedelta
        next_month = datetime.now() + timedelta(days=30)
        pending_renewals = db.session.query(func.count(Subscription.id)).filter(
            Subscription.next_billing_date <= next_month,
            Subscription.status == SubscriptionStatus.ACTIVE
        ).scalar() or 0
        
        return {
            'total_subscribers': total_subscribers,
            'active_subscriptions': active_subscriptions,
            'monthly_revenue': float(monthly_revenue),
            'pending_renewals': pending_renewals
        }

    def get_all_subscribers(self) -> list:
        """Get all subscribers with their details"""
        from sqlalchemy import text
        
        # Get subscribers with their subscription details and user information
        # First, let's try without the properties join to avoid column issues
        query = text("""
            SELECT 
                u.id as user_id,
                u.email,
                u.first_name,
                u.last_name,
                u.phone_number,
                u.created_at as user_created_at,
                s.id as subscription_id,
                s.status,
                s.created_at as subscription_created_at,
                sp.name as plan_display_name,
                sp.monthly_price as plan_monthly_price,
                sp.max_properties as plan_max_properties,
                COALESCE(pc.properties_count, 0) as properties_count
            FROM users u
            INNER JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN subscription_plans sp ON s.plan_id = sp.id
            LEFT JOIN (
                SELECT owner_id, COUNT(*) AS properties_count
                FROM properties
                GROUP BY owner_id
            ) pc ON pc.owner_id = u.id
            ORDER BY s.created_at DESC
        """)
        
        result = db.session.execute(query)
        subscribers = []
        
        for row in result:
            subscriber = {
                'user_id': row.user_id,
                'email': row.email,
                'first_name': row.first_name or '',
                'last_name': row.last_name or '',
                'phone': row.phone_number or '',
                'full_name': f"{row.first_name or ''} {row.last_name or ''}".strip() or row.email,
                'user_created_at': row.user_created_at.isoformat() if row.user_created_at else None,
                'subscription': {
                    'id': row.subscription_id,
                    'status': row.status or 'inactive',
                    'plan_name': row.plan_display_name or 'No Plan',
                    'monthly_fee': float(row.plan_monthly_price or 0),
                    'max_properties': row.plan_max_properties or 0,
                    'properties_used': row.properties_count or 0,
                    'subscription_created_at': row.subscription_created_at.isoformat() if row.subscription_created_at else None
                }
            }
            subscribers.append(subscriber)
        
        return subscribers

    def get_billing_history(self) -> list:
        """Get billing history from subscription_bills table"""
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                sb.id,
                sb.invoice_number,
                sb.user_id,
                sb.subscription_id,
                sb.plan_id,
                sb.amount,
                sb.status,
                sb.due_date,
                sb.payment_method,
                sb.payment_date,
                sb.billing_period_start,
                sb.billing_period_end,
                sb.created_at,
                u.first_name,
                u.last_name,
                u.email as user_email,
                sp.name as plan_name
            FROM subscription_bills sb
            LEFT JOIN users u ON sb.user_id = u.id
            LEFT JOIN subscription_plans sp ON sb.plan_id = sp.id
            ORDER BY sb.created_at DESC
        """)
        
        result = db.session.execute(query)
        billing_history = []
        
        for row in result:
            billing_entry = {
                'id': row.id,
                'invoice_number': row.invoice_number,
                'user_id': row.user_id,  # Include user_id for filtering
                'subscription_id': row.subscription_id,
                'plan_id': row.plan_id,
                'customer_name': f"{row.first_name or ''} {row.last_name or ''}".strip() or row.user_email,
                'email': row.user_email,
                'plan_name': row.plan_name,
                'amount': float(row.amount) if row.amount is not None else 0.0,
                'status': row.status.lower() if row.status else 'pending',  # Normalize status to lowercase
                'billing_date': row.due_date.isoformat() if row.due_date else None,
                'date': row.due_date.isoformat() if row.due_date else (row.created_at.isoformat() if row.created_at else None),  # Alias for frontend compatibility
                'payment_date': row.payment_date.isoformat() if row.payment_date else None,
                'payment_method': row.payment_method,
                'billing_period_start': row.billing_period_start.isoformat() if row.billing_period_start else None,
                'billing_period_end': row.billing_period_end.isoformat() if row.billing_period_end else None,
                'created_at': row.created_at.isoformat() if row.created_at else None
            }
            billing_history.append(billing_entry)
        
        return billing_history

    def get_billing_history_by_user(self, user_id: int) -> list:
        """Get billing history from subscription_bills table for a specific user"""
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                sb.id,
                sb.invoice_number,
                sb.user_id,
                sb.subscription_id,
                sb.plan_id,
                sb.amount,
                sb.status,
                sb.due_date,
                sb.payment_method,
                sb.payment_date,
                sb.billing_period_start,
                sb.billing_period_end,
                sb.created_at,
                u.first_name,
                u.last_name,
                u.email as user_email,
                sp.name as plan_name
            FROM subscription_bills sb
            LEFT JOIN users u ON sb.user_id = u.id
            LEFT JOIN subscription_plans sp ON sb.plan_id = sp.id
            WHERE sb.user_id = :user_id
            ORDER BY sb.created_at DESC
        """)
        
        result = db.session.execute(query, {'user_id': user_id})
        billing_history = []
        
        for row in result:
            billing_entry = {
                'id': row.id,
                'invoice_number': row.invoice_number,
                'plan_name': row.plan_name,
                'plan': row.plan_name,  # Alias for frontend compatibility
                'amount': float(row.amount) if row.amount is not None else 0.0,  # Ensure amount is always a number
                'status': row.status.lower() if row.status else 'pending',  # Normalize to lowercase
                'billing_date': row.due_date.isoformat() if row.due_date else None,
                'date': row.due_date.isoformat() if row.due_date else (row.created_at.isoformat() if row.created_at else None),  # Alias for frontend compatibility
                'payment_date': row.payment_date.isoformat() if row.payment_date else None,
                'payment_method': row.payment_method,
                'billing_period_start': row.billing_period_start.isoformat() if row.billing_period_start else None,
                'billing_period_end': row.billing_period_end.isoformat() if row.billing_period_end else None,
                'created_at': row.created_at.isoformat() if row.created_at else None
            }
            billing_history.append(billing_entry)
        
        return billing_history

    def create_subscription_bill(self, bill_data: dict) -> dict:
        """Create a new subscription bill"""
        from sqlalchemy import text
        from datetime import datetime
        
        # Generate invoice number if not provided
        if not bill_data.get('invoice_number'):
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            bill_data['invoice_number'] = f"INV-{timestamp}-{bill_data.get('user_id', 'USER')}"
        
        # Resolve dependent IDs if provided only as names/emails
        if not bill_data.get('user_id') and bill_data.get('customer_email'):
            from sqlalchemy import text as _t
            u = db.session.execute(_t("SELECT id FROM users WHERE email = :e"), {'e': bill_data['customer_email']}).fetchone()
            if u:
                bill_data['user_id'] = u.id
        if not bill_data.get('plan_id') and bill_data.get('plan_name'):
            from sqlalchemy import text as _t
            p = db.session.execute(_t("SELECT id FROM subscription_plans WHERE name = :n"), {'n': bill_data['plan_name']}).fetchone()
            if p:
                bill_data['plan_id'] = p.id
        if not bill_data.get('subscription_id') and bill_data.get('user_id'):
            from sqlalchemy import text as _t
            s = db.session.execute(_t("SELECT id FROM subscriptions WHERE user_id = :u"), {'u': bill_data['user_id']}).fetchone()
            if s:
                bill_data['subscription_id'] = s.id

        # Provide default billing period if not supplied
        if not bill_data.get('billing_period_start') or not bill_data.get('billing_period_end'):
            from datetime import datetime, timedelta
            start = datetime.now().date()
            end = start + timedelta(days=30)
            bill_data.setdefault('billing_period_start', start)
            bill_data.setdefault('billing_period_end', end)

        # Insert into subscription_bills table (reduced schema)
        query = text("""
            INSERT INTO subscription_bills (
                user_id, subscription_id, plan_id, invoice_number, amount, billing_period_start,
                billing_period_end, due_date, status, payment_method
            ) VALUES (
                :user_id, :subscription_id, :plan_id, :invoice_number, :amount, :billing_period_start,
                :billing_period_end, :due_date, :status, :payment_method
            )
        """)

        result = db.session.execute(query, bill_data)
        db.session.commit()

        # Return the created bill (table now has reduced columns)
        bill_id = None
        try:
            bill_id = getattr(result, 'lastrowid', None) or (result.inserted_primary_key[0] if getattr(result, 'inserted_primary_key', None) else None)
        except Exception:
            bill_id = None
        if bill_id is None:
            # Fallback: fetch most recent row for this user/plan by invoice number
            created_row = db.session.execute(
                text("SELECT id FROM subscription_bills WHERE invoice_number = :inv ORDER BY id DESC LIMIT 1"),
                {'inv': bill_data['invoice_number']}
            ).fetchone()
            bill_id = created_row.id if created_row else None

        created_bill = None
        if bill_id is not None:
            created_bill = db.session.execute(
                text("SELECT id, user_id, subscription_id, plan_id, invoice_number, amount, status, due_date, payment_method FROM subscription_bills WHERE id = :id"),
                {'id': bill_id}
            ).fetchone()

        # Derive human display fields from related tables when needed
        plan_name = None
        try:
            plan_row = db.session.execute(text("SELECT name FROM subscription_plans WHERE id = :pid"), { 'pid': created_bill.plan_id }).fetchone()
            if plan_row:
                plan_name = plan_row.name
        except Exception:
            plan_name = None

        return {
            'id': created_bill.id if created_bill else None,
            'invoice_number': created_bill.invoice_number if created_bill else bill_data['invoice_number'],
            'plan_id': created_bill.plan_id if created_bill else bill_data.get('plan_id'),
            'plan_name': plan_name,
            'subscription_id': created_bill.subscription_id if created_bill else bill_data.get('subscription_id'),
            'user_id': created_bill.user_id if created_bill else bill_data.get('user_id'),
            'amount': float(created_bill.amount) if created_bill else float(bill_data.get('amount', 0)),
            'status': created_bill.status if created_bill else bill_data.get('status', 'pending'),
            'billing_date': (created_bill.due_date.isoformat() if (created_bill and created_bill.due_date) else (
                bill_data.get('due_date').isoformat() if bill_data.get('due_date') else None
            )),
            'payment_method': created_bill.payment_method if created_bill else bill_data.get('payment_method')
        }

    def update_subscription_bill_status(self, bill_id: int, status: str, payment_date: str = None) -> bool:
        """Update subscription bill status"""
        from sqlalchemy import text
        from datetime import datetime
        
        result = None
        rows_updated = 0
        
        # Try with updated_at first, fallback to without if column doesn't exist
        try:
            if payment_date:
                query = text("""
                    UPDATE subscription_bills 
                    SET status = :status, payment_date = :payment_date, updated_at = :updated_at
                    WHERE id = :bill_id
                """)
                result = db.session.execute(query, {
                    'status': status,
                    'payment_date': payment_date,
                    'updated_at': datetime.now(),
                    'bill_id': bill_id
                })
                rows_updated = result.rowcount
            else:
                query = text("""
                    UPDATE subscription_bills 
                    SET status = :status, updated_at = :updated_at
                    WHERE id = :bill_id
                """)
                result = db.session.execute(query, {
                    'status': status,
                    'updated_at': datetime.now(),
                    'bill_id': bill_id
                })
                rows_updated = result.rowcount
        except Exception:
            # Fallback: update without updated_at if column doesn't exist
            if payment_date:
                query = text("""
                    UPDATE subscription_bills 
                    SET status = :status, payment_date = :payment_date
                    WHERE id = :bill_id
                """)
                result = db.session.execute(query, {
                    'status': status,
                    'payment_date': payment_date,
                    'bill_id': bill_id
                })
                rows_updated = result.rowcount
            else:
                query = text("""
                    UPDATE subscription_bills 
                    SET status = :status
                    WHERE id = :bill_id
                """)
                result = db.session.execute(query, {
                    'status': status,
                    'bill_id': bill_id
                })
                rows_updated = result.rowcount
        
        db.session.commit()
        
        # Return True only if rows were actually updated
        return rows_updated > 0

    def get_plan_by_id(self, plan_id: int):
        """Get subscription plan by ID (do not restrict by is_active).

        Admin edit flows need to access inactive plans too, so we should not
        filter by is_active here. Callers that need only active plans should
        use list_active_plans().
        """
        return SubscriptionPlan.query.get(plan_id)

    def get_plan_by_slug(self, slug: str):
        """Back-compat: resolve plans by name when slug is not present."""
        # Some older callers may pass a slug; our model no longer has slug.
        # Try matching by name instead.
        from sqlalchemy import or_
        return SubscriptionPlan.query.filter(or_(SubscriptionPlan.name == slug)).first()

    def create_subscription(self, user_id: int, plan_id: int):
        """Create a new subscription"""
        from datetime import datetime, timedelta
        
        # Get the plan
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError('Plan not found')
        
        # Create subscription
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            # status is set after construction because __init__ doesn't accept it
            billing_interval=BillingInterval.MONTHLY
        )
        # Ensure required datetime fields are set
        subscription.start_date = datetime.now()
        subscription.next_billing_date = datetime.now() + timedelta(days=30)
        subscription.status = SubscriptionStatus.ACTIVE
        
        db.session.add(subscription)
        db.session.commit()
        return subscription

    def update_subscription_plan(self, subscription_id: int, plan_id: int):
        """Update subscription plan"""
        from datetime import datetime, timedelta
        
        subscription = Subscription.query.get(subscription_id)
        if not subscription:
            raise ValueError('Subscription not found')
        
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError('Plan not found')
        
        # Update subscription
        subscription.plan_id = plan_id
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.next_billing_date = datetime.now() + timedelta(days=30)
        
        db.session.commit()
        return subscription

    def get_by_user_id(self, user_id: int):
        """Get subscription by user ID"""
        return Subscription.query.filter_by(user_id=user_id).first()

    def update_subscription(self, subscription_id: int, plan_id: int = None, status: str = None):
        """Update subscription plan and/or status"""
        from datetime import datetime, timedelta
        from app.models.subscription import SubscriptionStatus
        
        subscription = Subscription.query.get(subscription_id)
        if not subscription:
            raise ValueError('Subscription not found')
        
        if plan_id is not None:
            plan = self.get_plan_by_id(plan_id)
            if not plan:
                raise ValueError('Plan not found')
            subscription.plan_id = plan_id
        
        if status is not None:
            # Convert string status to enum
            try:
                status_enum = SubscriptionStatus(status.lower())
                subscription.status = status_enum
                
                # If activating, set next billing date if not set
                if status_enum == SubscriptionStatus.ACTIVE and not subscription.next_billing_date:
                    subscription.next_billing_date = datetime.now() + timedelta(days=30)
            except ValueError:
                raise ValueError(f'Invalid status: {status}')
        
        subscription.updated_at = datetime.now()
        db.session.commit()
        return subscription

    def get_subscription_bill_by_id(self, bill_id: int) -> dict:
        """Get subscription bill by ID"""
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                id, user_id, subscription_id, plan_id, invoice_number,
                amount, status, due_date, payment_method
            FROM subscription_bills 
            WHERE id = :bill_id
        """)
        
        result = db.session.execute(query, {'bill_id': bill_id}).fetchone()
        
        if result:
            return {
                'id': result.id,
                'user_id': result.user_id,
                'subscription_id': result.subscription_id,
                'plan_id': result.plan_id,
                'invoice_number': result.invoice_number,
                'amount': float(result.amount),
                'status': result.status,
                'due_date': result.due_date,
                'payment_method': result.payment_method
            }
        return None

    def activate_subscription(self, subscription_id: int) -> bool:
        """Activate a subscription"""
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            subscription.status = SubscriptionStatus.ACTIVE
            db.session.commit()
            return True
        return False
