# Bangumi 推荐系统 — 引擎层 (engines/)

系统包含 5 个推荐引擎，均继承 `BaseRecommender`，独立产生推荐结果后由 `WeightedFusion` 加权融合。

---

## 一、GCN 引擎 — 图神经网络推荐

### 技术栈

- **模型**: LightGCN（自实现，3 层图卷积）
- **嵌入维度**: 64
- **输入**: `models/gcn/train.txt`（用户-物品交互）、`models/gcn/all.txt`（全量交互）
- **映射**: `models/gcn/user_list.txt`、`models/gcn/item_list.txt`（Bangumi ID ↔ GCN ID）
- **预计算**: `s_pre_adj_mat.npz`（归一化邻接矩阵，加速推理）

### 文件结构

```
engines/gcn/
├── engine.py           # 引擎入口，GCNRecommender
└── lightgcn/
    ├── __init__.py
    ├── model.py        # LightGCN 模型定义
    ├── world.py         # 全局配置 (设备、超参数)
    ├── dataloader.py    # 数据加载、邻接矩阵构建
    └── register.py     # 数据集实例化
```

### 推荐流程

```
recommend(ctx, top_k)
│
├── 1. 延迟加载模型 (首次调用时)
│   ├── 读取 train.txt 构建交互矩阵
│   ├── 构建/加载归一化邻接矩阵 S = D^(-1/2) A D^(-1/2)
│   ├── 初始化 Embedding 层 (n_users + m_items) × 64
│   └── 加载预训练 checkpoint
│
├── 2. 获取 GCN 用户 ID
│   └── id_mapping.get_gcn_user_id(ctx.user_id)
│   └── 若不在训练集中 → 返回 []
│
├── 3. 确定排除集合
│   └── all_exclude = 用户已交互项 ∪ ctx.gcn_exclude_items
│
├── 4. 推理评分
│   ├── 无 Warm-start:
│   │   └── model.getUsersRating(user_tensor) → 全量物品评分
│   │
│   └── 有 Warm-start (用户看过新物品但未在 train.txt):
│       ├── 取用户嵌入 user_emb
│       ├── 取新物品嵌入均值 new_signal (warm_items 向量平均)
│       ├── 融合: updated = 0.5 × user_emb + 0.5 × new_signal
│       └── 用融合后的向量计算全量评分
│
├── 5. 排除已交互项 + Top-K
│   └── ratings[exclude_items] = -inf
│   └── torch.topk → top_k 个最高分
│
└── 6. 映射回 Bangumi ID + 补充元数据
    └── lookup_subject(mapped_item_id) → 若为 None 则跳过该物品
    └── get_anime_name / get_anime_rating
```

### Warm-Start 机制

当用户有新的交互（看过但在 GCN 训练数据 `train.txt` 中未出现），不重新训练模型，而是：

```
updated_user_emb = α × learned_user_emb + (1-α) × mean(new_item_embs)
```

其中 `α = 0.5`（配置为 `WARM_ALPHA`）。

### 数据文件

| 文件 | 格式 | 说明 |
|------|------|------|
| `train.txt` | `uid i1 i2 i3 ...` | 每行一个用户及其交互物品 |
| `all.txt` | `uid i1 i2 i3 ...` | 全量交互（含验证集） |
| `user_list.txt` | 每行一个 user_id | Bangumi user_id 列表 |
| `item_list.txt` | 每行一个 subject_id | Bangumi subject_id 列表 |

---

## 二、ItemCF 引擎 — 物品协同过滤

### 原理

基于物品相似度的协同过滤，使用**用户评分偏差**加权：
- 用户对物品 `i` 的评分 `r_i` 高于均分 → 该物品相似物品获得正向加权
- 低于均分 → 负向加权

### 推荐流程

```
recommend(ctx, top_k)
│
├── 1. 加载相似度矩阵 (JSON)
│   └── item_similarity_final.json
│   └── {subject_id: [(sim_subject_id, similarity), ...]}
│   └── 延迟加载，首次调用时解析
│
├── 2. 遍历用户已评分的动画
│   └── 对每个 (sid, rate):
│       ├── 获取 sid 的相似物品列表
│       ├── 排除已看物品
│       └── score[sim_id] += similarity × (rate - user_mean)
│
├── 3. 降序排序取 top_k
│
└── 4. 补充元数据 → RecommendItem
```

### 评分偏差公式

```
predict(user, item_j) = Σ similarity(item_i, item_j) × (rating(user, item_i) - mean_rating(user))
```

---

## 三、Content 引擎 — 内容向量推荐

### 特征来源

基于 `content_features_v2.pt`（`models/content/` 目录），包含以下特征：

| 特征维度 | 说明 | 来源 |
|---------|------|------|
| `staff_dense` | 制作人员向量 | infobox 中核心人员/主要人员 |
| `va_dense` | 声优向量 | infobox 中核心声优/主要声优 |
| `tag_tfidf_dense` | 标签 TF-IDF 向量 | Bangumi tags |
| `meta_dense` | 元信息向量 | 类型、平台等 |

四种特征拼接为统一的 `anime_vectors`。

### 用户画像构建

```
build_user_vector(watched: Dict[subject_id, rating], wished: List[subject_id])
│
├── 对已看动画:
│   ├── rating ≥ mean_rating → weight = WATCHED_HIGH_WEIGHT (2.0)
│   └── rating < mean_rating → weight = WATCHED_LOW_WEIGHT (0.5)
│
├── 对想看动画:
│   └── weight = WISHED_WEIGHT (1.0)
│
└── 加权平均 → L2 归一化 → 用户画像向量
```

### 相似度匹配

```
similarity = anime_vectors • user_vector  (点积 = 余弦相似度)

排除已看 + 想看 → torch.topk → top_k
```

### 推荐理由生成

- 匹配动画的 Top-3 标签
- 匹配动画的 Top-2 制作人员
- 匹配动画的 Top-2 声优
- 分维度 breakdown: `{staff: 0.xx, va: 0.xx, tag: 0.xx, meta: 0.xx}`

---

## 四、Hot 引擎 — 热度排序推荐

### 推荐流程

```
recommend(ctx, top_k)
│
├── 调用 get_hot_items(top_k, min_rating_count)
│   │
│   ├── 1. 从 anime_meta.db 查询
│   │   └── 条件: score > 0 AND 收藏数 ≥ min_rating_count
│   │   └── 字段: score, favorite_wish, favorite_watch, date
│   │
│   ├── 2. 分维度 Max 归一化
│   │   ├── watching 归一化 (看过数 / max_watching)
│   │   ├── wish 归一化 (想看数 / max_wish)
│   │   └── rating 归一化 (评分 / 10.0) × weight
│   │
│   ├── 3. 加权求和
│   │   └── hot = 0.35×wish_norm + 0.35×watched_norm + 0.30×rating_norm
│   │
│   ├── 4. 时间衰减
│   │   └── factor = e^(-ln(2) × days / 360)
│   │   └── hot *= factor
│   │
│   └── 5. 降序排序取 top_k
│
└── 补充元数据 → RecommendItem
```

### 参数配置

| 参数 | 值 | 说明 |
|------|-----|------|
| `HOT_WEIGHT_WATCHED` | 0.35 | "看过"维度权重 |
| `HOT_WEIGHT_WISHED` | 0.35 | "想看"维度权重 |
| `HOT_WEIGHT_RATING` | 0.30 | 评分维度权重 |
| `HOT_MIN_RATING_COUNT` | 2000 | 最低评分人数要求 |
| `HOT_TIME_DECAY_HALF_LIFE_DAYS` | 360 | 时间衰减半衰期（天） |

### 特点

- **不依赖用户个人数据**：对所有用户返回相同结果
- **实时计算**：每次推荐都从数据库查询最新热度
- 衰减函数使老番分数随时间自然降低

---

## 五、LLM 引擎 — 语义嵌入推荐

### 技术栈

- **嵌入来源**: `crawler/scripts/embed_anime.py` 使用 BGE-small-zh-v1.5 对 overall_comment 批量编码
- **嵌入文件**: `embeddings.npy` + `index.json`
- **向量维度**: 512
- **无需加载 BGE 模型**: 仅使用预计算嵌入

### 推荐流程

```
recommend(ctx, top_k)
│
├── 1. 前置检查
│   ├── ctx.history_ratings 为空 → 返回 []
│   └── len(history_ratings) < LLM_MIN_RATED_COUNT (3) → 返回 []
│
├── 2. 延迟加载 LLMEmbeddingStore
│   ├── 加载 embeddings.npy (N×512, float32, L2 归一化)
│   ├── 加载 index.json ([{subject_id, comment_len}, ...])
│   └── 构建 subject_id → row_index 映射
│
├── 3. 构建用户画像
│   ├── 计算用户平均评分 mean_rating
│   ├── 筛选 rating ≥ mean_rating 的「高质量已看」
│   ├── 若全同分 → 回退使用全部已看
│   ├── 过滤不在嵌入索引中的动画
│   ├── 对筛选动画的嵌入取均值 → 用户画像向量
│   └── L2 归一化
│
├── 4. 相似度匹配
│   ├── scores = embeddings • user_vector (点积 = 余弦相似度)
│   ├── 排除已看 + 想看
│   ├── argpartition + argsort 取 top_k
│   └── 返回 [{subject_id, similarity, idx}, ...]
│
└── 5. 补充元数据 → RecommendItem
```

### 用户画像构建公式

```
avg = mean(user ratings)
high_rated = {sid | rating(sid) ≥ avg}
profile = mean( embeddings[high_rated] )
profile = L2_normalize(profile)
```

### 边界处理

| 情况 | 行为 |
|------|------|
| 无评分记录 | 返回 `[]` |
| 评分 < 3 条 | 返回 `[]` |
| 全部同分 | 回退使用全部已看 |
| 已看动画不在嵌入索引中 | 跳过 |
| 全部已看无嵌入 | 返回 `[]` |
| 嵌入文件不存在 | 引擎初始化失败，不参与路由 |

### 与 Content 引擎的区别

| 维度 | Content | LLM |
|------|---------|-----|
| 特征 | staff/VA/tag 结构化特征 | overall_comment 语义嵌入 |
| 关注 | 「制作阵容相似」 | 「观众评价语义相似」 |
| 画像 | 看过 + 想看加权 | 仅高于均分的已看 |
| 相似度 | 分维度 break down | 纯余弦相似度 |

---

## 六、引擎对比

| 特性 | GCN | ItemCF | Content | Hot | LLM |
|------|-----|--------|---------|-----|-----|
| 个性化 | ✓ | ✓ | ✓ | ✗ | ✓ |
| 冷启动 | ✗ (需在训练集) | ✗ (需有评分) | ✓ (有想看即可) | ✓ (无依赖) | ✗ (需 ≥3 评分) |
| 可解释性 | 低 | 中 | 高 (标签/人员) | 低 | 中 (语义相似度) |
| 训练依赖 | 高 (需 GPU 训练) | 中 (需预计算) | 中 (需预计算) | 低 (实时计算) | 低 (需预计算) |
| 更新频率 | 需要重训 | 低 | 低 | 实时 | 低 |
