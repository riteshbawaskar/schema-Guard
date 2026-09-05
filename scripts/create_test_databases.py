"""Creates test_data/source.db and test_data/destination.db - two SQLite
databases with intentional, well-known schema differences so the full
application workflow can be exercised without any external database.

Run: python scripts/create_test_databases.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DATA_DIR = ROOT / "test_data"


def _fresh_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def build_source(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE CUSTOMER (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            phone VARCHAR(30),
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED'))
        );
        CREATE INDEX idx_customer_status ON CUSTOMER(status);
        CREATE INDEX idx_customer_name ON CUSTOMER(last_name, first_name);

        CREATE TABLE ADDRESS (
            address_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            line1 VARCHAR(255) NOT NULL,
            line2 VARCHAR(255),
            city VARCHAR(100) NOT NULL,
            state VARCHAR(50),
            postal_code VARCHAR(20),
            country VARCHAR(2) NOT NULL DEFAULT 'US',
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        CREATE TABLE ACCOUNT (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            account_number VARCHAR(34) NOT NULL UNIQUE,
            account_type VARCHAR(20) NOT NULL,
            balance NUMERIC(18,2) NOT NULL DEFAULT 0,
            opened_date DATE NOT NULL,
            closed_date DATE,
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );
        CREATE UNIQUE INDEX ux_account_number ON ACCOUNT(account_number);

        CREATE TABLE "TRANSACTION" (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description VARCHAR(255),
            FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );
        CREATE INDEX idx_transaction_account ON "TRANSACTION"(account_id);
        CREATE INDEX idx_transaction_date ON "TRANSACTION"(transaction_date);

        CREATE TABLE PRODUCT (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku VARCHAR(50) NOT NULL UNIQUE,
            product_name VARCHAR(255) NOT NULL,
            unit_price NUMERIC(12,2) NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE ORDER_HEADER (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            total_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        CREATE TABLE ORDER_DETAIL (
            order_id INTEGER NOT NULL,
            line_number INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(12,2) NOT NULL,
            PRIMARY KEY (order_id, line_number),
            FOREIGN KEY (order_id) REFERENCES ORDER_HEADER(order_id),
            FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id)
        );

        -- AX* tables, used to exercise reusable table filters
        CREATE TABLE AX_CUSTOMER (
            ax_customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_id VARCHAR(50) NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            migrated_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        CREATE TABLE AX_ACCOUNT (
            ax_account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_account_number VARCHAR(50) NOT NULL,
            account_id INTEGER NOT NULL,
            FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );

        -- This table exists ONLY in source - will show as REMOVED when
        -- compared against destination.
        CREATE TABLE AX_TRANSACTION (
            ax_transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_ref VARCHAR(50) NOT NULL,
            transaction_id INTEGER NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES "TRANSACTION"(transaction_id)
        );
        """
    )
    conn.commit()


def build_destination(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.executescript(
        """
        -- CUSTOMER: added column (loyalty_points), removed column (phone),
        -- datatype mismatch (email length), nullable mismatch (last_name),
        -- default mismatch (status).
        CREATE TABLE CUSTOMER (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100),
            email VARCHAR(320) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            loyalty_points INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED','PENDING'))
        );
        CREATE INDEX idx_customer_status ON CUSTOMER(status);
        -- idx_customer_name index removed intentionally (index difference)

        CREATE TABLE ADDRESS (
            address_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            line1 VARCHAR(255) NOT NULL,
            line2 VARCHAR(255),
            city VARCHAR(100) NOT NULL,
            state VARCHAR(50),
            postal_code VARCHAR(20),
            country VARCHAR(2) NOT NULL DEFAULT 'US',
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        -- ACCOUNT: PK difference - composite PK added (account_id, customer_id)
        -- instead of single-column PK (primary key difference / composite key diff).
        CREATE TABLE ACCOUNT (
            account_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            account_number VARCHAR(34) NOT NULL UNIQUE,
            account_type VARCHAR(20) NOT NULL,
            balance NUMERIC(18,2) NOT NULL DEFAULT 0,
            opened_date DATE NOT NULL,
            closed_date DATE,
            PRIMARY KEY (account_id, customer_id),
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );
        CREATE UNIQUE INDEX ux_account_number ON ACCOUNT(account_number);

        CREATE TABLE "TRANSACTION" (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description VARCHAR(255),
            FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );
        CREATE INDEX idx_transaction_account ON "TRANSACTION"(account_id);
        CREATE INDEX idx_transaction_date ON "TRANSACTION"(transaction_date);

        -- PRODUCT: FK difference - added new FK to CATEGORY (added column + FK).
        CREATE TABLE CATEGORY (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name VARCHAR(100) NOT NULL
        );

        CREATE TABLE PRODUCT (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku VARCHAR(50) NOT NULL UNIQUE,
            product_name VARCHAR(255) NOT NULL,
            unit_price NUMERIC(12,2) NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            category_id INTEGER,
            FOREIGN KEY (category_id) REFERENCES CATEGORY(category_id)
        );

        CREATE TABLE ORDER_HEADER (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            total_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        CREATE TABLE ORDER_DETAIL (
            order_id INTEGER NOT NULL,
            line_number INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(12,2) NOT NULL,
            PRIMARY KEY (order_id, line_number),
            FOREIGN KEY (order_id) REFERENCES ORDER_HEADER(order_id),
            FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id)
        );

        CREATE TABLE AX_CUSTOMER (
            ax_customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_id VARCHAR(50) NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            migrated_at TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
        );

        CREATE TABLE AX_ACCOUNT (
            ax_account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            legacy_account_number VARCHAR(50) NOT NULL,
            account_id INTEGER NOT NULL,
            FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );

        -- New AX table only in destination - will show as ADDED.
        CREATE TABLE AX_BALANCE_SNAPSHOT (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            balance NUMERIC(18,2) NOT NULL,
            FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id)
        );

        -- AX_TEMP_STAGING intentionally present to exercise exclude patterns
        -- (e.g. a filter with include AX* / exclude AX_TEMP*).
        CREATE TABLE AX_TEMP_STAGING (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT
        );
        -- Note: AX_TRANSACTION does NOT exist here (REMOVED vs source).
        """
    )
    conn.commit()


def main() -> None:
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    src_path = TEST_DATA_DIR / "source.db"
    dst_path = TEST_DATA_DIR / "destination.db"

    src_conn = _fresh_db(src_path)
    build_source(src_conn)
    src_conn.close()

    dst_conn = _fresh_db(dst_path)
    build_destination(dst_conn)
    dst_conn.close()

    print(f"Created {src_path}")
    print(f"Created {dst_path}")
    print(
        "Intentional differences: table added (AX_BALANCE_SNAPSHOT, CATEGORY), "
        "table removed (AX_TRANSACTION), column added (loyalty_points, category_id), "
        "column removed (phone), datatype mismatch (email length), "
        "nullable mismatch (last_name), default mismatch (status), "
        "PK/composite key difference (ACCOUNT), FK difference (PRODUCT->CATEGORY), "
        "index difference (idx_customer_name removed)."
    )


if __name__ == "__main__":
    main()
