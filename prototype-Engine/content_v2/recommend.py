#!/usr/bin/env python3
"""
CLI entry for content-based recommendation.

Examples:
    python recommend.py --watched-file watched.json --top-k 20
    python recommend.py --watched-file watched.json --wished-file wished.json --top-k 50
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from recommender import ContentRecommenderV2


def load_watched(file_path: str) -> dict:
    if not os.path.exists(file_path):
        print(f"Watched file not found: {file_path}")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return {item.get("subject_id", item.get("id")): item.get("rating", item.get("score", 1.0)) for item in data}
    elif isinstance(data, dict):
        return {int(k): float(v) for k, v in data.items()}
    return {}


def load_wished(file_path: str) -> list:
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, (int, str)):
                result.append(int(item))
            elif isinstance(item, dict):
                sid = item.get("subject_id") or item.get("id")
                if sid:
                    result.append(int(sid))
        return result
    return []


def format_recommendations(recs, title=""):
    print(f"\n{'=' * 120}")
    print(title)
    print(f"{'=' * 120}")
    print(f"{'Rank':<6} {'Bangumi ID':<12} {'CN Name':<36} {'Original Name':<38} {'Score':<8} {'Similarity':<10}")
    print(f"{'-' * 120}")

    for rec in recs:
        name_cn = rec.get("name_cn", "") or ""
        name = rec.get("name", "") or ""
        if len(name_cn) > 35:
            name_cn = name_cn[:33] + ".."
        if len(name) > 37:
            name = name[:35] + ".."

        print(
            f"{rec.get('rank', 0):<6} {rec.get('subject_id', 0):<12} "
            f"{name_cn:<36} {name:<38} "
            f"{rec.get('rating_score', 0.0):<8.1f} {rec.get('score', 0.0):.4f}"
        )

        if rec.get("breakdown"):
            b = rec["breakdown"]
            parts = []
            for dim in ["staff", "va", "tag", "meta"]:
                if dim in b and b[dim] > 0:
                    parts.append(f"{dim}={b[dim]:.4f}")
            if parts:
                print(f"       breakdown: {', '.join(parts)}")

        reasons = rec.get("reasons", [])
        if reasons:
            print(f"       reasons: {' | '.join(reasons[:3])}")

    print(f"\nTotal: {len(recs)}")


def main():
    parser = argparse.ArgumentParser(description="Anime recommendation (Content-based V2)")
    parser.add_argument("--watched-file", type=str, help="JSON file of watched anime {id: rating}")
    parser.add_argument("--wished-file", type=str, help="JSON file of wished anime [id]")
    parser.add_argument("--top-k", type=int, default=20, help="Number of recommendations")
    parser.add_argument("--user-id", type=str, help="User ID (for display)")
    parser.add_argument("--feature-path", type=str, default=config.FEATURE_PATH, help="Path to content_features_v2.pt")
    args = parser.parse_args()

    if not args.watched_file:
        parser.print_help()
        return

    watched = load_watched(args.watched_file)
    wished = load_wished(args.wished_file) if args.wished_file else []

    if not watched and not wished:
        print("No watched or wished anime provided")
        return

    print(f"Input: watched={len(watched)}, wished={len(wished)}")

    recommender = ContentRecommenderV2(feature_path=args.feature_path)

    recs = recommender.recommend(
        watched=watched,
        wished=wished,
        top_k=args.top_k,
    )

    if not recs:
        print("\nNo recommendations available")
        return

    user_label = f"User {args.user_id}" if args.user_id else "Recommendations"
    format_recommendations(recs, f"{user_label} (Top-{args.top_k})")


if __name__ == "__main__":
    main()
