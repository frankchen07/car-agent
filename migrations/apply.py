"""Apply migrations to the database."""
import os
import psycopg
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def apply():
    db_url = os.environ["DATABASE_URL"]
    migrations_dir = Path(__file__).parent
    sql_files = sorted(migrations_dir.glob("*.sql"))

    with psycopg.connect(db_url) as conn:
        for sql_file in sql_files:
            print(f"Applying {sql_file.name}...")
            conn.execute(sql_file.read_text())
        conn.commit()
    print("Done.")

if __name__ == "__main__":
    apply()
