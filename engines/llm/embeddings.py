import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger("llm.embeddings")


class LLMEmbeddingStore:
    def __init__(self, embeddings_dir: str):
        d = Path(embeddings_dir)
        npy_path = d / "embeddings.npy"
        idx_path = d / "index.json"

        if not npy_path.exists():
            raise FileNotFoundError(
                f"嵌入文件不存在: {npy_path}。请先运行 crawler 的 embed_anime.py。"
            )

        self.embeddings = np.load(npy_path)

        with open(idx_path, "r", encoding="utf-8") as f:
            self.index = json.load(f)

        if len(self.embeddings) != len(self.index):
            log.error(
                "嵌入矩阵行数 (%d) 与索引条目数 (%d) 不一致!",
                len(self.embeddings),
                len(self.index),
            )
            sys.exit(1)

        self._sid_to_row = {e["subject_id"]: i for i, e in enumerate(self.index)}

        log.info(
            "LLMEmbeddingStore 已加载: N=%d, dim=%d",
            len(self.embeddings),
            self.embeddings.shape[1],
        )

    def get_anime_vector(self, subject_id: int) -> Optional[np.ndarray]:
        idx = self._sid_to_row.get(subject_id)
        if idx is None:
            return None
        return self.embeddings[idx]

    def build_user_profile(self, rated_anime: Dict[int, float]) -> Optional[np.ndarray]:
        if not rated_anime:
            return None

        ratings = list(rated_anime.values())
        mean_rating = sum(ratings) / len(ratings)

        high_rated = {
            sid: r
            for sid, r in rated_anime.items()
            if r >= mean_rating
        }

        selected = high_rated if high_rated else rated_anime

        vectors = []
        for sid in selected:
            vec = self.get_anime_vector(sid)
            if vec is not None:
                vectors.append(vec)

        if not vectors:
            return None

        profile = np.mean(vectors, axis=0).astype(np.float32)
        norm = np.linalg.norm(profile)
        if norm > 0:
            profile = profile / norm
        return profile

    def find_similar(
        self,
        user_vector: np.ndarray,
        top_k: int,
        exclude_ids: Optional[set] = None,
    ) -> List[Dict]:
        scores = np.dot(self.embeddings, user_vector)

        candidate_k = top_k
        if exclude_ids:
            candidate_k = min(top_k + len(exclude_ids), len(self.index))

        top_indices = np.argpartition(scores, -candidate_k)[-candidate_k:]
        top_indices = top_indices[np.argsort(-scores[top_indices])]

        results = []
        exclude = exclude_ids or set()
        for i in top_indices:
            sid = self.index[i]["subject_id"]
            if sid in exclude:
                continue
            results.append(
                {
                    "idx": int(i),
                    "subject_id": sid,
                    "similarity": float(scores[i]),
                }
            )
            if len(results) >= top_k:
                break

        return results
