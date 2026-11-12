"""Copy application data inside Render's private network without logging URLs.

The source is never modified. Destination writes and the recovery receipt commit
atomically. Refuse a nonempty destination rather than overwriting its data.
"""
import hashlib
import json
from datetime import date, datetime

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, func, inspect, select, text

from .db import Base, make_engine, now

receipt_metadata = MetaData()
receipts = Table("migration_receipts", receipt_metadata,
                 Column("id", String(80), primary_key=True),
                 Column("created_at", DateTime, nullable=False),
                 Column("sha256", String(64), nullable=False),
                 Column("counts", JSON, nullable=False),
                 Column("snapshot", JSON, nullable=False))
RECEIPT = "render-to-neon-v1"


def normalized(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def digest(payload):
    return hashlib.sha256(json.dumps(normalized(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def rows(connection):
    return {table.name: [dict(row) for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
            for table in Base.metadata.sorted_tables}


def migrate(source_url, target_url):
    source, target = make_engine(source_url), make_engine(target_url)
    try:
        return copy_database(source, target)
    finally:
        source.dispose()
        target.dispose()


def copy_database(source, target):
    # A completed migration must never re-import old data over new review actions.
    with target.connect() as connection:
        if inspect(connection).has_table(receipts.name):
            receipt = connection.execute(select(receipts).where(receipts.c.id == RECEIPT)).mappings().first()
            if receipt:
                return {"status": "already_completed", "counts": receipt["counts"], "sha256": receipt["sha256"]}

    with source.begin() as source_connection:
        existing = set(inspect(source_connection).get_table_names())
        expected = set(Base.metadata.tables)
        if not expected <= existing:
            raise RuntimeError("Source application schema is incomplete; nothing copied")
        if existing - expected - {receipts.name}:
            raise RuntimeError("Unexpected source tables require an explicit migration review")
        if source.dialect.name == "postgresql":
            names = ", ".join(source.dialect.identifier_preparer.quote(t.name) for t in Base.metadata.sorted_tables)
            source_connection.execute(text(f"LOCK TABLE {names} IN SHARE MODE"))
        payload = rows(source_connection)
        checksum = digest(payload)
        counts = {name: len(items) for name, items in payload.items()}
        with target.begin() as connection:
            if target.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(8431983)"))
            Base.metadata.create_all(connection)
            receipt_metadata.create_all(connection)
            if any(connection.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables):
                raise RuntimeError("Destination contains application data; refusing to overwrite")
            for table in Base.metadata.sorted_tables:
                if payload[table.name]:
                    connection.execute(table.insert(), payload[table.name])
            if digest(rows(connection)) != checksum:
                raise RuntimeError("Migration verification failed; destination transaction rolled back")
            if target.dialect.name == "postgresql":
                for table in Base.metadata.sorted_tables:
                    if "id" in table.c and isinstance(table.c.id.type, Integer):
                        maximum = connection.scalar(select(func.max(table.c.id)))
                        connection.execute(text("SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :value, :called)"),
                                           {"table_name": table.name, "value": maximum or 1, "called": maximum is not None})
            connection.execute(receipts.insert().values(id=RECEIPT, created_at=now(), sha256=checksum,
                                                       counts=counts, snapshot=normalized(payload)))
    return {"status": "completed", "counts": counts, "sha256": checksum}
