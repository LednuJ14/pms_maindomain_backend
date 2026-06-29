"""
Public Units API for Tenant Access
This module provides public endpoints for tenants to view available units.
"""
import math
from flask import Blueprint, request, jsonify, current_app
from app import db
from sqlalchemy import text

public_units_bp = Blueprint('public_units', __name__)

@public_units_bp.route('/active', methods=['GET'])
def get_active_units():
    """
    Get active units
    ---
    tags:
      - Public Units
    summary: Get all active/available units for tenant browsing
    description: Retrieve a list of all active and available units that tenants can browse and inquire about
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
        description: Search term
      - in: query
        name: latitude
        type: number
        description: Latitude for location-based search
      - in: query
        name: longitude
        type: number
        description: Longitude for location-based search
      - in: query
        name: radius
        type: number
        description: Search radius in meters
    responses:
      200:
        description: Active units retrieved successfully
        schema:
          type: object
          properties:
            units:
              type: array
              items:
                type: object
            total:
              type: integer
            page:
              type: integer
      500:
        description: Server error
    """
    try:
        params = request.args
        page = int(params.get('page', 1))
        per_page = min(int(params.get('per_page', 20)), 100)

        # Build filters against units/properties
        filters = []
        binds = {}

        # Filter out occupied units - a unit is occupied if there's an active tenant_units record
        # (move_out_date is NULL or in the future). We'll add this in the JOIN clause.
        # property active - we'll try with status filter and retry without it if it fails
        # Store the status filter separately so we can remove it if needed
        status_filter = "(p.status = 'active' OR p.status = 'approved')"
        # Also filter out draft units - only show published units (vacant, occupied, etc. but not draft)
        # Handle NULL status as draft (unpublished units)
        unit_status_filter = "(u.status IS NOT NULL AND LOWER(u.status) != 'draft')"

        # Distance-based location filter (if coordinates provided) - takes priority over text search
        lat = params.get('latitude', type=float)
        lng = params.get('longitude', type=float)
        radius = params.get('radius', type=float) or 100  # Default 100 meters
        
        if lat is not None and lng is not None:
            # Haversine formula for distance calculation (in meters)
            # Formula: distance = 6371000 * acos(cos(radians(lat1)) * cos(radians(lat2)) * cos(radians(lng2) - radians(lng1)) + sin(radians(lat1)) * sin(radians(lat2)))
            # We'll use a bounding box approximation for better performance, then filter by exact distance
            # Approximate 1 degree latitude ≈ 111km, 1 degree longitude ≈ 111km * cos(latitude)
            # For 100m radius: ~0.0009 degrees
            lat_offset = radius / 111000.0  # Convert meters to degrees (approximate)
            # Longitude offset depends on latitude (longitude lines get closer near poles)
            lng_offset = radius / (111000.0 * math.cos(math.radians(lat))) if lat != 0 else radius / 111000.0
            
            # Filter by bounding box first for performance, then exact distance
            # Check if latitude/longitude columns exist (for backward compatibility)
            filters.append("""
                (p.latitude IS NOT NULL AND p.longitude IS NOT NULL AND
                p.latitude BETWEEN :min_lat AND :max_lat AND
                p.longitude BETWEEN :min_lng AND :max_lng AND
                (6371000 * acos(
                    GREATEST(-1, LEAST(1, 
                        cos(radians(:search_lat)) * cos(radians(p.latitude)) * 
                        cos(radians(p.longitude) - radians(:search_lng)) + 
                        sin(radians(:search_lat)) * sin(radians(p.latitude))
                    ))
                )) <= :radius_meters)
            """)
            binds['min_lat'] = lat - lat_offset
            binds['max_lat'] = lat + lat_offset
            binds['min_lng'] = lng - lng_offset
            binds['max_lng'] = lng + lng_offset
            binds['search_lat'] = lat
            binds['search_lng'] = lng
            binds['radius_meters'] = radius
        else:
            # Text-based location filter - only use if coordinates not provided
            location_filter = params.get('city') or params.get('location') or ''
            if location_filter:
                location_term = location_filter.strip()
                # Search in street, barangay, or city
                filters.append("(p.street LIKE :location OR p.barangay LIKE :location OR p.city LIKE :location)")
                binds['location'] = f"%{location_term}%"

        if params.get('type'):
            filters.append("p.property_type = :ptype")
            binds['ptype'] = params.get('type').strip().lower()

        if params.get('bedrooms'):
            try:
                binds['beds'] = int(params.get('bedrooms'))
                filters.append("u.bedrooms >= :beds")
            except ValueError:
                pass

        if params.get('min_price'):
            try:
                binds['min_price'] = float(params.get('min_price'))
                filters.append("u.monthly_rent >= :min_price")
            except ValueError:
                pass

        if params.get('max_price'):
            try:
                binds['max_price'] = float(params.get('max_price'))
                filters.append("u.monthly_rent <= :max_price")
            except ValueError:
                pass

        # Search filter - search across property title, description, city, street, barangay, and amenities
        search_term = params.get('search', '').strip()
        if search_term:
            filters.append("""
                (p.title LIKE :search_term OR 
                 p.description LIKE :search_term OR 
                 p.city LIKE :search_term OR 
                 p.street LIKE :search_term OR 
                 p.barangay LIKE :search_term OR
                 p.amenities LIKE :search_term OR
                 u.description LIKE :search_term)
            """)
            binds['search_term'] = f"%{search_term}%"

        # Try with status filter first
        filters.append(status_filter)
        filters.append(unit_status_filter)
        where_sql = " AND ".join(filters) if filters else "1=1"
        
        try:
            # total count - exclude units with active tenant assignments
            total_sql = text(f"""
              SELECT COUNT(*) AS cnt
              FROM units u
              JOIN properties p ON p.id = u.property_id
              LEFT JOIN tenant_units tu ON tu.unit_id = u.id 
                  AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
              WHERE {where_sql}
                  AND tu.id IS NULL
            """)
            total_count = db.session.execute(total_sql, binds).scalar() or 0

            offset = (page - 1) * per_page
            list_sql = text(f"""
              SELECT
                u.id AS unit_id,
                u.unit_name,
                u.bedrooms,
                u.bathrooms,
                u.monthly_rent,
                u.size_sqm,
                u.images,
                u.floor_number,
                u.parking_spaces,
                u.amenities,
                u.status AS unit_status,
                u.description AS unit_description,
                u.security_deposit,
                p.id AS property_id,
                p.building_name,
                p.address,
                p.street,
                p.barangay,
                p.postal_code,
                p.latitude,
                p.longitude,
                p.title AS property_title,
                p.city,
                p.province,
                p.contact_email,
                p.contact_phone,
                p.property_type,
                p.description AS property_description,
                p.contact_person,
                p.owner_id
              FROM units u
              JOIN properties p ON p.id = u.property_id
              LEFT JOIN tenant_units tu ON tu.unit_id = u.id 
                  AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
              WHERE {where_sql}
                  AND tu.id IS NULL
              ORDER BY COALESCE(u.updated_at, u.created_at) DESC
              LIMIT :limit OFFSET :offset
            """)
            rows = db.session.execute(list_sql, {**binds, 'limit': per_page, 'offset': offset}).mappings().all()
        except Exception as query_error:
            error_str = str(query_error).lower()
            # If error is about missing status column, retry without status filter
            if 'status' in error_str and ('unknown column' in error_str or 'doesn\'t exist' in error_str):
                current_app.logger.warning(f"Status column error, retrying without status filter: {str(query_error)}")
                # Remove status filters and retry (but keep unit status filter if possible)
                filters_without_status = [f for f in filters if f != status_filter and f != unit_status_filter]
                # Try to keep unit status filter if units table has status column
                try:
                    # Test if units.status exists by checking if the error mentions properties table specifically
                    if 'properties' in error_str.lower() or 'p.status' in error_str.lower():
                        # Only property status is missing, keep unit status filter
                        filters_without_status.append(unit_status_filter)
                except:
                    pass
                where_sql = " AND ".join(filters_without_status) if filters_without_status else "1=1"
                
                total_sql = text(f"""
                  SELECT COUNT(*) AS cnt
                  FROM units u
                  JOIN properties p ON p.id = u.property_id
                  LEFT JOIN tenant_units tu ON tu.unit_id = u.id 
                      AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                  WHERE {where_sql}
                      AND tu.id IS NULL
                """)
                total_count = db.session.execute(total_sql, binds).scalar() or 0

                offset = (page - 1) * per_page
                list_sql = text(f"""
                  SELECT
                    u.id AS unit_id,
                    u.unit_name,
                    u.bedrooms,
                    u.bathrooms,
                    u.monthly_rent,
                    u.size_sqm,
                    u.images,
                    u.floor_number,
                    u.parking_spaces,
                    u.amenities,
                    u.status AS unit_status,
                    u.description AS unit_description,
                    u.security_deposit,
                    p.id AS property_id,
                    p.building_name,
                    p.address,
                    p.street,
                    p.barangay,
                    p.title AS property_title,
                    p.city,
                    p.province,
                    p.postal_code,
                    p.latitude,
                    p.longitude,
                    p.contact_email,
                    p.contact_phone,
                    p.property_type,
                    p.description AS property_description,
                    p.contact_person,
                    p.owner_id
                  FROM units u
                  JOIN properties p ON p.id = u.property_id
                  LEFT JOIN tenant_units tu ON tu.unit_id = u.id 
                      AND (tu.move_out_date IS NULL OR tu.move_out_date > CURDATE())
                  WHERE {where_sql}
                      AND tu.id IS NULL
                  ORDER BY COALESCE(u.updated_at, u.created_at) DESC
                  LIMIT :limit OFFSET :offset
                """)
                rows = db.session.execute(list_sql, {**binds, 'limit': per_page, 'offset': offset}).mappings().all()
            else:
                # Re-raise if it's a different error
                raise

        properties_data = []
        for r in rows:
            images = []
            if r.get('images'):
                try:
                    import json
                    data = json.loads(r['images'])
                    if isinstance(data, list):
                        images = [s for s in data if isinstance(s, str) and (s.startswith('http') or s.startswith('/'))]
                except Exception:
                    pass

            # Parse amenities from JSON
            amenities = {}
            if r.get('amenities'):
                try:
                    import json
                    amenities_data = json.loads(r['amenities'])
                    if isinstance(amenities_data, dict):
                        amenities = amenities_data
                except Exception:
                    pass

            # Parse property amenities if available (removed for now as field might not exist)
            property_amenities = []

            properties_data.append({
                'id': r['unit_id'],
                'property_id': r.get('property_id'),
                'title': f"{r.get('unit_name')} at {r.get('building_name')}",
                'description': r.get('unit_description') or r.get('property_description'),
                'property_type': r.get('property_type') or 'apartment',
                'status': r.get('unit_status') or 'active',
                'city': r.get('city') or 'Cebu City',
                'province': r.get('province') or 'Cebu',
                'street': r.get('street') or None,
                'barangay': r.get('barangay') or None,
                'postal_code': r.get('postal_code') or None,
                'address': r.get('address') or None,  # Keep full address as fallback
                'latitude': float(r.get('latitude')) if r.get('latitude') is not None else None,
                'longitude': float(r.get('longitude')) if r.get('longitude') is not None else None,
                'monthly_rent': float(r['monthly_rent']) if r.get('monthly_rent') is not None else None,
                'bedrooms': r.get('bedrooms'),
                'bathrooms': r.get('bathrooms') or 'own',  # ENUM: 'own' or 'share'
                'floor_area': r.get('size_sqm'),
                'images': images,
                'owner': {
                    'id': None,
                    'first_name': None,
                    'last_name': None,
                    'email': r.get('contact_email'),
                    'phone': r.get('contact_phone')
                },
                'unit_details': {
                    'floor_number': r.get('floor_number'),
                    'parking_spaces': r.get('parking_spaces'),
                    'furnished': amenities.get('furnished', False),
                    'security_deposit': float(r.get('security_deposit') or 0),
                    'unit_status': r.get('unit_status'),
                    'unit_description': r.get('unit_description'),
                    'amenities': {
                        'balcony': amenities.get('balcony', False),
                        'air_conditioning': amenities.get('air_conditioning', False),
                        'wifi': amenities.get('wifi', False),
                        'security': amenities.get('security', False)
                    }
                },
                'property_info': {
                    'building_name': r.get('building_name'),
                    'address': r.get('address'),
                    'property_title': r.get('property_title'),
                    'property_description': r.get('property_description'),
                    'contact_person': r.get('contact_person')
                },
                'contact_info': {
                    'email': r.get('contact_email'),
                    'phone': r.get('contact_phone'),
                    'contact_person': r.get('contact_person')
                },
                'financial_info': {
                    'monthly_rent': float(r['monthly_rent']) if r.get('monthly_rent') is not None else None,
                    'security_deposit': float(r.get('security_deposit') or 0)
                },
                'availability_info': {
                    'unit_status': r.get('unit_status')
                }
            })

        total_pages = (total_count + per_page - 1) // per_page if per_page else 1
        return jsonify({
            'properties': properties_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
                'next_num': page + 1 if page < total_pages else None,
                'prev_num': page - 1 if page > 1 else None,
                'total_items': total_count
            }
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        current_app.logger.error(f'Get active units error: {e}')
        current_app.logger.error(f'Error traceback: {error_trace}')
        return jsonify({
            'error': 'Failed to retrieve available units',
            'message': f'An error occurred while fetching available units: {str(e)}',
            'details': str(e) if current_app.debug else None
        }), 500

def extract_city_from_address(address):
    """Extract city name from address string."""
    if not address:
        return 'Cebu City'
    
    # Common Cebu cities/areas
    cebu_areas = ['Cebu City', 'Mandaue', 'Lapu-Lapu', 'Talisay', 'Minglanilla', 'Consolacion']
    address_lower = address.lower()
    
    for area in cebu_areas:
        if area.lower() in address_lower:
            return area
    
    return 'Cebu City'  # Default

def parse_amenities(amenities_json):
    """Parse amenities JSON string into a list."""
    if not amenities_json:
        return []
    
    try:
        import json
        amenities = json.loads(amenities_json)
        if isinstance(amenities, list):
            return amenities
        elif isinstance(amenities, str):
            return [amenities]
    except:
        pass
    
    return []