import logging
import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import time

logger = logging.getLogger(__name__)

try:
    import spacy  # type: ignore[import-untyped]
except Exception as e:
    spacy = None
    logger.warning(f"spaCy library not found or failed to load (DLL error): {e}. NLP will run in keyword-only mode.")

class NLPProcessor:
    def __init__(self, gemini_model=None):
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

        # Gemini Integration — uses the shared client from main.py
        self.gemini_enabled = gemini_model is not None
        self.gemini_model = gemini_model
        self._circuit_open_until = 0
        if self.gemini_enabled:
            logger.info("NLP Processor: Gemini AI augmentation enabled (shared client).")

    def analyze_with_gemini(self, text, baseline_entities):
        """Perform deep medical/epidemiological reasoning using AI, anchored by rule-based extraction."""
        if not self.gemini_enabled: return None
        if time.time() < self._circuit_open_until:
            return None
        
        prompt = f"""Extract health entities from: "{text}"
Baseline: diseases={baseline_entities.get('diseases')}, locations={baseline_entities.get('locations')}, severity={baseline_entities.get('severity_score')}
Refine baseline. Return JSON: {{"diseases":[], "locations":[], "severity_score":0.0-1.0, "intelligence_summary":"", "public_health_advisory":"", "category":"Infectious/Environmental/Other", "policy_alert":bool}}"""
        # 3. Execution via Gemini
        try:
            from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
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
            
        prompt = f"""Extract health entities from {len(payload)} reports. Refine baselines.
Data: {json.dumps(payload)}
Return JSON array: [{{"id":int, "diseases":[], "locations":[], "severity_score":0.0-1.0, "intelligence_summary":"", "public_health_advisory":"", "category":"Infectious/Environmental/Other", "policy_alert":bool}}]"""
        try:
            from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
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
        
        entities: Dict[str, Any] = {
            "diseases": [],
            "locations": [],
            "severity_score": 0.1
        }

        # 1. spaCy NER
        if self.nlp:
            doc = self.nlp(text)  # type: ignore[misc]
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

        entities["severity_score"] = min(1.0, float(entities["severity_score"]))
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
            
            time.sleep(0.005) # Yield GIL
            
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
                        # Merge Gemini intelligence into the result if available
                        results[idx].update({
                            "diseases": [str(d) for d in g_res.get("diseases", []) if str(d).strip()],
                            "locations": [str(l) for l in g_res.get("locations", []) if str(l).strip()],
                            "severity_score": float(g_res.get("severity_score", results[idx].get("severity_score"))),
                            "ai_summary": g_res.get("intelligence_summary") or f"Automatically detected {results[idx].get('diseases')} signal in {results[idx].get('locations')}.",
                            "public_health_advisory": g_res.get("public_health_advisory") or "Standard health protocol advised. Monitoring for further updates.",
                            "category": g_res.get("category", "General Intelligence"),
                            "policy_alert": g_res.get("policy_alert", False)
                        })
                        results[idx]["ai_powered"] = True
                        traces[idx].append({"step": "Gemini deep batch analysis applied."})
            
            # Post-Gemini cleanup: Ensure even skipped/failed alerts have a basic summary for the vector store
            for res in results:
                if not res.get("ai_summary"):
                    res["ai_summary"] = f"Baseline detection: {res.get('diseases')} in {res.get('locations')}."
                    res["ai_powered"] = False
                        
        # 3. Zip back together
        return list(zip(results, traces))
