import sqlite3
import os

db_path = os.path.join("backend", "data", "data.db")
if not os.path.exists(db_path):
    # Try current directory if backend prefix fails
    db_path = os.path.join("data", "data.db")

print(f"Connecting to database at: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(ebs_alerts)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "created_at" not in columns:
        print("Adding 'created_at' column to 'ebs_alerts' table...")
        # Step 1: Add as nullable without dynamic default
        cursor.execute("ALTER TABLE ebs_alerts ADD COLUMN created_at DATETIME")
        
        # Step 2: Update existing rows with current time
        from datetime import datetime
        now = datetime.now().replace(microsecond=0)
        cursor.execute("UPDATE ebs_alerts SET created_at = ?", (now,))
        
        conn.commit()
        print("Column added and existing rows updated successfully.")
    else:
        print("Column 'created_at' already exists.")
        
    conn.close()
except Exception as e:
    print(f"Migration failed: {e}")
