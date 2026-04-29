import os
import torch

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

dataset = "bangumi"
model_name = "lgn"
GPU = torch.cuda.is_available()
device = torch.device("cuda" if GPU else "cpu")

config = {
    "latent_dim_rec": 64,
    "lightGCN_n_layers": 3,
    "dropout": 0,
    "keep_prob": 0.6,
    "A_split": False,
    "pretrain": 0,
}


class _PrintLogger:
    def info(self, msg, *args, **kwargs):
        print(f"[gcn] {msg % args if args else msg}")

    def error(self, msg, *args, **kwargs):
        print(f"[gcn] ERROR: {msg % args if args else msg}")

    def warning(self, msg, *args, **kwargs):
        print(f"[gcn] WARNING: {msg % args if args else msg}")


logger = _PrintLogger()
