"""
Flask Configuration Settings
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def validate_required_config(flask_env):
    """
    Validate that required configuration variables are set.
    Raises ValueError if critical variables are missing in production.
    Returns validation report.
    """
    required_in_production = [
        'SECRET_KEY',
        'JWT_SECRET_KEY',
        'MYSQL_USER',
        'MYSQL_PASSWORD',
        'MYSQL_HOST',
        'MYSQL_DATABASE'
    ]
    
    recommended_vars = [
        'CORS_ORIGINS',
        'MAIL_USERNAME',
        'MAIL_PASSWORD',
        'STRIPE_SECRET_KEY'
    ]
    
    missing_required = []
    missing_recommended = []
    
    for var in required_in_production:
        if not os.environ.get(var):
            missing_required.append(var)
    
    for var in recommended_vars:
        if not os.environ.get(var):
            missing_recommended.append(var)
    
    # Production: fail if required vars are missing
    if missing_required and flask_env == 'production':
        raise ValueError(
            f"Missing required environment variables for production: {', '.join(missing_required)}. "
            f"Please set these in your .env file or environment."
        )
    
    # Development: warn about missing vars
    if (missing_required or missing_recommended) and flask_env == 'development':
        import warnings
        if missing_required:
            warnings.warn(
                f"Missing recommended environment variables: {', '.join(missing_required)}. "
                f"Using defaults for development only.",
                UserWarning
            )
        if missing_recommended:
            warnings.warn(
                f"Missing optional environment variables: {', '.join(missing_recommended)}. "
                f"Some features may not work correctly.",
                UserWarning
            )
    
    # Return validation report
    return {
        'required_missing': missing_required,
        'recommended_missing': missing_recommended,
        'is_valid': len(missing_required) == 0 if flask_env == 'production' else True
    }

class Config:
    """Base configuration class."""
    
    # Flask Configuration
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'
    
    # Validate configuration on class creation
    validate_required_config(FLASK_ENV)
    
    # SECRET_KEY - Required in production, allow default only in development/testing
    _secret_key = os.environ.get('SECRET_KEY')
    if not _secret_key:
        if FLASK_ENV == 'production':
            raise ValueError("SECRET_KEY must be set in production environment")
        _secret_key = 'dev-secret-key-change-in-production'
    SECRET_KEY = _secret_key
    
    # Database Configuration
    _db_url = os.environ.get('DATABASE_URL')
    if not _db_url:
        # Build from components
        db_user = os.environ.get('MYSQL_USER', 'property_mgmt_2026')
        db_password = os.environ.get('MYSQL_PASSWORD', 'property2026')
        db_host = os.environ.get('MYSQL_HOST', 'siquijor-db-do-user-12791289-0.j.db.ondigitalocean.com')
        db_port = os.environ.get('MYSQL_PORT', '25060')
        db_name = os.environ.get('MYSQL_DATABASE', 'property_mgmt')
        _db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    SQLALCHEMY_DATABASE_URI = _db_url
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_timeout': 20,
        'max_overflow': 0,
    }
    
    # JWT Configuration - Required in production, allow default only in development/testing
    _jwt_secret = os.environ.get('JWT_SECRET_KEY')
    if not _jwt_secret:
        if FLASK_ENV == 'production':
            raise ValueError("JWT_SECRET_KEY must be set in production environment")
        _jwt_secret = 'jwt-secret-change-in-production'
    JWT_SECRET_KEY = _jwt_secret
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000)))
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ['access', 'refresh']
    
    # Security Configuration
    BCRYPT_LOG_ROUNDS = int(os.environ.get('BCRYPT_LOG_ROUNDS', 12))
    WTF_CSRF_ENABLED = True
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATE_LIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_DEFAULT = "100 per hour"
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16777216))  # 16MB
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    ALLOWED_EXTENSIONS = set(os.environ.get('ALLOWED_EXTENSIONS', 'jpg,jpeg,png,gif,pdf').split(','))
    
    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')
    
    # Frontend URL for email verification links
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
    
    # Pagination
    DEFAULT_PAGE_SIZE = int(os.environ.get('DEFAULT_PAGE_SIZE', 10))
    MAX_PAGE_SIZE = int(os.environ.get('MAX_PAGE_SIZE', 100))
    
    # CORS Configuration - Environment-based origins
    # In production, CORS_ORIGINS must be set via environment variable
    # Format: comma-separated list of origins, e.g., "https://app.example.com,https://www.example.com"
    _cors_origins_env = os.environ.get('CORS_ORIGINS')
    if _cors_origins_env:
        # Parse comma-separated origins from environment
        CORS_ORIGINS = [origin.strip() for origin in _cors_origins_env.split(',') if origin.strip()]
    else:
        # Default development origins (only used if CORS_ORIGINS not set)
        if FLASK_ENV == 'production':
            raise ValueError(
                "CORS_ORIGINS must be set in production environment. "
                "Set it as a comma-separated list of allowed origins."
            )
        # Development defaults
        CORS_ORIGINS = [
            'http://localhost:3000', 
            'http://127.0.0.1:3000',
            'http://localhost:8080',
            'http://127.0.0.1:8080',
        ]
    
    # Subscription Configuration
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_ENV = 'development'
    SQLALCHEMY_ECHO = True  # Log SQL queries in development

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_ENV = 'production'
    
    # Enhanced security for production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Stricter rate limiting for production
    RATELIMIT_DEFAULT = "60 per hour"

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4  # Faster hashing for tests

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
