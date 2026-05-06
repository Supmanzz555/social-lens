"""Great Expectations validation for silver data quality.

Reads silver Parquet from R2, validates against expectations,
writes reports and returns exit code 1 on failure.

Usage:
    python scripts/run_data_quality.py
"""

import json
import sys
import os
import io
import logging
from datetime import datetime
from pathlib import Path

import boto3
import pyarrow.parquet as pq
import pandas as pd
import great_expectations as gx
from great_expectations.expectations.expectation_configuration import ExpectationConfiguration

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

R2_BUCKET = os.getenv("R2_BUCKET_NAME", "datalake")
R2_ENDPOINT = f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
EXPECTATIONS_DIR = Path("/opt/airflow/data_quality/expectations")
REPORTS_DIR = Path("/opt/airflow/data_quality/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

S3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
)


def list_r2_keys(prefix):
    keys = []
    resp = S3.list_objects_v2(Bucket=R2_BUCKET, Prefix=prefix)
    for obj in resp.get("Contents", []):
        if obj["Key"].endswith(".parquet"):
            keys.append(obj["Key"])
    return keys


def read_silver_df(source):
    keys = list_r2_keys(f"silver/{source}/")
    if not keys:
        raise ValueError(f"No silver data found for {source}")
    dfs = []
    for key in keys:
        data = S3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read()
        table = pq.read_table(io.BytesIO(data))
        dfs.append(table.to_pandas())
    return pd.concat(dfs, ignore_index=True)


def load_expectations(suite_name):
    path = EXPECTATIONS_DIR / f"{suite_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Expectations file not found: {path}")
    with open(path) as f:
        return json.load(f)["expectations"]


def validate(source, df, expectations):
    logger.info("Validating %s (%d rows, %d expectations)", source, len(df), len(expectations))

    context = gx.get_context()
    datasource = context.data_sources.add_pandas(f"{source}_datasource")
    asset = datasource.add_dataframe_asset(name=f"{source}_silver")
    batch_def = asset.add_batch_definition_whole_dataframe("all")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{source}_suite"))
    for exp in expectations:
        ec = ExpectationConfiguration(type=exp["type"], kwargs=exp["kwargs"])
        suite.add_expectation_configuration(ec)

    validator = context.get_validator(
        batch=batch,
        expectation_suite=suite,
    )

    result = validator.validate()
    success = result.success

    results_summary = []
    for r in result.results:
        status = "PASS" if r.success else "FAIL"
        cfg = r.expectation_config
        if hasattr(cfg, "type"):
            exp_type = cfg.type
        elif isinstance(cfg, dict):
            exp_type = cfg.get("type", "unknown")
        else:
            exp_type = "unknown"
        results_summary.append({
            "expectation_type": exp_type,
            "success": r.success,
        })
        logger.info("  [%s] %s", status, exp_type)

    report = {
        "source": source,
        "row_count": len(df),
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "results": results_summary,
    }

    report_path = REPORTS_DIR / f"{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("Report: %s | Success: %s", report_path, success)
    return success


def main():
    sources = {
        "hackernews": "hackernews_expectations",
        "github": "github_expectations",
        "youtube": "youtube_expectations",
    }

    all_passed = True
    for source, suite_name in sources.items():
        try:
            df = read_silver_df(source)
            expectations = load_expectations(suite_name)
            success = validate(source, df, expectations)
            if not success:
                all_passed = False
        except Exception as e:
            logger.exception("Validation failed for %s: %s", source, e)
            all_passed = False

    if all_passed:
        logger.info("All validations passed.")
        sys.exit(0)
    else:
        logger.error("One or more validations failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
