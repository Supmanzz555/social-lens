"""Train 3 models to predict HN story score, log to MLflow, register best.

Models:
  1. Linear Regression (baseline)
  2. Random Forest (non-linear patterns)
  3. XGBoost (gradient boosting, usually best)

Usage:
    python ml/train_model.py [--data ml/data/synthetic.csv] [--experiment engagement-predictor]

Outputs:
  - MLflow runs with params, metrics (RMSE, MAE, R2), and model artifacts
  - Best model registered in MLflow model registry as "hn_score_predictor"
"""

import argparse
import os
import warnings

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
import xgboost as xgb

warnings.filterwarnings("ignore")

FEATURES = ["hour_of_day", "day_of_week", "title_length", "word_count", "has_url", "has_text", "is_story"]
TARGET = "score"


def train_and_log(model, name, X_train, y_train, X_test, y_test, params):
    """Train model, compute metrics, log to MLflow."""
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    rmse = mean_squared_error(y_test, preds) ** 0.5
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)

    print(f"  {name}: RMSE={rmse:.2f}, MAE={mae:.2f}, R2={r2:.4f}")

    with mlflow.start_run(run_name=name):
        mlflow.log_params(params)
        mlflow.log_metrics({"rmse": rmse, "mae": mae, "r2": r2})
        mlflow.sklearn.log_model(model, "model")
        print(f"  Logged to MLflow (run: {mlflow.active_run().info.run_id})")

    return {"model": model, "rmse": rmse, "mae": mae, "r2": r2, "name": name}


def main(data_path="ml/data/synthetic.csv", experiment_name="engagement-predictor"):
    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    print(f"  {len(df)} rows, {len(FEATURES)} features")

    X = df[FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    mlflow.set_experiment(experiment_name)
    print(f"Experiment: {experiment_name}")

    results = []

    # 1. Linear Regression
    print("\n1. Linear Regression")
    params = {"model": "LinearRegression"}
    result = train_and_log(LinearRegression(), "linear_regression", X_train, y_train, X_test, y_test, params)
    results.append(result)

    # 2. Random Forest
    print("\n2. Random Forest")
    params = {"model": "RandomForest", "n_estimators": 100, "max_depth": 10, "random_state": 42}
    rf = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
    result = train_and_log(rf, "random_forest", X_train, y_train, X_test, y_test, params)
    results.append(result)

    # 3. XGBoost
    print("\n3. XGBoost")
    params = {"model": "XGBoost", "n_estimators": 100, "max_depth": 5, "learning_rate": 0.1, "random_state": 42}
    xgb_model = xgb.XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)
    result = train_and_log(xgb_model, "xgboost", X_train, y_train, X_test, y_test, params)
    results.append(result)

    # Pick best by R2
    best = max(results, key=lambda r: r["r2"])
    print(f"\nBest model: {best['name']} (R2={best['r2']:.4f})")

    # Register best model
    best_run = mlflow.search_runs(
        experiment_names=[experiment_name],
        filter_string=f"tags.mlflow.runName = '{best['name']}'",
    ).iloc[0]
    model_uri = f"runs:/{best_run.run_id}/model"

    try:
        mlflow.register_model(model_uri, "hn_score_predictor")
        print(f"Registered 'hn_score_predictor' version 1 from {best['name']}")
    except mlflow.exceptions.MlflowException as e:
        print(f"Model already registered (may already exist): {e}")

    print(f"\nLogged {len(results)} runs to MLflow. Best model: {best['name']} (R2={best['r2']:.4f})")
    print(f"View at: {os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="ml/data/synthetic.csv")
    parser.add_argument("--experiment", type=str, default="engagement-predictor")
    args = parser.parse_args()
    main(data_path=args.data, experiment_name=args.experiment)
