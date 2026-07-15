"""标准化报告生成模块 — 输出格式与 output.jsonl 一致"""
import logging

from models.report import DiagnosticReport

logger = logging.getLogger(__name__)


class ReportGenerator:
    """生成标准化故障诊断报告"""

    @staticmethod
    def generate(
        alert_error_message: str | None,
        call_chain: list[str],
        root_cause_analysis: dict,
        all_logs: list[dict],
        fault_summary: str | None = None,
    ) -> DiagnosticReport:
        """
        生成标准化 JSON 格式诊断报告。
        输出字段与 output.jsonl 完全一致：
          fault_summary, affected_services, root_cause, suggestion

        Args:
            alert_error_message: 告警原始错误信息
            call_chain: 调用链路径
            root_cause_analysis: 根因分析结果
            all_logs: 所有追踪到的日志
            fault_summary: 故障现象简述（可选，自动生成）
        """
        root_cause = root_cause_analysis.get("root_cause", "无法判断")
        suggestion = root_cause_analysis.get("suggestion", "无")

        # 自动生成故障摘要
        if not fault_summary:
            affected = call_chain[-1] if call_chain else "unknown"
            if len(call_chain) > 1:
                chain_str = " -> ".join(call_chain)
                fault_summary = f"调用链异常 ({chain_str}): {affected} 服务发生故障"
            elif alert_error_message:
                short_msg = (
                    alert_error_message[:100]
                    + ("..." if len(alert_error_message) > 100 else "")
                )
                fault_summary = f"{affected} 服务异常：{short_msg}"
            else:
                fault_summary = f"{affected} 服务发生故障"

        report = DiagnosticReport(
            fault_summary=fault_summary,
            affected_services=list(call_chain),
            root_cause=root_cause,
            suggestion=suggestion,
        )

        logger.info("诊断报告生成完成")
        return report
