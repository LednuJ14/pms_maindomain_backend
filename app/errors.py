"""
Typed application errors for centralized handling
"""

class AppError(Exception):
    status_code = 400
    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}

class ValidationAppError(AppError):
    status_code = 400

class NotFoundAppError(AppError):
    status_code = 404

class UnauthorizedAppError(AppError):
    status_code = 401

class ForbiddenAppError(AppError):
    status_code = 403

class ConflictAppError(AppError):
    status_code = 409
