"""
ADIPHAS Data Migration Script: SQLite → Neon PostgreSQL
Reads all data from the local SQLite database and inserts it into the cloud Neon database.
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# --- Source: Local SQLite ---
SQLITE_URL = "sqlite:///./data/data.db"
sqlite_engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
SqliteSession = sessionmaker(bind=sqlite_engine)

# --- Target: Neon PostgreSQL ---
PG_URL = os.getenv("DATABASE_URL")
if not PG_URL:
    print("ERROR: DATABASE_URL not found in .env")
    sys.exit(1)

if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

pg_engine = create_engine(PG_URL, pool_pre_ping=True)
PgSession = sessionmaker(bind=pg_engine)

# --- Import models to create tables ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.database import Base
from backend import models  # noqa: F401 — registers all models with Base

# Tables to migrate (in dependency order)
TABLES = [
    "users",
    "idsr_records",
    "ebs_alerts",
    "system_activities",
    "autonomous_snapshots",
    "predictive_snapshots",
    "evaluation_samples",
]

def migrate():
    print("=" * 50)
    print("ADIPHAS Migration: SQLite -> Neon PostgreSQL")
    print("=" * 50)
    
    # 1. Create all tables in PostgreSQL
    print("\n[1/3] Creating tables in Neon PostgreSQL...")
    Base.metadata.create_all(bind=pg_engine)
    print("      [OK] All tables created.")
    
    # 2. Check what exists in SQLite
    sqlite_inspector = inspect(sqlite_engine)
    existing_tables = sqlite_inspector.get_table_names()
    print(f"\n[2/3] SQLite tables found: {existing_tables}")
    
    # 3. Migrate each table
    print("\n[3/3] Migrating data...")
    total_rows = 0
    
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy import MetaData
    
    meta = MetaData()
    meta.reflect(bind=pg_engine)
    
    for table_name in TABLES:
        if table_name not in existing_tables:
            print(f"      [SKIP]  {table_name}: not in SQLite, skipping.")
            continue
        
        # Read all rows from SQLite
        with sqlite_engine.connect() as src_conn:
            rows = src_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            columns = src_conn.execute(text(f"SELECT * FROM {table_name} LIMIT 0")).keys()
            col_names = list(columns)
        
        if not rows:
            print(f"      [SKIP]  {table_name}: 0 rows, skipping.")
            continue
            
        target_table = meta.tables[table_name]
        target_cols = [c.name for c in target_table.columns]
        
        # Prepare batch data
        batch_data = []
        for row in rows:
            row_dict = dict(zip(col_names, row))
            filtered_row = {k: v for k, v in row_dict.items() if k in target_cols}
            
            # Map known boolean columns properly
            for k in ['verified', 'ai_powered', 'policy_alert', 'requires_hitl', 'is_vectorized', 'is_anomaly']:
                if k in filtered_row and isinstance(filtered_row[k], int):
                    filtered_row[k] = bool(filtered_row[k])
                    
            batch_data.append(filtered_row)
            
        try:
            with pg_engine.begin() as dest_conn:
                stmt = insert(target_table).values(batch_data)
                stmt = stmt.on_conflict_do_nothing()
                result = dest_conn.execute(stmt)
                inserted = result.rowcount
            
            total_rows += inserted
            print(f"      [OK] {table_name}: {inserted} rows migrated (duplicates ignored)")
        except Exception as e:
            err_str = str(e)[:150]
            print(f"      [WARN] {table_name} insert error: {err_str}")
    
    print(f"\n{'=' * 50}")
    print(f"Migration complete! {total_rows} total rows transferred to Neon.")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    migrate()
