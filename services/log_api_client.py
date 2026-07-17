"""日志查询 API 客户端

通过 HTTP API 调用微服务日志查询接口获取日志数据。
API 接口规范：
- 请求：POST /api/trace (URL params: serviceName, alertTime)
- 响应：{ "code": 200, "message": "success", "data": [...] }
- 日志数据字段：微服务名称，日志等级，日志内容，产生时间，下游微服务名称，traceid
"""
import logging
import httpx
from services.config import LOG_API_BASE_URL, LOG_API_TIMEOUT

logger = logging.getLogger(__name__)


class LogAPIClient:
    """日志查询 API 客户端"""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = base_url or LOG_API_BASE_URL
        self.timeout = timeout or LOG_API_TIMEOUT
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def query_logs(self, service_name: str, alert_time: str) -> list[dict]:
        """
        调用日志链路查询 API。

        Args:
            service_name: 微服务名称
            alert_time: 告警时间（RFC3339 格式）

        Returns:
            日志列表：[{ "微服务名称": "...", "日志等级": "...", "日志内容": "...",
                       "产生时间": "...", "下游微服务名称": "...", "traceid": "..." }, ...]
            如果查询失败或无数据，返回空列表 []
        """
        client = self._get_client()

        logger.info(
            f"[API] 查询日志链路：serviceName={service_name}, alertTime={alert_time}"
        )

        try:
            response = client.post(
                "/api/trace",
                params={"serviceName": service_name, "alertTime": alert_time},
            )
            response.raise_for_status()
            result = response.json()
            
            # 解析响应
            code = result.get("code", 0)
            if code != 200:
                logger.warning(f"[API] 日志查询返回非 200 状态码：{code}, {result.get('message')}")
                return []

            data = result.get("data", [])
            if not isinstance(data, list):
                logger.warning(f"[API] 返回 data 字段不是列表：{type(data)}")
                return []

            # 转换为内部格式
            logs = self._normalize_logs(data)
            logger.info(f"[API] 获取到 {len(logs)} 条日志")
            return logs

        except httpx.HTTPStatusError as e:
            logger.error(f"[API] HTTP 错误：{e.response.status_code} - {e.response.text}")
            return []
        except httpx.RequestError as e:
            logger.error(f"[API] 请求失败：{e}")
            return []
        except Exception as e:
            logger.error(f"[API] 未知错误：{e}")
            return []

    def _normalize_logs(self, data: list[dict]) -> list[dict]:
        """
        将 API 返回的日志格式转换为内部格式。

        API 返回格式：
        { "微服务名称": "...", "日志等级": "...", "日志内容": "...",
          "产生时间": "...", "下游微服务名称": "...", "traceid": "..." }

        内部格式：
        { "timestamp": "...", "level": "...", "message": "...",
          "downstream_service": "...", "trace_id": "..." }
        """
        normalized = []
        for log in data:
            normalized.append({
                "timestamp": log.get("产生时间", ""),
                "level": log.get("日志等级", "").upper(),
                "message": log.get("日志内容", ""),
                "downstream_service": log.get("下游微服务名称"),
                "trace_id": log.get("traceid"),
            })
        return normalized

    def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None


# 全局客户端实例
_log_api_client: LogAPIClient | None = None


def get_log_api_client() -> LogAPIClient:
    """获取全局日志 API 客户端实例"""
    global _log_api_client
    if _log_api_client is None:
        _log_api_client = LogAPIClient()
    return _log_api_client


def query_logs_via_api(service_name: str, alert_time: str) -> list[dict]:
    """便捷函数：通过 API 查询日志"""
    client = get_log_api_client()
    return client.query_logs(service_name=service_name, alert_time=alert_time)
