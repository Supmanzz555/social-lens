# AGENT INSTRUCTIONS

> **Read this file first. Always.** Every time you work on this project, these rules apply.

---

## Rule 1: MASTER_PLAN.md is the Single Source of Truth

Before doing ANYTHING, read `MASTER_PLAN.md` in full. It contains:
- The complete architecture and data flow
- Every component and what it does
- The exact directory structure and purpose of every file
- All build phases (1-9) with deliverables, dependencies, and verification steps
- Setup checklist and cloud service details
- API rate limits, data fields, and deduplication strategies
- Common pitfalls and troubleshooting
- Every design decision we made and why

**Do not invent new tools, services, or approaches.** If the plan says use X, use X. If you think Y would be better, ask the user first — do not switch on your own.

---

## Rule 2: PROJECT_PLAN.md is the Quick Reference

If you need a shorter summary of the architecture and components, read `PROJECT_PLAN.md`. It's a condensed version of MASTER_PLAN.md.

---

## Rule 3: Check Existing Files Before Creating New Ones

Before writing any code:
1. Check if the file already exists in the project structure
2. Read its current contents
3. Follow the patterns and conventions already established
4. Import from the config modules in `configs/` (e.g., `configs/spark_config.py`, `configs/r2_config.py`)

**Do not create new files** unless the phase explicitly calls for them in MASTER_PLAN.md.

---

## Rule 4: Verify at Each Phase

Every phase in MASTER_PLAN.md has a "✅ Verification Steps" section.
- After completing a phase, run ALL verification steps
- Do not proceed to the next phase until all checks pass
- If a check fails, fix it before moving on
- Do NOT skip verification or say "we'll fix it later"

---

## Rule 5: Credentials and .env

- The `.env` file contains real credentials. **NEVER commit it to git.**
- The `.gitignore` already excludes `.env`.
- When you need env vars, load them with `from dotenv import load_dotenv; load_dotenv()`
- Reference `.env.example` for the expected variable names

---

## Rule 6: What Runs Where

| Service | Where | How |
|---------|-------|-----|
| Kafka | Docker container | `docker-compose up -d` |
| Airflow | Docker containers (webserver + scheduler) | `docker-compose up -d` |
| PostgreSQL | Docker container (Airflow metadata only) | `docker-compose up -d` |
| Metabase | Docker container | `docker-compose up -d` |
| PySpark | Local machine (not Docker) | `uv run python spark/...` |
| Python producers | Local machine | `python producers/...` |
| dbt | Local machine CLI | `cd dbt && dbt run` |
| MLflow | Local machine | `bash scripts/start_mlflow.sh` |
| Great Expectations | Local machine | Python library, triggered via Airflow |

**Total containers: 5** (Kafka, Postgres, Airflow webserver, Airflow scheduler, Metabase)
**Total RAM: ~2-2.5GB**

---

## Rule 7: Cloud Services Are Free Tier Only

The project uses these cloud services — all free tier:
- **Cloudflare R2** — 10GB storage, free forever

**Neon PostgreSQL is NOT used.** The data warehouse runs on local PostgreSQL (`analytics_db`). The Neon credentials in `.env` are preserved in case you want to switch later.

Do not suggest paid services or suggest migrating to paid tiers unless the user explicitly asks.

---

## Rule 8: Data Sources

| Source | Auth | Rate Limit | Producer File |
|--------|------|------------|---------------|
| Hacker News | None | Unlimited | `producers/hackernews_producer.py` |
| GitHub | PAT token | 5,000 req/hr | `producers/github_producer.py` |
| YouTube | API key | 10,000 units/day | `producers/youtube_producer.py` |

---

## Rule 9: Build Phases Are Sequential

```
Phase 1: Cloud setup + Docker (Kafka, Airflow, Metabase)
Phase 2: Kafka Producers (HN, GitHub, YouTube → Kafka)
Phase 3: PySpark Streaming (Kafka → R2 bronze)
Phase 4: PySpark Batch (bronze → silver → gold → Neon)
Phase 5: Airflow DAGs (orchestrate everything)
Phase 6: Data Quality (Great Expectations)
Phase 7: dbt Models (SQL transforms on Neon)
Phase 8: Metabase Dashboards (BI visualization)
Phase 9: ML Pipeline (MLflow — synthetic first, then real data)
```

Do not jump ahead. Each phase depends on the previous one.

---

## Rule 10: Log Every Problem in journey_log

**Always.** Every time you encounter an error, fix something, make a design change, or hit a dead end:

1. Check if `journey_log/YYYY-MM-DD.md` exists for today. If not, create it
2. Append an entry with:
   - **Issue number**: sequential for the day
   - **Problem**: what happened, what error message, what failed
   - **Root cause**: why it happened
   - **Fix**: what you changed (file paths, commands, config values)
   - **Key takeaway**: lesson learned so it's not repeated
3. Update `journey_log/README.md` index if adding a new day's file
4. **Never delete entries** — even "obvious" mistakes are valuable

Before trying to fix a problem, **check journey_log first** — we may have already solved it.

---

## Rule 11: Python Environment — Always Use UV

**Never use system Python directly.** Never use `pip3 install --break-system-packages`. Never rely on manual `python -m venv`.

### How to run any Python code outside Docker:

1. **Check if a project `.venv` exists** (created via `uv venv`)
2. If not, create it in the project root:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   uv pip install <packages>
   # or use a requirements file:
   uv pip install -r <path>/requirements.txt
   ```
4. Run scripts within the activated env:
   ```bash
   uv run python script.py
   # or activate then run:
   source .venv/bin/activate
   python script.py
   ```

### Why UV:
- Isolated from system Python (no `PEP 668` errors)
- Much faster than pip + venv
- Deterministic lockfiles (`uv.lock`)
- Handles Python versions automatically

**Rule: If you need to run a Python one-liner for verification, use `uv run python -c "..."` inside the project directory.**

---

## Rule 12: When in Doubt, Ask

If you're unsure about:
- A design decision
- Which tool to use
- How to handle an error
- Whether to add something not in the plan

**Ask the user.** Do not guess or improvise.

---

## File Locations Quick Reference

```
MASTER_PLAN.md          → Complete project documentation (READ THIS FIRST)
PROJECT_PLAN.md         → Architecture overview (quick reference)
AGENT.md                → Agent rules and conventions (READ THIS FIRST)
README.md               → Quick start guide
.env                    → Real credentials (NEVER commit)
.env.example            → Template for credentials
docker-compose.yml      → 5 containers: Kafka, Postgres, Airflow x2, Metabase
journey_log/            → Every problem, fix, and lesson learned (CHECK BEFORE debugging)
scripts/                → Utility scripts (start_mlflow, verify_phase1, etc.)
configs/                → Shared config modules (Spark, R2)
producers/              → Kafka producer scripts
spark/                  → PySpark streaming and batch jobs
airflow/                → Airflow DAGs, plugins, data (SQLite was replaced by Postgres)
dbt/                    → dbt SQL models
data_quality/           → Great Expectations configs
ml/                     → MLflow training and prediction
dashboards/             → Metabase exports
```
