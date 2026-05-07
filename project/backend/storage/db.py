import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "tasks.db"


def get_conn() -> sqlite3.Connection:
    """Create sqlite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize required database tables."""
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress REAL NOT NULL,
                current_row INTEGER NOT NULL,
                total_rows INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                output_path TEXT NOT NULL,
                selected_column TEXT,
                contact_name TEXT,
                contact_phone TEXT,
                contact_email TEXT,
                company_name TEXT,
                address_detail TEXT,
                province TEXT,
                city TEXT,
                country TEXT,
                delivery_note TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        conn.commit()
    finally:
        conn.close()
