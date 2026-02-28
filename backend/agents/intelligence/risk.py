from datetime import datetime
from collections import Counter

class RiskEngine:
    """
    Engine responsible for computing personal health risk scores.
    """
    def __init__(self, gemini_model=None):
        self.gemini_model = gemini_model
    
    def generate_risk_summary(self, score, category, user_traits, active_alerts):
        """Uses Gemini to provide a tailored situational risk summary."""
        if not self.gemini_model: return None
        
        traits_str = f"Genotype: {user_traits.get('genotype')}, Blood Group: {user_traits.get('blood_group')}"
        alert_str = ", ".join([f"{a.disease} in {a.location_text}" for a in active_alerts[:3]])
        
        prompt = f"""
        Act as a Professional Personal Health Security Advisor in Nigeria.
        Situation: Health risk score is {score:.1f} ({category}).
        User Traits: {traits_str}.
        LGA Alert Context: {alert_str}.
        
        Provide a 1-sentence "Preventative Action" explaining their biological vulnerability 
        (if relevant to traits) and the single most critical precautionary step to take today.
        """
        try:
            response = self.gemini_model.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except:
            return "AI situational summary currently unavailable."

    def interpret_risk_score(self, score, user_traits=None, active_alerts=None):
        """
        Interpret risk score using a hybrid (Thresholds + AI) approach.
        """
        trace = []
        trace.append({"step": f"Interpreting final risk score: {score:.2f}", "timestamp": datetime.now().isoformat()})
        
        # 1. CORE SKELETON (Thresholds)
        if score < 30: category = "Low"
        elif score < 50: category = "Moderate"
        elif score < 75: category = "High"
        else: category = "Critical"
        
        trace.append({"step": f"Risk category: {category}", "timestamp": datetime.now().isoformat()})
        
        result = {"category": category, "trace": trace}

        # 2. AI AUGMENTATION (Situational Summary)
        if self.gemini_model and user_traits and active_alerts:
            summary = self.generate_risk_summary(score, category, user_traits, active_alerts)
            if summary:
                result["ai_situational_summary"] = summary
                trace.append({"step": "AI Situational Risk Summary generated.", "timestamp": datetime.now().isoformat()})
        
        return result

    def identify_trending_diseases(self, active_alerts):
        """
        Identify diseases with multiple alerts in the last 14 days.
        """
        if not active_alerts:
            return []
            
        disease_counts = Counter()
        for alert in active_alerts:
            # In a real app, we would check alert.created_at
            # For this MVP, we consider all active alerts
            if alert.disease:
                disease_counts[alert.disease] += 1
        
        # A disease is 'trending' if it has 3+ alerts (threshold for this MVP)
        trending = [disease for disease, count in disease_counts.items() if count >= 2]
        return trending

    def compute_environmental_risk_enhanced(self, user_lga, active_alerts):
        """
        Adjust risk based on proximity AND disease priority/trends.
        """
        trace = []
        trace.append({
            "step": f"Assessing enhanced environmental risk for {user_lga}...",
            "timestamp": datetime.now().replace(microsecond=0)
        })
        
        env_penalty = 0.0
        relevant_alerts = [a for a in active_alerts if user_lga.lower() in (a.location_text or "").lower()]
        
        trending_diseases = self.identify_trending_diseases(active_alerts)
        if trending_diseases:
            trace.append({"step": f"Identified Trending Diseases in Lagos: {', '.join(trending_diseases)}", "timestamp": datetime.now().isoformat()})

        # Priority diseases
        priority_diseases = ["Cholera", "Measles", "Lassa Fever", "Malaria"]

        for alert in relevant_alerts:
            # Use a slightly more descriptive variable for readability
            risk_magnitude = 20.0 if alert.risk_level == "High" else (10.0 if alert.risk_level == "Medium" else 5.0)
            base_p = risk_magnitude
            
            # Critical Disease Bonus
            if alert.disease in priority_diseases:
                base_p += 15.0
                trace.append({"step": f"Priority Disease Penalty applied for {alert.disease}: +15.0", "timestamp": datetime.now().isoformat()})
            elif alert.disease in trending_diseases:
                base_p += 10.0
                trace.append({"step": f"Trending Disease Penalty applied for {alert.disease}: +10.0", "timestamp": datetime.now().isoformat()})
            
            env_penalty += base_p

        # Clamp penalty
        env_penalty = min(env_penalty, 60.0)
        return env_penalty, trace

    def get_personalized_advisory(self, genotype, blood_group, detected_disease=None):
        """
        Generate specific advice based on user's biological traits.
        """
        advisories = []
        
        # Genotype Advisory
        if genotype in ["SS", "SC"]:
            advisories.append("[Genotype SS/SC] You are at higher risk for severe Malaria complications. Ensure you sleep under a treated net.")
        elif genotype == "AS":
            advisories.append("[Genotype AS] Your genotype provides some disease protection, but take standard precautions.")

        # Blood Group Advisory
        if blood_group in ["O+", "O-"]:
            advisories.append("[Blood Group O] Some studies suggest higher severity in Cholera infections for this group. Ensure water is boiled.")

        # Disease-Specific Deep Dives
        if detected_disease == "Cholera":
            advisories.append("[CHOLERA ADVISORY] Drink only treated water. Use ORS if diarrheic. Wash hands frequently.")
        elif detected_disease == "Measles":
            advisories.append("[MEASLES ADVISORY] Isolate to prevent spread. Ensure Vitamin A supplementation. Monitor fever.")
        elif detected_disease == "Lassa Fever":
            advisories.append("[LASSA FEVER ADVISORY] Keep food in rodent-proof containers. Seek care for bleeding/fever.")
        elif detected_disease == "Malaria":
            advisories.append("[MALARIA ADVISORY] Consult a doctor for testing (RDT/Microscopy). If positive, complete full ACT course. Sleep under a net.")

        # Emergency Socials & Verification Channels
        advisories.append("OFFICIAL CHANNELS:")
        advisories.append("- NCDC: Call 6232 (Toll-Free) or WhatsApp +234 708 711 0839")
        advisories.append("- Twitter: @NCDCgov, @Fmohnigeria, @LSMOH, @NphcdaNG, @nhia_ng")
        advisories.append("- NAFDAC: @NafdacAgency for food/drug safety.")
        
        return advisories
