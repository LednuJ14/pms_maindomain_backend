"""
Users controller (v2): delegates to UsersService
"""
from flask import Blueprint, request, jsonify, current_app
from app.utils.decorators import admin_required, owner_or_admin_required, validate_json_content_type
from app.services.users_service import UsersService, UsersValidationError

users_bp = Blueprint('users', __name__)


@users_bp.route('', methods=['GET'])
@admin_required
def get_users(current_user):
    """
    Get all users
    ---
    tags:
      - Users
    summary: List all users (Admin only)
    description: Retrieve a list of all users in the system. Admin access required.
    security:
      - Bearer: []
    parameters:
      - in: query
        name: page
        type: integer
        description: Page number for pagination
      - in: query
        name: per_page
        type: integer
        description: Number of items per page
      - in: query
        name: role
        type: string
        description: Filter by user role
      - in: query
        name: search
        type: string
        description: Search term for user name or email
    responses:
      200:
        description: Users retrieved successfully
        schema:
          type: object
          properties:
            users:
              type: array
              items:
                type: object
            total:
              type: integer
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        data = UsersService().list_users(request.args)
        return jsonify(data), 200
    except UsersValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Get users error: {e}')
        return jsonify({'error': 'Failed to retrieve users', 'message': 'An error occurred while fetching users'}), 500


@users_bp.route('/<int:user_id>', methods=['GET'])
@owner_or_admin_required
def get_user(current_user, user_id):
    """
    Get user by ID
    ---
    tags:
      - Users
    summary: Get a specific user by ID
    description: Retrieve detailed information about a specific user. Users can only view their own profile unless they are admin.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: user_id
        type: integer
        required: true
        description: The user ID
    responses:
      200:
        description: User retrieved successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            email:
              type: string
            first_name:
              type: string
            last_name:
              type: string
            role:
              type: string
      401:
        description: Unauthorized
      403:
        description: Forbidden - Cannot access this user
      404:
        description: User not found
      500:
        description: Server error
    """
    try:
        data = UsersService().get_user(current_user, user_id)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get user error: {e}')
        return jsonify({'error': 'Failed to retrieve user', 'message': 'An error occurred while fetching user information'}), 500


@users_bp.route('/<int:user_id>', methods=['PUT'])
@owner_or_admin_required
@validate_json_content_type
def update_user(current_user, user_id):
    """
    Update user
    ---
    tags:
      - Users
    summary: Update user information
    description: Update user profile information. Users can only update their own profile unless they are admin.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: user_id
        type: integer
        required: true
        description: The user ID
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            first_name:
              type: string
            last_name:
              type: string
            phone:
              type: string
    responses:
      200:
        description: User updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
            user:
              type: object
      400:
        description: Validation error
      401:
        description: Unauthorized
      403:
        description: Forbidden
      500:
        description: Server error
    """
    try:
        data = UsersService().update_user(current_user, user_id, request.get_json() or {})
        return jsonify(data), 200
    except UsersValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Update user error: {e}')
        return jsonify({'error': 'Failed to update user', 'message': 'An error occurred while updating user information'}), 500


@users_bp.route('/<int:user_id>/status', methods=['PATCH'])
@admin_required
@validate_json_content_type
def update_user_status(current_user, user_id):
    """
    Update user status
    ---
    tags:
      - Users
    summary: Update user account status (Admin only)
    description: Activate, suspend, or deactivate a user account. Admin access required.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: user_id
        type: integer
        required: true
        description: The user ID
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - status
          properties:
            status:
              type: string
              enum: [active, inactive, suspended]
              description: New account status
    responses:
      200:
        description: User status updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
            user:
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
        data = UsersService().update_user_status(current_user, user_id, request.get_json() or {})
        return jsonify(data), 200
    except UsersValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Update user status error: {e}')
        return jsonify({'error': 'Failed to update user status', 'message': 'An error occurred while updating user status'}), 500


@users_bp.route('/stats', methods=['GET'])
@admin_required
def get_user_stats(current_user):
    """
    Get user statistics
    ---
    tags:
      - Users
    summary: Get user statistics (Admin only)
    description: Retrieve statistics about users in the system. Admin access required.
    security:
      - Bearer: []
    responses:
      200:
        description: Statistics retrieved successfully
        schema:
          type: object
          properties:
            total_users:
              type: integer
            active_users:
              type: integer
            users_by_role:
              type: object
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        data = UsersService().stats()
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get user stats error: {e}')
        return jsonify({'error': 'Failed to retrieve user statistics', 'message': 'An error occurred while fetching user statistics'}), 500
