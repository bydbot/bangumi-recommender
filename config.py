import os
from core.types import EngineName

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DB_DIR = os.path.join(BASE_DIR, "db")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")

USER_INTERACTIONS_DB = os.path.join(DB_DIR, "user_interactions.db")
ANIME_META_DB = os.path.join(DB_DIR, "anime_meta.db")
API_CACHE_DB = os.path.join(DB_DIR, "api_cache.db")
SEASONAL_DB = os.path.join(DB_DIR, "seasonal.db")
RECOMMEND_CACHE_DB = os.path.join(DB_DIR, "recommend_cache.db")
COMMENTS_DB = os.path.join(DB_DIR, "comments.db")
API_CACHE_TTL_HOURS = 168

ANIME_JSONLINES = "e:/bangumi/bangumi/Animes.jsonlines"
ANIME_NODES_CSV = os.path.join(MODELS_DIR, "meta", "anime_nodes.csv")

GCN_DATA_DIR = os.path.join(MODELS_DIR, "gcn")
GCN_CHECKPOINT = os.path.join(GCN_DATA_DIR, "lgn-bangumi-epoch90.pth.tar")

ITEMCF_SIM_PATH = os.path.join(MODELS_DIR, "itemcf", "item_similarity_final.json")

BANGUMI_API_BASE = "https://api.bgm.tv"
BANGUMI_USER_AGENT = "Indie_guy(https://github.com/bydbot)"
ACCESS_TOKEN = None

API_REQUEST_DELAY = 1.0
API_MAX_RETRIES = 3

GCN_DATASET = "bangumi"
WARM_ALPHA = 0.5

HOT_WEIGHT_WATCHED = 0.35
HOT_WEIGHT_WISHED = 0.35
HOT_WEIGHT_RATING = 0.30
HOT_MIN_RATING_COUNT = 2000
HOT_TIME_DECAY_HALF_LIFE_DAYS = 360
HOT_NORMALIZE_RATING_SCALE = 10.0

CACHE_ENGINE_TOP_M = 125
RECOMMEND_CACHE_TTL_HOURS = 168
ENABLE_LLM = True

LLM_EMBEDDINGS_DIR = r"E:\bangumi\crawler\embeddings"
LLM_MIN_RATED_COUNT = 3

FUSION_WEIGHTS_BY_PROFILE = {
    "small_collection": {
        EngineName.CONTENT: 0.30,
        EngineName.HOT: 0.40,
        EngineName.LLM: 0.30,
    },
    "gcn_user": {
        EngineName.GCN: 0.5,
        EngineName.LLM: 0.5,
    },
    "rich_no_gcn": {
        EngineName.ITEMCF: 0.40,
        EngineName.CONTENT: 0.30,
        EngineName.LLM: 0.30,
    },
}
