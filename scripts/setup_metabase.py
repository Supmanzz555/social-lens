"""Unified Metabase setup — creates a single comprehensive dashboard.

Idempotent — safe to run multiple times. Creates cards with explicit MBQL/SQL queries
that work with Metabase v0.60+. Uses POST /dashboard + PUT to add cards.

Usage:
    python scripts/setup_metabase.py --email admin@example.com --password secret
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:3000/api"


def get_session(email, password):
    data = json.dumps({"username": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{BASE}/session", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["id"]
    except urllib.error.HTTPError as e:
        print(f"ERROR: Failed to authenticate: {e.read().decode()}")
        sys.exit(1)


def api(session, method, path, data=None):
    url = f"{BASE}{path}"
    headers = {"X-Metabase-Session": session, "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"  WARN {e.code} {path}: {e.read().decode()[:150]}")
        return None


def add_database(session, name="analytics_db"):
    existing = api(session, "GET", "/database")
    db_list = existing.get("data", existing) if isinstance(existing, dict) else existing
    for db in db_list:
        if db.get("name") == name:
            print(f"  Database '{name}' already exists (ID: {db['id']})")
            return db["id"]
    result = api(session, "POST", "/database", {
        "name": name, "engine": "postgres",
        "details": {"host": "postgres", "port": 5432, "dbname": "analytics_db",
                    "user": "airflow", "password": "airflow", "ssl": False},
    })
    if result:
        db_id = result.get("id") or result.get("data", {}).get("id")
        print(f"  Added database '{name}' (ID: {db_id})")
        return db_id
    return None


def get_table_id(session, db_id, table_name):
    tables = api(session, "GET", "/table")
    if isinstance(tables, dict):
        tables = tables.get("data", tables)
    for t in tables:
        if t.get("db_id") == db_id and t.get("name") == table_name:
            return t["id"]
    return None


def make_mbql(db_id, source_table, aggregation=None, breakout=None,
              order_by=None, limit=None, filters=None):
    """Build MBQL query using the format Metabase v0.60+ accepts."""
    stages = [{"source-table": source_table, "lib/type": "mbql.stage/mbql"}]
    stage = stages[0]
    if aggregation is not None:
        stage["aggregation"] = aggregation
    if breakout is not None:
        stage["breakout"] = breakout
    if order_by is not None:
        stage["order-by"] = order_by
    if limit is not None:
        stage["limit"] = limit
    if filters is not None:
        stage["filter"] = filters

    return {
        "lib/type": "mbql/query",
        "database": db_id,
        "stages": stages,
    }


def make_sql_card(db_id, query):
    """Build a native SQL query card."""
    return {
        "type": "native",
        "native": {"query": query},
        "database": db_id,
    }


def create_card(session, name, display, dataset_query, viz_settings=None):
    result = api(session, "POST", "/card", {
        "name": name, "display": display,
        "dataset_query": dataset_query,
        "visualization_settings": viz_settings or {},
    })
    if result:
        print(f"  Card {result['id']}: {name}")
        return result["id"]
    print(f"  ERROR: Failed to create card '{name}'")
    return None


def create_mbql_card(session, name, display, db_id, source_table,
                     aggregation=None, breakout=None, order_by=None,
                     limit=None, filters=None):
    return create_card(session, name, display,
        make_mbql(db_id, source_table, aggregation, breakout, order_by, limit, filters))


def create_sql_card(session, name, display, db_id, sql, viz_settings=None):
    return create_card(session, name, display, make_sql_card(db_id, sql), viz_settings)


def create_dashboard_with_cards(session, name, description, cards_info):
    dashcards = []
    for i, (card_id, r, c, sx, sy) in enumerate(cards_info, 1):
        dashcards.append({
            "id": i, "card_id": card_id,
            "row": r, "col": c, "size_x": sx, "size_y": sy,
            "visualization_settings": {},
        })

    result = api(session, "POST", "/dashboard", {"name": name, "description": description})
    if not result:
        return None
    dash_id = result["id"]
    print(f"  Dashboard: {name} (id={dash_id})")

    api(session, "PUT", f"/dashboard/{dash_id}", {"id": dash_id, "dashcards": dashcards})
    print(f"  Added {len(dashcards)} cards to {name}")
    return dash_id


def main():
    parser = argparse.ArgumentParser(description="Setup Metabase dashboard")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    print("=== Metabase Setup ===")
    session = get_session(args.email, args.password)
    print("Authenticated")

    db_id = add_database(session)
    if not db_id:
        print("ERROR: Could not add database")
        sys.exit(1)

    print("  Waiting for table sync...")
    time.sleep(15)

    # Resolve table IDs
    tables = {}
    for tname in ["gold_individual_items", "gold_content_engagement", "gold_creator_metrics",
                  "gold_trending_topics", "fct_daily_engagement", "dim_creators",
                  "dim_platforms", "int_daily_metrics", "ml_predictions",
                  "stg_hackernews__stories", "stg_github__events", "stg_youtube__videos"]:
        tid = get_table_id(session, db_id, tname)
        if tid:
            tables[tname] = tid
            print(f"  Table: {tname} (id={tid})")
        else:
            print(f"  WARN: Table {tname} not found")

    if not tables:
        print("ERROR: No tables found. Run batch_pipeline first.")
        sys.exit(1)

    # ─── Build all cards ───
    print("\nCreating cards...")
    cards = []  # (card_id, row, col, size_x, size_y)

    # === SECTION 1: Pipeline Overview (Row 0-3) ===
    # Total items ingested (stat)
    cid = create_sql_card(session, "Total Items Ingested", "stat", db_id,
        "SELECT COUNT(*) AS total FROM gold_individual_items")
    if cid: cards.append((cid, 0, 0, 4, 4))

    # Items by source (pie) - SQL for reliability
    if "gold_individual_items" in tables:
        cid = create_sql_card(session, "Items by Source", "pie", db_id,
            "SELECT source, COUNT(*) AS cnt FROM gold_individual_items GROUP BY source")
        if cid: cards.append((cid, 0, 4, 4, 4))

    # Data freshness — latest date per source (table)
    cid = create_sql_card(session, "Data Freshness", "table", db_id,
        "SELECT source, MAX(date) AS latest_date, COUNT(*) AS item_count "
        "FROM gold_individual_items GROUP BY source ORDER BY source")
    if cid: cards.append((cid, 0, 8, 8, 4))

    # Pipeline layers row count (table)
    cid = create_sql_card(session, "Pipeline Layer Counts", "table", db_id,
        "SELECT 'gold_individual_items' AS layer, COUNT(*) FROM gold_individual_items "
        "UNION ALL SELECT 'gold_content_engagement', COUNT(*) FROM gold_content_engagement "
        "UNION ALL SELECT 'gold_creator_metrics', COUNT(*) FROM gold_creator_metrics "
        "UNION ALL SELECT 'gold_trending_topics', COUNT(*) FROM gold_trending_topics "
        "UNION ALL SELECT 'fct_daily_engagement', COUNT(*) FROM fct_daily_engagement "
        "UNION ALL SELECT 'dim_creators', COUNT(*) FROM dim_creators "
        "UNION ALL SELECT 'ml_predictions', COUNT(*) FROM ml_predictions "
        "ORDER BY layer")
    if cid: cards.append((cid, 4, 0, 8, 4))

    # Platform summary (table)
    if "dim_platforms" in tables:
        cid = create_mbql_card(session, "Platforms", "table", db_id, tables["dim_platforms"])
        if cid: cards.append((cid, 4, 8, 8, 4))

    # === SECTION 2: Engagement Overview (Row 8-15) ===
    # Daily engagement trend (line) - SQL for reliability
    if "fct_daily_engagement" in tables:
        cid = create_sql_card(session, "Daily Engagement Trend", "line", db_id,
            "SELECT date, SUM(total_items) AS total "
            "FROM fct_daily_engagement "
            "GROUP BY date ORDER BY date")
        if cid: cards.append((cid, 8, 0, 8, 6))

    # Avg score by platform (bar) - SQL for reliability
    if "fct_daily_engagement" in tables:
        cid = create_sql_card(session, "Avg Score by Platform", "bar", db_id,
            "SELECT platform, AVG(avg_score) AS avg_s "
            "FROM fct_daily_engagement "
            "GROUP BY platform ORDER BY avg_s DESC NULLS LAST")
        if cid: cards.append((cid, 8, 8, 8, 6))

    # Top 15 items by score (table) - SQL for reliability
    if "gold_individual_items" in tables:
        cid = create_sql_card(session, "Top 15 Items by Score", "table", db_id,
            "SELECT source, event_type, title, creator, score, views, comments "
            "FROM gold_individual_items "
            "ORDER BY score DESC NULLS LAST LIMIT 15")
        if cid: cards.append((cid, 14, 0, 12, 8))

    # Engagement by type (bar) - SQL for reliability
    if "fct_daily_engagement" in tables:
        cid = create_sql_card(session, "Engagement by Type", "bar", db_id,
            "SELECT type, SUM(total_items) AS total "
            "FROM fct_daily_engagement "
            "GROUP BY type ORDER BY total DESC NULLS LAST")
        if cid: cards.append((cid, 14, 12, 4, 6))

    # === SECTION 3: Platform Deep Dive (Row 22-28) ===
    # Hacker News stats (stat cards)
    if "stg_hackernews__stories" in tables:
        cid = create_sql_card(session, "HN: Total Stories", "stat", db_id,
            "SELECT SUM(total_items) FROM stg_hackernews__stories WHERE platform = 'hackernews'")
        if cid: cards.append((cid, 22, 0, 4, 4))

        cid = create_sql_card(session, "HN: Avg Score", "stat", db_id,
            "SELECT AVG(avg_score) FROM stg_hackernews__stories WHERE platform = 'hackernews'")
        if cid: cards.append((cid, 22, 4, 4, 4))

        cid = create_sql_card(session, "HN: Unique Authors", "stat", db_id,
            "SELECT SUM(unique_actors) FROM stg_hackernews__stories WHERE platform = 'hackernews'")
        if cid: cards.append((cid, 22, 8, 4, 4))

    # GitHub stats
    if "stg_github__events" in tables:
        cid = create_sql_card(session, "GH: Total Events", "stat", db_id,
            "SELECT SUM(total_items) FROM stg_github__events WHERE platform = 'github'")
        if cid: cards.append((cid, 22, 12, 4, 4))

    # YouTube stats
    if "stg_youtube__videos" in tables:
        cid = create_sql_card(session, "YT: Total Videos", "stat", db_id,
            "SELECT SUM(total_items) FROM stg_youtube__videos WHERE platform = 'youtube'")
        if cid: cards.append((cid, 26, 0, 4, 4))

        cid = create_sql_card(session, "YT: Avg Views", "stat", db_id,
            "SELECT AVG(avg_views) FROM stg_youtube__videos WHERE platform = 'youtube'")
        if cid: cards.append((cid, 26, 4, 4, 4))

    # Gold content engagement breakdown (table) - SQL
    if "gold_content_engagement" in tables:
        cid = create_sql_card(session, "Content Engagement Breakdown", "table", db_id,
            "SELECT source, type, total_items, avg_score, max_score, avg_comments, unique_actors "
            "FROM gold_content_engagement ORDER BY date, source")
        if cid: cards.append((cid, 26, 8, 16, 6))

    # === SECTION 4: Trending Topics (Row 32-38) ===
    if "gold_trending_topics" in tables:
        # Top words by frequency (bar) - using SQL to avoid MBQL permission issues
        cid = create_sql_card(session, "Top 20 Words by Frequency", "bar", db_id,
            "SELECT word, SUM(frequency) AS total_freq "
            "FROM gold_trending_topics "
            "GROUP BY word ORDER BY total_freq DESC LIMIT 20")
        if cid: cards.append((cid, 32, 0, 8, 8))

        # Top tags by avg score (table)
        cid = create_sql_card(session, "Top Tags by Avg Score", "table", db_id,
            "SELECT tag, AVG(avg_score) AS avg_s, SUM(frequency) AS total_freq "
            "FROM gold_trending_topics "
            "GROUP BY tag ORDER BY avg_s DESC NULLS LAST LIMIT 15")
        if cid: cards.append((cid, 32, 8, 8, 8))

        # Words by source (bar)
        cid = create_sql_card(session, "Top Words by Source", "bar", db_id,
            "SELECT word, source, SUM(frequency) AS total_freq "
            "FROM gold_trending_topics "
            "GROUP BY word, source ORDER BY total_freq DESC LIMIT 30")
        if cid: cards.append((cid, 40, 0, 16, 8))

    # === SECTION 5: Creator Leaderboard (Row 48-54) ===
    if "dim_creators" in tables:
        # Top 15 creators by avg score (bar) - using SQL
        cid = create_sql_card(session, "Top 15 Creators by Avg Score", "bar", db_id,
            "SELECT creator, AVG(avg_score) AS avg_s "
            "FROM dim_creators "
            "GROUP BY creator ORDER BY avg_s DESC NULLS LAST LIMIT 15")
        if cid: cards.append((cid, 48, 0, 8, 8))

        # Top creators by total views (bar)
        cid = create_sql_card(session, "Top 15 Creators by Views", "bar", db_id,
            "SELECT creator, SUM(total_views) AS total_v "
            "FROM dim_creators "
            "GROUP BY creator ORDER BY total_v DESC NULLS LAST LIMIT 15")
        if cid: cards.append((cid, 48, 8, 8, 8))

        # Creator activity by platform (table) - SQL
        cid = create_sql_card(session, "Creator Activity by Platform", "table", db_id,
            "SELECT creator, platform, post_count, avg_score, max_score, total_views "
            "FROM dim_creators ORDER BY avg_score DESC NULLS LAST LIMIT 20")
        if cid: cards.append((cid, 56, 0, 16, 8))

    # Gold creator metrics detail
    if "gold_creator_metrics" in tables:
        cid = create_sql_card(session, "Creator Metrics Detail", "table", db_id,
            "SELECT creator, source, post_count, avg_score, max_score, total_comments "
            "FROM gold_creator_metrics ORDER BY avg_score DESC NULLS LAST LIMIT 20")
        if cid: cards.append((cid, 64, 0, 16, 8))

    # === SECTION 6: ML Predictions (Row 72-80) ===
    if "ml_predictions" in tables:
        # Predicted vs Actual (scatter) - SQL
        cid = create_sql_card(session, "Predicted vs Actual Score", "scatter", db_id,
            "SELECT predicted_score, actual_score, hour_of_day, day_of_week "
            "FROM ml_predictions LIMIT 100")
        if cid: cards.append((cid, 72, 0, 8, 8))

        # Model stats (stat)
        cid = create_sql_card(session, "ML: Predictions Count", "stat", db_id,
            "SELECT COUNT(*) FROM ml_predictions")
        if cid: cards.append((cid, 72, 8, 4, 4))

        cid = create_sql_card(session, "ML: Avg Predicted", "stat", db_id,
            "SELECT ROUND(AVG(predicted_score), 1) FROM ml_predictions")
        if cid: cards.append((cid, 72, 12, 4, 4))

        cid = create_sql_card(session, "ML: Avg Actual", "stat", db_id,
            "SELECT ROUND(AVG(actual_score), 1) FROM ml_predictions")
        if cid: cards.append((cid, 76, 8, 4, 4))

        cid = create_sql_card(session, "ML: Avg Error", "stat", db_id,
            "SELECT ROUND(AVG(ABS(predicted_score - actual_score)), 1) AS avg_error FROM ml_predictions")
        if cid: cards.append((cid, 76, 12, 4, 4))

        # Predicted score distribution (bar) - SQL
        cid = create_sql_card(session, "Predicted Score Distribution", "bar", db_id,
            "SELECT predicted_score, COUNT(*) AS cnt "
            "FROM ml_predictions "
            "GROUP BY predicted_score ORDER BY predicted_score LIMIT 30")
        if cid: cards.append((cid, 80, 0, 8, 6))

        # Top predictions (table) - SQL
        cid = create_sql_card(session, "Top 15 Highest Predictions", "table", db_id,
            "SELECT * FROM ml_predictions "
            "ORDER BY predicted_score DESC LIMIT 15")
        if cid: cards.append((cid, 80, 8, 8, 6))

    # ─── Create single dashboard ───
    print("\nCreating dashboard...")
    if cards:
        create_dashboard_with_cards(
            session,
            "Social Media Data Platform — Complete Overview",
            "Single-page dashboard covering the entire data pipeline: ingestion, engagement, platforms, trends, creators, and ML predictions.",
            cards
        )

    print("\n=== Setup Complete ===")


if __name__ == "__main__":
    main()
