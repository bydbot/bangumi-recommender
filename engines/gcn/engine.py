import sys
import os
from typing import List

import torch

from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName
from data.mappings import get_id_mapping
from data.anime_db import get_anime_name, get_anime_rating


class GCNRecommender(BaseRecommender):
    name = EngineName.GCN

    def __init__(self, checkpoint_path: str, data_dir: str, dataset: str = "bangumi"):
        self._checkpoint_path = checkpoint_path
        self._data_dir = data_dir
        self._dataset = dataset
        self._model = None
        self._world = None
        self._dataset_obj = None

    def _load(self):
        if self._model is not None:
            return

        lightgcn_dir = os.path.join(os.path.dirname(__file__), "lightgcn")
        if lightgcn_dir not in sys.path:
            sys.path.insert(0, lightgcn_dir)

        import engines.gcn.lightgcn.world as world
        import engines.gcn.lightgcn.register as register

        self._world = world
        self._dataset_obj = register.dataset

        checkpoint = torch.load(self._checkpoint_path, map_location=world.device)
        model = register.MODELS[world.model_name](world.config, self._dataset_obj)
        model = model.to(world.device)

        if "model_state_dict" in checkpoint:
            model.load_state_dict(checkpoint["model_state_dict"])
        else:
            model.load_state_dict(checkpoint)

        model.eval()
        self._model = model

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        self._load()
        mappings = get_id_mapping()

        mapped_user_id = mappings.get_gcn_user_id(ctx.user_id)
        if mapped_user_id is None:
            return []

        user_pos_items = self._dataset_obj.getUserPosItems([mapped_user_id])[0]
        exclude_ids = ctx.gcn_exclude_items if ctx.gcn_exclude_items else []
        warm_ids = ctx.gcn_new_for_warm if ctx.gcn_new_for_warm else []

        all_exclude = set(int(i) for i in user_pos_items)
        all_exclude.update(exclude_ids)
        exclude_t = torch.LongTensor(list(all_exclude)).to(self._world.device)

        with torch.no_grad():
            if warm_ids:
                all_users, all_items = self._model.computer()
                user_emb = all_users[mapped_user_id]
                warm_t = torch.LongTensor(warm_ids).to(self._world.device)
                new_signal = all_items[warm_t].mean(dim=0)
                updated = 0.5 * user_emb + 0.5 * new_signal
                ratings = self._model.f(
                    torch.matmul(updated.unsqueeze(0), all_items.T)
                )
            else:
                user_tensor = torch.LongTensor([mapped_user_id]).to(
                    self._world.device
                )
                ratings = self._model.getUsersRating(user_tensor)

            ratings[0, exclude_t] = -torch.inf
            scores, indices = torch.topk(ratings, k=top_k)

        results = []
        rank = 1
        for i in range(min(top_k, scores.size(1))):
            mapped_item_id = indices[0][i].item()
            score = round(scores[0][i].item(), 4)
            subject_id = mappings.lookup_subject(mapped_item_id)
            if subject_id is None:
                continue
            results.append(
                RecommendItem(
                    rank=rank,
                    subject_id=subject_id,
                    name=get_anime_name(subject_id),
                    name_cn=get_anime_name(subject_id),
                    score=score,
                    source=EngineName.GCN,
                    rating_score=get_anime_rating(subject_id),
                )
            )
            rank += 1
        return results
