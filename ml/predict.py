"""Score new posts with the production model from MLflow, write predictions to Postgres.

Loads the registered 'hn_score_predictor' model, generates test features,
predicts scores, and writes results to local PostgreSQL (analytics_db).

Usage:
    python ml/predict.py [--n 100] [--tracking-uri http://localhost:5000]
"""

import argparse
import os
import numpy as np
import pandas as pd
import mlflow
import mlflow.pyfunc
import psycopg2

FEATURES = ["hour_of_day", "day_of_week", "title_length", "word_count", "has_url", "has_text", "is_story"]

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = "5432"
PG_USER = "airflow"
PG_PASSWORD = "airflow"
PG_DB = "analytics_db"


def generate_test_data(n=100, seed=99):
    """Generate test features to score."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "hour_of_day": rng.integers(0, 24, size=n),
        "day_of_week": rng.integers(0, 7, size=n),
        "title_length": rng.integers(10, 200, size=n),
        "word_count": rng.integers(1, 50, size=n),
        "has_url": rng.choice([0, 1], size=n),
        "has_text": rng.choice([0, 1], size=n),
        "is_story": np.ones(n, dtype=int),
        "actual_score": np.clip(rng.normal(100, 80, size=n), 1, 1000).astype(int),
    })


def main(n=100, tracking_uri=None):
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    else:
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))

    print(f"Loading production model from MLflow ({mlflow.get_tracking_uri()})...")

    try:
        model = mlflow.pyfunc.load_model("models:/hn_score_predictor/production")
        print("  Loaded model 'hn_score_predictor/production'")
    except Exception:
        try:
            model = mlflow.pyfunc.load_model("models:/hn_score_predictor/1")
            print("  Loaded model 'hn_score_predictor/1' (no production alias)")
        except Exception as e:
            print(f"ERROR: Could not load model. Train first. ({e})")
            return

    # Generate test data
    df = generate_test_data(n=n)
    print(f"Generated {n} test rows")

    # Predict
    df["predicted_score"] = model.predict(df[FEATURES])
    df["predicted_score"] = np.clip(df["predicted_score"], 0, 10000).astype(int)
    print(f"Predicted scores: min={df['predicted_score'].min()}, max={df['predicted_score'].max()}, mean={df['predicted_score'].mean():.1f}")

    # Write to Postgres
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id SERIAL PRIMARY KEY,
            hour_of_day INT,
            day_of_week INT,
            title_length INT,
            word_count INT,
            has_url INT,
            has_text INT,
            predicted_score INT,
            actual_score INT,
            predicted_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("DELETE FROM ml_predictions")
    conn.commit()

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO ml_predictions
            (hour_of_day, day_of_week, title_length, word_count, has_url, has_text, predicted_score, actual_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            int(row["hour_of_day"]), int(row["day_of_week"]), int(row["title_length"]),
            int(row["word_count"]), int(row["has_url"]), int(row["has_text"]),
            int(row["predicted_score"]), int(row["actual_score"])
        ))

    conn.commit()
    conn.close()
    print(f"Scored {n} posts. Predictions written to local Postgres (ml_predictions table).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--tracking-uri", type=str, default=None)
    args = parser.parse_args()
    main(n=args.n, tracking_uri=args.tracking_uri)
