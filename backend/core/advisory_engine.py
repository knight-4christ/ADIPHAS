from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

class AdvisoryEngine:
    """
    Core logic for health interaction and alert generation.
    Incorporates a hybrid approach: Rule-based baseline + Gemini-powered deep reasoning.
    """

    def __init__(self, gemini_model=None):
        # Specific Keyword Dictionaries
        self.DISEASE_SIGNATURES: Dict[str, Dict[str, Any]] = {
            "Lassa Fever": {"keywords": ["fever", "bleeding", "rat", "mastomys", "headache"], "threshold": 2, "critical": ["bleeding"]},
            "Cholera": {"keywords": ["diarrhea", "vomiting", "rice-water", "dehydration"], "threshold": 2, "critical": ["rice-water"]},
            "Malaria": {"keywords": ["fever", "chills", "sweating", "headache"], "threshold": 2, "critical": []}
        }
        self.gemini_model = gemini_model

    def chat_with_ai(self, messages: list, user_metadata: dict = None, enable_reasoning: bool = False, context: str = "") -> str:
        """
        Conversational entry point for the Advisory Chat.
        Injects user biodata and real-time search context.
        """
        bio_block = ""
        if user_metadata:
            bio_block = f"\n\n[USER PROFILE & LOCATION]\n- Location: {user_metadata.get('location', 'Unknown')}\n- Genotype: {user_metadata.get('genotype', 'N/A')}\n- Blood Group: {user_metadata.get('blood_group', 'N/A')}\n- Known Conditions: {user_metadata.get('health_conditions', 'None')}\n"

        context_block = f"\n\n[REAL-TIME INTELLIGENCE CONTEXT]\n{context}" if context else ""

        # Construct a conversational prompt from history
        history_str = ""
        for msg in messages:
            role = "Assistant" if msg.get("role") == "assistant" else "User"
            history_str += f"{role}: {msg.get('content')}\n"

        full_prompt = f"""
        Act as the ADIPHAS Health Advisory Agent. 
        Context: You are helping a resident of Lagos, Nigeria named {user_metadata.get('name', 'User') if user_metadata else 'User'}.
        Address them by their name directly.
        {bio_block}
        {context_block}
        
        Recent Conversation:
        {history_str}
        
        Provide the next response following the guidelines of NCDC and WHO. 
        Be professional, comprehensive, detailed, and simple to understand.
        CRITICAL RULE: DO NOT use markdown tables. Provide output as text and bullet points only.
        """
        try:
            from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
            reply, model_used = smart_generate(
                self.gemini_model, 
                full_prompt, 
                enable_reasoning=enable_reasoning
            )
            return reply or "AI chat currently unavailable."
        except Exception:
            return "AI chat currently unavailable."

    def analyze_with_ai(self, symptoms: list, duration_days: int, context_str: str = "", user_metadata: dict = None) -> Optional[str]:
        """
        Uses Gemini to provide a deep clinical analysis of symptoms.
        Optionally enriched with RAG context and User Biodata (Genotype/Blood Group).
        """
        if not self.gemini_model:
            return None

        context_block = f"\n\nVerified Intelligence Context:\n{context_str}" if context_str else ""
        
        bio_block = ""
        if user_metadata:
            bio_block = f"\n\nUser Profile & Location:\n- Location: {user_metadata.get('location', 'Unknown')}\n- Genotype: {user_metadata.get('genotype', 'N/A')}\n- Blood Group: {user_metadata.get('blood_group', 'N/A')}\n- Known Conditions: {user_metadata.get('health_conditions', 'None')}"
            
        prompt = f"""
        Act as a Senior Clinical Epidemiologist and Medical Consultant in Nigeria.
        Condition: Patient reports {', '.join(symptoms)} over {duration_days} days.
        Patient Name: {user_metadata.get('name', 'User') if user_metadata else 'User'}
        {bio_block}
        {context_block}
        
        Provide a highly professional, comprehensive, detailed yet simple-to-understand actionable advisory tailored to {user_metadata.get('name', 'the user') if user_metadata else 'them'}. 
        Focus on: 
        1. Specific Clinical Protocol.
        2. Public Health Action.
        
        IMPORTANT: Use their Biological Profile to tailor the advice. 
        CRITICAL RULE: DO NOT use markdown tables under any circumstances. Use bullet points and paragraphs.
        """
        try:
            from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
            text, model_used = smart_generate(self.gemini_model, prompt, context="SymptomCheck")
            return text or "AI clinical deep-dive currently unavailable."
        except Exception:
            return "AI clinical deep-dive currently unavailable."

    def analyze_symptoms(self, symptoms: list, duration_days: int, user_metadata: dict = None) -> dict:
        """
        Analyzes user input symptoms using a hybrid (Rule + AI) approach.
        """
        trace = []
        trace.append({"step": "Initializing hybrid symptom analysis...", "timestamp": datetime.now().replace(microsecond=0)})
        
        symptoms_lower = [s.lower() for s in symptoms]
        
        # 1. CORE SKELETON (Rule-Based Guardrails)
        detected_risks: List[Dict[str, str]] = []
        result: Dict[str, Any] = {}
        
        # Specific High-Priority Check (Lassa)
        if "fever" in symptoms_lower and "bleeding" in symptoms_lower:
            trace.append({"step": "CRITICAL: Fever + Bleeding pattern detected (Lassa Signature).", "timestamp": datetime.now().replace(microsecond=0)})
            result = {
                "risk_level": "CRITICAL",
                "disease": "Lassa Fever",
                "message": "CRITICAL: Potential Lassa Fever detected (Fever + Bleeding). Immediate isolation required.",
                "action": "Go to the nearest isolation center immediately."
            }
        else:
            # General Signature Matching
            for disease, sig in self.DISEASE_SIGNATURES.items():
                keywords: List[str] = sig["keywords"]
                critical_list: List[str] = sig["critical"]
                threshold: int = sig["threshold"]
                match_count = sum(1 for k in keywords if any(k in s for s in symptoms_lower))
                critical_hit = any(c in symptoms_lower for c in critical_list)
                
                if critical_hit or match_count >= threshold:
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
            ai_insight = self.analyze_with_ai(symptoms, duration_days, user_metadata=user_metadata)
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
            except Exception:
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

    def generate_dashboard_insight(self, user_metadata: dict, alerts_summary: str = "") -> str:
        """
        Generates a quick, personalized 2-sentence situational awareness insight for the dashboard.
        """
        if not self.gemini_model:
            return "AI summary engine offline."
            
        location = user_metadata.get('location', 'Unknown')
        
        bio_block = f"Genotype: {user_metadata.get('genotype', 'N/A')}, Blood Group: {user_metadata.get('blood_group', 'N/A')}, Conditions: {user_metadata.get('health_conditions', 'None')}"
        
        user_name = user_metadata.get('name', 'User')
        prompt = f"""
        Act as the ADIPHAS public health command center AI. 
        User Name: {user_name}
        User Location: {location}
        User Biodata: {bio_block}
        Recent Local Alerts context: {alerts_summary}
        
        Provide a highly personalized, comprehensive, detailed and professional situational briefing tailored specifically to {user_name}'s location ({location}) and biological profile. Address {user_name} directly.
        CRITICAL RULE: DO NOT use tables. Output simple, easy-to-read prose. Keep it under 3-4 sentences total so it fits on a dashboard.
        """
        try:
            from backend.core.model_config import smart_generate # type: ignore[import-untyped]
            reply, _ = smart_generate(self.gemini_model, prompt, enable_reasoning=False)
            return reply or "Stay safe and monitor local health feeds."
        except Exception as e:
            return f"Stay safe and monitor local health feeds. (Error: {str(e)})"
