#!/usr/bin/env python3
"""
Build content features with BGE embeddings for anime recommendation.

Output:
    content_v2/output/content_features_v2.pt
"""
import argparse
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Set, Tuple

import pandas as pd
import torch

import config
from embedding_utils import BGEEmbedder

HIGH_ROLE_POSITIONS = {2, 74, 3, 10}
MID_ROLE_POSITIONS = {1, 67}
ROLE_WEIGHTS = {
    "high": 1.0,
    "mid": 0.8,
    "low": 0.5,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build content features with BGE embeddings")
    parser.add_argument(
        "--subgraph-dir",
        default=config.SUBGRAPH_DIR,
        help="Directory containing subgraph CSV files",
    )
    parser.add_argument(
        "--animes-file",
        default=config.ANIMES_FILE,
        help="Animes jsonlines file path",
    )
    parser.add_argument(
        "--output-dir",
        default=config.OUTPUT_DIR,
        help="Output directory",
    )
    return parser.parse_args()


def role_group(position: int) -> str:
    if position in HIGH_ROLE_POSITIONS:
        return "high"
    if position in MID_ROLE_POSITIONS:
        return "mid"
    return "low"


def safe_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def safe_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_valid_tags(tag_file: str = None) -> List[str]:
    if tag_file is None:
        tag_file = os.path.join(config.FILTERED_DATA_DIR, "tag_statistics_filtered.txt")
    if not os.path.exists(tag_file):
        return []
    tags: List[str] = []
    with open(tag_file, "r", encoding="utf-8") as f:
        for _ in range(4):
            f.readline()
        for line in f:
            line = line.strip()
            if not line or line.startswith("-"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                tags.append(parts[0])
    return tags


def load_valid_staff_ids() -> Set[int]:
    csv_path = os.path.join(config.STATISTICS_DIR, "staff_classification.csv")
    if not os.path.exists(csv_path):
        return set()
    df = pd.read_csv(csv_path)
    valid = df[df["category"].isin(config.VALID_STAFF_CATEGORIES)]
    return set(int(pid) for pid in valid["person_id"])


def load_valid_va_ids() -> Set[int]:
    csv_path = os.path.join(config.STATISTICS_DIR, "voice_actor_classification.csv")
    if not os.path.exists(csv_path):
        return set()
    df = pd.read_csv(csv_path)
    valid = df[df["category"].isin(config.VALID_VA_CATEGORIES)]
    return set(int(pid) for pid in valid["person_id"])


def parse_date(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def build_meta_feature(anime_row: Dict) -> Dict[str, float]:
    feature = {}
    type_id = safe_int(anime_row.get("type", 0), 0)
    feature[f"type:{type_id}"] = 1.0

    dt = parse_date(anime_row.get("date", ""))
    if dt:
        month = dt.month
        if month in (12, 1, 2):
            season = "winter"
        elif month in (3, 4, 5):
            season = "spring"
        elif month in (6, 7, 8):
            season = "summer"
        else:
            season = "autumn"
        feature[f"season:{season}"] = 1.0
        year_bucket = (dt.year // 5) * 5
        feature[f"year_bucket:{year_bucket}"] = 1.0
    return feature


def compute_idf(df_counter: Counter, total_docs: int) -> Dict[str, float]:
    idf = {}
    for key, df in df_counter.items():
        idf[key] = math.log((total_docs + 1.0) / (float(df) + 1.0)) + 1.0
    return idf


def apply_tfidf(
    doc_tf: Dict[int, Counter],
    idf: Dict[str, float],
    key_weight_fn=None,
) -> Dict[int, Dict[str, float]]:
    out = {}
    for anime_id, tf_counter in doc_tf.items():
        vec = {}
        for key, tf in tf_counter.items():
            weight = 1.0
            if key_weight_fn is not None:
                weight = key_weight_fn(key)
            vec[key] = float(tf) * float(idf.get(key, 0.0)) * float(weight)
        out[anime_id] = vec
    return out


def build_sparse_to_dense(
    sparse_vectors: Dict[int, Dict[str, float]],
    anime_ids: List[int],
    vocab: List[str],
) -> torch.Tensor:
    vocab_index = {t: i for i, t in enumerate(vocab)}
    dense = torch.zeros((len(anime_ids), len(vocab)), dtype=torch.float32)
    anime_id_to_index = {sid: i for i, sid in enumerate(anime_ids)}
    for anime_id, vec in sparse_vectors.items():
        if anime_id not in anime_id_to_index:
            continue
        row_idx = anime_id_to_index[anime_id]
        for key, value in vec.items():
            if key in vocab_index:
                dense[row_idx, vocab_index[key]] = value
    return dense


def normalize_rows(matrix: torch.Tensor) -> torch.Tensor:
    norms = torch.linalg.norm(matrix, dim=1, keepdim=True)
    norms = torch.clamp(norms, min=1e-8)
    return matrix / norms


def build_anime_vectors(
    staff_dense: torch.Tensor,
    va_dense: torch.Tensor,
    tag_tfidf_dense: torch.Tensor,
    meta_dense: torch.Tensor,
    content_weights: Dict[str, float],
) -> torch.Tensor:
    w_staff = content_weights.get("staff", 0.4)
    w_va = content_weights.get("va", 0.25)
    w_tag = content_weights.get("tag", 0.3)
    w_meta = content_weights.get("meta", 0.05)

    staff_norm = normalize_rows(staff_dense)
    va_norm = normalize_rows(va_dense)
    tag_norm = normalize_rows(tag_tfidf_dense)
    meta_norm = normalize_rows(meta_dense)

    scaled_parts = [
        w_staff * staff_norm,
        w_va * va_norm,
        w_tag * tag_norm,
        w_meta * meta_norm,
    ]
    combined = torch.cat(scaled_parts, dim=1)
    return normalize_rows(combined)


def main() -> None:
    args = parse_args()
    subgraph_dir = args.subgraph_dir

    anime_nodes_path = os.path.join(subgraph_dir, "anime_nodes.csv")
    person_nodes_path = os.path.join(subgraph_dir, "person_nodes.csv")
    staff_path = os.path.join(subgraph_dir, "has_staff_relations.csv")
    voices_path = os.path.join(subgraph_dir, "voices_relations.csv")

    anime_nodes = pd.read_csv(anime_nodes_path)
    person_nodes = pd.read_csv(person_nodes_path)
    staff_df = pd.read_csv(staff_path)
    voices_df = pd.read_csv(voices_path)

    anime_ids = sorted([safe_int(v) for v in anime_nodes["id"].tolist()])
    anime_set = set(anime_ids)
    total_docs = len(anime_ids)

    person_name_map = {}
    for _, row in person_nodes.iterrows():
        pid = safe_int(row.get("id", 0), 0)
        if pid <= 0:
            continue
        person_name_map[pid] = row.get("name", "") if isinstance(row.get("name", ""), str) else ""

    anime_meta_map = {}
    for _, row in anime_nodes.iterrows():
        sid = safe_int(row.get("id", 0), 0)
        if sid <= 0:
            continue
        anime_meta_map[sid] = {
            "name": row.get("name", "") if isinstance(row.get("name", ""), str) else "",
            "name_cn": row.get("name_cn", "") if isinstance(row.get("name_cn", ""), str) else "",
            "score": safe_float(row.get("score", 0.0), 0.0),
            "type": safe_int(row.get("type", 0), 0),
            "platform": safe_int(row.get("platform", 0), 0),
            "date": row.get("date", "") if isinstance(row.get("date", ""), str) else "",
        }

    valid_staff_ids = load_valid_staff_ids()
    valid_va_ids = load_valid_va_ids()
    print(f"Valid staff IDs: {len(valid_staff_ids)}")
    print(f"Valid VA IDs: {len(valid_va_ids)}")

    staff_tf: Dict[int, Counter] = defaultdict(Counter)
    staff_df_counter: Counter = Counter()
    staff_seen_doc_keys: Dict[int, set] = defaultdict(set)
    for _, row in staff_df.iterrows():
        anime_id = safe_int(row.get("anime_id", 0), 0)
        person_id = safe_int(row.get("person_id", 0), 0)
        position = safe_int(row.get("position", 0), 0)
        if anime_id not in anime_set or person_id <= 0:
            continue
        if person_id not in valid_staff_ids:
            continue
        g = role_group(position)
        token = f"{person_id}@{g}"
        staff_tf[anime_id][token] += 1
        if token not in staff_seen_doc_keys[anime_id]:
            staff_df_counter[token] += 1
            staff_seen_doc_keys[anime_id].add(token)

    staff_idf = compute_idf(staff_df_counter, total_docs)

    def staff_key_weight(key: str) -> float:
        if key.endswith("@high"):
            return ROLE_WEIGHTS["high"]
        if key.endswith("@mid"):
            return ROLE_WEIGHTS["mid"]
        return ROLE_WEIGHTS["low"]

    staff_vectors = apply_tfidf(staff_tf, staff_idf, key_weight_fn=staff_key_weight)

    va_tf: Dict[int, Counter] = defaultdict(Counter)
    va_df_counter: Counter = Counter()
    va_seen_doc_keys: Dict[int, set] = defaultdict(set)
    for _, row in voices_df.iterrows():
        anime_id = safe_int(row.get("anime_id", 0), 0)
        person_id = safe_int(row.get("person_id", 0), 0)
        if anime_id not in anime_set or person_id <= 0:
            continue
        if person_id not in valid_va_ids:
            continue
        token = str(person_id)
        va_tf[anime_id][token] += 1
        if token not in va_seen_doc_keys[anime_id]:
            va_df_counter[token] += 1
            va_seen_doc_keys[anime_id].add(token)

    va_idf = compute_idf(va_df_counter, total_docs)
    va_vectors = apply_tfidf(va_tf, va_idf)

    valid_tags_list = load_valid_tags()
    valid_tags = set(valid_tags_list)
    tag_tf: Dict[int, Counter] = defaultdict(Counter)
    tag_df_counter: Counter = Counter()
    tag_seen_doc_keys: Dict[int, set] = defaultdict(set)
    if os.path.exists(args.animes_file):
        with open(args.animes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                anime_id = safe_int(data.get("id", 0), 0)
                if anime_id not in anime_set:
                    continue
                for tag in data.get("tags", []):
                    name = tag.get("name", "")
                    if not isinstance(name, str) or not name:
                        continue
                    if valid_tags and name not in valid_tags:
                        continue
                    token = name
                    count = safe_int(tag.get("count", 1), 1)
                    tag_tf[anime_id][token] = math.log1p(max(1, count))
                    if token not in tag_seen_doc_keys[anime_id]:
                        tag_df_counter[token] += 1
                        tag_seen_doc_keys[anime_id].add(token)

    tag_idf = compute_idf(tag_df_counter, total_docs)
    tag_vectors = apply_tfidf(tag_tf, tag_idf)

    print(f"Encoding {len(valid_tags_list)} tags with BGE...")
    embedder = BGEEmbedder(config.BGE_MODEL_DIR)
    tag_embeddings = embedder.encode(valid_tags_list)
    tag_vocab_index = {t: i for i, t in enumerate(valid_tags_list)}
    print(f"Tag embeddings shape: {tag_embeddings.shape}")

    meta_vectors: Dict[int, Dict[str, float]] = {}
    meta_keys_set = set()
    for anime_id in anime_ids:
        meta = anime_meta_map.get(anime_id, {})
        vec = build_meta_feature(meta)
        meta_vectors[anime_id] = vec
        meta_keys_set.update(vec.keys())

    meta_keys = sorted(meta_keys_set)
    meta_key_to_index = {k: i for i, k in enumerate(meta_keys)}
    meta_dense = torch.zeros((total_docs, len(meta_keys)), dtype=torch.float32)
    anime_id_to_index = {sid: i for i, sid in enumerate(anime_ids)}
    for anime_id, vec in meta_vectors.items():
        if anime_id not in anime_id_to_index:
            continue
        row_idx = anime_id_to_index[anime_id]
        for key, value in vec.items():
            col_idx = meta_key_to_index[key]
            meta_dense[row_idx, col_idx] = float(value)

    staff_vectors = {sid: staff_vectors.get(sid, {}) for sid in anime_ids}
    va_vectors = {sid: va_vectors.get(sid, {}) for sid in anime_ids}
    tag_vectors = {sid: tag_vectors.get(sid, {}) for sid in anime_ids}

    staff_vocab = sorted(staff_idf.keys())
    va_vocab = sorted(va_idf.keys())
    tag_vocab = sorted(tag_idf.keys())

    staff_dense = build_sparse_to_dense(staff_vectors, anime_ids, staff_vocab)
    va_dense = build_sparse_to_dense(va_vectors, anime_ids, va_vocab)
    tag_tfidf_dense = build_sparse_to_dense(tag_vectors, anime_ids, tag_vocab)

    anime_vectors = build_anime_vectors(
        staff_dense, va_dense, tag_tfidf_dense, meta_dense, config.CONTENT_WEIGHTS
    )

    output_data = {
        "anime_ids": anime_ids,
        "anime_id_to_index": anime_id_to_index,
        "anime_vectors": anime_vectors,
        "staff_vectors": staff_vectors,
        "va_vectors": va_vectors,
        "tag_vectors": tag_vectors,
        "staff_dense": staff_dense,
        "va_dense": va_dense,
        "tag_tfidf_dense": tag_tfidf_dense,
        "tag_embeddings": tag_embeddings,
        "tag_vocab": valid_tags_list,
        "tag_vocab_index": tag_vocab_index,
        "meta_dense": meta_dense,
        "meta_keys": meta_keys,
        "staff_idf": staff_idf,
        "va_idf": va_idf,
        "tag_idf": tag_idf,
        "staff_vocab": staff_vocab,
        "va_vocab": va_vocab,
        "tag_vocab_tfidf": tag_vocab,
        "person_name_map": person_name_map,
        "anime_meta_map": anime_meta_map,
        "settings": {
            "role_weights": ROLE_WEIGHTS,
            "high_role_positions": sorted(HIGH_ROLE_POSITIONS),
            "mid_role_positions": sorted(MID_ROLE_POSITIONS),
            "content_weights": config.CONTENT_WEIGHTS,
            "valid_staff_count": len(valid_staff_ids),
            "valid_va_count": len(valid_va_ids),
            "valid_tag_count": len(valid_tags_list),
            "created_at": datetime.utcnow().isoformat(),
        },
    }

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, "content_features_v2.pt")
    torch.save(output_data, output_path)

    print("=" * 72)
    print("Content feature build complete")
    print(f"Output: {output_path}")
    print(f"Anime: {len(anime_ids)}")
    print(f"Staff vocab: {len(staff_idf)} (filtered from {len(staff_df['person_id'].unique())} total)")
    print(f"VA vocab: {len(va_idf)} (filtered from {len(voices_df['person_id'].unique())} total)")
    print(f"Tag vocab: {len(tag_idf)}")
    print(f"Tag embeddings: {tag_embeddings.shape}")
    print(f"Meta dims: {len(meta_keys)}")
    print(f"Anime vectors: {anime_vectors.shape}")
    print("=" * 72)


if __name__ == "__main__":
    main()
