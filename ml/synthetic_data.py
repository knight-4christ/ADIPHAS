import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

def generate_idsr_data(num_weeks=52):
    lgas = [f"NGA-LGA-{i:03d}" for i in range(1, 21)]
    diseases = ["Cholera", "Lassa Fever", "Measles", "Meningitis"]
    
    data = []
    start_date = datetime(2024, 1, 1)
    
    for week in range(num_weeks):
        week_start = start_date + timedelta(weeks=week)
        for lga in lgas:
            for disease in diseases:
                # Simulate outbreak
                is_outbreak = random.random() < 0.05
                cases = np.random.poisson(50 if is_outbreak else 2)
                deaths = int(cases * 0.1) if cases > 0 else 0
                
                data.append({
                    "facility_id": f"FAC-{random.randint(1, 100):03d}",
                    "lga_code": lga,
                    "state_code": "NGA-STATE-01",
                    "disease": disease,
                    "week_start": week_start.strftime("%Y-%m-%d"),
                    "cases": cases,
                    "deaths": deaths,
                    "reporting_week": week + 1,
                    "reporters_notes": "Outbreak suspected" if is_outbreak else ""
                })
    
    df = pd.DataFrame(data)
    df.to_csv("idsr_synthetic.csv", index=False)
    print(f"Generated {len(df)} rows of IDSR data in idsr_synthetic.csv")

if __name__ == "__main__":
    generate_idsr_data()
