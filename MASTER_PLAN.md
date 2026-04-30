# Social Media Data Platform — Master Plan

> **Single source of truth** for the entire project. Every component, every decision, every data flow, every phase.

---

## Project Goal

Build a production-grade end-to-end data engineering pipeline that ingests data from Hacker News, GitHub, and YouTube APIs, processes it through streaming and batch layers, stores it in a cloud data lake, transforms it into analytics-ready tables, orchestrates the entire pipeline, validates data quality, builds SQL models, visualizes dashboards, and trains an ML model — all using **free cloud services** with **minimal local resources** (~1.5GB RAM, 2 Docker containers).

This project teaches what a real data engineer does day-to-day.

---

## Key Decisions Made

| Decision | What We Chose | What We Rejected | Why |
|----------|---------------|------------------|-----|
| **Architecture** | Hybrid SaaS (cloud services + local scripts) | Local Docker (8 containers) | Saves ~5GB RAM, uses real cloud tools |
| **Kafka** | Local Kafka (Docker, KRaft) | Upstash, Confluent Cloud | Unlimited, no quotas, full control, no cloud dependency |
| **Data Lake** | Cloudflare R2 | MinIO, AWS S3 | R2 is free forever (10GB), S3-compatible, no egress fees |
| **Warehouse** | Local PostgreSQL (Docker) | Neon, Snowflake | Zero latency, works offline, 200MB RAM, same engine |
| **Orchestration** | Apache Airflow (local Docker) | Prefect, Mage, Luigi | Industry standard, employer expectation, DAG concepts |
| **ML Tracking** | MLflow (local) | Weights & Biases, Neptune | Free, open source, model registry, industry standard |
| **BI** | Metabase (local) | Grafana, Superset | Simple setup, cloud-hosted, connects to Neon |
| **Table Format** | None (raw Parquet) | Delta Lake, Iceberg | Simpler for learning, can add later |
| **Hadoop** | Not included | HDFS, YARN | Spark reads R2 directly via s3a, Hadoop adds no value here |
| **ML Data** | Synthetic first, then real | External dataset | Pipeline generates its own data, more realistic |

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Hacker News API   │    │ GitHub API   │    │ YouTube API  │
│ (No rate limits) │    │ (No rate limits)│    │ (No rate limits)│
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│              Python Producers (local, lightweight)        │
│  Poll APIs, handle pagination/rate limits, push to Kafka │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         Local Kafka (Docker, KRaft mode, unlimited)          │
│  Topics: hackernews-posts | github-events | youtube-videos   │
└───────────────────────────┬─────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
┌──────────────────────┐    ┌──────────────────────────┐
│ PySpark Streaming     │    │ PySpark Batch (local)    │
│ (local machine)       │    │ (local machine)          │
│ Kafka → Cloudflare R2 │    │ R2 bronze→silver→gold    │
└──────────┬───────────┘    └──────────┬───────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│         Cloudflare R2 Data Lake (free, 10GB, cloud)      │
│  bronze/  → raw events, partitioned by date + source     │
│  silver/  → cleaned, deduplicated, typed                 │
│  gold/    → aggregated, business-ready                   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         Neon PostgreSQL (free, 500MB, serverless, cloud) │
│  Curated analytics tables for BI and ML                  │
└───────────────────────────┬─────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
┌──────────────────────┐    ┌──────────────────────┐
│ dbt Core (local CLI)  │    │ MLflow (local)       │
│ SQL transforms        │    │ Train → Register     │
│ staging→marts         │    │ Predict → Neon       │
└──────────────────────┘    └──────────┬───────────┘
                                       │
                  ┌────────────────────┴─────────────────┐
                  ▼                                      ▼
┌──────────────────────────┐              ┌──────────────────────┐
│ Metabase (local) (free)    │              │ Airflow (local Docker)│
│ BI dashboards            │              │ Schedules everything  │
│ Queries Neon directly    │              │ http://localhost:8080 │
└──────────────────────────┘              └──────────────────────┘
```

---

## Data Sources — How They Work

### Hacker News API

| Property | Value |
|----------|-------|
| **Auth** | None required |
| **Rate Limit** | None (Firebase backend) |
| **Endpoints Used** | `/topstories.json`, `/beststories.json`, `/newstories.json`, `/item/{id}.json` |
| **Data Per Request** | Up to 500 item IDs per list, then fetch each item individually |
| **Fields Returned** | `id`, `title`, `type` (story/comment/job/poll/pollopt), `by` (author), `score`, `descendants` (comment count), `time` (Unix timestamp), `url`, `text`, `kids` (comment IDs) |
| **Deduplication** | By `id` — store last processed ID |
| **Polling Strategy** | Every minute (new stories, score changes, comment counts increase) |
| **Data Freshness** | Data changes every minute — new stories, score changes, comment counts increase |
| **Realistic?** | Yes — real stories with real engagement, data changes over time |

**What makes it different each poll:** New stories appear, engagement scores change on existing stories, comment counts increase.

### GitHub API

| Property | Value |
|----------|-------|
| **Auth** | Personal Access Token (PAT) |
| **Rate Limit** | 5,000 requests/hour (authenticated) |
| **Endpoints Used** | `/events`, `/repos/{owner}/{repo}/events`, `/search/repositories` |
| **Data Per Request** | 30 events per page, paginated with `Link` header |
| **Fields Returned** | `id`, `type` (Push, Watch, Fork, PullRequest, Issues), `actor`, `repo`, `created_at`, `payload` |
| **Deduplication** | By `event_id` — each event has a unique ID |
| **Polling Strategy** | Every 15 minutes for public events, hourly for trending repos |
| **Data Freshness** | Events are real-time, continuously generated |
| **Realistic?** | Very — high volume, diverse event types, natural streaming data |

**What makes it different each poll:** Every push, star, fork, PR, and issue creates a new event. Massive volume.

### YouTube API

| Property | Value |
|----------|-------|
| **Auth** | API Key |
| **Rate Limit** | 10,000 units/day (varies by endpoint) |
| **Endpoints Used** | `videos.list` (with chart=mostPopular), `search.list` |
| **Cost Per Request** | `videos.list` = 1 unit, `search.list` = 100 units |
| **Data Per Request** | 50 videos per page, paginated with `nextPageToken` |
| **Fields Returned** | `videoId`, `title`, `channelTitle`, `publishedAt`, `viewCount`, `likeCount`, `commentCount`, `tags`, `categoryId`, `duration` |
| **Deduplication** | By `videoId` |
| **Polling Strategy** | Once per day (quota is tight — 10k units / 100 = 100 searches max) |
| **Data Freshness** | View counts change continuously, new videos daily |
| **Realistic?** | Yes — but quota constraints force batch design, which is realistic |

**What makes it different each poll:** View counts, like counts, comment counts all change. New videos appear daily. Limited quota forces smart batching.

---

## Component Details

### 1. Local Kafka — Event Streaming (Docker, KRaft Mode)

**What it is:** Apache Kafka running in Docker using KRaft mode (no Zookeeper needed). Acts as a message buffer between API producers and Spark consumers.

**What you learn:**
- Topics, partitions, consumer groups, offsets
- Producer configurations (acks, retries, batch size, linger.ms)
- Consumer configurations (auto.offset.reset, group.id, max.poll.records)
- KRaft mode (modern Kafka without Zookeeper)
- Broker configuration and log retention
- Schema design (JSON messages)
- Topic management and partition rebalancing

**Resource usage:** ~512MB RAM, runs in Docker alongside Airflow and Metabase.

**Setup:**
1. Docker Compose starts Kafka automatically with `docker-compose up -d`
2. Topics auto-create when first used (`KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`)
3. Or create manually: `docker exec kafka kafka-topics.sh --create --topic hackernews-posts --bootstrap-server localhost:9092`

**Configuration we'll use:**
```
Topics: 3 (hackernews-posts, github-events, youtube-videos)
Partitions per topic: 3
Replication factor: 1 (single broker, local learning)
Retention: 24 hours
Bootstrap server: localhost:9092
```
```

### 2. PySpark — Distributed Data Processing

**What it is:** Local PySpark that processes data in two modes — streaming (real-time) and batch (scheduled).

**What you learn:**
- Structured Streaming (Kafka source, checkpointing, watermarks)
- DataFrame API (read, transform, write)
- Spark SQL (joins, aggregations, window functions)
- S3 connectors (reading/writing to Cloudflare R2 via s3a://)
- Partitioning strategies
- Parquet file format optimization
- Catalyst optimizer basics

**Why local:** At this data scale (thousands of messages), a cluster is overkill. Same API, same concepts. You can deploy to EMR/Databricks later with minimal changes.

**Key jobs:**
- `kafka_to_r2.py` — Structured Streaming from Kafka to R2 bronze/
- `bronze_to_silver.py` — Clean, deduplicate, type-cast → R2 silver/
- `silver_to_gold.py` — Aggregate, join, model → R2 gold/
- `gold_to_neon.py` — Load gold tables → Neon PostgreSQL

### 3. Cloudflare R2 — Data Lake Storage

**What it is:** S3-compatible object storage. Stores raw and processed data in Parquet format.

**What you learn:**
- Data lake architecture (bronze/silver/gold medallion pattern)
- S3 API compatibility (boto3, s3a:// connector)
- Partitioning strategies (by date, by source)
- Parquet vs CSV vs JSON (why Parquet for analytics)
- File naming conventions (part-XXXXX.parquet)
- Storage optimization (compaction, avoiding small files)

**Free tier:** 10GB storage, **zero egress fees**, free forever. No credit card required (uses Cloudflare account).

**Setup:**
1. Enable R2 in Cloudflare dashboard
2. Create bucket: `data-lake`
3. Create API token with Object Read/Write permissions
4. Note: Access Key ID, Secret Access Key, Account ID

**S3 Endpoint:** `https://{account_id}.r2.cloudflarestorage.com`

### 4. PostgreSQL — Local Data Warehouse

**What it is:** Local PostgreSQL running in Docker. Stores two databases:
- `airflow` — Airflow metadata (DAG runs, connections, users)
- `analytics_db` — Data warehouse for curated analytics tables (gold layer → BI/ML)

**What you learn:**
- Dimensional modeling (star schema, fact/dimension tables)
- Connection strings and connection pooling
- Indexing for analytical queries
- Schema design for BI tools
- Database administration basics (init scripts, roles, permissions)

**Why local over Neon:** Neon has ~200ms RTT latency from Thailand. Local Postgres gives instant queries, works offline, and uses only ~200MB RAM. No sleep/wake latency. Same PostgreSQL engine, same SQL, same dbt compatibility.

**Free tier:** No tier needed — runs in your own Docker container.

**Setup:**
1. Docker Compose starts PostgreSQL automatically with `docker-compose up -d`
2. Init script (`postgres/init.sql`) creates `analytics_db` on first run
3. Both databases use the same credentials: `airflow` / `airflow`

**Connection strings:**
- Metadata: `postgresql://airflow:airflow@localhost:5432/airflow`
- Warehouse: `postgresql://airflow:airflow@localhost:5432/analytics_db`

### 5. Apache Airflow — Workflow Orchestration

**What it is:** The only local Docker service. Runs 2 containers (webserver + scheduler) that orchestrate the entire pipeline.

**What you learn:**
- DAG design (dependencies, scheduling, retries)
- Operators (PythonOperator, BashOperator, SparkSubmitOperator)
- Sensors (waiting for files, time-based triggers)
- XComs (passing data between tasks)
- Connections management (store Kafka, R2, Neon credentials)
- Variables (dynamic configuration)
- Backfilling (running DAGs for past dates)
- Monitoring (task logs, success/failure alerts)

**Why Airflow over Prefect/Mage:**
- Industry standard — what employers expect
- Massive ecosystem of operators
- DAG visualization is excellent for understanding pipeline structure
- Extensive documentation and community

**How it runs:**
- Docker Compose with 3 containers (webserver, scheduler, PostgreSQL for metadata)
- LocalExecutor (parallel task execution, no Celery/Redis needed)
- Metadata DB stored in local PostgreSQL (`postgres:16-alpine`, ~200MB RAM)
- DAGs mounted from local `airflow/dags/` directory

**DAGs we'll build:**
1. `ingest_streaming` — Triggers producers, monitors Kafka, runs Spark streaming
2. `batch_pipeline` — bronze→silver→gold→neon (sequential with dependencies)
3. `data_quality` — Great Expectations validation at layer transitions
4. `ml_pipeline` — Train model → MLflow → Predict → Write to Neon

**Ports:** 8080 (web UI)
**Credentials:** admin / admin

### 6. dbt Core — Data Transformations

**What it is:** SQL-based transformation tool that runs inside Neon PostgreSQL.

**What you learn:**
- Modeling patterns (staging → intermediate → marts)
- Tests (unique, not_null, accepted_values, relationships)
- Macros (reusable SQL snippets)
- Documentation (auto-generated docs site)
- Snapshots (slowly changing dimensions)
- Jinja templating in SQL
- dbt run vs dbt test vs dbt docs

**What it transforms:** The data already loaded into Neon by Spark. Additional SQL-level transforms for BI consumption.

**Run mode:** CLI on your machine, connects to Neon via connection string.

**Models we'll build:**
- `stg_hackernews__stories` — Clean source data from `gold.hackernews_stories`
- `stg_github__events` — Clean source data from `gold.github_events`
- `stg_youtube__videos` — Clean source data from `gold.youtube_videos`
- `int_creator_engagement` — Join creators across all 3 platforms
- `fct_daily_engagement` — Fact table: daily metrics per platform
- `dim_platforms` — Dimension: platform metadata
- `dim_creators` — Dimension: author/channel info

### 7. Great Expectations — Data Quality

**What it is:** Python library that validates data at layer transitions.

**What you learn:**
- Expectation suites (define validation rules)
- Checkpoints (run validations, generate reports)
- Data contracts (what "good" data looks like)
- Validation reports (what passed, what failed)
- Integration with Airflow (quality gates in pipeline)

**Where it validates:**
- Bronze → Silver: Schema validation, no nulls in required fields, date ranges
- Silver → Gold: Referential integrity, value bounds, uniqueness

**Expectations we'll define (example for Hacker News):**
```json
{
  "expect_column_to_exist": ["id", "title", "type", "by", "score", "descendants", "time", "url", "text"],
  "expect_column_values_to_not_be_null": ["id", "title"],
  "expect_column_values_to_be_between": ["score", 0, 100000],
  "expect_column_values_to_be_unique": ["id"],
  "expect_column_values_to_be_of_type": ["time", "INTEGER"],
  "expect_column_values_to_be_in_set": ["type", ["story", "comment", "job", "poll", "pollopt"]]
}
```

### 8. Metabase (local) — Business Intelligence

**What it is:** Cloud-hosted BI tool that connects to Neon PostgreSQL for dashboards.

**What you learn:**
- Connecting BI tools to databases
- Building SQL questions
- Chart types (line, bar, table, funnel, heatmap)
- Dashboard design and layout
- Filters and parameters
- Scheduling reports

**Free tier:** Up to 5 users.

**Dashboards we'll build:**
1. **Engagement Overview** — Daily post volume, avg score, comment trends
2. **Platform Comparison** — Hacker News vs GitHub vs YouTube engagement rates
3. **Trending Topics** — Top keywords, growth over time
4. **Creator Leaderboard** — Top authors/channels by engagement
5. **ML Predictions** — Predicted vs actual engagement scores

### 9. MLflow — Machine Learning Tracking

**What it is:** Local ML experiment tracking server.

**What you learn:**
- Experiments (organize related runs)
- Runs (individual model training executions)
- Parameters (hyperparameters logged per run)
- Metrics (RMSE, MAE, R² tracked per run)
- Artifacts (model files, feature importance plots)
- Model Registry (version models, promote to production)
- MLproject files (reproducible runs)

**ML task:** Predict post engagement (score) from features like:
- Time of day, day of week
- Story type/category
- Title length, word count
- Author posting history
- Number of comments
- Upvote ratio

**Models we'll train:**
1. Linear Regression (baseline)
2. Random Forest (non-linear patterns)
3. XGBoost (best performance)

**Training data strategy:**
1. First: Use `generate_synthetic.py` to create fake data with known patterns
2. Later: Use real pipeline data from `silver/hackernews/`

**MLflow UI:** http://localhost:5000

---

## Complete Data Flow — Step by Step

### The Journey of One Hacker News Story

```
1. Python Producer polls Hacker News API
    GET https://hacker-news.firebaseio.com/v0/topstories.json
    → Returns list of story IDs, then fetch each via /item/{id}.json

2. Producer serializes story to JSON
    {"id": 42345678, "title": "How to learn Spark", "type": "story",
     "by": "alice", "score": 342, "descendants": 45,
     "time": 1714400000, "url": "https://example.com", "text": "..."}

3. Producer pushes to Local Kafka
    Topic: hackernews-posts
    Key: "42345678" (story ID)
    Value: JSON string above

4. PySpark Streaming reads from Kafka
    - Consumes message via Structured Streaming
    - Writes raw JSON as Parquet to R2:
      s3://data-lake/bronze/source=hackernews/date=2026-04-29/part-00001.parquet

5. Airflow triggers bronze_to_silver.py
    - Reads all bronze parquet for today
    - Removes duplicates (by id)
    - Casts types (score → integer, time → timestamp)
    - Handles nulls (text → empty string)
    - Writes to R2 silver:
      s3://data-lake/silver/hackernews/date=2026-04-29/part-00001.parquet

6. Airflow triggers silver_to_gold.py
    - Reads silver data
    - Aggregates: avg score, total comments per day
    - Joins with GitHub and YouTube data for cross-platform metrics
    - Writes to R2 gold:
      s3://data-lake/gold/content_engagement/date=2026-04-29/part-00001.parquet

7. Airflow triggers gold_to_neon.py
    - Reads gold parquet from R2
    - Writes to Neon PostgreSQL table: public.content_engagement

8. dbt transforms inside Neon
    - Runs SQL models: staging → intermediate → marts
    - Creates final analytics tables

9. ML Pipeline runs (scheduled)
    - Reads silver data as training features
    - Trains model, logs to MLflow
    - Registers best model as "production"
    - Scores new stories, writes predictions to Neon

10. Metabase queries Neon
     - Builds charts from final analytics tables
     - Dashboard shows: "Top 10 stories by engagement"
     - Shows predicted vs actual scores from ML model
```

**Same flow for GitHub and YouTube** — separate Kafka topics, separate bronze paths, merge at silver/gold.

---

## Directory Structure — Every File Explained

```
social-media-data-platform/
│
├── .env.example                      # Template for all cloud credentials
│                                     # You copy this to .env and fill in your keys
│
├── .gitignore                        # Ignore .env, __pycache__, logs, etc.
│
├── MASTER_PLAN.md                    # This file — complete project documentation
├── PROJECT_PLAN.md                   # Architecture overview + component descriptions
├── README.md                         # Quick start guide for running the project
│
├── docker-compose.yml                # Docker Compose for Airflow + Metabase (3 containers)
│                                     # Uses Neon as metadata DB (no local Postgres needed)
│
├── journey_log/                      # Every problem, fix, and lesson learned
│                                     # CHECK THIS BEFORE debugging any issue
│
  ├── producers/                        # Kafka producers — poll APIs, push to Kafka
  │   ├── hackernews_producer.py            #   Polls Hacker News Firebase API, no auth needed
  │   │                               #   Pushes JSON messages to kafka topic: hackernews-posts
  │   │                               #   Deduplicates by storing last story ID
│   │
│   ├── github_producer.py            #   Polls GitHub Events API with PAT auth
│   │                               #   Pushes JSON messages to kafka topic: github-events
│   │                               #   Handles rate limiting (5000/hr), Link header pagination
│   │
│   ├── youtube_producer.py           #   Polls YouTube API with API key
│   │                               #   Pushes JSON messages to kafka topic: youtube-videos
│   │                               #   Batch mode (once/day due to quota)
│   │
│
├── spark/                            # PySpark jobs — streaming + batch processing
│   ├── streaming/
│   │   └── kafka_to_r2.py            #   Spark Structured Streaming job
│   │                               #   Reads from Local Kafka (3 topics)
│   │   │                           #   Writes raw Parquet to R2 bronze/
│   │   │                           #   Partitioned by source and date
│   │   │                           #   Checkpointing for fault tolerance
│   │   │
│   │   └── requirements.txt          #   pyspark, kafka-python, boto3
│   │
│   ├── batch/
│   │   ├── bronze_to_silver.py       #   Spark batch: clean bronze data
│   │   │                           #   Remove duplicates, cast types, handle nulls
│   │   │   │                       #   Validate schema, filter invalid records
│   │   │   │                       #   Write to R2 silver/
│   │   │   │
│   │   ├── silver_to_gold.py         #   Spark batch: aggregate silver data
│   │   │                           #   Join across sources (hackernews + github + youtube)
│   │   │   │                       #   Create engagement metrics, creator stats
│   │   │   │                       #   Write to R2 gold/
│   │   │   │
│   │   └── gold_to_neon.py           #   Spark batch: load gold to Neon
│   │                               #   Read gold Parquet from R2
│   │                               #   Write to Neon PostgreSQL tables
│   │                               #   Create tables if not exist
│   │                               #   Upsert strategy (merge on date)
│   │
│   └── requirements.txt              #   pyspark, boto3, delta-spark (if added later)
│
├── airflow/                          # Airflow orchestration
│   ├── dags/
│   │   ├── ingest_streaming.py       #   DAG: triggers producers, monitors Kafka
│   │   │                           #   Schedule: every 30 minutes
│   │   │   │                       #   Tasks: run_hackernews_producer, run_github_producer,
│   │   │   │                       #          run_youtube_producer, check_kafka_lag
│   │   │   │
│   │   ├── batch_pipeline.py         #   DAG: bronze→silver→gold→neon pipeline
│   │   │                           #   Schedule: daily at 2 AM
│   │   │   │                       #   Tasks: bronze_to_silver, silver_to_gold,
│   │   │   │                       #          gold_to_neon (sequential)
│   │   │   │                       #   Each task runs a Spark job
│   │   │   │
│   │   ├── data_quality.py           #   DAG: Great Expectations validation
│   │   │                           #   Schedule: after each batch run
│   │   │   │                       #   Tasks: validate_bronze, validate_silver,
│   │   │   │                       #          validate_gold, send_alerts
│   │   │   │
│   │   └── ml_pipeline.py            #   DAG: ML training and prediction
│   │                               #   Schedule: weekly
│   │                               #   Tasks: generate_features, train_model,
│   │                               #          register_model, predict, write_to_neon
│   │
│   └── plugins/                      #   Custom Airflow operators/hooks
│       └── operators/
│           ├── spark_operator.py     #   Custom operator for local Spark jobs
│           └── kafka_operator.py     #   Custom operator for Kafka producers
│
├── dbt/                              # dbt SQL transformations
│   ├── dbt_project.yml               #   dbt project config
│   ├── profiles.yml                  #   Connection to Neon PostgreSQL
│   ├── models/
│   │   ├── staging/                  #   Raw → cleaned source models
│   │   │   ├── stg_hackernews__stories.sql  #   Select from gold.hackernews_stories, clean columns
│   │   │   ├── stg_github__events.sql #   Select from gold.github_events, parse types
│   │   │   └── stg_youtube__videos.sql#   Select from gold.youtube_videos, format
│   │   │
│   │   ├── intermediate/             #   Business logic joins
│   │   │   ├── int_creator_engagement.sql  #   Join creators across all platforms
│   │   │   └── int_daily_metrics.sql       #   Daily aggregated metrics per platform
│   │   │
│   │   └── marts/                    #   Final analytics tables
│   │       ├── fct_daily_engagement.sql    #   Fact table: daily engagement metrics
│   │       ├── dim_creators.sql            #   Dimension: creator info
│   │       └── dim_platforms.sql           #   Dimension: platform metadata
│   │
│   ├── tests/                        #   Custom dbt tests
│   │   ├── test_positive_scores.sql   #   Ensure engagement scores are never negative
│   │   └── test_valid_dates.sql       #   Ensure dates are within expected range
│   │
│   └── macros/                       #   Reusable SQL macros
│       └── get_platform_name.sql     #   Macro to normalize platform names
│
├── data_quality/                     # Great Expectations
  │   ├── expectations/
  │   │   ├── hackernews_expectations.json  #   Validation rules for Hacker News data
  │   │   │                           #   - id is unique and not null
  │   │   │                           #   - title is not null
  │   │   │                           #   - score >= 0
  │   │   │                           #   - time is valid timestamp (integer)
  │   │   │                           #   - type is in set [story, comment, job, poll, pollopt]
│   │   │
│   │   ├── github_expectations.json  #   Validation rules for GitHub data
│   │   │                           #   - event_id is unique
│   │   │                           #   - event_type in valid set
│   │   │                           #   - created_at is valid timestamp
│   │   │
│   │   └── youtube_expectations.json #   Validation rules for YouTube data
│   │                               #   - video_id is unique
│   │                               #   - view_count >= 0
│   │                               #   - published_at is valid timestamp
│   │
│   └── checkpoints/
│       └── bronze_to_silver.json     #   Checkpoint: validate before silver write
│                                   #   Runs all expectations, fails if any critical fail
│
├── ml/                               # ML model training & inference
│   ├── generate_synthetic.py         #   Generate fake Hacker News data with known patterns
│   │                               #   Features: hour, day_of_week, title_length,
│   │   │                           #   word_count, story_type
│   │   │                           #   Target: score (generated with known formula)
│   │   │                           #   Output: CSV for training
│   │   │
│   ├── train_model.py                #   Train engagement prediction models
│   │                               #   Models: LinearRegression, RandomForest, XGBoost
│   │   │                           #   Logs to MLflow: params, metrics, artifacts
│   │   │                           #   Registers best model in MLflow registry
│   │   │
│   ├── predict.py                    #   Score new posts with registered model
│   │                               #   Loads production model from MLflow
│   │   │                           #   Predicts engagement for new silver data
│   │   │                           #   Writes predictions to Neon
│   │   │
│   └── requirements.txt              #   mlflow, scikit-learn, xgboost, pandas
│
├── configs/                          # Shared configuration
│   ├── kafka_topics.json             #   Topic definitions, partitions, retention
│   │                               #   {
│   │   │                               "hackernews-posts": {"partitions": 3, "retention_ms": 86400000},
│   │   │                               "github-events": {"partitions": 3, "retention_ms": 86400000},
│   │   │                               "youtube-videos": {"partitions": 1, "retention_ms": 86400000}
│   │   │                           #   }
│   │   │
│   └── spark_config.py               #   Spark session configuration
│                                   #   S3 endpoint (R2), credentials, parallelism
│
└── dashboards/                       # Metabase exports
    └── engagement_dashboard.json     #   Exported dashboard configuration
                                    #   Can be imported into Metabase (local)
```

---

## Resource Requirements

| Resource | Required | Notes |
|----------|----------|-------|
| **RAM** | 2-2.5GB | Kafka (512MB) + Postgres (200MB) + Airflow (1GB) + Metabase (512MB) + MLflow (256MB) |
| **Disk** | ~5GB | Docker images (~4GB) + project files (~1GB) |
| **CPU** | 2 cores | Spark local mode, PySpark jobs |
| **Internet** | Required | All cloud services, API calls |
| **Python** | 3.10+ | All scripts use modern Python |
| **Docker** | Required | For Kafka, Postgres, Airflow (2), Metabase |
| **Docker Compose** | Required | Start 5 containers |

**No heavy local infrastructure.** 5 Docker containers (Kafka, PostgreSQL, Airflow webserver, Airflow scheduler, Metabase). MLflow runs locally as a Python process. Everything else is cloud-hosted.

---

## Setup Checklist — Step by Step

### Step 1: Create Cloud Accounts (5 min each)

#### 1.1 Cloudflare R2
- [ ] Sign up: https://dash.cloudflare.com
- [ ] Enable R2 in sidebar
- [ ] Create bucket: `data-lake`
- [ ] Create API token with Object Read/Write
- [ ] Copy: Account ID, Access Key ID, Secret Access Key

#### 1.2 PostgreSQL (Local Docker)
- [ ] Docker Compose creates it automatically with `docker compose up -d`
- [ ] Init script creates two databases: `airflow` (metadata) and `analytics_db` (warehouse)
- [ ] Credentials: `airflow` / `airflow`

#### 1.3 API Keys (Data Sources)
- [ ] Hacker News: https://hacker-news.firebaseio.com/v0/ — No API key needed
- [ ] GitHub: https://github.com/settings/tokens → Generate token → Copy token
- [ ] YouTube: https://console.cloud.google.com/apis → Enable YouTube Data API v3 → Create API key

### Step 2: Configure Project

```bash
# Clone / navigate to project
cd social-media-data-platform

# Copy env template
cp .env.example .env

# Edit .env with your credentials (use any editor)
# KAFKA_BOOTSTRAP_SERVERS=pk://...
# KAFKA_API_KEY=...
# R2_ACCOUNT_ID=...
# NEON_CONNECTION_STRING=postgresql://...
# Hacker News needs no API key
```

### Step 3: Start Docker Containers

```bash
# Start all containers (Kafka, Postgres, Airflow x2, Metabase)
docker-compose up -d

# Wait ~2 minutes for initialization
# Airflow UI: http://localhost:8080 (admin / admin)
# Metabase UI: http://localhost:3000 (setup on first visit)
```

### Step 4: Install Python Dependencies

```bash
# Create virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install all dependencies
uv pip install -r producers/requirements.txt
uv pip install -r spark/requirements.txt
uv pip install -r ml/requirements.txt
uv pip install apache-airflow great-expectations dbt-postgres
```

### Step 5: Start MLflow

```bash
bash scripts/start_mlflow.sh
# Access UI at: http://localhost:5000
```

### Step 6: Verify All Connections

```bash
# Run automated verification
bash scripts/verify_phase1.sh
# Expected: 15 passed, 0 failed
```
python -c "import psycopg2; print('Neon OK')"

# Test Airflow + Metabase
curl -s http://localhost:8080/health
# Should return: {"status": "healthy"}
curl -s http://localhost:3000/api/health
# Should return: {"status": "ok"}
```

### Step 6: Start MLflow Server

```bash
mlflow server --host 0.0.0.0 --port 5000 &
# Access UI at: http://localhost:5000
```

---

## Build Phases — What Happens in Each

### Phase 1: Cloud Setup + Airflow Docker
**Goal:** All services are running and accessible
**Deliverables:**
- Cloud accounts created
- `.env` file configured
- Airflow Docker containers running
- All connection tests pass
**Time:** ~30 minutes
**Dependencies:** None

**✅ Verification Steps (must pass before Phase 2):**
```bash
# 1. Airflow is healthy
curl -s http://localhost:8080/health | grep '"status": "healthy"'
# Expected: {"status": "healthy"}

# 2. Kafka connection works (local Docker)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092
# Expected: hackernews-posts, github-events, youtube-videos — no connection errors

# 3. Kafka health check passes
docker exec kafka /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 2>/dev/null | head -1
# Expected: kafka:9092 (id: 1 rack: null) -> (...

# 3. R2 connection works
python -c "
import boto3, os
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com')
buckets = s3.list_buckets()['Buckets']
print('R2:', [b['Name'] for b in buckets])
"
# Expected: R2: ['data-lake']

# 4. Neon connection works
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('NEON_CONNECTION_STRING'))
cur = conn.cursor()
cur.execute('SELECT version()')
print('Neon:', cur.fetchone()[0][:30])
conn.close()
"
# Expected: Neon: PostgreSQL 16.x...

# 5. MLflow server responds
curl -s http://localhost:5000/api/2.0/mlflow/experiments/list | grep '"experiments"'
# Expected: {"experiments": []} or similar JSON
```
**🛑 Do not proceed until all 5 tests pass.**

### Phase 2: Kafka Producers
**Goal:** 3 Python scripts poll APIs and push messages to Kafka
**Deliverables:**
- `hackernews_producer.py` — polls Hacker News, pushes to `hackernews-posts`
- `github_producer.py` — polls GitHub, pushes to `github-events`
- `youtube_producer.py` — polls YouTube, pushes to `youtube-videos`
- Each handles: auth, pagination, rate limiting, deduplication, error handling
**Time:** ~2 hours
**Dependencies:** Phase 1

**✅ Verification Steps (must pass before Phase 3):**
```bash
# 1. Run Hacker News producer (10 posts)
python producers/hackernews_producer.py --limit 10
# Expected: "Sent 10 messages to hackernews-posts" with no errors

# 2. Run GitHub producer (10 events)
python producers/github_producer.py --limit 10
# Expected: "Sent 10 messages to github-events" with no errors

# 3. Run YouTube producer (5 videos)
python producers/youtube_producer.py --limit 5
# Expected: "Sent 5 messages to youtube-videos" with no errors

# 4. Verify messages exist in Local Kafka UI
# Go to https://N/A (runs locally) → Kafka → Topics → hackernews-posts → Browse
# Expected: See JSON messages with post data

# 5. Verify message count matches
python -c "
from kafka import KafkaConsumer, TopicPartition
import os
consumer = KafkaConsumer(bootstrap_servers='localhost:9092',
                         group_id='verify-test',
                         auto_offset_reset='earliest',
                         consumer_timeout_ms=5000)
tp = TopicPartition('hackernews-posts', 0)
consumer.assign([tp])
end = consumer.end_offsets([tp])[tp]
print(f'hackernews-posts total messages: {end}')
"
# Expected: Number matches what producer sent
```
**🛑 Do not proceed until messages are confirmed in Kafka.**

### Phase 3: PySpark Streaming
**Goal:** Spark consumes Kafka messages, writes Parquet to R2 bronze/
**Deliverables:**
- `kafka_to_r2.py` — Structured Streaming job
- Reads from 3 Kafka topics simultaneously
- Writes partitioned Parquet to R2: `bronze/source=X/date=Y/part-*.parquet`
- Checkpointing for fault tolerance
- Watermarks for late data handling
**Time:** ~2 hours
**Dependencies:** Phase 1, Phase 2 (messages in Kafka)

**✅ Verification Steps (must pass before Phase 4):**
```bash
# 1. Run streaming job (run for 30 seconds, then stop with Ctrl+C)
python spark/streaming/kafka_to_r2.py
# Expected: Spark starts, shows "Read batch X", writes files, no errors

# 2. Check R2 for bronze files
python -c "
import boto3, os
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
prefix = 'bronze/'
bucket = os.getenv('R2_BUCKET_NAME', 'datalake')
objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
for o in objs.get('Contents', []):
    print(f'  {o[\"Key\"]} ({o[\"Size\"]} bytes)')
"
# Expected: Files like bronze/source=hackernews/date=2026-04-29/part-00001.parquet

# 3. Read a parquet file locally to verify schema
python -c "
import boto3, io, os, pyarrow.parquet as pq
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))
bucket = os.getenv('R2_BUCKET_NAME', 'datalake')
# Pick first hackernews file
objs = s3.list_objects_v2(Bucket=bucket, Prefix='bronze/source=hackernews/')
key = objs['Contents'][0]['Key']
data = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
table = pq.read_table(io.BytesIO(data))
print(f'Rows: {table.num_rows}')
print(f'Columns: {table.column_names}')
"
# Expected: Rows > 0, Columns include id, title, score, created_utc, etc.
```
**🛑 Do not proceed until parquet files exist in R2 bronze/ with correct schema.**

### Phase 4: PySpark Batch
**Goal:** Three batch jobs transform data through the layers
**Deliverables:**
- `bronze_to_silver.py` — Clean, deduplicate, type-cast
- `silver_to_gold.py` — Aggregate, join, create business metrics
- `gold_to_neon.py` — Load gold tables to Neon PostgreSQL
- Each job reads from R2, writes to R2/Neon
- Partition-aware, handles incremental data
**Time:** ~3 hours
**Dependencies:** Phase 3 (bronze data exists in R2)

**✅ Verification Steps (must pass before Phase 5):**
```bash
# 1. Run bronze → silver
python spark/batch/bronze_to_silver.py
# Expected: "Wrote X rows to silver/" with no errors

# 2. Verify silver data is clean (no nulls in key columns, correct types)
python -c "
import boto3, io, os, pyarrow.parquet as pq
s3 = boto3.client('s3', endpoint_url=f'https://{os.getenv(\"R2_ACCOUNT_ID\")}.r2.cloudflarestorage.com')
objs = s3.list_objects_v2(Bucket='data-lake', Prefix='silver/hackernews/')
key = objs['Contents'][0]['Key']
data = s3.get_object(Bucket='data-lake', Key=key)['Body'].read()
table = pq.read_table(io.BytesIO(data))
print(f'Silver rows: {table.num_rows}')
print(f'Nulls in id: {table.column(\"id\").null_count}')
print(f'Nulls in title: {table.column(\"title\").null_count}')
"
# Expected: null_count = 0 for key columns

# 3. Run silver → gold
python spark/batch/silver_to_gold.py
# Expected: "Wrote X rows to gold/" with no errors

# 4. Run gold → Neon
python spark/batch/gold_to_neon.py
# Expected: "Loaded X rows to Neon" with no errors

# 5. Verify data in Neon
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('NEON_CONNECTION_STRING'))
cur = conn.cursor()
cur.execute('SELECT count(*) FROM content_engagement')
print(f'content_engagement rows: {cur.fetchone()[0]}')
cur.execute('SELECT count(*) FROM creator_metrics')
print(f'creator_metrics rows: {cur.fetchone()[0]}')
cur.execute('SELECT count(*) FROM trending_topics')
print(f'trending_topics rows: {cur.fetchone()[0]}')
conn.close()
"
# Expected: All counts > 0
```
**🛑 Do not proceed until Neon tables have data and counts match expectations.**

### Phase 5: Airflow DAGs
**Goal:** All pipeline stages orchestrated by Airflow
**Deliverables:**
- `ingest_streaming.py` — DAG that triggers producers, monitors Kafka
- `batch_pipeline.py` — DAG that runs batch jobs in sequence
- `data_quality.py` — DAG that runs Great Expectations checks
- `ml_pipeline.py` — DAG that trains ML model, predicts
- All DAGs have: schedules, retries, alerts, proper dependencies
**Time:** ~2 hours
**Dependencies:** Phases 2-4 (scripts work independently)

**✅ Verification Steps (must pass before Phase 6):**
```bash
# 1. Check DAGs appear in Airflow UI
# Go to http://localhost:8080 → DAGs page
# Expected: 4 DAGs visible (ingest_streaming, batch_pipeline, data_quality, ml_pipeline)

# 2. Trigger batch_pipeline manually
# Click batch_pipeline → Trigger DAG → Wait for completion
# Expected: All tasks green, no failures

# 3. Check task logs
# Click any task → Logs tab
# Expected: Clean logs, no stack traces, "Task completed successfully"

# 4. Verify DAG runs on schedule
# Wait for scheduled run time (or set to @once for testing)
# Expected: DAG triggers automatically
```
**🛑 Do not proceed until at least one full DAG run completes with all tasks green.**

### Phase 6: Data Quality
**Goal:** Great Expectations validates data at layer transitions
**Deliverables:**
- Expectation suites for Hacker News, GitHub, YouTube data
- Checkpoints that run after bronze→silver transformation
- Validation reports generated per run
- Airflow integration (quality gate in batch_pipeline DAG)
**Time:** ~1.5 hours
**Dependencies:** Phase 4 (silver data exists)

**✅ Verification Steps (must pass before Phase 7):**
```bash
# 1. Run expectations on good data
python -c "
import great_expectations as gx
context = gx.get_context()
results = context.run_checkpoint(checkpoint_name='bronze_to_silver')
print(f'Validation result: {results[\"success\"]}')
"
# Expected: Validation result: True (all expectations pass)

# 2. Run expectations on intentionally bad data (inject a null id)
# Modify a silver parquet file to add a row with null id
# Run checkpoint again
# Expected: Validation result: False (catches the bad data)

# 3. Verify validation report exists
# Check great_expectations/uncommitted/validations/ directory
# Expected: JSON report files with timestamps
```
**🛑 Do not proceed until validation passes on good data and fails on bad data.**

### Phase 7: dbt Models
**Goal:** SQL transformations create final analytics tables in Neon
**Deliverables:**
- `dbt_project.yml` configured for Neon
- Staging models (clean source data)
- Intermediate models (business logic joins)
- Mart models (final analytics tables)
- Tests (uniqueness, not_null, accepted_values)
- dbt documentation site generated
**Time:** ~2 hours
**Dependencies:** Phase 4 (data in Neon)

**✅ Verification Steps (must pass before Phase 8):**
```bash
# 1. Run dbt models
cd dbt && dbt run
# Expected: All models pass with "OK" status, no errors

# 2. Run dbt tests
dbt test
# Expected: All tests pass, no failures

# 3. Verify tables exist in Neon
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('NEON_CONNECTION_STRING'))
cur = conn.cursor()
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'fct_%' OR table_name LIKE 'dim_%'\")
for row in cur.fetchall():
    print(row[0])
conn.close()
"
# Expected: fct_daily_engagement, dim_creators, dim_platforms

# 4. Generate dbt docs
dbt docs generate
# Expected: target/index.html created
```
**🛑 Do not proceed until `dbt run && dbt test` both pass with zero failures.**

### Phase 8: Metabase Dashboards
**Goal:** BI dashboards visualize the analytics
**Deliverables:**
- Metabase connected to Neon
- 5 dashboards: Engagement Overview, Platform Comparison, Trending Topics, Creator Leaderboard, ML Predictions
- Each dashboard has 3-5 charts
- Filters and date ranges configured
**Time:** ~1 hour
**Dependencies:** Phase 7 (analytics tables in Neon)

**✅ Verification Steps (must pass before Phase 9):**
```bash
# 1. Verify Metabase connects to Neon
# Go to https://localhost:3000 → Admin → Databases
# Expected: Neon PostgreSQL connected, sync successful

# 2. Verify charts render
# Open each dashboard
# Expected: Charts show data (not "No results" or errors)

# 3. Verify filters work
# Change date range filter on Engagement Overview
# Expected: All charts update with filtered data

# 4. Verify ML Predictions dashboard shows predicted vs actual
# Expected: Scatter plot or table with both columns populated
```
**🛑 Do not proceed until all 5 dashboards render with real data.**

### Phase 9: ML Pipeline
**Goal:** MLflow tracks experiments, model predicts engagement
**Deliverables:**
- `generate_synthetic.py` — fake data with known patterns
- `train_model.py` — trains 3 models, logs to MLflow, registers best
- `predict.py` — scores new posts with production model
- `ml_pipeline.py` — Airflow DAG for weekly training
- MLflow UI shows experiments, runs, metrics, artifacts
- Predictions written to Neon, visualized in Metabase
**Time:** ~2 hours
**Dependencies:** Phase 4 (silver data), Phase 8 (Metabase running)

**✅ Verification Steps (final project check):**
```bash
# 1. Generate synthetic data
python ml/generate_synthetic.py
# Expected: "Generated 1000 rows, saved to ml/data/synthetic.csv"

# 2. Train models
python ml/train_model.py
# Expected: "Logged 3 runs to MLflow. Best model: XGBoost (R²=0.xx)"

# 3. Check MLflow UI
# Go to http://localhost:5000 → Experiments → engagement-predictor
# Expected: 3 runs visible, metrics (RMSE, MAE, R²) logged, artifacts present

# 4. Register best model
# In MLflow UI, click "Register Model" on best run
# Expected: Model version 1 created in registry

# 5. Run predictions
python ml/predict.py
# Expected: "Scored 100 posts. Predictions written to Neon."

# 6. Verify predictions in Neon
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('NEON_CONNECTION_STRING'))
cur = conn.cursor()
cur.execute('SELECT count(*), avg(predicted_score), avg(actual_score) FROM ml_predictions')
print(f'Predictions: {cur.fetchone()}')
conn.close()
"
# Expected: count > 0, both averages are reasonable numbers

# 7. Trigger ML DAG in Airflow
# Go to http://localhost:8080 → ml_pipeline → Trigger DAG
# Expected: All tasks green

# 8. Check Metabase ML Predictions dashboard
# Expected: Chart shows predicted vs actual scores
```
**✅ All phases complete. Project is production-ready.**

---

## What the Finished Project Looks Like

When everything is built and running:

**You see:**
1. **Airflow UI** (http://localhost:8080) — Green DAGs running on schedule, showing pipeline health
2. **MLflow UI** (http://localhost:5000) — Experiment runs with metrics, best model registered as "production"
3. **Metabase** (https://localhost:3000) — Dashboards with real data from all 3 platforms
4. **R2 Console** — Parquet files organized in bronze/silver/gold folders
5. **Neon Console** — Analytics tables populated, dbt models materialized
6. **Local Kafka Console** — Kafka topics with messages flowing in
7. **Terminal** — PySpark jobs completing successfully

**The pipeline runs automatically:**
- Every 30 minutes: Producers poll APIs, messages flow through Kafka
- Every hour: Spark streaming writes new data to bronze
- Daily at 2 AM: Batch pipeline transforms bronze→silver→gold→Neon
- After batch: Data quality validates, dbt transforms, ML predicts
- Weekly: ML model retrains with new data

**You can:**
- Trigger any DAG manually in Airflow
- View data in R2 console at any layer
- Query Neon directly with SQL
- Add new charts to Metabase
- Compare model experiments in MLflow
- See data lineage in dbt docs

---

## Common Pitfalls & How to Avoid Them

| Pitfall | How to Avoid |
|---------|-------------|
| Kafka connection fails | Check bootstrap server URL, API key/secret, firewall |
| R2 write fails | Verify S3 endpoint URL format: `https://{account_id}.r2.cloudflarestorage.com` |
| Spark can't read from Kafka | Ensure Kafka package is included in Spark submit (`--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1`) |
| Airflow DAG not showing | DAG file must be in `airflow/dags/`, have `default_args` and `DAG` object at top level |
| dbt can't connect to Neon | Connection string must include database name, use `dbt-postgres` adapter |
| MLflow artifacts not saving | Check `MLFLOW_TRACKING_URI` environment variable points to local server |

**Before troubleshooting any new issue, check `journey_log/` first** — we may have already solved it.
| YouTube API quota exceeded | Reduce polling frequency, batch requests, use `videos.list` (1 unit) not `search.list` (100 units) |
| Spark OOM error | Reduce `spark.driver.memory`, process data in smaller date ranges |
| Duplicate data in Kafka | Ensure producer deduplicates by ID before sending |
| Neon connection timeout | Neon scales to zero — first query takes 2-3 seconds to wake up |

---

## Future Enhancements (Optional)

After completing all 9 phases, you could add:

- **Delta Lake** on top of R2 for ACID transactions and time travel
- **Grafana + Prometheus** for infrastructure monitoring (Kafka lag, Spark metrics, Airflow task duration)
- **CI/CD** with GitHub Actions for automated testing of DAGs, dbt models, Spark jobs
- **Alerting** via Slack/PagerDuty when pipeline fails or data quality checks fail
- **Additional data sources** (Twitter/X API, Spotify API, weather data)
- **Real-time dashboard** using WebSockets or streaming to Metabase
- **Model monitoring** — track prediction drift over time
- **Data catalog** — OpenMetadata or DataHub for metadata management
- **Spark cluster** — Deploy to AWS EMR or Databricks for production scale

---

## Quick Reference — Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Local Kafka | Docker container | N/A (runs locally) |
| Cloudflare R2 Console | https://dash.cloudflare.com → R2 | Your Cloudflare account |
| Neon Console | https://console.neon.tech | Your email + password |
| Airflow UI | http://localhost:8080 | admin / admin |
| Metabase | http://localhost:3000 | Setup on first visit |
| MLflow UI | http://localhost:5000 | No auth needed |
| Kafka Bootstrap | `localhost:9092` | No auth needed (PLAINTEXT) |
| R2 S3 Endpoint | `https://{account_id}.r2.cloudflarestorage.com` | From R2 settings |
| Neon Connection | `postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/db` | From project dashboard |

---

## Summary

**What this project is:** A complete data engineering pipeline that simulates a real production environment using free cloud services.

**What it teaches you:** Everything a data engineer does — API integration, streaming, batch processing, data lakes, data warehouses, orchestration, data quality, SQL modeling, BI visualization, and ML tracking.

**What it costs:** $0. All services are free tier.

**What resources it needs:** ~3GB RAM, 4 Docker containers (Kafka, Airflow webserver, scheduler, Metabase), Python 3.10+.

**How long it takes:** ~15-18 hours total across 9 phases.

**What you'll have at the end:** A portfolio-worthy project that demonstrates production data engineering skills.
