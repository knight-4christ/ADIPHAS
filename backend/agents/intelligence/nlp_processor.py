import logging
import re
import json
from datetime import datetime
import os
import time
from google import genai

logger = logging.getLogger(__name__)

try:
    import spacy
except Exception as e:
    spacy = None
    logger.warning(f"spaCy library not found or failed to load (DLL error): {e}. NLP will run in keyword-only mode.")

class NLPProcessor:
    def __init__(self, gemini_api_key=None):
        self.nlp = None
        if spacy:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("Loaded spaCy model 'en_core_web_sm'")
            except OSError:
                logger.warning("spaCy model 'en_core_web_sm' not found. Using keyword fallback.")

        # Nigerian Disease Registry (Consolidated)
        self.diseases = [
            "Cholera", "Malaria", "Typhoid", "Lassa Fever", "Measles", "Yellow Fever", 
            "Meningitis", "Monkeypox", "Dengue", "COVID-19", "Ebola", "Anthrax", "Rabies"
        ]
        
        # 20 LGAs & 37 LCDAs (Consolidated Lagos Spatial Registry)
        self.lgas = [
            "Agege", "Ajeromi-Ifelodun", "Alimosho", "Amuwo-Odofin", "Apapa", "Badagry",
            "Epe", "Eti-Osa", "Ibeju-Lekki", "Ifako-Ijaiye", "Ikeja", "Ikorodu",
            "Kosofe", "Lagos Island", "Lagos Mainland", "Mushin", "Ojo", "Oshodi-Isolo",
            "Shomolu", "Surulere",
            "Agbado/Oke-Odo", "Agboyi-Ketu", "Ayobo-Ipaja", "Bariga", "Eredo", "Egbe-Idimu", 
            "Ejigbo", "Igando-Ikotun", "Ikosi-Isheri", "Isolo", "Mosan-Okunola", 
            "Odi Olowo-Ojuwoye", "Ojodu", "Ojokoro", "Onigbongbo", "Orile Agege", 
            "Iru-Victoria Island", "Ikoyi-Obalende", "Eti-Osa East", "Lagos Island East", 
            "Yaba", "Itire-Ikate", "Coker-Aguda", "Apapa-Iganmu", "Ifelodun", "Oriade", 
            "Badagry West", "Olorunda", "Iba", "Oto-Awori", "Ijede", "Ikorodu North", 
            "Ikorodu West", "Imota", "Igbogbo-Bayeku", "Lekki", "Ikosi-Ejinrin"
        ]

        # Gemini Integration
        self.gemini_enabled = False
        self.gemini_model = None
        self._circuit_open_until = 0
        if gemini_api_key:
            try:
                self.gemini_model = genai.Client(api_key=gemini_api_key)
                self.gemini_enabled = True
                logger.info("Gemini 2.5 Flash initialized for Deep Analysis.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")

    def analyze_with_gemini(self, text, baseline_entities):
        """Perform deep medical/epidemiological reasoning using AI, anchored by rule-based extraction."""
        if not self.gemini_enabled: return None
        if time.time() < self._circuit_open_until:
            return None
        
        prompt = f"""
        Act as a Public Health Intelligence Agent for Lagos State, Nigeria.
        Analyze this report: "{text}"
        
        Our underlying mathematical/rule-based system detected the following baseline entities:
        - Diseases: {baseline_entities.get('diseases')}
        - Locations: {baseline_entities.get('locations')}
        - Base Severity Score: {baseline_entities.get('severity_score')}

        Your task is to orchestrate the final extraction. You must SERIOUSLY CONSIDER the baseline entities above, but you can refine them (e.g., correcting false positives or adding missed context).
        
        Extract and return valid JSON exact structure:
        {{
            "diseases": ["list of detected diseases"],
            "locations": ["list of specific LGAs or LCDAs"],
            "severity_score": 0.0 to 1.0 (float, you can adjust the base score if context warrants it),
            "intelligence_summary": "1-sentence technical summary",
            "public_health_advisory": "Actionable advice for citizens",
            "category": "Infectious, Environmental, or Other",
            "policy_alert": true or false
        }}
        """
        # 3. Execution via Gemini
        try:
            from backend.core.model_config import smart_generate
            raw_text, model_used = smart_generate(self.gemini_model, prompt, context="NLP_EntityExtraction")
            
            if not raw_text:
                return {"diseases": [], "locations": [], "severity_score": 0.0}
                
            clean_json = re.sub(r'```json\s*|\s*```', '', raw_text).strip()
            return json.loads(clean_json)
            
        except Exception as e:
            logger.error(f"[NLP] Parsing error or all models failed: {e}")
            return {"diseases": [], "locations": [], "severity_score": 0.0}

    def analyze_batch_with_gemini(self, articles_batch):
        """Perform deep medical reasoning on a bulk array of articles simultaneously."""
        if not self.gemini_enabled: return None
        if time.time() < self._circuit_open_until: return None
        if not articles_batch: return []
        
        # Prepare the bulk payload for the prompt
        payload = []
        for i, article in enumerate(articles_batch):
            payload.append({
                "id": i,
                "text": article['text'],
                "baseline": article['baseline']
            })
            
        prompt = f"""
        Act as a Public Health Intelligence Agent for Lagos State, Nigeria.
        Analyze this BATCH of {len(payload)} reports.
        
        Batch Data: {json.dumps(payload, indent=2)}
        
        For each item in the batch, orchestrate the final extraction. Consider the baseline entities strongly, but refine them.
        Extract and return a valid JSON ARRAY of objects exact structure:
        [
          {{
              "id": (match the id from the input),
              "diseases": ["list of detected diseases"],
              "locations": ["list of specific LGAs or LCDAs"],
              "severity_score": 0.0 to 1.0,
              "intelligence_summary": "1-sentence technical summary",
              "public_health_advisory": "Actionable advice for citizens",
              "category": "Infectious, Environmental, or Other",
              "policy_alert": true or false
          }}
        ]
        """
        try:
            from backend.core.model_config import smart_generate
            raw_text, model_used = smart_generate(self.gemini_model, prompt, context="NLP_BatchExtraction")
            
            if not raw_text: return None
                
            clean_json = re.sub(r'```json\s*|\s*```', '', raw_text).strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"[NLP_BATCH] Parsing error: {e}")
            return None

    def extract_entities(self, text):
        """Hybrid extraction: NER + Rule-based + Case-Insensitive Matching."""
        text = str(text)
        trace = []
        trace.append({"step": "Initializing NLP Extraction...", "timestamp": datetime.now().replace(microsecond=0)})
        
        entities = {
            "diseases": [],
            "locations": [],
            "severity_score": 0.1
        }

        # 1. spaCy NER
        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ in ["GPE", "LOC"]:
                    # Case-insensitive check against Lagos Registry
                    found_lga = next((l for l in self.lgas if l.lower() == ent.text.lower()), None)
                    if found_lga:
                        entities["locations"].append(found_lga)
                        trace.append({"step": f"Found Location (NER): {found_lga}"})

        # 2. Case-Insensitive Keyword Matching (Safety Net)
        for disease in self.diseases:
            if re.search(r'\b' + re.escape(disease) + r'\b', text, re.IGNORECASE):
                if disease not in entities["diseases"]:
                    entities["diseases"].append(disease)
                    trace.append({"step": f"Detected Disease: {disease}"})
                    entities["severity_score"] += 0.2

        for lga in self.lgas:
            # Avoid redundant matches if NER already found it
            if any(l.lower() == lga.lower() for l in entities["locations"]):
                continue
            if re.search(r'\b' + re.escape(lga) + r'\b', text, re.IGNORECASE):
                entities["locations"].append(lga)
                trace.append({"step": f"Detected Location: {lga}"})

        # 3. Urgency Detection
        urgent_keywords = ["Outbreak", "Epidemic", "Dozens", "Fatalities", "Killed", "Crisis", "Emergency"]
        if any(re.search(r'\b' + re.escape(k) + r'\b', text, re.IGNORECASE) for k in urgent_keywords):
            entities["severity_score"] += 0.4
            trace.append({"step": "Urgency signals detected."})

        entities["severity_score"] = min(1.0, entities["severity_score"])
        trace.append({"step": "Baseline math/rule extraction complete.", "timestamp": datetime.now().replace(microsecond=0)})
        
        trace.append({"step": "Extraction cycle complete.", "timestamp": datetime.now().replace(microsecond=0)})
        return entities, trace

    def extract_entities_batch(self, headlines):
        """
        Process an array of headlines at once.
        Returns a list of tuples: (entities_dict, trace_list) corresponding to the input list.
        """
        results = []
        gemini_payload = []
        traces = []
        
        # 1. Run local baselines mathematically (CPU bound, but fast)
        for i, item in enumerate(headlines):
            text = str(item.get('title', item.get('text', '')))
            
            import time as base_time
            base_time.sleep(0.005) # Yield GIL
            
            base_entities, trace = self.extract_entities(text)
            traces.append(trace)
            results.append(base_entities) # Will overwrite with Gemini later if successful
            
            if self.gemini_enabled:
                gemini_payload.append({
                    "id": i,
                    "text": text,
                    "baseline": base_entities
                })
                
        # 2. Bulk process via Gemini
        if self.gemini_enabled and gemini_payload:
            gemini_results = self.analyze_batch_with_gemini(gemini_payload)
            if isinstance(gemini_results, list):
                # Map back to original indices
                for g_res in gemini_results:
                    idx = g_res.get('id')
                    if idx is not None and 0 <= idx < len(results):
                        # Merge Gemini intelligence into the result
                        results[idx].update({
                            "diseases": [str(d) for d in g_res.get("diseases", []) if str(d).strip()],
                            "locations": [str(l) for l in g_res.get("locations", []) if str(l).strip()],
                            "severity_score": float(g_res.get("severity_score", results[idx].get("severity_score"))),
                            "ai_summary": g_res.get("intelligence_summary"),
                            "public_health_advisory": g_res.get("public_health_advisory"),
                            "category": g_res.get("category", "General"),
                            "policy_alert": g_res.get("policy_alert", False)
                        })
                        traces[idx].append({"step": "Gemini deep batch analysis applied."})
                        
        # 3. Zip back together
        return list(zip(results, traces))
