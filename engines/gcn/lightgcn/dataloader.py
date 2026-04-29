import os
import numpy as np
import torch
import scipy.sparse as sp
from scipy.sparse import csr_matrix
from time import time

import engines.gcn.lightgcn.world as world


class BasicDataset:
    def __init__(self):
        pass

    @property
    def n_users(self):
        raise NotImplementedError

    @property
    def m_items(self):
        raise NotImplementedError


class Loader(BasicDataset):
    def __init__(self, config=None, data_path="../data/bangumi"):
        if config is None:
            config = world.config
        print(f"[gcn] Loading dataset from: {data_path}")
        self.split = config.get("A_split", False)
        self.folds = config.get("A_n_fold", 100)
        self.n_user = 0
        self.m_item = 0

        train_file = os.path.join(data_path, "train.txt")
        all_file = os.path.join(data_path, "all.txt")

        trainUniqueUsers, trainItem, trainUser = [], [], []
        self.traindataSize = 0

        with open(train_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                uid = int(parts[0])
                items = [int(i) for i in parts[1:]]
                trainUniqueUsers.append(uid)
                trainUser.extend([uid] * len(items))
                trainItem.extend(items)
                self.m_item = max(self.m_item, max(items) + 1)
                self.n_user = max(self.n_user, uid + 1)
                self.traindataSize += len(items)

        self.trainUniqueUsers = np.array(trainUniqueUsers)
        self.trainUser = np.array(trainUser)
        self.trainItem = np.array(trainItem)

        self.user_pos_items = {}
        if os.path.exists(all_file):
            with open(all_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    uid = int(parts[0])
                    items = list(map(int, parts[1:]))
                    self.user_pos_items[uid] = items
        else:
            for uid in set(trainUniqueUsers):
                pass

        self.Graph = None
        print(f"[gcn] {self.traindataSize} interactions loaded, "
              f"{self.n_user} users, {self.m_item} items")

        self.UserItemNet = csr_matrix(
            (np.ones(len(self.trainUser)), (self.trainUser, self.trainItem)),
            shape=(self.n_user, self.m_item),
        )
        self.users_D = np.array(self.UserItemNet.sum(axis=1)).squeeze()
        self.users_D[self.users_D == 0.0] = 1
        self.items_D = np.array(self.UserItemNet.sum(axis=0)).squeeze()
        self.items_D[self.items_D == 0.0] = 1.0

        self._allPos = self.getUserPosItems(list(range(self.n_user)))

    @property
    def n_users(self):
        return self.n_user

    @property
    def m_items(self):
        return self.m_item

    def _convert_sp_mat_to_sp_tensor(self, X):
        coo = X.tocoo().astype(np.float32)
        row = torch.Tensor(coo.row).long()
        col = torch.Tensor(coo.col).long()
        index = torch.stack([row, col])
        data = torch.FloatTensor(coo.data)
        return torch.sparse_coo_tensor(index, data, torch.Size(coo.shape))

    def getSparseGraph(self):
        if self.Graph is None:
            data_dir = os.path.dirname(os.path.join(world.ROOT_PATH, "models/gcn/train.txt"))
            npz_path = os.path.join(
                data_dir if os.path.isdir(data_dir) else os.path.dirname(data_dir),
                "s_pre_adj_mat.npz",
            )
            try:
                pre_adj_mat = sp.load_npz(npz_path)
                print("[gcn] loaded pre-computed adjacency matrix")
                norm_adj = pre_adj_mat
            except Exception:
                print("[gcn] generating adjacency matrix...")
                s = time()
                adj_mat = sp.dok_matrix(
                    (self.n_users + self.m_items, self.n_users + self.m_items),
                    dtype=np.float32,
                )
                adj_mat = adj_mat.tolil()
                R = self.UserItemNet.tolil()
                adj_mat[: self.n_users, self.n_users :] = R
                adj_mat[self.n_users :, : self.n_users] = R.T
                adj_mat = adj_mat.todok()
                rowsum = np.array(adj_mat.sum(axis=1))
                d_inv = np.power(rowsum + 1e-10, -0.5).flatten()
                d_inv[np.isinf(d_inv)] = 0.0
                d_mat = sp.diags(d_inv)
                norm_adj = d_mat.dot(adj_mat).dot(d_mat).tocsr()
                print(f"[gcn] adjacency matrix built in {time() - s:.1f}s")

            self.Graph = self._convert_sp_mat_to_sp_tensor(norm_adj)
            self.Graph = self.Graph.coalesce().to(world.device)
        return self.Graph

    def getUserPosItems(self, users):
        posItems = []
        for user in users:
            posItems.append(self.UserItemNet[user].nonzero()[1])
        return posItems

    def getFullUserPosItems(self, users):
        return [self.user_pos_items.get(u, []) for u in users]
