import sys
import os

# Add the project root to the path so we can import backend models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine, SessionLocal
from backend.models import Base
from sqlalchemy import text

def apply_schema_updates():
    print("Applying schema updates to database...")
    
    # create_all will create new tables (like system_activities)
    # but it WILL NOT add new columns (like 'url') to existing tables in SQLite.
    Base.metadata.create_all(bind=engine)
    print("Created any missing tables.")

    # Manually add the 'url' column to ebs_alerts if it doesn't exist
    db = SessionLocal()
    try:
        # Check if column exists
        result = db.execute(text("PRAGMA table_info(ebs_alerts)")).fetchall()
        columns = [row[1] for row in result]
        
        if 'url' not in columns:
            print("Adding 'url' column to ebs_alerts...")
            db.execute(text("ALTER TABLE ebs_alerts ADD COLUMN url VARCHAR"))
            db.commit()
            
            # Create the index
            print("Creating index on 'url'...")
            db.execute(text("CREATE UNIQUE INDEX ix_ebs_alerts_url ON ebs_alerts (url)"))
            db.commit()
            print("Schema update for ebs_alerts complete.")
        else:
            print("'url' column already exists in ebs_alerts.")
            
    except Exception as e:
        print(f"Error updating schema: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    apply_schema_updates()
