# Bangumi 推荐系统

基于 [Bangumi（番组计划）](https://bgm.tv) 的多引擎混合推荐系统。根据用户的收藏数据和历史评分，自动选择合适的推荐引擎组合，经加权融合后输出个性化动画推荐列表。

## 系统特性

- **5 个推荐引擎**：图神经网络 (LightGCN)、物品协同过滤 (ItemCF)、内容向量匹配、热度排序、LLM 语义嵌入
- **智能路由**：根据用户画像（收藏量、是否在训练集等）自动选择最优引擎组合
- **加权融合**：Min-Max 归一化 + 按引擎权重合并，避免单一引擎偏差
- **多层缓存**：API 响应缓存 + 推荐结果缓存，减少重复计算
- **双入口**：CLI 命令行 + FastAPI HTTP 服务
- **浏览器集成**：提供用户脚本，可在 Bangumi 页面直接展示推荐

## 架构概览

```
入口层 (CLI / FastAPI API)
  └── 核心层 (Context → Router → Fusion)
        └── 引擎层 (GCN / ItemCF / Content / Hot / LLM)
              └── 数据层 (SQLite × 5 / Bangumi API)
```

详细的架构图和数据流请参考 [docs/architecture.md](docs/architecture.md)。

## 前置条件

- Python 3.8+
- **数据库文件未包含在仓库中**，需要自行准备（见下方"数据准备"部分）
- GCN 引擎需要预训练模型权重文件

## 安装

```bash
pip install -r requirements.txt
```

### 依赖说明

| 包 | 用途 |
|---|---|
| torch | GCN 模型推理、Content 引擎向量计算 |
| requests | Bangumi API 调用 |
| numpy / scipy | 数值计算、稀疏矩阵 |
| pandas | 数据处理 |
| fastapi / uvicorn | HTTP API 服务 |

## 数据准备

> **重要**：仓库的 `.gitignore` 排除了 `db/`、`models/` 和 `outputs/` 目录，这些目录中的数据文件需要你自行准备。

### 1. 数据库文件

系统运行依赖以下 SQLite 数据库，存放于 `db/` 目录：

| 数据库 | 用途 | 创建方式 |
|---|---|---|
| `anime_meta.db` | 动画元数据（名称、评分、标签等） | 运行 `python main.py import-anime` 导入 |
| `user_interactions.db` | 用户收藏与评分记录 | 首次推荐时自动创建 |
| `api_cache.db` | Bangumi API 响应缓存 | 首次调用 API 时自动创建 |
| `recommend_cache.db` | 推荐结果缓存 | 首次推荐时自动创建 |
| `seasonal.db` | 季度动画数据 | 运行 `python main.py crawl-season` 时自动创建 |

首次使用需要先导入动画基础数据：

```bash
python main.py import-anime
```

该命令会从配置路径 `e:/bangumi/bangumi/Animes.jsonlines` 读取数据并导入 `anime_meta.db`。如果你的数据源路径不同，请修改 `config.py` 中的 `ANIME_JSONLINES` 配置。

### 2. 模型文件

各引擎需要预计算的文件，存放于 `models/` 目录：

| 文件 | 引擎 | 说明 |
|---|---|---|
| `models/gcn/lgn-bangumi-epoch90.pth.tar` | GCN | LightGCN 预训练权重 |
| `models/gcn/train.txt` | GCN | 训练集用户-物品交互 |
| `models/gcn/user_list.txt` | GCN | 用户 ID 映射列表 |
| `models/gcn/item_list.txt` | GCN | 物品 ID 映射列表 |
| `models/gcn/s_pre_adj_mat.npz` | GCN | 归一化邻接矩阵 |
| `models/itemcf/item_similarity_final.json` | ItemCF | 预计算的物品相似度矩阵 |
| `models/content/content_features_v2.pt` | Content | 动画内容特征向量 |

> GCN、ItemCF、Content 引擎对应的模型文件如果不存在，系统会自动跳过该引擎（打印警告），不影响其他引擎运行。Hot 引擎无需预训练文件。

### 3. LLM 嵌入文件

LLM 引擎需要预计算的语义嵌入：

| 文件 | 说明 |
|---|---|
| `embeddings/` 目录下的 `embeddings.npy` 和 `index.json` | BGE-small-zh-v1.5 编码的动画评论嵌入 |

嵌入文件路径由 `config.py` 中的 `LLM_EMBEDDINGS_DIR` 指定。如果不需要 LLM 引擎，设置 `ENABLE_LLM = False`。

## 使用方法

### CLI 命令行

```bash
# 为用户推荐（默认 100 条）
python main.py recommend --user <用户ID>

# 指定推荐数量 + 使用 API Token
python main.py recommend --user <用户ID> --top-k 50 --token <token>

# 强制刷新 API 缓存 + 禁用推荐缓存（获取最新推荐）
python main.py recommend --user <用户ID> --refresh --no-cache

# 导出到指定文件
python main.py recommend --user <用户ID> --output results/user_12345.json
```

#### 其他命令

```bash
# 清理推荐缓存
python main.py clear-cache [--user <用户ID>]

# 爬取当季新番
python main.py crawl-season --year 2025 --month 4

# 更新动画完结状态
python main.py update-db

# 导入动画元数据
python main.py import-anime
```

### HTTP API 服务

```bash
# 启动服务
uvicorn api:app --host 0.0.0.0 --port 8000

# 调用推荐接口
curl "http://localhost:8000/recommend?user_id=<用户ID>&top_k=20"
```

| 端点 | 方法 | 说明 |
|---|---|---|
| `GET /recommend` | GET | 生成推荐，参数：`user_id`（必填）、`top_k`（默认20）、`use_cache`（默认true）、`token` |
| `GET /health` | GET | 健康检查 |

### 浏览器用户脚本

`userscripts/recommend.js` 可在 Bangumi 页面嵌入推荐面板。安装到 Tampermonkey/Violentmonkey 后，修改脚本中的 API 地址指向你的服务即可。

## 推荐引擎与路由策略

系统根据用户特征自动选择引擎组合：

| 用户画像 | 引擎组合 | 说明 |
|---|---|---|
| 收藏 ≤ 50 部 | Content + Hot + LLM | 冷启动用户，依赖内容和热度 |
| 在 GCN 训练集中 | GCN + LLM | 有图模型推荐能力 |
| 其他 | ItemCF + Content + LLM | 有足够历史数据的用户 |

各引擎权重按画像自动缩放，详见 [docs/engines.md](docs/engines.md)。

## 配置

所有配置集中在 `config.py`：

- **路径配置**：`DB_DIR`、`MODELS_DIR`、`OUTPUTS_DIR` 等
- **API 配置**：`BANGUMI_API_BASE`、`ACCESS_TOKEN`、请求间隔与重试次数
- **引擎配置**：`ENABLE_LLM`、各引擎模型路径、融合权重
- **缓存配置**：API 缓存 TTL（默认 168 小时）、推荐缓存 TTL

## 项目结构

```
├── core/           # 核心层：类型定义、引擎基类、路由、融合
├── engines/        # 引擎层：GCN / ItemCF / Content / Hot / LLM
├── data/           # 数据层：数据库操作、API 客户端、缓存、ID 映射
├── scheduler/      # 调度层：季度爬取、完结状态更新
├── docs/           # 详细文档
├── userscripts/    # 浏览器用户脚本
├── prototype-Engine/ # 原型实验代码（仅供参考）
├── config.py       # 全局配置
├── main.py         # CLI 入口
├── api.py          # FastAPI 入口
└── requirements.txt
```

## 扩展新引擎

1. 在 `core/types.py` 的 `EngineName` 枚举中添加名称
2. 创建 `engines/<name>/engine.py`，继承 `BaseRecommender` 并实现 `recommend()` 方法
3. 在 `main.py` 的 `init_engines()` 中注册
4. 在 `config.py` 的 `FUSION_WEIGHTS_BY_PROFILE` 中配置各画像的权重
5. （可选）在 `RecommendRouter.get_engine_names()` 中调整路由逻辑

## 注意事项

- 仓库不包含任何数据库文件、模型权重文件和输出文件（均在 `.gitignore` 中）
- Bangumi API 有频率限制，默认请求间隔 1 秒，遇到 429 状态码会自动等待 60 秒后重试
- GCN 引擎需要 GPU 训练的模型权重，如仅需推理可在 CPU 上运行
- `prototype-Engine/` 目录为早期实验代码，不直接参与主流程
