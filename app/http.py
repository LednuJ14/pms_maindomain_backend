"""
Unified HTTP helpers and typed exceptions
"""
from flask import jsonify


def ok(data=None, meta=None, status=200):
    return jsonify({
        'data': data,
        'error': None,
        'meta': meta or {}
    }), status


def fail(message, code=400, details=None):
    return jsonify({
        'data': None,
        'error': {
            'code': code,
            'message': message,
            'details': details or {}
        },
        'meta': {}
    }), code
