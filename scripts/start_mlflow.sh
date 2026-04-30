#!/bin/bash
cd "$(dirname "$0")"
nohup uv run mlflow server --host 0.0.0.0 --port 5000 > /tmp/mlflow.log 2>&1 &
echo "MLflow started with PID $!"
