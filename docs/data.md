# Bangumi 推荐系统 — 数据层 (data/)

数据层负责用户交互存储、动画元数据管理、API 调用与缓存、GCN ID 映射、热度计算和推荐缓存。

---

## 一、用户收藏同步 (`data/sync_db.py`)

### 数据库

- **文件**: `db/user_interactions.db`
- **表**: `user_collections`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `user_id` | TEXT | PK, NOT NULL | Bangumi 用户 ID |
| `subject_id` | INTEGER | PK, NOT NULL | 动画 ID |
| `rate` | REAL | - | 用户评分（仅看过有） |
| `collect_type` | INTEGER | PK, NOT NULL | 1=想看, 2=看过 |
| `updated_at` | TEXT | - | ISO 时间戳 |

联合主键: `(user_id, subject_id, collect_type)`

### 接口

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `init_user_db(db_path)` | - | - | 建表 |
| `sync_user_interactions(user_id, watched, wished)` | 用户 ID + CollectionItem 列表 | - | 先删后插：清空该用户所有记录，重新插入 |
| `load_watched_from_db(user_id)` | 用户 ID | `List[int]` | `collect_type=2` 的 subject_id 列表 |
| `load_wished_from_db(user_id)` | 用户 ID | `List[int]` | `collect_type=1` 的 subject_id 列表 |
| `load_history_ratings(user_id)` | 用户 ID | `Dict[int,float]` | `{subject_id: rate}` 评分字典 |

### 数据流

```
API 收藏数据 → fetch_watched_and_wished()
  ├── 写入 api_cache.db (API 缓存)
  └── 同步到 user_interactions.db (sync_user_interactions)

推荐时:
  user_interactions.db → _build_context()
    ├── load_watched_from_db()    → watched_subject_ids
    ├── load_wished_from_db()     → wished_subject_ids
    └── load_history_ratings()    → history_ratings
```

---

## 二、动画元数据 (`data/anime_db.py`)

### 数据库

- **文件**: `db/anime_meta.db`
- **表**: `anime_entries` (28 个字段)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | Bangumi subject_id |
| `name` | TEXT | 原始名称 |
| `name_cn` | TEXT | 中文名称 |
| `type` | INTEGER | 类型 (2=动画) |
| `infobox` | TEXT (JSON) | 包含 STAFF、声优等信息 |
| `platform` | INTEGER | 平台 |
| `summary` | TEXT | 简介 |
| `nsfw` | BOOLEAN | 是否成人内容 |
| `tags` | TEXT (JSON) | Bangumi 标签 |
| `meta_tags` | TEXT (JSON) | 元标签 |
| `score` | REAL | Bangumi 评分 |
| `score_details` | TEXT (JSON) | 评分分布 |
| `rank` | INTEGER | 排名 |
| `date` | TEXT | 播出日期 |
| `series` | BOOLEAN | 是否为系列 |
| `favorite_wish` | INTEGER | 想看人数 |
| `favorite_watch` | INTEGER | 看过人数 |
| `favorite_doing` | INTEGER | 在看人数 |
| `favorite_on_hold` | INTEGER | 搁置人数 |
| `favorite_dropped` | INTEGER | 抛弃人数 |
| `episode_ids` | TEXT (JSON) | 章节 ID 列表 |
| `created_at` | TEXT | - |
| `updated_at` | TEXT | - |

### 接口

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `init_anime_db(db_path)` | - | - | 建表 |
| `import_anime_jsonlines(jsonlines_path)` | Animes.jsonlines 路径 | - | 从 `Animes.jsonlines` 批量导入 |
| `insert_or_replace_anime(data)` | dict | - | 插入或替换单条 |
| `get_anime_meta(subject_id)` | int | `{name, name_cn, score}` | 获取动画基本元数据 |
| `get_anime_name(subject_id)` | int | str | 优先中文名，回退日文名 |
| `get_anime_rating(subject_id)` | int | float | 获取 Bangumi 评分 |

### 数据来源

- **批量导入**: `python main.py import-anime` → 从 `e:/bangumi/bangumi/Animes.jsonlines`
- **增量更新**: `scheduler/db_updater.py` 在标记完结时同步

---

## 三、API 客户端 (`data/api_client.py`)

### Bangumi API 调用

| 函数 | API 端点 | 说明 |
|------|---------|------|
| `check_user_exists(username)` | `GET /v0/users/{username}` | 检查用户是否存在 |
| `fetch_collections(username, collect_type)` | `GET /v0/users/{username}/collections` | 分页获取收藏（type=1想看, 2看过） |
| `fetch_watched_and_wished(username, force_refresh)` | - | 获取看过+想看，带缓存 |
| `get_subject_detail(subject_id)` | `GET /p1/subjects/{subject_id}` | 获取动画详情 |
| `browse_seasonal(year, month)` | `GET /p1/subjects` | 按季度浏览动画 |
| `fetch_calendar()` | `GET /calendar` | 获取在播动画日历 |

### 请求管理

| 配置 | 值 | 说明 |
|------|-----|------|
| `BANGUMI_API_BASE` | `https://api.bgm.tv` | API 基础地址 |
| `API_REQUEST_DELAY` | 1.0 秒 | 请求间隔（避免限流） |
| `API_MAX_RETRIES` | 3 | 最大重试次数 |
| Access Token | 运行时设置 | Bearer Token 认证 |
| 429 处理 | 等待 60 秒后重试 | 频率限制应对 |

### 类型定义 (`data/api_types.py`)

| 类型 | 用途 |
|------|------|
| `SlimSubject` | 季度浏览返回的简化动画信息 |
| `CollectionItem` | 用户收藏条目（含评分） |
| `Subject` | 动画详情（完整字段） |
| `SeasonalAnime` | 季度动画完整信息 |

---

## 四、API 缓存 (`data/api_cache.py`)

### 数据库

- **文件**: `db/api_cache.db`
- **表**: `collection_cache`
- **TTL**: 168 小时（7 天）

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | TEXT PK | 用户 ID |
| `watched_json` | TEXT | 看过列表 (JSON) |
| `wished_json` | TEXT | 想看列表 (JSON) |
| `fetched_at` | TEXT | 获取时间 (ISO) |

### 接口

| 方法 | 说明 |
|------|------|
| `get(user_id)` | 获取缓存，过期返回 None |
| `set(user_id, watched, wished)` | 写入缓存 |
| `is_fresh(user_id)` | 检查缓存是否新鲜 |

---

## 五、推荐结果缓存 (`data/recommend_cache.py`)

### 数据库

- **文件**: `db/recommend_cache.db`
- **表**: `recommend_cache`
- **TTL**: 168 小时

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增 |
| `user_id` | TEXT | 用户 ID |
| `engine_combo` | TEXT | 引擎组合标识（如 "gcn+llm"） |
| `top_k` | INTEGER | 推荐数量 |
| `result_json` | TEXT | 推荐结果 (JSON) |
| `created_at` | TEXT | 创建时间 |
| UNIQUE | - | `(user_id, engine_combo, top_k)` |

### 接口

| 方法 | 说明 |
|------|------|
| `get(user_id, engine_combo, top_k)` | 获取缓存 |
| `get_for_user(ctx, top_k, available_engines)` | 自动推断 engine_combo |
| `set(user_id, engine_combo, top_k, result)` | 写入缓存 |
| `clear(user_id=None)` | 清理缓存（指定用户或全部） |

### engine_combo 计算

```python
# 由 RecommendRouter.get_engine_names() 决定
# 示例: ["gcn", "llm"] → "gcn+llm"
combo = "+".join(engine_name.value for engine_name in names)
```

---

## 六、GCN ID 映射 (`data/mappings.py`)

### 数据文件

| 文件 | 格式 | 说明 |
|------|------|------|
| `models/gcn/item_list.txt` | 每行一个 subject_id | Bangumi Subject ID → GCN Item ID |
| `models/gcn/user_list.txt` | 每行一个 user_id | Bangumi User ID → GCN User ID |

### IDMapping 类

| 方法 | 说明 |
|------|------|
| `lookup_gcn_item(subject_id)` | Bangumi Subject ID → GCN Item ID，找不到返回 None |
| `lookup_subject(mapped_id)` | GCN Item ID → Bangumi Subject ID，找不到返回 None |
| `is_gcn_user(user_id)` | 用户是否在 GCN 训练集中 |
| `get_gcn_user_id(user_id)` | 获取 GCN 用户 ID，不在则返回 None |
| `subjects_to_gcn_items(subject_ids)` | 批量转换，自动过滤无映射的 |

### 全局单例

```python
_id_mapping = IDMapping()  # 模块加载时自动初始化

def get_id_mapping() -> IDMapping:
    return _id_mapping
```

---

## 七、热度计算 (`data/db.py`)

### get_hot_items()

```
get_hot_items(top_k=100, min_rating_count=30) → List[(subject_id, hot_score)]
│
├── 1. 从 anime_meta.db 查询所有评分 > 0 的动画
│
├── 2. 分维度 Max 归一化
│   ├── wish_norm  = favorite_wish / max(favorite_wish)
│   ├── watch_norm = favorite_watch / max(favorite_watch)
│   └── rating_norm = score / 10.0
│
├── 3. 加权求和
│   └── hot = 0.35×wish_norm + 0.35×watch_norm + 0.30×rating_norm
│
├── 4. 时间衰减
│   └── factor = e^(-ln(2) × days_since_air / 360)
│   └── hot *= factor
│
└── 5. 降序排序取 top_k
```

### 时间衰减曲线

```
衰减因子
1.0 ┤***
    │   ╲
0.7 ┤     ╲__
    │        ╲__
0.5 ┤           ╲___
    │               ╲_________
0.2 ┤                        ╲_________

    0     180    360    540    720 (天)
```

半衰期 360 天，即一部动画播出 360 天后热度衰减为原来的 50%。

---

## 八、文件依赖关系

```
data/api_client.py
  ├── data/api_types.py (类型定义)
  └── data/api_cache.py (API 缓存)

data/sync_db.py
  └── data/api_types.py (CollectionItem)

data/anime_db.py
  └── config.py (ANIME_JSONLINES)

data/mappings.py
  └── config.py (GCN_DATA_DIR)

data/db.py
  └── config.py (ANIME_META_DB)

data/recommend_cache.py
  ├── config.py
  └── core/router.py (判定 engine_combo)
```
