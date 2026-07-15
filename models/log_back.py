"""日志数据模型 — 字段与 log.jsonl 一致"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"


# LLM 下游检测客户端实例（延迟初始化，避免模型层直接依赖 LLM）
_downstream_llm_client = None


def set_downstream_llm_client(client):
    """注入 LLM 客户端用于下游服务语义检测。"""
    global _downstream_llm_client
    _downstream_llm_client = client


class LogEntry(BaseModel):
    """
    单条日志记录 — 字段与 log.jsonl 一致。
    log.jsonl 格式:
      { "service": "order-service",
        "logs": [
          { "timestamp": "2025-03-20 10:23:05", "level": "ERROR",
            "message": "调用 inventory-service 超时, 耗时3100ms",
            "trace_id": "abc-123-def" }
        ]
      }
    """
    timestamp: str = Field(..., description="日志时间")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")
    trace_id: Optional[str] = Field(None, description="追踪ID")
    # 可选扩展字段
    stack_trace: Optional[str] = Field(None, description="异常堆栈")
    span_id: Optional[str] = Field(None, description="Span ID")

    def has_downstream_call(
        self,
        known_services: Optional[list[str]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        检测日志是否包含下游服务调用信息。

        两级检测策略：
          1. 快速正则匹配：基于已知服务名称直接匹配（高效，覆盖常见场景）
          2. LLM 语义理解：当正则未命中时，使用大模型判断是否调用了下游服务

        Args:
            known_services: 已知服务名称列表，用于正则匹配和 LLM 提示

        Returns:
            (是否有下游调用, 下游服务名)
        """
        import re
        message = self.message

        # ====== 第一级：基于已知服务名的快速正则匹配 ======
        if known_services:
            # 构建备选服务名正则：按长度降序排列，优先匹配长名称（避免子串误匹配）
            sorted_services = sorted(known_services, key=len, reverse=True)
            escaped = [re.escape(s) for s in sorted_services]
            # 使用宽泛的边界：匹配服务名前后不是字母/数字/连字符/斜杠/点的位置
            # \b 在中文-英文交界处不生效，所以用 (?<![a-zA-Z0-9_\-]) 代替
            prefix = r"(?<![a-zA-Z0-9_\-/\.])"
            suffix = r"(?![a-zA-Z0-9_\-/\.])"
            pattern = prefix + "(" + "|".join(escaped) + ")" + suffix
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                # 排除文件路径中的服务名（如 /etc/grid/user-service/config.yaml）
                # 如果服务名出现在文件路径中（前后有 / 或 .），跳过
                start, end = match.start(), match.end()
                before = message[start - 1:start] if start > 0 else ""
                after = message[end:end + 1] if end < len(message) else ""
                if before in ("/", ".") or after in ("/", "."):
                    # 可能出现在文件路径中，仍交给 LLM 判断
                    pass
                else:
                    return True, match.group(1)

        # ====== 第二级：LLM 语义理解（fallback） ======
        global _downstream_llm_client
        if _downstream_llm_client is not None:
            has_downstream, service_name = _downstream_llm_client.detect_downstream_service(
                message=message,
                stack_trace=self.stack_trace,
                known_services=known_services,
            )
            if has_downstream and service_name:
                return True, service_name

        # ====== 兜底：从堆栈中提取服务名 ======
        if self.stack_trace:
            match = re.search(
                r"com\.\S+?\.(?:client|service|rpc)\.(\w+?)(?:Client|Service|Rpc)",
                self.stack_trace,
            )
            if match:
                return True, f"{match.group(1).lower()}-service"

        return False, None
