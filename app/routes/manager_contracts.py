"""
Manager Contract Routes - Create and manage rental contracts before tenant assignment
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
from app.models.property import Property
from app.models.inquiry import Inquiry
from app.models.rental_contract import RentalContract
from app.utils.decorators import manager_required, auth_required
from app.utils.error_handlers import handle_api_error
from sqlalchemy import text


manager_contracts_bp = Blueprint('manager_contracts', __name__)


@manager_contracts_bp.route('/', methods=['POST'])
@manager_required
def create_contract(current_user):
    """
    Create a new rental contract (before tenant assignment).
    
    Required fields:
    - inquiry_id: ID of the inquiry
    - unit_id: ID of the unit
    - contract_type: 'quarterly' or 'yearly'
    - start_date: Contract start date (YYYY-MM-DD)
    - monthly_rent: Monthly rent amount
    
    Optional fields:
    - security_deposit: Security deposit amount
    - terms_and_conditions: Contract terms
    - special_conditions: Special conditions
    """
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        inquiry_id = data.get('inquiry_id')
        unit_id = data.get('unit_id')
        contract_type = data.get('contract_type')
        start_date_str = data.get('start_date')
        monthly_rent = data.get('monthly_rent')
        
        if not all([inquiry_id, unit_id, contract_type, start_date_str, monthly_rent]):
            return handle_api_error(400, "Missing required fields: inquiry_id, unit_id, contract_type, start_date, monthly_rent")
        
        # Validate contract type
        if contract_type.lower() not in ['quarterly', 'yearly']:
            return handle_api_error(400, "contract_type must be 'quarterly' or 'yearly'")
        
        # Parse start date
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return handle_api_error(400, "Invalid start_date format. Use YYYY-MM-DD")
        
        # Get inquiry using raw SQL to avoid enum conversion issues
        inquiry_row = db.session.execute(text(
            """
            SELECT id, property_id, tenant_id, inquiry_type, status
            FROM inquiries
            WHERE id = :iid
            """
        ), {'iid': inquiry_id}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, "Inquiry not found")
        
        inquiry_property_id = inquiry_row.get('property_id')
        
        # Verify manager owns the property
        property_obj = Property.query.get(inquiry_property_id)
        if not property_obj or property_obj.owner_id != current_user.id:
            return handle_api_error(403, "You can only create contracts for your own properties")
        
        # Verify unit belongs to property
        unit_check = db.session.execute(text(
            "SELECT id, property_id FROM units WHERE id = :uid"
        ), {'uid': unit_id}).first()
        
        if not unit_check:
            return handle_api_error(404, "Unit not found")
        
        if unit_check[1] != inquiry_property_id:
            return handle_api_error(400, "Unit does not belong to the property in the inquiry")
        
        # Check if contract already exists for this inquiry
        existing_contract = RentalContract.query.filter_by(
            inquiry_id=inquiry_id,
            status='draft'
        ).first()
        
        if existing_contract:
            return handle_api_error(400, "A draft contract already exists for this inquiry")
        
        # Create contract (without tenant_unit_id - will be linked later)
        contract = RentalContract(
            unit_id=unit_id,
            property_id=inquiry_property_id,
            contract_type=contract_type.lower(),
            start_date=start_date,
            monthly_rent=monthly_rent,
            inquiry_id=inquiry_id,
            tenant_id=inquiry_row.get('tenant_id'),  # Link to tenant user (not tenant profile yet)
            security_deposit=data.get('security_deposit'),
            terms_and_conditions=data.get('terms_and_conditions'),
            special_conditions=data.get('special_conditions'),
            status='draft'
        )
        
        db.session.add(contract)
        db.session.commit()
        
        return jsonify({
            'message': 'Contract created successfully',
            'contract': contract.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating contract: {str(e)}")
        return handle_api_error(500, f"Failed to create contract: {str(e)}")


@manager_contracts_bp.route('/<int:contract_id>', methods=['GET'])
@manager_required
def get_contract(current_user, contract_id):
    """Get a specific contract."""
    try:
        contract = RentalContract.query.get(contract_id)
        if not contract:
            return handle_api_error(404, "Contract not found")
        
        # Verify manager owns the property
        property_obj = Property.query.get(contract.property_id)
        if not property_obj or property_obj.owner_id != current_user.id:
            return handle_api_error(403, "Access denied")
        
        return jsonify(contract.to_dict()), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting contract: {str(e)}")
        return handle_api_error(500, f"Failed to get contract: {str(e)}")


@manager_contracts_bp.route('/inquiry/<int:inquiry_id>', methods=['GET'])
@manager_required
def get_contract_by_inquiry(current_user, inquiry_id):
    """Get contract for a specific inquiry."""
    try:
        # Use raw SQL to avoid enum conversion issues
        inquiry_row = db.session.execute(text(
            """
            SELECT id, property_id, tenant_id, inquiry_type, status
            FROM inquiries
            WHERE id = :iid
            """
        ), {'iid': inquiry_id}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, "Inquiry not found")
        
        # Verify manager owns the property
        property_obj = Property.query.get(inquiry_row.get('property_id'))
        if not property_obj or property_obj.owner_id != current_user.id:
            return handle_api_error(403, "Access denied")
        
        contract = RentalContract.query.filter_by(inquiry_id=inquiry_id).first()
        if not contract:
            return jsonify({'contract': None}), 200
        
        return jsonify({'contract': contract.to_dict()}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting contract: {str(e)}")
        return handle_api_error(500, f"Failed to get contract: {str(e)}")


@manager_contracts_bp.route('/<int:contract_id>/sign-landlord', methods=['POST'])
@manager_required
def sign_contract_landlord(current_user, contract_id):
    """Sign contract as landlord/property manager."""
    try:
        contract = RentalContract.query.get(contract_id)
        if not contract:
            return handle_api_error(404, "Contract not found")
        
        # Verify manager owns the property
        property_obj = Property.query.get(contract.property_id)
        if not property_obj or property_obj.owner_id != current_user.id:
            return handle_api_error(403, "Access denied")
        
        if contract.landlord_signed:
            return handle_api_error(400, "Contract already signed by landlord")
        
        contract.sign_by_landlord(current_user.id)
        
        return jsonify({
            'message': 'Contract signed by landlord successfully',
            'contract': contract.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error signing contract: {str(e)}")
        return handle_api_error(500, f"Failed to sign contract: {str(e)}")


@manager_contracts_bp.route('/<int:contract_id>', methods=['PUT'])
@manager_required
def update_contract(current_user, contract_id):
    """Update a draft contract (only draft contracts can be updated)."""
    try:
        contract = RentalContract.query.get(contract_id)
        if not contract:
            return handle_api_error(404, "Contract not found")
        
        # Verify manager owns the property
        property_obj = Property.query.get(contract.property_id)
        if not property_obj or property_obj.owner_id != current_user.id:
            return handle_api_error(403, "Access denied")
        
        # Allow updating if contract is draft OR if neither party has signed yet (negotiation phase)
        if contract.status != 'draft' and (contract.tenant_signed or contract.landlord_signed):
            return handle_api_error(400, "Cannot update contract: Contract has been signed. Only draft contracts or unsigned contracts can be updated.")
        
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        # Update allowed fields
        if 'monthly_rent' in data:
            contract.monthly_rent = data['monthly_rent']
            contract.total_contract_value = contract._calculate_total_value()
        
        if 'security_deposit' in data:
            contract.security_deposit = data['security_deposit']
        
        if 'start_date' in data:
            try:
                contract.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
                contract.end_date = contract._calculate_end_date(contract.start_date, contract.contract_type)
                contract.total_contract_value = contract._calculate_total_value()
            except ValueError:
                return handle_api_error(400, "Invalid start_date format. Use YYYY-MM-DD")
        
        if 'contract_type' in data:
            contract_type = data['contract_type'].lower()
            if contract_type not in ['quarterly', 'yearly']:
                return handle_api_error(400, "contract_type must be 'quarterly' or 'yearly'")
            contract.contract_type = contract_type
            contract.end_date = contract._calculate_end_date(contract.start_date, contract_type)
            contract.total_contract_value = contract._calculate_total_value()
        
        if 'terms_and_conditions' in data:
            contract.terms_and_conditions = data['terms_and_conditions']
        
        if 'special_conditions' in data:
            contract.special_conditions = data['special_conditions']
        
        contract.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Contract updated successfully',
            'contract': contract.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating contract: {str(e)}")
        return handle_api_error(500, f"Failed to update contract: {str(e)}")

