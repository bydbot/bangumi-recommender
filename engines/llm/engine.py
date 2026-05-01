import logging
from typing import Dict, List

import config
from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName
from data.anime_db import get_anime_meta

log = logging.getLogger("llm.engine")


class LLMRecommender(BaseRecommender):
    name = EngineName.LLM

    def __init__(self, embeddings_dir: str):
        self._embeddings_dir = embeddings_dir
        self._store = None

    def _get_store(self):
        if self._store is None:
            from .embeddings import LLMEmbeddingStore

            self._store = LLMEmbeddingStore(self._embeddings_dir)
        return self._store

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        if not ctx.history_ratings:
            log.info("用户 %s 无评分记录，LLM 引擎跳过", ctx.user_id)
            return []

        rated_count = len(ctx.history_ratings)
        if rated_count < config.LLM_MIN_RATED_COUNT:
            log.info(
                "用户 %s 评分数量不足 (got=%d < min=%d)，LLM 引擎跳过",
                ctx.user_id,
                rated_count,
                config.LLM_MIN_RATED_COUNT,
            )
            return []

        store = self._get_store()

        user_vector = store.build_user_profile(ctx.history_ratings)
        if user_vector is None:
            log.info(
                "用户 %s 的已看动画均不在嵌入索引中，LLM 引擎跳过",
                ctx.user_id,
            )
            return []

        exclude = set(ctx.watched_subject_ids) | ctx.wished_subject_ids
        similar = store.find_similar(user_vector, top_k, exclude_ids=exclude)

        results: List[RecommendItem] = []
        for rank, s in enumerate(similar, 1):
            sid = s["subject_id"]
            meta = get_anime_meta(sid)
            name = meta.get("name", "")
            name_cn = meta.get("name_cn", "")
            rating_score = meta.get("score", 0.0) or 0.0
            is_wished = sid in ctx.wished_subject_ids

            results.append(
                RecommendItem(
                    rank=rank,
                    subject_id=sid,
                    name=name or "",
                    name_cn=name_cn or "",
                    score=s["similarity"],
                    source=EngineName.LLM,
                    is_wished=is_wished,
                    rating_score=float(rating_score),
                    reasons=[
                        f"semantic similarity: {s['similarity']:.4f}"
                    ],
                )
            )

        log.info(
            "LLM 引擎推荐完成: user=%s, 结果数=%d/%d",
            ctx.user_id,
            len(results),
            top_k,
        )
        return results
