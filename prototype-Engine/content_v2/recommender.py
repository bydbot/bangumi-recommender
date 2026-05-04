#!/usr/bin/env python3
"""
Content-based recommendation engine using BGE embeddings.

Input: {watched: {subject_id: rating}, wished: [subject_id]}
Output: List[Dict] compatible with RecommendItem format.
"""
import os
from typing import Dict, List, Optional, Set, Tuple

import torch

import config


class ContentRecommenderV2:
    def __init__(self, feature_path: str = config.FEATURE_PATH):
        if not os.path.exists(feature_path):
            raise FileNotFoundError(
                f"Feature file not found: {feature_path}. "
                "Please run build_features.py first."
            )

        data = torch.load(feature_path, map_location="cpu", weights_only=False)

        self.anime_ids: List[int] = [int(x) for x in data["anime_ids"]]
        self.anime_id_to_index: Dict[int, int] = {
            int(k): int(v) for k, v in data["anime_id_to_index"].items()
        }
        self.anime_vectors: torch.Tensor = data["anime_vectors"].float()

        self.staff_vectors: Dict[int, Dict[str, float]] = {
            int(k): {str(t): float(v) for t, v in vec.items()}
            for k, vec in data.get("staff_vectors", {}).items()
        }
        self.va_vectors: Dict[int, Dict[str, float]] = {
            int(k): {str(t): float(v) for t, v in vec.items()}
            for k, vec in data.get("va_vectors", {}).items()
        }
        self.tag_vectors: Dict[int, Dict[str, float]] = {
            int(k): {str(t): float(v) for t, v in vec.items()}
            for k, vec in data.get("tag_vectors", {}).items()
        }

        self.staff_dense: torch.Tensor = data.get("staff_dense", torch.tensor([])).float()
        self.va_dense: torch.Tensor = data.get("va_dense", torch.tensor([])).float()
        self.tag_tfidf_dense: torch.Tensor = data.get("tag_tfidf_dense", torch.tensor([])).float()
        self.meta_dense: torch.Tensor = data.get("meta_dense", torch.tensor([])).float()

        self.tag_embeddings: torch.Tensor = data.get("tag_embeddings", torch.tensor([])).float()
        self.tag_vocab: List[str] = [str(t) for t in data.get("tag_vocab", [])]
        self.tag_vocab_index: Dict[str, int] = {
            str(t): int(v) for t, v in data.get("tag_vocab_index", {}).items()
        }

        self.meta_keys: List[str] = list(data.get("meta_keys", []))
        self.person_name_map: Dict[int, str] = {
            int(k): v for k, v in data.get("person_name_map", {}).items()
        }
        self.anime_meta_map: Dict[int, Dict] = {
            int(k): v for k, v in data.get("anime_meta_map", {}).items()
        }

        self.staff_dim = self.staff_dense.shape[1] if self.staff_dense.numel() > 0 else 0
        self.va_dim = self.va_dense.shape[1] if self.va_dense.numel() > 0 else 0
        self.tag_dim = self.tag_tfidf_dense.shape[1] if self.tag_tfidf_dense.numel() > 0 else 0
        self.meta_dim = self.meta_dense.shape[1] if self.meta_dense.numel() > 0 else 0

        self._staff_end = self.staff_dim
        self._va_end = self._staff_end + self.va_dim
        self._tag_end = self._va_end + self.tag_dim
        self._meta_end = self._tag_end + self.meta_dim

        print(
            f"ContentRecommenderV2: loaded {len(self.anime_ids)} anime, "
            f"vectors shape: {self.anime_vectors.shape}"
        )

    def _metadata(self, subject_id: int) -> Dict:
        return self.anime_meta_map.get(subject_id, {})

    def build_user_vector(
        self,
        watched: Dict[int, float],
        wished: List[int],
    ) -> torch.Tensor:
        watched_vectors = []
        watched_weights = []

        valid_watched = {
            int(sid): float(rating)
            for sid, rating in watched.items()
            if int(sid) in self.anime_id_to_index
        }

        if valid_watched:
            ratings = list(valid_watched.values())
            mean_rating = sum(ratings) / len(ratings)

            for sid, rating in valid_watched.items():
                idx = self.anime_id_to_index[sid]
                vec = self.anime_vectors[idx]
                if rating >= mean_rating:
                    weight = config.WATCHED_HIGH_WEIGHT
                else:
                    weight = config.WATCHED_LOW_WEIGHT
                watched_vectors.append(vec)
                watched_weights.append(weight)

        wished_vectors = []
        wished_weights = []
        valid_wished = [
            int(sid) for sid in wished if int(sid) in self.anime_id_to_index
        ]

        for sid in valid_wished:
            idx = self.anime_id_to_index[sid]
            vec = self.anime_vectors[idx]
            wished_vectors.append(vec)
            wished_weights.append(config.WISHED_WEIGHT)

        all_vectors = watched_vectors + wished_vectors
        all_weights = watched_weights + wished_weights

        if not all_vectors:
            return torch.zeros(self.anime_vectors.shape[1], dtype=torch.float32)

        stacked = torch.stack(all_vectors, dim=0)
        weights = torch.tensor(all_weights, dtype=torch.float32).unsqueeze(1)
        weighted_sum = (stacked * weights).sum(dim=0)
        weight_total = weights.sum()

        user_vector = weighted_sum / weight_total
        norm = torch.linalg.norm(user_vector)
        if norm > 0:
            user_vector = user_vector / norm

        return user_vector

    def recommend(
        self,
        watched: Dict[int, float],
        wished: List[int],
        top_k: int = 20,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[Dict]:
        user_vector = self.build_user_vector(watched, wished)

        if user_vector.sum().abs().item() == 0:
            return []

        exclude = set(exclude_ids) if exclude_ids else set()
        exclude.update(int(sid) for sid in watched.keys())
        exclude.update(int(sid) for sid in wished)

        similarities = torch.mv(self.anime_vectors, user_vector)

        candidate_indices = []
        for idx, sid in enumerate(self.anime_ids):
            if sid not in exclude:
                candidate_indices.append(idx)

        if not candidate_indices:
            return []

        candidate_tensor = torch.tensor(candidate_indices, dtype=torch.long)
        candidate_scores = similarities[candidate_tensor]

        top_k = min(top_k, len(candidate_indices))
        top_values, top_positions = torch.topk(candidate_scores, top_k)

        results = []
        for i in range(top_k):
            pos = top_positions[i].item()
            idx = candidate_indices[pos]
            sid = self.anime_ids[idx]
            score = top_values[i].item()
            meta = self._metadata(sid)

            breakdown = self._compute_breakdown(idx, user_vector)
            reasons = self._generate_reasons(sid, breakdown, score)

            results.append(
                {
                    "subject_id": sid,
                    "name": meta.get("name", ""),
                    "name_cn": meta.get("name_cn", ""),
                    "score": round(score, 4),
                    "rating_score": float(meta.get("score", 0.0)),
                    "reasons": reasons,
                    "breakdown": breakdown,
                }
            )

        for rank, item in enumerate(results, 1):
            item["rank"] = rank

        return results

    def _compute_breakdown(self, anime_idx: int, user_vector: torch.Tensor) -> Dict[str, float]:
        breakdown = {}

        if self.staff_dim > 0:
            staff_vec = self.staff_dense[anime_idx]
            staff_norm = staff_vec / torch.clamp(torch.linalg.norm(staff_vec), min=1e-8)
            user_staff = user_vector[:self._staff_end]
            breakdown["staff"] = float(torch.dot(staff_norm, user_staff).item())

        if self.va_dim > 0:
            va_vec = self.va_dense[anime_idx]
            va_norm = va_vec / torch.clamp(torch.linalg.norm(va_vec), min=1e-8)
            user_va = user_vector[self._staff_end:self._va_end]
            breakdown["va"] = float(torch.dot(va_norm, user_va).item())

        if self.tag_dim > 0:
            tag_vec = self.tag_tfidf_dense[anime_idx]
            tag_norm = tag_vec / torch.clamp(torch.linalg.norm(tag_vec), min=1e-8)
            user_tag = user_vector[self._va_end:self._tag_end]
            breakdown["tag"] = float(torch.dot(tag_norm, user_tag).item())

        if self.meta_dim > 0:
            meta_vec = self.meta_dense[anime_idx]
            meta_norm = meta_vec / torch.clamp(torch.linalg.norm(meta_vec), min=1e-8)
            user_meta = user_vector[self._tag_end:self._meta_end]
            breakdown["meta"] = float(torch.dot(meta_norm, user_meta).item())

        return breakdown

    def _generate_reasons(
        self, subject_id: int, breakdown: Dict[str, float], score: float
    ) -> List[str]:
        reasons = []

        tag_vec = self.tag_vectors.get(subject_id, {})
        if tag_vec:
            top_tags = sorted(tag_vec.items(), key=lambda x: x[1], reverse=True)[:3]
            tag_names = [t for t, _ in top_tags]
            reasons.append(f"tag: {', '.join(tag_names)}")

        staff_vec = self.staff_vectors.get(subject_id, {})
        if staff_vec:
            top_staff = sorted(staff_vec.items(), key=lambda x: x[1], reverse=True)[:2]
            staff_names = []
            for token, _ in top_staff:
                pid_str = token.split("@")[0]
                try:
                    pid = int(pid_str)
                    name = self.person_name_map.get(pid, pid_str)
                except ValueError:
                    name = pid_str
                staff_names.append(name)
            reasons.append(f"staff: {', '.join(staff_names)}")

        va_vec = self.va_vectors.get(subject_id, {})
        if va_vec:
            top_va = sorted(va_vec.items(), key=lambda x: x[1], reverse=True)[:2]
            va_names = []
            for token, _ in top_va:
                try:
                    pid = int(token)
                    name = self.person_name_map.get(pid, token)
                except ValueError:
                    name = token
                va_names.append(name)
            reasons.append(f"va: {', '.join(va_names)}")

        breakdown_parts = []
        for dim in ["staff", "va", "tag", "meta"]:
            if dim in breakdown and breakdown[dim] > 0:
                breakdown_parts.append(f"{dim}={breakdown[dim]:.3f}")
        if breakdown_parts:
            reasons.append(f"breakdown: {'; '.join(breakdown_parts)}")

        reasons.append(f"similarity: {score:.4f}")

        return reasons
