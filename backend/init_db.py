# Create or reset database tables from schema.sql.
# python -m backend.init_db           # create missing tables
# python -m backend.init_db --reset   # drop every table then recreate them

import argparse
from pathlib import Path

from .db import connect_database

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

# tables in schema.sql, sync if a new table is added.
TABLES = (
    "Audit_Log", "Notifications", "Disbursement_Audit_Logs", "Payment_History",
    "Disbursements", "Approval_Views", "Approvals", "Request_History",
    "Procurement", "Asset_Assignments", "Requests", "Vehicle_Details", "Assets",
    "Project_Status_History", "Approval_Requests", "Tasks", "Projects", "Users",
    "Procurements",
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