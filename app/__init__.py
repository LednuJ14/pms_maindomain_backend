"""
Flask Application Factory
"""
import os
import re
from flask import Flask, request
from flask import send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flasgger import Swagger

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
jwt = JWTManager()
bcrypt = Bcrypt()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)
mail = Mail()
swagger = Swagger()

def create_app(config_name=None):
    """
    Create and configure the Flask application.
    
    Args:
        config_name (str): Configuration environment name
        
    Returns:
        Flask: Configured Flask application instance
    """
    # Set template directory to the backend/templates folder
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_dir)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    from config import config
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # Configure CORS with environment-based origins
    raw_origins = app.config.get('CORS_ORIGINS', [])
    
    if not raw_origins:
        app.logger.warning("No CORS origins configured. CORS will be disabled.")
        cors_origins = []
    else:
        # Validate and format origins
        cors_origins = []
        for origin in raw_origins:
            if isinstance(origin, str):
                # Validate origin format
                if not origin.startswith(('http://', 'https://')):
                    app.logger.warning(f"Invalid CORS origin format (must start with http:// or https://): {origin}")
                    continue
                # Only allow wildcards in development
                if '*' in origin and app.config.get('FLASK_ENV') == 'production':
                    app.logger.warning(f"Wildcard CORS origins not allowed in production: {origin}")
                    continue
                # Convert wildcard patterns to regex in development only
                if '*' in origin and app.config.get('FLASK_ENV') == 'development':
                    pattern = re.escape(origin).replace(r'\*', r'.*')
                    cors_origins.append(re.compile(f"^{pattern}$"))
                else:
                    cors_origins.append(origin)
            else:
                cors_origins.append(origin)
    
    # Regex pattern for dev tunnel URLs (e.g., *.devtunnels.ms, *.asse.devtunnels.ms)
    devtunnel_regex = re.compile(r'^https?://[a-zA-Z0-9-]+\.(devtunnels\.ms|asse\.devtunnels\.ms)(/.*)?$')
    
    # Validator function for CORS origins (supports localhost and dev tunnels)
    def cors_origin_validator(origin):
        """Validate if origin is allowed (localhost or dev tunnel URLs)."""
        if not origin:
            return False
        # Check if it matches dev tunnel pattern (for development)
        if devtunnel_regex.match(origin):
            return True
        # Check if origin is in the configured list
        for allowed_origin in cors_origins:
            if isinstance(allowed_origin, re.Pattern):
                if allowed_origin.match(origin):
                    return True
            elif allowed_origin == origin:
                return True
        return False
    
    # In development, automatically allow dev tunnels
    if app.config.get('FLASK_ENV') == 'development':
        # Add dev tunnel pattern to allowed origins
        if devtunnel_regex not in cors_origins:
            cors_origins.append(devtunnel_regex)
    
    # Configure CORS with stricter settings
    cors_config = {
        "supports_credentials": True,
        "resources": {
            r"/api/*": {
                "origins": cors_origins if cors_origins else ["*"],  # Fallback to * only if no origins configured
                "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
                "expose_headers": ["Content-Type", "Authorization"],
                "max_age": 3600,
            }
        },
    }
    
    cors.init_app(app, **cors_config)
    
    # Handle preflight requests globally to ensure dev tunnel origins are allowed
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = app.make_default_options_response()
            headers = response.headers
            origin = request.headers.get('Origin', '')
            # Allow origin if it passes validation
            if origin and cors_origin_validator(origin):
                headers['Access-Control-Allow-Origin'] = origin
                headers['Access-Control-Allow-Credentials'] = 'true'
            headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
            headers['Access-Control-Max-Age'] = '3600'
            return response
    
    # Also handle CORS for actual requests (including error responses)
    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin', '')
        # Allow origin if it passes validation
        if origin and cors_origin_validator(origin):
            # Override Flask-CORS headers to ensure dev tunnels are allowed
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        # Always add these headers
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept, Origin'
        return response
    jwt.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register JWT handlers
    register_jwt_handlers(app)
    
    # Initialize request/response logging middleware
    from app.middleware import init_request_logging
    init_request_logging(app)

    # Configure Swagger / OpenAPI documentation
    # This is scoped to /api routes only and should not affect existing behavior.
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "JACS Property Platform API",
            "description": "Interactive API documentation for the main-domain backend.\n\n"
                           "## Authentication\n"
                           "Most endpoints require JWT authentication. Include the token in the Authorization header:\n"
                           "```\n"
                           "Authorization: Bearer <your-access-token>\n"
                           "```\n\n"
                           "## Response Format\n"
                           "All responses follow a standardized format:\n"
                           "- **Success**: `{success: true, data: {...}, error: null}`\n"
                           "- **Error**: `{success: false, data: null, error: {message, code, status_code, details}}`\n\n"
                           "## Error Codes\n"
                           "- `BAD_REQUEST` (400): Invalid request data\n"
                           "- `UNAUTHORIZED` (401): Authentication required\n"
                           "- `FORBIDDEN` (403): Insufficient permissions\n"
                           "- `NOT_FOUND` (404): Resource not found\n"
                           "- `CONFLICT` (409): Resource conflict\n"
                           "- `VALIDATION_ERROR` (422): Validation failed\n"
                           "- `INTERNAL_ERROR` (500): Server error\n\n"
                           "## Rate Limiting\n"
                           "API requests are rate-limited. Default: 100 requests/hour (production), 200 requests/hour (development).\n"
                           "Rate limit information is included in response headers.",
            "version": "1.0.0",
            "contact": {
                "name": "JACS Support",
                "email": "support@jacs-cebu.com"
            }
        },
        "basePath": "/",
        "schemes": ["http", "https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\"\n\n"
                               "To obtain a token:\n"
                               "1. Register: POST /api/auth/register\n"
                               "2. Login: POST /api/auth/login\n"
                               "3. Use the returned access_token in subsequent requests"
            }
        },
        "security": [
            {
                "Bearer": []
            }
        ],
        "definitions": {
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "example": False
                    },
                    "data": {
                        "type": "null"
                    },
                    "error": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "example": "Error message"
                            },
                            "code": {
                                "type": "string",
                                "example": "ERROR_CODE"
                            },
                            "status_code": {
                                "type": "integer",
                                "example": 400
                            },
                            "details": {
                                "type": "object"
                            }
                        }
                    }
                }
            },
            "SuccessResponse": {
                "type": "object",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "example": True
                    },
                    "data": {
                        "type": "object"
                    },
                    "message": {
                        "type": "string",
                        "example": "Operation successful"
                    },
                    "error": {
                        "type": "null"
                    },
                    "meta": {
                        "type": "object",
                        "properties": {
                            "pagination": {
                                "type": "object"
                            }
                        }
                    }
                }
            }
        },
        "responses": {
            "UnauthorizedError": {
                "description": "Authentication required",
                "schema": {
                    "$ref": "#/definitions/ErrorResponse"
                },
                "examples": {
                    "application/json": {
                        "success": False,
                        "data": None,
                        "error": {
                            "message": "Authentication required",
                            "code": "UNAUTHORIZED",
                            "status_code": 401
                        }
                    }
                }
            },
            "ForbiddenError": {
                "description": "Insufficient permissions",
                "schema": {
                    "$ref": "#/definitions/ErrorResponse"
                },
                "examples": {
                    "application/json": {
                        "success": False,
                        "data": None,
                        "error": {
                            "message": "Access forbidden",
                            "code": "FORBIDDEN",
                            "status_code": 403
                        }
                    }
                }
            },
            "ValidationError": {
                "description": "Validation failed",
                "schema": {
                    "$ref": "#/definitions/ErrorResponse"
                },
                "examples": {
                    "application/json": {
                        "success": False,
                        "data": None,
                        "error": {
                            "message": "Validation failed",
                            "code": "VALIDATION_ERROR",
                            "status_code": 422,
                            "details": {
                                "email": ["Invalid email format"],
                                "password": ["Password too short"]
                            }
                        }
                    }
                }
            },
            "NotFoundError": {
                "description": "Resource not found",
                "schema": {
                    "$ref": "#/definitions/ErrorResponse"
                },
                "examples": {
                    "application/json": {
                        "success": False,
                        "data": None,
                        "error": {
                            "message": "Resource not found",
                            "code": "NOT_FOUND",
                            "status_code": 404
                        }
                    }
                }
            },
            "InternalServerError": {
                "description": "Internal server error",
                "schema": {
                    "$ref": "#/definitions/ErrorResponse"
                },
                "examples": {
                    "application/json": {
                        "success": False,
                        "data": None,
                        "error": {
                            "message": "Internal server error",
                            "code": "INTERNAL_ERROR",
                            "status_code": 500
                        }
                    }
                }
            }
        }
    }

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_main",
                "route": "/api/swagger.json",
                # Limit to API routes only so other Flask endpoints are untouched
                "rule_filter": lambda rule: rule.rule.startswith("/api/"),
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        # Swagger UI will be served at /api/docs/
        "specs_route": "/api/docs/",
    }

    Swagger(app, template=swagger_template, config=swagger_config)
    
    # Create upload directory if it doesn't exist
    upload_dir = os.path.join(app.instance_path, app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)

    # Serve uploaded files from instance/uploads via /uploads/*
    @app.route('/uploads/<path:filename>')
    def uploaded_files(filename):
        response = send_from_directory(upload_dir, filename)
        # Add CORS headers for dev tunnel support
        origin = request.headers.get('Origin', '')
        if origin and cors_origin_validator(origin):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # API proxy route for uploads to avoid mixed content issues with HTTPS pages
    @app.route('/api/uploads/<path:filename>')
    def api_uploaded_files(filename):
        """Proxy route for uploads to avoid mixed content warnings on HTTPS pages."""
        response = send_from_directory(upload_dir, filename)
        # Add CORS headers for dev tunnel support
        origin = request.headers.get('Origin', '')
        if origin and cors_origin_validator(origin):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    return app

def register_blueprints(app):
    """Register application blueprints."""
    # Swap to v2 auth controller (service-backed)
    from app.controllers.auth_controller_v2 import auth_bp
    # Swap to v2 users controller (service-backed)
    from app.controllers.users_controller_v2 import users_bp
    # Swap to v2 properties controller (service-backed)
    from app.controllers.properties_controller_v2 import properties_bp
    # Swap to v2 subscriptions controller (service-backed)
    from app.controllers.subscriptions_controller_v2 import subscriptions_bp
    # Swap to v2 admin controller (service-backed)
    from app.controllers.admin_controller_v2 import admin_bp
    from app.routes.admin_properties import admin_properties_bp
    from app.routes.admin_analytics import admin_analytics_bp
    from app.routes.admin_documents import admin_documents_bp
    from app.routes.manager_properties import manager_properties_bp
    from app.routes.manager_inquiries_new import manager_inquiries_bp
    from app.routes.manager_analytics import manager_analytics_bp
    from app.routes.manager_contracts import manager_contracts_bp
    from app.routes.tenant_inquiries_new import tenant_inquiries_bp
    from app.routes.tenant_profile import tenant_profile_bp
    from app.routes.tenant_contracts import tenant_contracts_bp
    from app.routes.tenant_notifications import tenant_notifications_bp
    from app.routes.manager_notifications import manager_notifications_bp
    from app.routes.admin_notifications import admin_notifications_bp
    from app.routes.public_units import public_units_bp
    from app.routes.inquiry_attachments import inquiry_attachments_bp
    from app.routes.health import health_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(properties_bp, url_prefix='/api/properties')
    app.register_blueprint(subscriptions_bp, url_prefix='/api/subscriptions')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_properties_bp, url_prefix='/api/admin/properties')
    app.register_blueprint(admin_analytics_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_documents_bp, url_prefix='/api/admin')
    app.register_blueprint(manager_properties_bp, url_prefix='/api/manager/properties')
    app.register_blueprint(manager_inquiries_bp, url_prefix='/api/manager/inquiries')
    app.register_blueprint(manager_analytics_bp, url_prefix='/api/manager/analytics')
    app.register_blueprint(manager_contracts_bp, url_prefix='/api/manager/contracts')
    app.register_blueprint(tenant_inquiries_bp, url_prefix='/api/tenant/inquiries')
    app.register_blueprint(tenant_profile_bp, url_prefix='/api/tenant/profile')
    app.register_blueprint(tenant_contracts_bp, url_prefix='/api/tenant/contracts')
    app.register_blueprint(tenant_notifications_bp, url_prefix='/api/tenant/notifications')
    app.register_blueprint(manager_notifications_bp, url_prefix='/api/manager/notifications')
    app.register_blueprint(admin_notifications_bp, url_prefix='/api/admin/notifications')
    
    # Inquiry attachments
    from app.routes.inquiry_attachments import inquiry_attachments_bp
    from app.routes.health import health_bp
    app.register_blueprint(inquiry_attachments_bp, url_prefix='/api/inquiries')
    # Note: password_reset_bp removed - all routes now handled by auth_controller_v2.py
    app.register_blueprint(public_units_bp, url_prefix='/api/units')
    app.register_blueprint(health_bp, url_prefix='/api')

    # Configure rate limiting - removed broad exemptions, use default limits
    # Rate limits are now enforced on all endpoints (was exempted before)
    # Default limits are set in config.py: 100/hour (production) or 200/hour (development)
    # Individual routes can override with @limiter.limit() decorator if needed
    
    # Note: OPTIONS requests (CORS preflight) are automatically exempted by Flask-Limiter
    # No need to manually exempt them
    
    app.logger.info(f"Rate limiting enabled: {app.config.get('RATELIMIT_DEFAULT', '100 per hour')}")

def register_error_handlers(app):
    """Register application error handlers."""
    from app.utils.error_handlers import register_error_handlers as register_handlers
    register_handlers(app)

def register_jwt_handlers(app):
    """Register JWT-related handlers."""
    from app.utils.jwt_handlers import register_jwt_handlers as register_handlers
    register_handlers(app, jwt)
