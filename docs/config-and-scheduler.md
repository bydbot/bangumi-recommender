# Bangumi 推荐系统 — 配置与调度

---

## 一、全局配置 (`config.py`)

### 路径配置

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DB_DIR = os.path.join(BASE_DIR, "db")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
```

### 数据库路径

| 变量 | 值 | 用途 |
|------|-----|------|
| `USER_INTERACTIONS_DB` | `db/user_interactions.db` | 用户收藏与评分 |
| `ANIME_META_DB` | `db/anime_meta.db` | 动画元数据 |
| `API_CACHE_DB` | `db/api_cache.db` | API 响应缓存 |
| `SEASONAL_DB` | `db/seasonal.db` | 季度动画 |
| `RECOMMEND_CACHE_DB` | `db/recommend_cache.db` | 推荐结果缓存 |

### 数据文件路径

| 变量 | 值 | 用途 |
|------|-----|------|
| `ANIME_JSONLINES` | `e:/bangumi/bangumi/Animes.jsonlines` | 动画元数据导入源 |
| `ANIME_NODES_CSV` | `models/meta/anime_nodes.csv` | 动画节点 CSV |

### GCN 配置

| 变量 | 值 | 说明 |
|------|-----|------|
| `GCN_DATA_DIR` | `models/gcn` | GCN 数据目录 |
| `GCN_CHECKPOINT` | `lgn-bangumi-epoch90.pth.tar` | 模型检查点 |
| `GCN_DATASET` | `"bangumi"` | 数据集名称 |
| `WARM_ALPHA` | 0.5 | Warm-start 融合系数 |

### ItemCF 配置

| 变量 | 值 | 说明 |
|------|-----|------|
| `ITEMCF_SIM_PATH` | `models/itemcf/item_similarity_final.json` | 相似度矩阵 |

### API 配置

| 变量 | 值 | 说明 |
|------|-----|------|
| `BANGUMI_API_BASE` | `https://api.bgm.tv` | API 根地址 |
| `BANGUMI_USER_AGENT` | `Indie_guy(...)` | User-Agent |
| `ACCESS_TOKEN` | `None` | Bearer Token（运行时设置） |
| `API_REQUEST_DELAY` | `1.0` | 请求间隔（秒） |
| `API_MAX_RETRIES` | `3` | 最大重试次数 |
| `API_CACHE_TTL_HOURS` | `168` | API 缓存有效期（7 天） |

### Hot 引擎参数

| 变量 | 值 | 说明 |
|------|-----|------|
| `HOT_WEIGHT_WATCHED` | `0.35` | "看过"维度权重 |
| `HOT_WEIGHT_WISHED` | `0.35` | "想看"维度权重 |
| `HOT_WEIGHT_RATING` | `0.30` | 评分维度权重 |
| `HOT_MIN_RATING_COUNT` | `2000` | 最低评分人数 |
| `HOT_TIME_DECAY_HALF_LIFE_DAYS` | `360` | 半衰期（天） |
| `HOT_NORMALIZE_RATING_SCALE` | `10.0` | 评分归一化上限 |

### LLM 引擎参数

| 变量 | 值 | 说明 |
|------|-----|------|
| `ENABLE_LLM` | `True` | LLM 引擎开关 |
| `LLM_EMBEDDINGS_DIR` | `E:\bangumi\crawler\embeddings` | 嵌入向量目录 |
| `LLM_MIN_RATED_COUNT` | `3` | 用户最少评分数量 |

### 推荐缓存

| 变量 | 值 | 说明 |
|------|-----|------|
| `RECOMMEND_CACHE_TTL_HOURS` | `168` | 推荐缓存有效期（7 天） |

### 融合权重

```python
FUSION_WEIGHTS_BY_PROFILE = {
    "small_collection": {           # 收藏 ≤ 50
        EngineName.CONTENT: 0.30,
        EngineName.HOT: 0.40,
        EngineName.LLM: 0.30,
    },
    "gcn_user": {                   # GCN 训练集中
        EngineName.GCN: 0.60,
        EngineName.LLM: 0.40,
    },
    "rich_no_gcn": {                # 收藏多但不在 GCN
        EngineName.ITEMCF: 0.40,
        EngineName.CONTENT: 0.30,
        EngineName.LLM: 0.30,
    },
}
```

---

## 二、调度层 (scheduler/)

### 季度新番爬取 (`scheduler/seasonal.py`)

#### 入口

```bash
python main.py crawl-season --year 2025 --month 4
```

#### 流程

```
crawl_and_persist(year, month)
│
├── 1. browse_seasonal(year, month)
│   ├── GET /p1/subjects (type=2, 动画)
│   └── 遍历 month 和 month+1 两个月的全部页面
│   → 返回 List[SlimSubject]
│
├── 2. get_subject_detail(subject_id)
│   └── 对每部动画获取详情
│   → 返回 List[Subject]
│
├── 3. fetch_calendar()
│   └── GET /calendar → 当前在播动画 ID 集合
│   └── 不在在播集合中的标记为 is_completed=True
│
├── 4. 存入 seasonal.db (seasonal_anime 表)
│   ├── INSERT OR REPLACE
│   └── 记录 update_log
│
└── 5. 输出统计
    └── 总爬取数 / 已完结数
```

#### 数据库 (`seasonal.db`)

**`seasonal_anime`** 表:

| 字段 | 类型 | 说明 |
|------|------|------|
| `subject_id` | INTEGER UNIQUE | 动画 ID |
| `name` / `name_cn` | TEXT | 名称 |
| `summary` | TEXT | 简介 |
| `meta_tags` | TEXT (JSON) | 元标签 |
| `rating_score` | REAL | 评分 |
| `rating_total` | INTEGER | 评分人数 |
| `wish_count` | INTEGER | 想看人数 |
| `watch_count` | INTEGER | 看过人数 |
| `airtime_date` / `year` / `month` | TEXT/INT | 播出时间 |
| `season_label` | TEXT | 季度标识 (如 "2025-04") |
| `is_completed` | INTEGER | 是否已完结 (0/1) |
| `crawled_at` / `updated_at` | TEXT | 时间戳 |

**`update_log`** 表:

| 字段 | 类型 | 说明 |
|------|------|------|
| `season_label` | TEXT | 季度标识 |
| `crawled_count` | INTEGER | 本次爬取数 |
| `completed_count` | INTEGER | 已完结数 |
| `started_at` / `finished_at` | TEXT | 开始/结束时间 |

---

### 完结状态更新 (`scheduler/db_updater.py`)

#### 入口

```bash
python main.py update-db
```

#### 流程

```
update_completed_anime()
│
├── 1. 查询 seasonal_anime 中 is_completed=0 的所有条目
│
├── 2. fetch_calendar() → 获取在播动画 ID 集合
│
├── 3. 对每个不在播的动画:
│   ├── get_subject_detail(sid) → 获取详情
│   ├── 若 rating_total < min_rating_count → 丢弃删除
│   └── 否则:
│       ├── 更新 seasonal_anime: is_completed=1, 评分/收藏数
│       └── insert_or_replace_anime() → 同步到 anime_meta.db
│
└── 4. 输出统计
    └── 完结数 / 同步到动画条目数
```

#### 使用时机

- 季度结束后运行，标记已完结动画
- 定期运行，同步最新评分和收藏数据
- 自动过滤评分人数过少的动画（可能是冷门/错误条目）

---

## 三、Content 引擎配置 (`engines/content/config.py`)

| 变量 | 值 | 说明 |
|------|-----|------|
| `BGE_MODEL_DIR` | `models/content/bge-small-zh-v1.5` | BGE 模型路径 |
| `FEATURE_PATH` | `models/content/content_features_v2.pt` | 预计算特征文件 |
| `WATCHED_HIGH_WEIGHT` | `2.0` | 高于均分的已看权重 |
| `WATCHED_LOW_WEIGHT` | `0.5` | 低于均分的已看权重 |
| `WISHED_WEIGHT` | `1.0` | 想看动画的权重 |
| `VALID_STAFF_CATEGORIES` | `{"核心人员", "主要人员"}` | 参与画像的 STAFF 类别 |
| `VALID_VA_CATEGORIES` | `{"核心声优", "主要声优"}` | 参与画像的声优类别 |

---

## 四、LightGCN 超参数 (`engines/gcn/lightgcn/world.py`)

| 参数 | 值 | 说明 |
|------|-----|------|
| `latent_dim_rec` | 64 | 嵌入向量维度 |
| `lightGCN_n_layers` | 3 | 图卷积层数 |
| `dropout` | 0 | Dropout 率（未使用） |
| `keep_prob` | 0.6 | 保留概率（未使用） |
| `A_split` | False | 不分拆邻接矩阵 |
| `device` | cuda/cpu 自动 | 推理设备 |

---

## 五、数据依赖关系概览

```
models/
├── gcn/
│   ├── train.txt               # GCN 训练数据
│   ├── all.txt                 # 全量交互数据
│   ├── user_list.txt           # 用户 ID 映射
│   ├── item_list.txt           # 物品 ID 映射
│   ├── lgn-bangumi-epoch90.pth.tar  # 模型检查点
│   └── s_pre_adj_mat.npz       # 预计算邻接矩阵
│
├── itemcf/
│   └── item_similarity_final.json  # 物品相似度矩阵
│
├── content/
│   ├── bge-small-zh-v1.5/      # BGE 模型文件
│   └── content_features_v2.pt  # 预计算特征向量
│
└── meta/
    └── anime_nodes.csv         # 动画节点数据

db/
├── user_interactions.db        # 用户收藏
├── anime_meta.db               # 动画元数据
├── api_cache.db                # API 缓存
├── recommend_cache.db          # 推荐缓存
└── seasonal.db                 # 季度数据

crawler (外部依赖)/
├── embeddings/
│   ├── embeddings.npy          # overall_comment 嵌入
│   └── index.json              # 嵌入索引
└── bge-small-zh-v1.5/          # BGE 模型（embed_anime.py 用）

bangumi (外部数据)/
└── Animes.jsonlines            # 动画元数据（已废弃，改用 API 同步）
```

---

## 六、预留功能 / 扩展点

### 1. LLM 引擎扩展

当前 LLM 引擎基于 overall_comment 嵌入。预留扩展方向：

- **多模态语义**: 融合简介、标签文本、用户评论等多源文本的嵌入
- **LLM 生成推荐理由**: 调用 LLM API 生成个性化推荐文案
- **动态画像更新**: 用户每次评分后实时更新画像向量
- **负反馈建模**: 利用用户低分动画做负向筛选

### 2. 引擎热插拔

`init_engines()` 中的 try/except 模式允许引擎加载失败时静默跳过。新增引擎只需：

1. 在 `EngineName` 中注册
2. 实现 `BaseRecommender`
3. 在 `init_engines()` 中添加 try/except 块
4. 在 `FUSION_WEIGHTS_BY_PROFILE` 中配置权重
5. 在 `RecommendRouter.get_engine_names()` 中调整路由

### 3. 融合策略扩展

当前仅支持加权融合。预留扩展点：

- **级联融合**: 先用高精度引擎，再对候选集用其他引擎重排
- **多样性重排**: MMR (Maximal Marginal Relevance) 避免结果同质化
- **上下文融合**: 根据请求时间、用户活跃度等动态调整权重

### 4. 实时反馈

- **点击率追踪**: 记录用户对推荐结果的点击行为
- **A/B 测试框架**: 比较不同引擎组合的效果
- **冷启动兜底**: 对于无历史数据的新用户，纯靠 Hot + Content 引擎

### 5. 数据管线

- **增量更新**: 定期 cron 任务自动运行 `update-db` 和 `crawl-season`
- **模型重训**: GCN/ItemCF 模型的周期性重训流程
- **嵌入刷新**: overall_comment 嵌入随新评论定期重新编码
