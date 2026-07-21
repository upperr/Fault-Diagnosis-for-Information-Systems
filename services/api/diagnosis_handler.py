"""
诊断服务 - 核心诊断流程封装
"""
import logging
import os
from typing import Dict, Any

logger = logging.getLogger("diagnosis-agent")


class DiagnosisHandler:
    """故障诊断处理器 - 封装完整诊断流程供 API 路由调用"""
    
    def __init__(self, alert_data: Dict[str, Any]):
        self.alert_data = alert_data
    
    def execute(self) -> Dict[str, Any]:
        """
        执行完整诊断流程
        
        Returns:
            诊断结果字典，包含 status, report, message 等字段
        """
        from services.alert_parser import AlertParser
        from services.log_tracker import LogTracker
        from services.report_gen import ReportGenerator
        from services.root_cause import RootCauseAnalyzer
        
        alert = self.alert_data
        
        # 记录日志
        if alert.get('告警信息'):
            logger.info(f"收到诊断请求：服务={alert['微服务名称']}, 时间={alert['告警时间']}, 告警信息={alert['告警信息']}")
        else:
            logger.info(f"收到诊断请求：服务={alert['微服务名称']}, 时间={alert['告警时间']} (无告警信息，仅基于日志分析)")
        
        # 1. 解析告警
        parsed_alert, error_report = AlertParser.parse(alert)
        if error_report:
            return {
                "status": "incomplete",
                "report": error_report.to_dict(),
                "message": error_report.根因分析,
            }
        
        # 2. 追踪日志
        tracker = LogTracker()
        trace_result = tracker.trace(
            service_name=parsed_alert.微服务名称,
            start_time=parsed_alert.normalized_time,
            alert_message=alert.get('告警信息') or "",
        )
        logger.info(f"调用链:{' -> '.join(trace_result['call_chain'])}")
        
        # 3. 生成诊断报告
        report = ReportGenerator.generate(
            alert_error_message=parsed_alert.告警信息,
            call_chain=trace_result["call_chain"],
            root_cause_analysis={},  # 占位，后续由 analyzer 填充
            all_logs=trace_result["all_logs"],
        )
        
        # 4. 执行根因分析
        analyzer = RootCauseAnalyzer()
        root_cause_result = analyzer.analyze(
            call_chain=trace_result["call_chain"],
            all_logs=trace_result["all_logs"],
            fault_symptom=report.fault_symptom,
            error_type=None,
            alert_info={
                "alert_message": alert.get('告警信息') or "",
                "alert_time": alert['告警时间'],
            },
        )
        
        # 5. 更新报告的根因分析和建议
        report.root_cause = root_cause_result.get("根因分析", "无法判断")
        report.suggestion = root_cause_result.get("处置建议", "无")
        
        # 6. 构建响应数据
        response_report = report.to_dict()
        response_report["call_chain"] = trace_result["call_chain"]
        response_report["logs"] = trace_result["all_logs"]
        response_report["matched_cases"] = root_cause_result.get("matched_cases", [])
        response_report["confidence"] = root_cause_result.get("confidence", "medium")
        response_report["is_new_case"] = root_cause_result.get("is_new_case", False)
        response_report["new_case_message"] = root_cause_result.get("new_case_message", "")
        response_report["new_case_info"] = root_cause_result.get("new_case_info")
        
        return {
            "status": "success",
            "report": response_report,
            "message": "诊断完成",
        }
