from werkzeug.security import generate_password_hash
from .db import connect_database

DEMO_USERS = [
    ("admin", "admin@nexus.com", "Admin-demo-2026", "admin"),
    ("manager", "manager@nexus.com", "Manager-demo-2026", "manager"),
    ("storemanager", "store@nexus.com", "Store-demo-2026", "store_manager"),
    ("staff", "staff@nexus.com", "Staff-demo-2026", "staff"),
]

DEMO_ASSETS = [
    ("tool", "Cordless Drill", "Power tool", "Bosch", "TL-001", "available"),
    ("tool", "Tape Measure", "Hand tool", "Stanley", "TL-002", "available"),
    ("tool", "Angle Grinder", "Power tool", "Makita", "TL-003", "maintenance"),
    ("device", "Dell Laptop", "Laptop", "Dell", "DV-001", "available"),
    ("device", "Tablet", "Tablet", "Samsung", "DV-002", "available"),
]

DEMO_VEHICLES = [
    ("Pickup Truck", "Pickup", "Toyota", "VH-001", "KDA 123A", "Toyota", "Hilux", 45200),
]


def seed():
    with connect_database() as connection:
        for username, email, password, role in DEMO_USERS:
            connection.execute(
                """
                INSERT INTO "Users" (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (username, email, generate_password_hash(password), role),
            )

        store_manager = connection.execute(
            'SELECT user_id FROM "Users" WHERE username = %s', ("storemanager",)
        ).fetchone()["user_id"]
        manager = connection.execute(
            'SELECT user_id FROM "Users" WHERE username = %s', ("manager",)
        ).fetchone()["user_id"]

        for asset_type, name, category, brand, serial_no, status in DEMO_ASSETS:
            connection.execute(
                """
                INSERT INTO "Assets"
                    (asset_type, name, category, brand, serial_no, status, added_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (serial_no) DO NOTHING
                """,
                (asset_type, name, category, brand, serial_no, status, store_manager),
            )

        for name, category, brand, serial_no, plate_no, make, model, mileage in DEMO_VEHICLES:
            created = connection.execute(
                """
                INSERT INTO "Assets"
                    (asset_type, name, category, brand, serial_no, added_by)
                VALUES ('vehicle', %s, %s, %s, %s, %s)
                ON CONFLICT (serial_no) DO NOTHING
                RETURNING asset_id
                """,
                (name, category, brand, serial_no, store_manager),
            ).fetchone()
            if created:
                connection.execute(
                    """
                    INSERT INTO "Vehicle_Details" (asset_id, plate_no, make, model, mileage)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (created["asset_id"], plate_no, make, model, mileage),
                )

        if not connection.execute('SELECT 1 FROM "Projects" LIMIT 1').fetchone():
            connection.execute(
                """
                INSERT INTO "Projects" (name, description, status, manager_id)
                VALUES ('Warehouse Upgrade', 'Demo project for development.', 'active', %s)
                """,
                (manager,),
            )
    print("Demo data loaded.")


if __name__ == "__main__":
    seed()