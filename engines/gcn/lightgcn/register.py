import engines.gcn.lightgcn.world as world
import engines.gcn.lightgcn.dataloader as dataloader
import engines.gcn.lightgcn.model as model

import os

_recommender_root = os.path.dirname(os.path.dirname(world.ROOT_PATH))
data_path = os.path.join(_recommender_root, "models", "gcn")
dataset = dataloader.Loader(data_path=data_path)

MODELS = {"lgn": model.LightGCN}
