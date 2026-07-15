"""
全局配置文件
统一管理大模型 API、数据库、服务参数等所有配置。
优先从环境变量读取，未设置时使用默认值。
"""
import os


# ==================== 大模型 API 配置 ====================

# API Key
LLM_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "sk-0c2e7432f5a44a88866f6c98fdae182f")

# API 基础 URL（OpenAI 兼容格式）
LLM_BASE_URL: str = os.getenv(
    "LLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 使用的模型名称
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-turbo")

# 是否启用 LLM 推理（False 时使用规则推理降级）
ENABLE_LLM: bool = bool(LLM_API_KEY)

# 推理参数
LLM_TEMPERATURE: float = 0.1
LLM_MAX_TOKENS: int = 1024


# ==================== OpenAI 兼容 API 配置（本地嵌入模型） ====================

# OpenAI 兼容 API 基础 URL（如 Ollama: http://localhost:11434/v1）
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# API Key（Ollama 默认为 ollama）
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "sk-0c2e7432f5a44a88866f6c98fdae182f")

# 嵌入模型名称
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

# 向量维度（根据模型调整：text-embedding-v2=1536, mxbai-embed-large=1024, nomic-embed-text=768）
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1536"))


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
DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


# ==================== 向量检索配置 ====================

# 向量检索相似度阈值
VECTOR_SEARCH_THRESHOLD: float = 0.3

# 向量检索返回数量
VECTOR_SEARCH_LIMIT: int = 3

# 向量检索字段
VECTOR_SEARCH_FIELDS: list[str] = ["symptom", "diagnosis_process", "root_cause"]

# 新故障判定阈值（低于此值判定为新故障）
NEW_CASE_SIMILARITY_THRESHOLD: float = 0.5

# 是否启用自动学习（新故障自动入库）
ENABLE_AUTO_LEARN: bool = os.getenv("ENABLE_AUTO_LEARN", "false").lower() == "true"


# ==================== 服务配置 ====================

# FastAPI 服务主机和端口
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# ==================== 诊断参数 ====================

# 全链路追踪最大深度
MAX_TRACE_DEPTH: int = 3

# 知识库匹配最低分数阈值（低于此值不视为匹配）
KB_MIN_SCORE: int = 5

# 报告最大支撑日志条数
MAX_SUPPORTING_LOGS: int = 5


# ==================== 日志 API 配置 ====================

# 日志查询 API 基础 URL
# 默认使用本地 mock 服务地址，实际部署时修改为真实服务地址
LOG_API_BASE_URL: str = os.getenv("LOG_API_BASE_URL", "http://localhost:8080")

# API 请求超时时间（秒）
LOG_API_TIMEOUT: int = int(os.getenv("LOG_API_TIMEOUT", "30"))

# 是否启用 API 模式（False 时使用本地 mock 数据降级）
LOG_API_ENABLED: bool = os.getenv("LOG_API_ENABLED", "false").lower() == "true"


# ==================== 文件路径配置 ====================

# 项目根目录
import pathlib
PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).parent

# 数据集目录
DATASET_DIR: pathlib.Path = PROJECT_ROOT / "dataset"

# 告警数据文件
ALERT_FILE: pathlib.Path = DATASET_DIR / "alert.json"

# 历史故障知识库文件
KNOWLEDGE_EXCEL_FILE: pathlib.Path = DATASET_DIR / "历史故障知识库.xlsx"
