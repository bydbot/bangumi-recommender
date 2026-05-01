# Bangumi 推荐系统 — 入口层 (main.py + api.py)

系统提供两种入口：CLI 命令行 和 HTTP API 服务。

---

## 一、CLI 入口 (`main.py`)

### 命令概览

```
python main.py <command> [options]
```

| 命令 | 说明 | 示例 |
|------|------|------|
| `recommend` | 为用户生成推荐 | `python main.py recommend --user 12345` |
| `clear-cache` | 清理推荐缓存 | `python main.py clear-cache --user 12345` |
| `crawl-season` | 爬取当季新番 | `python main.py crawl-season --year 2025 --month 4` |
| `update-db` | 更新动画完结状态 | `python main.py update-db` |
| `import-anime` | 导入动画元数据 | `python main.py import-anime` |

### `recommend` 命令参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--user` | str | (必填) | Bangumi 用户 ID |
| `--top-k` | int | 100 | 推荐数量 |
| `--token` | str | None | API Access Token |
| `--refresh` | flag | False | 强制刷新 API 缓存 |
| `--no-cache` | flag | False | 禁用推荐缓存（总是重新计算） |
| `--output` | str | `outputs/user_{user}.json` | 结果输出路径 |

### `recommend` 命令输出

终端表格：
```
============================================================
推荐结果 (共 100 部) | 引擎: gcn+llm
============================================================
排名  ID       想看  评分     Bangumi 名称
------------------------------------------------------------
1     12345         0.8521  8.5     进击的巨人 Final Season
2     67890   ✓     0.8234  7.9     某科学的超电磁炮T
...
```

同时写入 JSON 文件：
```json
{
  "user_id": "12345",
  "source": "gcn+llm",
  "collection_count": 156,
  "wished_count": 23,
  "in_training_data": true,
  "gcn_exclude_items": 156,
  "gcn_new_for_warm": 12,
  "recommendations": [
    {
      "rank": 1,
      "subject_id": 12345,
      "name": "进击的巨人 Final Season",
      "name_cn": "進撃の巨人 The Final Season",
      "score": 0.8521,
      "source": "gcn",
      "is_wished": false,
      "rating_score": 8.5,
      "reasons": ["semantic similarity: 0.8521"]
    }
  ]
}
```

### 引擎初始化 (`init_engines`)

```python
init_engines() → Dict[EngineName, BaseRecommender]
│
├── 尝试加载 GCN    → GCNRecommender(checkpoint, data_dir, dataset)
├── 尝试加载 ItemCF → ItemCFRecommender(sim_path)
├── 尝试加载 Content → ContentBasedRecommender()
├── 尝试加载 Hot    → HotRecommender(min_rating_count)
└── 若 ENABLE_LLM  → LLMRecommender(embeddings_dir)
```

每个引擎加载失败时打印 warning 并跳过，不影响其他引擎。引擎实例全局单例，首次调用后缓存。

### `run_recommend` 完整流程

```python
run_recommend(username, top_k, use_cache, force_refresh, token)
│
├── 1. 设置 Token (如有)
├── 2. check_user_exists(username) → 不存在则返回错误
├── 3. fetch_watched_and_wished(username) → 获取收藏 (缓存优先)
├── 4. _build_context(username, id_mapping) → 构建 RecommendContext
├── 5. 检查推荐缓存 (use_cache=True 时)
├── 6. 懒加载引擎 → Router 路由 → 多引擎推荐
├── 7. WeightedFusion 融合
├── 8. 缓存结果 (use_cache=True 时)
└── 9. 返回 JSON dict
```

---

## 二、HTTP API 入口 (`api.py`)

### 技术栈

- **框架**: FastAPI
- **CORS**: 全开放

### 端点

#### `GET /recommend`

为用户生成推荐。

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `user_id` | str | (必填) | - | Bangumi 用户 ID |
| `top_k` | int | 20 | 1-100 | 推荐数量 |
| `use_cache` | bool | True | - | 是否使用推荐缓存 |
| `token` | str | None | - | API Access Token |

**状态码**:

| 状态 | 说明 |
|------|------|
| 200 | 成功，返回推荐结果 JSON |
| 404 | 用户不存在，返回 `{"detail":"用户 xxx 不存在"}` |

**响应格式**: 与 CLI 的 JSON 输出一致。

#### `GET /health`

健康检查。

```json
{"status": "ok"}
```

### 启动方式

```bash
cd e:\bangumi\recommender
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## 三、典型使用场景

### 场景 1: 开发调试

```bash
# 强制刷新 API 数据 + 禁用推荐缓存，获取最新推荐
python main.py recommend --user 12345 --refresh --no-cache --top-k 20
```

### 场景 2: 批量推荐

```bash
# 输出到指定文件
python main.py recommend --user 12345 --output results/user_12345.json
```

### 场景 3: 服务部署

```bash
# 启动 API 服务
uvicorn api:app --host 0.0.0.0 --port 8000

# 访问
curl "http://localhost:8000/recommend?user_id=12345&top_k=20"
```

### 场景 4: 数据维护

```bash
# 导入动画基础数据（首次运行或数据更新后）
python main.py import-anime

# 爬取当季新番
python main.py crawl-season --year 2025 --month 4

# 更新完结状态
python main.py update-db

# 清理缓存
python main.py clear-cache              # 清理全部
python main.py clear-cache --user 12345 # 清理指定用户
```

---

## 四、用户脚本集成 (`userscripts/recommend.js`)

`userscripts/recommend.js` 是一个浏览器用户脚本，可在 Bangumi 页面上嵌入推荐面板，通过调用本系统的 HTTP API 获取推荐结果并在页面上展示。

### 工作原理

```
Bangumi 页面 (用户已登录)
  │
  ├── 用户脚本检测当前页面用户 ID
  ├── 调用 GET /recommend?user_id={current_user}&top_k=10
  ├── 在页面侧边栏或弹窗中渲染推荐列表
  └── 每个条目链接到对应的 Bangumi 动画页面
```

### 部署

1. 确保 API 服务运行（`uvicorn api:app`）
2. 在 Tampermonkey / Violentmonkey 中安装 `recommend.js`
3. 修改脚本中的 API 地址指向实际服务
