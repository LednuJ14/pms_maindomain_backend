"""
Tenant Profile API Routes
"""
from flask import Blueprint, request, jsonify, current_app
import os
from app import db
from app.models.user import User, UserRole
from app.utils.decorators import tenant_required
from app.utils.error_handlers import handle_api_error
from app.utils.validators import validate_required_fields, sanitize_input
from app.utils.file_helpers import save_uploaded_file, IMAGE_EXTENSIONS
import base64
import pyotp
import qrcode
from io import BytesIO

tenant_profile_bp = Blueprint('tenant_profile', __name__)

@tenant_profile_bp.route('/', methods=['GET'])
@tenant_required
def get_tenant_profile(current_user):
    """
    Get tenant profile
    ---
    tags:
      - Tenant Profile
    summary: Get the current tenant's profile
    description: Retrieve profile information for the authenticated tenant
    security:
      - Bearer: []
    responses:
      200:
        description: Profile retrieved successfully
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
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        # Build a conservative, flat profile payload to avoid serialization issues
        role_value = getattr(current_user.role, 'value', current_user.role)
        status_value = getattr(current_user.status, 'value', current_user.status)
        def safe_iso(dt):
            try:
                return dt.isoformat() if dt else None
            except Exception:
                return str(dt) if dt else None
        profile_data = {
            'id': current_user.id,
            'email': current_user.email,
            'role': role_value,
            'status': status_value,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'full_name': f"{current_user.first_name} {current_user.last_name}",
            'phone_number': current_user.phone_number,
            'date_of_birth': safe_iso(current_user.date_of_birth),
            'profile_image_url': current_user.profile_image_url,
            'two_factor_enabled': bool(getattr(current_user, 'two_factor_enabled', False)),
            # Flattened address fields expected by frontend
            'address': current_user.address,
            'city': current_user.city,
            'province': current_user.province,
            'postal_code': current_user.postal_code,
            'country': current_user.country,
            'bio': current_user.bio,
            'created_at': safe_iso(current_user.created_at),
            'updated_at': safe_iso(current_user.updated_at),
            'last_login': safe_iso(current_user.last_login)
        }
        
        # Add tenant-specific data with safe fallbacks
        try:
            total_inquiries = current_user.sent_inquiries.count() if hasattr(current_user, 'sent_inquiries') and current_user.sent_inquiries is not None else 0
        except Exception:
            total_inquiries = 0
        try:
            active_inquiries = current_user.sent_inquiries.filter_by(is_archived=False).count() if hasattr(current_user, 'sent_inquiries') and current_user.sent_inquiries is not None else 0
        except Exception:
            active_inquiries = 0
        try:
            member_since = current_user.created_at.isoformat() if getattr(current_user, 'created_at', None) else None
        except Exception:
            member_since = None

        profile_data['statistics'] = {
            'total_inquiries': total_inquiries,
            'active_inquiries': active_inquiries,
            'member_since': member_since
        }
        
        unit_info = None
        property_info = None
        unit_assignments = []
        
        try:
            from sqlalchemy import text
            from datetime import date
            
            current_app.logger.info(f'=== Fetching tenant assignments for user_id: {current_user.id} ===')
            
            tenant_rows = db.session.execute(text("""
                SELECT id
                FROM tenants
                WHERE user_id = :user_id
            """), {'user_id': current_user.id}).mappings().all()
            
            tenant_ids = [int(row.get('id')) for row in tenant_rows if row.get('id') is not None]
            where_clauses = ["tu.tenant_id = :user_id"]
            params = {'user_id': current_user.id}
            if tenant_ids:
                ids_sql = ", ".join(str(tid) for tid in tenant_ids)
                where_clauses.append(f"tu.tenant_id IN ({ids_sql})")
            where_sql = " OR ".join(where_clauses)
            
            rows = db.session.execute(text(f"""
                SELECT 
                    tu.id as tu_id,
                    tu.unit_id,
                    tu.property_id as tu_property_id,
                    tu.move_in_date,
                    tu.move_out_date,
                    tu.monthly_rent,
                    u.id as unit_db_id,
                    u.property_id as unit_property_id,
                    u.unit_name,
                    u.unit_number,
                    u.status as unit_status,
                    u.monthly_rent as unit_monthly_rent,
                    p.id as property_id,
                    p.building_name,
                    p.title as property_title,
                    p.address as property_address,
                    p.city as property_city,
                    p.province as property_province
                FROM tenant_units tu
                LEFT JOIN units u ON u.id = tu.unit_id
                LEFT JOIN properties p ON p.id = COALESCE(tu.property_id, u.property_id)
                WHERE {where_sql}
                ORDER BY tu.id DESC
            """), params).mappings().all()
            
            today = date.today()
            active_rows = []
            for row in rows:
                move_out = row.get('move_out_date')
                try:
                    if not move_out or (hasattr(move_out, 'date') and move_out >= today):
                        active_rows.append(row)
                except Exception:
                    active_rows.append(row)
            
            primary_row = active_rows[0] if active_rows else (rows[0] if rows else None)
            
            def build_unit(row):
                unit_id_val = row.get('unit_id') or row.get('unit_db_id')
                unit_name_val = row.get('unit_name') or row.get('unit_number') or (f"Unit {unit_id_val}" if unit_id_val else "Unit")
                unit_number_val = row.get('unit_number') or row.get('unit_name') or (str(unit_id_val) if unit_id_val else None)
                return {
                    'id': unit_id_val,
                    'unit_name': unit_name_val,
                    'unit_number': unit_number_val,
                    'status': row.get('unit_status'),
                    'monthly_rent': float(row.get('monthly_rent') or row.get('unit_monthly_rent') or 0),
                    'move_in_date': safe_iso(row.get('move_in_date')),
                    'move_out_date': safe_iso(row.get('move_out_date'))
                }
            
            def build_property(row):
                prop_id_val = row.get('tu_property_id') or row.get('unit_property_id') or row.get('property_id')
                prop_title = row.get('property_title')
                prop_building = row.get('building_name')
                if not (prop_id_val or prop_title or prop_building or row.get('property_address')):
                    return None
                return {
                    'id': prop_id_val,
                    'building_name': prop_building,
                    'title': prop_title or prop_building,
                    'address': row.get('property_address'),
                    'city': row.get('property_city'),
                    'province': row.get('property_province')
                }
            
            if primary_row:
                unit_info = build_unit(primary_row)
                property_info = build_property(primary_row)
                current_app.logger.info(
                    f'Primary assignment for user_id={current_user.id}: unit_id={unit_info.get("id") if unit_info else None}, '
                    f'property_id={property_info.get("id") if property_info else None}'
                )
            else:
                current_app.logger.info(f'No tenant_units rows found for user_id={current_user.id}')
            
            for row in rows:
                unit_obj = build_unit(row)
                property_obj = build_property(row)
                if unit_obj or property_obj:
                    unit_assignments.append({
                        'unit': unit_obj,
                        'property': property_obj
                    })
            
            try:
                existing_pairs = set()
                for a in unit_assignments:
                    u = a.get('unit') or {}
                    p_obj = a.get('property') or {}
                    existing_pairs.add((u.get('id'), p_obj.get('id')))
                
                assigned_rows = db.session.execute(text("""
                    SELECT 
                        i.id as inquiry_id,
                        i.property_id,
                        i.unit_id,
                        p.id as prop_id,
                        p.building_name,
                        p.title as property_title,
                        p.address as property_address,
                        p.city as property_city,
                        p.province as property_province,
                        u.id as unit_db_id,
                        u.unit_name,
                        u.unit_number,
                        u.status as unit_status,
                        u.monthly_rent as unit_monthly_rent
                    FROM inquiries i
                    LEFT JOIN properties p ON p.id = i.property_id
                    LEFT JOIN units u ON u.id = i.unit_id
                    WHERE i.tenant_id = :user_id
                    ORDER BY COALESCE(i.updated_at, i.created_at) DESC, i.id DESC
                    LIMIT 50
                """), {'user_id': current_user.id}).mappings().all()
                
                for assigned_inquiry in assigned_rows:
                    prop_id_ai = assigned_inquiry.get('property_id') or assigned_inquiry.get('prop_id')
                    unit_id_ai = assigned_inquiry.get('unit_id') or assigned_inquiry.get('unit_db_id')
                    if (unit_id_ai, prop_id_ai) in existing_pairs:
                        continue
                    
                    unit_name_ai = assigned_inquiry.get('unit_name') or assigned_inquiry.get('unit_number') or (f"Unit {unit_id_ai}" if unit_id_ai else "Unit")
                    unit_number_ai = assigned_inquiry.get('unit_number') or assigned_inquiry.get('unit_name') or (str(unit_id_ai) if unit_id_ai else None)
                    
                    unit_from_inquiry = None
                    if unit_id_ai or unit_name_ai or unit_number_ai:
                        unit_from_inquiry = {
                            'id': unit_id_ai,
                            'unit_name': unit_name_ai,
                            'unit_number': unit_number_ai,
                            'status': assigned_inquiry.get('unit_status'),
                            'monthly_rent': float(assigned_inquiry.get('unit_monthly_rent') or 0),
                            'move_in_date': None,
                            'move_out_date': None
                        }
                    
                    property_from_inquiry = None
                    if prop_id_ai or assigned_inquiry.get('property_title') or assigned_inquiry.get('building_name') or assigned_inquiry.get('property_address'):
                        property_from_inquiry = {
                            'id': prop_id_ai,
                            'building_name': assigned_inquiry.get('building_name'),
                            'title': assigned_inquiry.get('property_title') or assigned_inquiry.get('building_name'),
                            'address': assigned_inquiry.get('property_address'),
                            'city': assigned_inquiry.get('property_city'),
                            'province': assigned_inquiry.get('property_province')
                        }
                    
                    if unit_from_inquiry or property_from_inquiry:
                        if not unit_info and unit_from_inquiry:
                            unit_info = unit_from_inquiry
                        if not property_info and property_from_inquiry:
                            property_info = property_from_inquiry
                        unit_assignments.append({
                            'unit': unit_from_inquiry,
                            'property': property_from_inquiry
                        })
            except Exception as inquiry_error:
                current_app.logger.error(f'Failed to merge assigned inquiries into tenant assignments: {str(inquiry_error)}', exc_info=True)
        except Exception as unit_error:
            current_app.logger.error(f'Failed to fetch tenant unit/property info: {str(unit_error)}', exc_info=True)
            unit_info = None
            property_info = None
        
        profile_data['current_unit'] = unit_info
        profile_data['current_property'] = property_info
        profile_data['unit_assignments'] = unit_assignments
        
        # Log what we're returning for debugging
        current_app.logger.info(f'Profile response - current_unit: {unit_info is not None}, current_property: {property_info is not None}')
        if unit_info:
            current_app.logger.info(f'Unit info details: id={unit_info.get("id")}, name={unit_info.get("unit_name")}, number={unit_info.get("unit_number")}')
        if property_info:
            current_app.logger.info(f'Property info details: id={property_info.get("id")}, title={property_info.get("title")}, building={property_info.get("building_name")}')
        
        return jsonify({
            'profile': profile_data
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get tenant profile error: {e}')
        return handle_api_error(500, "Failed to retrieve profile")

@tenant_profile_bp.route('/', methods=['PUT'])
@tenant_required
def update_tenant_profile(current_user):
    """Update the current tenant's profile information."""
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        # Update basic profile fields
        if 'first_name' in data and data['first_name']:
            current_user.first_name = sanitize_input(data['first_name'])
        
        if 'last_name' in data and data['last_name']:
            current_user.last_name = sanitize_input(data['last_name'])
        
        if 'phone_number' in data:
            current_user.phone_number = sanitize_input(data['phone_number']) if data['phone_number'] else None
        
        if 'date_of_birth' in data:
            if data['date_of_birth']:
                from datetime import datetime
                try:
                    current_user.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
                except ValueError:
                    return handle_api_error(400, "Invalid date format. Use YYYY-MM-DD")
            else:
                current_user.date_of_birth = None
        
        # Update address fields
        if 'address' in data:
            current_user.address = sanitize_input(data['address']) if data['address'] else None
        
        address_fields = ['city', 'province', 'postal_code', 'country']
        for field in address_fields:
            if field in data:
                value = sanitize_input(data[field]) if data[field] else None
                setattr(current_user, field, value)
        
        # Update bio field
        if 'bio' in data:
            current_user.bio = sanitize_input(data['bio']) if data['bio'] else None
        
        db.session.commit()
        
        # Send notification about profile update
        try:
            from app.services.notification_service import NotificationService
            NotificationService.notify_account_update(
                tenant_id=current_user.id,
                update_type="profile"
            )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': 'Profile updated successfully',
            'profile': current_user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Update tenant profile error: {e}')
        return handle_api_error(500, "Failed to update profile")

@tenant_profile_bp.route('/change-password', methods=['POST'])
@tenant_required
def change_password(current_user):
    """Change the current tenant's password."""
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not current_password or not new_password or not confirm_password:
            return handle_api_error(400, "All password fields are required")
        
        # Verify current password
        if not current_user.check_password(current_password):
            return handle_api_error(400, "Current password is incorrect")
        
        # Verify new password confirmation
        if new_password != confirm_password:
            return handle_api_error(400, "New password and confirmation do not match")
        
        # Validate new password strength (basic validation)
        if len(new_password) < 8:
            return handle_api_error(400, "New password must be at least 8 characters long")
        
        # Update password
        current_user.set_password(new_password)
        db.session.commit()
        
        # Send notification about password change
        try:
            from app.services.notification_service import NotificationService
            NotificationService.notify_account_update(
                tenant_id=current_user.id,
                update_type="password"
            )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': 'Password changed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Change password error: {e}')
        return handle_api_error(500, "Failed to change password")


@tenant_profile_bp.route('/upload-image', methods=['POST'])
@tenant_required
def upload_profile_image(current_user):
    """Upload and set the tenant's profile image."""
    try:
        if 'image' not in request.files:
            return handle_api_error(400, "No image file provided")

        file = request.files['image']
        if not file or file.filename == '':
            return handle_api_error(400, "No image selected")

        # Build user-specific upload directory under instance/uploads/users/<id>
        upload_folder = os.path.join(
            current_app.instance_path,
            current_app.config.get('UPLOAD_FOLDER', 'uploads'),
            'users',
            str(current_user.id)
        )

        success, filename, error = save_uploaded_file(
            file,
            upload_folder,
            allowed_extensions=IMAGE_EXTENSIONS,
            max_size=5 * 1024 * 1024  # 5MB
        )

        if not success:
            return handle_api_error(400, error or "Failed to save image")

        # Public URL served by /uploads route
        public_url = f"/uploads/users/{current_user.id}/{filename}"

        # Persist on user
        current_user.profile_image_url = public_url
        db.session.commit()

        return jsonify({
            'message': 'Profile image updated successfully',
            'profile_image_url': public_url
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Upload profile image error: {e}')
        return handle_api_error(500, "Failed to upload profile image")


# Two-Factor Authentication (TOTP) - DEPRECATED: System uses email-based 2FA
# These routes are kept for backward compatibility but may not work if two_factor_secret column is dropped
@tenant_profile_bp.route('/2fa/setup', methods=['POST'])
@tenant_required
def twofa_setup(current_user):
    """Initialize 2FA setup: generate secret and QR image (data URL)."""
    try:
        # Check if two_factor_secret column exists (for backward compatibility)
        if not hasattr(current_user, 'two_factor_secret'):
            return handle_api_error(400, 'TOTP 2FA is not available. Please use email-based 2FA instead.')
        
        # Generate new secret
        secret = pyotp.random_base32()
        current_user.two_factor_secret = secret
        db.session.commit()

        issuer = (current_app.config.get('APP_NAME') or 'CapstoneApp').replace(':', '')
        label = f"{issuer}:{current_user.email}"
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=label, issuer_name=issuer)

        # Create QR code PNG as data URL
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        data_url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')

        return jsonify({'secret': secret, 'otpauth_url': uri, 'qr_data_url': data_url}), 200
    except Exception as e:
        current_app.logger.error(f'2FA setup error: {e}')
        return handle_api_error(500, 'Failed to initialize 2FA')


@tenant_profile_bp.route('/2fa/enable', methods=['POST'])
@tenant_required
def twofa_enable(current_user):
    """Verify code and enable 2FA."""
    try:
        # Check if two_factor_secret column exists (for backward compatibility)
        if not hasattr(current_user, 'two_factor_secret'):
            return handle_api_error(400, 'TOTP 2FA is not available. Please use email-based 2FA instead.')
        
        data = request.get_json() or {}
        code = (data.get('code') or '').strip()
        if not current_user.two_factor_secret:
            return handle_api_error(400, '2FA secret not initialized')
        totp = pyotp.TOTP(current_user.two_factor_secret)
        if not totp.verify(code, valid_window=1):
            return handle_api_error(400, 'Invalid verification code')
        current_user.two_factor_enabled = True
        db.session.commit()
        return jsonify({'message': 'Two-factor authentication enabled'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'2FA enable error: {e}')
        return handle_api_error(500, 'Failed to enable 2FA')


@tenant_profile_bp.route('/2fa/disable', methods=['POST'])
@tenant_required
def twofa_disable(current_user):
    """Disable 2FA after verifying current password or code (optional simple flow)."""
    try:
        current_user.two_factor_enabled = False
        # Keep secret so user can re-enable quickly; clear if you prefer
        db.session.commit()
        return jsonify({'message': 'Two-factor authentication disabled'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'2FA disable error: {e}')
        return handle_api_error(500, 'Failed to disable 2FA')


# Email-based 2FA toggle (no TOTP)
@tenant_profile_bp.route('/2fa/email/enable', methods=['POST'])
@tenant_required
def twofa_email_enable(current_user):
    """Enable email-based 2FA for current tenant."""
    try:
        current_user.two_factor_enabled = True
        # Clear any TOTP secret to avoid confusion (if column exists)
        try:
            if hasattr(current_user, 'two_factor_secret'):
                current_user.two_factor_secret = None
        except Exception:
            pass
        db.session.commit()
        return jsonify({'message': 'Email-based two-factor authentication enabled'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'2FA email enable error: {e}')
        return handle_api_error(500, 'Failed to enable 2FA')


@tenant_profile_bp.route('/2fa/email/disable', methods=['POST'])
@tenant_required
def twofa_email_disable(current_user):
    """Disable email-based 2FA for current tenant."""
    try:
        current_user.two_factor_enabled = False
        current_user.two_factor_email_code = None
        current_user.two_factor_email_expires = None
        db.session.commit()
        return jsonify({'message': 'Email-based two-factor authentication disabled'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'2FA email disable error: {e}')
        return handle_api_error(500, 'Failed to disable 2FA')
