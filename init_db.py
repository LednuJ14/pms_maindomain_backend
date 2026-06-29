from app import create_app, db
from app.models.user import User, UserRole, UserStatus


def ensure_user(email: str, password: str, role: UserRole, first_name: str, last_name: str) -> User:
    normalized_email = email.lower().strip()
    user = User.query.filter_by(email=normalized_email).first()

    if user:
        if user.role != role:
            user.role = role
        if user.status != UserStatus.ACTIVE:
            user.status = UserStatus.ACTIVE
        if not user.email_verified:
            user.email_verified = True
        db.session.commit()
        print(f"✓ User already exists: {normalized_email} (role={user.role.value}, status={user.status.value})")
        return user

    user = User(
        email=normalized_email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
    )
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    db.session.add(user)
    db.session.commit()
    print(f"+ Created user: {normalized_email} (role={role.value})")
    return user


def main() -> None:
    app = create_app()

    with app.app_context():
        print("Initializing database (non-destructive)...")

        ensure_user(
            email="admin@jacs-cebu.com",
            password="Admin123!",
            role=UserRole.ADMIN,
            first_name="System",
            last_name="Admin",
        )

        ensure_user(
            email="manager@example.com",
            password="Manager123!",
            role=UserRole.MANAGER,
            first_name="Demo",
            last_name="Manager",
        )

        ensure_user(
            email="tenant@example.com",
            password="Tenant123!",
            role=UserRole.TENANT,
            first_name="Demo",
            last_name="Tenant",
        )

        print("✅ Default demo users are now present in the database.")


if __name__ == "__main__":
    main()
