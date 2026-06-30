from app import create_app, db
from sqlalchemy import text

def update():
    app = create_app()
    with app.app_context():
        updates = [
            ("Sunnyvale Apartment Complex", "sunnyvale"),
            ("Oakwood Dormitory", "oakwood"),
            ("Maple Boarding House", "maple")
        ]
        
        sql = text("UPDATE properties SET portal_subdomain = :subdomain WHERE title = :title")
        for title, subdomain in updates:
            db.session.execute(sql, {"title": title, "subdomain": subdomain})
            print(f"Updated {title} to subdomain {subdomain}")
            
        db.session.commit()

if __name__ == "__main__":
    update()
