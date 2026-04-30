"""Polls YouTube Data API and publishes videos to Kafka topic 'youtube-videos'."""

import json
import os
import sys
import time
import logging
import requests
from kafka import KafkaProducer
from kafka.errors import KafkaError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
TOPIC = os.getenv("KAFKA_TOPIC_YOUTUBE", "youtube-videos")
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS_LOCAL", "localhost:9092")
API_KEY = os.getenv("YOUTUBE_API_KEY", "")
LAST_VIDEO_FILE = os.path.join(os.path.dirname(__file__), ".yt_last_video")

POPULAR_CATEGORIES = ["10", "20", "22", "23", "24", "25", "28"]


def get_last_videos():
    if os.path.exists(LAST_VIDEO_FILE):
        with open(LAST_VIDEO_FILE) as f:
            return set(f.read().strip().split(","))
    return set()


def save_last_videos(video_ids):
    with open(LAST_VIDEO_FILE, "w") as f:
        f.write(",".join(video_ids))


def fetch_popular_videos(max_results=50):
    """Fetch most popular videos from YouTube API."""
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": "US",
        "maxResults": min(max_results, 50),
        "key": API_KEY,
    }
    resp = requests.get(f"{YT_API}/videos", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_search_videos(query="technology", max_results=25):
    """Search for recent videos matching a query."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "date",
        "maxResults": min(max_results, 50),
        "key": API_KEY,
    }
    resp = requests.get(f"{YT_API}/search", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_video_details(video_ids):
    """Fetch detailed stats for specific video IDs."""
    ids_str = ",".join(video_ids)
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ids_str,
        "key": API_KEY,
    }
    resp = requests.get(f"{YT_API}/videos", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_duration(iso_duration):
    """Convert ISO 8601 duration (PT1H2M3S) to seconds."""
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    h, m, s = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def create_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda v: v.encode("utf-8") if v else None,
        retries=5,
        acks="all",
        linger_ms=50,
        batch_size=16384,
    )


def run(limit=None):
    """Poll YouTube API and publish videos to Kafka."""
    if not API_KEY:
        logger.error("YOUTUBE_API_KEY not set. Cannot fetch videos.")
        return 0

    logger.info("Connecting to Kafka at %s", BOOTSTRAP)
    producer = create_producer()
    logger.info("Connected to Kafka. Topic: %s", TOPIC)

    last_videos = get_last_videos()
    count = 0
    new_video_ids = set()

    items = []

    try:
        popular = fetch_popular_videos(max_results=limit or 50)
        items.extend(popular.get("items", []))
    except requests.RequestException as e:
        logger.warning("Failed to fetch popular videos: %s", e)

    queries = ["technology", "data engineering", "python programming"]
    for q in queries:
        if limit and count >= limit:
            break
        try:
            search = fetch_search_videos(query=q, max_results=10)
            search_items = search.get("items", [])
            video_ids = [i["id"]["videoId"] for i in search_items]
            if video_ids:
                details = get_video_details(video_ids)
                items.extend(details.get("items", []))
        except requests.RequestException as e:
            logger.warning("Failed to search '%s': %s", q, e)

    for item in items:
        if limit and count >= limit:
            break

        video_id = item["id"]
        if video_id in last_videos:
            continue

        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        message = {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "published_at": snippet.get("publishedAt", ""),
            "description": snippet.get("description", "")[:500],
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "duration_seconds": parse_duration(content.get("duration", "PT0S")),
        }

        try:
            producer.send(TOPIC, key=video_id, value=message)
            count += 1
            new_video_ids.add(video_id)
            logger.info("Published video %s: %s", video_id, message["title"][:60])
        except KafkaError as e:
            logger.error("Failed to publish video %s: %s", video_id, e)

    combined = last_videos | new_video_ids
    if len(combined) > 1000:
        combined = set(list(combined)[-1000:])
    save_last_videos(combined)

    producer.flush()
    producer.close()
    logger.info("Done. Published %d messages to %s", count, TOPIC)
    return count


if __name__ == "__main__":
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    run(limit=limit)
