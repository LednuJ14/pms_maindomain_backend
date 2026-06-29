
#!/usr/bin/env python3
"""
Environment variable validation script
Validates all required and recommended environment variables
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


# Required in production
REQUIRED_PRODUCTION = [
    'SECRET_KEY',
    'JWT_SECRET_KEY',
    'MYSQL_USER',
    'MYSQL_PASSWORD',
    'MYSQL_HOST',
    'MYSQL_DATABASE',
    'CORS_ORIGINS'
]

# Recommended (warn if missing)
RECOMMENDED = [
    'MAIL_USERNAME',
    'MAIL_PASSWORD',
    'STRIPE_SECRET_KEY',
    'STRIPE_PUBLISHABLE_KEY'
]

# Optional (informational)
OPTIONAL = [
    'FLASK_ENV',
    'MAIL_SERVER',
    'MAIL_PORT',
    'RATE_LIMIT_STORAGE_URL',
    'FRONTEND_URL'
]


def validate_env():
    """Validate environment variables."""
    # Load .env file if it exists
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded .env file from {env_path}")
    else:
        print(f"⚠️  No .env file found at {env_path}")
        print("   Using environment variables from system")
    
    flask_env = os.environ.get('FLASK_ENV', 'development')
    is_production = flask_env == 'production'
    
    print(f"\nEnvironment: {flask_env}")
    print("="*60)
    
    # Check required variables
    missing_required = []
    for var in REQUIRED_PRODUCTION:
        value = os.environ.get(var)
        if not value:
            missing_required.append(var)
            print(f"❌ {var}: MISSING")
        else:
            # Mask sensitive values
            if 'SECRET' in var or 'PASSWORD' in var or 'KEY' in var:
                masked = '*' * min(len(value), 20) + ('...' if len(value) > 20 else '')
                print(f"✅ {var}: {masked}")
            else:
                print(f"✅ {var}: {value}")
    
    # Check recommended variables
    print("\nRecommended Variables:")
    print("-"*60)
    missing_recommended = []
    for var in RECOMMENDED:
        value = os.environ.get(var)
        if not value:
            missing_recommended.append(var)
            print(f"⚠️  {var}: MISSING (recommended)")
        else:
            if 'PASSWORD' in var or 'SECRET' in var or 'KEY' in var:
                masked = '*' * min(len(value), 20) + ('...' if len(value) > 20 else '')
                print(f"✅ {var}: {masked}")
            else:
                print(f"✅ {var}: {value}")
    
    # Show optional variables
    print("\nOptional Variables:")
    print("-"*60)
    for var in OPTIONAL:
        value = os.environ.get(var)
        if value:
            print(f"ℹ️  {var}: {value}")
        else:
            print(f"   {var}: (not set, using default)")
    
    # Summary
    print("\n" + "="*60)
    print("Validation Summary:")
    print("-"*60)
    
    if is_production:
        if missing_required:
            print(f"❌ FAILED: {len(missing_required)} required variables missing:")
            for var in missing_required:
                print(f"   - {var}")
            print("\n⚠️  Production requires all required variables to be set!")
            return False
        else:
            print("✅ All required variables are set")
    else:
        if missing_required:
            print(f"⚠️  {len(missing_required)} recommended variables missing (using defaults)")
        else:
            print("✅ All recommended variables are set")
    
    if missing_recommended:
        print(f"⚠️  {len(missing_recommended)} optional variables missing (some features may not work)")
    else:
        print("✅ All recommended variables are set")
    
    print("\n✅ Environment validation completed")
    return True


def main():
    """Main function."""
    try:
        success = validate_env()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error during validation: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

