
import os
from pathlib import Path
import psycopg
from flask import jsonify
from psycopg import errors, sql
from psycopg.rows import dict_row
from sqlalchemy import create_engine

from . import config

_engine = None
SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")

def connect_database(database_url=None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set")
    return psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row)

def init_db():
    """Apply the merged schema. Safe to run repeatedly (IF NOT EXISTS)."""
    with connect_database() as connection:
        connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        
def get_engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL must be set")
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix):]
                break
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine

def get_row(connection, table, id_column, row_id):
    query = sql.SQL("SELECT * FROM {} WHERE {} = %s").format(
        sql.Identifier(table), sql.Identifier(id_column)
    )
    return connection.execute(query, (row_id,)).fetchone()


def insert_row(connection, table, data):
    if not data:
        raise ValueError("No data to insert.")
    columns = list(data)
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    return connection.execute(query, [data[c] for c in columns]).fetchone()


def update_row(connection, table, id_column, row_id, changes, *, allowed=None):
    if not changes:
        raise ValueError("No changes to apply.")
    if allowed is not None:
        unknown = set(changes) - set(allowed)
        if unknown:
            raise ValueError(f"Fields not allowed: {', '.join(sorted(unknown))}")
    columns = list(changes)
    query = sql.SQL("UPDATE {} SET {} WHERE {} = %s RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns
        ),
        sql.Identifier(id_column),
    )
    return connection.execute(query, [changes[c] for c in columns] + [row_id]).fetchone()


def delete_row(connection, table, id_column, row_id):
    query = sql.SQL("DELETE FROM {} WHERE {} = %s").format(
        sql.Identifier(table), sql.Identifier(id_column)
    )
    return connection.execute(query, (row_id,)).rowcount > 0


def register_db_error_handlers(app):
    @app.errorhandler(errors.UniqueViolation)
    def unique_violation(error):
        return jsonify(error="Value already exists."), 409

    @app.errorhandler(errors.ForeignKeyViolation)
    def foreign_key_violation(error):
        return jsonify(error="The record is linked to, or refers to, a record that does not allow this change."), 409

    @app.errorhandler(errors.CheckViolation)
    @app.errorhandler(errors.NotNullViolation)
    def invalid_value(error):
        return jsonify(error="One or more fields contain an invalid/missing value."), 400

    @app.errorhandler(psycopg.OperationalError)
    def database_unavailable(error):
        return jsonify(error="Database is not available right now."), 503

