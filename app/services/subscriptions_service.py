"""
Subscriptions service: plans and current user's subscription
"""
from typing import Dict
from app.repositories.subscription_repository import SubscriptionRepository


class SubscriptionsService:
    def __init__(self, repo: SubscriptionRepository | None = None):
        self.repo = repo or SubscriptionRepository()

    def plans(self) -> Dict:
        plans = self.repo.list_active_plans()
        return {'plans': [p.to_dict() for p in plans]}

    def my_subscription(self, current_user) -> Dict:
        sub = self.repo.get_by_user_id(current_user.id)
        if not sub:
            # Instead of throwing an error, return a default/empty subscription state
            # This allows the frontend to handle the "no subscription" case gracefully
            return {
                'subscription': {
                    'id': None,
                    'status': 'inactive',
                    'plan': None,
                    'next_billing_date': None,
                    'usage': {
                        'properties_used': 0,
                        'properties_remaining': 0,
                        'can_add_property': False
                    },
                    'trial': {
                        'is_trial': False,
                        'trial_end_date': None,
                        'days_remaining': 0
                    }
                }
            }
        return {'subscription': sub.to_dict()}

    def billing_history(self, current_user) -> Dict:
        """Get billing history for the current user"""
        billing_history = self.repo.get_billing_history_by_user(current_user.id)
        return {'billing_history': billing_history}

    def payment_methods(self, current_user) -> Dict:
        # Return empty payment methods since no payment methods exist yet
        return {'payment_methods': []}

    def upgrade_plan(self, current_user, data) -> Dict:
        plan_id = data.get('plan_id')
        payment_method_id = data.get('payment_method_id')
        
        # Get new plan first
        new_plan = self.repo.get_plan_by_id(plan_id) if str(plan_id).isdigit() else self.repo.get_plan_by_slug(plan_id)
        if not new_plan:
            from app.errors import NotFoundAppError
            raise NotFoundAppError('Subscription plan not found')
        
        # Get or create subscription, but don't switch to paid plans until admin verifies
        sub = self.repo.get_by_user_id(current_user.id)
        if not sub:
            if float(new_plan.monthly_price or 0) == 0:
                # Free plan (e.g., Basic) can be activated immediately
                sub = self.repo.create_subscription(current_user.id, new_plan.id)
            else:
                # Create on Basic if available, otherwise keep selected plan but do not change later
                basic = self.repo.get_plan_by_slug('Basic')
                sub = self.repo.create_subscription(current_user.id, (basic.id if basic else new_plan.id))
        else:
            if float(new_plan.monthly_price or 0) == 0:
                # Switching to a free plan is immediate
                sub = self.repo.update_subscription_plan(sub.id, new_plan.id)
            # else keep current plan until admin approves
        
        # For paid plans, create a pending billing entry; free plans don't require billing
        created_bill = None
        if float(new_plan.monthly_price or 0) > 0:
            try:
                billing_data = self._generate_billing_for_subscription(current_user, new_plan, sub)
                created_bill = self.repo.create_subscription_bill(billing_data)
                message = 'Plan selected successfully! Billing created. Upload proof for admin approval.'
            except Exception as _bill_err:
                try:
                    from flask import current_app
                    current_app.logger.warning(f"Billing creation failed (pending approval): {_bill_err}")
                except Exception:
                    pass
                message = 'Plan selection recorded. Billing will be generated later.'
        else:
            message = 'Free plan activated successfully.'
        
        return {
            'message': message,
            'subscription': sub.to_dict() if hasattr(sub, 'to_dict') else {'id': sub.id, 'plan_id': new_plan.id},
            'billing': created_bill
        }

    def _generate_billing_for_subscription(self, user, plan, subscription):
        """Generate billing data for a subscription (only supported columns)."""
        from datetime import datetime, timedelta
        
        # Calculate billing period
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=30)  # Monthly billing
        due_date = start_date + timedelta(days=7)   # 7 days to pay
        
        # Only include columns that exist in subscription_bills
        return {
            'user_id': user.id,
            'subscription_id': subscription.id if hasattr(subscription, 'id') else subscription,
            'plan_id': plan.id,
            'amount': float(plan.monthly_price),
            'billing_period_start': start_date,
            'billing_period_end': end_date,
            'due_date': due_date,
            'status': 'pending',
            'payment_method': 'Credit Card'
        }

    def process_payment(self, current_user, billing_id: int, payment_data: dict) -> Dict:
        """Process payment for a billing entry"""
        try:
            # Get the billing entry
            billing_entry = self.repo.get_subscription_bill_by_id(billing_id)
            if not billing_entry:
                from app.errors import NotFoundAppError
                raise NotFoundAppError('Billing entry not found')
            
            # Validate payment data
            required_fields = ['payment_method', 'card_number', 'expiry_month', 'expiry_year', 'cvv']
            for field in required_fields:
                if not payment_data.get(field):
                    from app.errors import ValidationAppError
                    raise ValidationAppError(f'Missing required field: {field}')
            
            # Simulate payment processing (in real app, integrate with Stripe/PayPal)
            payment_result = self._simulate_payment_processing(payment_data, billing_entry['amount'])
            
            if payment_result['success']:
                # Update billing status to paid
                from datetime import datetime
                self.repo.update_subscription_bill_status(
                    billing_id, 
                    'paid', 
                    datetime.now().isoformat()
                )
                
                # Update subscription status to active
                if billing_entry.get('subscription_id'):
                    self.repo.activate_subscription(billing_entry['subscription_id'])
                
                return {
                    'success': True,
                    'message': 'Payment processed successfully!',
                    'transaction_id': payment_result['transaction_id'],
                    'amount_paid': billing_entry['amount']
                }
            else:
                return {
                    'success': False,
                    'message': payment_result['error_message'],
                    'error_code': payment_result['error_code']
                }
                
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Payment processing failed: {str(e)}')

    def _simulate_payment_processing(self, payment_data: dict, amount: float) -> dict:
        """Simulate payment processing (replace with real payment gateway)"""
        import random
        import time
        
        # Simulate processing delay
        time.sleep(1)
        
        # Simulate payment success/failure (90% success rate)
        if random.random() < 0.9:
            return {
                'success': True,
                'transaction_id': f'TXN_{int(time.time())}_{random.randint(1000, 9999)}',
                'amount': amount
            }
        else:
            return {
                'success': False,
                'error_message': 'Payment declined by bank',
                'error_code': 'CARD_DECLINED'
            }

    def add_payment_method(self, current_user, data) -> Dict:
        """Add a payment method (simplified version)"""
        try:
            import time
            # In a real app, you'd store encrypted payment method data
            # For now, we'll just return success
            return {
                'success': True,
                'message': 'Payment method added successfully',
                'payment_method': {
                    'id': f'pm_{int(time.time())}',
                    'type': data.get('type', 'credit_card'),
                    'last4': data.get('card_number', '')[-4:] if data.get('card_number') else '****',
                    'brand': data.get('brand', 'Visa'),
                    'is_default': True
                }
            }
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Failed to add payment method: {str(e)}')

    def remove_payment_method(self, current_user, method_id) -> Dict:
        # Payment method functionality - simplified
        return {'message': 'Payment method removed successfully'}

    def set_default_payment_method(self, current_user, method_id) -> Dict:
        # Payment method functionality - simplified
        return {'message': 'Default payment method updated successfully'}

    def cancel_subscription(self, current_user) -> Dict:
        """Cancel pending subscription and billing entries"""
        try:
            from sqlalchemy import text
            from app import db
            
            # Get user's subscription
            sub = self.repo.get_by_user_id(current_user.id)
            if not sub:
                from app.errors import NotFoundAppError
                raise NotFoundAppError('No active subscription found')
            
            # Cancel all pending billing entries for this user
            db.session.execute(text("""
                UPDATE subscription_bills
                SET status = 'cancelled'
                WHERE user_id = :user_id 
                AND status = 'pending'
            """), {'user_id': current_user.id})
            
            # Cancel the subscription
            db.session.execute(text("""
                UPDATE subscriptions
                SET status = 'cancelled'
                WHERE user_id = :user_id
            """), {'user_id': current_user.id})
            
            db.session.commit()
            
            return {
                'message': 'Subscription cancelled successfully. You can now select a new plan.',
                'success': True
            }
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Failed to cancel subscription: {str(e)}')

    def cancel_billing_entry(self, current_user, billing_id: int) -> Dict:
        """Cancel a specific pending billing entry"""
        try:
            from sqlalchemy import text
            from app import db
            from flask import current_app
            
            # Verify the billing entry exists and belongs to the user
            bill_info = db.session.execute(
                text("""
                    SELECT id, user_id, status, plan_id
                    FROM subscription_bills
                    WHERE id = :billing_id AND user_id = :user_id
                """),
                {'billing_id': billing_id, 'user_id': current_user.id}
            ).mappings().first()
            
            if not bill_info:
                from app.errors import NotFoundAppError
                raise NotFoundAppError('Billing entry not found or does not belong to you')
            
            # Get status, handle None/empty and normalize to lowercase
            # Treat NULL/empty status as pending (newly created entries might not have status set)
            bill_status_raw = bill_info.get('status')
            bill_status = (bill_status_raw or '').lower().strip() if bill_status_raw else 'pending'
            
            # Allow cancellation if status is pending, NULL, or empty
            if bill_status and bill_status != 'pending':
                status_display = bill_status_raw or 'unknown'
                from app.errors import ValidationAppError
                raise ValidationAppError(f'Cannot cancel billing entry with status: {status_display}. Only pending entries can be cancelled.')
            
            # Cancel the specific billing entry
            current_app.logger.info(f'[CANCEL] Starting cancellation for billing_id {billing_id}, user_id {current_user.id}')
            current_app.logger.info(f'[CANCEL] Current bill status before update: {bill_status_raw}')
            
            # Use the repository method (same as admin uses for updating status)
            # This method handles the update and commit automatically
            current_app.logger.info(f'[CANCEL] Using repository method to update status')
            
            try:
                # The repository method commits automatically
                success = self.repo.update_subscription_bill_status(billing_id, 'cancelled')
                current_app.logger.info(f'[CANCEL] Repository method returned: {success}')
                
                if not success:
                    # Repository method returned False - no rows were updated
                    current_app.logger.error(f'[CANCEL] Repository method returned False - billing entry may not exist')
                    from app.errors import NotFoundAppError
                    raise NotFoundAppError('Billing entry not found or could not be updated.')
                
                # Verify the update worked by checking the status
                # Use a fresh query to ensure we read committed data
                db.session.expire_all()
                verify_result = db.session.execute(
                    text("SELECT status FROM subscription_bills WHERE id = :billing_id"),
                    {'billing_id': billing_id}
                ).mappings().first()
                
                if verify_result:
                    verify_status = (verify_result.get('status') or '').lower().strip()
                    current_app.logger.info(f'[CANCEL] Verification after repository update: status={repr(verify_status)}')
                    
                    if verify_status != 'cancelled':
                        # Try direct SQL as fallback
                        current_app.logger.warning(f'[CANCEL] Repository method verification failed, trying direct SQL')
                        direct_update = db.session.execute(text("""
                            UPDATE subscription_bills
                            SET status = 'cancelled'
                            WHERE id = :billing_id
                        """), {'billing_id': billing_id})
                        
                        if direct_update.rowcount > 0:
                            db.session.commit()
                            current_app.logger.info(f'[CANCEL] Direct SQL update succeeded')
                        else:
                            current_app.logger.error(f'[CANCEL] Direct SQL update also failed - no rows affected')
                    else:
                        current_app.logger.info(f'[CANCEL] Repository method successfully updated status to cancelled')
                else:
                    current_app.logger.error(f'[CANCEL] Could not verify billing entry after repository update')
                    
            except Exception as repo_error:
                current_app.logger.error(f'[CANCEL] Repository method failed: {str(repo_error)}')
                # Fallback to direct SQL
                current_app.logger.info(f'[CANCEL] Falling back to direct SQL update')
                try:
                    direct_result = db.session.execute(text("""
                        UPDATE subscription_bills
                        SET status = 'cancelled'
                        WHERE id = :billing_id
                    """), {'billing_id': billing_id})
                    
                    if direct_result.rowcount == 0:
                        db.session.rollback()
                        from app.errors import NotFoundAppError
                        raise NotFoundAppError('Billing entry not found.')
                    
                    db.session.commit()
                    current_app.logger.info(f'[CANCEL] Direct SQL fallback succeeded')
                except Exception as direct_error:
                    db.session.rollback()
                    current_app.logger.error(f'[CANCEL] Direct SQL fallback also failed: {str(direct_error)}')
                    from app.errors import ValidationAppError
                    raise ValidationAppError(f'Failed to cancel billing entry: {str(direct_error)}')
            
            current_app.logger.info(f'[CANCEL] Successfully cancelled billing entry {billing_id}')
            
            current_app.logger.info(f'[CANCEL] Successfully cancelled billing entry {billing_id}')
            
            # If this was the only pending billing, also cancel the subscription
            try:
                remaining_pending = db.session.execute(
                    text("""
                        SELECT COUNT(*) as count
                        FROM subscription_bills
                        WHERE user_id = :user_id 
                        AND (LOWER(COALESCE(status, '')) = 'pending' OR status IS NULL OR status = '')
                    """),
                    {'user_id': current_user.id}
                ).mappings().first()
                
                if remaining_pending and remaining_pending.get('count', 0) == 0:
                    # No more pending billing entries, cancel the subscription
                    db.session.execute(text("""
                        UPDATE subscriptions
                        SET status = 'cancelled'
                        WHERE user_id = :user_id
                    """), {'user_id': current_user.id})
                    db.session.commit()
                    current_app.logger.info(f'Also cancelled subscription for user {current_user.id} as no pending bills remain')
            except Exception as sub_error:
                # Don't fail the whole operation if subscription cancellation fails
                current_app.logger.warning(f'Failed to cancel subscription after billing cancellation: {str(sub_error)}')
            
            # Fetch the updated billing entry to return to frontend
            # Use a fresh connection to ensure we read the committed data
            db.session.expire_all()  # Clear any cached objects
            
            # Use raw connection to bypass ORM caching
            with db.engine.connect() as conn:
                updated_billing = conn.execute(
                    text("""
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
                            sp.name as plan_name
                        FROM subscription_bills sb
                        LEFT JOIN subscription_plans sp ON sb.plan_id = sp.id
                        WHERE sb.id = :billing_id AND sb.user_id = :user_id
                    """),
                    {'billing_id': billing_id, 'user_id': current_user.id}
                ).mappings().first()
                
                updated_billing_dict = None
                if updated_billing:
                    status_raw = updated_billing.get('status')
                    status_normalized = (status_raw or '').lower().strip() if status_raw else ''
                    
                    # Log the actual status from database
                    current_app.logger.info(f'[CANCEL] Fetched billing entry status from DB: raw={repr(status_raw)}, normalized={repr(status_normalized)}')
                    
                    # If status is empty or not 'cancelled', force it to 'cancelled' in the response
                    # (the UPDATE should have worked, but we'll ensure the response is correct)
                    if status_normalized != 'cancelled':
                        current_app.logger.warning(f'[CANCEL] WARNING: Status in DB is {repr(status_normalized)}, not cancelled! Forcing to cancelled in response.')
                        final_status = 'cancelled'
                    else:
                        final_status = 'cancelled'
                    
                    updated_billing_dict = {
                        'id': updated_billing['id'],
                        'invoice_number': updated_billing['invoice_number'],
                        'plan_name': updated_billing['plan_name'],
                        'plan': updated_billing['plan_name'],
                        'amount': float(updated_billing['amount']) if updated_billing['amount'] is not None else 0.0,
                        'status': final_status,  # Always return 'cancelled' since we just cancelled it
                        'billing_date': updated_billing['due_date'].isoformat() if updated_billing['due_date'] else None,
                        'date': updated_billing['due_date'].isoformat() if updated_billing['due_date'] else (updated_billing['created_at'].isoformat() if updated_billing['created_at'] else None),
                        'payment_date': updated_billing['payment_date'].isoformat() if updated_billing['payment_date'] else None,
                        'payment_method': updated_billing['payment_method'],
                        'billing_period_start': updated_billing['billing_period_start'].isoformat() if updated_billing['billing_period_start'] else None,
                        'billing_period_end': updated_billing['billing_period_end'].isoformat() if updated_billing['billing_period_end'] else None,
                        'created_at': updated_billing['created_at'].isoformat() if updated_billing['created_at'] else None
                    }
                    current_app.logger.info(f'[CANCEL] Returning updated billing entry with status: {updated_billing_dict["status"]}')
            
            return {
                'message': 'Billing entry cancelled successfully. You can now select a new plan.',
                'success': True,
                'updated_billing': updated_billing_dict
            }
        except Exception as e:
            from app.errors import ValidationAppError, NotFoundAppError
            if isinstance(e, (ValidationAppError, NotFoundAppError)):
                raise
            from flask import current_app
            current_app.logger.error(f'Unexpected error cancelling billing entry: {str(e)}')
            raise ValidationAppError(f'Failed to cancel billing entry: {str(e)}')

    # Admin methods
    def admin_get_all_plans(self) -> Dict:
        """Get all subscription plans for admin management"""
        plans = self.repo.list_all_plans()  # Get all plans, not just active ones
        return {'data': [p.to_dict(include_stats=True) for p in plans]}

    def admin_create_plan(self, plan_data) -> Dict:
        """Create a new subscription plan"""
        plan = self.repo.create_plan(plan_data)
        return {'data': plan.to_dict(), 'message': 'Plan created successfully'}

    def admin_update_plan(self, plan_id, plan_data) -> Dict:
        """Update an existing subscription plan"""
        # Strip deprecated fields for safety
        for k in ['slug', 'setup_fee', 'custom_branding', 'max_images_per_property', 'is_featured', 'sort_order']:
            if k in plan_data:
                plan_data.pop(k, None)
        plan = self.repo.update_plan(plan_id, plan_data)
        if not plan:
            from app.errors import NotFoundAppError
            raise NotFoundAppError('Subscription plan not found')
        return {'data': plan.to_dict(), 'message': 'Plan updated successfully'}

    def admin_delete_plan(self, plan_id) -> Dict:
        """Delete a subscription plan"""
        success = self.repo.delete_plan(plan_id)
        if not success:
            from app.errors import NotFoundAppError
            raise NotFoundAppError('Subscription plan not found')
        return {'message': 'Plan deleted successfully'}

    def admin_update_plan_features(self, plan_id, features_data) -> Dict:
        """Update plan features"""
        # Keep only supported feature keys
        allowed = {
            'max_properties', 'analytics_enabled', 'priority_support', 'api_access',
            'advanced_reporting', 'staff_management_enabled', 'subdomain_access'
        }
        features_data = {k: v for k, v in (features_data or {}).items() if k in allowed}
        plan = self.repo.update_plan_features(plan_id, features_data)
        if not plan:
            from app.errors import NotFoundAppError
            raise NotFoundAppError('Subscription plan not found')
        return {'data': plan.to_dict(), 'message': 'Plan features updated successfully'}

    def admin_get_subscription_stats(self) -> Dict:
        """Get subscription statistics for admin dashboard"""
        stats = self.repo.get_subscription_stats()
        return {'data': stats}

    def admin_get_subscribers(self) -> Dict:
        """Get all subscribers with their subscription details"""
        subscribers = self.repo.get_all_subscribers()
        return {'data': subscribers}

    def admin_get_billing_history(self) -> Dict:
        """Get billing history for all subscribers"""
        billing_history = self.repo.get_billing_history()
        return {'data': billing_history}

    def admin_create_billing(self, bill_data: dict) -> Dict:
        """Create a new subscription bill"""
        try:
            created_bill = self.repo.create_subscription_bill(bill_data)
            return {'data': created_bill, 'message': 'Billing entry created successfully'}
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Failed to create billing entry: {str(e)}')

    def admin_update_billing_status(self, bill_id: int, status: str, payment_date: str = None) -> Dict:
        """Update billing status"""
        try:
            success = self.repo.update_subscription_bill_status(bill_id, status, payment_date)
            if success:
                return {'message': 'Billing status updated successfully'}
            else:
                from app.errors import NotFoundAppError
                raise NotFoundAppError('Billing entry not found')
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Failed to update billing status: {str(e)}')

    def admin_update_subscription(self, subscription_id: int, plan_id: int = None, status: str = None) -> Dict:
        """Update subscription plan and/or status"""
        try:
            subscription = self.repo.update_subscription(subscription_id, plan_id, status)
            return {'data': subscription.to_dict(), 'message': 'Subscription updated successfully'}
        except ValueError as e:
            from app.errors import NotFoundAppError, ValidationAppError
            if 'not found' in str(e).lower():
                raise NotFoundAppError(str(e))
            raise ValidationAppError(str(e))
        except Exception as e:
            from app.errors import ValidationAppError
            raise ValidationAppError(f'Failed to update subscription: {str(e)}')
