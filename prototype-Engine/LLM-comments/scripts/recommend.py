#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 overall_comment 嵌入向量的动画相似度推荐。
与 content_v2 使用相同的 transformers 技术栈。
"""

import sys
import json
import argparse
import logging
from pathlib import Path

import numpy as np
import torch
from transformers import BertModel, BertTokenizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("recommend")


class BGEEmbedder:
    """BGE 文本编码器，与 content_v2/embedding_utils.py 实现一致"""

    def __init__(self, model_dir: str, device: str = "cpu"):
        self.device = device
        self.tokenizer = BertTokenizer.from_pretrained(model_dir)
        self.model = BertModel.from_pretrained(model_dir).to(device)
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts, batch_size: int = 32) -> np.ndarray:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            outputs = self.model(**inputs)
            batch_embeddings = outputs.last_hidden_state[:, 0, :]
            batch_embeddings = torch.nn.functional.normalize(
                batch_embeddings, p=2, dim=1
            )
            embeddings.append(batch_embeddings.cpu().numpy())
        return np.concatenate(embeddings, axis=0).astype(np.float32)


# ─── 数据加载 ──────────────────────────────────────────────────────────────────────

def load_embeddings(embeddings_dir):
    """
    加载嵌入向量和索引。

    Returns:
        (np.ndarray, list[dict])
        embeddings: shape (N, 512), float32, L2 归一化
        index: [{subject_id, comment_len}, ...] 与 embeddings 行对齐
    """
    d = Path(embeddings_dir)
    npy_path = d / "embeddings.npy"
    idx_path = d / "index.json"

    if not npy_path.exists():
        log.error("嵌入文件不存在: %s。请先运行 embed_anime.py。", npy_path)
        sys.exit(1)

    embeddings = np.load(npy_path)
    with open(idx_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    if len(embeddings) != len(index):
        log.error("嵌入矩阵行数 (%d) 与索引条目数 (%d) 不一致!",
                  len(embeddings), len(index))
        sys.exit(1)

    log.info("嵌入已加载: N=%d, dim=%d", len(embeddings), embeddings.shape[1])
    return embeddings, index


def load_anime_metadata(metadata_path):
    """加载动画元数据，按 id 索引。"""
    path = Path(metadata_path)
    if not path.exists():
        log.warning("元数据文件不存在: %s，将不显示标题等信息。", path)
        return {}

    metadata = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            metadata[item["id"]] = {
                "name": item.get("name", ""),
                "name_cn": item.get("name_cn", ""),
                "score": item.get("score"),
                "tags": [t["name"] for t in item.get("tags", [])[:6]],
                "summary": item.get("summary", ""),
                "date": item.get("date", ""),
            }
    log.info("元数据已加载: %d 条记录", len(metadata))
    return metadata


# ─── 相似度计算 ────────────────────────────────────────────────────────────────────

def get_top_k(query_vec, db_vectors, index, k=10, exclude_id=None):
    """
    返回 top-K 相似动画 (余弦相似度 = 点积，向量已 L2 归一化)。
    """
    scores = np.dot(db_vectors, query_vec)

    candidate_k = k + 1 if exclude_id is not None else k
    top_indices = np.argpartition(scores, -candidate_k)[-candidate_k:]
    top_indices = top_indices[np.argsort(-scores[top_indices])]

    results = []
    for i in top_indices:
        sid = index[i]["subject_id"]
        if exclude_id is not None and sid == exclude_id:
            continue
        results.append({
            "idx": int(i),
            "subject_id": sid,
            "similarity": float(scores[i]),
        })
        if len(results) >= k:
            break

    return results


# ─── 推荐接口 ──────────────────────────────────────────────────────────────────────

def recommend_by_id(subject_id, embeddings, index, metadata, k=10):
    """根据动画 ID 找相似动画。"""
    idx_to_sid = {e["subject_id"]: i for i, e in enumerate(index)}
    if subject_id not in idx_to_sid:
        raise KeyError(
            f"subject_id={subject_id} 不在索引中。"
            f" 可能该动画的 overall_comment 为空，或尚未运行 embed_anime.py。"
        )

    query_vec = embeddings[idx_to_sid[subject_id]]
    results = get_top_k(query_vec, embeddings, index, k=k,
                        exclude_id=subject_id)
    return _enrich_results(results, index, metadata)


def recommend_by_text(query_text, embedder, embeddings, index, metadata, k=10):
    """根据文本描述搜索相似动画。"""
    query_vec = embedder.encode([query_text], batch_size=1)[0]
    results = get_top_k(query_vec, embeddings, index, k=k)
    return _enrich_results(results, index, metadata)


def _enrich_results(results, index, metadata):
    """用元数据丰富推荐结果。"""
    for r in results:
        sid = r["subject_id"]
        meta = metadata.get(sid, {})
        r["name"] = meta.get("name", "")
        r["name_cn"] = meta.get("name_cn", "")
        r["score"] = meta.get("score")
        r["tags"] = meta.get("tags", [])
        r["summary"] = meta.get("summary", "")
        r["date"] = meta.get("date", "")
    return results


# ─── CLI ───────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="基于 overall_comment 嵌入向量的动画相似度推荐"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    lookup = subparsers.add_parser("lookup", help="根据动画 ID 查找相似动画")
    lookup.add_argument("subject_id", type=int)
    lookup.add_argument("-k", type=int, default=10, help="返回数量 (默认 10)")

    search = subparsers.add_parser("search", help="根据文本描述搜索动画")
    search.add_argument("query", type=str, help="查询文本 (如 '热血战斗番')")
    search.add_argument("-k", type=int, default=10, help="返回数量 (默认 10)")

    parser.add_argument(
        "--embeddings-dir",
        default=r"E:\bangumi\crawler\embeddings",
        help="嵌入向量目录",
    )
    parser.add_argument(
        "--metadata-path",
        default=r"E:\bangumi\crawler\jsonline\large_comments_anime_records.jsonlines",
        help="动画元数据文件",
    )
    parser.add_argument(
        "--model-path",
        default=r"E:\bangumi\crawler\bge-small-zh-v1.5",
        help="本地 BGE 模型路径",
    )
    parser.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"],
        help="推理设备 (仅 search 模式，默认 cpu)",
    )

    args = parser.parse_args()

    if args.command not in ("lookup", "search"):
        parser.print_help()
        sys.exit(1)

    embeddings, index = load_embeddings(args.embeddings_dir)
    metadata = load_anime_metadata(args.metadata_path)

    if args.command == "lookup":
        try:
            results = recommend_by_id(
                args.subject_id, embeddings, index, metadata, k=args.k
            )
        except KeyError as e:
            log.error(str(e))
            sys.exit(1)
    else:
        log.info("加载模型: %s", args.model_path)
        embedder = BGEEmbedder(args.model_path, device=args.device)
        results = recommend_by_text(
            args.query, embedder, embeddings, index, metadata, k=args.k
        )

    # 输出
    name_width = 40
    print(f"\n{'#':<4} {'动画名称':<{name_width}} {'评分':<6} {'相似度':<8} 日期")
    print("-" * (4 + name_width + 6 + 8 + 12))
    for i, r in enumerate(results, 1):
        title = r["name_cn"] or r["name"] or f"ID:{r['subject_id']}"
        score_str = f"{r['score']:.1f}" if r["score"] else "N/A"
        date_str = r["date"] or ""
        print(f"{i:<4} {title:<{name_width}} {score_str:<6} "
              f"{r['similarity']:.4f}   {date_str}")


if __name__ == "__main__":
    main()
