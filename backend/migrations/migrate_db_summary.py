import sqlite3
import os

db_path = "data/data.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE ebs_alerts ADD COLUMN summary TEXT;")
        print("Successfully added 'summary' column to 'ebs_alerts' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column 'summary' already exists.")
        else:
            print(f"Error: {e}")
    
    conn.commit()
    conn.close()
else:
    print(f"Database {db_path} not found.")
