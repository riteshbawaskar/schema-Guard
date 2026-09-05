"""Check a Snowflake connection using a Programmatic Access Token.

Edit the configuration constants below, then run:

    python scripts/check_snowflake_pat.py

Exit code 0 means the connection succeeded. The PAT is never printed.
"""
from __future__ import annotations

import sys

import snowflake.connector


# Embedded connection configuration. Replace these values for your account.
ACCOUNT = "your-account"
USERNAME = "your-username"
PAT = "your-programmatic-access-token"
WAREHOUSE = "your-warehouse"
DATABASE = "your-database"
SCHEMA = "PUBLIC"
ROLE = None  # Example: "SYSADMIN"
URL = None  # Example: "https://your-account.region.snowflakecomputing.com"


def check_connection() -> bool:
    connection_args = {
        "account": ACCOUNT,
        "user": USERNAME,
        "password": PAT,
        "warehouse": WAREHOUSE,
        "database": DATABASE,
        "schema": SCHEMA,
        "login_timeout": 15,
    }
    if ROLE:
        connection_args["role"] = ROLE
    if URL:
        connection_args["host"] = URL.removeprefix("https://").removeprefix("http://").rstrip("/")

    connection = None
    cursor = None
    try:
        connection = snowflake.connector.connect(**connection_args)
        cursor = connection.cursor()
        cursor.execute("SELECT CURRENT_USER(), CURRENT_ACCOUNT(), CURRENT_REGION()")
        user, account, region = cursor.fetchone()
        print(f"Connection successful: user={user}, account={account}, region={region}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Connection failed: {exc}", file=sys.stderr)
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(0 if check_connection() else 1)