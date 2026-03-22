#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for Ghostwire Proxy

This script migrates all data from the existing SQLite database to PostgreSQL.
It preserves all UUIDs, timestamps, and relationships.

Usage:
    python migrate_sqlite_to_postgres.py

Environment Variables:
    SQLITE_PATH: Path to SQLite database (default: /data/sqlite/ghostwire-proxy.db)
    POSTGRES_URL or POSTGRES_* vars: PostgreSQL connection info

The script will:
1. Read all data from SQLite
2. Insert data into PostgreSQL (tables must already exist)
3. Verify row counts match
"""

import os
import sys
import sqlite3
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_batch

# Tables in dependency order (parents before children)
# Foreign key dependencies:
# - local_auth_users -> auth_walls
# - auth_providers -> auth_walls
# - ldap_configs -> auth_walls
# - auth_wall_sessions -> auth_walls
# - access_list_entries -> access_lists
# - proxy_hosts -> certificates, access_lists, auth_walls
# - upstream_servers -> proxy_hosts
# - proxy_locations -> proxy_hosts
# - dns_zones -> dns_providers
# - waf_rules -> waf_rule_sets
# - threat_events -> threat_actors, proxy_hosts, waf_rules
# - firewall_blocklist -> firewall_connectors
# - alert_preferences -> users, alert_channels
# - push_subscriptions -> users
# - analytics_* -> proxy_hosts
# - audit_logs -> users
# - traffic_logs -> proxy_hosts

TABLES_IN_ORDER = [
    # Independent tables (no foreign keys)
    "users",
    "certificates",
    "settings",
    "dns_providers",
    "threat_actors",
    "firewall_connectors",
    "geoip_settings",
    "access_lists",
    "auth_walls",
    "waf_rule_sets",
    "alert_channels",
    "threat_thresholds",
    "rate_limit_rules",
    "geoip_rules",

    # Second level (single FK)
    "local_auth_users",
    "auth_providers",
    "ldap_configs",
    "auth_wall_sessions",
    "access_list_entries",
    "dns_zones",
    "waf_rules",
    "firewall_blocklist",
    "push_subscriptions",

    # Third level (depends on multiple tables above)
    "proxy_hosts",

    # Fourth level (depends on proxy_hosts)
    "upstream_servers",
    "proxy_locations",
    "threat_events",
    "analytics_hourly",
    "analytics_daily",
    "analytics_geo",
    "traffic_logs",

    # Fifth level
    "alert_preferences",
    "audit_logs",
]


def get_sqlite_connection(sqlite_path: str):
    """Create SQLite connection."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection(postgres_url: str):
    """Create PostgreSQL connection."""
    return psycopg2.connect(postgres_url)


def get_sqlite_tables(sqlite_conn) -> set:
    """Get all table names from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
    )
    return {row[0] for row in cursor.fetchall()}


def get_postgres_tables(pg_conn) -> set:
    """Get all table names from PostgreSQL."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
    )
    return {row[0] for row in cursor.fetchall()}


def get_table_columns(sqlite_conn, table_name: str) -> list:
    """Get column names from SQLite table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def get_postgres_columns(pg_conn, table_name: str) -> list:
    """Get column names from PostgreSQL table."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        (table_name,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_postgres_column_types(pg_conn, table_name: str) -> dict:
    """Get column types from PostgreSQL table."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public'",
        (table_name,)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def convert_value(value, pg_type: str):
    """Convert SQLite value to PostgreSQL compatible value."""
    if value is None:
        return None

    # Convert SQLite integer booleans to PostgreSQL booleans
    if pg_type == 'boolean':
        if isinstance(value, int):
            return bool(value)
        return value

    return value


def migrate_table(sqlite_conn, pg_conn, table_name: str, batch_size: int = 1000):
    """Migrate a single table from SQLite to PostgreSQL."""

    # Get columns from both databases
    sqlite_columns = set(get_table_columns(sqlite_conn, table_name))
    postgres_columns = set(get_postgres_columns(pg_conn, table_name))

    # Use only columns that exist in both
    common_columns = sqlite_columns & postgres_columns

    if not common_columns:
        print(f"  Skipping {table_name}: no common columns between SQLite and PostgreSQL")
        return 0

    columns_list = sorted(common_columns)

    # Get PostgreSQL column types for conversion
    pg_column_types = get_postgres_column_types(pg_conn, table_name)

    # Count rows in SQLite
    cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    sqlite_count = cursor.fetchone()[0]

    if sqlite_count == 0:
        print(f"  {table_name}: 0 rows (empty)")
        return 0

    # Clear existing data in PostgreSQL (with CASCADE to handle FKs)
    pg_cursor = pg_conn.cursor()
    try:
        pg_cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
        pg_conn.commit()
    except Exception as e:
        pg_conn.rollback()
        print(f"  Warning: Could not truncate {table_name}: {e}")

    # Build INSERT statement
    columns_str = ", ".join(columns_list)
    placeholders = ", ".join(["%s"] * len(columns_list))
    insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    # Fetch all rows from SQLite
    cursor = sqlite_conn.execute(f"SELECT {columns_str} FROM {table_name}")

    # Insert in batches
    rows_migrated = 0
    batch = []

    for row in cursor:
        # Convert each value based on PostgreSQL column type
        row_data = tuple(
            convert_value(row[i], pg_column_types.get(columns_list[i], 'text'))
            for i in range(len(columns_list))
        )
        batch.append(row_data)

        if len(batch) >= batch_size:
            try:
                execute_batch(pg_cursor, insert_sql, batch)
                pg_conn.commit()
                rows_migrated += len(batch)
                print(f"    {table_name}: {rows_migrated}/{sqlite_count} rows migrated...")
            except Exception as e:
                pg_conn.rollback()
                print(f"    Error inserting batch: {e}")
            batch = []

    # Insert remaining rows
    if batch:
        try:
            execute_batch(pg_cursor, insert_sql, batch)
            pg_conn.commit()
            rows_migrated += len(batch)
        except Exception as e:
            pg_conn.rollback()
            print(f"    Error inserting final batch: {e}")

    # Verify count
    pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    pg_count = pg_cursor.fetchone()[0]

    if pg_count != sqlite_count:
        print(f"  {table_name}: {pg_count}/{sqlite_count} rows migrated (some rows may have been skipped)")
    else:
        print(f"  {table_name}: {pg_count} rows migrated successfully")

    return pg_count


def main():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration for Ghostwire Proxy")
    print("=" * 60)
    print()

    # Get connection parameters
    sqlite_path = os.environ.get("SQLITE_PATH", "/data/sqlite/ghostwire-proxy.db")
    postgres_url = os.environ.get("POSTGRES_URL")

    if not postgres_url:
        # Build from individual env vars
        pg_user = os.environ.get("POSTGRES_USER", "ghostwire")
        pg_pass = os.environ.get("POSTGRES_PASSWORD")
        pg_host = os.environ.get("POSTGRES_HOST", "localhost")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_db = os.environ.get("POSTGRES_DB", "ghostwire_proxy")

        if not pg_pass:
            print("ERROR: POSTGRES_PASSWORD environment variable is required")
            sys.exit(1)

        postgres_url = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

    print(f"SQLite database: {sqlite_path}")
    # Hide password in output
    display_url = postgres_url
    if "@" in display_url:
        parts = display_url.split("@")
        creds = parts[0].split(":")
        if len(creds) >= 2:
            display_url = f"{creds[0]}:****@{parts[1]}"
    print(f"PostgreSQL: {display_url}")
    print()

    # Check SQLite exists
    if not os.path.exists(sqlite_path):
        print(f"ERROR: SQLite database not found: {sqlite_path}")
        sys.exit(1)

    # Connect to databases
    print("Connecting to databases...")
    sqlite_conn = get_sqlite_connection(sqlite_path)
    pg_conn = get_postgres_connection(postgres_url)

    print("Connected successfully!")
    print()

    # Get available tables
    sqlite_tables = get_sqlite_tables(sqlite_conn)
    postgres_tables = get_postgres_tables(pg_conn)

    print(f"SQLite tables: {len(sqlite_tables)}")
    print(f"PostgreSQL tables: {len(postgres_tables)}")
    print()

    # Filter to tables that exist in both
    common_tables = sqlite_tables & postgres_tables
    tables_to_migrate = [t for t in TABLES_IN_ORDER if t in common_tables]

    # Add any tables not in our predefined order
    for t in sorted(common_tables - set(TABLES_IN_ORDER)):
        tables_to_migrate.append(t)

    print(f"Tables to migrate: {len(tables_to_migrate)}")
    print()

    # Run migrations
    print("Migrating tables...")
    print("-" * 40)

    total_rows = 0
    start_time = datetime.now()

    for table_name in tables_to_migrate:
        try:
            rows = migrate_table(sqlite_conn, pg_conn, table_name)
            total_rows += rows
        except Exception as e:
            print(f"  ERROR migrating {table_name}: {e}")
            pg_conn.rollback()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("-" * 40)
    print()
    print(f"Migration completed!")
    print(f"  Total rows migrated: {total_rows:,}")
    print(f"  Duration: {duration:.1f} seconds")
    print()

    # Close connections
    sqlite_conn.close()
    pg_conn.close()

    # Backup recommendation
    print("Recommendation:")
    print(f"  Keep SQLite backup at: {sqlite_path}.backup")
    print("  After verifying PostgreSQL data, you can remove the SQLite database")
    print()


if __name__ == "__main__":
    main()
