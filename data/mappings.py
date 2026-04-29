import os
from typing import Dict, Optional

import config


class IDMapping:
    def __init__(self, gcn_data_dir: str = config.GCN_DATA_DIR):
        self._subject_to_gcn_item: Dict[int, int] = {}
        self._gcn_item_to_subject: Dict[int, int] = {}
        self._original_to_gcn_user: Dict[str, int] = {}
        self._load()

    def _load(self):
        item_list = os.path.join(config.GCN_DATA_DIR, "item_list.txt")
        if os.path.exists(item_list):
            with open(item_list, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        mapped_id, original_id = int(parts[0]), int(parts[1])
                        self._subject_to_gcn_item[original_id] = mapped_id
                        self._gcn_item_to_subject[mapped_id] = original_id

        user_list = os.path.join(config.GCN_DATA_DIR, "user_list.txt")
        if os.path.exists(user_list):
            with open(user_list, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        mapped_id, original_id = int(parts[0]), parts[1]
                        self._original_to_gcn_user[original_id] = mapped_id

    def lookup_gcn_item(self, subject_id: int) -> Optional[int]:
        return self._subject_to_gcn_item.get(subject_id)

    def lookup_subject(self, mapped_id: int) -> int:
        return self._gcn_item_to_subject.get(mapped_id, mapped_id)

    def is_gcn_user(self, user_id: str) -> bool:
        return user_id in self._original_to_gcn_user

    def get_gcn_user_id(self, user_id: str) -> Optional[int]:
        return self._original_to_gcn_user.get(user_id)

    def subjects_to_gcn_items(self, subject_ids: list) -> list:
        result = []
        for sid in subject_ids:
            mapped = self.lookup_gcn_item(sid)
            if mapped is not None:
                result.append(mapped)
        return result


_global_id_mapping: Optional[IDMapping] = None


def get_id_mapping() -> IDMapping:
    global _global_id_mapping
    if _global_id_mapping is None:
        _global_id_mapping = IDMapping()
    return _global_id_mapping
