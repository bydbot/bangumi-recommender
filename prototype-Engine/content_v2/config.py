import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SUBGRAPH_DIR = r"e:\bangumi\content_recommend\data\subgraph"
STATISTICS_DIR = r"e:\bangumi\content_recommend\data\statistics"
FILTERED_DATA_DIR = r"e:\bangumi\content_recommend\data\filtered_data"
ANIMES_FILE = r"e:\bangumi\bangumi\Animes.jsonlines"

BGE_MODEL_DIR = os.path.join(BASE_DIR, "bge-small-zh-v1.5")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FEATURE_PATH = os.path.join(OUTPUT_DIR, "content_features_v2.pt")

WATCHED_HIGH_WEIGHT = 2.0
WATCHED_LOW_WEIGHT = 0.5
WISHED_WEIGHT = 1.0

CONTENT_WEIGHTS = {
    "staff": 0.30,
    "va": 0.25,
    "tag": 0.35,
    "meta": 0.10,
}

VALID_STAFF_CATEGORIES = {"核心人员", "主要人员"}
VALID_VA_CATEGORIES = {"核心声优", "主要声优"}
