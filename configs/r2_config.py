"""
Cloudflare R2 configuration helper.

Provides boto3 client and resource instances for interacting with R2 storage.
"""

import boto3
import os
from dotenv import load_dotenv

load_dotenv()


def get_r2_client():
    """Create an S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def get_r2_resource():
    """Create an S3 resource configured for Cloudflare R2."""
    return boto3.resource(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def list_r2_objects(prefix: str = "") -> list:
    """List all objects in the R2 bucket with optional prefix."""
    client = get_r2_client()
    response = client.list_objects_v2(Bucket=os.getenv("R2_BUCKET_NAME", "datalake"), Prefix=prefix)
    return response.get("Contents", [])
