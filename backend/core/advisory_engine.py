from datetime import datetime, timedelta

class AdvisoryEngine:
    """
    Core logic for health interaction and alert generation.
    Incorporates a hybrid approach: Rule-based baseline + Gemini-powered deep reasoning.
    """

    def __init__(self, gemini_model=None):
        # Specific Keyword Dictionaries
        self.DISEASE_SIGNATURES = {
            "Lassa Fever": {"keywords": ["fever", "bleeding", "rat", "mastomys", "headache"], "threshold": 2, "critical": ["bleeding"]},
            "Cholera": {"keywords": ["diarrhea", "vomiting", "rice-water", "dehydration"], "threshold": 2, "critical": ["rice-water"]},
            "Malaria": {"keywords": ["fever", "chills", "sweating", "headache"], "threshold": 2, "critical": []}
        }
        self.gemini_model = gemini_model

    def analyze_with_ai(self, symptoms: list, duration_days: int) -> str:
        """
        Uses Gemini to provide a deep clinical analysis of symptoms.
        """
        if not self.gemini_model:
            return None
            
        prompt = f"""
        Act as a Senior Clinical Epidemiologist and Medical Consultant in Nigeria.
        Condition: Patient reports {', '.join(symptoms)} over {duration_days} days.
        
        Provide a concise (2 sentence) actionable advisory. 
        Focus on: 
        1. Specific Clinical Protocol (e.g., "Initiate ORS and isolate", "Perform RDT for Malaria").
        2. Public Health Action (e.g., "Report to LGA surveillance officer if symptoms persist").
        """
        try:
            response = self.gemini_model.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except:
            return "AI clinical deep-dive currently unavailable."

    def analyze_symptoms(self, symptoms: list, duration_days: int) -> dict:
        """
        Analyzes user input symptoms using a hybrid (Rule + AI) approach.
        """
        trace = []
        trace.append({"step": "Initializing hybrid symptom analysis...", "timestamp": datetime.now().replace(microsecond=0)})
        
        symptoms_lower = [s.lower() for s in symptoms]
        
        # 1. CORE SKELETON (Rule-Based Guardrails)
        detected_risks = []
        result = {}
        
        # Specific High-Priority Check (Lassa)
        if "fever" in symptoms_lower and "bleeding" in symptoms_lower:
            trace.append({"step": "CRITICAL: Fever + Bleeding pattern detected (Lassa Signature).", "timestamp": datetime.now().replace(microsecond=0)})
            result = {
                "risk_level": "CRITICAL",
                "disease": "Lassa Fever",
                "message": "CRITICAL: Potential Lassa Fever detected (Fever + Bleeding). Immedate isolation required.",
                "action": "Go to the nearest isolation center immediately."
            }
        else:
            # General Signature Matching
            for disease, sig in self.DISEASE_SIGNATURES.items():
                match_count = sum(1 for k in sig["keywords"] if any(k in s for s in symptoms_lower))
                critical_hit = any(c in symptoms_lower for c in sig["critical"])
                
                if critical_hit or match_count >= sig["threshold"]:
                    risk = "High" if critical_hit else "Moderate"
                    detected_risks.append({"disease": disease, "risk": risk})
                    trace.append({"step": f"Matched {disease} pattern ({match_count} keywords).", "timestamp": datetime.now().replace(microsecond=0)})

            if detected_risks:
                top_risk = sorted(detected_risks, key=lambda x: 1 if x["risk"]=="High" else 0, reverse=True)[0]
                result = {
                    "risk_level": top_risk["risk"],
                    "disease": top_risk["disease"],
                    "message": f"Symptoms suggest possible {top_risk['disease']}.",
                    "action": "Consult a clinician for testing."
                }
            else:
                result = {
                    "risk_level": "Low",
                    "disease": "Unspecified",
                    "message": "No specific outbreak pattern detected. Monitor symptoms.",
                    "action": "Stay hydrated and rest."
                }
        
        # 2. AI AUGMENTATION (The "Heavy Lifting")
        if self.gemini_model:
            ai_insight = self.analyze_with_ai(symptoms, duration_days)
            if ai_insight:
                result["ai_clinical_insight"] = ai_insight
                trace.append({"step": "AI Clinical deep-dive generated.", "timestamp": datetime.now().replace(microsecond=0)})
        
        result["trace"] = trace
        return result

    def analyze_wellness(self, systolic: int, diastolic: int) -> dict:
        """
        Interprets blood-pressure readings and returns a categorised wellness advisory.
        BP categories follow standard NCDC/WHO thresholds.
        """
        if systolic >= 180 or diastolic >= 120:
            category = "Hypertensive Crisis"
            advice = "EMERGENCY: Seek immediate medical care. Call NCDC on 6232 or go to the nearest emergency unit."
        elif systolic >= 140 or diastolic >= 90:
            category = "High Blood Pressure - Stage 2"
            advice = "Consult a doctor urgently. Reduce sodium intake, avoid stress, and take prescribed medication."
        elif systolic >= 130 or diastolic >= 80:
            category = "High Blood Pressure - Stage 1"
            advice = "Monitor daily. Adopt a low-salt diet, exercise regularly, and consult a physician if persistent."
        elif systolic >= 120 and diastolic < 80:
            category = "Elevated Blood Pressure"
            advice = "Your reading is above ideal. Adopt a healthier lifestyle to prevent progression to hypertension."
        else:
            category = "Normal"
            advice = "Your blood pressure is within a healthy range. Maintain a balanced diet and active lifestyle."

        return {
            "systolic": systolic,
            "diastolic": diastolic,
            "category": category,
            "advice": advice
        }

    def check_community_risk(self, lga_signals: list) -> dict:
        """
        Local Alert Logic.
        Rule: If 3 signals of the same disease in LGA within 72h -> Community Watch.
        """
        now = datetime.now()
        seventy_two_hours_ago = now - timedelta(hours=72)
        
        # Filter recent signals
        recent_signals = []
        for s in lga_signals:
            try:
                ts = datetime.fromisoformat(s['timestamp'])
                if ts > seventy_two_hours_ago:
                    recent_signals.append(s)
            except:
                continue
        
        disease_counts = {}
        for s in recent_signals:
            d = s.get('disease')
            if d:
                disease_counts[d] = disease_counts.get(d, 0) + 1
        
        # Check threshold
        alerts = []
        for disease, count in disease_counts.items():
            if count >= 3:
                alerts.append(f"Community Watch: {disease} ({count} reports in 72h)")
                
        if alerts:
            return {"alert_level": "HIGH", "alerts": alerts}
        
        return {"alert_level": "NORMAL", "alerts": []}
