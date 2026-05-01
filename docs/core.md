# Bangumi 推荐系统 — 核心层 (core/)

核心层定义了推荐系统的基础数据结构、引擎接口、路由策略和融合算法。所有引擎只需实现统一接口即可接入。

---

## 一、类型定义 (`core/types.py`)

### 引擎名称枚举

```python
class EngineName(str, Enum):
    GCN     = "gcn"
    ITEMCF  = "itemcf"
    CONTENT = "content"
    HOT     = "hot"
    LLM     = "llm"
```

继承 `str` 和 `Enum`，可直接用于字符串比较和序列化。

### 推荐结果条目 (`RecommendItem`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rank` | `int` | - | 排名（1-based） |
| `subject_id` | `int` | - | Bangumi 动画 ID |
| `name` | `str` | `""` | 原始名称 |
| `name_cn` | `str` | `""` | 中文名称 |
| `score` | `float` | - | 推荐分数 |
| `source` | `EngineName` | - | 来源引擎 |
| `is_wished` | `bool` | `False` | 是否在用户想看列表中 |
| `reasons` | `List[str]` | `[]` | 推荐理由 |
| `breakdown` | `Dict[str,float]` | `{}` | 各维度分数拆解 |
| `rating_score` | `float` | `0.0` | Bangumi 评分 |

---

## 二、引擎基类 (`core/base.py`)

```python
class BaseRecommender(ABC):
    @abstractmethod
    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        ...

    @property
    @abstractmethod
    def name(self) -> EngineName:
        ...
```

所有推荐引擎必须实现两个成员：

| 成员 | 说明 |
|------|------|
| `recommend(ctx, top_k)` | 接收推荐上下文，返回 `RecommendItem` 列表 |
| `name` (property) | 返回引擎名称枚举值 |

**接口契约**：引擎内部不应修改 `RecommendContext`；若无法产生推荐，返回空列表 `[]` 即可。

---

## 三、推荐上下文 (`core/context.py`)

`RecommendContext` 是贯穿整个推荐流程的数据载体，由 `main.py` 的 `_build_context()` 构建。

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `user_id` | `str` | CLI/API 输入 | 用户 ID |
| `username` | `str` | CLI/API 输入 | 用户名 |
| `watched_subject_ids` | `List[int]` | `sync_db.load_watched_from_db()` | 用户看过的动画 ID |
| `wished_subject_ids` | `Set[int]` | `sync_db.load_wished_from_db()` | 用户想看的动画 ID |
| `history_ratings` | `Dict[int,float]` | `sync_db.load_history_ratings()` | 用户评分记录 |
| `collection_count` | `int` | `len(watched_sids)` | 收藏（看过）总数 |
| `in_training_data` | `bool` | `id_mapping.is_gcn_user()` | 是否在 GCN 训练集中 |
| `gcn_exclude_items` | `List[int]` | GCN item ID 列表 | GCN 引擎需排除的项 |
| `gcn_new_for_warm` | `List[int]` | train.txt 差集 | 用户看过但未在 train.txt 中的新项（Warm-start） |

### 构建过程（`_build_context`）

```
1. 从 user_interactions.db 加载:
   ├── load_watched_from_db(username)   → watched_sids
   ├── load_wished_from_db(username)    → wished_sids
   └── load_history_ratings(username)   → history_ratings

2. 判断是否在 GCN 训练数据中:
   └── id_mapping.is_gcn_user(username)

3. 若在 GCN 中:
   ├── 转换 subject_id → GCN item_id
   └── 从 models/gcn/train.txt 读取训练集，计算 warm_items 差集
```

---

## 四、引擎路由 (`core/router.py`)

`RecommendRouter` 根据用户画像自动选择引擎组合。

### 路由策略

| 条件 | 引擎组合 | Profile Key |
|------|---------|-------------|
| `collection_count ≤ 50` | Content + Hot + LLM | `small_collection` |
| `in_training_data = True` | GCN + LLM | `gcn_user` |
| 以上均不满足 | ItemCF + Content + LLM | `rich_no_gcn` |

### 静态方法

```python
RecommendRouter.get_engine_names(
    collection_count, in_training_data, available_engines
) -> List[EngineName]
```

- 先按画像决定理论引擎集合
- 若 `ENABLE_LLM = False`，移除 LLM
- 若传入 `available_engines`，仅保留实际初始化成功的引擎

### 实例方法

```python
router = RecommendRouter(engines: Dict[EngineName, BaseRecommender])
selected: List[BaseRecommender] = router.route(ctx: RecommendContext)
```

`route()` 内部调用 `get_engine_names()`，返回实际可用的引擎实例列表。

---

## 五、加权融合 (`core/fusion.py`)

`WeightedFusion` 将多路推荐结果合并为最终排序。

### 融合算法

```
输入: results_by_engine: Dict[EngineName, List[RecommendItem]]
      ctx: RecommendContext
      top_k: int

Step 1: 对各引擎结果做 Min-Max 归一化
        score_norm = (score - min) / (max - min)
        若 max == min，全部设为 1.0

Step 2: 归一化分数 × 引擎权重 → weighted_score[subject_id][engine]

Step 3: 合并 — 同一 subject_id 取所有引擎中的最高加权分

Step 4: 降序排序，截取 top_k

Step 5: 标记 is_wished (subject_id ∈ ctx.wished_subject_ids)

Step 6: 重新分配 rank (1-based)

输出: List[RecommendItem]
```

### 融合权重配置

| Profile | GCN | ItemCF | Content | Hot | LLM |
|---------|-----|--------|---------|-----|-----|
| `small_collection` | - | - | 0.30 | 0.40 | 0.30 |
| `gcn_user` | 0.60 | - | - | - | 0.40 |
| `rich_no_gcn` | - | 0.40 | 0.30 | - | 0.30 |

权重仅对实际选中的引擎生效。例如 `small_collection` 用户只选了 Content + Hot + LLM，则权重自动缩放到和为 1。

---

## 六、类图

```
┌─────────────────┐     ┌──────────────────┐
│  RecommendContext│     │   EngineName     │
│  (dataclass)     │     │   (str, Enum)    │
├─────────────────┤     ├──────────────────┤
│ + user_id        │     │ GCN, ITEMCF,     │
│ + username       │     │ CONTENT, HOT, LLM│
│ + watched_sids   │     └──────────────────┘
│ + wished_sids    │              ▲
│ + history_ratings│              │
│ + collection_cnt │     ┌────────┴─────────┐
│ + in_training    │     │  RecommendItem   │
│ + gcn_exclude    │     │  (dataclass)     │
│ + gcn_warm       │     ├──────────────────┤
└────────┬─────────┘     │ + rank            │
         │                │ + subject_id      │
         ▼                │ + name, name_cn   │
┌─────────────────┐      │ + score           │
│ BaseRecommender │      │ + source          │
│ (ABC)           │      │ + is_wished       │
├─────────────────┤      │ + reasons         │
│ + recommend()   │      │ + breakdown       │
│ + name          │      │ + rating_score    │
└────────┬────────┘      └──────────────────┘
         │
         ├── GCNRecommender
         ├── ItemCFRecommender
         ├── ContentBasedRecommender
         ├── HotRecommender
         └── LLMRecommender

┌──────────────────┐     ┌──────────────────┐
│ RecommendRouter  │     │  WeightedFusion  │
├──────────────────┤     ├──────────────────┤
│ + get_engine_names│    │ + merge()         │
│ + route()        │     │ + _min_max_norm() │
│ - available_engines│   │ - weights         │
└──────────────────┘     └──────────────────┘
```

---

## 七、扩展指南

### 新增引擎

1. 在 `core/types.py` 的 `EngineName` 枚举中新增值
2. 创建 `engines/<new_engine>/engine.py`，继承 `BaseRecommender`
3. 实现 `recommend(ctx, top_k) → List[RecommendItem]`
4. 在 `main.py` 的 `init_engines()` 中注册
5. 在 `config.py` 的 `FUSION_WEIGHTS_BY_PROFILE` 中配置权重
6. 在 `RecommendRouter.get_engine_names()` 中调整路由逻辑（可选）

### 新增画像维度

1. 在 `RecommendContext` 中添加字段
2. 在 `_build_context()` 中填充新字段
3. 在 `RecommendRouter` 中使用新字段做路由判断
