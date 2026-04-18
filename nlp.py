"""
nlp.py — Semantic NLP engine using sentence-transformers + ChromaDB.
Replaces keyword-based detection in main.py with embedding-based detection.

Fallback: if sentence-transformers or chromadb are not installed, all
detection functions automatically revert to the keyword-based logic.

CLI usage:
  python nlp.py --build        → (re)build all reference embeddings from scratch
  python nlp.py --build --force → force-rebuild (deletes & recreates collections)
"""

import os
import re
import sys
import argparse
from typing import Optional

# ==============================================================================
# OPTIONAL IMPORTS — graceful fallback if packages not installed
# ==============================================================================

_EMBEDDINGS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401 (used via chromadb EF)
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    _EMBEDDINGS_AVAILABLE = True
except ImportError:
    pass

# ==============================================================================
# REFERENCE DATA — mirrors main.py keyword dictionaries
# Single source of truth: edit here, changes apply to both engines.
# ==============================================================================

EMOTION_KEYWORDS = {
    "Angry": {
        "critical": [
            "lawsuit", "legal action", "lawyer", "attorney", "sue", "court",
            "this is outrageous", "absolutely unacceptable", "complete disaster",
            "cancel everything", "never working with you again", "i demand compensation",
            "i will escalate", "speak to your manager", "your company is a joke",
            "procès", "avocat", "poursuites judiciaires", "tribunal",
            "totalement inacceptable", "catastrophe absolue", "résiliation immédiate",
            "je vais porter plainte", "parlez-moi de votre responsable",
            "votre entreprise est nulle", "je veux une compensation", "honteux",
        ],
        "strong": [
            "unacceptable", "outrageous", "furious", "disgusted", "appalling",
            "scandal", "incompetent", "ridiculous", "pathetic", "disaster",
            "terrible service", "worst", "i refuse", "this is a joke",
            "waste of time", "unprofessional", "not good enough", "fed up",
            "inacceptable", "inadmissible", "scandaleux", "furieux", "révoltant",
            "excédé", "ras-le-bol", "lamentable", "incompétence", "ridicule",
            "pas professionnel", "service déplorable", "c'est une blague",
            "en colère", "intolérable", "inqualifiable", "aberrant", "nul",
        ],
        "moderate": [
            "not happy", "disappointed", "unhappy", "not satisfied", "complaint",
            "wrong", "problem again", "still broken", "this is wrong",
            "pas content", "mécontent", "insatisfait", "pas satisfait",
            "encore un problème", "toujours le même problème", "décevant",
        ],
    },
    "Frustrated": {
        "critical": [
            "i've been waiting for weeks", "no one responds", "completely ignored",
            "this is the third time", "how many times do i have to", "enough is enough",
            "j'attends depuis des semaines", "personne ne répond", "complètement ignoré",
            "c'est la troisième fois", "combien de fois dois-je", "j'en ai vraiment assez",
        ],
        "strong": [
            "still waiting", "no response", "no update", "no news", "ignored",
            "once again", "not the first time", "every single time", "always late",
            "never on time", "keep having issues", "tired of this",
            "toujours en attente", "aucune réponse", "aucune mise à jour",
            "encore une fois", "pas la première fois", "à chaque fois",
            "toujours en retard", "jamais à l'heure", "j'en ai marre",
            "sans nouvelles", "toujours rien", "sans réponse",
        ],
        "moderate": [
            "frustrated", "annoyed", "disappointed again", "delayed again",
            "why is it", "how long", "when will", "still not received",
            "frustré", "énervé", "déçu encore", "encore du retard",
            "pourquoi encore", "combien de temps", "quand est-ce que",
            "toujours pas reçu", "j'attends depuis",
        ],
    },
    "Urgent": {
        "critical": [
            "production stopped", "line stopped", "factory halted", "operations blocked",
            "we are losing money", "clients waiting", "shipment overdue by days",
            "must arrive today", "last possible moment", "cannot ship without",
            "production arrêtée", "ligne bloquée", "usine à l'arrêt", "opérations bloquées",
            "on perd de l'argent", "clients en attente", "livraison en retard de plusieurs jours",
            "doit arriver aujourd'hui", "dernier moment possible", "impossible de livrer sans",
        ],
        "strong": [
            "urgent", "asap", "immediately", "right now", "today", "emergency",
            "critical deadline", "blocking us", "top priority", "time sensitive",
            "cannot wait", "need it now", "running out", "out of stock",
            "de toute urgence", "immédiatement", "dès maintenant",
            "délai critique", "nous bloque", "priorité absolue", "ne peut pas attendre",
            "il nous faut maintenant", "rupture de stock", "stock épuisé",
        ],
        "moderate": [
            "deadline", "soon", "by end of week", "by friday", "we need it by",
            "no later than", "before", "quickly", "fast",
            "délai", "bientôt", "d'ici vendredi", "avant la fin de la semaine",
            "il nous faut avant", "au plus tard", "rapidement", "vite",
        ],
    },
    "Anxious": {
        "critical": [
            "really worried", "very concerned", "starting to panic", "we have a serious problem",
            "this could impact our contract", "our client is threatening",
            "vraiment inquiet", "très préoccupé", "on commence à paniquer",
            "nous avons un problème sérieux", "cela pourrait impacter notre contrat",
            "notre client menace",
        ],
        "strong": [
            "worried", "concerned", "anxious", "uncertain", "not sure what to do",
            "what happened", "any news", "please confirm", "can you check",
            "still no update", "tracking shows nothing", "is everything okay",
            "inquiet", "préoccupé", "incertain", "je ne sais pas quoi faire",
            "qu'est-ce qui se passe", "des nouvelles", "pouvez-vous confirmer",
            "pouvez-vous vérifier", "le suivi ne montre rien", "tout va bien",
        ],
        "moderate": [
            "wondering", "i hope", "not received yet", "should i", "is it normal",
            "getting worried", "bit concerned",
            "je me demande", "j'espère", "pas encore arrivé", "est-ce normal",
            "je commence à m'inquiéter", "un peu préoccupé", "pas encore reçu",
        ],
    },
    "Satisfied": {
        "critical": [
            "extremely satisfied", "exceptional service", "outstanding", "could not be happier",
            "extrêmement satisfait", "service exceptionnel", "remarquable", "très heureux",
        ],
        "strong": [
            "thank you", "great job", "well done", "excellent", "perfect", "satisfied",
            "happy with", "appreciate", "pleased", "wonderful", "fantastic",
            "merci", "très bien", "parfait", "satisfait", "content",
            "je vous remercie", "impeccable", "au top", "bravo", "super",
        ],
        "moderate": [
            "good", "okay", "fine", "received", "confirmed", "noted", "understood",
            "bien reçu", "bien livré", "reçu", "confirmé", "noté", "compris", "ok",
        ],
    },
}

INTENT_KEYWORDS = {
    "tracking": [
        "where is", "track", "tracking", "status", "where are", "shipment",
        "delivery status", "shipped yet", "in transit",
        "où est", "suivi", "statut", "expédié", "en transit", "mon colis",
    ],
    "refund": [
        "refund", "reimbursement", "credit note", "money back", "invoice credit",
        "get my money", "charge back", "overpaid",
        "remboursement", "avoir", "note de crédit", "trop payé", "récupérer mon argent",
    ],
    "cancel": [
        "cancel", "cancellation", "stop the order", "do not ship", "abort",
        "annuler", "annulation", "arrêter la commande", "ne pas expédier",
    ],
    "escalate": [
        "manager", "supervisor", "director", "escalate", "higher up", "team lead",
        "responsable", "directeur", "superviseur", "escalade", "hiérarchie", "supérieur",
    ],
    "complaint": [
        "complaint", "formal complaint", "report", "file a complaint", "not acceptable",
        "réclamation", "plainte formelle", "signaler", "déposer une plainte",
    ],
    "replace": [
        "replace", "replacement", "send again", "resend", "new shipment", "substitute",
        "remplacement", "renvoyer", "nouvelle livraison", "substitut", "remplacer",
    ],
    "info": [
        "why", "when", "what happened", "explain", "reason", "cause", "update",
        "pourquoi", "quand", "qu'est-ce qui s'est passé", "expliquer", "raison", "mise à jour",
    ],
    "payment": [
        "invoice", "payment", "billing", "overcharge", "wrong amount", "statement",
        "facture", "paiement", "facturation", "montant incorrect", "relevé",
    ],
    "document_request": [
        "send me", "please send", "can you send", "need the", "missing document",
        "delivery note", "proof of delivery", "pod", "packing slip", "receipt",
        "acknowledgement", "certificate", "analysis", "conformity", "safety sheet",
        "waybill", "cmr", "transport document", "customs document",
        "envoyez-moi", "pouvez-vous m'envoyer", "il me faut", "document manquant",
        "bon de livraison", "accusé de réception", "preuve de livraison",
        "certificat d'analyse", "certificat de conformité", "fiche de sécurité",
        "fiche technique", "lettre de voiture", "liasse documentaire",
        "bl", "coa", "coc", "fds", "sds", "ar",
    ],
    "ncmr": [
        "ncmr", "non-conformance", "nonconformance", "waiver", "deviation",
        "derogation", "shelf life extension", "lot extension", "expired lot",
        "out of spec", "non conforming material",
        "dérogation", "non-conformité", "non conformité", "prolongation de lot",
        "lot expiré", "lot périmé", "demande de dérogation", "extension de lot",
        "hors spécification", "matériau non conforme", "prolongation de durée",
        "durée de vie dépassée", "dde", "demande d'utilisation",
    ],
}

TOPIC_KEYWORDS = {
    "delivery": [
        "delivery", "shipment", "shipping", "transport", "carrier", "dispatch",
        "package", "parcel", "freight", "logistics", "arrived", "not arrived",
        "livraison", "expédition", "transport", "transporteur", "colis", "fret",
        "logistique", "arrivé", "pas arrivé", "réception",
    ],
    "payment": [
        "invoice", "payment", "billing", "credit note", "overcharge", "amount",
        "balance", "statement", "bank transfer", "wire",
        "facture", "paiement", "facturation", "avoir", "montant", "solde",
        "relevé", "virement",
    ],
    "stock": [
        "stock", "availability", "available", "out of stock", "inventory",
        "replenishment", "restock", "production",
        "disponibilité", "disponible", "rupture", "inventaire",
        "réapprovisionnement",
    ],
    "quality": [
        "damaged", "broken", "wrong product", "defective", "not conforming",
        "quality issue", "wrong reference", "incorrect",
        "endommagé", "cassé", "mauvais produit", "défectueux", "non conforme",
        "problème qualité", "mauvaise référence",
    ],
    "admin": [
        "document", "certificate", "compliance", "customs", "declaration",
        "contract", "agreement", "terms",
        "certificat", "conformité", "douane", "déclaration",
        "contrat", "accord", "conditions",
    ],
}

FRENCH_KEYWORDS = [
    "commande", "livraison", "retard", "facture", "bonjour", "merci",
    "problème", "bloquée", "inacceptable", "votre", "notre", "nous",
    "pouvez", "pouvons", "avons", "avez", "sont", "être", "colis",
    "expédition", "transporteur", "réception", "délai", "article",
    "produit", "référence", "numéro", "suivi", "paiement", "avoir",
    "remboursement", "annulation", "relance", "réclamation", "bonsoir",
    "cordialement", "passé", "toujours", "encore", "pourquoi", "depuis",
    "aucun", "aucune", "besoin", "urgent", "immédiatement", "résoudre",
    "résolution", "escalade", "responsable", "service", "client",
    "partenaire", "fournisseur", "contrat", "accord", "conformité",
]

_WEIGHT_MAP  = {"critical": 3, "strong": 2, "moderate": 1}
_CHROMA_PATH = "./chroma_db"
_MODEL_NAME  = "all-MiniLM-L6-v2"

# Cosine similarity thresholds for emotion intensity
# all-MiniLM-L6-v2 produces scores in the 0.25–0.65 range for related content
_INTENSITY_THRESHOLDS = [
    (0.55, "Very High"),
    (0.44, "High"),
    (0.35, "Medium"),
    (0.25, "Low"),
]


# ==============================================================================
# KEYWORD FALLBACK — used when embeddings are unavailable
# ==============================================================================

def _kw_detect_emotion(text: str) -> tuple:
    scores = {}
    for emotion, levels in EMOTION_KEYWORDS.items():
        score = 0
        for level, kws in levels.items():
            w = _WEIGHT_MAP[level]
            for kw in kws:
                if re.search(r'\b' + re.escape(kw) + r'\b', text):
                    score += w
        scores[emotion] = score

    best      = max(scores, key=scores.get)
    top_score = scores[best]

    if top_score == 0:
        return "Neutral", "Low", scores

    if top_score >= 6:
        intensity = "Very High"
    elif top_score >= 4:
        intensity = "High"
    elif top_score >= 2:
        intensity = "Medium"
    else:
        intensity = "Low"

    return best, intensity, scores


def _kw_detect_intent(text: str) -> str:
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, kws in INTENT_KEYWORDS.items():
        for kw in kws:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general inquiry"


def _kw_detect_topic(text: str) -> str:
    scores = {topic: 0 for topic in TOPIC_KEYWORDS}
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                scores[topic] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


# ==============================================================================
# NLP ENGINE
# ==============================================================================

class NLPEngine:
    """
    Embedding-based NLP engine (sentence-transformers + ChromaDB).
    Falls back to keyword detection automatically if packages are unavailable
    or if ChromaDB fails to initialize.
    """

    def __init__(self, auto_build: bool = True):
        self._ready = False

        if not _EMBEDDINGS_AVAILABLE:
            print("[NLPEngine] sentence-transformers/chromadb not found → keyword fallback active.")
            return

        try:
            self._ef = SentenceTransformerEmbeddingFunction(model_name=_MODEL_NAME)
            self._chroma = chromadb.PersistentClient(path=_CHROMA_PATH)

            self._emo_col = self._chroma.get_or_create_collection(
                name="emotion_refs",
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._int_col = self._chroma.get_or_create_collection(
                name="intent_refs",
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._top_col = self._chroma.get_or_create_collection(
                name="topic_refs",
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )

            self._kb_col = self._chroma.get_or_create_collection(
                name="knowledge_base",
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )

            self._ready = True

            if auto_build and self._emo_col.count() == 0:
                print("[NLPEngine] First run — building reference embeddings...")
                self.build_reference_embeddings()
                print("[NLPEngine] Reference embeddings ready.")

            # Auto-build KB embeddings if collection is empty
            if auto_build and self._kb_col.count() == 0:
                self._try_build_kb_from_file()

        except Exception as exc:
            print(f"[NLPEngine] Init failed ({exc}) → keyword fallback active.")
            self._ready = False

    # ── Build / Rebuild ───────────────────────────────────────────────────────

    def build_reference_embeddings(self, force: bool = False):
        """
        Upserts all reference phrases into ChromaDB collections.
        force=True deletes and recreates each collection from scratch.
        """
        if not self._ready:
            print("[NLPEngine] Engine not ready — cannot build embeddings.")
            return

        if force:
            for name in ("emotion_refs", "intent_refs", "topic_refs", "knowledge_base"):
                try:
                    self._chroma.delete_collection(name)
                except Exception:
                    pass
            self._emo_col = self._chroma.get_or_create_collection(
                "emotion_refs", embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._int_col = self._chroma.get_or_create_collection(
                "intent_refs", embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._top_col = self._chroma.get_or_create_collection(
                "topic_refs", embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )

        # Emotions
        docs, ids, metas = [], [], []
        for emotion, levels in EMOTION_KEYWORDS.items():
            for level, phrases in levels.items():
                weight = _WEIGHT_MAP.get(level, 1)
                for i, phrase in enumerate(phrases):
                    ids.append(f"emo_{emotion}_{level}_{i}")
                    docs.append(phrase)
                    metas.append({"category": emotion, "level": level, "weight": weight})
        if docs:
            self._emo_col.upsert(ids=ids, documents=docs, metadatas=metas)
            print(f"  OK Emotion collection: {len(docs)} phrases indexed.")

        # Intents
        docs, ids, metas = [], [], []
        for intent, phrases in INTENT_KEYWORDS.items():
            for i, phrase in enumerate(phrases):
                ids.append(f"int_{intent}_{i}")
                docs.append(phrase)
                metas.append({"category": intent, "weight": 1})
        if docs:
            self._int_col.upsert(ids=ids, documents=docs, metadatas=metas)
            print(f"  OK Intent collection: {len(docs)} phrases indexed.")

        # Topics
        docs, ids, metas = [], [], []
        for topic, phrases in TOPIC_KEYWORDS.items():
            for i, phrase in enumerate(phrases):
                ids.append(f"top_{topic}_{i}")
                docs.append(phrase)
                metas.append({"category": topic, "weight": 1})
        if docs:
            self._top_col.upsert(ids=ids, documents=docs, metadatas=metas)
            print(f"  OK Topic collection:  {len(docs)} phrases indexed.")

    def _try_build_kb_from_file(self, kb_path: str = "knowledge_base.json"):
        """Loads knowledge_base.json and builds KB embeddings if the file exists."""
        import json as _json
        if not os.path.exists(kb_path):
            return
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                entries = _json.load(f).get("entries", [])
            if entries:
                print("[NLPEngine] Building KB embeddings from knowledge_base.json...")
                self.build_kb_embeddings(entries)
        except Exception as exc:
            print(f"[NLPEngine] KB auto-build failed: {exc}")

    def build_kb_embeddings(self, entries: list, force: bool = False):
        """
        Embeds each KB entry (title + content) and stores it in the
        'knowledge_base' ChromaDB collection.

        Parameters
        ----------
        entries : list of dicts from knowledge_base.json
        force   : if True, wipe the collection before inserting
        """
        if not self._ready:
            return

        if force:
            try:
                self._chroma.delete_collection("knowledge_base")
            except Exception:
                pass

        # Always refresh the handle — collection may have been deleted by a prior force rebuild
        self._kb_col = self._chroma.get_or_create_collection(
            "knowledge_base", embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

        docs, ids, metas = [], [], []
        for entry in entries:
            doc_text = f"{entry.get('title', '')}. {entry.get('content', '')}"
            ids.append(entry["id"])
            docs.append(doc_text)
            metas.append({
                "id":      entry["id"],
                "title":   entry.get("title", ""),
                "intents": ",".join(entry.get("intents", [])),
                "topics":  ",".join(entry.get("topics", [])),
            })

        if docs:
            self._kb_col.upsert(ids=ids, documents=docs, metadatas=metas)
            print(f"  OK Knowledge base: {len(docs)} entries indexed.")

    def search_kb(self, query: str, intent: str = None,
                  topic: str = None, max_results: int = 3) -> list:
        """
        Semantic KB search.

        Embeds the query, retrieves top candidates by cosine similarity,
        then applies metadata boosts:
          +0.10 if intent matches entry intents
          +0.05 if topic  matches entry topics

        Returns a list of entry dicts (from metadata) sorted by boosted score,
        each with a "relevance" float field (0–1) added.
        Falls back to empty list if engine not ready.
        """
        if not self._ready:
            return []

        try:
            count = self._kb_col.count()
            if count == 0:
                return []

            results = self._kb_col.query(
                query_texts=[query],
                n_results=min(5, count),
                include=["distances", "metadatas"],
            )

            candidates = []
            for dist, meta in zip(results["distances"][0], results["metadatas"][0]):
                sim = self._sim(dist)

                # Metadata boosts
                entry_intents = meta.get("intents", "").split(",")
                entry_topics  = meta.get("topics",  "").split(",")
                boost = 0.0
                if intent and intent in entry_intents:
                    boost += 0.10
                if topic and topic in entry_topics:
                    boost += 0.05

                boosted = min(1.0, sim + boost)
                candidates.append({
                    "id":        meta.get("id", ""),
                    "title":     meta.get("title", ""),
                    "relevance": round(boosted, 3),
                    "_intents":  entry_intents,
                    "_topics":   entry_topics,
                })

            candidates.sort(key=lambda x: -x["relevance"])
            return candidates[:max_results]

        except Exception as exc:
            print(f"[NLPEngine] search_kb error: {exc}")
            return []

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _sim(cosine_distance: float) -> float:
        """ChromaDB cosine distance → similarity (0 = different, 1 = identical)."""
        return max(0.0, 1.0 - cosine_distance)

    def _aggregate(self, collection, text: str, categories: list, n: int = 50) -> tuple:
        """
        Query a collection and return:
          scores    — {category: weighted_similarity_sum}
          top_sim   — highest single-phrase similarity found
        """
        count = collection.count()
        if count == 0:
            return {c: 0.0 for c in categories}, 0.0

        results = collection.query(
            query_texts=[text],
            n_results=min(n, count),
            include=["distances", "metadatas"],
        )

        scores  = {c: 0.0 for c in categories}
        top_sim = 0.0

        for dist, meta in zip(results["distances"][0], results["metadatas"][0]):
            sim    = self._sim(dist)
            cat    = meta.get("category", "")
            weight = meta.get("weight", 1)
            if cat in scores:
                scores[cat] += sim * weight
            if sim > top_sim:
                top_sim = sim

        return scores, top_sim

    @staticmethod
    def _intensity_from_sim(sim: float) -> str:
        for threshold, label in _INTENSITY_THRESHOLDS:
            if sim >= threshold:
                return label
        return "Low"

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_emotion(self, text: str) -> tuple:
        """
        Returns (emotion, intensity, all_scores, confidence).
          all_scores  — {emotion: weighted_similarity_sum}  (float values)
          confidence  — top cosine similarity for the winning category (0–1)
        Falls back to keyword detection if engine not ready.
        """
        if not self._ready:
            emo, intens, scores = _kw_detect_emotion(text)
            return emo, intens, scores, 0.0

        try:
            categories = list(EMOTION_KEYWORDS.keys())
            scores, top_sim = self._aggregate(self._emo_col, text, categories)

            if top_sim < 0.22:
                return "Neutral", "Low", {c: 0.0 for c in categories}, round(top_sim, 3)

            best      = max(scores, key=scores.get)
            intensity = self._intensity_from_sim(top_sim)
            confidence = round(top_sim, 3)

            return best, intensity, scores, confidence

        except Exception as exc:
            print(f"[NLPEngine] detect_emotion error ({exc}) → fallback")
            emo, intens, scores = _kw_detect_emotion(text)
            return emo, intens, scores, 0.0

    def detect_intent(self, text: str) -> tuple:
        """
        Returns (intent, confidence).
        Falls back to keyword detection if engine not ready.
        """
        if not self._ready:
            return _kw_detect_intent(text), 0.0

        try:
            categories = list(INTENT_KEYWORDS.keys())
            scores, top_sim = self._aggregate(self._int_col, text, categories)

            if top_sim < 0.22:
                return "general inquiry", round(top_sim, 3)

            best = max(scores, key=scores.get)
            return best, round(top_sim, 3)

        except Exception as exc:
            print(f"[NLPEngine] detect_intent error ({exc}) → fallback")
            return _kw_detect_intent(text), 0.0

    def detect_topic(self, text: str) -> tuple:
        """
        Returns (topic, confidence).
        Falls back to keyword detection if engine not ready.
        """
        if not self._ready:
            return _kw_detect_topic(text), 0.0

        try:
            categories = list(TOPIC_KEYWORDS.keys())
            scores, top_sim = self._aggregate(self._top_col, text, categories)

            if top_sim < 0.22:
                return "general", round(top_sim, 3)

            best = max(scores, key=scores.get)
            return best, round(top_sim, 3)

        except Exception as exc:
            print(f"[NLPEngine] detect_topic error ({exc}) → fallback")
            return _kw_detect_topic(text), 0.0

    def detect_language(self, text: str) -> tuple:
        """
        Returns (language, confidence) using keyword matching.
        Keyword approach works well for FR/EN and doesn't need embeddings.
        """
        matches = sum(
            1 for w in FRENCH_KEYWORDS
            if re.search(r'\b' + re.escape(w) + r'\b', text)
        )
        if matches >= 3:
            return "French", min(1.0, round(matches / 8, 2))
        elif matches >= 1:
            return "French", 0.5
        return "English", 0.9


# ==============================================================================
# SINGLETON — one engine per process, shared across the app
# ==============================================================================

_engine: Optional[NLPEngine] = None


def get_engine() -> NLPEngine:
    global _engine
    if _engine is None:
        _engine = NLPEngine()
    return _engine


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build/rebuild NLP reference embeddings")
    parser.add_argument("--build", action="store_true", help="Build embeddings (skip if already built)")
    parser.add_argument("--force", action="store_true", help="Force full rebuild (delete + recreate)")
    args = parser.parse_args()

    if not args.build:
        parser.print_help()
        sys.exit(0)

    if not _EMBEDDINGS_AVAILABLE:
        print("ERROR: Required packages not installed.")
        print("  pip install sentence-transformers chromadb")
        sys.exit(1)

    engine = NLPEngine(auto_build=False)
    if not engine._ready:
        print("ERROR: Engine failed to initialize.")
        sys.exit(1)

    if args.force:
        print("Force-rebuilding all collections...")
    engine.build_reference_embeddings(force=args.force)

    # Also rebuild KB embeddings
    engine._try_build_kb_from_file("knowledge_base.json")
    print("Done.")
