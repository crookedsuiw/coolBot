"""Seeds the Kalqy client with the settings, FAQs and crawl URLs that used to be hardcoded.

Safe to run more than once: existing rows are left untouched, so dashboard edits are never overwritten.
Usage (from kalqy_bot/): python -m scripts.seed
"""
import secrets
import psycopg
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector
from core.db import DATABASE_URL
from core.embeddings import get_ov_embedding

CLIENT_SLUG = "kalqy"
CLIENT_NAME = "Kalqy"
# Websites allowed to embed the widget (scheme + domain only). Enforced from Phase 1.
ALLOWED_ORIGINS = ["https://kalqy.in"]
GROQ_MODEL_NAME = 'qwen/qwen3.8-27b'

# --- Bot settings (version 1, previously the two prompts in main.py) ---
BOT_NAME = "KalqyBot"
PERSONA = """You are KalqyBot, a helpful assistant for Kalqy.
Tone: Parent-friendly, avoiding jargon, enthusiastic, and brief."""
INSTRUCTIONS = "Only use links when relevant to the user's question or when they flow with a natural response."
DO_NOT_RULES = """Do not hallucinate specific facts about Kalqy.
Do not jam in links for unrelated queries."""
APPROVED_LINKS = [
    {"label": "Download the App", "url": "https://kalqy.in/#download"},
    {"label": "Explore Games", "url": "https://kalqy.in/games"},
    {"label": "Media & Gallery", "url": "https://kalqy.in/gallery"},
    {"label": "About the Team", "url": "https://kalqy.in/#team"},
    {"label": "Main Website", "url": "https://kalqy.in/"},
]
GREETING = "Ask about our movement-based games, installing the app, or anything else about Kalqy."
FAQ_THRESHOLD = 0.70
RAG_TOP_K = 5

# --- Widget content (migration 002) ---
LOGO_URL = "/static/download.jpg"
PRIVACY_URL = None  # TODO: Kalqy's privacy policy link; the widget hides the link while this is empty
WELCOME_TITLE = "Hi! How can we help?"
QUICK_REPLIES = [
    {"label": "Download the app", "message": "How do I download the app?", "icon": "download"},
    {"label": "Explore games", "message": "What games does Kalqy have?", "icon": "games"},
    {"label": "What is Kalqy?", "message": "What is Kalqy?", "icon": "sparkle"},
    {"label": "Contact support", "message": "How do I contact support?", "icon": "phone"},
]

# --- Tier 1 FAQs (previously FAQ_DB in main.py) ---
DOWNLOAD_ANSWERS = [
    "Good news — the Kalqy app is available to download for both Windows and Mac! 💻<br><a href='https://kalqy.in/#download' target='_blank' class='action-btn'>Download App</a>",
    "You can download the Kalqy app for Windows and Mac here 💻<br><a href='https://kalqy.in/#download' target='_blank' class='action-btn'>Download App</a>",
]
ABOUT_ANSWERS = [
    "Kalqy is a playful, AI-driven learning platform built for children ages 3 to 5! 🎉\nRather than simply tapping on a screen, kids engage by using their entire body—jumping, clapping, balancing, and more. This transforms typical screen time into active learning, supporting physical development, sharper thinking, and stronger social skills through imaginative play. The goal: learning that feels joyful. 🏃‍♂️✨",
    "Kalqy is a playful, AI-powered platform designed to help young children—ages 3 to 5 learn through movement rather than passive screen use. 🎉Kids jump, clap, balance, and move their bodies as part of the experience, turning ordinary screen time into hands-on, active learning. The approach is built to support physical growth, sharper thinking, and social development, all through play and imagination—with joy at the center of it all. 🏃‍♂️✨",
]
FAQS = {
    "how to install": DOWNLOAD_ANSWERS,
    "how can i install kalqi": DOWNLOAD_ANSWERS,
    "where can i download the app": DOWNLOAD_ANSWERS,
    "what is kalqy": ABOUT_ANSWERS,
    "explain kalqi": ABOUT_ANSWERS,
    "how do i contact support": [
        "You can contact support by emailing or contacting us.\n✉️ **Email:** info@kalqy.in \n📱 **Phone:** +91 8943000243"
    ],
}

# --- Crawl sources (previously the URL lists in crawler.py) ---
KNOWLEDGE_SOURCES = [
    ("https://kalqy.in/gallery", "html"),
    ("https://kids-game-mu.vercel.app/", "html"),
    ("https://kalqy.in/", "html"),
    ("https://kalqy.in/games", "recursive_only"),
]

# Params: (slug, name, widget_key, allowed_origins)
UPSERT_CLIENT_QUERY = """
    INSERT INTO clients (slug, name, widget_key, allowed_origins)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug  -- no-op update so RETURNING yields the existing row
    RETURNING id, widget_key
"""

# Creates the "Default" setting with version 1 live, only when the client has no settings yet. Params: dict
INSERT_INITIAL_SETTINGS_QUERY = """
    WITH profile AS (
        INSERT INTO bot_profiles (client_id, name)
        SELECT %(client_id)s, 'Default'
        WHERE NOT EXISTS (SELECT 1 FROM bot_profiles WHERE client_id = %(client_id)s)
        RETURNING id
    )
    INSERT INTO bot_settings
        (client_id, profile_id, version, is_active, bot_name, persona, instructions, do_not_rules, approved_links,
         rag_top_k, model)
    SELECT %(client_id)s, profile.id, 1, true, %(bot_name)s, %(persona)s, %(instructions)s, %(do_not_rules)s,
           %(approved_links)s, %(rag_top_k)s, %(model)s
    FROM profile
"""

# Only fills branding that is still empty. Params: (logo_url, privacy_url, client_id)
FILL_CLIENT_BRANDING_QUERY = """
    UPDATE clients
    SET logo_url = COALESCE(logo_url, %s), privacy_url = COALESCE(privacy_url, %s)
    WHERE id = %s
"""

# Fills the widget content once (while quick_replies is still empty), so later dashboard edits stick.
# Params: (welcome_title, greeting, quick_replies, client_id)
FILL_WIDGET_CONTENT_QUERY = """
    UPDATE clients
    SET welcome_title = %s, greeting = %s, quick_replies = %s
    WHERE id = %s AND quick_replies = '[]'::jsonb
"""

# Sets the FAQ threshold once (while it is still the column default), so later dashboard edits stick.
# Params: (faq_threshold, client_id)
FILL_FAQ_THRESHOLD_QUERY = "UPDATE clients SET faq_threshold = %s WHERE id = %s AND faq_threshold = 0.70"

# An FAQ with one wording, skipped when that wording already exists. Params: dict
INSERT_FAQ_QUERY = """
    WITH faq AS (
        INSERT INTO faqs (client_id, answers)
        SELECT %(client_id)s, %(answers)s
        WHERE NOT EXISTS (SELECT 1 FROM faq_questions WHERE client_id = %(client_id)s AND lower(question) = lower(%(question)s))
        RETURNING id
    )
    INSERT INTO faq_questions (faq_id, client_id, question, embedding)
    SELECT id, %(client_id)s, %(question)s, %(embedding)s FROM faq
"""

# Params: (client_id, url, strategy)
INSERT_SOURCE_QUERY = """
    INSERT INTO knowledge_sources (client_id, url, strategy)
    VALUES (%s, %s, %s)
    ON CONFLICT (client_id, url) DO NOTHING
"""

def main():
    questions = list(FAQS.keys())
    faq_embeddings = get_ov_embedding(questions).numpy()

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        client_id, widget_key = conn.execute(
            UPSERT_CLIENT_QUERY, (CLIENT_SLUG, CLIENT_NAME, secrets.token_urlsafe(16), ALLOWED_ORIGINS)
        ).fetchone()

        conn.execute(INSERT_INITIAL_SETTINGS_QUERY, {
            "client_id": client_id, "bot_name": BOT_NAME, "persona": PERSONA, "instructions": INSTRUCTIONS,
            "do_not_rules": DO_NOT_RULES, "approved_links": Jsonb(APPROVED_LINKS),
            "rag_top_k": RAG_TOP_K, "model": GROQ_MODEL_NAME,
        })
        conn.execute(FILL_FAQ_THRESHOLD_QUERY, (FAQ_THRESHOLD, client_id))
        conn.execute(FILL_CLIENT_BRANDING_QUERY, (LOGO_URL, PRIVACY_URL, client_id))
        conn.execute(FILL_WIDGET_CONTENT_QUERY, (WELCOME_TITLE, GREETING, Jsonb(QUICK_REPLIES), client_id))

        with conn.cursor() as cur:
            cur.executemany(INSERT_FAQ_QUERY, [
                {"client_id": client_id, "question": question, "answers": FAQS[question], "embedding": embedding}
                for question, embedding in zip(questions, faq_embeddings)
            ])
            cur.executemany(INSERT_SOURCE_QUERY, [
                (client_id, url, strategy) for url, strategy in KNOWLEDGE_SOURCES
            ])

    print(f"Seeded client '{CLIENT_SLUG}' (id {client_id}, widget_key {widget_key}).")

if __name__ == "__main__":
    main()
