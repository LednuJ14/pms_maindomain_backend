"""
Pytest configuration and fixtures
"""
import pytest
from app import create_app, db as _db
from config import TestingConfig


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app('testing')
    app.config.from_object(TestingConfig)
    
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def db(app):
    """Create database for testing."""
    _db.create_all()
    yield _db
    _db.drop_all()


@pytest.fixture(scope='function')
def client(app, db):
    """Create test client."""
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def auth_headers(client):
    """Get authentication headers for testing."""
    # This would need to be implemented based on your auth flow
    # For now, returns empty dict - implement based on your needs
    return {
        'Content-Type': 'application/json'
    }

