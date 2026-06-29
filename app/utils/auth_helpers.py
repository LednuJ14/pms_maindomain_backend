"""
Authentication helper functions
"""
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps
from flask import current_app, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, get_jwt
from app import bcrypt
from app.models.blacklisted_token import BlacklistedToken

def generate_token(user_id, expires_delta=None):
    """
    Generate JWT access token for user.
    
    Args:
        user_id (int): User ID
        expires_delta (timedelta): Custom expiration time
        
    Returns:
        str: JWT access token
    """
    if expires_delta:
        return create_access_token(
            identity=user_id,
            expires_delta=expires_delta
        )
    return create_access_token(identity=user_id)

def generate_refresh_token(user_id):
    """
    Generate JWT refresh token for user.
    
    Args:
        user_id (int): User ID
        
    Returns:
        str: JWT refresh token
    """
    return create_refresh_token(identity=user_id)

def verify_token(token):
    """
    Verify JWT token and check if it's blacklisted.
    
    Args:
        token (str): JWT token to verify
        
    Returns:
        dict: Token payload if valid, None otherwise
    """
    try:
        # Check if token is blacklisted
        if BlacklistedToken.check_blacklist(token):
            return None
        
        # Token verification is handled by Flask-JWT-Extended
        return {'valid': True}
    except Exception:
        return None

def blacklist_token(token, expires_at, user_id=None):
    """
    Add token to blacklist.
    
    Args:
        token (str): JWT token to blacklist
        expires_at (datetime): Token expiration time
        user_id (int): Optional user ID
    """
    BlacklistedToken.add_token_to_blacklist(token, expires_at, user_id)

def hash_password(password):
    """
    Hash password using bcrypt.
    
    Args:
        password (str): Plain text password
        
    Returns:
        str: Hashed password
    """
    return bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(password_hash, password):
    """
    Check if password matches hash.
    
    Args:
        password_hash (str): Stored password hash
        password (str): Plain text password to check
        
    Returns:
        bool: True if password matches, False otherwise
    """
    return bcrypt.check_password_hash(password_hash, password)

def generate_random_string(length=32, include_symbols=False):
    """
    Generate cryptographically secure random string.
    
    Args:
        length (int): Length of string to generate
        include_symbols (bool): Include symbols in string
        
    Returns:
        str: Random string
    """
    alphabet = string.ascii_letters + string.digits
    if include_symbols:
        alphabet += "!@#$%^&*"
    
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_verification_token():
    """
    Generate email verification token.
    
    Returns:
        str: Verification token
    """
    return generate_random_string(64)

def generate_password_reset_token():
    """
    Generate password reset token.
    
    Returns:
        str: Password reset token
    """
    return generate_random_string(64)

def is_token_expired(expires_at):
    """
    Check if token has expired.
    
    Args:
        expires_at (datetime): Token expiration time
        
    Returns:
        bool: True if expired, False otherwise
    """
    return datetime.utcnow() > expires_at

def get_token_expiry_time(token_type='access'):
    """
    Get expiry time for token type.
    
    Args:
        token_type (str): 'access' or 'refresh'
        
    Returns:
        datetime: Expiry time
    """
    if token_type == 'refresh':
        delta = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=30))
    else:
        delta = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', timedelta(hours=1))
    
    return datetime.utcnow() + delta
