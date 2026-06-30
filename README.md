# PMS Property Management System - Backend API

A secure and scalable Flask-based REST API for the PMS Property Management System platform, featuring JWT authentication, MySQL database, subscription management, and comprehensive security measures.

## 🚀 Features

### Core Features
- **Secure Authentication** - JWT-based auth with refresh tokens, account locking, and password strength validation
- **Role-Based Access Control** - Admin, Property Manager, and Tenant roles with granular permissions
- **Subscription Management** - Multi-tier subscription plans with usage tracking and limits
- **Property Management** - Complete CRUD operations for rental properties with image uploads
- **Inquiry System** - Tenant-property manager communication system
- **File Upload** - Secure file handling with image optimization and validation

### Security Features
- **Password Security** - Bcrypt hashing with configurable rounds
- **Rate Limiting** - Configurable rate limits per endpoint
- **Input Validation** - Comprehensive validation for all user inputs
- **SQL Injection Protection** - SQLAlchemy ORM with parameterized queries
- **CORS Protection** - Configurable CORS policies
- **Token Blacklisting** - JWT token revocation on logout
- **Account Security** - Failed login attempt tracking and account locking

### Technical Features
- **Database Migrations** - Flask-Migrate for schema versioning
- **Error Handling** - Comprehensive error handling with logging
- **API Documentation** - Built-in API documentation
- **Environment Configuration** - Flexible configuration management
- **File Management** - Secure file upload and management
- **Pagination** - Efficient pagination for large datasets

## 📋 Prerequisites

- Python 3.8 or higher
- MySQL 8.0 or higher
- Redis (optional, for rate limiting)
- Git

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <repository-url> PMS
cd PMS/main-domain/backend
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Setup
```bash
# Copy environment template
copy env.example .env  # Windows
cp env.example .env    # macOS/Linux
```

### 5. Configure Environment Variables
Edit `.env` file with your settings:

```env
# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-super-secret-key-change-this-in-production

# Database Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your-mysql-username
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=pms_property_db

# JWT Configuration
JWT_SECRET_KEY=your-jwt-secret-key-change-this-in-production
JWT_ACCESS_TOKEN_EXPIRES=3600
JWT_REFRESH_TOKEN_EXPIRES=2592000

# Email Configuration (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### 6. Create MySQL Database
```sql
CREATE DATABASE pms_property_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pms_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON pms_property_db.* TO 'pms_user'@'localhost';
FLUSH PRIVILEGES;
```

### 7. Initialize Database
```bash
python init_db.py
```

### 8. Run Database Migrations (if needed)
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

## 🚀 Running the Application

### Development Mode
```bash
python app.py
```

### Production Mode
```bash
# Using Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Using environment variables
export FLASK_ENV=production
export FLASK_DEBUG=False
python app.py
```

The API will be available at `http://localhost:5000`

## 📚 API Documentation

### Authentication Endpoints

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "first_name": "John",
    "last_name": "Doe",
    "role": "tenant",
    "phone_number": "+63 917 123 4567"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "SecurePassword123!"
}
```

#### Get Current User
```http
GET /api/auth/me
Authorization: Bearer <access_token>
```

#### Logout
```http
POST /api/auth/logout
Authorization: Bearer <access_token>
```

### Default User Accounts

After running `init_db.py`, these accounts will be available:

| Role | Email | Password | Description |
|------|-------|----------|-------------|
| Admin | admin@pms-cebu.com | Admin123! | System administrator |
| Manager | manager@example.com | Manager123! | Property manager |
| Tenant | tenant@example.com | Tenant123! | Sample tenant |

⚠️ **Important**: Change these passwords in production!

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── models/                  # Database models
│   │   ├── user.py             # User model
│   │   ├── property.py         # Property models
│   │   ├── subscription.py     # Subscription models
│   │   ├── inquiry.py          # Inquiry model
│   │   └── blacklisted_token.py # Token blacklist
│   ├── routes/                  # API routes
│   │   ├── auth.py             # Authentication routes
│   │   ├── users.py            # User management
│   │   ├── properties.py       # Property management
│   │   ├── subscriptions.py    # Subscription management
│   │   └── admin.py            # Admin routes
│   ├── utils/                   # Utility functions
│   │   ├── auth_helpers.py     # Authentication utilities
│   │   ├── validators.py       # Input validation
│   │   ├── decorators.py       # Custom decorators
│   │   ├── error_handlers.py   # Error handling
│   │   ├── jwt_handlers.py     # JWT callbacks
│   │   ├── file_helpers.py     # File management
│   │   └── pagination.py       # Pagination utilities
│   └── middleware/              # Custom middleware
├── migrations/                  # Database migrations
├── tests/                       # Test files
├── uploads/                     # File uploads directory
├── config.py                   # Configuration settings
├── app.py                      # Application entry point
├── init_db.py                  # Database initialization
├── requirements.txt            # Python dependencies
├── env.example                 # Environment template
└── README.md                   # This file
```

## 🔒 Security Features

### Authentication Security
- **JWT Tokens**: Secure token-based authentication
- **Token Blacklisting**: Revoked tokens are blacklisted
- **Password Hashing**: Bcrypt with configurable rounds
- **Account Locking**: Protection against brute force attacks
- **Password Strength**: Enforced password complexity

### Input Security
- **Validation**: Comprehensive input validation
- **Sanitization**: XSS protection through input sanitization
- **SQL Injection**: Protected by SQLAlchemy ORM
- **File Upload**: Secure file handling with type/size validation

### API Security
- **Rate Limiting**: Configurable rate limits per endpoint
- **CORS**: Cross-origin request protection
- **Error Handling**: Secure error responses (no sensitive data exposure)
- **Logging**: Comprehensive security event logging

## 🧪 Testing

### Run Tests
```bash
# Install test dependencies
pip install pytest pytest-flask coverage

# Run tests
pytest

# Run with coverage
pytest --cov=app
```

### Test Database
The application automatically uses an in-memory SQLite database for testing.

## 📈 Monitoring and Logging

### Health Check
```http
GET /api/auth/health
```

### Logging
- Application logs are written to console in development
- Configure logging handlers for production
- Security events are logged with appropriate detail

## 🚀 Deployment

### Production Checklist
- [ ] Change all default passwords
- [ ] Set strong SECRET_KEY and JWT_SECRET_KEY
- [ ] Configure production database
- [ ] Set up HTTPS/SSL
- [ ] Configure rate limiting with Redis
- [ ] Set up log aggregation
- [ ] Configure email service
- [ ] Set up monitoring and alerts
- [ ] Review and set appropriate CORS origins

### Docker Deployment (Optional)
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation for common issues

## 🔄 Version History

- **v1.0.0** - Initial release with core functionality
- **v1.1.0** - Added subscription management
- **v1.2.0** - Enhanced security features

---

**Note**: This is a development version. Ensure proper security configuration before deploying to production.
