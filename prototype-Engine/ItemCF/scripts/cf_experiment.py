import argparse
import json
import math
import random
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

import numpy as np
from scipy.sparse import csr_matrix


@dataclass(frozen=True)
class VariantConfig:
    name: str
    use_shrink: bool
    use_tail: bool
    use_novelty: bool
    use_mmr: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline CF experiments with shrink/tail/novelty/MMR."
    )
    parser.add_argument(
        "--db-path",
        default=r"E:\bangumi\usr\database\merged_filtered_collections.db",
        help="Path to merged_filtered_collections.db",
    )
    parser.add_argument(
        "--sim-path",
        default=r"E:\bangumi\usr\item_similarity_base.json",
        help="Path to base item similarity JSON (no shrinkage applied)",
    )
    parser.add_argument(
        "--output-dir",
        default=r"E:\bangumi\usr\results",
        help="Directory for experiment outputs",
    )
    parser.add_argument("--min-user", type=int, default=20, help="Min items per user")
    parser.add_argument("--min-item", type=int, default=20, help="Min users per item")
    parser.add_argument("--test-ratio", type=float, default=0.2, help="Holdout ratio")
    parser.add_argument(
        "--seeds",
        default="42,52,62",
        help="Comma-separated random seeds for repeated runs",
    )
    parser.add_argument("--topn", type=int, default=50, help="Final recommendation size")
    parser.add_argument(
        "--candidate-k", type=int, default=400, help="Candidate pool size before MMR"
    )
    parser.add_argument("--shrink-k", type=float, default=50.0, help="Shrink k")
    parser.add_argument("--alpha-base", type=float, default=0.6, help="Base alpha for tail")
    parser.add_argument("--mmr-base", type=float, default=0.3, help="Base MMR penalty")
    parser.add_argument("--lambda-gini", type=float, default=0.30, help="Lambda1 for Gini")
    parser.add_argument(
        "--lambda-coverage", type=float, default=0.40, help="Lambda2 for Coverage"
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=0,
        help="Optional cap of users for faster iteration (0 means all users).",
    )
    parser.add_argument(
        "--skip-variants",
        nargs="*",
        default=[],
        choices=["baseline", "plus_shrink", "plus_tail", "plus_novelty_mmr"],
        help="Skip specific variants to save time",
    )
    parser.add_argument(
        "--top-k-neighbors",
        type=int,
        default=100,
        help="Max neighbors per item to use during scoring (default 100)",
    )
    return parser.parse_args()


def novelty_factor(user_count: int) -> float:
    if user_count < 100:
        return 0.85
    if user_count < 500:
        return 1.0
    if user_count < 1000:
        return 1.15
    return 1.30


def load_similarity_graph(sim_path: Path) -> Dict[int, List[Tuple[int, float]]]:
    with sim_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    graph: Dict[int, List[Tuple[int, float]]] = {}
    for k, neighbors in raw.items():
        item_i = int(k)
        graph[item_i] = [(int(item_j), float(sim)) for item_j, sim in neighbors]
    return graph


def load_user_histories(
    db_path: Path, min_user: int, min_item: int, max_users: int, seed: int
) -> Dict[str, List[Tuple[int, float]]]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    selected_users: Set[str] = set()
    if max_users > 0:
        cur.execute(
            """
            SELECT user_id
            FROM user_collections
            GROUP BY user_id
            HAVING COUNT(*) >= ?
            """,
            (min_user,),
        )
        all_users = [str(r[0]) for r in cur.fetchall()]
        if max_users < len(all_users):
            rng = random.Random(seed)
            selected_users = set(rng.sample(all_users, max_users))
        else:
            selected_users = set(all_users)

    cur.execute(
        "SELECT user_id, subject_id, rate FROM user_collections ORDER BY user_id"
    )

    histories: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    item_count = Counter()
    while True:
        rows = cur.fetchmany(50000)
        if not rows:
            break
        for user_id, subject_id, rate in rows:
            user_id_str = str(user_id)
            if selected_users and user_id_str not in selected_users:
                continue
            item_id = int(subject_id)
            rating = float(rate)
            histories[user_id_str].append((item_id, rating))
            item_count[item_id] += 1

    conn.close()

    # Iterative filter to respect min_user/min_item constraints.
    changed = True
    while changed:
        changed = False
        keep_items = {iid for iid, c in item_count.items() if c >= min_item}
        new_histories: Dict[str, List[Tuple[int, float]]] = {}
        new_item_count = Counter()
        for uid, records in histories.items():
            filtered = [(iid, r) for iid, r in records if iid in keep_items]
            if len(filtered) >= min_user:
                new_histories[uid] = filtered
                for iid, _ in filtered:
                    new_item_count[iid] += 1
        if len(new_histories) != len(histories) or len(new_item_count) != len(item_count):
            changed = True
        histories = new_histories
        item_count = new_item_count

    if not histories:
        raise RuntimeError(
            "No users left after filtering. Try increasing --max-users or lowering thresholds."
        )

    return histories


def split_train_test(
    histories: Dict[str, List[Tuple[int, float]]], test_ratio: float, seed: int
) -> Tuple[Dict[str, List[Tuple[int, float]]], Dict[str, List[Tuple[int, float]]]]:
    rng = random.Random(seed)
    train: Dict[str, List[Tuple[int, float]]] = {}
    test: Dict[str, List[Tuple[int, float]]] = {}

    for uid, records in histories.items():
        idxs = list(range(len(records)))
        rng.shuffle(idxs)
        test_size = max(1, int(round(len(records) * test_ratio)))
        test_idx = set(idxs[:test_size])
        test_records = [records[i] for i in range(len(records)) if i in test_idx]
        train_records = [records[i] for i in range(len(records)) if i not in test_idx]
        # Keep at least one train record to build profile.
        if not train_records:
            train_records = [test_records.pop()]
        train[uid] = train_records
        test[uid] = test_records
    return train, test


def build_item_pop(histories: Dict[str, List[Tuple[int, float]]]) -> Counter:
    pop = Counter()
    for records in histories.values():
        for iid, _ in records:
            pop[iid] += 1
    return pop


def filter_graph_to_catalog(
    graph: Dict[int, List[Tuple[int, float]]], item_catalog: Set[int]
) -> Dict[int, List[Tuple[int, float]]]:
    out: Dict[int, List[Tuple[int, float]]] = {}
    for i, neigh in graph.items():
        if i not in item_catalog:
            continue
        filtered = [(j, s) for j, s in neigh if j in item_catalog and j != i]
        if filtered:
            out[i] = filtered
    return out


def build_binary_matrix(
    train_histories: Dict[str, List[Tuple[int, float]]]
) -> Tuple[csr_matrix, Dict[int, int], Dict[int, int], List[str]]:
    user_ids = list(train_histories.keys())
    item_ids = sorted({iid for recs in train_histories.values() for iid, _ in recs})
    user_to_idx = {uid: idx for idx, uid in enumerate(user_ids)}
    item_to_idx = {iid: idx for idx, iid in enumerate(item_ids)}
    idx_to_item = {idx: iid for iid, idx in item_to_idx.items()}

    rows = []
    cols = []
    data = []
    for uid, recs in train_histories.items():
        uidx = user_to_idx[uid]
        seen = set()
        for iid, _ in recs:
            if iid in seen:
                continue
            seen.add(iid)
            rows.append(uidx)
            cols.append(item_to_idx[iid])
            data.append(1)

    mat = csr_matrix(
        (np.asarray(data, dtype=np.int32), (np.asarray(rows), np.asarray(cols))),
        shape=(len(user_ids), len(item_ids)),
        dtype=np.int32,
    )
    return mat, item_to_idx, idx_to_item, user_ids


def build_shrunk_graph(
    base_graph: Dict[int, List[Tuple[int, float]]],
    item_to_idx: Dict[int, int],
    co_matrix: csr_matrix,
    shrink_k: float,
) -> Dict[int, List[Tuple[int, float]]]:
    out: Dict[int, List[Tuple[int, float]]] = {}
    for i, neigh in base_graph.items():
        if i not in item_to_idx:
            continue
        row = co_matrix.getrow(item_to_idx[i])
        row_map = {int(c): int(v) for c, v in zip(row.indices, row.data)}
        adjusted = []
        for j, sim in neigh:
            j_idx = item_to_idx.get(j)
            if j_idx is None:
                continue
            n_co = row_map.get(j_idx, 0)
            if n_co <= 0:
                continue
            shrink = n_co / (n_co + shrink_k)
            s_adj = sim * shrink
            if s_adj != 0.0:
                adjusted.append((j, s_adj))
        if adjusted:
            out[i] = adjusted
    return out


def to_lookup(graph: Dict[int, List[Tuple[int, float]]]) -> Dict[int, Dict[int, float]]:
    out: Dict[int, Dict[int, float]] = {}
    for i, neigh in graph.items():
        out[i] = {j: s for j, s in neigh}
    return out


def sim_between(
    lookup: Dict[int, Dict[int, float]], item_a: int, item_b: int
) -> float:
    sim1 = lookup.get(item_a, {}).get(item_b, 0.0)
    sim2 = lookup.get(item_b, {}).get(item_a, 0.0)
    return max(sim1, sim2, 0.0)


def recommend_for_user(
    train_recs: List[Tuple[int, float]],
    base_graph: Dict[int, List[Tuple[int, float]]],
    pop_train: Counter,
    cfg: VariantConfig,
    alpha_base: float,
    mmr_base: float,
    topn: int,
    candidate_k: int,
    sim_lookup: Dict[int, Dict[int, float]],
) -> List[int]:
    train_items = {iid for iid, _ in train_recs}
    user_count = len(train_recs)
    user_mean = statistics.fmean(r for _, r in train_recs)

    nf = novelty_factor(user_count) if cfg.use_novelty else 1.0
    alpha_eff = alpha_base * nf
    mmr_eff = mmr_base * nf

    score = defaultdict(float)
    tail_cache: Dict[int, float] = {}

    for iid, rating in train_recs:
        for cand, sim in base_graph.get(iid, []):
            if cand in train_items:
                continue
            edge = sim
            if cfg.use_tail:
                t = tail_cache.get(cand)
                if t is None:
                    pop_j = pop_train.get(cand, 0)
                    t = 1.0 / (math.log(2.0 + pop_j) ** alpha_eff)
                    tail_cache[cand] = t
                edge *= t
            score[cand] += (rating - user_mean) * edge

    if not score:
        # Fallback to popular unseen items.
        fallback = [iid for iid, _ in pop_train.most_common(topn * 2) if iid not in train_items]
        return fallback[:topn]

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)
    candidates = [iid for iid, _ in ranked[:candidate_k]]

    if not cfg.use_mmr:
        return candidates[:topn]

    selected: List[int] = []
    rel = {iid: score[iid] for iid in candidates}
    pool = set(candidates)
    while pool and len(selected) < topn:
        best_item = None
        best_value = -1e18
        for cand in pool:
            div_pen = 0.0
            if selected:
                div_pen = max(sim_between(sim_lookup, cand, s) for s in selected)
            value = rel[cand] - mmr_eff * div_pen
            if value > best_value:
                best_value = value
                best_item = cand
        selected.append(best_item)
        pool.remove(best_item)
    return selected


def evaluate_variant(
    train: Dict[str, List[Tuple[int, float]]],
    test: Dict[str, List[Tuple[int, float]]],
    graph: Dict[int, List[Tuple[int, float]]],
    cfg: VariantConfig,
    pop_train: Counter,
    all_items: Set[int],
    topn: int,
    candidate_k: int,
    alpha_base: float,
    mmr_base: float,
    lambda_gini: float,
    lambda_cov: float,
    sim_lookup: Dict[int, Dict[int, float]],
) -> Dict[str, float]:
    recalls = []
    ndcgs = []
    rec_counter = Counter()
    total_users = 0

    for uid, train_recs in train.items():
        test_recs = test.get(uid, [])
        if not test_recs:
            continue
        gt = {iid for iid, _ in test_recs}
        if not gt:
            continue
        recs = recommend_for_user(
            train_recs=train_recs,
            base_graph=graph,
            pop_train=pop_train,
            cfg=cfg,
            alpha_base=alpha_base,
            mmr_base=mmr_base,
            topn=topn,
            candidate_k=candidate_k,
            sim_lookup=sim_lookup,
        )
        if not recs:
            recalls.append(0.0)
            ndcgs.append(0.0)
            total_users += 1
            continue

        for iid in recs:
            rec_counter[iid] += 1

        hit = 0
        dcg = 0.0
        for rank, iid in enumerate(recs, start=1):
            if iid in gt:
                hit += 1
                dcg += 1.0 / math.log2(rank + 1.0)
        idcg = sum(1.0 / math.log2(r + 1.0) for r in range(1, min(len(gt), topn) + 1))
        recall_u = hit / len(gt)
        ndcg_u = (dcg / idcg) if idcg > 0 else 0.0

        recalls.append(recall_u)
        ndcgs.append(ndcg_u)
        total_users += 1

    recall = float(np.mean(recalls)) if recalls else 0.0
    ndcg = float(np.mean(ndcgs)) if ndcgs else 0.0

    coverage = len(rec_counter) / max(len(all_items), 1)

    # Gini over all catalog items, including zero-frequency items.
    freqs = np.array([rec_counter.get(iid, 0) for iid in all_items], dtype=np.float64)
    if freqs.sum() == 0:
        gini = 0.0
    else:
        sorted_freq = np.sort(freqs)
        n = sorted_freq.size
        index = np.arange(1, n + 1, dtype=np.float64)
        gini = float((2.0 * np.sum(index * sorted_freq) / (n * np.sum(sorted_freq))) - (n + 1) / n)

    objective = ndcg - lambda_gini * gini + lambda_cov * coverage
    return {
        "users_evaluated": total_users,
        "Recall@50": recall,
        "NDCG@50": ndcg,
        "CatalogCoverage@50": coverage,
        "Gini": gini,
        "Score": objective,
    }


def aggregate_results(per_seed: List[Dict[str, float]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    keys = [k for k in per_seed[0].keys() if k != "users_evaluated"]
    out["runs"] = len(per_seed)
    out["users_evaluated_avg"] = float(np.mean([x["users_evaluated"] for x in per_seed]))
    for k in keys:
        vals = [x[k] for x in per_seed]
        out[f"{k}_mean"] = float(np.mean(vals))
        out[f"{k}_std"] = float(np.std(vals))
    return out


def render_markdown(
    variants: Sequence[VariantConfig],
    per_variant_seed: Dict[str, List[Dict[str, float]]],
    per_variant_agg: Dict[str, Dict[str, float]],
    recall_constraint: float,
) -> str:
    lines = []
    lines.append("# CF Offline Experiment Report")
    lines.append("")
    lines.append("> **Note**: This experiment uses a **pure base cosine similarity** (`item_similarity_base.json`) as the starting point.")
    lines.append("> Each variant applies its own transformations on top, ensuring fair comparison.")
    lines.append("")
    lines.append("## Aggregated Results (mean +/- std)")
    lines.append("")
    lines.append(
        "| Variant | Recall@50 | NDCG@50 | Coverage@50 | Gini | Score | Recall Constraint |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|")

    baseline_recall = per_variant_agg["baseline"]["Recall@50_mean"]
    threshold = baseline_recall - recall_constraint
    for v in variants:
        agg = per_variant_agg[v.name]
        recall = agg["Recall@50_mean"]
        ok = "PASS" if recall >= threshold else "FAIL"
        lines.append(
            f"| {v.name} | "
            f"{agg['Recall@50_mean']:.4f} +/- {agg['Recall@50_std']:.4f} | "
            f"{agg['NDCG@50_mean']:.4f} +/- {agg['NDCG@50_std']:.4f} | "
            f"{agg['CatalogCoverage@50_mean']:.4f} +/- {agg['CatalogCoverage@50_std']:.4f} | "
            f"{agg['Gini_mean']:.4f} +/- {agg['Gini_std']:.4f} | "
            f"{agg['Score_mean']:.4f} +/- {agg['Score_std']:.4f} | "
            f"{ok} (>= {threshold:.4f}) |"
        )

    lines.append("")
    lines.append("## Per-Seed Details")
    lines.append("")
    for v in variants:
        lines.append(f"### {v.name}")
        lines.append("")
        lines.append("| Run | Users | Recall@50 | NDCG@50 | Coverage@50 | Gini | Score |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        for idx, row in enumerate(per_variant_seed[v.name], start=1):
            lines.append(
                f"| {idx} | {int(row['users_evaluated'])} | "
                f"{row['Recall@50']:.4f} | {row['NDCG@50']:.4f} | "
                f"{row['CatalogCoverage@50']:.4f} | {row['Gini']:.4f} | {row['Score']:.4f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()

    if args.output_dir == r"E:\bangumi\usr\results":
        seeds_str = args.seeds.replace(",", "")
        param_suffix = f"s{seeds_str}_n{args.top_k_neighbors}_k{int(args.shrink_k)}"
        output_dir = Path(r"E:\bangumi\usr") / f"results_{param_suffix}"
    else:
        output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")

    db_path = Path(args.db_path)
    sim_path = Path(args.sim_path)
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    print("Loading global data...")
    t0 = time.time()
    histories = load_user_histories(
        db_path=db_path,
        min_user=args.min_user,
        min_item=args.min_item,
        max_users=args.max_users,
        seed=seeds[0] if seeds else 42,
    )
    print(f"Loaded users: {len(histories):,}")
    print(f"Load done in {time.time() - t0:.1f}s")

    print("Loading similarity graph...")
    sim_graph = load_similarity_graph(sim_path)
    print(f"Similarity nodes: {len(sim_graph):,}")

    # 实验变体定义 (基于纯净基础相似度)
    # baseline: 基础余弦相似度，无修正
    # plus_shrink: + Shrinkage 修正 (抑制低共现噪声)
    # plus_tail: + Shrinkage + 长尾惩罚 (降低热门物品偏差)
    # plus_novelty_mmr: + Shrinkage + 长尾惩罚 + 新奇度因子 + MMR重排序 (提升多样性)
    all_variants = [
        VariantConfig("baseline", False, False, False, False),
        VariantConfig("plus_shrink", True, False, False, False),
        VariantConfig("plus_tail", True, True, False, False),
        VariantConfig("plus_novelty_mmr", True, True, True, True),
    ]

    variants = [v for v in all_variants if v.name not in args.skip_variants]
    if args.skip_variants:
        print(f"跳过变体: {args.skip_variants}")
    print(f"运行变体: {[v.name for v in variants]}")

    per_variant_seed: Dict[str, List[Dict[str, float]]] = {v.name: [] for v in all_variants}

    for seed in seeds:
        print(f"\n=== Seed {seed} ===")
        train, test = split_train_test(histories, args.test_ratio, seed)
        pop_train = build_item_pop(train)
        item_catalog = set(pop_train.keys())

        base_filtered = filter_graph_to_catalog(sim_graph, item_catalog)

        if args.top_k_neighbors > 0:
            base_filtered = {
                k: v[:args.top_k_neighbors] for k, v in base_filtered.items()
            }

        B, item_to_idx, _, _ = build_binary_matrix(train)
        co_matrix = (B.T @ B).tocsr()

        shrink_graph = build_shrunk_graph(
            base_graph=base_filtered,
            item_to_idx=item_to_idx,
            co_matrix=co_matrix,
            shrink_k=args.shrink_k,
        )
        sim_lookup = to_lookup(base_filtered)

        graph_for_variant = {
            "baseline": base_filtered,
            "plus_shrink": shrink_graph,
            "plus_tail": shrink_graph,
            "plus_novelty_mmr": shrink_graph,
        }

        for v in variants:
            print(f"Evaluating {v.name} ...")
            metrics = evaluate_variant(
                train=train,
                test=test,
                graph=graph_for_variant[v.name],
                cfg=v,
                pop_train=pop_train,
                all_items=item_catalog,
                topn=args.topn,
                candidate_k=args.candidate_k,
                alpha_base=args.alpha_base,
                mmr_base=args.mmr_base,
                lambda_gini=args.lambda_gini,
                lambda_cov=args.lambda_coverage,
                sim_lookup=sim_lookup,
            )
            per_variant_seed[v.name].append(metrics)
            print(
                f"  Recall@50={metrics['Recall@50']:.4f} "
                f"NDCG@50={metrics['NDCG@50']:.4f} "
                f"Coverage={metrics['CatalogCoverage@50']:.4f} "
                f"Gini={metrics['Gini']:.4f} Score={metrics['Score']:.4f}"
            )

    per_variant_agg = {
        name: aggregate_results(rows) for name, rows in per_variant_seed.items() if rows
    }

    report = {
        "config": {
            "db_path": str(db_path),
            "sim_path": str(sim_path),
            "min_user": args.min_user,
            "min_item": args.min_item,
            "test_ratio": args.test_ratio,
            "seeds": seeds,
            "topn": args.topn,
            "candidate_k": args.candidate_k,
            "shrink_k": args.shrink_k,
            "alpha_base": args.alpha_base,
            "mmr_base": args.mmr_base,
            "lambda_gini": args.lambda_gini,
            "lambda_coverage": args.lambda_coverage,
            "novelty_factor": {
                "<100": 0.85,
                "100-499": 1.0,
                "500-999": 1.15,
                ">=1000": 1.30,
            },
            "objective": "Score = NDCG@50 - lambda_gini*Gini + lambda_coverage*CatalogCoverage@50",
            "recall_constraint": "Recall@50 >= baseline - 0.03",
        },
        "per_seed": per_variant_seed,
        "aggregated": per_variant_agg,
    }

    json_path = output_dir / "cf_experiment_report.json"
    md_path = output_dir / "cf_experiment_report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(
        render_markdown(
            variants=variants,
            per_variant_seed=per_variant_seed,
            per_variant_agg=per_variant_agg,
            recall_constraint=0.03,
        ),
        encoding="utf-8",
    )

    print("\nDone.")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")


if __name__ == "__main__":
    main()
