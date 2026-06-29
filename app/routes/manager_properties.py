"""
Property Manager API Routes
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.property import Property, PropertyStatus, PropertyType, FurnishingType, ManagementStatus
from app.models.user import User, UserRole
from app.utils.decorators import auth_required, manager_required
from app.utils.pagination import paginate_query
from app.utils.error_handlers import handle_api_error
import json

manager_properties_bp = Blueprint('manager_properties', __name__)

@manager_properties_bp.route('/companies', methods=['GET'])
@manager_required
def list_properties(current_user):
    """
    List properties (Manager)
    ---
    tags:
      - Manager Properties
    summary: List all properties owned by the manager
    description: Retrieve all properties (building-level) owned by the authenticated property manager
    security:
      - Bearer: []
    parameters:
      - in: query
        name: owner_id
        type: integer
        description: Filter by owner/manager user ID
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
      401:
        description: Unauthorized
      403:
        description: Forbidden - Manager access required
      500:
        description: Server error
    """
    try:
        from sqlalchemy import text
        
        owner_id = request.args.get('owner_id', type=int)
        
        # Build query with optional owner filter
        where_clause = ""
        params = {}
        if owner_id:
            where_clause = "WHERE owner_id = :owner_id"
            params['owner_id'] = owner_id
        
        query_sql = text(f"""
            SELECT p.*
            FROM properties p
            {where_clause}
            ORDER BY p.created_at DESC
        """)
        
        rows = db.session.execute(query_sql, params).fetchall()
        
        # Convert rows to dict format
        items = []
        for row in rows:
            item = {
                'id': row.id,
                'title': row.title,
                'description': row.description,
                'property_type': row.property_type,
                'address': row.address,
                'city': row.city,
                'province': row.province,
                'total_units': row.total_units,
                'owner_id': row.owner_id,
                'building_name': row.building_name,
                'subdomain': row.portal_subdomain,  # Map portal_subdomain to subdomain
                'contact_person': row.contact_person,
                'contact_email': row.contact_email,
                'contact_phone': row.contact_phone,
                'monthly_rent': float(row.monthly_rent) if row.monthly_rent else 0,
                'furnishing': row.furnishing,
                'status': row.status,
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None
            }
            items.append(item)
        
        return jsonify({'properties': items}), 200
    except Exception as e:
        current_app.logger.error(f'List properties error: {e}')
        return handle_api_error(500, 'Failed to fetch properties')

@manager_properties_bp.route('/companies', methods=['POST'])
@manager_required
def create_property(current_user):
    """
    Create property (Manager)
    ---
    tags:
      - Manager Properties
    summary: Create a new property
    description: Create a new property listing. Subject to subscription plan property limits.
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - building_name
            - address
            - contact_person
            - contact_email
            - contact_phone
          properties:
            building_name:
              type: string
            address:
              type: string
            contact_person:
              type: string
            contact_email:
              type: string
            contact_phone:
              type: string
    responses:
      201:
        description: Property created successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            message:
              type: string
      400:
        description: Validation error or property limit reached
      401:
        description: Unauthorized
      403:
        description: Forbidden
      500:
        description: Server error
    """
    try:
        data = request.get_json(force=True)
        required = ['building_name', 'address', 'contact_person', 'contact_email', 'contact_phone']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return handle_api_error(400, f"Missing required fields: {', '.join(missing)}")


        # Get owner_id from authenticated user
        owner_id = current_user.id
        current_app.logger.info(f"Creating property for user ID: {owner_id}, email: {current_user.email}")
        current_app.logger.info(f"Received data: {data}")

        # Enforce subscription property limit for this manager
        try:
            from app.repositories.subscription_repository import SubscriptionRepository
            from sqlalchemy import text as _t
            repo = SubscriptionRepository()
            sub = repo.get_by_user_id(owner_id)
            max_allowed = None
            if sub and sub.plan:
                max_allowed = getattr(sub.plan, 'max_properties', None)
            # Count current properties owned by this manager
            cnt_row = db.session.execute(_t("SELECT COUNT(*) AS c FROM properties WHERE owner_id = :oid"), {'oid': owner_id}).fetchone()
            current_count = cnt_row.c if cnt_row else 0
            if max_allowed is not None and max_allowed != -1 and current_count >= int(max_allowed):
                return handle_api_error(403, f"Property limit reached for your plan (max {int(max_allowed)}). Upgrade your plan to add more properties.")
        except Exception as _limit_err:
            current_app.logger.warning(f"Property limit check failed, proceeding conservatively: {_limit_err}")

        # Independent property manager - no company concept
        manager_user = current_user
        current_app.logger.info(f"Creating property for independent manager: {manager_user.first_name} {manager_user.last_name}")
        
        # Create Property object using raw SQL to match actual database schema
        from sqlalchemy import text
        
        # Map property type to database enum values
        db_property_type = 'bed_space'  # default
        if data.get('property_type'):
            type_mapping = {
                'bed_space': 'bed_space',
                'dormitory': 'dormitory', 
                'boarding_house': 'boarding_house',
                'studio_apartment': 'studio_apartment',
                'room_for_rent': 'room_for_rent'
            }
            db_property_type = type_mapping.get(data['property_type'].lower(), 'bed_space')

        # Map furnishing to database enum values
        db_furnishing = 'UNFURNISHED'  # default
        if data.get('furnishing'):
            furnishing_mapping = {
                'unfurnished': 'UNFURNISHED',
                'semi-furnished': 'SEMI_FURNISHED',
                'semi_furnished': 'SEMI_FURNISHED',
                'furnished': 'FURNISHED',
                'fully_furnished': 'FURNISHED'
            }
            db_furnishing = furnishing_mapping.get(data['furnishing'].lower(), 'UNFURNISHED')


        # Insert directly into database using raw SQL
        insert_sql = text("""
            INSERT INTO properties (
                title, description, property_type, address, street, barangay, city, province, postal_code,
                latitude, longitude,
                total_units, owner_id, building_name,
                contact_person, contact_email, contact_phone, monthly_rent,
                furnishing, status,
                portal_subdomain, legal_documents, images, amenities, additional_notes,
                created_at, updated_at
            ) VALUES (
                :title, :description, :property_type, :address, :street, :barangay, :city, :province, :postal_code,
                :latitude, :longitude,
                :total_units, :owner_id, :building_name,
                :contact_person, :contact_email, :contact_phone, :monthly_rent,
                :furnishing, :status,
                :portal_subdomain, :legal_documents, :images, :amenities, :additional_notes,
                NOW(), NOW()
            )
        """)
        
        def normalize_json_field(value):
            if value is None:
                return '[]'
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith('[') and stripped.endswith(']'):
                    return stripped
                if not stripped:
                    return '[]'
                return json.dumps([value])
            try:
                return json.dumps(value)
            except Exception:
                return '[]'
        
        legal_docs_json = normalize_json_field(data.get('legal_documents'))
        images_json = normalize_json_field(data.get('images'))
        amenities_json = normalize_json_field(data.get('amenities'))
        additional_notes = data.get('additional_notes') or data.get('description', '')
        
        # Auto-generate address from components if not provided or if components are available
        street = data.get('street', '').strip() or None
        barangay = data.get('barangay', '').strip() or None
        city = data.get('city', 'Cebu City')
        province = data.get('province', 'Cebu')
        postal_code = data.get('postal_code', '').strip() or None
        
        # Build address from components (prioritize components over provided address)
        if street or barangay:
            address_parts = []
            if street:
                address_parts.append(street)
            if barangay:
                address_parts.append(barangay)
            if city:
                address_parts.append(city)
            if province:
                address_parts.append(province)
            if postal_code:
                address_parts.append(postal_code)
            generated_address = ', '.join(address_parts)
        else:
            # Use provided address or fallback
            generated_address = data.get('address', '').strip() or f"{city}, {province}"
        
        # Prepare SQL parameters
        sql_params = {
            'title': data['building_name'].strip(),
            'description': data.get('description', ''),
            'property_type': db_property_type,
            'address': generated_address,
            'street': street,
            'barangay': barangay,
            'city': city,
            'province': province,
            'postal_code': postal_code,
            'latitude': float(data.get('latitude')) if data.get('latitude') else None,
            'longitude': float(data.get('longitude')) if data.get('longitude') else None,
            'total_units': int(data.get('total_units', 1)),
            'owner_id': owner_id,
            'building_name': data['building_name'].strip(),
            'contact_person': data['contact_person'].strip(),
            'contact_email': data['contact_email'].strip(),
            'contact_phone': data['contact_phone'].strip(),
            'monthly_rent': float(data.get('monthly_rent', 0)),
            'furnishing': db_furnishing,
            'status': 'pending_approval',
            'portal_subdomain': data.get('subdomain', '').strip().lower(),
            'legal_documents': legal_docs_json,
            'images': images_json,
            'amenities': amenities_json,
            'additional_notes': additional_notes
        }
        
        current_app.logger.info(f"Executing SQL with params: {sql_params}")
        
        result = db.session.execute(insert_sql, sql_params)
        
        # Get the inserted property ID
        property_id = result.lastrowid
        
        db.session.commit()
        
        # Fetch the created property to return
        fetch_sql = text("SELECT * FROM properties WHERE id = :property_id")
        property_row = db.session.execute(fetch_sql, {'property_id': property_id}).fetchone()
        
        # Convert to dict format
        property_data = {
            'id': property_row.id,
            'title': property_row.title,
            'description': property_row.description,
            'property_type': property_row.property_type,
            'address': property_row.address,
            'street': getattr(property_row, 'street', None),
            'barangay': getattr(property_row, 'barangay', None),
            'city': property_row.city,
            'province': property_row.province,
            'postal_code': getattr(property_row, 'postal_code', None),
            'latitude': float(getattr(property_row, 'latitude', 0)) if getattr(property_row, 'latitude', None) else None,
            'longitude': float(getattr(property_row, 'longitude', 0)) if getattr(property_row, 'longitude', None) else None,
            'total_units': property_row.total_units,
            'owner_id': property_row.owner_id,
            'building_name': property_row.building_name,
            'subdomain': getattr(property_row, 'portal_subdomain', None),
            'contact_person': property_row.contact_person,
            'contact_email': property_row.contact_email,
            'contact_phone': property_row.contact_phone,
            'monthly_rent': float(property_row.monthly_rent) if property_row.monthly_rent else 0,
            'furnishing': property_row.furnishing,
            'status': property_row.status,
            'created_at': property_row.created_at.isoformat() if property_row.created_at else None,
            'updated_at': property_row.updated_at.isoformat() if property_row.updated_at else None,
            'images': property_row.images,
            'amenities': property_row.amenities,
            'legal_documents': property_row.legal_documents,
            'additional_notes': property_row.additional_notes
        }
        
        return jsonify({'item': property_data}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Create property error: {e}')
        return handle_api_error(500, 'Failed to create property')


@manager_properties_bp.route('/debug-properties', methods=['GET'])
def debug_properties():
    """Debug endpoint to test basic property queries."""
    try:
        owner_id = request.args.get('owner_id', type=int)
        current_app.logger.info(f"Debug endpoint called with owner_id: {owner_id}")
        
        if not owner_id:
            return jsonify({'error': 'owner_id parameter required'}), 400
        
        # Simple query
        from sqlalchemy import text
        query_sql = text("SELECT id, title, status, owner_id FROM properties WHERE owner_id = :owner_id")
        rows = db.session.execute(query_sql, {'owner_id': owner_id}).fetchall()
        
        properties = []
        approved_count = 0
        for row in rows:
            is_approved = row.status in ['approved', 'active']
            if is_approved:
                approved_count += 1
            properties.append({
                'id': row.id,
                'title': row.title,
                'status': row.status,
                'owner_id': row.owner_id,
                'is_approved': is_approved
            })
        
        return jsonify({
            'properties': properties,
            'total_properties': len(properties),
            'approved_properties': approved_count,
            'debug': True,
            'note': 'Properties with status "approved" or "active" are considered approved'
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Debug properties error: {e}')
        return jsonify({'error': str(e)}), 500

@manager_properties_bp.route('/my-properties', methods=['GET'])
@manager_required
def get_my_properties(current_user):
    """Get all properties owned by the current manager."""
    try:
        current_app.logger.info("=== Starting get_my_properties endpoint ===")
        
        # Get owner_id from query parameters
        owner_id = request.args.get('owner_id', type=int)
        current_app.logger.info(f"Received owner_id parameter: {owner_id}")
        
        # Use current authenticated user
        manager_user_id = current_user.id
        current_app.logger.info(f"Using current authenticated user: {current_user.email} (ID: {manager_user_id})")
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status')
        
        # Use raw SQL query to avoid ORM enum issues
        from sqlalchemy import text
        
        # Build base query with raw SQL
        base_sql = "SELECT * FROM properties WHERE owner_id = :owner_id"
        params = {'owner_id': manager_user_id}
        
        # Add status filter if provided
        if status_filter:
            current_app.logger.info(f"Applying status filter: {status_filter}")
            try:
                # Handle different status filter formats
                if status_filter.lower() in ['approved', 'active']:
                    base_sql += " AND (status = 'approved' OR status = 'active')"
                else:
                    base_sql += " AND status = :status_filter"
                    params['status_filter'] = status_filter.lower()
            except Exception as e:
                current_app.logger.warning(f"Error with status filter '{status_filter}': {e}")
        
        base_sql += " ORDER BY updated_at DESC"
        
        current_app.logger.info(f"Executing SQL: {base_sql} with params: {params}")
        
        # Execute raw SQL query
        try:
            rows = db.session.execute(text(base_sql), params).fetchall()
            current_app.logger.info(f"Raw SQL returned {len(rows)} rows")
            
            property_ids = [row.id for row in rows]
            unit_counts_map = {}
            if property_ids:
                from sqlalchemy import bindparam
                # Calculate occupancy based on actual tenant assignments, not unit status
                # A unit is occupied if there's an active tenant_units record (move_out_date is NULL or in the future)
                counts_sql = text("""
                    SELECT 
                        u.property_id,
                        COUNT(DISTINCT u.id) AS total_units,
                        COUNT(DISTINCT CASE 
                            WHEN tu.id IS NOT NULL AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                            THEN u.id 
                        END) AS occupied_units
                    FROM units u
                    LEFT JOIN tenant_units tu ON tu.unit_id = u.id 
                        AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                    WHERE u.property_id IN :property_ids
                    GROUP BY u.property_id
                """).bindparams(bindparam('property_ids', expanding=True))
                counts_rows = db.session.execute(counts_sql, {'property_ids': property_ids}).fetchall()
                for cnt in counts_rows:
                    total_units = int(cnt.total_units or 0)
                    occupied_units = int(cnt.occupied_units or 0)
                    vacant_units = max(0, total_units - occupied_units)
                    unit_counts_map[cnt.property_id] = {
                        'total_units': total_units,
                        'occupied_units': occupied_units,
                        'vacant_units': vacant_units
                    }
            
            # Convert rows to property-like objects for pagination
            properties_data = []
            for row in rows:
                try:
                    unit_counts = unit_counts_map.get(row.id, {})
                    # computed_total_units is the actual count of units created
                    computed_total_units = unit_counts.get('total_units')
                    occupied_units = unit_counts.get('occupied_units', 0)
                    vacant_units = unit_counts.get('vacant_units')
                    # row.total_units is the property's unit limit (set when property was created)
                    property_unit_limit = row.total_units or 0
                    if computed_total_units is None:
                        computed_total_units = 0  # No units created yet
                    if vacant_units is None:
                        vacant_units = max(0, computed_total_units - occupied_units)
                    
                    # Parse images from JSON string
                    images = []
                    images_raw = getattr(row, 'images', None)
                    if images_raw:
                        try:
                            if isinstance(images_raw, str):
                                images_data = json.loads(images_raw)
                            else:
                                images_data = images_raw
                            
                            # Convert to frontend format: array of objects with 'url' property
                            if isinstance(images_data, list):
                                for img in images_data:
                                    if isinstance(img, str):
                                        images.append({'url': img})
                                    elif isinstance(img, dict) and 'url' in img:
                                        images.append(img)
                                    elif isinstance(img, dict) and 'image_url' in img:
                                        images.append({'url': img['image_url']})
                        except (json.JSONDecodeError, TypeError) as e:
                            current_app.logger.warning(f"Error parsing images for property {row.id}: {e}")
                    
                    # Parse amenities from JSON string
                    amenities = []
                    amenities_raw = getattr(row, 'amenities', None)
                    if amenities_raw:
                        try:
                            if isinstance(amenities_raw, str):
                                amenities = json.loads(amenities_raw)
                            else:
                                amenities = amenities_raw
                            if not isinstance(amenities, list):
                                amenities = []
                        except (json.JSONDecodeError, TypeError):
                            amenities = []
                    
                    prop_dict = {
                        'id': row.id,
                        'title': row.title or 'Untitled',
                        'description': row.description or '',
                        'property_type': row.property_type or 'bed_space',
                        'address': {
                            'full': row.address or '',
                        'city': row.city or '',
                        'province': row.province or '',
                            'building_name': row.building_name or ''
                        },
                        'city': row.city or '',  # Keep for backward compatibility
                        'province': row.province or '',  # Keep for backward compatibility
                        'total_units': property_unit_limit,  # Property's unit limit from database (set when property was created)
                        'actual_units': computed_total_units,  # Actual count of units created
                        'occupied_units': occupied_units,
                        'vacant_units': vacant_units,
                        'owner_id': row.owner_id,
                        'building_name': row.building_name or '',
                        'contact_person': row.contact_person or '',
                        'contact_email': row.contact_email or '',
                        'contact_phone': row.contact_phone or '',
                        'pricing': {
                            'monthly_rent': float(row.monthly_rent) if row.monthly_rent else 0.0
                        },
                        'monthly_rent': float(row.monthly_rent) if row.monthly_rent else 0.0,  # Keep for backward compatibility
                        'furnishing': row.furnishing or 'unfurnished',
                        'status': (row.status or '').upper().replace(' ', '_') if row.status else 'INACTIVE',  # Normalize to uppercase with underscores
                        'created_at': row.created_at.isoformat() if row.created_at else None,
                        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
                        'portal_subdomain': getattr(row, 'portal_subdomain', None),
                        'subdomain': getattr(row, 'portal_subdomain', None),  # Add alias for frontend compatibility
                        'portal_enabled': getattr(row, 'portal_enabled', False),
                        'images': images,
                        'amenities': amenities
                    }
                    prop_dict['unit_counts'] = unit_counts if unit_counts else {
                        'total_units': property_unit_limit,  # Property limit
                        'actual_units': computed_total_units,  # Actual count
                        'occupied_units': occupied_units,
                        'vacant_units': vacant_units
                    }
                    properties_data.append(prop_dict)
                    current_app.logger.info(f"Successfully converted property {row.id} (status: {row.status}) limit: {property_unit_limit}, actual: {computed_total_units}, occupied: {occupied_units}, vacant: {vacant_units}")
                except Exception as e:
                    current_app.logger.error(f"Error converting row {row.id}: {e}")
                    import traceback
                    current_app.logger.error(traceback.format_exc())
                    continue
            
            # Create pagination info
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            total = len(properties_data)
            start = (page - 1) * per_page
            end = start + per_page
            paginated_properties = properties_data[start:end]
            
            pagination = {
                'page': page,
                'pages': (total + per_page - 1) // per_page,
                'per_page': per_page,
                'total': total
            }
            
            response_data = {
                'properties': paginated_properties,
                'pagination': pagination,
                'total_properties': len(paginated_properties)
            }
            
            current_app.logger.info(f"Final response: {len(paginated_properties)} properties, total: {total}")
            return jsonify(response_data), 200
            
        except Exception as e:
            current_app.logger.error(f"Error executing raw SQL query: {e}")
            # Fallback to empty response
            return jsonify({
                'properties': [],
                'pagination': {'page': 1, 'pages': 1, 'per_page': 20, 'total': 0},
                'total_properties': 0
            }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get manager properties error: {e}')
        return handle_api_error(500, "Failed to retrieve properties")

@manager_properties_bp.route('/add', methods=['POST'])
@manager_required
def add_property(current_user):
    """Add a new property for the current manager."""
    try:
        # Use authenticated user
        manager_user = current_user
        manager_user_id = manager_user.id
        
        # Independent property manager - no company concept
        
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        # Validate required fields
        required_fields = ['title', 'address_line1', 'city', 'province', 'monthly_rent']
        for field in required_fields:
            if not data.get(field):
                return handle_api_error(400, f"Missing required field: {field}")
        
        # Handle preferred subdomain
        preferred_subdomain = data.get('preferred_subdomain', '').strip().lower()
        if preferred_subdomain:
            # Validate subdomain format
            import re
            if not re.match(r'^[a-z0-9-]+$', preferred_subdomain):
                return handle_api_error(400, "Subdomain can only contain lowercase letters, numbers, and hyphens")
            
            # Check if subdomain is already taken
            existing_property = Property.query.filter_by(portal_subdomain=preferred_subdomain).first()
            if existing_property:
                return handle_api_error(400, f"Subdomain '{preferred_subdomain}' is already taken")
        
        # Enforce subscription property limit
        try:
            from app.repositories.subscription_repository import SubscriptionRepository
            from sqlalchemy import text as _t
            repo = SubscriptionRepository()
            sub = repo.get_by_user_id(manager_user_id)
            max_allowed = None
            if sub and sub.plan:
                max_allowed = getattr(sub.plan, 'max_properties', None)
            cnt_row = db.session.execute(_t("SELECT COUNT(*) AS c FROM properties WHERE owner_id = :oid"), {'oid': manager_user_id}).fetchone()
            current_count = cnt_row.c if cnt_row else 0
            if max_allowed is not None and max_allowed != -1 and current_count >= int(max_allowed):
                return handle_api_error(403, f"Property limit reached for your plan (max {int(max_allowed)}). Upgrade your plan to add more properties.")
        except Exception as _limit_err:
            current_app.logger.warning(f"Property limit check failed, proceeding conservatively: {_limit_err}")

        # Create new property with required fields only
        property_type_str = data.get('property_type', 'BED_SPACE').upper()
        # Map frontend values to enum values
        property_type_mapping = {
            'BED_SPACE': PropertyType.BED_SPACE,
            'DORMITORY': PropertyType.DORMITORY,
            'BOARDING_HOUSE': PropertyType.BOARDING_HOUSE,
            'STUDIO_APARTMENT': PropertyType.STUDIO_APARTMENT,
            'ROOM_FOR_RENT': PropertyType.ROOM_FOR_RENT
        }
        property_type = property_type_mapping.get(property_type_str, PropertyType.BED_SPACE)
        
        new_property = Property(
            title=data['title'],
            property_type=property_type,
            address_line1=data['address_line1'],
            city=data['city'],
            monthly_rent=float(data['monthly_rent']),
            owner_id=manager_user_id
        )
        
        # Set additional fields after creation
        new_property.description = data.get('description', '')
        new_property.status = 'pending_approval'  # Use string instead of enum
        new_property.province = data['province']
        # bedrooms field removed (not in database schema)
        # Map furnishing type - use string values directly
        furnishing_str = data.get('furnishing', 'UNFURNISHED').upper()
        furnishing_mapping = {
            'UNFURNISHED': 'UNFURNISHED',
            'SEMI_FURNISHED': 'SEMI_FURNISHED',
            'FURNISHED': 'FURNISHED'
        }
        new_property.furnishing = furnishing_mapping.get(furnishing_str, 'UNFURNISHED')
        new_property.portal_subdomain = preferred_subdomain if preferred_subdomain else None
        
        db.session.add(new_property)
        db.session.commit()
        
        response_data = {
            'message': 'Property added successfully and is pending admin approval',
            'property': {
                'id': new_property.id,
                'title': new_property.title,
                'status': new_property.status.value
            }
        }
        
        if preferred_subdomain:
            response_data['subdomain_info'] = {
                'subdomain': preferred_subdomain,
                'future_url': f"localhost:8080",
                'note': "Subdomain will be active after admin approval"
            }
        
        return jsonify(response_data), 201
        
    except ValueError as e:
        return handle_api_error(400, f"Invalid data format: {str(e)}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Add property error: {e}')
        return handle_api_error(500, "Failed to add property")

@manager_properties_bp.route('/set-subdomain/<int:property_id>', methods=['POST'])
@manager_required
def set_property_subdomain(current_user, property_id):
    """Set subdomain for a property owned by the current manager."""
    try:
        # current_user is already provided by the manager_required decorator
        manager_user_id = current_user.id
        
        # Find the property
        property_obj = Property.query.filter_by(id=property_id, owner_id=manager_user_id).first()
        if not property_obj:
            return handle_api_error(404, "Property not found or not owned by manager")
        
        # Check if property is approved before allowing subdomain assignment
        if property_obj.status != PropertyStatus.ACTIVE:
            return handle_api_error(400, "Property must be approved (ACTIVE) before setting a subdomain")
        
        data = request.get_json()
        if not data or not data.get('subdomain'):
            return handle_api_error(400, "Subdomain is required")
        
        subdomain = data['subdomain'].lower().strip()
        
        # Validate subdomain format (alphanumeric and hyphens only)
        import re
        if not re.match(r'^[a-z0-9-]+$', subdomain):
            return handle_api_error(400, "Subdomain can only contain lowercase letters, numbers, and hyphens")
        
        if len(subdomain) < 3 or len(subdomain) > 50:
            return handle_api_error(400, "Subdomain must be between 3 and 50 characters")
        
        # Check if subdomain is already taken
        existing = Property.query.filter_by(portal_subdomain=subdomain).first()
        if existing and existing.id != property_id:
            return handle_api_error(409, "Subdomain already taken")
        
        # Set the subdomain
        property_obj.portal_subdomain = subdomain
        property_obj.portal_enabled = True
        
        db.session.commit()
        
        return jsonify({
            'message': 'Subdomain set successfully',
            'subdomain': subdomain,
            'portal_url': f'localhost:8080'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Set subdomain error: {e}')
        return handle_api_error(500, "Failed to set subdomain")

@manager_properties_bp.route('/property/<int:property_id>', methods=['GET'])
@manager_required
def get_property_details(current_user, property_id):
    """Get detailed information about a specific property owned by the current manager."""
    try:
        # current_user is already provided by the manager_required decorator
        manager_user_id = current_user.id
        
        property_obj = Property.query.filter_by(
            id=property_id, 
            owner_id=manager_user_id
        ).first()
        
        if not property_obj:
            return handle_api_error(404, "Property not found or access denied")
        
        prop_dict = property_obj.to_dict(include_owner=True)
        
        return jsonify({
            'property': prop_dict
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get property details error: {e}')
        return handle_api_error(500, "Failed to retrieve property details")

@manager_properties_bp.route('/property/<int:property_id>', methods=['PUT'])
@manager_required
def update_property(current_user, property_id):
    """Update property information for the current manager."""
    try:
        from sqlalchemy import text
        
        # current_user is already provided by the manager_required decorator
        manager_user_id = current_user.id
        
        # Check if property exists and belongs to the manager
        check_sql = text("""
            SELECT id FROM properties 
            WHERE id = :property_id AND owner_id = :owner_id
        """)
        
        result = db.session.execute(check_sql, {
            'property_id': property_id,
            'owner_id': manager_user_id
        }).fetchone()
        
        if not result:
            return handle_api_error(404, "Property not found or access denied")
        
        data = request.get_json()
        
        # Build dynamic update query
        update_fields = []
        update_values = {'property_id': property_id}
        
        if 'title' in data:
            update_fields.append('title = :title')
            update_values['title'] = data['title']
        if 'building_name' in data:
            update_fields.append('building_name = :building_name')
            update_values['building_name'] = data['building_name']
        if 'description' in data:
            update_fields.append('description = :description')
            update_values['description'] = data['description']
        if 'property_type' in data:
            update_fields.append('property_type = :property_type')
            update_values['property_type'] = data['property_type']
        # Auto-generate address from components when any location field is updated
        # First, collect all location updates
        location_updates = {}
        if 'street' in data:
            location_updates['street'] = data.get('street', '').strip() or None
            update_fields.append('street = :street')
            update_values['street'] = location_updates['street']
        if 'barangay' in data:
            location_updates['barangay'] = data.get('barangay', '').strip() or None
            update_fields.append('barangay = :barangay')
            update_values['barangay'] = location_updates['barangay']
        if 'city' in data:
            location_updates['city'] = data.get('city', 'Cebu City')
            update_fields.append('city = :city')
            update_values['city'] = location_updates['city']
        if 'province' in data:
            location_updates['province'] = data.get('province', 'Cebu')
            update_fields.append('province = :province')
            update_values['province'] = location_updates['province']
        if 'postal_code' in data:
            location_updates['postal_code'] = data.get('postal_code', '').strip() or None
            update_fields.append('postal_code = :postal_code')
            update_values['postal_code'] = location_updates['postal_code']
        
        # If any location component is being updated, auto-generate address
        if location_updates:
            # Fetch current values for fields not being updated
            current_prop = db.session.execute(
                text("SELECT street, barangay, city, province, postal_code FROM properties WHERE id = :id"),
                {'id': property_id}
            ).fetchone()
            
            street = location_updates.get('street') if 'street' in location_updates else (getattr(current_prop, 'street', None) if current_prop else None)
            barangay = location_updates.get('barangay') if 'barangay' in location_updates else (getattr(current_prop, 'barangay', None) if current_prop else None)
            city = location_updates.get('city') if 'city' in location_updates else (current_prop.city if current_prop else 'Cebu City')
            province = location_updates.get('province') if 'province' in location_updates else (current_prop.province if current_prop else 'Cebu')
            postal_code = location_updates.get('postal_code') if 'postal_code' in location_updates else (getattr(current_prop, 'postal_code', None) if current_prop else None)
            
            # Build address from components
            address_parts = []
            if street:
                address_parts.append(street)
            if barangay:
                address_parts.append(barangay)
            if city:
                address_parts.append(city)
            if province:
                address_parts.append(province)
            if postal_code:
                address_parts.append(postal_code)
            generated_address = ', '.join(address_parts) if address_parts else f"{city}, {province}"
            
            update_fields.append('address = :address')
            update_values['address'] = generated_address
        elif 'address' in data:
            # Only use provided address if no components are being updated
            update_fields.append('address = :address')
            update_values['address'] = data['address']
        if 'latitude' in data:
            update_fields.append('latitude = :latitude')
            update_values['latitude'] = float(data.get('latitude')) if data.get('latitude') else None
        if 'longitude' in data:
            update_fields.append('longitude = :longitude')
            update_values['longitude'] = float(data.get('longitude')) if data.get('longitude') else None
        if 'total_units' in data:
            update_fields.append('total_units = :total_units')
            update_values['total_units'] = data['total_units']
        if 'monthly_rent' in data:
            update_fields.append('monthly_rent = :monthly_rent')
            update_values['monthly_rent'] = data['monthly_rent']
        if 'furnishing' in data:
            update_fields.append('furnishing = :furnishing')
            update_values['furnishing'] = data['furnishing']
        if 'status' in data:
            update_fields.append('status = :status')
            update_values['status'] = data['status']
        if 'contact_person' in data:
            update_fields.append('contact_person = :contact_person')
            update_values['contact_person'] = data['contact_person']
        if 'contact_phone' in data:
            update_fields.append('contact_phone = :contact_phone')
            update_values['contact_phone'] = data['contact_phone']
        if 'contact_email' in data:
            update_fields.append('contact_email = :contact_email')
            update_values['contact_email'] = data['contact_email']
        if 'images' in data:
            update_fields.append('images = :images')
            update_values['images'] = data['images']
        if 'legal_documents' in data:
            update_fields.append('legal_documents = :legal_documents')
            update_values['legal_documents'] = data['legal_documents']
        if 'amenities' in data:
            update_fields.append('amenities = :amenities')
            update_values['amenities'] = data['amenities']
        
        # Always update the updated_at timestamp
        update_fields.append('updated_at = NOW()')
        
        if not update_fields:
            return jsonify({'message': 'No fields to update'}), 400
        
        # Build and execute update query - update_fields are safe (whitelisted column names)
        # Using parameterized query for values
        set_clause = ', '.join(update_fields)  # Safe - only whitelisted columns
        update_sql = text(f"""
            UPDATE properties 
            SET {set_clause}
            WHERE id = :property_id
        """)
        
        try:
            db.session.execute(update_sql, update_values)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Error updating property: {str(e)}', exc_info=True)
            raise
        
        # Get updated property data
        select_sql = text("""
            SELECT id, title, building_name, description, property_type, address, 
                   street, barangay, city, province, postal_code, latitude, longitude,
                   total_units, monthly_rent, 
                   furnishing, status, contact_person, contact_phone, contact_email, images, 
                   legal_documents, amenities, created_at, updated_at, owner_id
            FROM properties 
            WHERE id = :property_id
        """)
        
        property_result = db.session.execute(select_sql, {'property_id': property_id}).fetchone()
        
        if property_result:
            property_data = {
                'id': property_result.id,
                'title': property_result.title,
                'building_name': property_result.building_name,
                'description': property_result.description,
                'property_type': property_result.property_type,
                'address': property_result.address,
                'street': property_result.street if hasattr(property_result, 'street') else None,
                'barangay': property_result.barangay if hasattr(property_result, 'barangay') else None,
                'city': property_result.city,
                'province': property_result.province,
                'postal_code': property_result.postal_code if hasattr(property_result, 'postal_code') else None,
                'latitude': float(property_result.latitude) if hasattr(property_result, 'latitude') and property_result.latitude else None,
                'longitude': float(property_result.longitude) if hasattr(property_result, 'longitude') and property_result.longitude else None,
                'total_units': property_result.total_units,
                'monthly_rent': float(property_result.monthly_rent) if property_result.monthly_rent else 0,
                'furnishing': property_result.furnishing,
                'status': property_result.status,
                'contact_person': property_result.contact_person,
                'contact_phone': property_result.contact_phone,
                'contact_email': property_result.contact_email,
                'images': property_result.images,
                'legal_documents': property_result.legal_documents,
                'amenities': property_result.amenities,
                'created_at': property_result.created_at.isoformat() if property_result.created_at else None,
                'updated_at': property_result.updated_at.isoformat() if property_result.updated_at else None,
                'owner_id': property_result.owner_id
            }
        else:
            property_data = {'id': property_id}
        
        return jsonify({
            'message': 'Property updated successfully',
            'property': property_data
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Update property error: {e}')
        return handle_api_error(500, "Failed to update property")

@manager_properties_bp.route('/dashboard-stats', methods=['GET'])
@manager_required
def get_dashboard_stats(current_user):
    """Get dashboard statistics for the current manager."""
    try:
        current_app.logger.info(f"Getting dashboard stats for manager: {current_user.email} (ID: {current_user.id})")
        manager_user_id = current_user.id
        
        # Use raw SQL queries to avoid enum issues and handle string status values
        from sqlalchemy import text
        
        # Get total properties count
        total_sql = text("SELECT COUNT(*) as count FROM properties WHERE owner_id = :owner_id")
        total_result = db.session.execute(total_sql, {'owner_id': manager_user_id}).fetchone()
        total_properties = total_result.count if total_result else 0
        
        # Get active properties (status = 'active' or 'approved')
        active_sql = text("""
            SELECT COUNT(*) as count 
            FROM properties 
            WHERE owner_id = :owner_id 
            AND LOWER(status) IN ('active', 'approved')
        """)
        active_result = db.session.execute(active_sql, {'owner_id': manager_user_id}).fetchone()
        active_properties = active_result.count if active_result else 0
        
        # Get pending properties
        pending_sql = text("""
            SELECT COUNT(*) as count 
            FROM properties 
            WHERE owner_id = :owner_id 
            AND LOWER(status) = 'pending_approval'
        """)
        pending_result = db.session.execute(pending_sql, {'owner_id': manager_user_id}).fetchone()
        pending_properties = pending_result.count if pending_result else 0
        
        # Get rejected properties
        rejected_sql = text("""
            SELECT COUNT(*) as count 
            FROM properties 
            WHERE owner_id = :owner_id 
            AND LOWER(status) = 'rejected'
        """)
        rejected_result = db.session.execute(rejected_sql, {'owner_id': manager_user_id}).fetchone()
        rejected_properties = rejected_result.count if rejected_result else 0
        
        # Calculate total monthly revenue from active tenant leases (actual revenue, not property base rent)
        # Get property IDs first
        property_ids_sql = text("""
            SELECT id FROM properties 
            WHERE owner_id = :owner_id 
            AND LOWER(status) IN ('active', 'approved')
        """)
        property_ids_result = db.session.execute(property_ids_sql, {'owner_id': manager_user_id}).fetchall()
        property_ids = [row[0] for row in property_ids_result] if property_ids_result else []
        
        if property_ids:
            # Use tuple for IN clause (MySQL/MariaDB compatible)
            property_ids_tuple = tuple(property_ids) if len(property_ids) > 1 else (property_ids[0],)
            
            # Calculate real revenue from tenant_units (active leases)
            revenue_sql = text("""
                SELECT COALESCE(SUM(tu.monthly_rent), 0) as total_revenue
                FROM tenant_units tu
                INNER JOIN units u ON u.id = tu.unit_id
                WHERE u.property_id IN :property_ids
                AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                AND tu.move_in_date <= NOW()
            """)
            revenue_result = db.session.execute(revenue_sql, {'property_ids': property_ids_tuple}).fetchone()
            total_revenue = float(revenue_result.total_revenue) if revenue_result and revenue_result.total_revenue else 0.0
        else:
            total_revenue = 0.0
        
        # Get portal statistics
        portals_sql = text("""
            SELECT COUNT(*) as count 
            FROM properties 
            WHERE owner_id = :owner_id 
            AND portal_enabled = TRUE
        """)
        portals_result = db.session.execute(portals_sql, {'owner_id': manager_user_id}).fetchone()
        portals_enabled = portals_result.count if portals_result else 0
        
        # Calculate average rent
        average_rent = total_revenue / active_properties if active_properties > 0 else 0
        
        current_app.logger.info(f"Dashboard stats calculated: total={total_properties}, active={active_properties}, pending={pending_properties}, revenue={total_revenue}")
        
        return jsonify({
            'stats': {
                'total_properties': total_properties,
                'active_properties': active_properties,
                'pending_properties': pending_properties,
                'rejected_properties': rejected_properties,
                'total_monthly_revenue': total_revenue,
                'portals_enabled': portals_enabled,
                'average_rent': average_rent
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get dashboard stats error: {e}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, "Failed to retrieve dashboard statistics")

@manager_properties_bp.route('/profile/', methods=['GET'])
@manager_required
def get_manager_profile(current_user):
    """Get manager profile information."""
    try:
        manager_user = current_user
        current_app.logger.info(f"Getting profile for manager: {manager_user.email} (ID: {manager_user.id})")
        
        # Get manager's properties for activity
        try:
            recent_properties = Property.query.filter_by(owner_id=manager_user.id).order_by(Property.created_at.desc()).limit(5).all()
        except Exception as e:
            current_app.logger.error(f"Recent properties query error: {e}")
            recent_properties = []
        
        recent_activity = []
        for prop in recent_properties:
            recent_activity.append({
                'id': prop.id,
                'type': 'listing',
                'action': 'Property submitted for approval',
                'property': prop.title,
                'time': f"{(datetime.utcnow() - prop.created_at).days} days ago" if prop.created_at else "Recently",
                'icon': '🏠',
                'status': 'pending' if prop.status == 'PENDING_APPROVAL' else 'success'
            })
        
        # Build safe flat payload to avoid serialization issues
        profile = {
            'personalInfo': {
                'name': f"{manager_user.first_name} {manager_user.last_name}",
                'email': manager_user.email,
                'phone': manager_user.phone_number or '+63 912 345 6789',
                'position': 'Property Manager',
                'location': 'Cebu City, Philippines',  # Default value, field removed from database
                'bio': f'Property manager with {len(recent_properties)} properties under management.',  # Default value, field removed from database
                'avatar': '',
                'two_factor_enabled': bool(manager_user.two_factor_enabled)
            },
            'recentActivity': recent_activity
        }

        return jsonify({'profile': profile}), 200
        
    except Exception as e:
        current_app.logger.error(f'Get manager profile error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, "Failed to retrieve profile information")

@manager_properties_bp.route('/profile/', methods=['PUT'])
@manager_required
def update_manager_profile(current_user):
    """Update manager profile information."""
    try:
        manager_user = current_user
        
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        personal_info = data.get('personalInfo', {})
        
        # Update user fields
        if 'name' in personal_info:
            name_parts = personal_info['name'].split(' ', 1)
            manager_user.first_name = name_parts[0]
            manager_user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if 'phone' in personal_info:
            manager_user.phone_number = personal_info['phone']

        # Optionally allow email update if provided and unique
        if 'email' in personal_info and personal_info['email']:
            new_email = personal_info['email'].strip().lower()
            if new_email != manager_user.email:
                exists = User.query.filter_by(email=new_email).first()
                if exists:
                    return handle_api_error(409, "Email already in use")
                manager_user.email = new_email

        # location and bio fields removed - no longer persisted to database
        # Values are provided as defaults in response only
        
        db.session.commit()
        
        # Notify manager about profile update
        try:
            from app.services.notification_service import NotificationService
            NotificationService.notify_manager_account_update(
                manager_id=current_user.id,
                update_type="profile"
            )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({
            'message': 'Profile updated successfully',
            'profile': {
                'personalInfo': {
                    'name': f"{manager_user.first_name} {manager_user.last_name}",
                    'email': manager_user.email,
                    'phone': manager_user.phone_number,
                    'position': 'Property Manager',
                    'location': 'Cebu City, Philippines',  # Default value, field removed
                    'bio': f'Property manager managing properties.'  # Default value, field removed
                }
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Update manager profile error: {e}')
        return handle_api_error(500, "Failed to update profile")

@manager_properties_bp.route('/profile/change-password', methods=['POST'])
@manager_required
def change_manager_password(current_user):
    """Change manager password."""
    try:
        data = request.get_json()
        if not data:
            return handle_api_error(400, "No data provided")
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            return handle_api_error(400, "All password fields are required")
        
        if new_password != confirm_password:
            return handle_api_error(400, "New passwords do not match")
        
        if not current_user.check_password(current_password):
            return handle_api_error(400, "Current password is incorrect")
        
        if len(new_password) < 8:
            return handle_api_error(400, "New password must be at least 8 characters long")
        
        current_user.set_password(new_password)
        db.session.commit()
        
        # Notify manager about password change
        try:
            from app.services.notification_service import NotificationService
            NotificationService.notify_manager_account_update(
                manager_id=current_user.id,
                update_type="password"
            )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Change manager password error: {e}')
        return handle_api_error(500, "Failed to change password")

@manager_properties_bp.route('/profile/2fa/email/enable', methods=['POST'])
@manager_required
def enable_manager_2fa_email(current_user):
    """Enable email-based 2FA for manager."""
    try:
        current_user.two_factor_enabled = True
        db.session.commit()
        
        return jsonify({
            'message': '2FA via email enabled successfully',
            'two_factor_enabled': True
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Enable manager 2FA error: {e}')
        return handle_api_error(500, "Failed to enable 2FA")

@manager_properties_bp.route('/profile/2fa/email/disable', methods=['POST'])
@manager_required
def disable_manager_2fa_email(current_user):
    """Disable email-based 2FA for manager."""
    try:
        current_user.two_factor_enabled = False
        current_user.two_factor_email_code = None
        current_user.two_factor_email_expires = None
        db.session.commit()
        
        return jsonify({
            'message': '2FA via email disabled successfully',
            'two_factor_enabled': False
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Disable manager 2FA error: {e}')
        return handle_api_error(500, "Failed to disable 2FA")

@manager_properties_bp.route('/profile/upload-image', methods=['POST'])
@manager_required
def upload_manager_profile_image(current_user):
    """Upload and set the manager's profile image."""
    try:
        if 'image' not in request.files:
            return handle_api_error(400, "No image file provided")

        file = request.files['image']
        if not file or file.filename == '':
            return handle_api_error(400, "No image selected")

        from app.utils.file_helpers import save_uploaded_file, IMAGE_EXTENSIONS
        import os
        
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
        current_app.logger.error(f'Upload manager profile image error: {e}')
        return handle_api_error(500, "Failed to upload profile image")

@manager_properties_bp.route('/upload-image', methods=['POST'])
@manager_required
def upload_property_image(current_user):
    """Endpoint for property managers to upload a property image and get back the public URL."""
    try:
        if 'image' not in request.files:
            return handle_api_error(400, "No image file provided")
        file = request.files['image']
        if not file or file.filename == '':
            return handle_api_error(400, "No image selected")
        from app.utils.file_helpers import save_uploaded_file, IMAGE_EXTENSIONS
        import os
        # Save file to instance/uploads/properties directory
        upload_folder = os.path.join(current_app.instance_path,
                                    current_app.config.get('UPLOAD_FOLDER', 'uploads'),
                                    'properties')
        max_size = 5 * 1024 * 1024  # 5MB
        success, filename, error = save_uploaded_file(
            file, upload_folder, allowed_extensions=IMAGE_EXTENSIONS, max_size=max_size
        )
        if not success:
            return handle_api_error(400, error or "Failed to save image")
        # Return the public URL, matching /uploads/properties/<filename>
        public_url = f"/uploads/properties/{filename}"
        return jsonify({
            'message': 'Image uploaded',
            'url': public_url
        }), 200
    except Exception as e:
        current_app.logger.error(f'Upload property image error: {e}')
        return handle_api_error(500, "Failed to upload image")

@manager_properties_bp.route('/upload-legal-document', methods=['POST'])
@manager_required
def upload_legal_document(current_user):
    """Endpoint for property managers to upload a legal document and get back the file path."""
    try:
        if 'document' not in request.files:
            return handle_api_error(400, "No document file provided")
        file = request.files['document']
        if not file or file.filename == '':
            return handle_api_error(400, "No document selected")
        
        from app.utils.file_helpers import save_uploaded_file
        import os
        
        # Allowed extensions for legal documents
        DOCUMENT_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
        
        # Save file to instance/uploads/legal-documents directory
        upload_folder = os.path.join(
            current_app.instance_path,
            current_app.config.get('UPLOAD_FOLDER', 'uploads'),
            'legal-documents'
        )
        max_size = 50 * 1024 * 1024  # 50MB for documents
        
        success, filename, error = save_uploaded_file(
            file, 
            upload_folder, 
            allowed_extensions=DOCUMENT_EXTENSIONS, 
            max_size=max_size
        )
        
        if not success:
            return handle_api_error(400, error or "Failed to save document")
        
        # Return the server file path (relative to instance/uploads)
        # This will be used to construct the full path when needed
        file_path = os.path.join('legal-documents', filename)
        
        return jsonify({
            'message': 'Document uploaded successfully',
            'path': file_path,
            'filename': filename,
            'size': file.content_length if hasattr(file, 'content_length') else None
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Upload legal document error: {e}')
        import traceback
        current_app.logger.error(traceback.format_exc())
        return handle_api_error(500, "Failed to upload document")

@manager_properties_bp.route('/upload-unit-image', methods=['POST'])
@manager_required
def upload_unit_image(current_user):
    """Endpoint for managers to upload a unit (space) image and get back the public URL."""
    try:
        if 'image' not in request.files:
            return handle_api_error(400, "No image file provided")
        file = request.files['image']
        if not file or file.filename == '':
            return handle_api_error(400, "No image selected")
        from app.utils.file_helpers import save_uploaded_file, IMAGE_EXTENSIONS
        import os
        # Save file to instance/uploads/unit-images directory
        upload_folder = os.path.join(current_app.instance_path,
                                    current_app.config.get('UPLOAD_FOLDER', 'uploads'),
                                    'unit-images')
        max_size = 5 * 1024 * 1024
        success, filename, error = save_uploaded_file(
            file, upload_folder, allowed_extensions=IMAGE_EXTENSIONS, max_size=max_size
        )
        if not success:
            return handle_api_error(400, error or "Failed to save image")
        # Return the public URL, matching /uploads/unit-images/<filename>
        public_url = f"/uploads/unit-images/{filename}"
        return jsonify({'message': 'Image uploaded', 'url': public_url}), 200
    except Exception as e:
        current_app.logger.error(f'Upload unit image error: {e}')
        return handle_api_error(500, "Failed to upload image")

