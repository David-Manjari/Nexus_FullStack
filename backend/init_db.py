import argparse
from pathlib import Path
from .db import connect_database

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

TABLES = (
    "Audit_Log", "Notifications", "Disbursements", "Approvals", "Procurements",
    "Asset_Assignments", "Requests", "Vehicle_Details", "Assets", "Tasks",
    "Projects", "Users",
)

def init_db(reset=False):
    with connect_database() as connection:
        if reset:
            for table in TABLES:
                connection.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        connection.execute(SCHEMA_FILE.read_text())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()
    init_db(reset=args.reset)
    print("Database reset and schema applied." if args.reset else "Schema applied.")

if __name__ == "__main__":
    main()