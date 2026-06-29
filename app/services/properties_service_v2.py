"""
Properties service: encapsulates listing, retrieval, creation for properties
"""
from datetime import datetime
from typing import Dict, Any
from sqlalchemy import or_
from app import db
from app.models.property import Property, PropertyType, PropertyStatus, FurnishingType
from app.utils.pagination import paginate_query
from app.utils.validators import validate_required_fields, validate_numeric_range, sanitize_input


from app.errors import ValidationAppError

class PropertiesValidationError(ValidationAppError):
    def __init__(self, message: str, details: Dict | None = None):
        super().__init__(message)
        self.details = details or {}


class PropertiesService:
    def list_public(self, params: Dict[str, Any]) -> Dict:
        page = int(params.get('page', 1) or 1)
        per_page = int(params.get('per_page', 10) or 10)
        filters = {
            'type': params.get('type'),
            'city': params.get('city'),
            'min_price': params.get('min_price'),
            'max_price': params.get('max_price'),
            'bedrooms': params.get('bedrooms'),
            'search': (params.get('search') or '').strip(),
        }
        # Validate property_type eagerly for better error messaging
        if filters['type']:
            try:
                PropertyType(filters['type'])
            except ValueError:
                raise PropertiesValidationError('Invalid property type', {
                    'message': f"Type must be one of: {', '.join([t.value for t in PropertyType])}"
                })

        from app.repositories.property_repository import PropertyRepository
        repo = PropertyRepository()
        query = repo.list_public_filtered(filters)
        query = query.order_by(Property.created_at.desc())
        result = paginate_query(query, page, per_page)
        return {
            'properties': [prop.to_dict() for prop in result['items']],
            'pagination': result['pagination'],
        }

    def list_my_properties(self, current_user, params: Dict[str, Any]) -> Dict:
        page = int(params.get('page', 1) or 1)
        per_page = int(params.get('per_page', 10) or 10)
        status_filter = params.get('status')
        from app.repositories.property_repository import PropertyRepository
        repo = PropertyRepository()
        query = repo.list_by_owner(current_user.id, status_filter)
        result = paginate_query(query, page, per_page)
        return {
            'properties': [prop.to_dict(include_stats=True) for prop in result['items']],
            'pagination': result['pagination'],
        }

    def list_active_for_inquiries(self, params: Dict[str, Any]) -> Dict:
        """List only active properties available for tenant inquiries."""
        page = int(params.get('page', 1) or 1)
        per_page = int(params.get('per_page', 20) or 20)  # More properties per page for inquiries
        
        # Get only active properties
        from app.repositories.property_repository import PropertyRepository
        repo = PropertyRepository()
        
        # Use the existing public filtered method but only for active properties
        # Since list_public_filtered already filters for active properties, we don't need to pass status
        filters = {}
        query = repo.list_public_filtered(filters)
        query = query.order_by(Property.created_at.desc())
        
        result = paginate_query(query, page, per_page)
        
        # Format properties for inquiry UI - flatten the structure to match frontend expectations
        properties_data = []
        for prop in result['items']:
            prop_dict = prop.to_dict(include_owner=True)
            # Flatten the structure for frontend compatibility
            flat_prop = {
                'id': prop_dict['id'],
                'title': prop_dict['title'],
                'description': prop_dict['description'],
                'property_type': prop_dict['property_type'],
                'status': prop_dict['status'],
                'city': prop_dict['address']['city'],
                'province': prop_dict['address']['province'],
                'monthly_rent': prop_dict['pricing']['monthly_rent'],
                'bedrooms': prop_dict['details']['bedrooms'],
                'bathrooms': prop_dict['details']['bathrooms'],
                'images': [img['url'] for img in prop_dict['images']] if prop_dict['images'] else [],
                'owner': prop_dict.get('owner'),
                'created_at': prop_dict['created_at']
            }
            properties_data.append(flat_prop)
        
        return {
            'properties': properties_data,
            'pagination': result['pagination'],
        }

    def get_by_id_public(self, property_id: int) -> Dict:
        property_obj = Property.query.get_or_404(property_id)
        property_obj.increment_view_count()
        return {'property': property_obj.to_dict(include_owner=True, include_stats=True)}

    def create(self, current_user, payload: Dict[str, Any]) -> Dict:
        ok, missing = validate_required_fields(payload, ['title', 'property_type', 'address_line1', 'city', 'monthly_rent'])
        if not ok:
            raise PropertiesValidationError('Missing required fields', {'missing_fields': missing})

        try:
            property_type = PropertyType(payload['property_type'])
        except ValueError:
            raise PropertiesValidationError('Invalid property type', {
                'message': f"Type must be one of: {', '.join([t.value for t in PropertyType])}"
            })

        is_valid_rent, rent_error = validate_numeric_range(payload['monthly_rent'], min_value=1000, max_value=1000000, field_name="Monthly rent")
        if not is_valid_rent:
            raise PropertiesValidationError('Invalid monthly rent', {'message': rent_error})

        property_obj = Property(
            title=sanitize_input(payload['title']),
            property_type=property_type,
            address_line1=sanitize_input(payload['address_line1']),
            city=sanitize_input(payload['city']),
            monthly_rent=payload['monthly_rent'],
            owner_id=current_user.id,
        )

        optional_fields = {
            'description': str,
            'address_line2': str,
            'barangay': str,
            'province': str,
            'postal_code': str,
            'bedrooms': int,
            'bathrooms': str,
            'floor_area': float,
            'lot_area': float,
            'parking_spaces': int,
            'security_deposit': float,
            'advance_payment': int,
            'maximum_occupants': int,
        }
        for field, field_type in optional_fields.items():
            if field in payload and payload[field] is not None:
                try:
                    if field_type == str:
                        setattr(property_obj, field, sanitize_input(str(payload[field])))
                    else:
                        setattr(property_obj, field, field_type(payload[field]))
                except (ValueError, TypeError):
                    raise PropertiesValidationError(f'Invalid {field}', {'message': f'{field} must be a valid {field_type.__name__}'})

        if 'furnishing' in payload and payload['furnishing']:
            try:
                property_obj.furnishing = FurnishingType(payload['furnishing'])
            except ValueError:
                raise PropertiesValidationError('Invalid furnishing type', {
                    'message': f"Furnishing must be one of: {', '.join([f.value for f in FurnishingType])}"
                })

        if 'available_from' in payload and payload['available_from']:
            try:
                property_obj.available_from = datetime.strptime(payload['available_from'], '%Y-%m-%d').date()
            except ValueError:
                raise PropertiesValidationError('Invalid date format', {'message': 'Available from date must be in YYYY-MM-DD format'})

        property_obj.contact_name = current_user.get_full_name()
        property_obj.contact_email = current_user.email
        property_obj.contact_phone = current_user.phone_number

        if 'contact_name' in payload:
            property_obj.contact_name = sanitize_input(payload['contact_name'])
        if 'contact_email' in payload:
            property_obj.contact_email = sanitize_input(payload['contact_email'])
        if 'contact_phone' in payload:
            property_obj.contact_phone = sanitize_input(payload['contact_phone'])

        db.session.add(property_obj)
        db.session.flush()
        property_obj.generate_slug()
        db.session.commit()

        if current_user.subscription:
            current_user.subscription.update_properties_used()

        return {
            'message': 'Property created successfully',
            'property': property_obj.to_dict(include_owner=True),
        }
