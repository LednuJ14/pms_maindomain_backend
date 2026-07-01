"""
Simplified Manager Inquiries API Routes
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
from app.models.property import Property
from app.models.inquiry import Inquiry, InquiryStatus, InquiryType
from app.utils.decorators import auth_required, manager_required
from app.utils.error_handlers import handle_api_error
import json

def safe_isoformat(dt):
    """Convert datetime to ISO format string with UTC indicator if timezone info is missing."""
    if not dt:
        return None
    iso_str = dt.isoformat()
    # If no timezone info, append 'Z' to indicate UTC
    if not iso_str.endswith('Z') and '+' not in iso_str:
        # Check if it's a naive datetime (no timezone offset in string)
        if len(iso_str) == 19 or (len(iso_str) > 19 and iso_str[19] not in ['+', '-', 'Z']):
            iso_str += 'Z'
    return iso_str

manager_inquiries_bp = Blueprint('manager_inquiries', __name__)

@manager_inquiries_bp.route('/', methods=['GET'])
@manager_required
def get_manager_inquiries(current_user):
    """
    Get manager inquiries
    ---
    tags:
      - Manager Inquiries
    summary: Get all inquiries for manager's properties
    description: Retrieve all inquiries for properties owned by the authenticated property manager
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by inquiry status
      - in: query
        name: property_id
        type: integer
        description: Filter by property ID
    responses:
      200:
        description: Inquiries retrieved successfully
        schema:
          type: object
          properties:
            inquiries:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  property_id:
                    type: integer
                  tenant_id:
                    type: integer
                  status:
                    type: string
                  messages:
                    type: array
      401:
        description: Unauthorized
      403:
        description: Forbidden - Manager access required
      500:
        description: Server error
    """
    try:
        # Get all properties owned by this manager using raw SQL to avoid model mismatches
        from sqlalchemy import text
        rows = db.session.execute(text(
            "SELECT id FROM properties WHERE owner_id = :oid"
        ), { 'oid': current_user.id }).fetchall()
        property_ids = [r[0] for r in rows]
        
        if not property_ids:
            return jsonify({
                'inquiries': []
            }), 200
        
        # Get all inquiries for manager's properties using raw SQL to avoid enum mismatches
        from sqlalchemy import text
        
        # Ensure we have property_ids as a tuple for SQL IN clause (MySQL/MariaDB compatible)
        property_ids_tuple = tuple(property_ids) if len(property_ids) > 1 else (property_ids[0],) if len(property_ids) == 1 else ()
        
        # Query with unit_id column (now always available)
        # Explicitly filter by property_ids and ensure property_manager_id matches current_user
        # This ensures we only get inquiries for properties owned by this manager
        # Allow multiple inquiries per property/unit - removed the MAX(created_at) grouping
        # Use DISTINCT to prevent duplicate rows from JOINs
        inquiries = db.session.execute(text(
            """
            SELECT DISTINCT i.id, i.property_id, i.tenant_id, i.property_manager_id,
                   i.inquiry_type, i.status, i.message,
                   i.created_at, i.updated_at, i.read_at,
                   i.unit_id,
                   COALESCE(u.unit_name, u2.unit_name) AS unit_name
            FROM inquiries i
            LEFT JOIN units u ON u.id = i.unit_id
            LEFT JOIN units u2 ON u2.property_id = i.property_id AND u2.status = 'vacant' AND i.unit_id IS NULL
            LEFT JOIN users tenant ON tenant.id = i.tenant_id
            WHERE i.property_id IN :pids
              AND (i.property_manager_id = :manager_id OR i.property_manager_id IS NULL)
              AND (i.is_archived IS NULL OR i.is_archived = 0)
            ORDER BY i.created_at DESC
            """
        ), { 
            'pids': property_ids_tuple,
            'manager_id': current_user.id
        }).mappings().all()
        
        # Additional deduplication by ID in case DISTINCT doesn't catch everything
        seen_ids = set()
        unique_inquiries = []
        for inquiry in inquiries:
            inquiry_id = inquiry.get('id')
            if inquiry_id and inquiry_id not in seen_ids:
                seen_ids.add(inquiry_id)
                unique_inquiries.append(inquiry)
        
        inquiry_data = []
        for inquiry in unique_inquiries:
            # Get property info and verify ownership (extra security check)
            prop_row = db.session.execute(text(
                "SELECT id, title, building_name, address, city, province, owner_id FROM properties WHERE id = :pid AND owner_id = :manager_id"
            ), { 
                'pid': inquiry.get('property_id'),
                'manager_id': current_user.id
            }).mappings().first()
            
            # Skip if property doesn't belong to this manager (shouldn't happen due to WHERE clause, but extra safety)
            if not prop_row:
                current_app.logger.warning(f'Inquiry {inquiry.get("id")} references property {inquiry.get("property_id")} not owned by manager {current_user.id}')
                continue
            property_data = {
                'id': prop_row.get('id') if prop_row else None,
                'title': prop_row.get('title') if prop_row else 'Unknown Property',
                'building_name': prop_row.get('building_name') if prop_row else None,
                'address': prop_row.get('address') if prop_row else None,
                'city': prop_row.get('city') if prop_row else None,
                'province': prop_row.get('province') if prop_row else None
            } if prop_row else None
            
            # Get tenant info from users table
            tenant_info = User.query.get(inquiry.get('tenant_id'))
            tenant_data = {
                'id': tenant_info.id if tenant_info else None,
                'first_name': tenant_info.first_name if tenant_info else '',
                'last_name': tenant_info.last_name if tenant_info else '',
                'email': tenant_info.email if tenant_info else '',
                'phone': tenant_info.phone_number if tenant_info else None
            } if tenant_info else {
                'id': None,
                'first_name': '',
                'last_name': '',
                'email': '',
                'phone': None
            }
            
            # Get messages from inquiry_messages table
            message_rows = db.session.execute(text(
                """
                SELECT id, inquiry_id, sender_id, message, is_read, created_at, updated_at
                FROM inquiry_messages
                WHERE inquiry_id = :iid
                ORDER BY created_at ASC
                """
            ), { 'iid': inquiry.get('id') }).mappings().all()
            
            # Format messages for frontend
            messages_list = []
            property_manager_id = inquiry.get('property_manager_id')
            for msg_row in message_rows:
                # Determine if sender is tenant or manager
                sender_id = msg_row.get('sender_id')
                # Compare as integers to ensure proper comparison
                is_manager = int(sender_id) == int(property_manager_id) if sender_id and property_manager_id else False
                messages_list.append({
                    'id': msg_row.get('id'),
                    'inquiry_id': msg_row.get('inquiry_id'),
                    'sender_id': sender_id,
                    'sender': 'manager' if is_manager else 'tenant',
                    'message': msg_row.get('message'),
                    'text': msg_row.get('message'),  # Add 'text' alias for frontend compatibility
                    'is_read': bool(msg_row.get('is_read')),
                    'created_at': safe_isoformat(msg_row.get('created_at'))
                })
            
            # Get pre-qualification details if available
            pre_qual_row = db.session.execute(text(
                "SELECT income_bracket, employment_status, has_pets, move_in_date FROM pre_qualification_data WHERE inquiry_id = :iid"
            ), {'iid': inquiry.get('id')}).mappings().first()
            
            pre_qual_data = None
            if pre_qual_row:
                pre_qual_data = {
                    'income': pre_qual_row.get('income_bracket'),
                    'employment': pre_qual_row.get('employment_status'),
                    'pets': bool(pre_qual_row.get('has_pets')),
                    'move_in_date': safe_isoformat(pre_qual_row.get('move_in_date'))
                }
                
            inquiry_dict = {
                'id': inquiry.get('id'),
                'property_id': inquiry.get('property_id'),
                'unit_id': inquiry.get('unit_id'),
                'tenant_id': inquiry.get('tenant_id'),
                'property_manager_id': inquiry.get('property_manager_id'),
                'inquiry_type': str(inquiry.get('inquiry_type')).lower() if inquiry.get('inquiry_type') else 'rental_inquiry',
                'status': str(inquiry.get('status')).lower() if inquiry.get('status') else 'pending',
                'message': inquiry.get('message'),  # Keep for backward compatibility
                'messages': messages_list,  # New messages array from inquiry_messages table
                'tenant': tenant_data,
                'created_at': safe_isoformat(inquiry.get('created_at')),
                'updated_at': safe_isoformat(inquiry.get('updated_at')),
                'unit_id': inquiry.get('unit_id'),
                'unit_name': inquiry.get('unit_name'),
                'property': property_data,
                'tenant': tenant_data,
                'pre_qualification': pre_qual_data
            }
            
            inquiry_data.append(inquiry_dict)
        
        return jsonify({
            'inquiries': inquiry_data
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get manager inquiries error: {e}')
        return handle_api_error(500, f"Failed to retrieve inquiries: {str(e)}")

@manager_inquiries_bp.route('/send-message', methods=['POST'])
@manager_required
def send_message(current_user):
    """
    Send message to inquiry
    ---
    tags:
      - Manager Inquiries
    summary: Send a response message to an inquiry
    description: Send a message response to a tenant inquiry
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - inquiry_id
            - message
          properties:
            inquiry_id:
              type: integer
              description: The inquiry ID
            message:
              type: string
              description: Message content
    responses:
      200:
        description: Message sent successfully
        schema:
          type: object
          properties:
            message:
              type: string
            inquiry_id:
              type: integer
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
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")

        inquiry_id = data.get('inquiry_id')
        message = data.get('message', '').strip()

        if not inquiry_id or not message:
            return handle_api_error(400, "Inquiry ID and message are required")

        from sqlalchemy import text
        # Fetch inquiry minimal fields
        row = db.session.execute(text(
            "SELECT id, property_id FROM inquiries WHERE id = :iid"
        ), { 'iid': inquiry_id }).mappings().first()
        if not row:
            return handle_api_error(404, "Inquiry not found")

        # Verify manager owns the property
        owner_ok = db.session.execute(text(
            "SELECT 1 FROM properties WHERE id = :pid AND owner_id = :oid"
        ), { 'pid': row.get('property_id'), 'oid': current_user.id }).first()
        if not owner_ok:
            return handle_api_error(403, "You can only respond to inquiries for your properties")

        # Create a new message using InquiryMessage model
        try:
            from app.models.inquiry_message import InquiryMessage
            
            # Create new message record
            new_message = InquiryMessage(
                inquiry_id=inquiry_id,
                sender_id=current_user.id,
                message=message,
                is_read=False
            )
            db.session.add(new_message)
            
            # Update inquiry status to RESPONDED if it's still pending
            db.session.execute(text(
                """
                UPDATE inquiries
                SET status = CASE 
                        WHEN status = 'PENDING' OR status = 'pending' THEN 'RESPONDED'
                        ELSE status
                    END,
                    updated_at = NOW()
                WHERE id = :iid
                """
            ), { 'iid': inquiry_id })
            
            db.session.commit()
            
            # Send notification to tenant about the response
            try:
                from app.services.notification_service import NotificationService
                from sqlalchemy import text
                
                # Get inquiry and property details for notification
                inquiry_info = db.session.execute(text(
                    """
                    SELECT i.tenant_id, i.property_id, p.title, p.building_name,
                           u.first_name, u.last_name
                    FROM inquiries i
                    JOIN properties p ON p.id = i.property_id
                    LEFT JOIN users u ON u.id = :mid
                    WHERE i.id = :iid
                    """
                ), { 'iid': inquiry_id, 'mid': current_user.id }).mappings().first()
                
                if inquiry_info:
                    property_name = inquiry_info.get('title') or inquiry_info.get('building_name') or 'Property'
                    manager_name = f"{inquiry_info.get('first_name') or ''} {inquiry_info.get('last_name') or ''}".strip() or 'Property Manager'
                    tenant_id = inquiry_info.get('tenant_id')
                    
                    NotificationService.notify_inquiry_response(
                        tenant_id=tenant_id,
                        inquiry_id=inquiry_id,
                        property_name=property_name,
                        manager_name=manager_name
                    )
            except Exception as notif_error:
                current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
                # Don't fail the request if notification fails
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating inquiry: {str(e)}")
            return handle_api_error(500, "Failed to send response")

        return jsonify({ 'message': 'Response sent successfully', 'success': True }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Send message error: {e}')
        return handle_api_error(500, f"Failed to send response: {str(e)}")

@manager_inquiries_bp.route('/<int:inquiry_id>/mark-read', methods=['POST'])
@manager_required
def mark_as_read(current_user, inquiry_id):
    """
    Mark inquiry as read
    ---
    tags:
      - Manager Inquiries
    summary: Mark an inquiry as read
    description: Mark an inquiry as read by the property manager
    security:
      - Bearer: []
    parameters:
      - in: path
        name: inquiry_id
        type: integer
        required: true
        description: The inquiry ID
    responses:
      200:
        description: Inquiry marked as read
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Inquiry not found
      500:
        description: Server error
    """
    try:
        inquiry = Inquiry.query.get(inquiry_id)
        if not inquiry:
            return handle_api_error(404, "Inquiry not found")
        
        # Check if the inquiry is for a property owned by this manager
        property_info = Property.query.get(inquiry.property_id)
        if not property_info or property_info.owner_id != current_user.id:
            return handle_api_error(403, "You can only mark inquiries for your properties as read")
        
        # Update the inquiry
        inquiry.status = InquiryStatus.READ
        inquiry.read_at = datetime.utcnow()
        inquiry.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating inquiry: {str(e)}")
            return handle_api_error(500, "Failed to mark inquiry as read")
        
        return jsonify({
            'message': 'Inquiry marked as read',
            'success': True
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Mark as read error: {e}')
        return handle_api_error(500, f"Failed to mark inquiry as read: {str(e)}")


@manager_inquiries_bp.route('/assign-tenant', methods=['POST'])
@manager_required
def assign_tenant_to_property(current_user):
    """Assign a tenant to a property based on inquiry."""
    tenant_profile_id = None
    tenant_unit_id = None
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")

        inquiry_id = data.get('inquiry_id')
        property_id = data.get('property_id')

        if not inquiry_id or not property_id:
            return handle_api_error(400, "Inquiry ID and Property ID are required")

        from sqlalchemy import text
        
        # Verify the inquiry exists and get tenant info (join with users table to get tenant name and email)
        inquiry_row = db.session.execute(text(
            """
            SELECT i.id, i.tenant_id, i.property_id, i.unit_id,
                   u.first_name, u.last_name, u.email, u.phone_number
            FROM inquiries i
            LEFT JOIN users u ON u.id = i.tenant_id
            WHERE i.id = :iid
            """
        ), { 'iid': inquiry_id }).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, "Inquiry not found")

        # Verify manager owns the property
        owner_check = db.session.execute(text(
            "SELECT id FROM properties WHERE id = :pid AND owner_id = :oid"
        ), { 'pid': property_id, 'oid': current_user.id }).first()
        
        if not owner_check:
            return handle_api_error(403, "You can only assign tenants to your own properties")

        # Check if property_id matches the inquiry's property
        if inquiry_row.get('property_id') != property_id:
            return handle_api_error(400, "Property ID does not match the inquiry's property")

        # ⭐ NEW: Check if a signed contract exists for this inquiry
        from app.models.rental_contract import RentalContract
        contract = RentalContract.query.filter_by(inquiry_id=inquiry_id).first()
        
        if not contract:
            return handle_api_error(400, "Cannot assign tenant: No contract found. Please create and sign a contract first.")
        
        if contract.status != 'active' or not (contract.tenant_signed and contract.landlord_signed):
            return handle_api_error(400, "Cannot assign tenant: Contract must be fully signed by both parties before assignment. Current status: " + 
                                  f"Tenant signed: {contract.tenant_signed}, Landlord signed: {contract.landlord_signed}")

        # Get or create tenant user
        tenant_id = inquiry_row.get('tenant_id')
        # Get tenant name and email from users table
        tenant_first_name = inquiry_row.get('first_name') or ''
        tenant_last_name = inquiry_row.get('last_name') or ''
        tenant_name = f"{tenant_first_name} {tenant_last_name}".strip() if (tenant_first_name or tenant_last_name) else None
        tenant_email = inquiry_row.get('email')

        if not tenant_id:
            # If tenant_id is missing, we need tenant info to create a new user
            # Since tenant_id is required in inquiries table, this should rarely happen
            if not tenant_email:
                return handle_api_error(400, "Cannot assign tenant: inquiry is missing tenant information")
            
            # Create a new tenant user if they don't exist
            from app.models.user import User, UserRole
            from werkzeug.security import generate_password_hash
            import secrets
            
            # Generate a temporary password
            temp_password = secrets.token_urlsafe(12)
            
            # Split tenant name
            name_parts = tenant_name.split(' ') if tenant_name else ['Tenant']
            first_name = name_parts[0]
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            
            new_tenant = User(
                first_name=first_name,
                last_name=last_name,
                email=tenant_email,
                password_hash=generate_password_hash(temp_password),
                role=UserRole.TENANT,
                is_active=True,
                phone_number=inquiry_row.get('phone_number')
            )
            
            db.session.add(new_tenant)
            db.session.flush()  # Get the ID
            tenant_id = new_tenant.id

        # Get old status before updating
        old_status_row = db.session.execute(text(
            "SELECT status FROM inquiries WHERE id = :iid"
        ), { 'iid': inquiry_id }).mappings().first()
        old_status = old_status_row.get('status') if old_status_row else 'pending'
        
        # Update the inquiry status to assigned (use lowercase to match frontend)
        db.session.execute(text(
            """
            UPDATE inquiries 
            SET status = 'assigned', 
                updated_at = NOW()
            WHERE id = :iid
            """
        ), { 'iid': inquiry_id })
        
        # Send notification to tenant about status change
        try:
            from app.services.notification_service import NotificationService
            from sqlalchemy import text
            
            # Get inquiry and property details
            inquiry_info = db.session.execute(text(
                """
                SELECT i.tenant_id, i.property_id, p.title, p.building_name
                FROM inquiries i
                JOIN properties p ON p.id = i.property_id
                WHERE i.id = :iid
                """
            ), { 'iid': inquiry_id }).mappings().first()
            
            if inquiry_info:
                property_name = inquiry_info.get('title') or inquiry_info.get('building_name') or 'Property'
                tenant_id = inquiry_info.get('tenant_id')
                
                NotificationService.notify_inquiry_status_change(
                    tenant_id=tenant_id,
                    inquiry_id=inquiry_id,
                    property_name=property_name,
                    old_status=old_status.lower(),
                    new_status="assigned"
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails

        # Get the specific unit if inquiry has unit_id, or use provided unit_id/unit_name, or get first available
        unit_id_from_inquiry = inquiry_row.get('unit_id')
        unit_id_from_request = data.get('unit_id')
        unit_name_from_request = data.get('unit_name')
        
        unit_row = None
        
        # Priority 1: Use unit_id from request if provided
        if unit_id_from_request:
            unit_row = db.session.execute(text(
                "SELECT id, unit_name, monthly_rent, security_deposit FROM units WHERE id = :uid AND property_id = :pid AND (status = 'vacant' OR status = 'available')"
            ), { 'uid': unit_id_from_request, 'pid': property_id }).first()
        
        # Priority 2: Use unit_id from inquiry if available
        if not unit_row and unit_id_from_inquiry:
            unit_row = db.session.execute(text(
                "SELECT id, unit_name, monthly_rent, security_deposit FROM units WHERE id = :uid AND property_id = :pid AND (status = 'vacant' OR status = 'available')"
            ), { 'uid': unit_id_from_inquiry, 'pid': property_id }).first()
        
        # Priority 3: Use unit_name from request if provided
        if not unit_row and unit_name_from_request:
            unit_row = db.session.execute(text(
                "SELECT id, unit_name, monthly_rent, security_deposit FROM units WHERE property_id = :pid AND unit_name = :uname AND (status = 'vacant' OR status = 'available')"
            ), { 'pid': property_id, 'uname': unit_name_from_request }).first()
        
        # Priority 4: Fallback to first available unit
        if not unit_row:
            unit_row = db.session.execute(text(
                "SELECT id, unit_name, monthly_rent, security_deposit FROM units WHERE property_id = :pid AND (status = 'vacant' OR status = 'available') LIMIT 1"
            ), { 'pid': property_id }).first()
        
        if unit_row:
            unit_id = unit_row[0]
            unit_name = unit_row[1]
            monthly_rent = float(unit_row[2]) if unit_row[2] else 0.0
            security_deposit = float(unit_row[3]) if unit_row[3] else 0.0
            
                # Note: Unit status is now computed dynamically from tenant_units table
            # We don't manually update the unit status here - it will automatically show as 'occupied' 
            # when a tenant_units record exists with move_out_date in the future or NULL
            
            try:
                tenant_profile = db.session.execute(text(
                    "SELECT id FROM tenants WHERE user_id = :tid AND property_id = :pid"
                ), { 'tid': tenant_id, 'pid': property_id }).first()
                
                if tenant_profile:
                    tenant_profile_id = tenant_profile[0]
                    current_app.logger.info(f"Tenant profile already exists for user_id={tenant_id}, property_id={property_id}")
                else:
                    tenant_user = db.session.execute(text(
                        "SELECT email, phone_number FROM users WHERE id = :tid"
                    ), { 'tid': tenant_id }).mappings().first()
                    
                    tenant_email = tenant_user.get('email') if tenant_user else None
                    tenant_phone = tenant_user.get('phone_number') if tenant_user else None
                    
                    db.session.execute(text(
                        """
                        INSERT INTO tenants (user_id, property_id, phone_number, email, created_at, updated_at)
                        VALUES (:tid, :pid, :phone, :email, NOW(), NOW())
                        """
                    ), { 
                        'tid': tenant_id,
                        'pid': property_id,
                        'phone': tenant_phone,
                        'email': tenant_email
                    })
                    db.session.flush()
                    
                    tenant_profile_result = db.session.execute(text(
                        "SELECT id FROM tenants WHERE user_id = :tid AND property_id = :pid ORDER BY id DESC LIMIT 1"
                    ), { 'tid': tenant_id, 'pid': property_id }).first()
                    if tenant_profile_result:
                        tenant_profile_id = tenant_profile_result[0]
                        current_app.logger.info(f"Created tenant record: tenant_id={tenant_profile_id} for user_id={tenant_id}, property_id={property_id}")
                    else:
                        current_app.logger.error(f"Failed to verify tenant record creation for user_id={tenant_id}, property_id={property_id}")
                
                if tenant_profile_id:
                    existing_tenant_unit = db.session.execute(text(
                        "SELECT id FROM tenant_units WHERE tenant_id = :tid AND unit_id = :uid AND property_id = :pid"
                    ), { 
                        'tid': tenant_profile_id, 
                        'uid': unit_id,
                        'pid': property_id
                    }).first()
                    
                    move_in_date = contract.start_date
                    move_out_date = contract.end_date
                    contract_monthly_rent = float(contract.monthly_rent) if contract.monthly_rent else monthly_rent
                    contract_security_deposit = float(contract.security_deposit) if contract.security_deposit else security_deposit
                    
                    if existing_tenant_unit:
                        tenant_unit_id = existing_tenant_unit[0]
                        try:
                            db.session.execute(text(
                                """
                                UPDATE tenant_units
                                SET move_in_date = :move_in,
                                    move_out_date = :move_out,
                                    monthly_rent = :rent,
                                    security_deposit = :deposit,
                                    updated_at = NOW()
                                WHERE id = :id
                                """
                            ), {
                                'move_in': move_in_date,
                                'move_out': move_out_date,
                                'rent': contract_monthly_rent,
                                'deposit': contract_security_deposit,
                                'id': tenant_unit_id
                            })
                            db.session.flush()
                            try:
                                contract.link_to_tenant_unit(tenant_unit_id, tenant_profile_id)
                            except Exception as link_error:
                                current_app.logger.warning(f"Failed to link contract to existing tenant_unit: {str(link_error)}")
                        except Exception as update_existing_error:
                            current_app.logger.error(f"Failed to update existing tenant_units record: {str(update_existing_error)}")
                            raise
                    else:
                        try:
                            db.session.execute(text(
                                """
                                INSERT INTO tenant_units (property_id, tenant_id, unit_id, move_in_date, move_out_date, rent_start_date, rent_end_date, monthly_rent, security_deposit, created_at, updated_at)
                                VALUES (:property_id, :tenant_profile_id, :unit_id, :move_in, :move_out, :rent_start, :rent_end, :rent, :deposit, NOW(), NOW())
                                """
                            ), { 
                                'property_id': property_id,
                                'tenant_profile_id': tenant_profile_id,
                                'unit_id': unit_id,
                                'move_in': move_in_date,
                                'move_out': move_out_date,
                                'rent_start': contract.start_date,
                                'rent_end': contract.end_date,
                                'rent': contract_monthly_rent,
                                'deposit': contract_security_deposit
                            })
                        except Exception as rent_dates_error:
                            current_app.logger.warning(f"rent_start_date/rent_end_date columns may not exist, using move dates only: {str(rent_dates_error)}")
                            db.session.execute(text(
                                """
                                INSERT INTO tenant_units (property_id, tenant_id, unit_id, move_in_date, move_out_date, monthly_rent, security_deposit, created_at, updated_at)
                                VALUES (:property_id, :tenant_profile_id, :unit_id, :move_in, :move_out, :rent, :deposit, NOW(), NOW())
                                """
                            ), { 
                                'property_id': property_id,
                                'tenant_profile_id': tenant_profile_id,
                                'unit_id': unit_id,
                                'move_in': move_in_date,
                                'move_out': move_out_date,
                                'rent': contract_monthly_rent,
                                'deposit': contract_security_deposit
                            })
                        db.session.flush()
                        
                        tenant_unit_result = db.session.execute(text(
                            "SELECT id FROM tenant_units WHERE tenant_id = :tid AND unit_id = :uid AND property_id = :pid ORDER BY created_at DESC LIMIT 1"
                        ), {
                            'tid': tenant_profile_id,
                            'uid': unit_id,
                            'pid': property_id
                        }).first()
                        
                        tenant_unit_id = tenant_unit_result[0] if tenant_unit_result else None
                        
                        if tenant_unit_id:
                            try:
                                contract.link_to_tenant_unit(tenant_unit_id, tenant_profile_id)
                                current_app.logger.info(f"Linked contract {contract.id} to tenant_unit {tenant_unit_id}")
                            except Exception as link_error:
                                current_app.logger.warning(f"Failed to link contract to new tenant_unit: {str(link_error)}")
                        
                        current_app.logger.info(f"Successfully created tenant_units record: tenant_id={tenant_profile_id}, unit_id={unit_id}, property_id={property_id}, move_in={move_in_date}, move_out={move_out_date}")
                        
                        try:
                            db.session.execute(text(
                                "UPDATE units SET status = 'occupied', updated_at = NOW() WHERE id = :uid"
                            ), { 'uid': unit_id })
                            db.session.flush()
                            current_app.logger.info(f"Updated unit {unit_id} status to 'occupied'")
                        except Exception as status_update_error:
                            current_app.logger.warning(f"Failed to update unit status: {str(status_update_error)}")

                else:
                    current_app.logger.error(f"Failed to get tenant_profile_id for user_id={tenant_id}")
            except Exception as tenant_unit_error:
                db.session.rollback()
                current_app.logger.error(f"Error creating tenant_units record: {str(tenant_unit_error)}")
                return handle_api_error(
                    500,
                    f"Failed to assign tenant due to internal error while creating tenant unit: {str(tenant_unit_error)}"
                )
        else:
            return handle_api_error(400, "No available units found for this property")

        db.session.commit()
        
        try:
            import os
            import requests
            subdomain_api_url = os.environ.get('SUBDOMAIN_API_URL', 'http://localhost:5001/api')
            cross_domain_api_key = os.environ.get('CROSS_DOMAIN_API_KEY')
            if subdomain_api_url and cross_domain_api_key and tenant_unit_id and tenant_profile_id:
                url = f"{subdomain_api_url}/contracts/{contract.id}/generate-document"
                headers = {
                    'X-API-Key': cross_domain_api_key,
                    'Content-Type': 'application/json'
                }
                payload = {
                    'tenant_unit_id': tenant_unit_id,
                    'tenant_profile_id': tenant_profile_id
                }
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=15)
                    if response.status_code != 200:
                        current_app.logger.error(
                            f"Subdomain contract document generation failed for contract {contract.id}: "
                            f"status={response.status_code}, body={response.text[:1000]}"
                        )
                except requests.exceptions.Timeout:
                    current_app.logger.error(f"Timeout while calling subdomain generate-document for contract {contract.id}")
                except requests.exceptions.RequestException as req_err:
                    current_app.logger.error(f"Error calling subdomain generate-document for contract {contract.id}: {str(req_err)}")
            else:
                current_app.logger.warning("Subdomain API configuration missing or tenant linkage incomplete; skipping contract document generation")
        except Exception as cross_domain_error:
            current_app.logger.error(f"Unexpected error while triggering subdomain contract document generation: {str(cross_domain_error)}")
        
        # Verify tenant_units was created (for subdomain login)
        tenant_unit_created = False
        try:
            tenant_profile_check = db.session.execute(text(
                "SELECT id FROM tenants WHERE user_id = :tid AND property_id = :pid ORDER BY id DESC LIMIT 1"
            ), { 'tid': tenant_id, 'pid': property_id }).first()
            if tenant_profile_check:
                tenant_profile_id_check = tenant_profile_check[0]
                tenant_unit_check = db.session.execute(text(
                    "SELECT id FROM tenant_units WHERE tenant_id = :tid AND unit_id = :uid AND property_id = :pid"
                ), { 
                    'tid': tenant_profile_id_check, 
                    'uid': unit_id,
                    'pid': property_id
                }).first()
                tenant_unit_created = tenant_unit_check is not None
                if tenant_unit_created:
                    current_app.logger.info(f"Verified: tenant_units record exists for tenant_id={tenant_profile_id_check}, unit_id={unit_id}, property_id={property_id}")
                else:
                    current_app.logger.error(f"CRITICAL: tenant_units record NOT found after creation for tenant_id={tenant_profile_id_check}, unit_id={unit_id}, property_id={property_id}")
        except Exception as verify_error:
            current_app.logger.warning(f"Error verifying tenant_units: {str(verify_error)}")

        response_data = {
            'message': f'Tenant successfully assigned to {unit_name}',
            'success': True,
            'tenant_id': tenant_id,
            'unit_name': unit_name,
            'property_id': property_id,
            'tenant_unit_created': tenant_unit_created
        }
        
        if not tenant_unit_created:
            response_data['warning'] = 'Tenant assigned but subdomain login setup may have failed. Please check backend logs.'
            current_app.logger.error(f"CRITICAL: tenant_units record not verified for tenant_id={tenant_id}, unit_id={unit_id}, property_id={property_id}")

        return jsonify(response_data), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Assign tenant error: {e}')
        return handle_api_error(500, f"Failed to assign tenant: {str(e)}")

@manager_inquiries_bp.route('/units/<int:property_id>', methods=['GET'])
@manager_required
def list_units(current_user, property_id):
    """Return units for a manager-owned property (used by PM UI)."""
    try:
        from sqlalchemy import text
        # Verify ownership
        owner = db.session.execute(text(
            "SELECT id FROM properties WHERE id = :pid AND owner_id = :oid"
        ), { 'pid': property_id, 'oid': current_user.id }).first()
        if not owner:
            return handle_api_error(403, "You do not own this property")

        rows = db.session.execute(text(
            """
            SELECT u.id, u.unit_name, u.status, u.monthly_rent, u.size_sqm,
                   u.bedrooms, u.bathrooms, u.description, u.security_deposit,
                   u.floor_number, u.parking_spaces, u.images, u.amenities,
                   u.created_at, u.updated_at,
                   CASE 
                       WHEN EXISTS (
                           SELECT 1 FROM tenant_units tu 
                           WHERE tu.unit_id = u.id 
                           AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                       ) THEN 'occupied'
                       ELSE NULL
                   END AS has_active_tenant,
                   COALESCE((
                       SELECT COUNT(*) 
                       FROM inquiries i 
                       WHERE i.unit_id = u.id 
                       AND (i.is_archived IS NULL OR i.is_archived = 0)
                   ), 0) AS inquiries_count
            FROM units u
            WHERE u.property_id = :pid
            ORDER BY COALESCE(u.updated_at, u.created_at) DESC
            """
        ), { 'pid': property_id }).mappings().all()

        def parse_json(value):
            if not value:
                return []
            try:
                import json
                out = json.loads(value)
                return out if isinstance(out, (list, dict)) else []
            except Exception:
                return []

        units = []
        for r in rows:
            # Determine status: preserve 'draft' status, but override to 'occupied' if there's an active tenant
            # Otherwise use the stored status from database
            # IMPORTANT: Don't default to 'vacant' - preserve NULL or empty as-is, only normalize case
            raw_status = r.get('status')
            if raw_status:
                stored_status = str(raw_status).lower().strip()
            else:
                # If status is NULL or empty, default to 'draft' (not 'vacant') for new units
                stored_status = 'draft'
            
            has_active_tenant = r.get('has_active_tenant') == 'occupied'
            
            # If unit has active tenant, it's always occupied (regardless of stored status)
            # Otherwise, preserve the stored status (draft, vacant, maintenance, etc.)
            if has_active_tenant:
                final_status = 'occupied'
            else:
                final_status = stored_status  # Preserve draft, vacant, maintenance, etc.
            
            units.append({
                'id': r.get('id'),
                'name': r.get('unit_name'),
                'unit_name': r.get('unit_name'),
                'status': final_status,  # Use stored status, but override to occupied if tenant exists
                'price': float(r.get('monthly_rent') or 0),
                'size_sqm': r.get('size_sqm'),
                'bedrooms': r.get('bedrooms'),
                'bathrooms': r.get('bathrooms'),
                'description': r.get('description'),
                'security_deposit': float(r.get('security_deposit') or 0),
                'floor_number': r.get('floor_number'),
                'parking_spaces': r.get('parking_spaces'),
                'images': parse_json(r.get('images')),
                'amenities': parse_json(r.get('amenities')),
                'inquiries_count': int(r.get('inquiries_count') or 0),
                'created_at': r.get('created_at').isoformat() if r.get('created_at') else None,
                'updated_at': r.get('updated_at').isoformat() if r.get('updated_at') else None,
            })

        return jsonify({ 'units': units }), 200

    except Exception as e:
        current_app.logger.error(f'List manager units error: {e}')
        return handle_api_error(500, f"Failed to list units: {str(e)}")


@manager_inquiries_bp.route('/units/<int:property_id>', methods=['POST'])
@manager_required
def create_unit(current_user, property_id):
    """Create a new unit for a manager-owned property."""
    try:
        from sqlalchemy import text
        
        # Verify ownership
        ownership_check = db.session.execute(text(
            "SELECT id FROM properties WHERE id = :pid AND owner_id = :uid"
        ), {'pid': property_id, 'uid': current_user.id}).first()
        
        if not ownership_check:
            return handle_api_error(403, "Property not found or access denied")
        
        # Check property's total_units limit if property is approved
        property_info = db.session.execute(text(
            "SELECT total_units, status FROM properties WHERE id = :pid"
        ), {'pid': property_id}).first()
        
        if property_info:
            total_units = property_info.total_units or 0
            property_status = property_info.status or ''
            
            # Only enforce limit for approved properties
            if property_status.lower() in ['approved', 'active'] and total_units > 0:
                # Count existing units for this property
                unit_count_result = db.session.execute(text(
                    "SELECT COUNT(*) AS count FROM units WHERE property_id = :pid"
                ), {'pid': property_id}).first()
                
                existing_unit_count = unit_count_result.count if unit_count_result else 0
                
                # Prevent creating more units than total_units
                if existing_unit_count >= total_units:
                    return handle_api_error(
                        400, 
                        f"Cannot create unit. Property has reached its maximum unit limit of {total_units}. "
                        f"Current unit count: {existing_unit_count}. "
                        f"Please contact support if you need to increase the limit."
                    )
        
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        # Extract unit data
        unit_name = data.get('unitName', '').strip()
        monthly_rent = data.get('monthlyRent', 0)  # Frontend sends monthlyRent, DB column is now 'monthly_rent'
        bedrooms = data.get('bedrooms', 1)
        bathrooms = data.get('bathrooms', 1)
        size_sqm = data.get('sizeSqm', 0)
        description = data.get('description', '').strip()
        security_deposit = data.get('securityDeposit', 0)
        floor_number = data.get('floorNumber', 1)
        parking_spaces = data.get('parkingSpaces', 0)
        # Get status from request, default to 'draft' for new units (not 'vacant')
        # This ensures new units are created as drafts until published
        status = data.get('status', 'draft')
        
        # Log the status being saved for debugging
        current_app.logger.info(f"Creating unit with status: '{status}' (raw from request: {data.get('status')})")
        
        # Validate required fields
        if not unit_name:
            return handle_api_error(400, "Unit name is required")
        
        # Extract images
        images = data.get('images')
        images_json = json.dumps(images) if images else None

        amenities_obj = {}
        if isinstance(data.get('amenities'), dict):
            src = data.get('amenities')
            amenities_obj = {
                'balcony': bool(src.get('balcony', False)),
                'study_area': bool(src.get('studyArea') or src.get('study_area') or False),
                'laundry_area': bool(src.get('laundryArea') or src.get('laundry_area') or False),
                'built_in_cabinets': bool(src.get('builtInCabinets') or src.get('built_in_cabinets') or False),
                'closet_wardrobe': bool(src.get('closetWardrobe') or src.get('closet_wardrobe') or False),
                'air_conditioning': bool(src.get('airConditioning') or src.get('air_conditioning') or False),
                'electric_fan': bool(src.get('electricFan') or src.get('electric_fan') or False),
                'refrigerator': bool(src.get('refrigerator', False)),
                'security_24_7': bool(src.get('security247') or src.get('security_24_7') or False),
                'cctv_camera': bool(src.get('cctvCamera') or src.get('cctv_camera') or False),
                'fire_extinguisher': bool(src.get('fireExtinguisher') or src.get('fire_extinguisher') or False),
                'wifi': bool(src.get('wifi', False))
            }
        else:
            amenities_obj = {
                'balcony': bool(data.get('balcony', False)),
                'study_area': bool(data.get('studyArea', False)),
                'laundry_area': bool(data.get('laundryArea', False)),
                'built_in_cabinets': bool(data.get('builtInCabinets', False)),
                'closet_wardrobe': bool(data.get('closetWardrobe', False)),
                'air_conditioning': bool(data.get('AirConditioning', False) or data.get('airConditioning', False)),
                'electric_fan': bool(data.get('electricFan', False)),
                'refrigerator': bool(data.get('refrigerator', False)),
                'security_24_7': bool(data.get('security247', False)),
                'cctv_camera': bool(data.get('cctvCamera', False)),
                'fire_extinguisher': bool(data.get('fireExtinguisher', False)),
                'wifi': bool(data.get('wifi', False))
            }
        amenities_json = json.dumps(amenities_obj)

        amenities_obj = {}
        amenities_json = json.dumps({})
        if isinstance(data.get('amenities'), dict):
            src = data.get('amenities')
            amenities_obj = {
                'balcony': bool(src.get('balcony', False)),
                'study_area': bool(src.get('studyArea') or src.get('study_area') or False),
                'laundry_area': bool(src.get('laundryArea') or src.get('laundry_area') or False),
                'built_in_cabinets': bool(src.get('builtInCabinets') or src.get('built_in_cabinets') or False),
                'closet_wardrobe': bool(src.get('closetWardrobe') or src.get('closet_wardrobe') or False),
                'air_conditioning': bool(src.get('airConditioning') or src.get('air_conditioning') or False),
                'electric_fan': bool(src.get('electricFan') or src.get('electric_fan') or False),
                'refrigerator': bool(src.get('refrigerator', False)),
                'security_24_7': bool(src.get('security247') or src.get('security_24_7') or False),
                'cctv_camera': bool(src.get('cctvCamera') or src.get('cctv_camera') or False),
                'fire_extinguisher': bool(src.get('fireExtinguisher') or src.get('fire_extinguisher') or False),
                'wifi': bool(src.get('wifi', False))
            }
        else:
            amenities_obj = {
                'balcony': bool(data.get('balcony', False)),
                'study_area': bool(data.get('studyArea', False)),
                'laundry_area': bool(data.get('laundryArea', False)),
                'built_in_cabinets': bool(data.get('builtInCabinets', False)),
                'closet_wardrobe': bool(data.get('closetWardrobe', False)),
                'air_conditioning': bool(data.get('AirConditioning', False) or data.get('airConditioning', False)),
                'electric_fan': bool(data.get('electricFan', False)),
                'refrigerator': bool(data.get('refrigerator', False)),
                'security_24_7': bool(data.get('security247', False)),
                'cctv_camera': bool(data.get('cctvCamera', False)),
                'fire_extinguisher': bool(data.get('fireExtinguisher', False)),
                'wifi': bool(data.get('wifi', False))
            }
        amenities_json = json.dumps(amenities_obj)
        
        amenities_obj = {}
        if isinstance(data.get('amenities'), dict):
            src = data.get('amenities')
            amenities_obj = {
                'balcony': bool(src.get('balcony', False)),
                'study_area': bool(src.get('studyArea') or src.get('study_area') or False),
                'laundry_area': bool(src.get('laundryArea') or src.get('laundry_area') or False),
                'built_in_cabinets': bool(src.get('builtInCabinets') or src.get('built_in_cabinets') or False),
                'closet_wardrobe': bool(src.get('closetWardrobe') or src.get('closet_wardrobe') or False),
                'air_conditioning': bool(src.get('airConditioning') or src.get('air_conditioning') or False),
                'electric_fan': bool(src.get('electricFan') or src.get('electric_fan') or False),
                'refrigerator': bool(src.get('refrigerator', False)),
                'security_24_7': bool(src.get('security247') or src.get('security_24_7') or False),
                'cctv_camera': bool(src.get('cctvCamera') or src.get('cctv_camera') or False),
                'fire_extinguisher': bool(src.get('fireExtinguisher') or src.get('fire_extinguisher') or False),
                'wifi': bool(src.get('wifi', False))
            }
        else:
            amenities_obj = {
                'balcony': bool(data.get('balcony', False)),
                'study_area': bool(data.get('studyArea', False)),
                'laundry_area': bool(data.get('laundryArea', False)),
                'built_in_cabinets': bool(data.get('builtInCabinets', False)),
                'closet_wardrobe': bool(data.get('closetWardrobe', False)),
                'air_conditioning': bool(data.get('AirConditioning', False) or data.get('airConditioning', False)),
                'electric_fan': bool(data.get('electricFan', False)),
                'refrigerator': bool(data.get('refrigerator', False)),
                'security_24_7': bool(data.get('security247', False)),
                'cctv_camera': bool(data.get('cctvCamera', False)),
                'fire_extinguisher': bool(data.get('fireExtinguisher', False)),
                'wifi': bool(data.get('wifi', False))
            }
        amenities_json = json.dumps(amenities_obj)
        
        amenities_obj = {}
        if isinstance(data.get('amenities'), dict):
            amenities_src = data.get('amenities')
            amenities_obj = {
                'balcony': bool(amenities_src.get('balcony', False)),
                'study_area': bool(amenities_src.get('studyArea') or amenities_src.get('study_area') or False),
                'laundry_area': bool(amenities_src.get('laundryArea') or amenities_src.get('laundry_area') or False),
                'built_in_cabinets': bool(amenities_src.get('builtInCabinets') or amenities_src.get('built_in_cabinets') or False),
                'closet_wardrobe': bool(amenities_src.get('closetWardrobe') or amenities_src.get('closet_wardrobe') or False),
                'air_conditioning': bool(amenities_src.get('airConditioning') or amenities_src.get('air_conditioning') or False),
                'electric_fan': bool(amenities_src.get('electricFan') or amenities_src.get('electric_fan') or False),
                'refrigerator': bool(amenities_src.get('refrigerator', False)),
                'security_24_7': bool(amenities_src.get('security247') or amenities_src.get('security_24_7') or False),
                'cctv_camera': bool(amenities_src.get('cctvCamera') or amenities_src.get('cctv_camera') or False),
                'fire_extinguisher': bool(amenities_src.get('fireExtinguisher') or amenities_src.get('fire_extinguisher') or False),
                'wifi': bool(amenities_src.get('wifi', False))
            }
        else:
            amenities_obj = {
                'balcony': bool(data.get('balcony', False)),
                'study_area': bool(data.get('studyArea', False)),
                'laundry_area': bool(data.get('laundryArea', False)),
                'built_in_cabinets': bool(data.get('BuiltInCabinets', False) or data.get('builtInCabinets', False)),
                'closet_wardrobe': bool(data.get('closetWardrobe', False)),
                'air_conditioning': bool(data.get('AirConditioning', False) or data.get('airConditioning', False)),
                'electric_fan': bool(data.get('electricFan', False)),
                'refrigerator': bool(data.get('refrigerator', False)),
                'security_24_7': bool(data.get('security247', False)),
                'cctv_camera': bool(data.get('cctvCamera', False)),
                'fire_extinguisher': bool(data.get('FireExtinguisher', False) or data.get('fireExtinguisher', False)),
                'wifi': bool(data.get('wifi', False))
            }
        amenities_json = json.dumps(amenities_obj)
        
        # Insert new unit
        insert_sql = text("""
            INSERT INTO units (
                property_id, unit_name, monthly_rent, bedrooms, bathrooms, 
                size_sqm, description, security_deposit, floor_number, 
                parking_spaces, status, images, amenities, created_at, updated_at
            ) VALUES (
                :property_id, :unit_name, :monthly_rent, :bedrooms, :bathrooms,
                :size_sqm, :description, :security_deposit, :floor_number,
                :parking_spaces, :status, :images, :amenities, NOW(), NOW()
            )
        """)
        
        result = db.session.execute(insert_sql, {
            'property_id': property_id,
            'unit_name': unit_name,
            'monthly_rent': monthly_rent,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'size_sqm': size_sqm,
            'description': description,
            'security_deposit': security_deposit,
            'floor_number': floor_number,
            'parking_spaces': parking_spaces,
            'status': status,
            'images': images_json,
            'amenities': amenities_json,
        })
        
        db.session.commit()
        
        # Get the created unit ID
        unit_id = result.lastrowid
        
        # Verify what was actually saved to database
        saved_unit = db.session.execute(text(
            "SELECT id, status FROM units WHERE id = :uid"
        ), {'uid': unit_id}).first()
        if saved_unit:
            current_app.logger.info(f"Unit {unit_id} saved with status: '{saved_unit.status}' (expected: '{status}')")
            # If status doesn't match, it means the database rejected 'draft' value
            if str(saved_unit.status).lower() != str(status).lower():
                current_app.logger.warning(f"Status mismatch! Sent '{status}' but database saved '{saved_unit.status}'. Database may not accept 'draft' status.")
        
        # Return the created unit
        return jsonify({
            'message': 'Unit created successfully',
            'item': {
                'id': unit_id,
                'unit_name': unit_name,
                'monthly_rent': monthly_rent,
                'bedrooms': bedrooms,
                'bathrooms': bathrooms,
                'size_sqm': size_sqm,
                'description': description,
                'security_deposit': security_deposit,
                'floor_number': floor_number,
                'parking_spaces': parking_spaces,
                'status': status,
                'property_id': property_id,
                'images': images or [],
                'amenities': amenities_obj,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Create unit error: {e}')
        return handle_api_error(500, f"Failed to create unit: {str(e)}")


@manager_inquiries_bp.route('/units/<int:unit_id>', methods=['PUT'])
@manager_required
def update_unit(current_user, unit_id):
    """Update an existing unit."""
    try:
        from sqlalchemy import text
        
        # Verify ownership through property
        ownership_check = db.session.execute(text("""
            SELECT u.id FROM units u
            INNER JOIN properties p ON u.property_id = p.id
            WHERE u.id = :uid AND p.owner_id = :owner_id
        """), {'uid': unit_id, 'owner_id': current_user.id}).first()
        
        if not ownership_check:
            return handle_api_error(403, "Unit not found or access denied")
        
        data = request.get_json()
        current_app.logger.info(f"=== UPDATE UNIT {unit_id} ===")
        current_app.logger.info(f"Received data: {data}")
        
        if not data:
            return handle_api_error(400, "No data provided")
        
        # Extract unit data
        unit_name = data.get('unitName', '').strip()
        monthly_rent = data.get('monthlyRent', 0)
        bedrooms = data.get('bedrooms', 1)
        bathrooms = data.get('bathrooms', 1)
        size_sqm = data.get('sizeSqm', 0)
        description = data.get('description', '').strip()
        security_deposit = data.get('securityDeposit', 0)
        floor_number = data.get('floorNumber', 1)
        parking_spaces = data.get('parkingSpaces', 0)
        # For updates, preserve existing status if not provided, but allow status changes
        # Default to 'draft' if status is not provided (same as create)
        status = data.get('status', 'draft')
        
        # Validate required fields
        if not unit_name:
            return handle_api_error(400, "Unit name is required")
        
        # Extract images
        images = data.get('images')
        images_json = json.dumps(images) if images else None

        if isinstance(data.get('amenities'), dict):
            _a = data.get('amenities')
            amenities_obj = {
                'balcony': bool(_a.get('balcony', False)),
                'study_area': bool(_a.get('studyArea') or _a.get('study_area') or False),
                'laundry_area': bool(_a.get('laundryArea') or _a.get('laundry_area') or False),
                'built_in_cabinets': bool(_a.get('builtInCabinets') or _a.get('built_in_cabinets') or False),
                'closet_wardrobe': bool(_a.get('closetWardrobe') or _a.get('closet_wardrobe') or False),
                'air_conditioning': bool(_a.get('airConditioning') or _a.get('air_conditioning') or False),
                'electric_fan': bool(_a.get('electricFan') or _a.get('electric_fan') or False),
                'refrigerator': bool(_a.get('refrigerator', False)),
                'security_24_7': bool(_a.get('security247') or _a.get('security_24_7') or False),
                'cctv_camera': bool(_a.get('cctvCamera') or _a.get('cctv_camera') or False),
                'fire_extinguisher': bool(_a.get('fireExtinguisher') or _a.get('fire_extinguisher') or False),
                'wifi': bool(_a.get('wifi', False))
            }
        else:
            amenities_obj = {
                'balcony': bool(data.get('balcony', False)),
                'study_area': bool(data.get('studyArea', False)),
                'laundry_area': bool(data.get('laundryArea', False)),
                'built_in_cabinets': bool(data.get('BuiltInCabinets', False) or data.get('builtInCabinets', False)),
                'closet_wardrobe': bool(data.get('closetWardrobe', False)),
                'air_conditioning': bool(data.get('AirConditioning', False) or data.get('airConditioning', False)),
                'electric_fan': bool(data.get('electricFan', False)),
                'refrigerator': bool(data.get('refrigerator', False)),
                'security_24_7': bool(data.get('security247', False)),
                'cctv_camera': bool(data.get('cctvCamera', False)),
                'fire_extinguisher': bool(data.get('FireExtinguisher', False) or data.get('fireExtinguisher', False)),
                'wifi': bool(data.get('wifi', False))
            }
        amenities_json = json.dumps(amenities_obj)

        # Update unit
        update_sql = text("""
            UPDATE units SET
                unit_name = :unit_name,
                monthly_rent = :monthly_rent,
                bedrooms = :bedrooms,
                bathrooms = :bathrooms,
                size_sqm = :size_sqm,
                description = :description,
                security_deposit = :security_deposit,
                floor_number = :floor_number,
                parking_spaces = :parking_spaces,
                status = :status,
                images = :images,
                amenities = :amenities,
                updated_at = NOW()
            WHERE id = :unit_id
        """)
        
        db.session.execute(update_sql, {
            'unit_id': unit_id,
            'unit_name': unit_name,
            'monthly_rent': monthly_rent,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'size_sqm': size_sqm,
            'description': description,
            'security_deposit': security_deposit,
            'floor_number': floor_number,
            'parking_spaces': parking_spaces,
            'status': status,
            'images': images_json,
            'amenities': amenities_json,
        })
        
        current_app.logger.info(f"Executing UPDATE query for unit {unit_id}")
        current_app.logger.info(f"New monthly_rent: {monthly_rent}")
        db.session.commit()
        current_app.logger.info(f"UPDATE committed successfully")
        
        return jsonify({
            'message': 'Unit updated successfully',
            'item': {
                'id': unit_id,
                'unit_name': unit_name,
                'monthly_rent': monthly_rent,
                'bedrooms': bedrooms,
                'bathrooms': bathrooms,
                'size_sqm': size_sqm,
                'description': description,
                'security_deposit': security_deposit,
                'floor_number': floor_number,
                'parking_spaces': parking_spaces,
                'status': status,
                'images': images or [],
                'amenities': amenities_obj,
                'updated_at': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Update unit error: {e}')
        return handle_api_error(500, f"Failed to update unit: {str(e)}")


@manager_inquiries_bp.route('/units/<int:unit_id>', methods=['DELETE'])
@manager_required
def delete_unit(current_user, unit_id):
    """Delete a unit."""
    try:
        from sqlalchemy import text
        
        # Verify ownership through property
        ownership_check = db.session.execute(text("""
            SELECT u.id FROM units u
            INNER JOIN properties p ON u.property_id = p.id
            WHERE u.id = :uid AND p.owner_id = :owner_id
        """), {'uid': unit_id, 'owner_id': current_user.id}).first()
        
        if not ownership_check:
            return handle_api_error(403, "Unit not found or access denied")
        
        # Delete the unit
        delete_sql = text("DELETE FROM units WHERE id = :unit_id")
        db.session.execute(delete_sql, {'unit_id': unit_id})
        db.session.commit()
        
        return jsonify({'message': 'Unit deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Delete unit error: {e}')
        return handle_api_error(500, f"Failed to delete unit: {str(e)}")


@manager_inquiries_bp.route('/<int:inquiry_id>/status', methods=['PUT'])
@manager_required
def update_inquiry_status(current_user, inquiry_id):
    try:
        data = request.get_json()
        new_status = data.get('status')
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
            
        inquiry = Inquiry.query.get_or_404(inquiry_id)
        if inquiry.property_manager_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Update status
        inquiry.status = InquiryStatus(new_status)
        db.session.commit()
        
        return jsonify({
            'message': 'Status updated successfully',
            'inquiry': inquiry.to_dict()
        }), 200
    except ValueError:
        return jsonify({'error': 'Invalid status'}), 400
    except Exception as e:
        db.session.rollback()
        print(f'Error updating status: {str(e)}')
        return jsonify({'error': 'Failed to update status'}), 500

@manager_inquiries_bp.route('/<int:inquiry_id>/viewing', methods=['POST', 'PUT'])
@manager_required
def schedule_viewing(current_user, inquiry_id):
    from app.models.inquiry import ViewingSchedule
    try:
        data = request.get_json()
        scheduled_at_str = data.get('scheduled_at')
        if not scheduled_at_str:
            return jsonify({'error': 'Scheduled time is required'}), 400
            
        inquiry = Inquiry.query.get_or_404(inquiry_id)
        if inquiry.property_manager_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
        
        # Check if schedule exists
        schedule = ViewingSchedule.query.filter_by(inquiry_id=inquiry_id).first()
        if schedule:
            schedule.scheduled_at = scheduled_at
            schedule.status = data.get('status', 'scheduled')
        else:
            schedule = ViewingSchedule(
                inquiry_id=inquiry_id,
                scheduled_at=scheduled_at
            )
            db.session.add(schedule)
            
        # Also update inquiry status to VIEWING_SCHEDULED if it is pending/read
        if inquiry.status in [InquiryStatus.PENDING, InquiryStatus.READ]:
            inquiry.status = InquiryStatus.VIEWING_SCHEDULED
            
        db.session.commit()
        
        return jsonify({
            'message': 'Viewing scheduled successfully',
            'inquiry_status': str(inquiry.status.value)
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f'Error scheduling viewing: {str(e)}')
        return jsonify({'error': 'Failed to schedule viewing'}), 500
