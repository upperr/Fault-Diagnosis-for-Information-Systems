"""告警解析与信息提取模块"""
import logging
from models.alert import Alert
from models.report import DiagnosticReport

logger = logging.getLogger(__name__)


class AlertParser:
    """解析告警数据，提取关键信息"""

    @staticmethod
    def parse(alert_data: dict) -> tuple[Alert | None, DiagnosticReport | None]:
        """
        解析告警 JSON 数据。
        返回：(alert, None) 解析成功; (None, report) 信息不足返回错误报告
        """
        try:
            alert = Alert(**alert_data)
        except Exception as e:
            logger.error(f"告警数据格式错误：{e}")
            return None, DiagnosticReport(
                fault_symptom="告警数据格式错误，无法解析",
                diagnosis_process=[],
                root_cause="信息不足",
                suggestion="请检查告警数据格式是否符合 JSON 规范，确保包含必要字段：微服务名称、告警时间",
            )

        is_complete, missing_fields = alert.validate_completeness()
        if not is_complete:
            logger.warning(f"告警信息不完整，缺失字段：{missing_fields}")
            return None, DiagnosticReport(
                fault_symptom=f"告警信息不足，缺失关键字段：{', '.join(missing_fields)}",
                diagnosis_process=[alert.service] if alert.微服务名称 else [],
                root_cause="信息不足",
                suggestion=f"告警数据缺少以下必要字段：{', '.join(missing_fields)}。请确保告警推送时包含微服务名称、告警时间字段。",
            )

        logger.info(f"告警解析成功：服务={alert.微服务名称}, 时间={alert.告警时间}")
        return alert, None
