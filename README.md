# 告警驱动型故障诊断智能体

基于 FastAPI + Vue3 的智能运维故障诊断系统，能够自动接收告警、追踪微服务日志链路、推理故障根因并生成标准化诊断报告。

## 📋 项目背景

在信息系统日常运维中，微服务架构的广泛应用使得系统故障排查复杂度呈指数级上升。传统故障处理流程依赖人工经验：收到告警后，运维人员需手动登录日志平台，根据告警中的微服务名、trace_id 或错误码，逐层向下追踪微服务调用链，分析上游至下游的日志上下文，最终定位根因。

本系统旨在构建一个"告警驱动型"故障诊断智能体，将平均故障定位时间缩短 50% 以上，推动运维模式从"被动响应、人工溯源"向"主动感知、智能归因"转变。

## ✨ 核心功能

| 功能模块 | 说明 |
|---------|------|
| 📥 告警接入 | 接收 JSON 格式告警数据，自动提取服务名、时间、错误码等关键信息 |
| 🔗 全链路追踪 | 递归追踪微服务调用链（最多 3 层），自动发现下游服务调用 |
| 🧠 根因推理 | 结合向量检索和 LLM 进行智能根因分析 |
| 📊 报告生成 | 输出标准化 JSON 诊断报告，包含根因、建议、调用链等 |
| 📚 知识库检索 | 从 PostgreSQL 向量数据库检索相似历史案例（可选） |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端界面 (Vue3)                       │
│                   http://localhost:8000                  │
│  ┌─────────────────────────────────────────────────────┐│
│  │  告警输入 → 诊断提交 → 报告展示 → 一键复制           ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
                            │
                            │ POST /api/diagnose
                            ▼
┌─────────────────────────────────────────────────────────┐
│                FastAPI 后端服务 (8000 端口)               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 告警解析模块  │  │ 日志追踪模块  │  │ 根因推理模块   │  │
│  │ AlertParser  │  │ LogTracker   │  │ RootCause     │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                      │
│  │ 报告生成模块  │  │ 知识库检索    │                      │
│  │ ReportGen    │  │ KnowledgeRetriever                  │
│  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
                            │
                            │ HTTP 调用
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Mock API 服务 (8080 端口)                    │
│  GET  /api/alerts   - 获取随机告警数据                    │
│  GET  /api/alerts/all - 获取所有告警数据                  │
│  POST /api/trace    - 查询日志链路 (serviceName, time)   │
│  GET  /api/services - 获取服务列表                       │
│  GET  /api/stats    - 数据统计                           │
└─────────────────────────────────────────────────────────┘
                            │
              (可选) PostgreSQL 向量知识库
              ┌─────────────────────────┐
              │  pgvector/pgvector:pg15 │
              │  Port: 5432             │
              │  DB: fault_knowledge    │
              └─────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ (可选，仅前端开发需要)
- Docker & Docker Compose (可选，用于 PostgreSQL 知识库)

### 1. 安装 Python 依赖

```bash
cd /Users/yanghanxuan/Documents/工作/入职/国网新员工培训/AI+微创新/比武打擂/code

# 创建虚拟环境
uv venv
source .venv/bin/activate

# 安装依赖（使用阿里云镜像加速）
uv pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2. 安装前端依赖（可选）

如需修改前端代码，需要安装 Node.js 依赖：

```bash
cd webui
npm install
```

### 3. 配置环境变量（可选）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置 LLM API Key 等
# DASHSCOPE_API_KEY=your_api_key
# LOG_API_ENABLED=true
# LOG_API_BASE_URL=http://localhost:8080
```

### 4. 启动 PostgreSQL 知识库（可选）

PostgreSQL + pgvector 用于存储和检索历史故障案例，支持向量相似度搜索。**如不需要知识库检索功能，可跳过此步骤，系统会自动降级为纯 LLM 推理。**

#### 方式一：使用 Docker Compose（推荐）

```bash
# 启动 PostgreSQL 容器
docker-compose -f docker-compose.postgres.yml up -d

# 查看容器状态
docker ps | grep fault-knowledge-db

# 查看日志
docker logs -f fault-knowledge-db
```

#### 方式二：手动启动 Docker

```bash
# 拉取镜像
docker pull pgvector/pgvector:pg15

# 启动容器
docker run -d \
  --name fault-knowledge-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=fault_knowledge \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  -v $(pwd)/scripts/init_postgres.sql:/docker-entrypoint-initdb.d/init.sql \
  pgvector/pgvector:pg15
```

#### 导入历史故障数据

知识库启动后，导入 Excel 格式的历史故障案例：

```bash
# 确保已激活 Python 虚拟环境
python scripts/import_knowledge.py dataset/历史故障知识库.xlsx
```

#### 管理知识库

```bash
# 查看所有案例
python scripts/manage_knowledge.py list

# 删除指定案例
python scripts/manage_knowledge.py delete --case-no 1

# 清空知识库
python scripts/manage_knowledge.py clear
```

#### 停止/重启知识库

```bash
# 停止容器
docker-compose -f docker-compose.postgres.yml down

# 重启容器
docker-compose -f docker-compose.postgres.yml restart

# 删除容器和数据卷（慎用！）
docker-compose -f docker-compose.postgres.yml down -v
```

### 5. 启动服务

#### 方式一：分别启动

```bash
# 终端 1 - 启动 Mock API 服务（8080 端口）
python mock_api_server.py

# 终端 2 - 启动主服务（8000 端口，包含前端）
python main.py
```

#### 方式二：开发模式（前端热更新）

```bash
# 终端 1 - Mock API
python mock_api_server.py

# 终端 2 - 主服务
python main.py

# 终端 3 - 前端开发服务器
cd webui
npm run dev
```

### 6. 访问前端界面

打开浏览器访问：**http://localhost:8000**

## 📥 输入格式（告警 JSON）

前端页面直接输入 JSON 格式告警数据：

```json
{
  "微服务名称": "网关服务",
  "告警信息": "搜索请求异常",
  "告警时间": "2026-06-01T10:05:08Z"
}
```

### 必填字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `微服务名称` | string | 微服务名称 | `"网关服务"` |
| `告警信息` | string | 错误信息描述 | `"搜索请求异常"` |
| `告警时间` | string | 告警时间（ISO 8601 格式） | `"2026-06-01T10:05:08Z"` |

### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `error_code` | string | 错误码（TIMEOUT, NULL_POINTER 等） |
| `trace_id` | string | 链路追踪 ID |
| `level` | string | 告警级别（ERROR, WARN） |

## 📤 输出格式（诊断报告）

```json
{
  "status": "success",
  "report": {
    "fault_summary": "网关服务搜索请求异常",
    "root_cause": "搜索服务索引重建失败导致查询超时",
    "suggestions": [
      "1. 检查搜索服务索引重建任务状态",
      "2. 重启搜索服务",
      "3. 检查 Elasticsearch 集群健康状态"
    ],
    "call_chain": ["网关服务", "搜索服务"],
    "logs": [
      {
        "level": "ERROR",
        "微服务名称": "网关服务",
        "产生时间": "2026-06-01T10:05:08Z",
        "日志内容": "搜索请求超时"
      }
    ],
    "matched_cases": [
      {
        "fault_symptom": "搜索服务超时",
        "root_cause": "索引重建失败",
        "suggestion": "检查索引重建任务",
        "similarity": 0.85
      }
    ],
    "confidence": "high",
    "is_new_case": false
  },
  "message": "诊断完成"
}
```

### 输出字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 诊断状态：`success`（成功）/ `incomplete`（信息不足） |
| `report.fault_summary` | string | 故障现象简述 |
| `report.call_chain` | array | 服务调用链路（按调用顺序） |
| `report.root_cause` | string | 根因分析结果 |
| `report.suggestions` | array | 处置建议列表 |
| `report.confidence` | string | 置信度：`high` / `medium` / `low` |
| `report.matched_cases` | array | 匹配的历史案例（含相似度） |
| `report.logs` | array | 关键日志列表 |
| `report.is_new_case` | boolean | 是否为新故障（知识库中无相似案例） |

## 🔌 API 接口

### POST /api/diagnose

提交告警进行诊断

**请求体：**
```json
{
  "微服务名称": "网关服务",
  "告警信息": "搜索请求异常",
  "告警时间": "2026-06-01T10:05:08Z"
}
```

**响应：** 诊断报告（见上方输出格式）

### GET /api/knowledge

查看历史知识库中的所有案例

**响应：**
```json
{
  "count": 10,
  "cases": [
    {
      "case_no": 1,
      "fault_symptom": "...",
      "root_cause": "...",
      "suggestion": "..."
    }
  ]
}
```

### GET /health

健康检查

**响应：**
```json
{
  "service": "告警驱动型故障诊断智能体",
  "version": "1.0.0",
  "status": "running"
}
```

## 📁 项目结构

```
code/
├── main.py                    # FastAPI 主入口
├── config.py                  # 全局配置
├── mock_api_server.py         # Mock API 服务（告警 + 日志数据）
├── batch_diagnose.py          # 批量诊断脚本
├── docker-compose.postgres.yml # PostgreSQL Docker 配置
├── requirements.txt           # Python 依赖
├── dataset/
│   ├── mock_data.json         # Mock 数据（告警 + 日志）
│   └── 历史故障知识库.xlsx     # 历史故障案例
├── models/                    # 数据模型
│   ├── alert.py               # 告警模型
│   ├── log.py                 # 日志模型
│   └── report.py              # 诊断报告模型
├── services/                  # 业务服务
│   ├── alert_parser.py        # 告警解析
│   ├── log_tracker.py         # 日志追踪
│   ├── root_cause.py          # 根因推理
│   ├── report_gen.py          # 报告生成
│   ├── knowledge_retriever.py # 知识库检索
│   ├── llm_client.py          # LLM 客户端
│   └── prompt.py              # 提示词模板
├── data/                      # 数据访问层
│   └── __init__.py            # Mock API 客户端
├── scripts/                   # 工具脚本
│   ├── init_postgres.sql      # PostgreSQL 初始化脚本
│   ├── import_knowledge.py    # 导入知识库数据
│   ├── manage_knowledge.py    # 管理知识库
│   └── batch_diagnose.py      # 批量诊断
└── webui/                     # Vue3 前端
    ├── src/
    │   ├── App.vue            # 主组件
    │   └── main.js            # 入口
    ├── dist/                  # 生产构建产物
    ├── package.json
    └── vite.config.js
```

## 🔧 配置说明

### config.py 主要配置项

```python
# LLM 配置
LLM_API_KEY = "sk-..."           # DashScope API Key
LLM_MODEL = "qwen-turbo"         # 使用的模型
LLM_BASE_URL = "https://dashscope.aliyuncs.com/..."

# 服务配置
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000

# 日志 API 配置
LOG_API_ENABLED = False          # 是否启用 API 模式
LOG_API_BASE_URL = "http://localhost:8080"

# PostgreSQL 配置
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "fault_knowledge"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "postgres"

# 诊断参数
MAX_TRACE_DEPTH = 3              # 调用链追踪最大深度
```

### 环境变量（.env）

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | - |
| `LLM_MODEL` | LLM 模型名称 | `qwen-turbo` |
| `POSTGRES_HOST` | PostgreSQL 主机 | `localhost` |
| `POSTGRES_PORT` | PostgreSQL 端口 | `5432` |
| `LOG_API_ENABLED` | 是否启用日志 API | `false` |
| `ENABLE_AUTO_LEARN` | 是否自动学习新案例 | `false` |

## 🧪 测试示例

### 示例 1：完整告警诊断

```json
{
  "微服务名称": "网关服务",
  "告警信息": "网关请求超时",
  "告警时间": "2026-06-01T10:00:13Z"
}
```

### 示例 2：批量诊断

使用批量诊断脚本对所有告警进行诊断：

```bash
python batch_diagnose.py
```

输出：
- `diagnosis_results/batch_diagnosis_report.md` - Markdown 综合报告
- `diagnosis_results/batch_diagnosis_details.json` - JSON 详细结果

### 示例 3：信息不足

```json
{
  "微服务名称": "网关服务"
  // 缺少告警信息和告警时间
}
```

响应将返回 `status: "incomplete"`，并说明缺失的字段。

## 📝 核心任务完成情况

| 核心任务 | 要求 | 完成情况 |
|---------|------|---------|
| (1) 告警接入与关键信息提取 | 接收 JSON 告警，提取服务名、时间、错误码等 | ✅ |
| (2) 全链路日志追踪 | 递归追踪调用链（≤3 层），记录完整路径 | ✅ |
| (3) 根因智能推理 | 结合知识库检索和 LLM 推理根因 | ✅ |
| (4) 标准化报告生成 | 输出统一 JSON 格式报告 | ✅ |

## 🛠️ 故障排除

### Mock API 启动失败

```bash
# 检查 8080 端口是否被占用
lsof -i :8080

# 如有占用，终止进程后重启
kill -9 <PID>
```

### PostgreSQL 启动失败

```bash
# 检查 5432 端口是否被占用
lsof -i :5432

# 查看容器日志
docker logs fault-knowledge-db

# 重启容器
docker-compose -f docker-compose.postgres.yml restart
```

### 前端页面无法访问

```bash
# 检查 dist 目录是否存在
ls webui/dist

# 如不存在，重新构建
cd webui
npm run build
```

### LLM 调用失败

- 检查 `DASHSCOPE_API_KEY` 是否正确配置
- 检查网络连接
- LLM 不可用时会自动降级为规则推理

### 知识库检索失败

- 确保 PostgreSQL 容器已启动
- 检查 `POSTGRES_*` 环境变量配置
- 确认已运行 `import_knowledge.py` 导入数据

## 📄 许可证

本项目为国网新员工培训 AI+ 微创新比武打擂参赛项目。

## 👥 开发团队

- 参赛队伍：AI+ 微创新
- 项目：告警驱动型故障诊断智能体
- 版本：1.0.0
