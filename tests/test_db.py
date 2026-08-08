import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

DATABASE_FILE = BASE_DIR / "test_finsight.db"
SCHEMA_FILE = BASE_DIR / "test_schema.sql"


def create_database():
    print("Creating test database...")

    connection = sqlite3.connect(DATABASE_FILE)

    try:
        # Enable foreign key support
        connection.execute("PRAGMA foreign_keys = ON")

        # Read SQL schema
        schema = SCHEMA_FILE.read_text(
            encoding="utf-8"
        )

        # Create all tables
        connection.executescript(schema)

        connection.commit()

        print("Database created successfully.")
        print(f"Database location: {DATABASE_FILE}")

        # Check tables
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        print("\nTables created:")

        for table in tables:
            print(f"  - {table[0]}")

    except sqlite3.Error as error:
        print("Database error:")
        print(error)

    finally:
        connection.close()


if __name__ == "__main__":
    create_database()