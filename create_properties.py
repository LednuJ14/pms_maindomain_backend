from app import create_app, db
from app.models.user import User
from sqlalchemy import text
from datetime import datetime

def create_dummy_properties():
    app = create_app()
    with app.app_context():
        # Find user
        email = "abao@gmail.com"
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"Error: User {email} not found.")
            return

        contact_person = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Admin User"
        contact_email = user.email or "admin@gmail.com"
        contact_phone = user.phone_number or "+1234567890"

        # Properties to add
        properties_data = [
            {
                "title": "Sunnyvale Apartment Complex",
                "address": "123 Sunshine Blvd",
                "city": "Cebu City",
                "property_type": "studio_apartment",
                "status": "active",  # active means approved/verified in this system
                "management_status": "managed",
                "monthly_rent": 15000.00,
                "total_units": 10,
                "portal_enabled": True,
                "contact_person": contact_person,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            },
            {
                "title": "Oakwood Dormitory",
                "address": "456 Oak St",
                "city": "Mandaue City",
                "property_type": "dormitory",
                "status": "active",
                "management_status": "managed",
                "monthly_rent": 5000.00,
                "total_units": 20,
                "portal_enabled": True,
                "contact_person": contact_person,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            },
            {
                "title": "Maple Boarding House",
                "address": "789 Maple Ave",
                "city": "Lapu-Lapu City",
                "property_type": "boarding_house",
                "status": "active",
                "management_status": "managed",
                "monthly_rent": 8000.00,
                "total_units": 5,
                "portal_enabled": True,
                "contact_person": contact_person,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            }
        ]

        check_sql = text("SELECT id FROM properties WHERE title = :title")
        update_sql = text("""
            UPDATE properties 
            SET contact_person = :contact_person, contact_email = :contact_email, contact_phone = :contact_phone
            WHERE title = :title
        """)
        insert_sql = text("""
            INSERT INTO properties (
                title, property_type, address, city, monthly_rent, owner_id, 
                status, management_status, total_units, portal_enabled, created_at, updated_at,
                contact_person, contact_email, contact_phone
            ) VALUES (
                :title, :property_type, :address, :city, :monthly_rent, :owner_id, 
                :status, :management_status, :total_units, :portal_enabled, :created_at, :updated_at,
                :contact_person, :contact_email, :contact_phone
            )
        """)

        now = datetime.utcnow()

        for p_data in properties_data:
            existing = db.session.execute(check_sql, {"title": p_data["title"]}).fetchone()
            if existing:
                print(f"Property {p_data['title']} already exists. Updating contact info...")
                db.session.execute(update_sql, {
                    "title": p_data["title"],
                    "contact_person": p_data["contact_person"],
                    "contact_email": p_data["contact_email"],
                    "contact_phone": p_data["contact_phone"]
                })
            else:
                db.session.execute(insert_sql, {
                    "title": p_data["title"],
                    "property_type": p_data["property_type"],
                    "address": p_data["address"],
                    "city": p_data["city"],
                    "monthly_rent": p_data["monthly_rent"],
                    "owner_id": user.id,
                    "status": p_data["status"],
                    "management_status": p_data["management_status"],
                    "total_units": p_data["total_units"],
                    "portal_enabled": p_data["portal_enabled"],
                    "created_at": now,
                    "updated_at": now,
                    "contact_person": p_data["contact_person"],
                    "contact_email": p_data["contact_email"],
                    "contact_phone": p_data["contact_phone"]
                })
                print(f"Created property: {p_data['title']}")
                
        db.session.commit()
        print(f"Successfully added/updated properties for {email}!")

if __name__ == "__main__":
    create_dummy_properties()
