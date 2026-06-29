"""
Database transaction management utilities
"""
from contextlib import contextmanager
from flask import current_app
from app import db


@contextmanager
def db_transaction():
    """
    Context manager for database transactions with automatic rollback on error.
    
    Usage:
        with db_transaction():
            # database operations
            db.session.add(some_object)
            # commit happens automatically on success
    """
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Transaction failed, rolled back: {str(e)}', exc_info=True)
        raise


def safe_db_operation(operation, *args, **kwargs):
    """
    Execute a database operation with automatic transaction management.
    
    Args:
        operation: Callable that performs database operations
        *args, **kwargs: Arguments to pass to operation
        
    Returns:
        Result of the operation
        
    Raises:
        Exception: Any exception raised by the operation (after rollback)
    """
    try:
        result = operation(*args, **kwargs)
        db.session.commit()
        return result
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Database operation failed, rolled back: {str(e)}', exc_info=True)
        raise

