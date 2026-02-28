import sqlite3
import os

db_path = "data/data.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(ebs_alerts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "ai_powered" not in columns:
            print("Adding 'ai_powered' column to 'ebs_alerts' table...")
            cursor.execute("ALTER TABLE ebs_alerts ADD COLUMN ai_powered INTEGER DEFAULT 0;")
            print("Migration complete.")
        else:
            print("'ai_powered' column already exists.")
    except Exception as e:
        print(f"Error during migration: {e}")
    
    conn.commit()
    conn.close()
else:
    print(f"Database {db_path} not found.")
