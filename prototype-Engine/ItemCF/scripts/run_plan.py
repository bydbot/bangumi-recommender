import sqlite3
import os
import json
import numpy as np
from scipy import sparse
import math
import time

OUTPUT_DIR = r"e:\bangumi\usr"
DATA_DB = os.path.join(OUTPUT_DIR, "database", "merged_filtered_collections.db")
SIMILARITY_FILE = os.path.join(OUTPUT_DIR, "item_similarity_base.json")


# ======================
# Step 1: 构建隐式矩阵
# ======================
def build_sparse_matrix():
    print("=" * 70)
    print("Step 1: 构建用户-物品隐式矩阵（仅收藏）")
    print("=" * 70)

    conn = sqlite3.connect(DATA_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT user_id FROM user_collections")
    user_ids = [row[0] for row in cursor.fetchall()]
    user_map = {u: i for i, u in enumerate(user_ids)}

    cursor.execute("SELECT DISTINCT subject_id FROM user_collections")
    item_ids = [row[0] for row in cursor.fetchall()]
    item_map = {i: idx for idx, i in enumerate(item_ids)}
    idx_to_item = {idx: i for i, idx in item_map.items()}

    print(f"用户数: {len(user_ids):,}")
    print(f"物品数: {len(item_ids):,}")

    cursor.execute("SELECT user_id, subject_id FROM user_collections")

    rows, cols, data = [], [], []

    for user_id, item_id in cursor.fetchall():
        rows.append(user_map[user_id])
        cols.append(item_map[item_id])
        data.append(1.0)  # 关键：隐式信号

    conn.close()

    matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(len(user_ids), len(item_ids))
    )

    print(f"矩阵密度: {matrix.nnz / (matrix.shape[0]*matrix.shape[1]):.6f}")

    return matrix, item_map, idx_to_item


# ======================
# Step 2: 相似度计算
# ======================
def compute_item_similarity(matrix, idx_to_item, TOP_K=100, SHRINK=None):
    print("\n" + "=" * 70)
    if SHRINK is not None:
        print(f"Step 2: 计算 ItemCF 相似度（共现 + shrinkage k={SHRINK}）")
    else:
        print("Step 2: 计算 ItemCF 基础相似度（共现 + 余弦，无 shrinkage）")
    print("=" * 70)

    item_matrix = matrix.T.tocsr()

    print("计算物品范数...")
    norms = np.sqrt(item_matrix.multiply(item_matrix).sum(axis=1))
    norms = np.asarray(norms).flatten()
    norms[norms == 0] = 1

    n_items = item_matrix.shape[0]
    batch_size = 500

    item_similarity = {}

    start = time.time()

    for start_i in range(0, n_items, batch_size):
        end_i = min(start_i + batch_size, n_items)

        batch = item_matrix[start_i:end_i]

        # 点积（共现）
        sim = batch.dot(item_matrix.T).toarray()

        for i in range(end_i - start_i):
            idx_i = start_i + i
            row = sim[i]

            # 去掉自己
            row[idx_i] = 0

            # cosine
            row /= (norms[idx_i] * norms + 1e-8)

            # ===== shrink（可选，默认不应用）=====
            if SHRINK is not None:
                co_counts = sim[i]
                row *= co_counts / (co_counts + SHRINK)

            # 去负数
            row[row < 0] = 0

            # TopK
            top_idx = np.argsort(row)[-TOP_K:][::-1]
            top_scores = row[top_idx]

            valid = top_scores > 0
            top_idx = top_idx[valid]
            top_scores = top_scores[valid]

            item_similarity[idx_to_item[idx_i]] = [
                (int(idx_to_item[j]), float(s))
                for j, s in zip(top_idx, top_scores)
            ]

        if start_i % (batch_size * 10) == 0:
            progress = end_i / n_items * 100
            print(f"进度: {progress:.1f}%")

    print(f"耗时: {time.time() - start:.1f}s")

    return item_similarity


# ======================
# Step 3: 保存
# ======================
def save_similarity(sim):
    print("\n保存相似度...")

    with open(SIMILARITY_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sim.items()}, f)

    avg = np.mean([len(v) for v in sim.values()])
    print(f"物品数: {len(sim)}")
    print(f"平均邻居: {avg:.1f}")
    print(f"路径: {SIMILARITY_FILE}")


# ======================
# 主函数
# ======================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='计算 ItemCF 物品相似度')
    parser.add_argument('--top-k', type=int, default=100, help='每个物品的邻居数 (默认100)')
    parser.add_argument('--shrink-k', type=float, default=None, help='Shrinkage参数 (默认不应用shrinkage)')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径 (默认item_similarity_base.json)')
    args = parser.parse_args()

    if args.output:
        global SIMILARITY_FILE
        SIMILARITY_FILE = args.output

    matrix, item_map, idx_to_item = build_sparse_matrix()

    sim = compute_item_similarity(matrix, idx_to_item, TOP_K=args.top_k, SHRINK=args.shrink_k)

    save_similarity(sim)


if __name__ == "__main__":
    main()