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
          故障现象简述，受影响服务列表，根因分析，处置建议

        Args:
            alert_error_message: 告警原始错误信息
            call_chain: 调用链路径
            root_cause_analysis: 根因分析结果
            all_logs: 所有追踪到的日志
            fault_summary: 故障现象简述（可选，自动生成）
        """
        from services.llm_client import LLMClient
        
        root_cause = root_cause_analysis.get("根因分析", "无法判断")
        suggestion = root_cause_analysis.get("处置建议", "无")

        # 使用 LLM 生成故障现象简述
        llm = LLMClient()
        
        if fault_summary:
            fault_symptom = fault_summary
        else:
            fault_symptom = llm.generate_fault_symptom(
                call_chain=call_chain,
                all_logs=all_logs,
                alert_message=alert_error_message,
            )

        # 受影响服务列表直接使用调用链
        affected_services = list(call_chain)

        report = DiagnosticReport(
            fault_symptom=fault_symptom,
            affected_services=affected_services,
            root_cause=root_cause,
            suggestion=suggestion,
        )

        logger.info("诊断报告生成完成")
        return report
