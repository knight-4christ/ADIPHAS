import pandas as pd
import io
from sqlalchemy.orm import Session
from backend import models
from datetime import datetime

class IngestionAgent:
    """
    Agent responsible for ingesting IDSR CSV data into the database.
    """
    def __init__(self):
        self.required_columns = [
            "facility_id", "lga_code", "state_code", "disease", 
            "week_start", "cases", "deaths", "reporting_week"
        ]
    
    def process_idsr_csv(self, file_content: bytes, db: Session):
        """
        Process and ingest IDSR CSV data.
        Returns:
            dict: {"ingested_rows": int, "errors": list, "status": str, "trace": list}
        """
        trace = []
        trace.append({
            "step": "Initializing IDSR Ingestion Agent...",
            "timestamp": datetime.now().replace(microsecond=0)
        })
        
        try:
            trace.append({
                "step": "Reading CSV file content...",
                "timestamp": datetime.now().replace(microsecond=0)
            })
            df = pd.read_csv(io.BytesIO(file_content))
            
            # Basic validation: check columns
            trace.append({
                "step": f"Validating required columns: {', '.join(self.required_columns)}",
                "timestamp": datetime.now().replace(microsecond=0)
            })
            
            if not all(col in df.columns for col in self.required_columns):
                missing = [col for col in self.required_columns if col not in df.columns]
                trace.append({
                    "step": f"Validation failed. Missing columns: {', '.join(missing)}",
                    "timestamp": datetime.now().replace(microsecond=0)
                })
                return {
                    "ingested_rows": 0,
                    "errors": [f"Missing required columns: {', '.join(missing)}"],
                    "status": "failed",
                    "trace": trace
                }

            trace.append({
                "step": f"Validation passed. Found {len(df)} rows to process.",
                "timestamp": datetime.now().replace(microsecond=0)
            })

            ingested_count = 0
            skipped_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    # Deduplication check: LGA + Disease + week_start + facility_id
                    w_start = pd.to_datetime(row["week_start"]).date()
                    exists = db.query(models.IDSRRecord).filter(
                        models.IDSRRecord.lga_code == str(row["lga_code"]),
                        models.IDSRRecord.disease == str(row["disease"]),
                        models.IDSRRecord.week_start == w_start,
                        models.IDSRRecord.facility_id == str(row["facility_id"])
                    ).first()

                    if exists:
                        skipped_count += 1
                        continue

                    record = models.IDSRRecord(
                        facility_id=str(row["facility_id"]),
                        lga_code=str(row["lga_code"]),
                        state_code=str(row["state_code"]),
                        disease=str(row["disease"]),
                        week_start=w_start,
                        cases=int(row["cases"]),
                        deaths=int(row["deaths"]),
                        reporting_week=int(row["reporting_week"]),
                        reporters_notes=str(row.get("reporters_notes", ""))
                    )
                    db.add(record)
                    ingested_count += 1
                    
                    if ingested_count % 10 == 0:  # Log progress every 10 records
                        trace.append({
                            "step": f"Processed {ingested_count} records...",
                            "timestamp": datetime.now().replace(microsecond=0)
                        })
                except Exception as e:
                    errors.append(f"Row {index}: {str(e)}")
            
            db.commit()
            trace.append({
                "step": f"Database commit successful. Ingested {ingested_count} records.",
                "timestamp": datetime.now().replace(microsecond=0)
            })
            
            if errors:
                trace.append({
                    "step": f"Completed with {len(errors)} errors.",
                    "timestamp": datetime.now().replace(microsecond=0)
                })
            
            return {
                "ingested_rows": ingested_count,
                "skipped_rows": skipped_count,
                "errors": errors,
                "status": "success",
                "trace": trace
            }

        except Exception as e:
            trace.append({
                "step": f"Critical error: {str(e)}",
                "timestamp": datetime.now().replace(microsecond=0)
            })
            return {
                "ingested_rows": 0,
                "errors": [str(e)],
                "status": "failed",
                "trace": trace
            }

