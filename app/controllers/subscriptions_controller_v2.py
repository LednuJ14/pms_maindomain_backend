"""
Subscriptions controller (v2): delegates to SubscriptionsService
"""
from flask import Blueprint, jsonify, current_app
from app.utils.decorators import manager_required
from app.services.subscriptions_service import SubscriptionsService

subscriptions_bp = Blueprint('subscriptions', __name__)


@subscriptions_bp.route('/plans', methods=['GET'])
def get_subscription_plans():
    """
    Get subscription plans
    ---
    tags:
      - Subscriptions
    summary: List all available subscription plans
    description: Retrieve a list of all available subscription plans with pricing and features
    responses:
      200:
        description: Subscription plans retrieved successfully
        schema:
          type: object
          properties:
            plans:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  price:
                    type: number
                  features:
                    type: array
      500:
        description: Server error
    """
    try:
        data = SubscriptionsService().plans()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get subscription plans error: {e}')
        return jsonify({'error': 'Failed to retrieve subscription plans', 'message': 'An error occurred while fetching subscription plans'}), 500


@subscriptions_bp.route('/my-subscription', methods=['GET'])
@manager_required
def get_my_subscription(current_user):
    """
    Get current user's subscription
    ---
    tags:
      - Subscriptions
    summary: Get the authenticated manager's subscription
    description: Retrieve the current subscription details for the authenticated property manager
    security:
      - Bearer: []
    responses:
      200:
        description: Subscription retrieved successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            plan:
              type: object
            status:
              type: string
            expires_at:
              type: string
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        data = SubscriptionsService().my_subscription(current_user)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get my subscription error: {e}')
        return jsonify({'error': 'Failed to retrieve subscription', 'message': 'An error occurred while fetching your subscription'}), 500


@subscriptions_bp.route('/billing-history', methods=['GET'])
@manager_required
def get_billing_history(current_user):
    """
    Get billing history
    ---
    tags:
      - Subscriptions
    summary: Get billing history for authenticated manager
    description: Retrieve billing history for the authenticated property manager
    security:
      - Bearer: []
    parameters:
      - in: query
        name: page
        type: integer
        description: Page number for pagination
    responses:
      200:
        description: Billing history retrieved successfully
        schema:
          type: object
          properties:
            bills:
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
        data = SubscriptionsService().billing_history(current_user)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get billing history error: {e}')
        return jsonify({'error': 'Failed to retrieve billing history', 'message': 'An error occurred while fetching billing history'}), 500


@subscriptions_bp.route('/payment-methods', methods=['GET'])
@manager_required
def get_payment_methods(current_user):
    """
    Get payment methods
    ---
    tags:
      - Subscriptions
    summary: Get saved payment methods
    description: Retrieve all saved payment methods for the authenticated manager
    security:
      - Bearer: []
    responses:
      200:
        description: Payment methods retrieved successfully
        schema:
          type: object
          properties:
            payment_methods:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  type:
                    type: string
                  last4:
                    type: string
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        data = SubscriptionsService().payment_methods(current_user)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get payment methods error: {e}')
        return jsonify({'error': 'Failed to retrieve payment methods', 'message': 'An error occurred while fetching payment methods'}), 500


@subscriptions_bp.route('/upgrade', methods=['POST'])
@manager_required
def upgrade_plan(current_user):
    """
    Upgrade subscription plan
    ---
    tags:
      - Subscriptions
    summary: Upgrade to a different subscription plan
    description: Upgrade the current subscription to a different plan
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - plan_id
          properties:
            plan_id:
              type: integer
              description: ID of the plan to upgrade to
    responses:
      200:
        description: Plan upgraded successfully
        schema:
          type: object
          properties:
            message:
              type: string
            subscription:
              type: object
      400:
        description: Validation error or upgrade not allowed
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        from flask import request
        data = request.get_json()
        result = SubscriptionsService().upgrade_plan(current_user, data)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Upgrade plan error: {e}')
        return jsonify({'error': 'Failed to upgrade plan', 'message': str(e)}), 500


@subscriptions_bp.route('/payment-methods/add', methods=['POST'])
@manager_required
def add_payment_method(current_user):
    try:
        from flask import request
        data = request.get_json()
        result = SubscriptionsService().add_payment_method(current_user, data)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Add payment method error: {e}')
        return jsonify({'error': 'Failed to add payment method', 'message': 'An error occurred while adding payment method'}), 500


@subscriptions_bp.route('/payment-methods/<int:method_id>', methods=['DELETE'])
@manager_required
def remove_payment_method(current_user, method_id):
    try:
        result = SubscriptionsService().remove_payment_method(current_user, method_id)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Remove payment method error: {e}')
        return jsonify({'error': 'Failed to remove payment method', 'message': 'An error occurred while removing payment method'}), 500


@subscriptions_bp.route('/payment-methods/<int:method_id>/set-default', methods=['POST'])
@manager_required
def set_default_payment_method(current_user, method_id):
    try:
        result = SubscriptionsService().set_default_payment_method(current_user, method_id)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Set default payment method error: {e}')
        return jsonify({'error': 'Failed to set default payment method', 'message': 'An error occurred while setting default payment method'}), 500


@subscriptions_bp.route('/billing/<int:billing_id>/pay', methods=['POST'])
@manager_required
def process_payment(current_user, billing_id):
    try:
        from flask import request
        payment_data = request.get_json()
        
        # Validate required payment fields
        required_fields = ['payment_method', 'card_number', 'expiry_month', 'expiry_year', 'cvv']
        for field in required_fields:
            if not payment_data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        result = SubscriptionsService().process_payment(current_user, billing_id, payment_data)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.error(f'Process payment error: {e}')
        return jsonify({'error': 'Payment processing failed', 'message': str(e)}), 500


@subscriptions_bp.route('/cancel', methods=['POST'])
@manager_required
def cancel_subscription(current_user):
    """
    Cancel subscription
    ---
    tags:
      - Subscriptions
    summary: Cancel the current subscription
    description: Cancel the active subscription. Access will continue until the end of the billing period.
    security:
      - Bearer: []
    responses:
      200:
        description: Subscription cancelled successfully
        schema:
          type: object
          properties:
            message:
              type: string
            subscription:
              type: object
      400:
        description: No active subscription to cancel
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        result = SubscriptionsService().cancel_subscription(current_user)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Cancel subscription error: {e}')
        if hasattr(e, 'status_code'):
            return jsonify({'error': str(e)}), e.status_code
        return jsonify({'error': 'Failed to cancel subscription', 'message': str(e)}), 500


@subscriptions_bp.route('/billing/<int:billing_id>/cancel', methods=['POST'])
@manager_required
def cancel_billing_entry(current_user, billing_id):
    try:
        result = SubscriptionsService().cancel_billing_entry(current_user, billing_id)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.error(f'Cancel billing entry error: {e}')
        if hasattr(e, 'status_code'):
            return jsonify({'error': str(e)}), e.status_code
        return jsonify({'error': 'Failed to cancel billing entry', 'message': str(e)}), 500