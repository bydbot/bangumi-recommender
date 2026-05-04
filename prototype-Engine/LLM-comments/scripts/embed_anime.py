#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 BGE-small-zh-v1.5 对 overall_comment 批量编码，生成嵌入向量。
与 content_v2 使用相同的 transformers 技术栈 (BertTokenizer + BertModel)。
"""

import sys
import json
import time
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
log = logging.getLogger("embed_anime")


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
            # [CLS] token 作为句向量，L2 归一化
            batch_embeddings = outputs.last_hidden_state[:, 0, :]
            batch_embeddings = torch.nn.functional.normalize(
                batch_embeddings, p=2, dim=1
            )
            embeddings.append(batch_embeddings.cpu().numpy())
        return np.concatenate(embeddings, axis=0).astype(np.float32)


def collect_analysis_files(root_dir):
    """
    遍历 comments_analysis/ 下所有 YYYY/QN/ID.json，
    提取 subject_id 和 overall.overall_comment。
    """
    root = Path(root_dir)
    if not root.is_dir():
        log.error("分析目录不存在: %s", root)
        sys.exit(1)

    entries = []
    skipped_empty = 0
    skipped_parse = 0

    for json_path in sorted(root.rglob("*.json")):
        subject_id_str = json_path.stem
        if not subject_id_str.isdigit():
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            skipped_parse += 1
            log.warning("跳过无法解析的文件: %s (%s)", json_path, e)
            continue

        comment = (
            data.get("overall", {})
            .get("overall_comment", "")
            .strip()
        )
        if not comment:
            skipped_empty += 1
            continue

        entries.append({
            "subject_id": int(subject_id_str),
            "comment": comment,
        })

    log.info("收集完成: %d 条有效评论", len(entries))
    if skipped_empty:
        log.info("跳过空评论: %d", skipped_empty)
    if skipped_parse:
        log.info("跳过解析失败: %d", skipped_parse)

    if not entries:
        log.error("未找到任何可用的 overall_comment，退出。")
        sys.exit(1)

    return entries


def save_embeddings(embeddings, index, output_dir):
    """保存嵌入向量 (npy) 和索引 (json)"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    npy_path = out / "embeddings.npy"
    np.save(npy_path, embeddings)
    log.info("嵌入向量已保存: %s (shape=%s)", npy_path, embeddings.shape)

    idx_path = out / "index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    log.info("索引已保存: %s (%d 条)", idx_path, len(index))


def main():
    parser = argparse.ArgumentParser(
        description="对 overall_comment 批量编码为 BGE 嵌入向量"
    )
    parser.add_argument(
        "--analysis-dir",
        default=r"E:\bangumi\crawler\comments_analysis",
        help="分析结果 JSON 目录",
    )
    parser.add_argument(
        "--model-path",
        default=r"E:\bangumi\crawler\bge-small-zh-v1.5",
        help="本地 BGE 模型路径",
    )
    parser.add_argument(
        "--output-dir",
        default=r"E:\bangumi\crawler\embeddings",
        help="输出目录",
    )
    parser.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"],
        help="推理设备 (默认 cpu)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=32,
        help="编码批次大小",
    )
    args = parser.parse_args()

    # 1. 收集评论文本
    entries = collect_analysis_files(args.analysis_dir)

    # 2. 加载模型
    log.info("从 %s 加载模型 (device=%s)...", args.model_path, args.device)
    embedder = BGEEmbedder(args.model_path, device=args.device)
    log.info("模型已加载，向量维度: %d", embedder.model.config.hidden_size)

    # 3. 生成嵌入
    comments = [e["comment"] for e in entries]
    log.info("开始编码 %d 条评论 (batch_size=%d)...", len(comments), args.batch_size)
    t0 = time.perf_counter()
    embeddings = embedder.encode(comments, batch_size=args.batch_size)
    elapsed = time.perf_counter() - t0
    log.info("编码完成，耗时 %.1f 秒 (%.0f 条/秒)",
             elapsed, len(comments) / elapsed)

    # 4. 构建索引
    index = [
        {"subject_id": e["subject_id"], "comment_len": len(e["comment"])}
        for e in entries
    ]

    # 5. 保存
    save_embeddings(embeddings, index, args.output_dir)
    log.info("全部完成。")


if __name__ == "__main__":
    main()
