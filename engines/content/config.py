import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "models", "content"))

BGE_MODEL_DIR = os.path.join(MODELS_DIR, "bge-small-zh-v1.5")
FEATURE_PATH = os.path.join(MODELS_DIR, "content_features_v2.pt")

WATCHED_HIGH_WEIGHT = 2.0
WATCHED_LOW_WEIGHT = 0.5
WISHED_WEIGHT = 1.0

VALID_STAFF_CATEGORIES = {"核心人员", "主要人员"}
VALID_VA_CATEGORIES = {"核心声优", "主要声优"}
