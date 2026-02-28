import pandas as pd, os

def load_outbreaks_for_region():
    # Load simulated outbreaks from CSV shipped with demo.
    path = os.path.join(os.path.dirname(__file__), "simulated_outbreaks.csv")
    if not os.path.exists(path):
        # create default
        df = pd.DataFrame([
            {"disease":"Cholera","affected_states":"Lagos;Oyo","summary":"Cluster of acute watery diarrhoea reported in coastal communities.","severity":"High","education_snippet":"Use treated water, boil drinking water, avoid street food."},
            {"disease":"Heatwave Hypertension Risk","affected_states":"Lagos;Kano","summary":"Sustained high temperatures increasing dehydration and BP for vulnerable people.","severity":"Moderate","education_snippet":"Stay hydrated, avoid long sun exposure, monitor blood pressure closely."},
            {"disease":"Influenza","affected_states":"FCT;Rivers","summary":"Seasonal influenza activity increasing.","severity":"Low","education_snippet":"Practice hand hygiene and get vaccinated if eligible."},
        ])
        df.to_csv(path, index=False)
    else:
        df = pd.read_csv(path)
    # normalize affected_states to semicolon-separated strings
    df["affected_states"] = df["affected_states"].astype(str)
    return df
