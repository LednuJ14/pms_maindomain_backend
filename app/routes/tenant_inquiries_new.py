"""
Simplified Tenant Inquiries API Routes
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
from app.models.property import Property
from app.models.inquiry import Inquiry, InquiryStatus, InquiryType
from app.utils.decorators import auth_required, tenant_required
from app.utils.error_handlers import handle_api_error

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

tenant_inquiries_bp = Blueprint('tenant_inquiries', __name__)

@tenant_inquiries_bp.route('/', methods=['GET'])
@tenant_required
def get_tenant_inquiries(current_user):
    """
    Get tenant inquiries
    ---
    tags:
      - Tenant Inquiries
    summary: Get all inquiries created by the tenant
    description: Retrieve all inquiries created by the authenticated tenant
    security:
      - Bearer: []
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
                  status:
                    type: string
                  messages:
                    type: array
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        from sqlalchemy import text
        rows = db.session.execute(text(
            """
            SELECT DISTINCT i.id, i.property_id, i.unit_id, i.tenant_id, i.property_manager_id,
                   i.inquiry_type, i.status, i.message,
                   i.created_at, i.updated_at, i.read_at,
                   COALESCE(u.unit_name, p.title, p.building_name) AS unit_name
            FROM inquiries i
            LEFT JOIN units u ON u.id = i.unit_id
            LEFT JOIN properties p ON p.id = i.property_id
            WHERE i.tenant_id = :tid
              AND (i.is_archived IS NULL OR i.is_archived = 0)
            ORDER BY i.created_at DESC
            """
        ), { 'tid': current_user.id }).mappings().all()
        
        # Additional deduplication by ID in case DISTINCT doesn't catch everything
        seen_ids = set()
        unique_rows = []
        for row in rows:
            row_id = row.get('id')
            if row_id and row_id not in seen_ids:
                seen_ids.add(row_id)
                unique_rows.append(row)
        
        inquiry_data = []
        for inquiry in unique_rows:
            # Get property info
            prop_row = db.session.execute(text(
                "SELECT id, title, building_name, address, city, province FROM properties WHERE id = :pid"
            ), { 'pid': inquiry.get('property_id') }).mappings().first()
            property_data = {
                'id': prop_row.get('id') if prop_row else None,
                'title': (prop_row.get('title') if prop_row else None) or 'Unknown Property',
                'building_name': prop_row.get('building_name') if prop_row else None,
                'address': prop_row.get('address') if prop_row else None,
                'city': prop_row.get('city') if prop_row else None,
                'province': prop_row.get('province') if prop_row else None
            } if prop_row else None
            
            # Get manager info
            manager_info = User.query.get(inquiry.get('property_manager_id'))
            manager_data = {
                'id': manager_info.id if manager_info else None,
                'first_name': manager_info.first_name if manager_info else 'Property',
                'last_name': manager_info.last_name if manager_info else 'Manager',
                'email': manager_info.email if manager_info else None
            } if manager_info else None
            
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
            tenant_id = inquiry.get('tenant_id')
            for msg_row in message_rows:
                # Determine if sender is tenant or manager
                sender_id = msg_row.get('sender_id')
                # Compare as integers to ensure proper comparison
                is_manager = int(sender_id) == int(property_manager_id) if sender_id and property_manager_id else False
                is_tenant = int(sender_id) == int(tenant_id) if sender_id and tenant_id else False
                messages_list.append({
                    'id': msg_row.get('id'),
                    'inquiry_id': msg_row.get('inquiry_id'),
                    'sender_id': sender_id,
                    'sender': 'manager' if is_manager else ('tenant' if is_tenant else 'unknown'),
                    'message': msg_row.get('message'),
                    'text': msg_row.get('message'),  # Add 'text' alias for frontend compatibility
                    'is_read': bool(msg_row.get('is_read')),
                    'created_at': safe_isoformat(msg_row.get('created_at'))
                })
            
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
                'read_at': safe_isoformat(inquiry.get('read_at')),
                'unit_name': inquiry.get('unit_name'),
                'property': property_data,
                'property_manager': manager_data
            }
            
            inquiry_data.append(inquiry_dict)
        
        return jsonify({
            'inquiries': inquiry_data
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get tenant inquiries error: {e}')
        return handle_api_error(500, f"Failed to retrieve inquiries: {str(e)}")

@tenant_inquiries_bp.route('/start', methods=['POST'])
@tenant_required
def start_inquiry(current_user):
    """
    Start new inquiry
    ---
    tags:
      - Tenant Inquiries
    summary: Start a new inquiry for a property
    description: Create a new inquiry for a property or specific unit
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - property_id
            - message
          properties:
            property_id:
              type: integer
            unit_id:
              type: integer
              description: Optional specific unit ID
            message:
              type: string
    responses:
      200:
        description: Inquiry created or existing inquiry returned
        schema:
          type: object
          properties:
            inquiry:
              type: object
      201:
        description: New inquiry created
      400:
        description: Validation error
      401:
        description: Unauthorized
      404:
        description: Property not found
      500:
        description: Server error
    """
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        property_id = data.get('property_id')
        unit_id = data.get('unit_id')  # Optional: specific unit inquiry
        message = data.get('message', '').strip()
        
        if not property_id or not message:
            return handle_api_error(400, "Property ID and message are required")
        
        # Get the property using a minimal raw SELECT to avoid ORM column mismatches
        from sqlalchemy import text
        prop_row = db.session.execute(text(
            """
            SELECT id, title, building_name, address, city, province,
                   contact_email, contact_phone, owner_id, status, monthly_rent
            FROM properties
            WHERE id = :pid
            """
        ), { 'pid': property_id }).mappings().first()
        if not prop_row:
            return handle_api_error(404, "Property not found")
        
        # If an open inquiry already exists for this tenant+property+unit, return it instead of creating duplicates
        from sqlalchemy import text
        existing = db.session.execute(text(
            """
            SELECT id, property_id, unit_id, tenant_id, property_manager_id,
                   inquiry_type, status, message,
                   created_at
            FROM inquiries
            WHERE tenant_id = :tid AND property_id = :pid 
            AND (unit_id = :uid OR (unit_id IS NULL AND :uid IS NULL))
            AND (is_archived IS NULL OR is_archived = 0)
            ORDER BY created_at DESC
            LIMIT 1
            """
        ), { 'tid': current_user.id, 'pid': property_id, 'uid': unit_id }).mappings().first()
        if existing:
            # Get unit name if unit_id exists
            unit_name = None
            if existing.get('unit_id'):
                unit_row = db.session.execute(text(
                    "SELECT unit_name FROM units WHERE id = :uid"
                ), { 'uid': existing.get('unit_id') }).mappings().first()
                unit_name = unit_row.get('unit_name') if unit_row else None
            
            inquiry_dict = {
                'id': existing.get('id'),
                'property_id': existing.get('property_id'),
                'unit_id': existing.get('unit_id'),
                'tenant_id': existing.get('tenant_id'),
                'property_manager_id': existing.get('property_manager_id'),
                'inquiry_type': str(existing.get('inquiry_type')).lower() if existing.get('inquiry_type') else 'rental_inquiry',
                'status': str(existing.get('status')).lower() if existing.get('status') else 'pending',
                'message': existing.get('message'),
                'tenant': {
                    'id': existing.get('tenant_id'),
                    'name': current_user.get_full_name(),
                    'email': current_user.email,
                    'phone': getattr(current_user, 'phone_number', None)
                },
                'created_at': existing.get('created_at').isoformat() if existing.get('created_at') else None,
                'unit_name': unit_name,
                'property': {
                    'id': prop_row.get('id'),
                    'title': prop_row.get('title') or prop_row.get('building_name') or 'Property',
                    'building_name': prop_row.get('building_name'),
                    'address': prop_row.get('address'),
                    'city': prop_row.get('city'),
                    'province': prop_row.get('province')
                },
                'property_manager': {
                    'id': prop_row.get('owner_id'),
                    'first_name': 'Property',
                    'last_name': 'Manager',
                    'email': prop_row.get('contact_email')
                }
            }
            return jsonify({ 'message': 'Inquiry already exists', 'inquiry': inquiry_dict }), 200

        # Create the inquiry using raw SQL to avoid enum value mismatch issues
        
        from time import time as _time
        init_ts_ms = int(_time() * 1000)
        # Store the first tenant message with its real send timestamp marker
        initial_payload = f"--- New Message [{init_ts_ms}] ---\n{message}"

        params = {
            'pid': property_id,
            'uid': unit_id,  # unit_id can be NULL
            'tid': current_user.id,
            'mid': prop_row.get('owner_id'),
            'itype': 'rental_inquiry',  # lowercase to match enum values
            'status': 'pending',
            'message': initial_payload
        }
        try:
            result = db.session.execute(text(
                """
                INSERT INTO inquiries (
                  property_id, unit_id, tenant_id, property_manager_id,
                  inquiry_type, status, message,
                  created_at, updated_at
                ) VALUES (
                  :pid, :uid, :tid, :mid,
                  :itype, :status, :message,
                  NOW(), NOW()
                )
                """
            ), params)
            db.session.commit()
            new_id = result.lastrowid or db.session.execute(text('SELECT LAST_INSERT_ID()')).scalar()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error creating inquiry: {str(e)}")
            return handle_api_error(500, "Failed to create inquiry")
        
        # Get unit name if unit_id exists
        unit_name = None
        if unit_id:
            unit_row = db.session.execute(text(
                "SELECT unit_name FROM units WHERE id = :uid"
            ), { 'uid': unit_id }).mappings().first()
            unit_name = unit_row.get('unit_name') if unit_row else None
        
        # Notify property manager about new inquiry
        try:
            from app.services.notification_service import NotificationService
            property_name = prop_row.get('title') or prop_row.get('building_name') or 'Property'
            tenant_name = current_user.get_full_name() or current_user.email
            NotificationService.notify_new_inquiry(
                manager_id=prop_row.get('owner_id'),
                inquiry_id=int(new_id),
                tenant_name=tenant_name,
                property_name=property_name,
                unit_name=unit_name
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send notification to property manager: {str(e)}")
            # Don't fail the inquiry creation if notification fails
        
        # Return the created inquiry
        inquiry_dict = {
            'id': int(new_id),
            'property_id': int(property_id),
            'unit_id': int(unit_id) if unit_id else None,
            'tenant_id': int(current_user.id),
            'property_manager_id': int(prop_row.get('owner_id')) if prop_row.get('owner_id') is not None else None,
            'inquiry_type': 'rental_inquiry',
            'status': 'pending',
            'message': message,
            'tenant': {
                'id': current_user.id,
                'name': current_user.get_full_name(),
                'email': current_user.email,
                'phone': getattr(current_user, 'phone_number', None)
            },
            'created_at': datetime.utcnow().isoformat(),
            'unit_name': unit_name,
            'property': {
                'id': prop_row.get('id'),
                'title': prop_row.get('title') or prop_row.get('building_name') or 'Property',
                'building_name': prop_row.get('building_name'),
                'address': prop_row.get('address'),
                'city': prop_row.get('city'),
                'province': prop_row.get('province')
            },
            'property_manager': {
                'id': prop_row.get('owner_id'),
                'first_name': 'Property',
                'last_name': 'Manager',
                'email': prop_row.get('contact_email')
            }
        }
        
        return jsonify({
            'message': 'Inquiry created successfully',
            'inquiry': inquiry_dict
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Start inquiry error: {e}')
        return handle_api_error(500, f"Failed to create inquiry: {str(e)}")

@tenant_inquiries_bp.route('/send-message', methods=['POST'])
@tenant_required
def send_message(current_user):
    """
    Send message in inquiry
    ---
    tags:
      - Tenant Inquiries
    summary: Send a message in an existing inquiry
    description: Send a message response in an existing inquiry conversation
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
            message:
              type: string
    responses:
      200:
        description: Message sent successfully
        schema:
          type: object
          properties:
            message:
              type: string
            success:
              type: boolean
      400:
        description: Validation error
      401:
        description: Unauthorized
      403:
        description: Forbidden - Not your inquiry
      404:
        description: Inquiry not found
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
        # Validate inquiry ownership
        row = db.session.execute(text(
            "SELECT id, tenant_id FROM inquiries WHERE id = :iid"
        ), { 'iid': inquiry_id }).mappings().first()
        if not row:
            return handle_api_error(404, "Inquiry not found")
        if int(row.get('tenant_id')) != int(current_user.id):
            return handle_api_error(403, "You can only send messages to your own inquiries")

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
            
            # Update inquiry updated_at timestamp
            db.session.execute(text(
                "UPDATE inquiries SET updated_at = NOW() WHERE id = :iid"
            ), { 'iid': inquiry_id })
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error creating message: {str(e)}")
            return handle_api_error(500, "Failed to send message")
        
        return jsonify({ 'success': True }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Send message error: {e}')
        return handle_api_error(500, f"Failed to send message: {str(e)}")

@tenant_inquiries_bp.route('/<int:inquiry_id>', methods=['GET'])
@tenant_required
def get_inquiry_details(current_user, inquiry_id):
    """
    Get inquiry details
    ---
    tags:
      - Tenant Inquiries
    summary: Get detailed information about a specific inquiry
    description: Retrieve detailed information about a specific inquiry including all messages and property details
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
        description: Inquiry details retrieved successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            property_id:
              type: integer
            status:
              type: string
            messages:
              type: array
      401:
        description: Unauthorized
      403:
        description: Forbidden - Not your inquiry
      404:
        description: Inquiry not found
      500:
        description: Server error
    """
    try:
        inquiry = Inquiry.query.get(inquiry_id)
        if not inquiry:
            return handle_api_error(404, "Inquiry not found")
        
        # Check if the inquiry belongs to the current user
        if inquiry.tenant_id != current_user.id:
            return handle_api_error(403, "You can only view your own inquiries")
        
        # Get property and manager info
        property_info = Property.query.get(inquiry.property_id)
        manager_info = User.query.get(inquiry.property_manager_id)
        
        inquiry_dict = {
            'id': inquiry.id,
            'property_id': inquiry.property_id,
            'tenant_id': inquiry.tenant_id,
            'property_manager_id': inquiry.property_manager_id,
            'inquiry_type': inquiry.inquiry_type.value if inquiry.inquiry_type else 'rental_inquiry',
            'status': inquiry.status.value if inquiry.status else 'pending',
            'subject': inquiry.subject,
            'message': inquiry.message,
            'tenant_name': inquiry.tenant_name,
            'tenant_email': inquiry.tenant_email,
            'tenant_phone': inquiry.tenant_phone,
            'response_message': inquiry.response_message,
            'responded_at': inquiry.responded_at.isoformat() if inquiry.responded_at else None,
            'created_at': inquiry.created_at.isoformat() if inquiry.created_at else None,
            'updated_at': inquiry.updated_at.isoformat() if inquiry.updated_at else None,
            'property': {
                'id': property_info.id if property_info else None,
                'title': property_info.title if property_info else 'Unknown Property',
                'building_name': property_info.building_name if property_info else None,
                'address': property_info.address if property_info else None,
                'city': property_info.city if property_info else None,
                'province': property_info.province if property_info else None
            } if property_info else None,
            'property_manager': {
                'id': manager_info.id if manager_info else None,
                'first_name': manager_info.first_name if manager_info else 'Property',
                'last_name': manager_info.last_name if manager_info else 'Manager',
                'email': manager_info.email if manager_info else None
            } if manager_info else None
        }
        
        return jsonify({
            'inquiry': inquiry_dict
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get inquiry details error: {e}')
        return handle_api_error(500, f"Failed to retrieve inquiry details: {str(e)}")
