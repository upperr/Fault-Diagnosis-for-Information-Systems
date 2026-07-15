"""
数据访问模块 — 通过 HTTP 请求本地 Mock API 服务获取告警和日志数据

Mock API 接口 (localhost:8080):
  GET  /api/alerts  - 返回随机一条告警
  POST /api/trace   - 根据 serviceName 和 alertTime 查询日志链路
"""
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Mock API 服务地址
MOCK_API_BASE_URL = "http://localhost:8080"
MOCK_API_TIMEOUT = 30

# 全局 HTTP 客户端
_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    """获取或创建 HTTP 客户端"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            base_url=MOCK_API_BASE_URL,
            timeout=MOCK_API_TIMEOUT,
            # 不设置固定 Content-Type，让 httpx 根据请求类型自动设置
        )
    return _http_client


def get_alert() -> Optional[dict]:
    """
    获取一条随机告警数据
    
    Mock API 每次返回随机一条告警。
    
    Returns:
        告警数据 dict，或 None（如果获取失败）
        格式：{
            "request_id": "API-xxx",
            "service": "xxx",
            "error_message": "xxx",
            "time": "xxx"
        }
    """
    client = _get_client()
    
    try:
        logger.info("[Mock API] 请求告警数据...")
        response = client.get("/api/alerts")
        response.raise_for_status()
        result = response.json()
        
        # 解析响应
        code = result.get("code", 0)
        if code != 200:
            logger.warning(f"[Mock API] 告警查询返回非 200 状态码：{code}")
            return None
        
        data = result.get("data", [])
        if not isinstance(data, list) or len(data) == 0:
            logger.warning("[Mock API] 返回数据为空")
            return None
        
        # 返回第一条（随机的一条）
        raw_alert = data[0]
        
        # 转换为内部格式
        return {
            "request_id": f"API-{raw_alert.get('告警时间', 'unknown')}",
            "service": raw_alert.get("微服务名称"),
            "error_message": raw_alert.get("告警信息"),
            "time": raw_alert.get("告警时间"),
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"[Mock API] HTTP 错误：{e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"[Mock API] 请求失败：{e}")
        return None
    except Exception as e:
        logger.error(f"[Mock API] 未知错误：{e}")
        return None


def query_logs(service_name: str, alert_time: str) -> list[dict]:
    """
    查询日志链路
    
    Args:
        service_name: 微服务名称
        alert_time: 告警时间
    
    Returns:
        日志列表，格式：
        [{
            "timestamp": "...",
            "level": "...",
            "message": "...",
            "downstream_service": "...",
            "trace_id": "..."
        }, ...]
    """
    client = _get_client()
    
    try:
        logger.info(f"[Mock API] 查询日志：serviceName={service_name}, alertTime={alert_time}")
        
        # POST /api/trace with URL params (httpx 会自动 URL 编码中文)
        response = client.post(
            "/api/trace",
            params={"serviceName": service_name, "alertTime": alert_time},
        )
        response.raise_for_status()
        result = response.json()
        
        # 解析响应
        code = result.get("code", 0)
        if code != 200:
            logger.warning(f"[Mock API] 日志查询返回非 200 状态码：{code}")
            return []
        
        data = result.get("data", [])
        if not isinstance(data, list):
            logger.warning(f"[Mock API] 返回 data 字段不是列表")
            return []
        
        # 转换为内部格式
        logs = _normalize_logs(data)
        logger.info(f"[Mock API] 获取到 {len(logs)} 条日志")
        return logs
        
    except httpx.HTTPStatusError as e:
        logger.error(f"[Mock API] HTTP 错误：{e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"[Mock API] 请求失败：{e}")
        return []
    except Exception as e:
        logger.error(f"[Mock API] 未知错误：{e}")
        return []


def _normalize_logs(data: list[dict]) -> list[dict]:
    """
    将 API 返回的日志格式转换为内部格式
    
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


def get_all_service_names() -> list[str]:
    """获取所有服务名称列表"""
    client = _get_client()
    
    try:
        response = client.get("/api/services")
        response.raise_for_status()
        result = response.json()
        
        data = result.get("data", {})
        services = data.get("services", [])
        return services if isinstance(services, list) else []
        
    except Exception as e:
        logger.error(f"[Mock API] 获取服务列表失败：{e}")
        return []


# 关闭时清理 HTTP 客户端
def close():
    """关闭 HTTP 客户端"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        _http_client.close()
        _http_client = None
