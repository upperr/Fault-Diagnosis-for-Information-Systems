"""
全局配置文件

统一管理大模型 API、数据库、服务参数等所有配置。
优先从环境变量读取，未设置时使用默认值。

命名规范：
- LLM_* : 大模型相关配置（根因分析、日志关联、检索决策）
- EMBEDDING_* : 嵌入模型相关配置（向量生成）
- RERANK_* : 重排序模型相关配置（检索结果精排）
- VECTOR_* : 向量检索相关配置（PostgreSQL pgvector）
- POSTGRES_* : PostgreSQL 数据库配置
- LOG_* : 日志 API 配置
- SERVER_* : 服务配置
"""
import os
import pathlib


# ==================== LLM 大模型配置 ====================

# 大模型 API Key（用于根因分析、日志关联、检索决策等）
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

# 大模型 API 基础 URL（OpenAI 兼容格式）
LLM_BASE_URL: str = os.getenv(
    "LLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 大模型名称
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-turbo")

# 是否启用 LLM 推理（False 时使用规则推理降级）
ENABLE_LLM: bool = bool(LLM_API_KEY)

# 大模型推理参数
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))


# ==================== EMBEDDING 嵌入模型配置 ====================

# 嵌入模型 API 基础 URL（OpenAI 兼容格式）
EMBEDDING_BASE_URL: str = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 嵌入模型 API Key
EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", LLM_API_KEY)

# 嵌入模型名称
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

# 向量维度（根据模型调整：text-embedding-v2=1536, mxbai-embed-large=1024, nomic-embed-text=768）
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1536"))


# ==================== RERANK 重排序模型配置 ====================

# Rerank 模型名称（阿里云 DashScope: qwen3-rerank, gte-rerank-v2 等）
RERANK_MODEL: str = os.getenv("RERANK_MODEL", "qwen3-rerank")

# Rerank 精排后返回数量
RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "5"))

# 是否启用 Rerank 精排
RERANK_ENABLED: bool = os.getenv("RERANK_ENABLED", "true").lower() == "true"

# Rerank 相关性阈值（低于此值视为不相关，精排阶段会过滤）
RERANK_THRESHOLD: float = float(os.getenv("RERANK_THRESHOLD", "0.5"))


# ==================== PostgreSQL 数据库配置 ====================

# 数据库主机
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")

# 数据库端口
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))

# 数据库名称
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "fault_knowledge")

# 数据库用户名
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")

# 数据库密码
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")

# 数据库连接字符串（供 SQLAlchemy 等使用）
DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:***@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


# ==================== 向量检索配置 ====================

# 向量检索相似度阈值（粗排）
VECTOR_SEARCH_THRESHOLD: float = float(os.getenv("VECTOR_SEARCH_THRESHOLD", "0.3"))

# 向量检索返回数量（粗排召回数量）
VECTOR_SEARCH_LIMIT: int = int(os.getenv("VECTOR_SEARCH_LIMIT", "20"))

# 向量检索字段
VECTOR_SEARCH_FIELDS: list[str] = ["symptom", "diagnosis_process", "root_cause"]

# 新故障判定阈值（低于此值判定为新故障）
NEW_CASE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("NEW_CASE_SIMILARITY_THRESHOLD", "0.5")
)

# 新故障判定 - 初筛向量相似度阈值
NEW_CASE_INITIAL_THRESHOLD: float = float(os.getenv("NEW_CASE_INITIAL_THRESHOLD", "0.5"))

# 新故障判定 - 是否启用 LLM 语义复查 (两阶段判定)
# 启用后：相似度低于阈值时，使用 LLM 进一步确认是否为新故障
NEW_CASE_LLM_REVIEW_ENABLED: bool = os.getenv("NEW_CASE_LLM_REVIEW_ENABLED", "true").lower() == "true"

# 新故障判定 - LLM 语义复查阈值 (LLM 输出的 confidence_score 高于此值判定为已有故障)
# 即：is_existing_case=True 且 confidence_score >= 阈值 => 已有故障，否则为新故障
NEW_CASE_LLM_THRESHOLD: float = float(os.getenv("NEW_CASE_LLM_THRESHOLD", "0.7"))


# ==================== 检索决策配置 ====================

# LLM 决策最大召回数量（从精排结果中筛选的最大案例数）
LLM_DECISION_TOP_K: int = int(os.getenv("LLM_DECISION_TOP_K", "3"))


# ==================== 日志 API 配置 ====================

# 日志查询 API 基础 URL
LOG_API_BASE_URL: str = os.getenv("LOG_API_BASE_URL", "http://localhost:8080")

# API 请求超时时间（秒）
LOG_API_TIMEOUT: int = int(os.getenv("LOG_API_TIMEOUT", "30"))

# 是否启用 API 模式（False 时使用本地 mock 数据降级）
LOG_API_ENABLED: bool = os.getenv("LOG_API_ENABLED", "false").lower() == "true"


# ==================== 诊断参数配置 ====================

# 全链路追踪最大深度
MAX_TRACE_DEPTH: int = int(os.getenv("MAX_TRACE_DEPTH", "3"))

# 知识库匹配最低分数阈值
KB_MIN_SCORE: int = int(os.getenv("KB_MIN_SCORE", "5"))

# 报告最大支撑日志条数
MAX_SUPPORTING_LOGS: int = int(os.getenv("MAX_SUPPORTING_LOGS", "5"))


# ==================== 服务配置 ====================

# FastAPI 服务主机和端口
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# ==================== 文件路径配置 ====================

# 项目根目录
PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).parent

# 数据集目录
DATASET_DIR: pathlib.Path = PROJECT_ROOT / "dataset"

# 告警数据文件
ALERT_FILE: pathlib.Path = DATASET_DIR / "alert.json"

# 历史故障知识库文件
KNOWLEDGE_EXCEL_FILE: pathlib.Path = DATASET_DIR / "历史故障知识库.xlsx"
