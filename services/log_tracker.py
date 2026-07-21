"""全链路日志追踪模块"""
from datetime import datetime
import logging
from services.config import LOG_API_ENABLED
from data import query_logs as query_logs_mock, get_all_service_names as get_all_service_names_mock

logger = logging.getLogger(__name__)

# 初始化日志 API 客户端
if LOG_API_ENABLED:
    try:
        from services.log_api_client import get_log_api_client
        _api_client = get_log_api_client()
        logger.info("日志 API 模式已启用")
    except Exception as e:
        logger.warning(f"日志 API 客户端初始化失败：{e}，降级为本地 mock 模式")
        LOG_API_ENABLED = False
else:
    logger.info("日志 API 模式未启用，使用本地 mock 数据")


def query_logs(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    level: str | None = None,
    trace_id: str | None = None,
) -> list[dict]:
    """
    统一日志查询接口：根据配置选择 API 或 mock 模式。
    API 模式只使用 service_name 和 start_time（作为 alertTime）。
    """
    if LOG_API_ENABLED:
        try:
            from services.log_api_client import get_log_api_client
            client = get_log_api_client()
            # API 只需要 serviceName 和 alertTime
            alert_time = start_time or ""
            return client.query_logs(
                service_name=service_name,
                alert_time=alert_time,
            )
        except Exception as e:
            logger.error(f"API 查询失败，降级为 mock 模式：{e}")
            return query_logs_mock(
                service_name=service_name,
                alert_time=start_time,
            )
    else:
        return query_logs_mock(
            service_name=service_name,
            alert_time=start_time,
        )


def get_all_service_names() -> list[str]:
    """获取所有已知服务名"""
    return get_all_service_names_mock()


class LogTracker:
    """全链路日志追踪：基于 trace_id 迭代追踪微服务调用链"""

    def __init__(self):
        self.call_chain: list[str] = []
        # 每条日志附带 _source_service 标记（内部使用，不输出）
        self.all_logs: list[dict] = []
        self.logs_by_service: dict[str, list[dict]] = {}
        self.trace_id: str | None = None
        self.trace_confidence: str = "low"
        self.trace_reasoning: str = ""

    def trace(
        self,
        service_name: str,
        start_time: str,
        alert_message: str = "",
    ) -> dict:
        """
        迭代追踪服务日志链路：
        1. 使用 LLM 分析第一条日志，确定 trace_id
        2. 基于 trace_id 和下游微服务名称，迭代追踪后续链路
        3. 最多追踪 4 个微服务（或直到下游为空）

        Args:
            service_name: 告警微服务名称
            start_time: 告警起始时间
            alert_message: 告警信息（用于 LLM 语义分析，确定最相关的 trace_id）

        Returns:
            {
                "call_chain": ["svc1", "svc2", ...],
                "logs_by_service": {"svc1": [...], "svc2": [...]},
                "all_logs": [...],  # 每条附带 _source_service 内部标记
                "trace_id": "...",  # 确定的 trace_id
                "trace_confidence": "high/medium/low",
                "trace_reasoning": "...",
            }
        """
        # 步骤 1: 查询告警服务的日志，使用 LLM 确定 trace_id
        logger.info(f"[步骤 1] 查询告警服务日志：{service_name}, 时间：{start_time} 前后 5 分钟")
        first_service_logs = query_logs(
            service_name=service_name,
            start_time=start_time,
        )
        
        # 按与告警时间差排序
        alert_dt = None
        if start_time:
            try:
                alert_dt = datetime.fromisoformat(start_time.rstrip("Z"))
            except Exception:
                pass
        
        if alert_dt:
            def time_diff(log):
                # 使用内部格式的 timestamp 字段
                log_time_str = log.get("timestamp", "")
                if not log_time_str:
                    return float('inf')
                try:
                    log_dt = datetime.fromisoformat(log_time_str.rstrip("Z"))
                    return abs((log_dt - alert_dt).total_seconds())
                except Exception:
                    return float('inf')
            first_service_logs.sort(key=time_diff)
            logger.info(f"  日志已按与告警时间差排序（最接近的在前）")
        else:
            first_service_logs.sort(key=lambda x: x.get("timestamp", ""))

        logger.info(f"  获取到 {len(first_service_logs)} 条日志")

        # 使用 LLM 分析日志关联性，确定 trace_id
        logger.info("  使用 LLM 分析日志关联性，确定 trace_id...")
        from services.llm_client import LLMClient
        llm = LLMClient()
        
        correlation_result = llm.analyze_log_correlation(
            service_name=service_name,
            alert_message=alert_message,
            alert_time=start_time,
            logs=first_service_logs,
        )
        
        self.trace_id = correlation_result.get("trace_id")
        self.trace_confidence = correlation_result.get("confidence", "low")
        self.trace_reasoning = correlation_result.get("reasoning", "")
        
        logger.info(f"  确定 trace_id: {self.trace_id} (置信度：{self.trace_confidence})")

        # 步骤 2: 基于 trace_id 迭代追踪调用链
        logger.info(f"[步骤 2] 基于 trace_id={self.trace_id} 迭代追踪调用链...")
        
        current_service = service_name
        current_time = start_time
        max_services = 4  # 最多追踪 4 个微服务
        
        for step in range(max_services):
            logger.info(f"  [链路节点 {step + 1}/{max_services}] 追踪服务：{current_service}")
            
            # 查询该服务的日志
            service_logs = query_logs(
                service_name=current_service,
                start_time=current_time,
            )
            
            # 过滤出与 trace_id 匹配的日志
            if self.trace_id:
                matched_logs = [
                    log for log in service_logs
                    if log.get("trace_id") == self.trace_id or log.get("traceid") == self.trace_id
                ]
                logger.info(f"    查询到 {len(service_logs)} 条日志，匹配 trace_id 的有 {len(matched_logs)} 条")
            else:
                matched_logs = service_logs
                logger.info(f"    查询到 {len(matched_logs)} 条日志（无 trace_id 过滤）")
            
            # 按时间排序
            if alert_dt:
                def time_diff(log):
                    # 使用内部格式的 timestamp 字段
                    log_time_str = log.get("timestamp", "")
                    if not log_time_str:
                        return float('inf')
                    try:
                        log_dt = datetime.fromisoformat(log_time_str.rstrip("Z"))
                        return abs((log_dt - alert_dt).total_seconds())
                    except Exception:
                        return float('inf')
                matched_logs.sort(key=time_diff)
            
            # 存储日志（标记来源服务）
            for log in matched_logs:
                log["_source_service"] = current_service
                self.all_logs.append(log)
            
            if current_service not in self.logs_by_service:
                self.logs_by_service[current_service] = []
            self.logs_by_service[current_service].extend(matched_logs)
            
            # 添加到调用链
            self.call_chain.append(current_service)
            
            # 检测下游服务：从匹配的日志中找到下游微服务名称
            downstream_service = None
            downstream_time = current_time
            for log in matched_logs:
                has_downstream, downstream = self._detect_downstream(log, current_service)
                if has_downstream and downstream:
                    downstream_service = downstream
                    # 使用内部格式的 timestamp 字段
                    downstream_time = log.get("timestamp", current_time)
                    logger.info(f"    发现下游服务：{downstream_service}, 时间：{downstream_time}")
                    break
            
            # 如果没有下游服务，链路结束
            if not downstream_service:
                logger.info(f"    未发现下游服务，链路追踪结束")
                break
            
            # 继续追踪下游服务
            current_service = downstream_service
            current_time = downstream_time
        
        logger.info(f"链路追踪完成，共追踪 {len(self.call_chain)} 个服务：{' -> '.join(self.call_chain)}")
        return self._build_result()

    def _detect_downstream(self, log: dict, source_service: str) -> tuple[bool, str | None]:
        """从日志中检测下游服务调用"""
        from models.log import LogEntry

        try:
            entry = LogEntry(**log)
            return entry.has_downstream_call()
        except Exception:
            return False, None

    def _build_logs_dict(self) -> dict[str, list[dict]]:
        """按服务名分组日志（不包含 _source_service 内部标记）"""
        result: dict[str, list[dict]] = {}
        for log in self.all_logs:
            svc = log.get("_source_service", "unknown")
            if svc not in result:
                result[svc] = []
            # 复制日志并移除内部标记
            clean_log = {k: v for k, v in log.items() if k != "_source_service"}
            result[svc].append(clean_log)
        return result

    def _build_result(self) -> dict:
        """构建返回结果"""
        return {
            "call_chain": list(self.call_chain),
            "logs_by_service": self._build_logs_dict(),
            "all_logs": list(self.all_logs),
            "trace_id": self.trace_id,
            "trace_confidence": self.trace_confidence,
            "trace_reasoning": self.trace_reasoning,
        }
