"""
Tests for health check endpoints
"""
import pytest


def test_health_check(client):
    """Test basic health check endpoint."""
    response = client.get('/api/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'healthy'
    assert 'timestamp' in data
    assert 'service' in data


def test_readiness_check(client):
    """Test readiness check endpoint."""
    response = client.get('/api/health/readiness')
    assert response.status_code in [200, 503]  # 200 if DB connected, 503 if not
    data = response.get_json()
    assert 'status' in data
    assert 'checks' in data
    assert 'database' in data['checks']


def test_detailed_status(client):
    """Test detailed status endpoint."""
    response = client.get('/api/health/status')
    assert response.status_code in [200, 503]
    data = response.get_json()
    assert 'status' in data
    assert 'checks' in data
    assert 'environment' in data

