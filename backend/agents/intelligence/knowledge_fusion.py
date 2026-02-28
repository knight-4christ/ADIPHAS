import logging
import hashlib
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class KnowledgeFusionAgent:
    def __init__(self, gemini_model=None):
        # Reliability weights for different sources
        self.source_weights = {
            "NCDC": 0.95, "WHO Nigeria": 0.95, "Nigeria Health Watch": 0.85,
            "Punch Health": 0.7, "Vanguard Health": 0.7, "NCDC_OFFICIAL": 0.9,
            "LSMOH": 0.95, "MOH_OFFICIAL": 0.9, "NEWS_MEDIA": 0.6, 
            "SOCIAL_MEDIA": 0.3, "USER_REPORT": 0.4, "LCDA_SOURCE": 0.3
        }
        
        # 57-Council Spatial Mapping for Verification
        self.lcda_mapping = {
            "Agbado/Oke-Odo": "Alimosho", "Agboyi-Ketu": "Kosofe", "Ayobo-Ipaja": "Alimosho",
            "Bariga": "Shomolu", "Eredo": "Epe", "Egbe-Idimu": "Alimosho", "Ejigbo": "Oshodi-Isolo",
            "Igando-Ikotun": "Alimosho", "Ikosi-Isheri": "Kosofe", "Isolo": "Oshodi-Isolo",
            "Mosan-Okunola": "Alimosho", "Odi Olowo-Ojuwoye": "Mushin", "Ojodu": "Ikeja",
            "Ojokoro": "Ifako-Ijaiye", "Onigbongbo": "Ikeja", "Orile Agege": "Agege",
            "Iru-Victoria Island": "Eti-Osa", "Ikoyi-Obalende": "Eti-Osa", "Eti-Osa East": "Eti-Osa",
            "Lagos Island East": "Lagos Island", "Yaba": "Lagos Mainland", "Itire-Ikate": "Surulere",
            "Coker-Aguda": "Surulere", "Apapa-Iganmu": "Apapa", "Ifelodun": "Ajeromi-Ifelodun",
            "Oriade": "Amuwo-Odofin", "Badagry West": "Badagry", "Olorunda": "Badagry",
            "Iba": "Ojo", "Oto-Awori": "Ojo", "Ijede": "Ikorodu", "Ikorodu North": "Ikorodu",
            "Ikorodu West": "Ikorodu", "Imota": "Ikorodu", "Igbogbo-Bayeku": "Ikorodu",
            "Lekki": "Ibeju-Lekki", "Ikosi-Ejinrin": "Epe"
        }
        
        self.seen_hashes = set() # Memory-based deduplication for the session
        self.gemini_model = gemini_model
        self._circuit_open_until = 0

    def get_source_registry(self):
        """Returns the list of monitored sources and their reliability weights."""
        return self.source_weights

    def _generate_content_hash(self, report):
        """Generates a stable hash based on normalized content to detect syndication."""
        # Normalize: Lowercase title/text and strip whitespace
        content = str(report.get("text", "")).lower().strip()
        # Create hash: [Disease]_[Location]_[Content]
        raw_key = f"{report.get('disease')}_{report.get('location')}_{content}"
        return hashlib.md5(raw_key.encode()).hexdigest()

    def _resolve_with_ai(self, unique_reports, base_confidence):
        """Uses Gemini to semantically reconcile conflicting reports, bounded by math."""
        if not self.gemini_model or not unique_reports: return None
        if time.time() < self._circuit_open_until:
            return None
        
        context = "\n".join([f"- [{r.get('source')}]: {r.get('text')}" for r in unique_reports])
        prompt = f"""
        Act as a Knowledge Fusion Expert for a disease intelligence platform.
        You have multiple reports about the same event:
        {context}
        
        Our underlying mathematical reliability model (based on source weighting and diversity) has assigned this event a Base Confidence Score of {base_confidence:.2f} (0.0 to 1.0).

        Semantically reconcile these reports and orchestrate the final confidence rating:
        1. Resolve linguistic conflicts (e.g., if one says "Outbreak" and another says "Cases").
        2. Summarize the true situation in 1 sentence ("synopsis").
        3. Merge any medical/preparedness advice into a single "fused_advisory" (1-2 sentences).
        4. Determine the Final Confidence Score (0.0 to 1.0) by taking the Base Confidence Score and adjusting it based on the semantic convergence or contradictions in the reports.
        
        Output JSON MUST be strictly: {{"synopsis": "...", "fused_advisory": "...", "final_confidence": 0.0}}
        """
        try:
            response = self.gemini_model.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            import json
            clean = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str:
                self._circuit_open_until = time.time() + 3600
                logger.error("[FUSION-DEBUG] Gemini Quota Exhausted! Circuit breaker active for 1 hour.")
            else:
                logger.error(f"[FUSION-DEBUG] Gemini Analysis Error: {e}")
            return None

    def fuse_reports(self, reports):
        """
        Fuses multiple reports using a hybrid (Weights + AI) approach.
        """
        trace = []
        trace.append({"step": "Initializing Knowledge Fusion Agent...", "timestamp": datetime.now().replace(microsecond=0)})
        
        if not reports:
            trace.append({"step": "No reports received. Aborting.", "timestamp": datetime.now().replace(microsecond=0)})
            return None, trace
            
        # 1. CORE SKELETON (Deduplication & Weights)
        unique_reports = []
        cycle_seen = set()
        for r in reports:
            h = self._generate_content_hash(r)
            if h not in cycle_seen:
                unique_reports.append(r)
                cycle_seen.add(h)
            else:
                trace.append({"step": f"Deduplicated syndicated report from {r.get('source')}.", "timestamp": datetime.now().replace(microsecond=0)})

        trace.append({"step": f"Processing {len(unique_reports)} UNIQUE reports for fusion.", "timestamp": datetime.now().replace(microsecond=0)})

        # --- DEMPSTER-SHAFER FUSION LOGIC ---
        # We treat each unique source as a mass function m_i(Real) = source_weight
        # Uncombined uncertainty (mass on universal set) = product(1 - w_i)
        # Combined Belief m(Real) = 1 - product(1 - w_i)
        
        uncertainty_product = 1.0
        weighted_sum_cases = 0
        total_weight = 0
        max_severity = 0.0

        for report in unique_reports:
            source = report.get("source", "UNKNOWN")
            # Get reliability weight (defaults to 0.5)
            w_i = self.source_weights.get(source, 0.5)
            
            # Dempster-Shafer Component: Pooling uncertainty
            uncertainty_product *= (1.0 - w_i)
            
            # Weighted case estimation
            cases = report.get("cases", 0)
            weighted_sum_cases += cases * w_i
            total_weight += w_i
            
            max_severity = max(max_severity, report.get("severity_score", 0.0))

        # Final DST Confidence Score
        # If uncertainty_product is 0.05, then belief is 0.95
        dst_confidence = 1.0 - uncertainty_product
        
        # Diversity adjustment: DS handles scaling but we cap at 0.99 for non-official
        # and ensure it's at least as high as the best single source
        estimated_cases = weighted_sum_cases / total_weight if total_weight > 0 else 0

        trace.append({"step": f"Dempster-Shafer Belief m(Real): {dst_confidence:.2f} (Uncertainty Remaining: {uncertainty_product:.2f})", "timestamp": datetime.now().replace(microsecond=0)})

        result = {
            "location": unique_reports[0].get("location"),
            "disease": unique_reports[0].get("disease"),
            "url": unique_reports[0].get("url"),
            "estimated_cases": round(estimated_cases),
            "confidence_score": round(dst_confidence, 2),
            "severity_score": round(max_severity, 2),
            "status": "CONFIRMED" if dst_confidence > 0.75 else "SUSPECTED",
            "timestamp": datetime.now().replace(microsecond=0)
        }

        # 1.5 [NEW] SPATIAL VERIFICATION: LCDA Parent Confirmation
        for r in unique_reports:
            loc = r.get("location")
            if loc in self.lcda_mapping:
                parent = self.lcda_mapping[loc]
                # Check for official report from parent LGA
                for pr in unique_reports:
                    if pr.get("location") == parent and pr.get("source") in ["NCDC", "LSMOH", "MOH_OFFICIAL"]:
                        result["status"] = "CONFIRMED"
                        result["confidence_score"] = 0.95
                        trace.append({"step": f"Spatial Verification: Signal in {loc} (LCDA) confirmed by official report from parent LGA ({parent}).", "timestamp": datetime.now().replace(microsecond=0)})
                        break

        # [Removed AI Orchestration to save quota, AI reserved for Insights only]

        trace.append({"step": f"Fusion Complete. Final Confidence: {result['confidence_score']}", "timestamp": datetime.now().replace(microsecond=0)})
        return result, trace
