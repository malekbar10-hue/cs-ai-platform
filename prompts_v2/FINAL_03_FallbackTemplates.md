Create all Jinja2 fallback template files for `FallbackTemplateEngine`.

The engine loads templates from `cs_ai/templates/fallback/`.
It selects `{reason}_{language}.j2` first, then falls back to `{reason}.j2`.
Four reasons × 2 languages = 8 files total.

---

## Step 1 — Create directory

Create `cs_ai/templates/fallback/` if it doesn't exist.

---

## Step 2 — Create all 8 template files

### `missing_info.j2` (English default)
```jinja2
Dear {{ ctx.get('customer_name') or 'Customer' }},

Thank you for contacting us. We want to help you as quickly as possible.

To locate your request and provide you with accurate information, we need your order number.

Could you please reply with:
- Your order number (format: ORD-XXXX-XXXX)
- The email address used when placing the order

Once we have these details, we will respond right away.

{{ ctx.get('signature', 'Best regards,\nCustomer Service') }}
```

### `missing_info_French.j2`
```jinja2
Bonjour {{ ctx.get('customer_name') or 'Madame, Monsieur' }},

Merci de nous avoir contactés. Nous souhaitons vous aider dans les meilleurs délais.

Afin de traiter votre demande, nous avons besoin de votre numéro de commande.

Pourriez-vous nous communiquer :
- Votre numéro de commande (format : ORD-XXXX-XXXX)
- L'adresse e-mail utilisée lors de la commande

Dès réception de ces informations, nous traiterons votre demande sans délai.

{{ ctx.get('signature', 'Cordialement,\nService Client') }}
```

### `system_unavailable.j2` (English default)
```jinja2
Dear {{ ctx.get('customer_name') or 'Customer' }},

Thank you for reaching out to us.

We are currently experiencing a temporary technical issue preventing us from accessing your order information in real time. Our technical team has been notified and is working to resolve this as quickly as possible.

{% if ctx.get('order_id') %}
We have noted your order reference: {{ ctx.order_id }}
{% endif %}

A member of our team will follow up with you within the next 2 business hours with a full update.

We sincerely apologize for this inconvenience and thank you for your patience.

{{ ctx.get('signature', 'Best regards,\nCustomer Service') }}
```

### `system_unavailable_French.j2`
```jinja2
Bonjour {{ ctx.get('customer_name') or 'Madame, Monsieur' }},

Merci de nous avoir contactés.

Nous rencontrons actuellement une interruption technique temporaire qui nous empêche d'accéder à vos informations de commande en temps réel. Notre équipe technique travaille à la résolution de ce problème dans les meilleurs délais.

{% if ctx.get('order_id') %}
Nous avons bien noté votre référence de commande : {{ ctx.order_id }}
{% endif %}

Un membre de notre équipe vous contactera dans les 2 heures ouvrables avec une réponse complète.

Nous vous prions de nous excuser pour ce désagrément et vous remercions de votre patience.

{{ ctx.get('signature', 'Cordialement,\nService Client') }}
```

### `high_risk.j2` (English default)
```jinja2
Dear {{ ctx.get('customer_name') or 'Customer' }},

Thank you for contacting us regarding your {% if ctx.get('order_id') %}order {{ ctx.order_id }}{% else %}recent request{% endif %}.

We understand this is an important matter and want to ensure it receives the attention it deserves. Your case has been flagged for priority review by a senior member of our customer service team.

A dedicated agent will contact you directly within 1 business hour to personally handle your request and provide a full resolution.

We apologize for any inconvenience and appreciate your patience.

{{ ctx.get('signature', 'Best regards,\nCustomer Service') }}
```

### `high_risk_French.j2`
```jinja2
Bonjour {{ ctx.get('customer_name') or 'Madame, Monsieur' }},

Merci de nous avoir contactés concernant {% if ctx.get('order_id') %}votre commande {{ ctx.order_id }}{% else %}votre demande récente{% endif %}.

Nous comprenons l'importance de cette situation. Votre dossier a été transmis en priorité à un membre senior de notre service client.

Un agent dédié vous contactera directement dans un délai d'1 heure ouvrable pour traiter votre demande et vous apporter une résolution complète.

Nous vous prions de nous excuser pour tout inconvénient et vous remercions de votre compréhension.

{{ ctx.get('signature', 'Cordialement,\nService Client') }}
```

### `ambiguous_request.j2` (English default)
```jinja2
Dear {{ ctx.get('customer_name') or 'Customer' }},

Thank you for your message. We want to make sure we address exactly what you need.

To help us direct your request to the right team, could you clarify:

1. Are you looking for an update on your order status, or would you like to modify or cancel your order?
{% if not ctx.get('order_id') %}
2. Could you please provide your order number (format: ORD-XXXX-XXXX)?
{% endif %}
3. Is there a specific deadline or urgency we should be aware of?

Once we have this, we will respond with a complete and accurate answer right away.

{{ ctx.get('signature', 'Best regards,\nCustomer Service') }}
```

### `ambiguous_request_French.j2`
```jinja2
Bonjour {{ ctx.get('customer_name') or 'Madame, Monsieur' }},

Merci pour votre message. Nous souhaitons nous assurer de répondre précisément à votre besoin.

Pourriez-vous nous préciser :

1. Souhaitez-vous obtenir une mise à jour sur l'état de votre commande, ou souhaitez-vous la modifier ou l'annuler ?
{% if not ctx.get('order_id') %}
2. Pourriez-vous nous indiquer votre numéro de commande (format : ORD-XXXX-XXXX) ?
{% endif %}
3. Y a-t-il une urgence ou un délai particulier dont nous devrions tenir compte ?

Dès réception de ces informations, nous vous apporterons une réponse complète dans les plus brefs délais.

{{ ctx.get('signature', 'Cordialement,\nService Client') }}
```

---

## Step 3 — Verify

Run in Python from repo root:

```python
import sys
sys.path.insert(0, "cs_ai/engine")
from fallback_engine import FallbackTemplateEngine

engine = FallbackTemplateEngine()
ctx_en = {"customer_name": "John", "order_id": "ORD-2024-001",
          "language": "English", "signature": "Best regards,\nCS Team"}
ctx_fr = {**ctx_en, "language": "French"}

for reason in ("missing_info", "system_unavailable", "high_risk", "ambiguous_request"):
    print(f"\n=== {reason} (EN) ===")
    print(engine.render(reason, ctx_en)[:120])
    print(f"\n=== {reason} (FR) ===")
    print(engine.render(reason, ctx_fr)[:120])
```

All 8 combinations must render without `TemplateNotFound` or `UndefinedError`.
Also test with `order_id=None` and `customer_name=""` to confirm conditional blocks work.
