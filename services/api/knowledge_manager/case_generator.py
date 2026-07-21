"""
故障信息生成器 - 生成排查流程和新故障确认信息
"""
import logging
from typing import Optional

from services.config import LLM_MODEL
from services.prompt import (
    build_diagnosis_process_summary_prompt,
    build_new_case_confirmation_prompt,
)

logger = logging.getLogger(__name__)


class CaseGenerator:
    """故障信息生成器 - 负责生成排查流程和新故障确认信息"""

    def __init__(self, llm_client):
        self.llm = llm_client
        self._llm_client = None  # 懒加载的 LLM 客户端

    def _get_llm_client(self):
        """获取 LLM 客户端 (懒加载)"""
        if self._llm_client is None:
            self._llm_client = self.llm._get_client()
        return self._llm_client

    def generate_diagnosis_process(
        self,
        call_chain: list[str],
        all_logs: list[dict],
    ) -> str:
        """
        使用 LLM 基于微服务多级调用链路总结生成排查流程。

        Args:
            call_chain: 调用链列表
            all_logs: 全链路日志

        Returns:
            排查流程描述文本
        """
        prompt = build_diagnosis_process_summary_prompt(call_chain, all_logs)

        try:
            client = self._get_llm_client()
            if not client:
                logger.warning("LLM 不可用，使用调用链作为排查流程")
                return " -> ".join(call_chain) if call_chain else "无调用链信息"

            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的运维故障分析专家，擅长总结故障排查流程。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            process = response.choices[0].message.content
            if not process:
                logger.warning("LLM 返回空内容")
                process = " -> ".join(call_chain) if call_chain else "无调用链信息"
            else:
                process = process.strip()
            logger.info(f"生成排查流程：{process[:100]}...")
            return process
        except Exception as e:
            logger.error(f"生成排查流程失败：{e}")
            # 降级：使用调用链
            return " -> ".join(call_chain) if call_chain else "无调用链信息"

    def generate_new_case_info(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        diagnosis_result: dict,
        alert_time: str,
        similar_cases: list[dict],
        llm_review_result: Optional[dict] = None,
    ) -> dict:
        """
        生成新故障确认信息 (用于前端展示)。

        Args:
            call_chain: 调用链
            all_logs: 全链路日志
            diagnosis_result: 诊断结果
            alert_time: 告警时间
            similar_cases: 相似案例列表
            llm_review_result: LLM 语义检测结果

        Returns:
            新故障确认信息字典
        """
        fault_symptom = diagnosis_result.get(
            "故障现象",
            "未知故障现象",
        )

        # 生成排查流程
        diagnosis_process = self.generate_diagnosis_process(call_chain, all_logs)

        # 构建确认提示
        confirmation_text = build_new_case_confirmation_prompt(
            symptom=fault_symptom,
            services=call_chain,
            alert_time=alert_time,
            diagnosis_process=diagnosis_process,
            suggestion=diagnosis_result.get("处置建议", ""),
            similar_cases=similar_cases,
        )

        return {
            "is_new_case": True,
            "fault_symptom": fault_symptom,
            "diagnosis_process": diagnosis_process,
            "根因分析": diagnosis_result.get("根因分析", ""),
            "处置建议": diagnosis_result.get("处置建议", ""),
            "call_chain": call_chain,
            "alert_time": alert_time,
            "similar_cases": similar_cases,
            "llm_review_result": llm_review_result,
            "confirmation_text": confirmation_text,
            "status": "pending_confirmation",  # 待用户确认
        }
