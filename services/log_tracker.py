"""全链路日志追踪模块"""
import logging
from config import MAX_TRACE_DEPTH, LOG_API_ENABLED
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
    """全链路日志追踪：递归追踪微服务调用链"""

    def __init__(self):
        self.call_chain: list[str] = []
        # 每条日志附带 _source_service 标记（内部使用，不输出）
        self.all_logs: list[dict] = []
        self.visited_services: set[str] = set()
        self.logs_by_service: dict[str, list[dict]] = {}

    def trace(
        self,
        service_name: str,
        start_time: str,
        trace_id: str | None = None,
        depth: int = 0,
    ) -> dict:
        """
        递归追踪服务日志，发现下游调用自动深入。

        Args:
            service_name: 服务名称
            start_time: 告警起始时间
            trace_id: 追踪ID（可选）
            depth: 当前递归深度

        Returns:
            {
                "call_chain": ["svc1", "svc2", ...],
                "logs_by_service": {"svc1": [...], "svc2": [...]},
                "all_logs": [...],  # 每条附带 _source_service 内部标记
            }
        """
        if depth >= MAX_TRACE_DEPTH:
            logger.info(f"已达最大追踪深度 {MAX_TRACE_DEPTH}，停止递归")
            return self._build_result(reached_max_depth=True)

        if service_name in self.visited_services:
            logger.warning(f"服务 {service_name} 已追踪过，跳过循环依赖")
            return self._build_result(cycle_detected=True)

        self.visited_services.add(service_name)
        self.call_chain.append(service_name)
        logger.info(
            f"[深度 {depth}] 追踪服务: {service_name}, 时间范围: {start_time} 之后"
        )

        # 查询该服务的 ERROR 级别日志
        error_logs = query_logs(
            service_name=service_name,
            start_time=start_time,
            level="ERROR",
            trace_id=trace_id,
        )
        # 查询少量 INFO 上下文日志
        info_logs = query_logs(
            service_name=service_name,
            start_time=start_time,
            level="INFO",
            trace_id=trace_id,
        )

        service_logs = error_logs + info_logs
        # 按时间排序
        service_logs.sort(key=lambda x: x["timestamp"])

        # 存储日志（标记来源服务，内部使用）
        for log in service_logs:
            log["_source_service"] = service_name
            self.all_logs.append(log)

        self.logs_by_service[service_name] = service_logs

        logger.info(
            f"  获取到 {len(service_logs)} 条日志 "
            f"(ERROR: {len(error_logs)}, INFO: {len(info_logs)})"
        )

        # 检测下游服务调用（优先从 ERROR 日志中检测）
        downstream_found = False
        for log in error_logs:
            has_downstream, downstream_service = self._detect_downstream(log, service_name)
            if has_downstream and downstream_service:
                logger.info(f"  发现下游服务调用: {downstream_service}")
                downstream_found = True
                # 递归追踪下游服务
                self.trace(
                    service_name=downstream_service,
                    start_time=log["timestamp"],
                    depth=depth + 1,
                )
                break  # 每次只追踪第一个发现的下游，避免分支爆炸

        # 如果 ERROR 日志中未发现下游，尝试从 INFO 日志中寻找调用线索
        if not downstream_found:
            for log in info_logs:
                has_downstream, downstream_service = self._detect_downstream(log, service_name)
                if has_downstream and downstream_service:
                    logger.info(f"  从INFO日志发现下游服务调用: {downstream_service}")
                    downstream_found = True
                    self.trace(
                        service_name=downstream_service,
                        start_time=log["timestamp"],
                        depth=depth + 1,
                    )
                    break

        if not downstream_found:
            if depth == 0:
                logger.info("  未发现下游服务调用，当前服务可能为根因")
            else:
                logger.info(f"  {service_name} 为调用链末端，可能为根因服务")

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

    def _build_result(
        self,
        reached_max_depth: bool = False,
        cycle_detected: bool = False,
    ) -> dict:
        """构建返回结果"""
        result = {
            "call_chain": list(self.call_chain),
            "logs_by_service": self._build_logs_dict(),
            "all_logs": list(self.all_logs),
        }
        if reached_max_depth:
            result["reached_max_depth"] = True
        if cycle_detected:
            result["cycle_detected"] = True
        return result
