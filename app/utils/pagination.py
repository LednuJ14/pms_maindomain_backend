"""
Pagination utilities
"""
from flask import request, url_for

def paginate_query(query, page=None, per_page=None, max_per_page=100):
    """
    Paginate a SQLAlchemy query.
    
    Args:
        query: SQLAlchemy query object
        page (int): Page number (1-indexed)
        per_page (int): Items per page
        max_per_page (int): Maximum items per page
        
    Returns:
        dict: Pagination result with items and metadata
    """
    # Get pagination parameters from request if not provided
    if page is None:
        page = request.args.get('page', 1, type=int)
    
    if per_page is None:
        per_page = request.args.get('per_page', 10, type=int)
    
    # Ensure per_page doesn't exceed maximum
    per_page = min(per_page, max_per_page)
    
    # Execute pagination
    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return {
        'items': pagination.items,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_prev': pagination.has_prev,
            'has_next': pagination.has_next,
            'prev_num': pagination.prev_num,
            'next_num': pagination.next_num
        }
    }

def get_pagination_links(pagination, endpoint, **kwargs):
    """
    Generate pagination links for API responses.
    
    Args:
        pagination: Flask-SQLAlchemy pagination object
        endpoint (str): Flask endpoint name
        **kwargs: Additional URL parameters
        
    Returns:
        dict: Pagination links
    """
    links = {}
    
    if pagination.has_prev:
        links['prev'] = url_for(endpoint, page=pagination.prev_num, **kwargs, _external=True)
        links['first'] = url_for(endpoint, page=1, **kwargs, _external=True)
    
    if pagination.has_next:
        links['next'] = url_for(endpoint, page=pagination.next_num, **kwargs, _external=True)
        links['last'] = url_for(endpoint, page=pagination.pages, **kwargs, _external=True)
    
    links['self'] = url_for(endpoint, page=pagination.page, **kwargs, _external=True)
    
    return links
