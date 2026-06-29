"""
Tenant Contract Routes - Sign contracts
"""
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.rental_contract import RentalContract
from app.models.inquiry import Inquiry
from app.utils.decorators import tenant_required
from app.utils.error_handlers import handle_api_error


tenant_contracts_bp = Blueprint('tenant_contracts', __name__)


@tenant_contracts_bp.route('/inquiry/<int:inquiry_id>', methods=['GET'])
@tenant_required
def get_contract_by_inquiry(current_user, inquiry_id):
    """Get contract for a specific inquiry (tenant's own inquiries only)."""
    try:
        # Use raw SQL to avoid enum conversion issues
        from sqlalchemy import text
        inquiry_row = db.session.execute(text(
            """
            SELECT id, property_id, tenant_id, inquiry_type, status
            FROM inquiries
            WHERE id = :iid
            """
        ), {'iid': inquiry_id}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, "Inquiry not found")
        
        # Verify tenant owns the inquiry
        if inquiry_row.get('tenant_id') != current_user.id:
            return handle_api_error(403, "Access denied")
        
        contract = RentalContract.query.filter_by(inquiry_id=inquiry_id).first()
        if not contract:
            return jsonify({'contract': None}), 200
        
        return jsonify({'contract': contract.to_dict()}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error getting contract: {str(e)}")
        return handle_api_error(500, f"Failed to get contract: {str(e)}")


@tenant_contracts_bp.route('/<int:contract_id>/sign-tenant', methods=['POST'])
@tenant_required
def sign_contract_tenant(current_user, contract_id):
    """Sign contract as tenant."""
    try:
        contract = RentalContract.query.get(contract_id)
        if not contract:
            return handle_api_error(404, "Contract not found")
        
        # Verify tenant is the one in the contract
        if contract.tenant_id != current_user.id:
            return handle_api_error(403, "Access denied")
        
        if contract.tenant_signed:
            return handle_api_error(400, "Contract already signed by tenant")
        
        contract.sign_by_tenant()
        
        return jsonify({
            'message': 'Contract signed by tenant successfully',
            'contract': contract.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error signing contract: {str(e)}")
        return handle_api_error(500, f"Failed to sign contract: {str(e)}")

