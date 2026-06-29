"""
Users service: list, get, update, update_status, stats
"""
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy import or_, func
from app import db
from app.models.user import User, UserRole, UserStatus
from app.utils.pagination import paginate_query
from app.utils.validators import validate_email, validate_phone, validate_required_fields, sanitize_input


from app.errors import ValidationAppError

class UsersValidationError(ValidationAppError):
    def __init__(self, message: str, details: Dict | None = None):
        super().__init__(message)
        self.details = details or {}


class UsersService:
    def list_users(self, params: Dict[str, Any]) -> Dict:
        page = int(params.get('page', 1) or 1)
        per_page = int(params.get('per_page', 10) or 10)
        role_filter = params.get('role')
        status_filter = params.get('status')
        search = (params.get('search') or '').strip()

        query = User.query
        if role_filter:
            try:
                query = query.filter(User.role == UserRole(role_filter))
            except ValueError:
                raise UsersValidationError('Invalid role filter')
        if status_filter:
            try:
                query = query.filter(User.status == UserStatus(status_filter))
            except ValueError:
                raise UsersValidationError('Invalid status filter')
        if search:
            st = f"%{search}%"
            query = query.filter(
                or_(
                    User.email.ilike(st),
                    User.first_name.ilike(st),
                    User.last_name.ilike(st),
                    func.concat(User.first_name, ' ', User.last_name).ilike(st)
                )
            )
        query = query.order_by(User.created_at.desc())
        result = paginate_query(query, page, per_page)
        return {
            'users': [u.to_dict(include_sensitive=True) for u in result['items']],
            'pagination': result['pagination'],
        }

    def get_user(self, requesting_user, user_id: int) -> Dict:
        user = User.query.get_or_404(user_id)
        include_sensitive = requesting_user.is_admin() or requesting_user.id == user_id
        subscription_info = user.subscription.to_dict() if user.is_manager() and user.subscription else None
        return {'user': user.to_dict(include_sensitive=include_sensitive), 'subscription': subscription_info}

    def update_user(self, requesting_user, user_id: int, payload: Dict[str, Any]) -> Dict:
        user = User.query.get_or_404(user_id)
        changes_made = False
        # basic fields
        updatable_fields = ['first_name', 'last_name', 'phone_number', 'address', 'city', 'province', 'postal_code', 'country']
        for field in updatable_fields:
            if field in payload:
                new_value = sanitize_input(str(payload[field])) if payload[field] else None
                if getattr(user, field) != new_value:
                    setattr(user, field, new_value)
                    changes_made = True
        # email
        if 'email' in payload:
            is_valid_email, normalized_email, email_error = validate_email(payload['email'])
            if not is_valid_email:
                raise UsersValidationError('Invalid email', {'message': email_error})
            existing_user = User.query.filter(User.email == normalized_email, User.id != user_id).first()
            if existing_user:
                raise UsersValidationError('Email already exists')
            if user.email != normalized_email:
                user.email = normalized_email
                user.email_verified = False
                changes_made = True
        # phone
        if 'phone_number' in payload and payload['phone_number']:
            is_valid_phone, formatted_phone, phone_error = validate_phone(payload['phone_number'])
            if not is_valid_phone:
                raise UsersValidationError('Invalid phone number', {'message': phone_error})
            if user.phone_number != formatted_phone:
                user.phone_number = formatted_phone
                # phone_verified removed - not used in system
                changes_made = True
        # DOB
        if 'date_of_birth' in payload and payload['date_of_birth']:
            try:
                new_dob = datetime.strptime(payload['date_of_birth'], '%Y-%m-%d').date()
                if user.date_of_birth != new_dob:
                    user.date_of_birth = new_dob
                    changes_made = True
            except ValueError:
                raise UsersValidationError('Invalid date format', {'message': 'Date of birth must be in YYYY-MM-DD format'})
        # Admin-only
        if requesting_user.is_admin():
            if 'status' in payload:
                try:
                    new_status = UserStatus(payload['status'])
                    if user.status != new_status:
                        user.status = new_status
                        changes_made = True
                except ValueError:
                    raise UsersValidationError('Invalid status')
            if 'role' in payload:
                try:
                    new_role = UserRole(payload['role'])
                    if user.role != new_role:
                        user.role = new_role
                        changes_made = True
                except ValueError:
                    raise UsersValidationError('Invalid role')
        if changes_made:
            # updated_by removed - not critical for audit trail
            db.session.commit()
            return {'message': 'User updated successfully', 'user': user.to_dict()}
        else:
            return {'message': 'No changes detected', 'user': user.to_dict()}

    def update_user_status(self, requesting_user, user_id: int, payload: Dict[str, Any]) -> Dict:
        user = User.query.get_or_404(user_id)
        if 'status' not in payload:
            raise UsersValidationError('Missing status')
        try:
            new_status = UserStatus(payload['status'])
        except ValueError:
            raise UsersValidationError('Invalid status')
        old_status = user.status
        user.status = new_status
        # updated_by removed - not critical for audit trail
        db.session.commit()
        return {'message': f'User status updated from {old_status.value} to {new_status.value}', 'user': user.to_dict(include_sensitive=True)}

    def stats(self) -> Dict:
        role_stats = {role.value: User.query.filter_by(role=role).count() for role in UserRole}
        status_stats = {status.value: User.query.filter_by(status=status).count() for status in UserStatus}
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_registrations = User.query.filter(User.created_at >= thirty_days_ago).count()
        total_users = User.query.count()
        return {
            'total_users': total_users,
            'role_distribution': role_stats,
            'status_distribution': status_stats,
            'recent_registrations': recent_registrations,
            'generated_at': datetime.utcnow().isoformat(),
        }
