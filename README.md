# KalqyBot

An embeddable AI chat widget for the Kalqy website. It comes with a manager dashboard for leads, chat history, prompts, FAQs and the knowledge base.

The app is a FastAPI server backed by PostgreSQL with pgvector. Embeddings run locally on OpenVINO, and replies come from the Groq API.

## How a message is answered

Every visitor message is routed through three tiers (see `features/chat_engine.py`):

1. **FAQ match.** The message is embedded and compared against the FAQ wordings in Postgres. If it is close enough, the stored answer is returned straight away and no LLM is called. The match threshold is set on the dashboard's FAQs page.
2. **Generic.** Small talk and generic questions are caught by regex and answered by the LLM without retrieval.
3. **RAG.** The most relevant chunks are retrieved from the crawled website extracts and the manager's notes, then sent to the LLM along with the live prompt setting.

The LLM can tag a reply to show a callback form (purchase or demo interest) or to flag a question it couldn't answer. When a visitor leaves their phone number, managers are alerted live on the dashboard and, if SMTP is set up, by email.

Background loops inside the server:
- **Analysis:** once a chat has been idle for a while, it gets a summary and a hot/warm/cold interest label.
- **Retention:** chats older than the client's retention period are deleted.

## Project layout

```
kalqy_bot/
├── main.py              FastAPI app: widget routes (/, /widget.js, /widget, /chat, /leads, ...)
├── crawler.py           Crawls the client's website into vector chunks (CLI or dashboard)
├── core/                Shared infrastructure
│   ├── db.py            Connection pool, queries, settings cache
│   ├── auth.py          Dashboard login, sessions, password hashing
│   └── embeddings.py    OpenVINO MiniLM embedding model
├── features/            App features
│   ├── chat_engine.py   Tier routing, prompt building, Groq calls
│   ├── leads.py         Callback requests and manager alerts
│   ├── analysis.py      AI summary and interest classification of chats
│   ├── retention.py     Deletes old chats
│   ├── admin.py         Dashboard pages, leads and chat history API
│   └── admin_*.py       Dashboard APIs: overview, prompts, faqs, knowledge, settings
├── migrations/
│   ├── db_setup.sql     One-time Postgres role, database and extension setup
│   ├── migrate.py       Applies versions/*.sql in order, each once
│   └── versions/        Numbered schema migrations
├── scripts/
│   ├── seed.py          Seeds the Kalqy client: settings, FAQs, crawl URLs
│   └── create_admin.py  Creates or resets the dashboard login
├── static/              Widget, dashboard and demo page frontend
└── all-MiniLM-L6-v2-ov-fp16/   Exported embedding model
```

Run every command below from inside `kalqy_bot/`. File paths, and the `python -m` imports, are resolved from the current folder.

## Setup (Linux / macOS)

### Requirements

- Python 3.12 (3.10+ should work)
- PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector) extension installed
- A [Groq API key](https://console.groq.com/)

### 1. Clone and install

```bash
git clone git@github.com:crookedsuiw/kalqiBot.git
cd kalqiBot/kalqy_bot

python -m venv venv
source venv/bin/activate

pip install uv
uv pip install -r requirements.txt
playwright install chromium   # the crawler renders pages in headless Chromium
```

If the `all-MiniLM-L6-v2-ov-fp16/` folder is missing, `core/embeddings.py` exports the model on first start using `optimum-cli`.

### 2. Create the database

Run this once, as a Postgres superuser. It creates the `kalqy` role and database, enables pgvector, and asks you to choose a password for `kalqy`:

```bash
psql -h localhost -U postgres -f migrations/db_setup.sql
```

### 3. Environment variables

```bash
export DATABASE_URL="postgresql://kalqy:<password>@localhost:5432/kalqy"
export GROQ_API_KEY="your-groq-key"
```

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes* | `postgresql://kalqy:kalqy1234@localhost:5432/kalqy` | Postgres connection. *The default only suits a throwaway local database. |
| `GROQ_API_KEY` | yes | — | LLM replies and chat analysis |
| `DEFAULT_CLIENT_SLUG` | no | `kalqy` | Client used for the demo page at `/` |
| `ANALYSIS_MODEL` | no | the client's chat model | Cheaper model for summaries and classification |
| `ANALYSIS_IDLE_MINUTES` | no | `30` | How long a chat must be idle before it is analysed |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | no | port `587` | Lead alert emails. Skipped until set. Port 465 uses SSL; any other port uses STARTTLS. |
| `COOKIE_SECURE` | prod | off | Set to `1` behind HTTPS |

### 4. Migrate, seed, create a login, crawl

```bash
python -m migrations.migrate                                  # apply schema migrations
python -m scripts.seed                                        # seed the Kalqy client (prints its widget_key)
python -m scripts.create_admin --client kalqy --username kalqy   # asks for a password (min 10 chars)
python crawler.py --client kalqy                              # fill the knowledge base
```

All four commands are safe to re-run:
- `migrate` skips migrations that are already applied.
- `seed` never overwrites rows edited on the dashboard.
- `create_admin` resets the password if the username already exists.

You can also start a re-crawl later from the dashboard's Overview page.

### 5. Run

```bash
uvicorn main:app --reload
```

- **http://127.0.0.1:8000/**: a demo page with the widget embedded
- **http://127.0.0.1:8000/admin**: the manager dashboard

## Adding a schema change

Add the next numbered file to `migrations/versions/`, for example `009_something.sql`, then run `python -m migrations.migrate`. Each file runs in its own transaction and is recorded in `schema_migrations`. Never edit a migration that has already been applied; add a new one instead.

## Client onboarding

The project currently runs a single client, Kalqy. The schema is multi-client: every table is scoped by `client_id`, and each client has its own widget key, settings and login. Adding another client is still manual. `scripts/seed.py` is hardcoded for Kalqy.

### Embedding the widget

Add this tag to the client's website:

```html
<script src="https://<your-bot-host>/widget.js" data-key="<widget_key>" async></script>
```

- `widget_key` is printed by `python -m scripts.seed`. You can also look it up with `SELECT widget_key FROM clients WHERE slug = 'kalqy';`.
- Only the launcher button is injected into the host page, inside a shadow root. The chat panel loads in an iframe.
- The iframe only loads on origins listed in the client's `allowed_origins` (scheme and domain, e.g. `https://kalqy.in`). This list is set in `scripts/seed.py`, or with SQL on the `clients` table. It can't be edited from the dashboard.

### Using the dashboard

Log in at `/admin` with the account from `create_admin`. The pages are:

- **Overview:** usage stats, the crawl URL list, and re-crawl.
- **Leads:** callback requests, with live alerts as they come in.
- **Chat history:** every conversation with its AI summary and interest level. Exportable as CSV.
- **Prompt rules:** named prompt settings with version history. Edit a draft, test it, merge it into a new version, then make it live.
- **FAQs:** FAQs that answer instantly at no AI cost. Each has several wordings, rotating answers and an optional button. Includes a match tester and a strictness setting.
- **Knowledge:** browse the crawled extracts, hide junk ones, add your own notes, and test what the bot would read for a question.
- **Settings:** business details, lead alert email, chat retention, password and sessions.

## Production checklist

- Serve over HTTPS and set `COOKIE_SECURE=1`.
- Use a strong Postgres password in `DATABASE_URL`. Don't rely on the default.
- Run **one** uvicorn worker, without `--reload`. Rate limits, login lockouts, live lead alerts and dashboard crawls all live in process memory.
- Set the `SMTP_*` variables if managers should get lead emails.
- Make sure the client's `allowed_origins` matches their live domain exactly.
- Back up Postgres. It holds all settings, FAQs, chats, leads and knowledge chunks.
