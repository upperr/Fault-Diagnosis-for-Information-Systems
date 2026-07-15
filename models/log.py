"""日志数据模型"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"


class LogEntry(BaseModel):
    """单条日志记录"""
    timestamp: str = Field(..., description="日志时间")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")
    trace_id: Optional[str] = Field(None, description="追踪 ID")
    downstream_service: Optional[str] = Field(None, description="下游微服务名称")

    def has_downstream_call(self) -> tuple[bool, Optional[str]]:
        """
        检测日志是否包含下游服务调用。
        直接依据 downstream_service 字段判断。

        Returns:
            (是否有下游调用，下游服务名)
        """
        if self.downstream_service:
            return True, self.downstream_service
        return False, None
