"""
Input validation utilities
"""
import re
import phonenumbers
from email_validator import validate_email as email_validate, EmailNotValidError
from datetime import datetime, date

def validate_email(email):
    """
    Validate email address format.
    
    Args:
        email (str): Email address to validate
        
    Returns:
        tuple: (is_valid: bool, normalized_email: str, error_message: str)
    """
    try:
        # Validate and get normalized result
        validated_email = email_validate(email)
        return True, validated_email.email, None
    except EmailNotValidError as e:
        return False, None, str(e)

def validate_phone(phone_number, country_code='PH'):
    """
    Validate phone number format.
    
    Args:
        phone_number (str): Phone number to validate
        country_code (str): Country code for validation (default: PH for Philippines)
        
    Returns:
        tuple: (is_valid: bool, formatted_number: str, error_message: str)
    """
    try:
        # Parse phone number
        parsed_number = phonenumbers.parse(phone_number, country_code)
        
        # Check if number is valid
        if not phonenumbers.is_valid_number(parsed_number):
            return False, None, "Invalid phone number format"
        
        # Format number in international format
        formatted_number = phonenumbers.format_number(
            parsed_number, 
            phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        
        return True, formatted_number, None
        
    except phonenumbers.NumberParseException as e:
        error_messages = {
            phonenumbers.NumberParseException.INVALID_COUNTRY_CODE: "Invalid country code",
            phonenumbers.NumberParseException.NOT_A_NUMBER: "Not a valid phone number",
            phonenumbers.NumberParseException.TOO_SHORT_NSN: "Phone number too short",
            phonenumbers.NumberParseException.TOO_LONG: "Phone number too long"
        }
        return False, None, error_messages.get(e.error_type, "Invalid phone number")

def validate_password_strength(password):
    """
    Validate password strength.
    
    Args:
        password (str): Password to validate
        
    Returns:
        tuple: (is_valid: bool, errors: list, strength_score: int)
    """
    errors = []
    score = 0
    
    # Length check
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    elif len(password) >= 12:
        score += 2
    else:
        score += 1
    
    # Character variety checks
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    else:
        score += 1
    
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    else:
        score += 1
    
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    else:
        score += 1
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    else:
        score += 1
    
    # Common password patterns
    common_patterns = [
        r'123456',
        r'password',
        r'qwerty',
        r'abc123',
        r'admin'
    ]
    
    for pattern in common_patterns:
        if re.search(pattern, password.lower()):
            errors.append("Password contains common patterns and is not secure")
            score = max(0, score - 2)
            break
    
    # Sequential characters
    if re.search(r'(012|123|234|345|456|567|678|789|890)', password):
        errors.append("Password should not contain sequential numbers")
        score = max(0, score - 1)
    
    if re.search(r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
        errors.append("Password should not contain sequential letters")
        score = max(0, score - 1)
    
    is_valid = len(errors) == 0
    return is_valid, errors, min(score, 5)  # Cap score at 5

def validate_required_fields(data, required_fields):
    """
    Validate that all required fields are present and not empty.
    
    Args:
        data (dict): Data to validate
        required_fields (list): List of required field names
        
    Returns:
        tuple: (is_valid: bool, missing_fields: list)
    """
    missing_fields = []
    
    for field in required_fields:
        if field not in data or not data[field] or str(data[field]).strip() == '':
            missing_fields.append(field)
    
    return len(missing_fields) == 0, missing_fields

def validate_date_format(date_string, format_string='%Y-%m-%d'):
    """
    Validate date string format.
    
    Args:
        date_string (str): Date string to validate
        format_string (str): Expected date format
        
    Returns:
        tuple: (is_valid: bool, parsed_date: date, error_message: str)
    """
    try:
        parsed_date = datetime.strptime(date_string, format_string).date()
        return True, parsed_date, None
    except ValueError as e:
        return False, None, f"Invalid date format. Expected format: {format_string}"

def validate_numeric_range(value, min_value=None, max_value=None, field_name="Value"):
    """
    Validate that numeric value is within specified range.
    
    Args:
        value: Numeric value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        field_name (str): Name of field for error messages
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        num_value = float(value)
        
        if min_value is not None and num_value < min_value:
            return False, f"{field_name} must be at least {min_value}"
        
        if max_value is not None and num_value > max_value:
            return False, f"{field_name} must not exceed {max_value}"
        
        return True, None
        
    except (ValueError, TypeError):
        return False, f"{field_name} must be a valid number"

def validate_string_length(value, min_length=None, max_length=None, field_name="Field"):
    """
    Validate string length.
    
    Args:
        value (str): String to validate
        min_length (int): Minimum length
        max_length (int): Maximum length
        field_name (str): Field name for error messages
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not isinstance(value, str):
        return False, f"{field_name} must be a string"
    
    length = len(value.strip())
    
    if min_length is not None and length < min_length:
        return False, f"{field_name} must be at least {min_length} characters long"
    
    if max_length is not None and length > max_length:
        return False, f"{field_name} must not exceed {max_length} characters"
    
    return True, None

def validate_enum_value(value, enum_class, field_name="Field"):
    """
    Validate that value is a valid enum member.
    
    Args:
        value: Value to validate
        enum_class: Enum class to validate against
        field_name (str): Field name for error messages
        
    Returns:
        tuple: (is_valid: bool, enum_value, error_message: str)
    """
    try:
        enum_value = enum_class(value)
        return True, enum_value, None
    except ValueError:
        valid_values = [e.value for e in enum_class]
        return False, None, f"{field_name} must be one of: {', '.join(valid_values)}"

def sanitize_input(value, strip_html=True, max_length=None):
    """
    Sanitize input string.
    
    Args:
        value (str): String to sanitize
        strip_html (bool): Whether to strip HTML tags
        max_length (int): Maximum length to truncate to
        
    Returns:
        str: Sanitized string
    """
    if not isinstance(value, str):
        return str(value)
    
    # Strip whitespace
    sanitized = value.strip()
    
    # Strip HTML tags if requested
    if strip_html:
        sanitized = re.sub(r'<[^>]+>', '', sanitized)
    
    # Truncate if max_length specified
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized
