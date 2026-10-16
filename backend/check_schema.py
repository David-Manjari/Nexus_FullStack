import sys
from sqlalchemy import inspect
from .db import get_engine
from .models import Base


def find_problems():
    inspector = inspect(get_engine())
    existing = set(inspector.get_table_names())
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            problems.append(f"Missing table: {table.name}")
            continue
        db_columns = {c["name"] for c in inspector.get_columns(table.name)}
        model_columns = {c.name for c in table.columns}
        for column in sorted(model_columns - db_columns):
            problems.append(f"{table.name}: model has '{column}' but the database does not")
        for column in sorted(db_columns - model_columns):
            problems.append(f"{table.name}: database has '{column}' but the model does not")
    for table in sorted(existing - {t.name for t in Base.metadata.sorted_tables}):
        problems.append(f"Table '{table}' exists in the database but has no model")
    return problems


def main():
    problems = find_problems()
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("Models and database match.")


if __name__ == "__main__":
    main()