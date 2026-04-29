# Bangumi 推荐系统 — 模块架构总览

## 项目概览

这是一个基于 Bangumi（番组计划）平台的动画推荐系统，整合了多种推荐算法（图神经网络、协同过滤、内容相似度、热度排名），通过用户收藏数据为用户提供个性化推荐。

---

## 一、入口层

### 1. CLI 入口 [`main.py`](file:///e:/bangumi/recommender/main.py)

**职责**：命令行主入口，提供推荐、缓存管理、数据同步等功能。

**主要接口**：
```
python main.py recommend --user <用户ID> [--top-k N] [--token <Token>] [--refresh] [--no-cache] [--output <路径>]
python main.py clear-cache [--user <用户ID>]
python main.py crawl-season --year <年> --month <月>
python main.py update-db
python main.py import-anime
```

**数据流向**：
```
用户请求 → 检查用户是否存在 → 获取收藏数据(API/缓存) → 构建上下文 → 路由选择引擎 → 
各引擎推荐 → 融合排序 → 缓存结果 → 输出
```

### 2. HTTP API [`api.py`](file:///e:/bangumi/recommender/api.py)

**职责**：FastAPI 包装，提供 REST 接口。

**接口**：
| 端点 | 方法 | 输入 | 输出 |
|------|------|------|------|
| `/recommend` | GET | `user_id`, `top_k`(1-100), `token` | JSON 推荐结果 |
| `/health` | GET | 无 | `{"status": "ok"}` |

---

## 二、配置层 [`config.py`](file:///e:/bangumi/recommender/config.py)

**职责**：集中管理全局配置。

**核心配置项**：
- **路径配置**：模型目录、数据库目录、输出目录
- **数据库路径**：用户交互、动漫元数据、API缓存、季度数据、推荐缓存
- **API 配置**：基础 URL、限速、重试策略
- **引擎参数**：GCN 模型路径、ItemCF 相似度矩阵路径
- **融合权重**：按用户画像（收藏少/GCN用户/收藏多）配置不同引擎权重

---

## 三、核心层 (`core/`)

### 1. 基础抽象 [`base.py`](file:///e:/bangumi/recommender/core/base.py)

```python
class BaseRecommender(ABC):
    def recommend(ctx: RecommendContext, top_k: int) -> List[RecommendItem]
    property name() -> EngineName
```

**职责**：所有推荐引擎必须继承的接口契约。

### 2. 推荐上下文 [`context.py`](file:///e:/bangumi/recommender/core/context.py)

**数据结构 [`RecommendContext`](file:///e:/bangumi/recommender/core/context.py#L5-L14)**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | str | Bangumi 用户 ID |
| `watched_subject_ids` | List[int] | 看过的动画 ID 列表 |
| `wished_subject_ids` | Set[int] | 想看的动画 ID 集合 |
| `history_ratings` | Dict[int, float] | 历史评分记录 |
| `collection_count` | int | 收藏数量 |
| `in_training_data` | bool | 是否在 GCN 训练数据中 |
| `gcn_exclude_items` | List[int] | GCN 需排除的项 |
| `gcn_new_for_warm` | List[int] | GCN Warm-start 项 |

### 3. 类型定义 [`types.py`](file:///e:/bangumi/recommender/core/types.py)

**引擎枚举 [`EngineName`](file:///e:/bangumi/recommender/core/types.py#L6-L11)**：`GCN`, `ITEMCF`, `CONTENT`, `HOT`, `LLM`

**推荐结果 [`RecommendItem`](file:///e:/bangumi/recommender/core/types.py#L14-L25)**：
| 字段 | 说明 |
|------|------|
| `rank` | 排名 |
| `subject_id` | 动画 ID |
| `name`/`name_cn` | 名称/中文名 |
| `score` | 推荐分数 |
| `source` | 来源引擎 |
| `is_wished` | 是否在想看列表 |
| `reasons` | 推荐理由 |
| `breakdown` | 各维度分数分解 |
| `rating_score` | Bangumi 评分 |

### 4. 引擎路由 [`router.py`](file:///e:/bangumi/recommender/core/router.py)

**职责**：根据用户画像动态选择推荐引擎组合。

**路由策略**：

| 用户画像 | 使用引擎 |
|----------|----------|
| 收藏 ≤ 50 部 | Content + Hot + LLM |
| 在 GCN 训练数据中 | GCN + LLM |
| 收藏多但不在 GCN 中 | ItemCF + Content + LLM |

### 5. 结果融合 [`fusion.py`](file:///e:/bangumi/recommender/core/fusion.py)

**职责**：将多个引擎的推荐结果合并排序。

**融合流程**：
```
各引擎结果 → Min-Max 归一化 → 乘以引擎权重 → 取最高分合并 → 排序 → Top-K
```

---

## 四、数据层 (`data/`)

### 1. API 客户端 [`api_client.py`](file:///e:/bangumi/recommender/data/api_client.py)

**职责**：与 Bangumi API 交互。

**主要接口**：
| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `check_user_exists` | 用户名 | bool | 检查用户是否存在 |
| `fetch_collections` | 用户名, 收藏类型, 分页 | List[CollectionItem] | 分页获取收藏 |
| `fetch_watched_and_wished` | 用户名, 刷新标志 | (watched, wished, 缓存命中) | 获取看过+想看 |
| `browse_seasonal` | 年, 月 | List[SlimSubject] | 浏览季度动画 |
| `get_subject_detail` | 动画 ID | Subject | 获取动画详情 |
| `fetch_calendar` | 无 | Dict[动画ID, SlimSubject] | 获取当前放送日历 |
| `browse_and_detail_seasonal` | 年, 月 | List[SeasonalAnime] | 季度动画+详情 |

**数据流向**：
```
请求 → 检查 API 缓存 → 缓存命中则返回 → 否则调用 Bangumi API → 
写入缓存 + 同步到 user_interactions.db
```

### 2. ID 映射 [`mappings.py`](file:///e:/bangumi/recommender/data/mappings.py)

**职责**：Bangumi Subject ID ↔ GCN Item ID 双向映射。

**数据源**：`models/gcn/item_list.txt`, `models/gcn/user_list.txt`

**接口**：
| 方法 | 输入 | 输出 |
|------|------|------|
| `lookup_gcn_item` | subject_id | gcn_item_id |
| `lookup_subject` | gcn_item_id | subject_id |
| `is_gcn_user` | user_id | bool |
| `get_gcn_user_id` | user_id | mapped_user_id |

### 3. 数据库同步 [`sync_db.py`](file:///e:/bangumi/recommender/data/sync_db.py)

**职责**：用户收藏数据持久化到 SQLite。

**数据库**：`db/user_interactions.db`

**表结构 `user_collections`**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | TEXT | 用户 ID |
| `subject_id` | INTEGER | 动画 ID |
| `rate` | REAL | 用户评分 |
| `collect_type` | INTEGER | 1=想看, 2=看过 |

**接口**：
| 函数 | 输入 | 输出 |
|------|------|------|
| `sync_user_interactions` | user_id, watched, wished | 无 |
| `load_watched_from_db` | user_id | List[subject_id] |
| `load_wished_from_db` | user_id | List[subject_id] |
| `load_history_ratings` | user_id | Dict[subject_id, rating] |

### 4. 动漫元数据 [`anime_db.py`](file:///e:/bangumi/recommender/data/anime_db.py)

**职责**：动画基础信息管理。

**数据库**：`db/anime_meta.db`

**接口**：
| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `import_anime_jsonlines` | 文件路径 | count | 从 JSONL 导入 |
| `insert_or_replace_anime` | data dict | 无 | 插入/更新 |
| `get_anime_meta` | subject_id | {name, name_cn, score} | 获取元数据 |
| `get_anime_name` | subject_id | str | 获取名称 |
| `get_anime_rating` | subject_id | float | 获取评分 |

### 5. API 缓存 [`api_cache.py`](file:///e:/bangumi/recommender/data/api_cache.py)

**职责**：API 响应缓存，避免频繁调用。

**数据库**：`db/api_cache.db`，TTL 默认 168 小时

### 6. 推荐缓存 [`recommend_cache.py`](file:///e:/bangumi/recommender/data/recommend_cache.py)

**职责**：推荐结果缓存，Key = (user_id, engine_combo, top_k)。

**数据库**：`db/recommend_cache.db`，TTL 默认 168 小时

---

## 五、推荐引擎层 (`engines/`)

### 1. GCN 引擎 [`engines/gcn/engine.py`](file:///e:/bangumi/recommender/engines/gcn/engine.py)

**算法**：LightGCN 图神经网络

**输入**：
- 模型检查点：`models/gcn/lgn-bangumi-epoch90.pth.tar`
- 训练数据：`models/gcn/train.txt`, `s_pre_adj_mat.npz`

**推荐流程**：
```
用户 ID → 查找映射 → 获取用户向量 → (可选) Warm-start 融合 → 
计算所有 Item 分数 → 排除已看过 → Top-K 输出
```

**Warm-start 机制**：新收藏的物品取平均向量，与用户向量 0.5/0.5 融合。

### 2. ItemCF 引擎 [`engines/itemcf/engine.py`](file:///e:/bangumi/recommender/engines/itemcf/engine.py)

**算法**：基于物品的协同过滤

**输入**：相似度矩阵 `models/itemcf/item_similarity_final.json`

**推荐流程**：
```
用户历史评分 → 计算平均分 → 对每个历史物品 → 
查找相似物品 → 加权累加 (相似度 × (评分 - 平均分)) → 排序输出
```

### 3. Content 引擎 [`engines/content/engine.py`](file:///e:/bangumi/recommender/engines/content/engine.py)

**算法**：基于内容的向量相似度推荐

**核心模型**：[`ContentRecommenderV2`](file:///e:/bangumi/recommender/engines/content/recommender.py#L16)

**特征文件**：`models/content/content_features_v2.pt`

**特征维度**：
| 维度 | 来源 |
|------|------|
| staff | 制作人员 BGE 嵌入 |
| va | 声优 BGE 嵌入 |
| tag | 标签 TF-IDF |
| meta | 元数据特征 |

**推荐流程**：
```
看过(含评分) + 想看 → 构建用户向量(加权平均) → 
与所有动画向量计算余弦相似度 → 排除已看过 → 
生成推荐理由(breakdown + 标签 + 人员) → 输出
```

### 4. Hot 引擎 [`engines/hot/engine.py`](file:///e:/bangumi/recommender/engines/hot/engine.py)

**算法**：热度加权排序（非个性化）

**评分公式**：
```
热度分 = (想看权重 × 归一化想看数 + 看过权重 × 归一化看过数 + 评分权重 × 归一化评分) × 时间衰减
```

**时间衰减**：半衰期 360 天的指数衰减

### 5. LLM 引擎 [`engines/llm/engine.py`](file:///e:/bangumi/recommender/engines/llm/engine.py)

**状态**：占位实现，当前返回空列表（默认 `ENABLE_LLM = False`）

---

## 六、调度层 (`scheduler/`)

### 1. 季度爬取 [`seasonal.py`](file:///e:/bangumi/recommender/scheduler/seasonal.py)

**职责**：爬取指定季度的动画信息。

**数据流向**：
```
调用 API 获取季度列表 → 获取每个动画详情 → 对比放送日历 → 
标记已完结 → 写入 seasonal.db → 记录日志
```

### 2. 完结状态更新 [`db_updater.py`](file:///e:/bangumi/recommender/scheduler/db_updater.py)

**职责**：定期检查未完结动画，更新完结状态。

**更新流程**：
```
查询未完成列表 → 获取当前放送日历 → 
不在放送中 → 获取详情 → 标记完结 → 同步到 anime_meta.db → 
评分人数不足则丢弃
```

---

## 整体数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                     用户请求                                  │
│              (CLI / HTTP API)                                │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   main.py                                    │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │ 用户验证    │───▶│ 获取收藏数据  │───▶│ 构建上下文     │  │
│  └─────────────┘    └──────┬───────┘    └────────┬───────┘  │
│                            │                     │          │
│                   ┌────────▼────────┐            │          │
│                   │ Bangumi API     │            │          │
│                   │ (api_client)    │            │          │
│                   └────────┬────────┘            │          │
│                            │                    │          │
│                   ┌────────▼────────┐   ┌────────▼───────┐  │
│                   │ API 缓存        │   │ 同步到 DB      │  │
│                   │ (api_cache.db)  │   │ (sync_db)      │  │
│                   └─────────────────┘   └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     推荐缓存检查                              │
│              (recommend_cache.db)                             │
└──────────────────┬──────────────────────────────────────────┘
                   ▼ (未命中)
┌─────────────────────────────────────────────────────────────┐
│                   引擎路由                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  收藏≤50:  Content + Hot + LLM                       │   │
│  │  GCN用户:    GCN + LLM                               │   │
│  │  收藏丰富:   ItemCF + Content + LLM                   │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   各引擎并行推荐                               │
│  ┌──────┐  ┌────────┐  ┌─────────┐  ┌─────┐  ┌─────┐       │
│  │ GCN  │  │ ItemCF │  │ Content │  │ Hot │  │ LLM │       │
│  └──┬───┘  └───┬────┘  └────┬────┘  └──┬──┘  └──┬──┘       │
│     │          │             │          │        │           │
│  ┌──▼──────────▼─────────────▼──────────▼────────▼──┐       │
│  │             各引擎返回列表 [RecommendItem]         │       │
│  └───────────────────────────────────────────────────┘       │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   结果融合                                    │
│  归一化 → 加权 → 合并 → 排序 → Top-K                         │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   缓存 + 输出                                 │
│  写入 recommend_cache.db → 返回 JSON                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据库汇总

| 数据库文件 | 用途 | 主要操作者 |
|-----------|------|-----------|
| `user_interactions.db` | 用户收藏数据 | `sync_db`, `api_client` |
| `anime_meta.db` | 动画元数据 | `anime_db` |
| `api_cache.db` | API 响应缓存 | `api_cache` |
| `seasonal.db` | 季度动画数据 | `seasonal`, `db_updater` |
| `recommend_cache.db` | 推荐结果缓存 | `recommend_cache` |