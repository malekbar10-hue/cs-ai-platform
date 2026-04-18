from openai import OpenAI
from dotenv import load_dotenv
import json
import os
from datetime import datetime
from connector import get_connector
from nlp import get_engine as _nlp
from paths import config_path as _config_path, resolve_company_file, resolve_data_file

load_dotenv()

# ==============================================================================
# CONFIG — load once at startup
# ==============================================================================

def load_config():
    with open(_config_path(), "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG    = load_config()
COMPANY   = CONFIG["company"]["name"]
SIGNATURE = CONFIG["company"]["agent_signature"]
ROLE      = CONFIG["company"]["agent_role"]
CLIENTS   = CONFIG["company"].get("example_clients", "major B2B accounts")
AI_MODEL  = CONFIG["ai"]["model"]   # kept for backward compat


def select_model(emotion: str, intensity: str, intent: str,
                 confidence_score: float = 0.5) -> dict:
    """
    Returns a model config dict {model, max_tokens, temperature} based on
    the complexity of the current interaction.

    Falls back to the legacy single-model config if "models" is not defined.
    """
    ai_cfg  = CONFIG.get("ai", {})
    models  = ai_cfg.get("models")
    routing = ai_cfg.get("routing", {})

    # Backward compatibility: no models block → use single model for everything
    if not models:
        legacy = ai_cfg.get("model", "gpt-4.1-mini")
        return {"model": legacy, "max_tokens": 1000, "temperature": 0.5}

    complex_intents     = routing.get("complex_intents",     ["escalate", "complaint", "cancel"])
    complex_emotions    = routing.get("complex_emotions",    ["Angry", "Urgent"])
    complex_intensities = routing.get("complex_intensities", ["Very High", "High"])
    simple_intents      = routing.get("simple_intents",      ["tracking", "info", "document_request"])

    # Complex: sensitive intent OR high-stakes emotion
    if intent in complex_intents or (
        emotion in complex_emotions and intensity in complex_intensities
    ):
        return models["complex"]

    # Simple: routine intent + high confidence + calm emotion
    if (
        intent in simple_intents
        and confidence_score > 0.80
        and emotion in ("Neutral", "Satisfied")
    ):
        return models["simple"]

    return models["standard"]

# ---- API client ----
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---- Data connector (swap json_mock → erp_api → crm_api in config.json) ----
connector = get_connector(CONFIG)

# ---- Order database (local dict built from connector for fast access) ----
order_database = {oid: connector.get_order(oid) for oid in connector.list_order_ids()}

# ==============================================================================
# LANGUAGE DETECTION
# ==============================================================================

french_keywords = [
    "commande", "livraison", "retard", "facture", "bonjour", "merci",
    "problème", "bloquée", "inacceptable", "votre", "notre", "nous",
    "pouvez", "pouvons", "avons", "avez", "sont", "être", "colis",
    "expédition", "transporteur", "réception", "délai", "article",
    "produit", "référence", "numéro", "suivi", "paiement", "avoir",
    "remboursement", "annulation", "relance", "réclamation", "bonsoir",
    "cordialement", "passé", "toujours", "encore", "pourquoi", "depuis",
    "aucun", "aucune", "besoin", "urgent", "immédiatement", "résoudre",
    "résolution", "escalade", "responsable", "service", "client",
    "partenaire", "fournisseur", "contrat", "accord", "conformité"
]

# def detect_language(text):  # ← original keyword version (kept as reference)
#     is_french = any(re.search(r'\b' + re.escape(w) + r'\b', text) for w in french_keywords)
#     return "French" if is_french else "English"

def detect_language(text):
    """Return (language: str, confidence: float, is_mixed: bool)."""
    return _nlp().detect_language(text)

# ==============================================================================
# EMOTION DETECTION — weighted scoring (critical=3, strong=2, moderate=1)
# ==============================================================================

emotion_keywords = {
    "Angry": {
        "critical": [
            "lawsuit", "legal action", "lawyer", "attorney", "sue", "court",
            "this is outrageous", "absolutely unacceptable", "complete disaster",
            "cancel everything", "never working with you again", "i demand compensation",
            "i will escalate", "speak to your manager", "your company is a joke",
            "procès", "avocat", "poursuites judiciaires", "tribunal",
            "totalement inacceptable", "catastrophe absolue", "résiliation immédiate",
            "je vais porter plainte", "parlez-moi de votre responsable",
            "votre entreprise est nulle", "je veux une compensation", "honteux"
        ],
        "strong": [
            "unacceptable", "outrageous", "furious", "disgusted", "appalling",
            "scandal", "incompetent", "ridiculous", "pathetic", "disaster",
            "terrible service", "worst", "i refuse", "this is a joke",
            "waste of time", "unprofessional", "not good enough", "fed up",
            "inacceptable", "inadmissible", "scandaleux", "furieux", "révoltant",
            "excédé", "ras-le-bol", "lamentable", "incompétence", "ridicule",
            "pas professionnel", "service déplorable", "c'est une blague",
            "en colère", "intolérable", "inqualifiable", "aberrant", "nul"
        ],
        "moderate": [
            "not happy", "disappointed", "unhappy", "not satisfied", "complaint",
            "wrong", "problem again", "still broken", "this is wrong",
            "pas content", "mécontent", "insatisfait", "pas satisfait",
            "encore un problème", "toujours le même problème", "décevant"
        ]
    },
    "Frustrated": {
        "critical": [
            "i've been waiting for weeks", "no one responds", "completely ignored",
            "this is the third time", "how many times do i have to", "enough is enough",
            "j'attends depuis des semaines", "personne ne répond", "complètement ignoré",
            "c'est la troisième fois", "combien de fois dois-je", "j'en ai vraiment assez"
        ],
        "strong": [
            "still waiting", "no response", "no update", "no news", "ignored",
            "once again", "not the first time", "every single time", "always late",
            "never on time", "keep having issues", "tired of this",
            "toujours en attente", "aucune réponse", "aucune mise à jour",
            "encore une fois", "pas la première fois", "à chaque fois",
            "toujours en retard", "jamais à l'heure", "j'en ai marre",
            "sans nouvelles", "toujours rien", "sans réponse"
        ],
        "moderate": [
            "frustrated", "annoyed", "disappointed again", "delayed again",
            "why is it", "how long", "when will", "still not received",
            "frustré", "énervé", "déçu encore", "encore du retard",
            "pourquoi encore", "combien de temps", "quand est-ce que",
            "toujours pas reçu", "j'attends depuis"
        ]
    },
    "Urgent": {
        "critical": [
            "production stopped", "line stopped", "factory halted", "operations blocked",
            "we are losing money", "clients waiting", "shipment overdue by days",
            "must arrive today", "last possible moment", "cannot ship without",
            "production arrêtée", "ligne bloquée", "usine à l'arrêt", "opérations bloquées",
            "on perd de l'argent", "clients en attente", "livraison en retard de plusieurs jours",
            "doit arriver aujourd'hui", "dernier moment possible", "impossible de livrer sans"
        ],
        "strong": [
            "urgent", "asap", "immediately", "right now", "today", "emergency",
            "critical deadline", "blocking us", "top priority", "time sensitive",
            "cannot wait", "need it now", "running out", "out of stock",
            "de toute urgence", "immédiatement", "dès maintenant",
            "délai critique", "nous bloque", "priorité absolue", "ne peut pas attendre",
            "il nous faut maintenant", "rupture de stock", "stock épuisé"
        ],
        "moderate": [
            "deadline", "soon", "by end of week", "by friday", "we need it by",
            "no later than", "before", "quickly", "fast",
            "délai", "bientôt", "d'ici vendredi", "avant la fin de la semaine",
            "il nous faut avant", "au plus tard", "rapidement", "vite"
        ]
    },
    "Anxious": {
        "critical": [
            "really worried", "very concerned", "starting to panic", "we have a serious problem",
            "this could impact our contract", "our client is threatening",
            "vraiment inquiet", "très préoccupé", "on commence à paniquer",
            "nous avons un problème sérieux", "cela pourrait impacter notre contrat",
            "notre client menace"
        ],
        "strong": [
            "worried", "concerned", "anxious", "uncertain", "not sure what to do",
            "what happened", "any news", "please confirm", "can you check",
            "still no update", "tracking shows nothing", "is everything okay",
            "inquiet", "préoccupé", "incertain", "je ne sais pas quoi faire",
            "qu'est-ce qui se passe", "des nouvelles", "pouvez-vous confirmer",
            "pouvez-vous vérifier", "le suivi ne montre rien", "tout va bien"
        ],
        "moderate": [
            "wondering", "i hope", "not received yet", "should i", "is it normal",
            "getting worried", "bit concerned",
            "je me demande", "j'espère", "pas encore arrivé", "est-ce normal",
            "je commence à m'inquiéter", "un peu préoccupé", "pas encore reçu"
        ]
    },
    "Satisfied": {
        "critical": [
            "extremely satisfied", "exceptional service", "outstanding", "could not be happier",
            "extrêmement satisfait", "service exceptionnel", "remarquable", "très heureux"
        ],
        "strong": [
            "thank you", "great job", "well done", "excellent", "perfect", "satisfied",
            "happy with", "appreciate", "pleased", "wonderful", "fantastic",
            "merci", "très bien", "parfait", "satisfait", "content",
            "je vous remercie", "impeccable", "au top", "bravo", "super"
        ],
        "moderate": [
            "good", "okay", "fine", "received", "confirmed", "noted", "understood",
            "bien reçu", "bien livré", "reçu", "confirmé", "noté", "compris", "ok"
        ]
    }
}

# def detect_emotion(text):  # ← original keyword version (kept as reference)
#     scores = {}
#     for emotion, levels in emotion_keywords.items():
#         score = 0
#         for kw in levels.get("critical", []):
#             if re.search(r'\b' + re.escape(kw) + r'\b', text): score += 3
#         for kw in levels.get("strong", []):
#             if re.search(r'\b' + re.escape(kw) + r'\b', text): score += 2
#         for kw in levels.get("moderate", []):
#             if re.search(r'\b' + re.escape(kw) + r'\b', text): score += 1
#         scores[emotion] = score
#     best = max(scores, key=scores.get)
#     top_score = scores[best]
#     if top_score == 0: return "Neutral", "Low", scores
#     intensity = "Very High" if top_score >= 6 else "High" if top_score >= 4 else "Medium" if top_score >= 2 else "Low"
#     return best, intensity, scores

def detect_emotion(text):
    """Returns (emotion, intensity, all_scores, confidence)."""
    return _nlp().detect_emotion(text)

# ==============================================================================
# INTENT DETECTION
# ==============================================================================

intent_keywords = {
    "tracking":  [
        "where is", "track", "tracking", "status", "where are", "shipment",
        "delivery status", "shipped yet", "in transit",
        "où est", "suivi", "statut", "expédié", "en transit", "mon colis"
    ],
    "refund":    [
        "refund", "reimbursement", "credit note", "money back", "invoice credit",
        "get my money", "charge back", "overpaid",
        "remboursement", "avoir", "note de crédit", "trop payé", "récupérer mon argent"
    ],
    "cancel":    [
        "cancel", "cancellation", "stop the order", "do not ship", "abort",
        "annuler", "annulation", "arrêter la commande", "ne pas expédier"
    ],
    "escalate":  [
        "manager", "supervisor", "director", "escalate", "higher up", "team lead",
        "responsable", "directeur", "superviseur", "escalade", "hiérarchie", "supérieur"
    ],
    "complaint": [
        "complaint", "formal complaint", "report", "file a complaint", "not acceptable",
        "réclamation", "plainte formelle", "signaler", "déposer une plainte"
    ],
    "replace":   [
        "replace", "replacement", "send again", "resend", "new shipment", "substitute",
        "remplacement", "renvoyer", "nouvelle livraison", "substitut", "remplacer"
    ],
    "info":      [
        "why", "when", "what happened", "explain", "reason", "cause", "update",
        "pourquoi", "quand", "qu'est-ce qui s'est passé", "expliquer", "raison", "cause", "mise à jour"
    ],
    "payment":   [
        "invoice", "payment", "billing", "overcharge", "wrong amount", "statement",
        "facture", "paiement", "facturation", "montant incorrect", "relevé"
    ],
    "document_request": [
        # EN
        "send me", "please send", "can you send", "need the", "missing document",
        "delivery note", "proof of delivery", "pod", "packing slip", "receipt",
        "acknowledgement", "certificate", "analysis", "conformity", "safety sheet",
        "waybill", "cmr", "transport document", "customs document",
        # FR
        "envoyez-moi", "pouvez-vous m'envoyer", "il me faut", "document manquant",
        "bon de livraison", "accusé de réception", "preuve de livraison",
        "certificat d'analyse", "certificat de conformité", "fiche de sécurité",
        "fiche technique", "lettre de voiture", "liasse documentaire",
        "bl", "coa", "coc", "fds", "sds", "cmr", "ar "
    ],
    "ncmr": [
        # EN
        "ncmr", "non-conformance", "nonconformance", "waiver", "deviation",
        "derogation", "shelf life extension", "lot extension", "expired lot",
        "out of spec", "non conforming material",
        # FR
        "dérogation", "non-conformité", "non conformité", "prolongation de lot",
        "lot expiré", "lot périmé", "demande de dérogation", "extension de lot",
        "hors spécification", "matériau non conforme", "prolongation de durée",
        "durée de vie dépassée", "dde", "demande d'utilisation"
    ]
}

# def detect_intent(text):  # ← original keyword version (kept as reference)
#     scores = {intent: 0 for intent in intent_keywords}
#     for intent, keywords in intent_keywords.items():
#         for kw in keywords:
#             if re.search(r'\b' + re.escape(kw) + r'\b', text): scores[intent] += 1
#     best = max(scores, key=scores.get)
#     return best if scores[best] > 0 else "general inquiry"

def detect_intent(text):
    """Returns (intent, confidence)."""
    return _nlp().detect_intent(text)

# ==============================================================================
# TOPIC DETECTION
# ==============================================================================

topic_keywords = {
    "delivery": [
        "delivery", "shipment", "shipping", "transport", "carrier", "dispatch",
        "package", "parcel", "freight", "logistics", "arrived", "not arrived",
        "livraison", "expédition", "transport", "transporteur", "colis", "fret",
        "logistique", "arrivé", "pas arrivé", "réception"
    ],
    "payment":  [
        "invoice", "payment", "billing", "credit note", "overcharge", "amount",
        "balance", "statement", "bank transfer", "wire",
        "facture", "paiement", "facturation", "avoir", "montant", "solde",
        "relevé", "virement"
    ],
    "stock":    [
        "stock", "availability", "available", "out of stock", "inventory",
        "replenishment", "restock", "production",
        "disponibilité", "disponible", "rupture", "inventaire",
        "réapprovisionnement"
    ],
    "quality":  [
        "damaged", "broken", "wrong product", "defective", "not conforming",
        "quality issue", "wrong reference", "incorrect",
        "endommagé", "cassé", "mauvais produit", "défectueux", "non conforme",
        "problème qualité", "mauvaise référence"
    ],
    "admin":    [
        "document", "certificate", "compliance", "customs", "declaration",
        "contract", "agreement", "terms",
        "certificat", "conformité", "douane", "déclaration",
        "contrat", "accord", "conditions"
    ]
}

# def detect_topic(text):  # ← original keyword version (kept as reference)
#     scores = {topic: 0 for topic in topic_keywords}
#     for topic, keywords in topic_keywords.items():
#         for kw in keywords:
#             if re.search(r'\b' + re.escape(kw) + r'\b', text): scores[topic] += 1
#     best = max(scores, key=scores.get)
#     return best if scores[best] > 0 else "general"

def detect_topic(text):
    """Returns (topic, confidence)."""
    return _nlp().detect_topic(text)

# ==============================================================================
# EMOTION INSTRUCTIONS
# ==============================================================================

emotion_instructions = {
    "Angry": {
        "Very High": "The customer is EXTREMELY ANGRY. Open with a direct, sincere apology. Take full ownership with no excuses. Propose an immediate concrete action. Do NOT be defensive or bureaucratic.",
        "High":      "The customer is VERY ANGRY. Acknowledge their frustration in the first sentence. Apologize clearly. Take ownership. Propose a concrete next step with a timeline.",
        "Medium":    "The customer is ANGRY. Acknowledge the issue respectfully. Apologize. Explain what you will do to fix it.",
        "Low":       "The customer shows dissatisfaction. Be empathetic and proactive. Propose a solution."
    },
    "Frustrated": {
        "Very High": "The customer is EXTREMELY FRUSTRATED (repeated failures). Acknowledge this is not the first time. Apologize for the pattern. Commit to a definitive resolution. Offer a direct point of contact.",
        "High":      "The customer is VERY FRUSTRATED. Acknowledge their long wait or repeated issue. Show you understand the history. Give a firm commitment with a date.",
        "Medium":    "The customer is FRUSTRATED. Acknowledge the inconvenience. Give a clear timeline and next steps.",
        "Low":       "The customer is slightly frustrated. Be informative and reassuring. Give a status update."
    },
    "Urgent": {
        "Very High": "CRITICAL URGENCY — customer operations are impacted. Lead immediately with action steps. Be direct and brief. No filler. Give a specific time commitment.",
        "High":      "HIGH URGENCY. Lead with your solution before anything else. Give a deadline for resolution.",
        "Medium":    "Urgent request. Prioritize their need. Give a clear action and estimated timeline.",
        "Low":       "Time-sensitive request. Address it promptly and give an estimated resolution time."
    },
    "Anxious": {
        "Very High": "The customer is VERY ANXIOUS and their business is at risk. Be immediately reassuring. Give all available status information. Commit to regular updates.",
        "High":      "The customer is worried. Be calm and reassuring. Confirm the current situation clearly. Provide tracking or status information.",
        "Medium":    "The customer is concerned. Reassure them with factual information. Confirm next steps.",
        "Low":       "The customer has a mild concern. Answer clearly and confirm everything is on track."
    },
    "Satisfied": {
        "Very High": "The customer is very satisfied. Respond warmly and positively. Reinforce the relationship.",
        "High":      "The customer is satisfied. Thank them sincerely and confirm all is in order.",
        "Medium":    "The customer is neutral/satisfied. Respond professionally and confirm receipt or status.",
        "Low":       "Standard inquiry. Be professional and informative."
    },
    "Neutral": {
        "Low": "The customer's tone is neutral. Be professional, clear, and informative."
    }
}

def get_emotion_instruction(emotion, intensity):
    levels = emotion_instructions.get(emotion, emotion_instructions["Neutral"])
    return levels.get(intensity, levels.get("Low", "Be professional and informative."))

# ==============================================================================
# ORDER DETECTION — returns (order_info_text, priority) or ("", "Normal")
# ==============================================================================

def find_order(text):
    for order_id in order_database:
        if order_id in text:
            order = order_database[order_id]
            priority      = order.get("priority", "Normal")
            stock         = order.get("stock", "N/A")
            status        = order["status"]
            customer      = order.get("customer", "Unknown")

            # Use action-oriented defaults for missing fields
            delivery_date = order.get("delivery_date") or "MISSING — commit to providing an update within 24 hours"
            reason        = order.get("reason") or "UNDER INVESTIGATION — our logistics team is actively reviewing the root cause"

            info = f"""
ORDER DATA (verified internal data):
- Order ID:      {order_id}
- Customer:      {customer}
- Status:        {status}
- Delivery date: {delivery_date}
- Reason:        {reason}
- Stock level:   {stock} units
- Priority:      {priority}
- Stock alert:   {"⚠ BLOCKED — no stock available" if stock == 0 else "Stock available"}
"""
            return info, priority, order_id
    return "", "Normal", None

# ==============================================================================
# BUILD SYSTEM PROMPT (rebuilt every turn with fresh analysis)
# ==============================================================================

def build_system_prompt(response_language, customer_emotion, emotion_intensity,
                         secondary_emotions, customer_intent, customer_topic,
                         order_info_text, priority, history_context="",
                         profile_context="", trajectory_context="", kb_context="",
                         lessons=None):

    _lessons_block = ""
    if lessons:
        _lines = "\n".join(f"- {l}" for l in lessons)
        _lessons_block = (
            "\nLEARNED FROM PAST CORRECTIONS — apply to this response:\n"
            f"{_lines}\n"
        )

    secondary_label = f" (secondary signals: {', '.join(secondary_emotions)})" if secondary_emotions else ""

    customer_profile = f"""CUSTOMER ANALYSIS (this turn):
- Language:        {response_language}
- Emotional state: {customer_emotion} — Intensity: {emotion_intensity}{secondary_label}
- Primary intent:  {customer_intent}
- Topic area:      {customer_topic}"""

    order_block = order_info_text if order_info_text else \
        "ORDER DATA: No order number found yet. If the customer hasn't provided one, politely ask for it."

    return f"""You are a {ROLE} at {COMPANY}, with years of experience handling professional accounts.

WHO YOU ARE:
You are the visible face of a full team working behind you — logistics coordinators, supply chain managers, transport specialists, and account managers. When a client contacts you, things are already moving internally. Your role is to be the calm, confident bridge between the client and that team. You never work alone, and you never stand in front of a client empty-handed.

YOUR MINDSET:
Act exactly like a real, experienced customer service professional would:
- Something is always being done. Even when you don't have the exact answer yet, your team is on it.
- You never expose internal uncertainty to the client. You absorb it and replace it with confidence.
- You don't need every detail to be reassuring — a real agent says "our team is actively working on this and you'll hear from us today" without knowing the exact internal status.
- When data is missing, assume the situation is being handled internally and communicate that naturally.
- You speak with the authority of someone who has direct access to internal systems and can trigger actions immediately.

WHAT YOU NEVER DO:
- Never say you don't know, can't confirm, or have no information — that's not your job
- Never leave a client without a next step, a commitment, or a timeline
- Never make the client feel like they're talking to someone powerless
- Never expose system limitations ("our database doesn't show...", "I have no record of...")

WHAT YOU ALWAYS DO:
- Project that the situation is under control and being actively managed
- Give a confident timeline even if approximate ("you will hear from us within 24 hours", "our team will confirm by end of day")
- Take personal ownership: "I am personally making sure this is resolved", "I am flagging this to our logistics team right now"
- Reassure without over-promising: be confident, not reckless

You are in an ongoing conversation — you have full memory of everything said before. Reference it naturally when relevant.

{customer_profile}

{order_block}

{profile_context if profile_context else ""}

{trajectory_context if trajectory_context else ""}

{kb_context if kb_context else ""}

{history_context if history_context else ""}

RESPONSE STRATEGY:
{get_emotion_instruction(customer_emotion, emotion_intensity)}

INTENT HANDLING:
- tracking    → provide status, delivery date, carrier info if available
- refund      → acknowledge, explain process, give timeline
- cancel      → confirm feasibility based on status, explain procedure
- escalate    → acknowledge the request, assure priority handling, do not deflect
- complaint   → treat formally, acknowledge, log and commit to follow-up
- replace     → confirm stock availability before committing
- info        → explain the reason clearly using the order data
- payment     → address billing details, request invoice number if missing
- general     → provide a helpful, professional response

PRIORITY HANDLING:
- Normal   → standard professional response
- High     → more proactive, offer a follow-up commitment
- Critical → strong ownership, immediate action, personal accountability

ORDER PRIORITY: {priority}

LANGUAGE RULE:
- Respond exclusively in {response_language}
- The entire email must be in {response_language}

FORMAT:
- Professional B2B email with subject line
- Clear paragraphs
- Signature: Best regards, / {SIGNATURE}
{_lessons_block}"""

# ==============================================================================
# ERP ACTIONS (mock — writes to orders.json)
# ==============================================================================

def detect_document_type(text):
    """Identifie quel document le client demande."""
    t = text.lower()
    docs = []
    if any(w in t for w in ["bon de livraison", " bl ", "delivery note", "packing slip", "liasse"]):
        docs.append("Bon de Livraison (BL)")
    if any(w in t for w in ["accusé de réception", " ar ", "acknowledgement", "receipt confirmation"]):
        docs.append("Accusé de Réception (AR)")
    if any(w in t for w in ["facture", "invoice", "billing document"]):
        docs.append("Facture")
    if any(w in t for w in ["certificat d'analyse", " coa", "certificate of analysis", "analyse"]):
        docs.append("Certificat d'Analyse (CoA)")
    if any(w in t for w in ["certificat de conformité", " coc", "certificate of conformity", "conformité"]):
        docs.append("Certificat de Conformité (CoC)")
    if any(w in t for w in ["fiche de sécurité", " fds", " sds", "safety data sheet", "msds", "fiche technique"]):
        docs.append("Fiche de Sécurité (FDS/SDS)")
    if any(w in t for w in [" cmr", "lettre de voiture", "waybill", "transport document"]):
        docs.append("Lettre de Voiture (CMR)")
    if any(w in t for w in ["preuve de livraison", "proof of delivery", " pod", "delivery proof"]):
        docs.append("Preuve de Livraison (POD)")
    if any(w in t for w in ["douane", "customs", "déclaration", "declaration"]):
        docs.append("Document Douanier")
    return docs if docs else ["Document (type non précisé)"]


# Hard keyword gate for highly specific intents — semantic engine can over-generalize these
_NCMR_HARD_KEYWORDS = [
    "ncmr", "dérogation", "derogation", "non-conformance", "nonconformance",
    "waiver", "shelf life", "lot expir", "prolongation de lot", "lot périmé",
    "hors spécification", "out of spec", "extension de lot", "demande de dérogation",
]

def _is_ncmr(text):
    t = text.lower()
    return any(kw in t for kw in _NCMR_HARD_KEYWORDS)

_DOC_HARD_KEYWORDS = [
    "bl", "bon de livraison", "delivery note", "ar ", "accusé de réception",
    "facture", "invoice", "coa", "certificat d'analyse", "coc", "certificat de conformité",
    "fds", "sds", "fiche de sécurité", "cmr", "lettre de voiture", "pod",
    "preuve de livraison", "document", "certificat",
]

def _is_document_request(text):
    t = text.lower()
    return any(kw in t for kw in _DOC_HARD_KEYWORDS)


def detect_suggested_action(order_id, customer_intent, customer_emotion, emotion_intensity, text=""):
    """Analyse la commande + le contexte client et propose une action ERP si pertinent."""
    # Guard: semantic engine sometimes misfires on specific intents — verify with hard keywords
    if customer_intent == "ncmr" and not _is_ncmr(text):
        customer_intent = "info"   # reclassify as generic info request
    if customer_intent == "document_request" and not _is_document_request(text):
        customer_intent = "info"
    if not order_id or order_id not in order_database:
        # Même sans commande connue, certaines actions restent possibles
        if customer_intent == "document_request":
            docs = detect_document_type(text)
            return {
                "type":        "REQUEST_DOCUMENT",
                "label":       f"Envoyer : {', '.join(docs)}",
                "description": "Le client demande un document. Précisez le numéro de commande si nécessaire.",
                "changes":     {"documents_requested": docs},
                "risk":        "Low",
            }
        if customer_intent == "ncmr":
            return {
                "type":        "CREATE_NCMR",
                "label":       "Créer une demande NCMR / Dérogation",
                "description": "Le client demande une dérogation ou prolongation de lot. Initier le processus qualité.",
                "changes":     {"ncmr_requested": True},
                "risk":        "Medium",
            }
        return None

    order    = order_database[order_id]
    status   = order.get("status", "")
    priority = order.get("priority", "Normal")
    stock    = order.get("stock", 0)

    # ── Demande de document ───────────────────────────────────────────────────
    if customer_intent == "document_request":
        docs = detect_document_type(text)
        return {
            "type":        "REQUEST_DOCUMENT",
            "label":       f"Envoyer : {', '.join(docs)} — commande {order_id}",
            "description": f"Le client demande les documents suivants pour la commande {order_id} : {', '.join(docs)}.",
            "changes":     {"documents_requested": docs},
            "risk":        "Low",
        }

    # ── NCMR / Dérogation ────────────────────────────────────────────────────
    if customer_intent == "ncmr":
        return {
            "type":        "CREATE_NCMR",
            "label":       f"Créer NCMR / Dérogation — commande {order_id}",
            "description": "Le client demande une dérogation ou prolongation de lot. Transmettre au service qualité.",
            "changes":     {"ncmr_requested": True, "ncmr_status": "Pending quality review"},
            "risk":        "Medium",
            "requires_input": True,
            "input_label": "Numéro de lot concerné (optionnel)",
        }

    # ── Débloquer : commande bloquée mais stock disponible ───────────────────
    if status == "Blocked" and stock > 0 and customer_intent in ["info", "escalate", "replace", "general inquiry", "tracking"]:
        return {
            "type":        "UNBLOCK_ORDER",
            "label":       f"Débloquer la commande {order_id}",
            "description": f"Statut : Blocked | Stock disponible : {stock} unités. Passer à Processing.",
            "changes":     {"status": "Processing", "reason": "Unblocked by customer service"},
            "risk":        "Medium",
        }

    # ── Escalader la priorité ────────────────────────────────────────────────
    if customer_emotion in ["Angry", "Urgent"] and emotion_intensity in ["High", "Very High"] and priority != "Critical":
        return {
            "type":        "ESCALATE_PRIORITY",
            "label":       f"Escalader priorité → Critical",
            "description": f"Priorité actuelle : {priority}. Émotion : {customer_emotion} ({emotion_intensity}).",
            "changes":     {"priority": "Critical"},
            "risk":        "Low",
        }

    # ── Annuler la commande ───────────────────────────────────────────────────
    if customer_intent == "cancel" and status not in ["Cancelled", "Shipped"]:
        return {
            "type":        "CANCEL_ORDER",
            "label":       f"Annuler la commande {order_id}",
            "description": f"Statut : {status}. Le client demande l'annulation.",
            "changes":     {"status": "Cancelled", "reason": "Cancelled at customer request"},
            "risk":        "High",
        }

    # ── Avoir / remboursement ─────────────────────────────────────────────────
    if customer_intent == "refund":
        return {
            "type":        "FLAG_CREDIT_NOTE",
            "label":       f"Marquer commande {order_id} pour avoir",
            "description": "Le client demande un remboursement. Marquer pour traitement financier.",
            "changes":     {"credit_note_requested": True},
            "risk":        "Low",
        }

    # ── Mettre à jour la date de livraison ────────────────────────────────────
    if status == "Delayed" and customer_intent in ["tracking", "info"]:
        return {
            "type":          "UPDATE_DELIVERY_DATE",
            "label":         f"Mettre à jour la date de livraison — {order_id}",
            "description":   f"Commande en retard. Saisir la nouvelle date confirmée.",
            "changes":       {"delivery_date": None},
            "risk":          "Low",
            "requires_input": True,
            "input_label":   "Nouvelle date de livraison (ex: 20 April)",
        }

    return None


def execute_action(order_id, changes):
    """Applique les changements via le connecteur (JSON mock, ERP API ou CRM API selon config)."""
    result = connector.update_order(order_id, changes)
    if result:
        # Keep local cache in sync
        for field, value in changes.items():
            if value is not None and order_id in order_database:
                order_database[order_id][field] = value
    return result


# ==============================================================================
# CUSTOMER PROFILES — persistent memory per client
# ==============================================================================

PROFILES_FILE = resolve_data_file("customer_profiles.json")
KB_FILE       = resolve_company_file(CONFIG.get("knowledge_base", {}).get("file", "knowledge_base.json"))

def load_profiles():
    return connector.get_all_profiles()

def save_profiles(profiles):
    for name, data in profiles.items():
        connector.update_customer_profile(name, data)

def get_customer_profile(customer_name):
    if not customer_name:
        return None
    return load_profiles().get(customer_name)

def update_customer_profile(customer_name, language, emotion, intent, topic, resolved):
    """Called after each approved/modified interaction to update the client profile."""
    if not customer_name:
        return
    profiles = load_profiles()
    p = profiles.get(customer_name, {
        "preferred_language":  language,
        "first_contact":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_interactions":  0,
        "resolved_cases":      0,
        "unresolved_cases":    0,
        "emotion_counts":      {},
        "intent_counts":       {},
        "topic_counts":        {},
        "last_contact":        "",
        "last_emotion":        "",
        "last_intent":         "",
    })

    p["last_contact"]        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p["total_interactions"]  = p.get("total_interactions", 0) + 1
    p["last_emotion"]        = emotion
    p["last_intent"]         = intent

    if resolved:
        p["resolved_cases"]   = p.get("resolved_cases", 0) + 1
    else:
        p["unresolved_cases"] = p.get("unresolved_cases", 0) + 1

    # Frequency counters
    p["emotion_counts"][emotion] = p.get("emotion_counts", {}).get(emotion, 0) + 1
    p["intent_counts"][intent]   = p.get("intent_counts",  {}).get(intent,  0) + 1
    p["topic_counts"][topic]     = p.get("topic_counts",   {}).get(topic,   0) + 1

    # Dominant values
    p["dominant_emotion"] = max(p["emotion_counts"], key=p["emotion_counts"].get)
    p["dominant_intent"]  = max(p["intent_counts"],  key=p["intent_counts"].get)
    p["dominant_topic"]   = max(p["topic_counts"],   key=p["topic_counts"].get)

    # Language: update if more recent
    if language in ("French", "English"):
        p["preferred_language"] = language

    profiles[customer_name] = p
    save_profiles(profiles)


def format_customer_profile_context(customer_name):
    """Returns a concise profile block for the system prompt."""
    p = get_customer_profile(customer_name)
    if not p:
        return ""

    total   = p.get("total_interactions", 0)
    resolved = p.get("resolved_cases", 0)
    rate    = f"{int(resolved/total*100)}%" if total > 0 else "N/A"
    recurrence = "High" if total >= 5 else "Medium" if total >= 2 else "Low"

    lines = [
        "CLIENT PROFILE (persistent memory):",
        f"- Name:                {customer_name}",
        f"- Preferred language:  {p.get('preferred_language', 'Unknown')}",
        f"- Total interactions:  {total} (resolution rate: {rate})",
        f"- Recurrence level:    {recurrence}",
        f"- Dominant emotion:    {p.get('dominant_emotion', 'Unknown')}",
        f"- Most common issue:   intent={p.get('dominant_intent','?')} / topic={p.get('dominant_topic','?')}",
        f"- Last contact:        {p.get('last_contact', 'Unknown')}",
        f"- Last emotion:        {p.get('last_emotion', 'Unknown')}",
    ]
    if recurrence == "High":
        lines.append("⚠ HIGH RECURRENCE: This client contacts us frequently. Show extra proactivity.")
    if p.get("unresolved_cases", 0) > 0:
        lines.append(f"⚠ {p['unresolved_cases']} unresolved case(s) on record. Acknowledge if relevant.")

    return "\n".join(lines)


# ==============================================================================
# EMOTIONAL TRAJECTORY — trend across sessions for this client
# ==============================================================================

EMOTION_SEVERITY = {
    "Satisfied": 0, "Neutral": 1, "Anxious": 2,
    "Frustrated": 3, "Urgent": 4, "Angry": 5
}

def get_emotion_trajectory(customer_name, n_sessions=6):
    """
    Calculates the emotional trend for a client across their last N sessions.
    Returns: {"trend": "Escalating|Stable|Improving", "sessions": [...], "alert": bool}
    """
    if not customer_name:
        return None

    all_logs = load_logs()
    client_logs = [
        e for e in all_logs
        if e.get("customer_name", "").lower() == customer_name.lower()
        and e.get("log_type") != "erp_action"
        and e.get("emotion")
    ]

    if len(client_logs) < 2:
        return None

    # Group by session, take dominant emotion per session
    sessions = {}
    for e in client_logs:
        sid = e.get("session_id", "")
        sev = EMOTION_SEVERITY.get(e.get("emotion", "Neutral"), 1)
        if sid not in sessions:
            sessions[sid] = {"timestamp": e.get("timestamp",""), "max_severity": sev, "emotion": e.get("emotion")}
        else:
            if sev > sessions[sid]["max_severity"]:
                sessions[sid]["max_severity"] = sev
                sessions[sid]["emotion"]      = e.get("emotion")

    # Sort by time, take last N
    sorted_sessions = sorted(sessions.values(), key=lambda x: x["timestamp"])[-n_sessions:]

    if len(sorted_sessions) < 2:
        return None

    severities = [s["max_severity"] for s in sorted_sessions]
    first_half = sum(severities[:len(severities)//2]) / max(len(severities)//2, 1)
    second_half = sum(severities[len(severities)//2:]) / max(len(severities) - len(severities)//2, 1)

    diff = second_half - first_half
    if diff >= 1.0:
        trend = "Escalating"
    elif diff <= -1.0:
        trend = "Improving"
    else:
        trend = "Stable"

    return {
        "trend":    trend,
        "sessions": sorted_sessions,
        "alert":    trend == "Escalating" and severities[-1] >= 3,
    }


def format_trajectory_context(trajectory, customer_name):
    if not trajectory:
        return ""
    icons = {"Escalating": "🔴", "Stable": "🟡", "Improving": "🟢"}
    icon  = icons.get(trajectory["trend"], "⚪")
    sessions_str = " → ".join(s["emotion"] for s in trajectory["sessions"])
    lines = [
        f"EMOTIONAL TRAJECTORY for {customer_name}:",
        f"- Trend:    {icon} {trajectory['trend']}",
        f"- History:  {sessions_str}",
    ]
    if trajectory.get("alert"):
        lines.append("⚠ ALERT: Client is escalating. Apply maximum empathy and proactivity.")
    return "\n".join(lines)


# ==============================================================================
# KNOWLEDGE BASE — FAQ, policies, procedures (RAG)
# ==============================================================================

def load_knowledge_base():
    if not os.path.exists(KB_FILE):
        return []
    with open(KB_FILE, "r", encoding="utf-8") as f:
        try:    return json.load(f).get("entries", [])
        except: return []

def search_knowledge_base_legacy(intent, topic, text, max_results=2):
    """
    Original keyword-based KB search — kept as fallback.
    Scores entries by intent match (+3), topic match (+2), keyword hits (+1 each).
    """
    entries = load_knowledge_base()
    t       = text.lower()
    scored  = []

    for entry in entries:
        score = 0
        if intent in entry.get("intents", []):
            score += 3
        if topic in entry.get("topics", []):
            score += 2
        for kw in entry.get("keywords", []):
            if kw in t:
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:max_results]]


def search_knowledge_base(intent, topic, text, max_results=2):
    """
    Semantic KB search via NLPEngine (sentence-transformers + ChromaDB).
    Falls back to keyword search if embeddings are unavailable.

    Semantic results are enriched with a "relevance" float (0–1).
    Legacy results get relevance derived from their keyword score.
    """
    engine = _nlp()

    # Try semantic search first
    if engine._ready:
        hits = engine.search_kb(query=text, intent=intent, topic=topic,
                                max_results=max_results)
        if hits:
            # Enrich with full entry content from knowledge_base.json
            all_entries = {e["id"]: e for e in load_knowledge_base()}
            results = []
            for hit in hits:
                entry = all_entries.get(hit["id"])
                if entry:
                    results.append({**entry, "relevance": hit["relevance"]})
            if results:
                return results

    # Fallback: keyword search (no relevance field)
    return search_knowledge_base_legacy(intent, topic, text, max_results)

def format_kb_context(entries):
    if not entries:
        return ""
    lines = [f"INTERNAL KNOWLEDGE BASE (official {COMPANY} policies and procedures):"]
    lines.append("Use this information to give accurate, policy-compliant answers.")
    lines.append("Higher relevance = stronger match to this specific situation.")
    lines.append("")
    for entry in entries:
        relevance = entry.get("relevance")
        rel_label = f" [relevance: {int(relevance * 100)}%]" if relevance is not None else ""
        lines.append(f"[{entry['title']}]{rel_label}")
        lines.append(entry["content"])
        lines.append("")
    return "\n".join(lines)


# ==============================================================================
# HISTORY SEARCH — Retrieval from logs (mock CRM)
# Designed to be swapped with a real CRM API later.
# Same interface, different data source.
# ==============================================================================

LOG_FILE = resolve_data_file("logs.json")

def load_logs():
    return connector.get_logs()


def search_history(order_id=None, customer_name=None, intent=None, topic=None,
                   current_session_id=None, max_results=4):
    """
    3-level history search:
      L1 — Same order_id          (score +4) → exact match
      L2 — Same customer_name     (score +3) → client history
      L3 — Same intent + topic    (score +1 each) → similar problem, any client

    Returns a dict with:
      - conversations: list of past messages sorted by relevance
      - erp_actions:   list of ERP actions taken on this order
      - pattern:       summary string if recurring issue detected
    """
    all_logs = load_logs()

    # Separate conversation logs from ERP action logs
    conv_logs = [
        e for e in all_logs
        if e.get("log_type") != "erp_action"
        and e.get("customer_msg")
        and e.get("session_id") != current_session_id   # exclude current session
    ]
    erp_logs = [
        e for e in all_logs
        if e.get("log_type") == "erp_action"
        and e.get("order_id") == order_id
    ]

    # ── Score all entries for this client only ───────────────────────────────
    scored = []
    for entry in conv_logs:
        score  = 0
        levels = []

        # Must belong to same client — L1 (same order) or L2 (same customer name)
        is_same_order  = order_id and entry.get("order_id") == order_id
        is_same_client = customer_name and entry.get("customer_name", "").lower() == customer_name.lower()

        if not is_same_order and not is_same_client:
            continue   # ignore other clients entirely

        if is_same_order:
            score += 4
            levels.append("L1:same_order")
        if is_same_client:
            score += 3
            levels.append("L2:same_client")

        # Similarity boost: same type of problem
        if intent and entry.get("intent") == intent:
            score += 2
            levels.append("same_intent")
        if topic and entry.get("topic") == topic:
            score += 1
            levels.append("same_topic")

        # Bonus: this case was resolved — valuable as inspiration
        if entry.get("action") in ("approved", "modified") and entry.get("final_reply"):
            score += 2
            levels.append("resolved")

        scored.append((score, entry, levels))

    # Sort: relevance desc, then most recent first
    scored.sort(key=lambda x: (-x[0], x[1].get("timestamp", "2000-01-01")))

    top = scored[:max_results]

    # ── Detect recurring pattern ──────────────────────────────────────────────
    same_order_count  = sum(1 for _, e, _ in top if e.get("order_id") == order_id and order_id)
    same_client_count = sum(1 for _, e, _ in top if "L2:same_client" in _)
    similar_resolved  = [(e, lv) for _, e, lv in top if "resolved" in lv and ("same_intent" in lv or "same_topic" in lv)]

    pattern = None
    if same_order_count >= 2:
        pattern = f"⚠ RECURRING — This order has been contacted {same_order_count} time(s) before."
    elif same_client_count >= 2:
        pattern = f"⚠ RECURRING CLIENT — {customer_name} has {same_client_count} past interactions on record."

    return {
        "conversations":     [(entry, levels) for _, entry, levels in top],
        "similar_resolved":  similar_resolved,   # resolved cases with similar problem
        "erp_actions":       erp_logs[-3:],
        "pattern":           pattern,
    }


def format_history_context(history):
    """
    Formats the retrieved history into a clear block for the system prompt.
    The AI uses this to:
    - Reference past interactions naturally
    - Detect and acknowledge recurring issues
    - Apply resolution patterns from similar past cases
    """
    if not history:
        return ""

    convs = history.get("conversations", [])
    erps  = history.get("erp_actions", [])
    pattern = history.get("pattern")

    if not convs and not erps:
        return ""

    lines = []
    lines.append("─" * 50)
    lines.append("HISTORICAL CONTEXT (retrieved from communication logs)")
    lines.append("Use this to personalize your response, reference past cases,")
    lines.append("and apply proven resolution patterns.")
    lines.append("")

    if pattern:
        lines.append(pattern)
        lines.append("")

    if convs:
        lines.append("Past interactions found:")
        for entry, levels in convs:
            match_label = (
                "Same order"    if "L1:same_order"  in levels else
                "Same client"   if "L2:same_client" in levels else
                "Similar case"
            )
            lines.append(
                f"  [{entry.get('timestamp','?')}] {match_label} | "
                f"Intent: {entry.get('intent','?')} | "
                f"Topic: {entry.get('topic','?')} | "
                f"Emotion: {entry.get('emotion','?')} ({entry.get('intensity','')})"
            )
            msg = entry.get("customer_msg", "")[:130].replace("\n", " ")
            lines.append(f"  Customer said: \"{msg}\"")

            reply = entry.get("final_reply") or entry.get("agent_reply", "")
            if reply:
                reply_preview = reply[:130].replace("\n", " ")
                lines.append(f"  Agent replied: \"{reply_preview}\"")

            action = entry.get("action", "")
            if action in ("approved", "modified"):
                lines.append(f"  → Response was sent ({action})")
            elif action == "rejected":
                lines.append(f"  → Draft was rejected (not sent)")
            lines.append("")

    if erps:
        lines.append("ERP actions previously executed on this order:")
        for erp in erps:
            lines.append(f"  [{erp.get('timestamp','?')}] {erp.get('label','?')}")
        lines.append("")

    # ── Resolved similar cases → resolution inspiration ───────────────────────
    similar_resolved = history.get("similar_resolved", [])
    if similar_resolved:
        lines.append("─" * 40)
        lines.append("RESOLUTION INSPIRATION — Similar problems already solved for this client:")
        lines.append("Do NOT copy these responses. Extract the resolution LOGIC and adapt it.")
        lines.append("")
        for entry, levels in similar_resolved:
            similarity = []
            if "same_intent" in levels: similarity.append(f"same intent ({entry.get('intent')})")
            if "same_topic"  in levels: similarity.append(f"same topic ({entry.get('topic')})")
            lines.append(
                f"  [{entry.get('timestamp','?')}] Similarity: {', '.join(similarity)} | "
                f"Emotion: {entry.get('emotion','?')} ({entry.get('intensity','')})"
            )
            msg = entry.get("customer_msg", "")[:120].replace("\n", " ")
            lines.append(f"  Problem: \"{msg}\"")
            reply = (entry.get("final_reply") or "")[:200].replace("\n", " ")
            if reply:
                lines.append(f"  How it was resolved: \"{reply}\"")
            lines.append("")
        lines.append(
            "Apply the same resolution logic to the current case, "
            "adapted to the client's current situation and emotion."
        )
        lines.append("")

    lines.append(
        "INSTRUCTION: Reference this history naturally when relevant "
        "(e.g. 'Comme lors de votre demande du [date]...'). "
        "If a recurring pattern is detected, show stronger ownership and proactivity."
    )
    lines.append("─" * 50)
    return "\n".join(lines)

def save_log(session_id, turn, language, emotion, intensity, intent, topic,
             order_id, priority, user_message, agent_reply):
    connector.save_log({
        "session_id":   session_id,
        "turn":         turn,
        "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "language":     language,
        "emotion":      emotion,
        "intensity":    intensity,
        "intent":       intent,
        "topic":        topic,
        "order_id":     order_id,
        "priority":     priority,
        "customer_msg": user_message,
        "agent_reply":  agent_reply,
    })

# ==============================================================================
# MAIN CONVERSATION LOOP
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print(f"  {COMPANY} Customer Service AI — Multi-turn session")
    print("  Type 'exit' to end the conversation")
    print("="*60 + "\n")

    conversation_history = []
    session_order_info   = ""
    session_priority     = "Normal"
    session_order_id     = None
    session_id           = datetime.now().strftime("%Y%m%d_%H%M%S")
    turn = 0

    closing_words = ["exit", "quit", "bye", "goodbye", "au revoir", "bonne journée", "merci beaucoup", "à bientôt"]

    while True:
        user_input = input("Customer: ").strip()

        if not user_input:
            continue

        if any(word in user_input.lower() for word in closing_words):
            print(f"\nAgent: Thank you for contacting {COMPANY}. Have a great day!\n")
            break

        turn += 1
        text = user_input.lower()

        response_language, _, _ = detect_language(text)
        customer_emotion, emotion_intensity, all_scores = detect_emotion(text)
        secondary_emotions = [e for e, s in all_scores.items() if s > 0 and e != customer_emotion]
        customer_intent  = detect_intent(text)
        customer_topic   = detect_topic(text)

        new_order_info, new_priority, new_order_id = find_order(user_input)
        if new_order_id:
            session_order_info = new_order_info
            session_priority   = new_priority
            session_order_id   = new_order_id

        system_prompt = build_system_prompt(
            response_language, customer_emotion, emotion_intensity,
            secondary_emotions, customer_intent, customer_topic,
            session_order_info, session_priority
        )

        conversation_history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": system_prompt}] + conversation_history

        response = client.chat.completions.create(model="gpt-4.1-mini", messages=messages)
        reply = response.choices[0].message.content

        conversation_history.append({"role": "assistant", "content": reply})
        save_log(session_id, turn, response_language, customer_emotion, emotion_intensity,
                 customer_intent, customer_topic, session_order_id, session_priority,
                 user_input, reply)

        print(f"\n{'─'*60}")
        print(f"  Turn {turn} | {response_language} | {customer_emotion} ({emotion_intensity}) | {customer_intent} | {customer_topic}")
        if session_order_id:
            print(f"  Order: {session_order_id} | Priority: {session_priority}")
        print(f"{'─'*60}\n")
        print(f"Agent:\n{reply}\n")
