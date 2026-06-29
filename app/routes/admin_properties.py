"""
Admin property management routes - approval and portal management
"""
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.property import Property, PropertyStatus
from app.utils.decorators import admin_required
from app.utils.error_handlers import handle_api_error
from sqlalchemy import text
import json

admin_properties_bp = Blueprint('admin_properties', __name__)

@admin_properties_bp.route('/all', methods=['GET'])
@admin_required
def get_all_properties(current_user):
    """
    Get all properties (Admin)
    ---
    tags:
      - Admin Properties
    summary: Get all properties for admin analytics
    description: Retrieve all properties in the system for admin analytics and management
    security:
      - Bearer: []
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
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        current_app.logger.info(f"Admin all properties request - User: {current_user.id}, Role: {current_user.role}")
        
        # Use raw SQL to avoid missing column issues
        query_sql = text("""
            SELECT 
                p.id,
                p.title,
                p.building_name,
                p.property_type,
                p.address,
                p.city,
                p.province,
                p.total_units,
                p.monthly_rent,
                p.status,
                p.created_at,
                p.updated_at,
                p.owner_id,
                u.first_name,
                u.last_name,
                u.email as owner_email
            FROM properties p
            LEFT JOIN users u ON p.owner_id = u.id
            ORDER BY p.created_at DESC
        """)
        
        properties_result = db.session.execute(query_sql).fetchall()
        
        current_app.logger.info(f"Found {len(properties_result)} total properties")
        
        # Convert to frontend format
        properties_data = []
        for prop in properties_result:
            prop_dict = {
                'id': prop.id,
                'title': prop.title or prop.building_name or 'Unnamed Property',
                'property_type': prop.property_type,
                'address': {
                    'city': prop.city,
                    'province': prop.province
                },
                'city': prop.city,
                'province': prop.province,
                'monthly_rent': prop.monthly_rent,
                'status': prop.status,
                'created_at': prop.created_at.isoformat() if prop.created_at else None,
                'updated_at': prop.updated_at.isoformat() if prop.updated_at else None,
                'owner': {
                    'id': prop.owner_id,
                    'name': f"{prop.first_name or ''} {prop.last_name or ''}".strip() or 'Unknown',
                    'email': prop.owner_email or ''
                } if prop.owner_id else None,
                'pricing': {
                    'monthly_rent': prop.monthly_rent
                }
            }
            properties_data.append(prop_dict)
        
        return jsonify({
            'properties': properties_data,
            'total': len(properties_data)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get all properties error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, f"Failed to retrieve properties: {str(e)}")

@admin_properties_bp.route('/pending-properties', methods=['GET'])
@admin_required
def get_pending_properties(current_user):
    """
    Get pending properties (Admin)
    ---
    tags:
      - Admin Properties
    summary: Get properties pending admin approval
    description: Retrieve all properties that are pending admin review and approval
    security:
      - Bearer: []
    responses:
      200:
        description: Pending properties retrieved successfully
        schema:
          type: object
          properties:
            properties:
              type: array
              items:
                type: object
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        from sqlalchemy import text
        
        # Debug logging
        current_app.logger.info(f"Admin properties request - User: {current_user.id}, Role: {current_user.role}")
        current_app.logger.info(f"Request args: {dict(request.args)}")
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)  # Cap at 100
        status_filter = (request.args.get('status') or 'pending').lower()
        
        current_app.logger.info(f"Query params - page: {page}, per_page: {per_page}, status_filter: {status_filter}")
        
        # Map status filter to database values
        status_mapping = {
            'pending': 'pending_approval',
            'approved': 'approved', 
            'rejected': 'rejected'
        }
        
        # Handle "all" status case
        if status_filter == 'all':
            db_status = None
            where_clause = ""
            count_where_clause = ""
        else:
            db_status = status_mapping.get(status_filter, 'pending_approval')
            where_clause = "WHERE p.status = :status"
            count_where_clause = "WHERE status = :status"
        
        # Query live properties table - always shows current information
        # This ensures admin sees the most up-to-date property details
        # even if the property manager updates the property while pending
        query_sql = text(f"""
            SELECT 
                p.id,
                p.title,
                p.building_name,
                p.description,
                p.property_type,
                p.address,
                p.city,
                p.province,
                p.total_units,
                p.monthly_rent,
                p.contact_person,
                p.contact_email,
                p.contact_phone,
                p.status,
                p.created_at,
                p.updated_at,
                p.owner_id,
                p.images,
                p.legal_documents,
                p.amenities,
                u.first_name,
                u.last_name,
                u.email as owner_email
            FROM properties p
            LEFT JOIN users u ON p.owner_id = u.id
            {where_clause}
            ORDER BY p.updated_at DESC, p.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        # Count query
        count_sql = text(f"SELECT COUNT(*) FROM properties {count_where_clause}")
        
        # Execute queries
        offset = (page - 1) * per_page
        
        # Prepare query parameters
        query_params = {
            'limit': per_page,
            'offset': offset
        }
        
        # Add status parameter only if not "all"
        if db_status is not None:
            query_params['status'] = db_status
        
        # Get total count
        total_count = db.session.execute(count_sql, query_params).scalar()
        
        # Get properties
        properties_result = db.session.execute(query_sql, query_params).fetchall()
        
        current_app.logger.info(f"Found {len(properties_result)} properties with status '{db_status}'")
        for prop in properties_result:
            current_app.logger.info(f"Property ID: {prop.id}, Title: {prop.title}, Status: {prop.status}, Updated: {prop.updated_at}")
        
        # Convert to frontend format
        properties_data = []
        for prop in properties_result:
            # Parse JSON fields safely
            images = []
            legal_docs = []
            amenities = []
            
            if prop.images:
                try:
                    images = json.loads(prop.images) if isinstance(prop.images, str) else prop.images
                except:
                    images = []
            
            if prop.legal_documents:
                try:
                    legal_docs = json.loads(prop.legal_documents) if isinstance(prop.legal_documents, str) else prop.legal_documents
                except:
                    legal_docs = []
            
            if prop.amenities:
                try:
                    amenities = json.loads(prop.amenities) if isinstance(prop.amenities, str) else prop.amenities
                except:
                    amenities = []
            
            prop_dict = {
                'id': prop.id,
                'name': prop.building_name or prop.title or 'Unnamed Property',
                'title': prop.title or prop.building_name or 'Unnamed Property',
                'type': 'Building',
                'category': 'building',
                'location': prop.address or 'No address',
                'address': prop.address or 'No address',
                'units': prop.total_units or 0,
                'num_units': prop.total_units or 0,
                'property_type': prop.property_type,
                'priceRange': f"₱{prop.monthly_rent:,.0f}" if prop.monthly_rent else None,
                'price': prop.monthly_rent,
                'rent_price': prop.monthly_rent,
                'images': images,
                'legal_documents': legal_docs,
                'amenities': amenities,
                'status': prop.status,
                'managerNotes': prop.description or '',
                'description': prop.description or '',
                'created_at': prop.created_at.isoformat() if prop.created_at else None,
                'updated_at': prop.updated_at.isoformat() if prop.updated_at else None,
                'last_updated': prop.updated_at.isoformat() if prop.updated_at else prop.created_at.isoformat() if prop.created_at else None,
                'owner': {
                    'id': prop.owner_id,
                    'name': f"{prop.first_name or ''} {prop.last_name or ''}".strip() or 'Unknown',
                    'email': prop.owner_email or ''
                } if prop.owner_id else None,
                'manager': prop.contact_person or 'Unknown',
                'managerEmail': prop.contact_email or '',
                'managerPhone': prop.contact_phone or ''
            }
            properties_data.append(prop_dict)
        
        # Create pagination
        total_pages = (total_count + per_page - 1) // per_page
        pagination_meta = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }
        
        return jsonify({
            'properties': properties_data,
            'pagination': pagination_meta,
            'total_pending': total_count
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get pending properties error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, f"Failed to retrieve properties: {str(e)}")

@admin_properties_bp.route('/approve-property/<int:property_id>', methods=['POST'])
@admin_required
def approve_property(current_user, property_id):
    """
    Approve property (Admin)
    ---
    tags:
      - Admin Properties
    summary: Approve a property and enable portal
    description: Approve a pending property and optionally set a custom subdomain for the portal
    security:
      - Bearer: []
    parameters:
      - in: path
        name: property_id
        type: integer
        required: true
        description: The property ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            notes:
              type: string
            custom_subdomain:
              type: string
    responses:
      200:
        description: Property approved successfully
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      404:
        description: Property not found
      500:
        description: Server error
    """
    try:
        data = request.get_json() or {}
        notes = data.get('notes', 'Property approved by admin')
        custom_subdomain = data.get('custom_subdomain', '').strip()

        # Check if property exists and is pending
        check_sql = text("""
            SELECT id, title, status, portal_subdomain 
            FROM properties 
            WHERE id = :property_id
        """)
        
        property_result = db.session.execute(check_sql, {'property_id': property_id}).fetchone()
        
        if not property_result:
            return handle_api_error(404, "Property not found")
        
        if property_result.status not in ['pending', 'pending_approval']:
            return handle_api_error(400, "Property is not pending approval")
        
        # Check if all legal documents are approved
        property_full_sql = text("""
            SELECT legal_documents 
            FROM properties 
            WHERE id = :property_id
        """)
        
        property_full = db.session.execute(property_full_sql, {'property_id': property_id}).fetchone()
        
        if property_full and property_full.legal_documents:
            import json
            try:
                legal_docs = json.loads(property_full.legal_documents) if isinstance(property_full.legal_documents, str) else property_full.legal_documents
                if isinstance(legal_docs, list) and len(legal_docs) > 0:
                    # Check if all documents are approved
                    pending_docs = []
                    for doc in legal_docs:
                        if isinstance(doc, dict):
                            doc_status = doc.get('status', 'pending')
                            if doc_status not in ['approved']:
                                doc_type = doc.get('type', 'unknown')
                                doc_name = doc.get('filename', doc.get('name', 'Unknown'))
                                pending_docs.append({
                                    'type': doc_type,
                                    'name': doc_name,
                                    'status': doc_status
                                })
                    
                    if pending_docs:
                        pending_list = '\n'.join([f"- {doc['name']} ({doc['type']}) - Status: {doc['status']}" for doc in pending_docs])
                        return handle_api_error(400, f"Cannot approve property. The following legal documents must be approved first:\n\n{pending_list}\n\nPlease review and approve all documents in Document Management before approving the property.")
            except Exception as doc_check_error:
                current_app.logger.warning(f"Error checking document status: {str(doc_check_error)}")
                # Continue with approval if document check fails (don't block approval due to parsing errors)
        
        # Generate subdomain if not provided
        if not custom_subdomain:
            # Create subdomain from property title
            import re
            subdomain_base = re.sub(r'[^\w\s-]', '', property_result.title.lower())
            subdomain_base = re.sub(r'[-\s]+', '-', subdomain_base)
            custom_subdomain = f"{subdomain_base}-{property_id}"
        
        # Update property status to approved
        update_sql = text("""
            UPDATE properties 
            SET status = 'approved', 
                portal_subdomain = :subdomain,
                updated_at = NOW()
            WHERE id = :property_id
        """)
        
        db.session.execute(update_sql, {
            'property_id': property_id,
            'subdomain': custom_subdomain
        })
        db.session.commit()
        
        # Notify property manager about approval
        try:
            from app.services.notification_service import NotificationService
            owner_result = db.session.execute(text("""
                SELECT owner_id, title, building_name
                FROM properties
                WHERE id = :property_id
            """), {'property_id': property_id}).mappings().first()
            
            if owner_result:
                property_name = owner_result.get('title') or owner_result.get('building_name') or 'Property'
                manager_id = owner_result.get('owner_id')
                NotificationService.notify_property_approved(
                    manager_id=manager_id,
                    property_id=property_id,
                    property_name=property_name
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': 'Property approved successfully',
            'property_id': property_id,
            'portal_subdomain': custom_subdomain,
            'portal_url': f'http://localhost:8080',
            'notes': notes,
            'status': 'approved'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Approve property error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, f"Failed to approve property: {str(e)}")

@admin_properties_bp.route('/reject-property/<int:property_id>', methods=['POST'])
@admin_required
def reject_property(current_user, property_id):
    """
    Reject property (Admin)
    ---
    tags:
      - Admin Properties
    summary: Reject a property with reason
    description: Reject a pending property with an optional rejection reason
    security:
      - Bearer: []
    parameters:
      - in: path
        name: property_id
        type: integer
        required: true
        description: The property ID
      - in: body
        name: body
        schema:
          type: object
          properties:
            reason:
              type: string
              description: Rejection reason
    responses:
      200:
        description: Property rejected successfully
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      404:
        description: Property not found
      500:
        description: Server error
    """
    try:
        data = request.get_json() or {}
        rejection_reason = data.get('reason', 'No reason provided')

        # Check if property exists and is pending
        check_sql = text("""
            SELECT id, title, status 
            FROM properties 
            WHERE id = :property_id
        """)
        
        property_result = db.session.execute(check_sql, {'property_id': property_id}).fetchone()
        
        if not property_result:
            return handle_api_error(404, "Property not found")
        
        if property_result.status not in ['pending', 'pending_approval']:
            return handle_api_error(400, "Property is not pending approval")
        
        # Update property status to rejected
        update_sql = text("""
            UPDATE properties 
            SET status = 'rejected', 
                updated_at = NOW()
            WHERE id = :property_id
        """)
        
        db.session.execute(update_sql, {'property_id': property_id})
        db.session.commit()
        
        # Notify property manager about rejection
        try:
            from app.services.notification_service import NotificationService
            owner_result = db.session.execute(text("""
                SELECT owner_id, title, building_name
                FROM properties
                WHERE id = :property_id
            """), {'property_id': property_id}).mappings().first()
            
            if owner_result:
                property_name = owner_result.get('title') or owner_result.get('building_name') or 'Property'
                manager_id = owner_result.get('owner_id')
                NotificationService.notify_property_rejected(
                    manager_id=manager_id,
                    property_id=property_id,
                    property_name=property_name,
                    reason=rejection_reason
                )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': 'Property rejected successfully',
            'property_id': property_id,
            'reason': rejection_reason,
            'status': 'rejected'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Reject property error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, f"Failed to reject property: {str(e)}")
