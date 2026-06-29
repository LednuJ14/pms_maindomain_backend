"""
Input validation and sanitization utilities
"""
import re
import html
from typing import Any, Optional
from flask import current_app


def sanitize_string(value: Any, max_length: Optional[int] = None, allow_html: bool = False) -> str:
    """
    Sanitize a string input.
    
    Args:
        value: Input value to sanitize
        max_length: Maximum allowed length
        allow_html: If False, escape HTML entities
        
    Returns:
        Sanitized string
    """
    if value is None:
        return ""
    
    # Convert to string
    str_value = str(value).strip()
    
    # Remove null bytes
    str_value = str_value.replace('\x00', '')
    
    # Escape HTML if not allowed
    if not allow_html:
        str_value = html.escape(str_value)
    
    # Truncate if max_length specified
    if max_length and len(str_value) > max_length:
        str_value = str_value[:max_length]
        current_app.logger.warning(f'String truncated to {max_length} characters')
    
    return str_value


def sanitize_email(email: str) -> Optional[str]:
    """
    Sanitize and validate email address.
    
    Args:
        email: Email address to sanitize
        
    Returns:
        Sanitized email or None if invalid
    """
    if not email:
        return None
    
    email = email.strip().lower()
    
    # Basic email validation pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return None
    
    # Additional length check
    if len(email) > 254:  # RFC 5321 limit
        return None
    
    return email


def sanitize_phone(phone: str) -> Optional[str]:
    """
    Sanitize phone number (remove non-digit characters except +).
    
    Args:
        phone: Phone number to sanitize
        
    Returns:
        Sanitized phone number or None if invalid
    """
    if not phone:
        return None
    
    # Remove all characters except digits, +, spaces, hyphens, parentheses
    cleaned = re.sub(r'[^\d\+\s\-\(\)]', '', phone)
    cleaned = cleaned.strip()
    
    # Basic validation - should have at least 7 digits
    digits_only = re.sub(r'\D', '', cleaned)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return None
    
    return cleaned


def sanitize_integer(value: Any, min_value: Optional[int] = None, max_value: Optional[int] = None) -> Optional[int]:
    """
    Sanitize and validate integer.
    
    Args:
        value: Value to convert to integer
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Integer value or None if invalid
    """
    if value is None:
        return None
    
    try:
        int_value = int(value)
        
        if min_value is not None and int_value < min_value:
            return None
        if max_value is not None and int_value > max_value:
            return None
        
        return int_value
    except (ValueError, TypeError):
        return None


def sanitize_float(value: Any, min_value: Optional[float] = None, max_value: Optional[float] = None) -> Optional[float]:
    """
    Sanitize and validate float.
    
    Args:
        value: Value to convert to float
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Float value or None if invalid
    """
    if value is None:
        return None
    
    try:
        float_value = float(value)
        
        if min_value is not None and float_value < min_value:
            return None
        if max_value is not None and float_value > max_value:
            return None
        
        return float_value
    except (ValueError, TypeError):
        return None


def sanitize_sql_identifier(identifier: str) -> Optional[str]:
    """
    Sanitize SQL identifier (table/column name) to prevent SQL injection.
    Only allows alphanumeric characters and underscores.
    
    Args:
        identifier: SQL identifier to sanitize
        
    Returns:
        Sanitized identifier or None if invalid
    """
    if not identifier:
        return None
    
    # Only allow alphanumeric and underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        return None
    
    return identifier


def validate_file_extension(filename: str, allowed_extensions: set) -> bool:
    """
    Validate file extension against allowed list.
    
    Args:
        filename: Filename to check
        allowed_extensions: Set of allowed extensions (lowercase, without dot)
        
    Returns:
        True if extension is allowed
    """
    if not filename or '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other security issues.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "file"
    
    # Remove path components
    filename = filename.replace('\\', '/').split('/')[-1]
    
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Remove or replace dangerous characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    
    return filename or "file"

