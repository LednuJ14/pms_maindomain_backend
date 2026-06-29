# Testing Guide

## Setup

1. Install test dependencies:
```bash
pip install pytest pytest-flask pytest-cov
```

2. Run tests:
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_health.py

# Run with verbose output
pytest -v
```

## Test Structure

- `conftest.py` - Pytest configuration and fixtures
- `test_health.py` - Health check endpoint tests
- More test files to be added...

## Writing Tests

### Example Test

```python
def test_example(client):
    """Test example endpoint."""
    response = client.get('/api/example')
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data
```

## Test Coverage Goals

- Unit tests for services: 80%+
- Integration tests for routes: 70%+
- Overall coverage: 75%+

## CI/CD Integration

Tests should run automatically on:
- Pull requests
- Before merging to main
- Before deployment

