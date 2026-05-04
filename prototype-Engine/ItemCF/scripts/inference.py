import sqlite3
import json
import csv
import os
from collections import defaultdict

DB_PATH = r"E:\bangumi\usr\database\merged_filtered_collections.db"
SIM_PATH = r"E:\bangumi\usr\item_similarity_final.json"
ANIME_META_PATH = r"E:\bangumi\bangumi\neo4j_data\anime_nodes.csv"


# ======================
# 1. 加载相似度表
# 使用实验验证的最佳策略生成的最终相似度矩阵 (item_similarity_final.json)
# ======================
def load_similarity():
    with open(SIM_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    sim = {
        int(k): [(int(j), float(s)) for j, s in v]
        for k, v in raw.items()
    }
    return sim


# ======================
# 2. 加载动画元数据（中文名和评分）
# ======================
def load_anime_metadata():
    metadata = {}
    if not os.path.exists(ANIME_META_PATH):
        print(f"警告：元数据文件不存在 {ANIME_META_PATH}")
        return metadata

    with open(ANIME_META_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = int(row["id"])
            metadata[sid] = {
                "name_cn": row.get("name_cn", ""),
                "score": float(row.get("score", 0)) if row.get("score") else 0.0,
            }
    print(f"加载了 {len(metadata)} 部动画的元数据")
    return metadata


# ======================
# 3. 获取用户历史
# ======================
def get_user_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT subject_id, rate FROM user_collections WHERE user_id = ?",
        (user_id,)
    )

    history = [(int(i), float(r)) for i, r in cursor.fetchall()]
    conn.close()

    return history


# ======================
# 4. 推荐函数（核心🔥）
# ======================
def recommend_for_user(user_id, sim, topn=20):
    history = get_user_history(user_id)

    if not history:
        return []

    scores = defaultdict(float)
    user_items = {i for i, _ in history}

    # 👉 用户平均分（去偏置）
    user_mean = sum(r for _, r in history) / len(history)

    for item_i, rating in history:
        for item_j, similarity in sim.get(item_i, []):

            # 不推荐已经看过的
            if item_j in user_items:
                continue

            # 👉 核心公式
            scores[item_j] += similarity * (rating - user_mean)

    # 排序
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return ranked[:topn]


# ======================
# 5. 测试
# ======================
if __name__ == "__main__":
    sim = load_similarity()
    metadata = load_anime_metadata()

    user_id = 588237   # 👈 替换成你的用户ID
    recs = recommend_for_user(user_id, sim, topn=100)

    print(f"\n{'='*80}")
    print(f"用户 {user_id} 推荐结果 (Top-{len(recs)})")
    print(f"{'='*80}")
    print(f"{'排名':<5} {'Bangumi ID':<12} {'中文名':<35} {'推荐得分':<15} {'原作评分':<8}")
    print(f"{'-'*80}")

    for rank, (item_id, score) in enumerate(recs, 1):
        meta = metadata.get(item_id, {})
        name_cn = meta.get("name_cn", "") if meta.get("name_cn") else "未知"
        orig_score = meta.get("score", 0.0)

        print(f"{rank:<5} {item_id:<12} {name_cn:<35} {score:<15.4f} {orig_score:<8.1f}")

    print(f"\n共 {len(recs)} 条推荐")