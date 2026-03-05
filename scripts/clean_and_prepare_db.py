"""
ADIPHAS Database Cleanup & Preparation Script
==============================================
Wipes EBS alerts, IDSR records, evaluation samples, and vectorized data
to provide a clean slate. Keeps: Users, System Activity logs (for history).

Run from project root:
    myenv\\Scripts\\python scripts\\clean_and_prepare_db.py
"""
import sys, os, shutil
sys.path.append(os.path.abspath("."))

from backend.database import SessionLocal
from backend import models

def clean():
    db = SessionLocal()
    try:
        # 1. Wipe EBS alerts (scraped news signals & simulation alerts)
        deleted_alerts = db.query(models.EBSAlert).delete()
        print(f"[OK] Deleted {deleted_alerts} EBS alerts.")

        # 2. Wipe IDSR records (dummy/old data)
        deleted_idsr = db.query(models.IDSRRecord).delete()
        print(f"[OK] Deleted {deleted_idsr} IDSR records.")

        # 3. Wipe evaluation samples
        deleted_eval = db.query(models.EvaluationSample).delete()
        print(f"[OK] Deleted {deleted_eval} evaluation samples.")

        # 4. Keep system_activities — CommandCentre history needs them
        act_count = db.query(models.SystemActivity).count()
        print(f"[KEPT] {act_count} system activity logs preserved for history.")

        db.commit()
        print("\n[OK] Database cleaned successfully.")

        # 5. Reset ChromaDB vector store (delete the data directory)
        chroma_path = os.path.join("data", "chroma_db")
        if os.path.exists(chroma_path):
            shutil.rmtree(chroma_path)
            print(f"[OK] Deleted ChromaDB data at {chroma_path}")
        else:
            print(f"[SKIP] No ChromaDB data found at {chroma_path}")

        print("\n====================================================")
        print("DATABASE IS CLEAN — Ready for testing!")
        print("====================================================")
        print("Next steps:")
        print("  1. Start backend: myenv\\Scripts\\python -m uvicorn backend.main:app --reload")
        print("  2. Seed Cholera: myenv\\Scripts\\python tmp\\simulate_cholera_full.py")
        print("  3. Seed Lassa:   myenv\\Scripts\\python tmp\\simulate_lassa_full.py")
        print("  4. Open UI:      myenv\\Scripts\\python -m streamlit run ui/app.py")
        print("====================================================\n")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Cleanup failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean()
