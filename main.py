import argparse
import json
import os
from typing import Dict, List, Optional

import config
from core.base import BaseRecommender
from core.context import RecommendContext
from core.fusion import WeightedFusion
from core.router import RecommendRouter
from core.types import EngineName, RecommendItem
from data.api_client import fetch_watched_and_wished, check_user_exists
from data.mappings import get_id_mapping
from data.recommend_cache import RecommendCache
from scheduler.seasonal import crawl_and_persist
from scheduler.db_updater import update_completed_anime


def _build_context(username: str, id_mapping) -> RecommendContext:
    from data.sync_db import load_watched_from_db, load_wished_from_db, load_history_ratings

    watched_sids = load_watched_from_db(username)
    wished_sids = set(load_wished_from_db(username))
    history_ratings = load_history_ratings(username)

    in_training = id_mapping.is_gcn_user(username)
    exclude_items: List[int] = []
    warm_items: List[int] = []

    if in_training:
        exclude_items = id_mapping.subjects_to_gcn_items(watched_sids)
        mapped_user_id = id_mapping.get_gcn_user_id(username)
        train_items = set()
        train_path = os.path.join(config.GCN_DATA_DIR, "train.txt")
        if os.path.exists(train_path):
            with open(train_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts and parts[0] == str(mapped_user_id):
                        train_items = set(int(i) for i in parts[1:])
                        break
        warm_items = [i for i in exclude_items if i not in train_items]

    return RecommendContext(
        user_id=username,
        username=username,
        watched_subject_ids=watched_sids,
        wished_subject_ids=wished_sids,
        history_ratings=history_ratings,
        collection_count=len(watched_sids),
        in_training_data=in_training,
        gcn_exclude_items=exclude_items,
        gcn_new_for_warm=warm_items,
    )


_engines: Optional[Dict[EngineName, BaseRecommender]] = None


def _get_engines() -> Dict[EngineName, BaseRecommender]:
    global _engines
    if _engines is None:
        _engines = init_engines()
    return _engines


def init_engines() -> Dict[EngineName, BaseRecommender]:
    engines: Dict[EngineName, BaseRecommender] = {}

    try:
        from engines.gcn.engine import GCNRecommender
        engines[EngineName.GCN] = GCNRecommender(
            checkpoint_path=config.GCN_CHECKPOINT,
            data_dir=config.GCN_DATA_DIR,
            dataset=config.GCN_DATASET,
        )
    except Exception as e:
        print(f"[main] GCN 引擎加载失败，已跳过: {e}")

    try:
        from engines.itemcf.engine import ItemCFRecommender
        engines[EngineName.ITEMCF] = ItemCFRecommender(
            sim_path=config.ITEMCF_SIM_PATH,
        )
    except Exception as e:
        print(f"[main] ItemCF 引擎加载失败，已跳过: {e}")

    try:
        from engines.content.engine import ContentBasedRecommender
        engines[EngineName.CONTENT] = ContentBasedRecommender()
    except Exception as e:
        print(f"[main] Content 引擎加载失败，已跳过: {e}")

    try:
        from engines.hot.engine import HotRecommender
        engines[EngineName.HOT] = HotRecommender(min_rating_count=config.HOT_MIN_RATING_COUNT)
    except Exception as e:
        print(f"[main] HOT 引擎加载失败，已跳过: {e}")

    if config.ENABLE_LLM:
        try:
            from engines.llm.engine import LLMRecommender
            engines[EngineName.LLM] = LLMRecommender()
        except Exception as e:
            print(f"[main] LLM 引擎加载失败，已跳过: {e}")

    return engines


def run_recommend(username: str, top_k: int = 100, use_cache: bool = True,
                  force_refresh_api: bool = False, token: Optional[str] = None) -> Dict:
    if token:
        config.ACCESS_TOKEN = token

    if not check_user_exists(username):
        return {"error": f"用户 {username} 不存在", "recommendations": []}

    id_mapping = get_id_mapping()

    _reload = force_refresh_api or (not use_cache)

    print(f"[main] 获取用户 {username} 收藏...")
    watched, wished, from_cache = fetch_watched_and_wished(username, force_refresh=_reload)
    if from_cache:
        print(f"[main] (缓存命中, API 调用已跳过)")
    else:
        print(f"[main] (API 数据已同步到 user_interactions.db)")

    ctx = _build_context(username, id_mapping)

    print(
        f"[main] 看过: {ctx.collection_count}, "
        f"想看: {len(ctx.wished_subject_ids)}, "
        f"在GCN中: {ctx.in_training_data}, "
        f"GCN排除: {len(ctx.gcn_exclude_items)}, "
        f"Warm: {len(ctx.gcn_new_for_warm)}"
    )

    engines = _get_engines()
    router = RecommendRouter(engines)

    if use_cache:
        rcache = RecommendCache()
        cached = rcache.get_for_user(ctx, top_k, available_engines=set(engines.keys()))
        if cached:
            print(f"[main] (推荐缓存命中)")
            return cached

    selected = router.route(ctx)
    selected_names = [e.name.value for e in selected]
    engine_combo = "+".join(selected_names)
    print(f"[main] 使用引擎: {selected_names}")

    profile_key = (
        "small_collection" if ctx.collection_count <= 50 else
        "gcn_user" if ctx.in_training_data else "rich_no_gcn"
    )
    weights = config.FUSION_WEIGHTS_BY_PROFILE[profile_key]
    fusion = WeightedFusion(weights)

    results_by_engine: Dict[EngineName, List[RecommendItem]] = {}
    for engine in selected:
        results_by_engine[engine.name] = engine.recommend(ctx, top_k)

    final = fusion.merge(results_by_engine, ctx, top_k)

    output = {
        "user_id": username,
        "source": engine_combo,
        "collection_count": ctx.collection_count,
        "wished_count": len(ctx.wished_subject_ids),
        "in_training_data": ctx.in_training_data,
        "gcn_exclude_items": len(ctx.gcn_exclude_items),
        "gcn_new_for_warm": len(ctx.gcn_new_for_warm),
        "recommendations": [
            {
                "rank": it.rank,
                "subject_id": it.subject_id,
                "name": it.name_cn or it.name,
                "name_cn": it.name_cn,
                "score": it.score,
                "source": it.source.value,
                "is_wished": it.is_wished,
                "rating_score": it.rating_score,
                "reasons": it.reasons,
            }
            for it in final
        ],
    }

    if use_cache:
        rcache = RecommendCache()
        rcache.set(username, engine_combo, top_k, output)
        print(f"[main] (推荐结果已缓存)")

    return output


def main():
    parser = argparse.ArgumentParser(description="Bangumi 推荐系统")
    sub = parser.add_subparsers(dest="command")

    rec = sub.add_parser("recommend", help="为用户推荐")
    rec.add_argument("--user", required=True, help="用户 ID")
    rec.add_argument("--top-k", type=int, default=100, help="推荐数量")
    rec.add_argument("--token", help="API Access Token")
    rec.add_argument("--refresh", action="store_true", help="强制刷新 API 缓存")
    rec.add_argument("--no-cache", action="store_true", help="禁用推荐缓存")
    rec.add_argument("--output", help="输出路径")

    clear = sub.add_parser("clear-cache", help="清理缓存")
    clear.add_argument("--user", help="清理指定用户")

    crawl = sub.add_parser("crawl-season", help="爬取当季新番")
    crawl.add_argument("--year", type=int, required=True)
    crawl.add_argument("--month", type=int, required=True)

    update = sub.add_parser("update-db", help="更新完结状态")

    import_anime = sub.add_parser("import-anime", help="导入 Animes.jsonlines 到 anime_meta.db")

    args = parser.parse_args()

    if args.command == "recommend":
        use_cache = not args.no_cache
        result = run_recommend(
            args.user, args.top_k,
            use_cache=use_cache,
            force_refresh_api=args.refresh,
            token=args.token,
        )
        if "error" in result:
            print(f"错误: {result['error']}")
            return

        print(f"\n{'='*60}")
        print(f"推荐结果 (共 {len(result['recommendations'])} 部) | 引擎: {result['source']}")
        print(f"{'='*60}")
        print(f"{'排名':<5} {'ID':<8} {'想看':<5} {'评分':<8} {'Bangumi':<6} 名称")
        print("-" * 60)
        for r in result["recommendations"]:
            wish = "\u2713" if r["is_wished"] else ""
            print(
                f"{r['rank']:<5} "
                f"{r['subject_id']:<8} "
                f"{wish:<5} "
                f"{r['score']:<8.4f} "
                f"{r['rating_score']:<6.1f} "
                f"{r['name']}"
            )

        output_path = args.output or os.path.join(config.OUTPUTS_DIR, f"user_{args.user}.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_path}")

    elif args.command == "clear-cache":
        rcache = RecommendCache()
        rcache.clear(args.user)
        print(f"[main] 缓存已清理")

    elif args.command == "crawl-season":
        crawl_and_persist(args.year, args.month)

    elif args.command == "update-db":
        update_completed_anime()

    elif args.command == "import-anime":
        from data.anime_db import import_anime_jsonlines
        import_anime_jsonlines()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
