"""
Property repository: encapsulates DB access related to properties
"""
from typing import Optional
from app import db
from app.models.property import Property


class PropertyRepository:
    def get_by_id(self, property_id: int) -> Optional[Property]:
        return Property.query.get(property_id)

    def get_by_subdomain(self, subdomain: str) -> Optional[Property]:
        return Property.query.filter_by(portal_subdomain=subdomain, portal_enabled=True).first()

    def list_public_filtered(self, filters: dict):
        """Return a SQLAlchemy query for active properties with optional filters.
        filters keys: type, city, min_price, max_price, bedrooms, search
        """
        from sqlalchemy import or_
        from app.models.property import PropertyStatus
        query = Property.query.filter_by(status=PropertyStatus.ACTIVE)
        if filters.get('type'):
            from app.models.property import PropertyType
            try:
                prop_type = PropertyType(filters['type'])
                query = query.filter(Property.property_type == prop_type)
            except ValueError:
                # caller should validate type; return unfiltered
                pass
        if filters.get('city') and filters.get('city').strip():
            query = query.filter(Property.city.ilike(f"%{filters['city']}%"))
        if filters.get('min_price') is not None and str(filters.get('min_price')).strip():
            try:
                min_price = float(filters['min_price'])
                query = query.filter(Property.monthly_rent >= min_price)
            except ValueError:
                # Skip filter if conversion fails
                pass
        if filters.get('max_price') is not None and str(filters.get('max_price')).strip():
            try:
                max_price = float(filters['max_price'])
                query = query.filter(Property.monthly_rent <= max_price)
            except ValueError:
                # Skip filter if conversion fails
                pass
        if filters.get('bedrooms') is not None and str(filters.get('bedrooms')).strip():
            try:
                bedrooms = int(filters['bedrooms'])
                query = query.filter(Property.bedrooms == bedrooms)
            except ValueError:
                # Skip filter if conversion fails
                pass
        if filters.get('search') and filters.get('search').strip():
            st = f"%{filters['search'].strip()}%"
            query = query.filter(
                or_(
                    Property.title.ilike(st),
                    Property.description.ilike(st),
                    Property.address_line1.ilike(st),
                    Property.city.ilike(st),
                    Property.barangay.ilike(st),
                )
            )
        return query

    def list_by_owner(self, owner_id: int, status: str | None):
        """Return a SQLAlchemy query for properties owned by a user with optional status filter."""
        from app.models.property import PropertyStatus
        query = Property.query.filter_by(owner_id=owner_id)
        if status:
            try:
                query = query.filter(Property.status == PropertyStatus(status))
            except ValueError:
                # caller should validate
                pass
        return query.order_by(Property.created_at.desc())
