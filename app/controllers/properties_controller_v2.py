"""
Properties controller (v2): delegates to PropertiesService
"""
from flask import Blueprint, request, jsonify, current_app
from app import db, limiter
from app.utils.decorators import auth_required, manager_required, property_limit_check, validate_json_content_type
from app.services.properties_service_v2 import PropertiesService, PropertiesValidationError

properties_bp = Blueprint('properties', __name__)


@properties_bp.route('', methods=['GET'])
def get_properties():
    """
    Get all public properties
    ---
    tags:
      - Properties
    summary: List all public properties
    description: Retrieve a list of all publicly available properties with optional filtering
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
        name: search
        type: string
        description: Search term for property name or location
    responses:
      200:
        description: Properties retrieved successfully
        schema:
          type: object
          properties:
            properties:
              type: array
              items:
                type: object
            total:
              type: integer
            page:
              type: integer
      400:
        description: Validation error
      500:
        description: Server error
    """
    try:
        data = PropertiesService().list_public(request.args)
        return jsonify(data), 200
    except PropertiesValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        current_app.logger.error(f'Get properties error: {e}')
        return jsonify({'error': 'Failed to retrieve properties', 'message': 'An error occurred while fetching properties'}), 500


@properties_bp.route('/<int:property_id>', methods=['GET'])
def get_property(property_id):
    """
    Get property by ID
    ---
    tags:
      - Properties
    summary: Get a specific property by ID
    description: Retrieve detailed information about a specific property
    parameters:
      - in: path
        name: property_id
        type: integer
        required: true
        description: The property ID
    responses:
      200:
        description: Property retrieved successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            address:
              type: string
            description:
              type: string
      404:
        description: Property not found
      500:
        description: Server error
    """
    try:
        data = PropertiesService().get_by_id_public(property_id)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get property error: {e}')
        return jsonify({'error': 'Failed to retrieve property', 'message': 'An error occurred while fetching property information'}), 500


@properties_bp.route('', methods=['POST'])
@property_limit_check
@validate_json_content_type
def create_property(current_user):
    """
    Create a new property
    ---
    tags:
      - Properties
    summary: Create a new property
    description: Create a new property listing. Property managers only. Subject to subscription plan limits.
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
            - address
          properties:
            name:
              type: string
            address:
              type: string
            description:
              type: string
            property_type:
              type: string
    responses:
      201:
        description: Property created successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
      400:
        description: Validation error or property limit reached
      401:
        description: Unauthorized
      403:
        description: Forbidden - Property manager access required
      500:
        description: Server error
    """
    try:
        data = PropertiesService().create(current_user, request.get_json() or {})
        return jsonify(data), 201
    except PropertiesValidationError as e:
        return jsonify({'error': str(e), **e.details}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Create property error: {e}')
        return jsonify({'error': 'Failed to create property', 'message': 'An error occurred while creating the property'}), 500


@properties_bp.route('/my-properties', methods=['GET'])
@manager_required
def get_my_properties(current_user):
    """
    Get my properties
    ---
    tags:
      - Properties
    summary: Get properties owned by authenticated manager
    description: Retrieve all properties owned by the currently authenticated property manager
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
    responses:
      200:
        description: Properties retrieved successfully
        schema:
          type: object
          properties:
            properties:
              type: array
              items:
                type: object
            total:
              type: integer
      401:
        description: Unauthorized
      403:
        description: Forbidden - Property manager access required
      500:
        description: Server error
    """
    try:
        data = PropertiesService().list_my_properties(current_user, request.args)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get my properties error: {e}')
        return jsonify({'error': 'Failed to retrieve properties', 'message': 'An error occurred while fetching your properties'}), 500


@properties_bp.route('/active', methods=['GET'])
def get_active_properties():
    """
    Get active properties for inquiries
    ---
    tags:
      - Properties
    summary: Get all active properties available for tenant inquiries
    description: Retrieve a list of all active properties that tenants can inquire about
    parameters:
      - in: query
        name: page
        type: integer
        description: Page number for pagination
      - in: query
        name: search
        type: string
        description: Search term for property name or location
    responses:
      200:
        description: Active properties retrieved successfully
        schema:
          type: object
          properties:
            properties:
              type: array
              items:
                type: object
            total:
              type: integer
      500:
        description: Server error
    """
    try:
        data = PropertiesService().list_active_for_inquiries(request.args)
        return jsonify(data), 200
    except Exception as e:
        current_app.logger.error(f'Get active properties error: {e}')
        return jsonify({'error': 'Failed to retrieve active properties', 'message': 'An error occurred while fetching available properties'}), 500
