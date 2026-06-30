from app import create_app, db
from sqlalchemy import text
from datetime import datetime
import random

def create_dummy_units():
    app = create_app()
    with app.app_context():
        # Get the properties
        properties_sql = text("SELECT id, title, property_type, monthly_rent FROM properties WHERE title IN ('Sunnyvale Apartment Complex', 'Oakwood Dormitory', 'Maple Boarding House')")
        properties = db.session.execute(properties_sql).fetchall()

        if not properties:
            print("No properties found to add units to.")
            return

        check_sql = text("SELECT id FROM units WHERE property_id = :property_id AND unit_name = :unit_name")
        update_sql = text("""
            UPDATE units 
            SET bedrooms = :bedrooms, bathrooms = :bathrooms, size_sqm = :size_sqm, 
                monthly_rent = :monthly_rent, security_deposit = :security_deposit, 
                status = :status, description = :description, floor_number = :floor_number, 
                parking_spaces = :parking_spaces, amenities = :amenities, updated_at = :updated_at
            WHERE property_id = :property_id AND unit_name = :unit_name
        """)
        insert_sql = text("""
            INSERT INTO units (
                property_id, unit_name, bedrooms, bathrooms, size_sqm, 
                monthly_rent, security_deposit, status, description, 
                floor_number, parking_spaces, amenities, created_at, updated_at
            ) VALUES (
                :property_id, :unit_name, :bedrooms, :bathrooms, :size_sqm, 
                :monthly_rent, :security_deposit, :status, :description, 
                :floor_number, :parking_spaces, :amenities, :created_at, :updated_at
            )
        """)

        now = datetime.utcnow()
        added_count = 0
        updated_count = 0

        studio_amenities = [
            "Kitchenette, Air Conditioning, Private Bathroom, Balcony",
            "Full Kitchen, AC, Fast Wi-Fi, Private Bath",
            "Air Conditioning, Private Bathroom, Wardrobe, Window View",
            "Kitchenette, Microwave, AC, Desk, En-suite Bathroom",
            "High-Speed Internet, AC, Mini-fridge, Private Bath",
            "Smart TV, AC, Kitchenette, Large Windows"
        ]

        dorm_amenities = [
            "Bunk Beds, Study Desk, Shared Bathroom, Lockers",
            "Single Bed, Shared Kitchen, Wi-Fi, AC",
            "Study Area, Shared Bathroom, Laundry Access",
            "Bunk Beds, AC, Shared Lounge, Wi-Fi",
            "Individual Desks, Lockers, Shared Bathroom",
            "Ceiling Fan, Bunk Beds, Wi-Fi, Shared Pantry"
        ]

        boarding_amenities = [
            "Bed, Closet, Ceiling Fan, Shared Bath",
            "Private Room, Desk, Shared Bath, Wi-Fi",
            "Bed, Wardrobe, AC, Shared Kitchen",
            "Ceiling Fan, Study Table, Private Bath",
            "Single Bed, Cabinet, AC, Shared Bath",
            "Bed, Drawer, Fan, Shared Living Area"
        ]
        
        descriptions = [
            "A beautifully lit {unit_name} perfect for comfortable living.",
            "Spacious and well-ventilated {unit_name} with great access to amenities.",
            "Cozy {unit_name} designed for maximum privacy and comfort.",
            "Newly renovated {unit_name} located on a quiet floor.",
            "Modern {unit_name} with premium features and a great view.",
            "Affordable and clean {unit_name}, ready for move-in."
        ]

        for prop in properties:
            prop_id = prop[0]
            prop_title = prop[1]
            prop_type = prop[2]
            base_rent = float(prop[3] or 0)

            # Generate 6 units per property
            for i in range(1, 7):
                floor = 1 if i <= 3 else 2
                unit_number = f"Unit {floor}0{i}" if prop_type == 'studio_apartment' else f"Room {floor}0{i}"
                
                # Determine some attributes based on property type
                if prop_type == 'studio_apartment':
                    bedrooms = 1
                    bathrooms = 'OWN'
                    size_sqm = random.randint(22, 35)
                    amenities = random.choice(studio_amenities)
                    parking = random.choice([0, 1])
                elif prop_type == 'dormitory':
                    bedrooms = 0
                    bathrooms = 'SHARE'
                    size_sqm = random.randint(12, 20)
                    amenities = random.choice(dorm_amenities)
                    parking = 0
                else: # boarding_house
                    bedrooms = 1
                    bathrooms = random.choice(['SHARE', 'OWN'])
                    size_sqm = random.randint(15, 25)
                    amenities = random.choice(boarding_amenities)
                    parking = 0

                # Make rent slightly varied
                rent_variation = random.randint(-500, 1500)
                monthly_rent = base_rent + rent_variation
                
                # Ensure it's a nice round number
                monthly_rent = round(monthly_rent / 100) * 100 
                
                # Always vacant
                status = 'vacant'
                desc = random.choice(descriptions).format(unit_name=unit_number.lower())

                unit_data = {
                    "property_id": prop_id,
                    "unit_name": unit_number,
                    "bedrooms": bedrooms,
                    "bathrooms": bathrooms,
                    "size_sqm": size_sqm,
                    "monthly_rent": monthly_rent,
                    "security_deposit": monthly_rent * 2,
                    "status": status,
                    "description": desc,
                    "floor_number": str(floor),
                    "parking_spaces": parking,
                    "amenities": amenities,
                    "updated_at": now
                }

                existing = db.session.execute(check_sql, {"property_id": prop_id, "unit_name": unit_number}).fetchone()
                if existing:
                    print(f"Updating {unit_number} in {prop_title}...")
                    db.session.execute(update_sql, unit_data)
                    updated_count += 1
                else:
                    unit_data["created_at"] = now
                    db.session.execute(insert_sql, unit_data)
                    added_count += 1
                    print(f"Added {unit_number} to {prop_title}")
                    
        db.session.commit()
        print(f"Successfully added {added_count} and updated {updated_count} units.")

if __name__ == "__main__":
    create_dummy_units()
