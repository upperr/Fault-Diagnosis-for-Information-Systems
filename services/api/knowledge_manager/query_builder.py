"""
查询构建器 - 构建用于向量检索的查询文本
"""
import logging

logger = logging.getLogger(__name__)


class QueryBuilder:
    """查询构建器 - 负责构建用于向量检索的查询文本"""

    def build_query_text(self, all_logs: list[dict]) -> str:
        """
        构建用于检索的查询文本。

        Args:
            all_logs: 全链路日志列表

        Returns:
            查询文本字符串
        """
        parts = []

        # 日志信息 (最多取前 10 条)
        for log in all_logs[:10]:
            msg = log.get("message", "")
            level = log.get("level", "?")
            svc = log.get("_source_service", log.get("service_name", "?"))
            parts.append(f"[{level}] {svc}: {msg}")

        return "\n".join(parts)
