"""Generate synthetic Hacker News data with known patterns for ML training.

Produces a CSV with 1000 rows. The score (target) is generated using a
deterministic formula with added noise so models can learn real patterns:

    score = base + hour_effect + day_effect + length_bonus + url_bonus + noise

Features:
  - hour_of_day (0-23)
  - day_of_week (0=Mon, 6=Sun)
  - title_length (chars)
  - word_count
  - has_url (0/1)
  - has_text (0/1)
  - is_story (1, always true for this dataset)

Target:
  - score (integer, 1-1000 range)

Usage:
    python ml/generate_synthetic.py [--n 1000] [--seed 42] [--output ml/data/synthetic.csv]
"""

import argparse
import os
import numpy as np
import pandas as pd


def generate(n=1000, seed=42):
    rng = np.random.default_rng(seed)

    hour = rng.integers(0, 24, size=n)
    day = rng.integers(0, 7, size=n)
    title_length = rng.integers(10, 200, size=n)
    word_count = title_length // 5 + rng.integers(-3, 6, size=n)
    word_count = np.clip(word_count, 1, 50)
    has_url = rng.choice([0, 1], size=n, p=[0.4, 0.6])
    has_text = rng.choice([0, 1], size=n, p=[0.6, 0.4])
    is_story = np.ones(n, dtype=int)

    # Known formula for score (with noise)
    hour_effect = np.where(
        (hour >= 8) & (hour <= 11), 150,  # morning bump
        np.where((hour >= 14) & (hour <= 17), 80, -30)
    )
    day_effect = np.where(day < 5, 50, -40)  # weekday > weekend
    length_bonus = np.where((title_length > 30) & (title_length < 80), 60, -20)
    url_bonus = has_url * 50
    noise = rng.normal(0, 80, size=n)

    base = 50
    score = base + hour_effect.astype(float) + day_effect.astype(float) + length_bonus.astype(float) + url_bonus + noise
    score = np.clip(score, 1, 2000).astype(int)

    df = pd.DataFrame({
        "hour_of_day": hour,
        "day_of_week": day,
        "title_length": title_length,
        "word_count": word_count,
        "has_url": has_url,
        "has_text": has_text,
        "is_story": is_story,
        "score": score,
    })

    os.makedirs("ml/data", exist_ok=True)
    output = "ml/data/synthetic.csv"
    df.to_csv(output, index=False)
    print(f"Generated {n} rows, saved to {output}")
    print(f"Score range: {score.min()}-{score.max()}, mean: {score.mean():.1f}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()
    df = generate(n=args.n, seed=args.seed)
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"Also saved to {args.output}")
