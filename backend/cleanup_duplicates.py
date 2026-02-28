import sys
import os

# Add the project root to the path so we can import backend models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import EBSAlert

def cleanup_duplicates():
    print("Starting database cleanup for duplicate EBSAlerts...")
    db = SessionLocal()
    try:
        # Get all alerts, ordered by timestamp ascending
        all_alerts = db.query(EBSAlert).order_by(EBSAlert.timestamp.asc()).all()
        print(f"Found {len(all_alerts)} total alerts.")

        seen_content = set()
        duplicates = []
        kept = 0

        for alert in all_alerts:
            # We'll use the title/text as the primary deduplication key for legacy records
            # since they don't have URLs yet.
            content_key = alert.text.lower().strip() if alert.text else ""
            
            if content_key in seen_content:
                duplicates.append(alert)
            else:
                seen_content.add(content_key)
                kept += 1

        print(f"Identified {len(duplicates)} duplicates. Keeping {kept} unique records.")

        if duplicates:
            # Delete duplicates
            for dup in duplicates:
                db.delete(dup)
            
            # Commit the deletions
            db.commit()
            print("Duplicates successfully removed from the database.")
        else:
            print("No duplicates found. Database is already clean.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_duplicates()
