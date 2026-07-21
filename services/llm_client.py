"""大语言模型推理客户端"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from services.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS
from services.prompt import (
    ROOT_CAUSE_SYSTEM_PROMPT,
    build_root_cause_user_prompt,
    LOG_CORRELATION_SYSTEM_PROMPT,
    build_log_correlation_prompt,
    build_fault_symptom_summary_prompt,
    build_diagnosis_process_summary_prompt,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 推理客户端，支持 DashScope（通义千问）或 OpenAI 兼容接口"""

    def __init__(self):
        self._client = None

    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        return bool(LLM_API_KEY)

    def _get_client(self):
        """懒加载 OpenAI 兼容客户端"""
        if self._client is None and LLM_API_KEY:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=LLM_API_KEY,
                    base_url=LLM_BASE_URL,
                )
                logger.info(
                    f"LLM 客户端已初始化：model={LLM_MODEL}, base_url={LLM_BASE_URL}"
                )
            except ImportError:
                logger.warning("openai 库未安装，将使用规则推理降级")
            except Exception as e:
                logger.warning(f"LLM 客户端初始化失败：{e}，将使用规则推理降级")
        return self._client

    def reason_root_cause(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        matched_cases: list[dict],
        error_type: str | None = None,
    ) -> dict:
        """
        调用 LLM 进行根因推理。

        Args:
            call_chain: 调用链路径
            all_logs: 所有追踪到的日志
            matched_cases: 知识库匹配的案例
            error_type: 告警错误类型

        Returns:
            {"根因分析": str, "处置建议": str, "confidence": str}
        """
        client = self._get_client()
        if not client:
            logger.warning("LLM 不可用，使用规则推理降级")
            return self._rule_based_fallback(call_chain, all_logs, matched_cases, error_type)

        system_prompt = ROOT_CAUSE_SYSTEM_PROMPT
        user_prompt = build_root_cause_user_prompt(
            call_chain, all_logs, matched_cases, error_type,
        )

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()
            logger.info(f"LLM 响应：{content[:300]}...")

            result = json.loads(content)
            return {
                "根因分析": result.get("根因分析", "无法判断"),
                "处置建议": result.get("处置建议", "建议联系运维团队进一步排查"),
                "confidence": result.get("confidence", "medium"),
            }
        except json.JSONDecodeError as e:
            logger.error(f"LLM 返回非 JSON 格式：{e}")
            return self._rule_based_fallback(call_chain, all_logs, matched_cases, error_type)
        except Exception as e:
            logger.error(f"LLM 调用失败：{e}")
            return self._rule_based_fallback(call_chain, all_logs, matched_cases, error_type)

    def generate_fault_symptom(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        alert_message: str | None = None,
    ) -> str:
        """
        使用 LLM 生成故障现象总结。

        Args:
            call_chain: 调用链列表
            all_logs: 全链路日志列表
            alert_message: 告警信息（可选）

        Returns:
            故障现象总结文本
        """
        client = self._get_client()
        if not client:
            logger.warning("LLM 不可用，使用规则生成故障现象")
            return self._rule_based_fault_symptom(call_chain, all_logs, alert_message)

        user_prompt = build_fault_symptom_summary_prompt(
            call_chain, all_logs, alert_message,
        )

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维故障分析专家，擅长总结故障现象。"},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            content = response.choices[0].message.content
            symptom = content.strip() if content else ""
            if not symptom:
                logger.warning("LLM 返回空内容")
                symptom = self._rule_based_fault_symptom(call_chain, all_logs, alert_message)
            logger.info(f"生成故障现象：{symptom[:100]}...")
            return symptom
        except Exception as e:
            logger.error(f"生成故障现象失败：{e}")
            return self._rule_based_fault_symptom(call_chain, all_logs, alert_message)

    def generate_diagnosis_process(
        self,
        call_chain: list[str],
        all_logs: list[dict],
    ) -> str:
        """
        使用 LLM 生成排查流程总结。

        Args:
            call_chain: 调用链列表
            all_logs: 全链路日志列表

        Returns:
            排查流程总结文本
        """
        client = self._get_client()
        if not client:
            logger.warning("LLM 不可用，使用调用链作为排查流程")
            return " -> ".join(call_chain) if call_chain else "无调用链信息"

        user_prompt = build_diagnosis_process_summary_prompt(call_chain, all_logs)

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维故障分析专家，擅长总结故障排查流程。"},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            content = response.choices[0].message.content
            process = content.strip() if content else ""
            if not process:
                logger.warning("LLM 返回空内容")
                process = " -> ".join(call_chain) if call_chain else "无调用链信息"
            logger.info(f"生成排查流程：{process[:100]}...")
            return process
        except Exception as e:
            logger.error(f"生成排查流程失败：{e}")
            return " -> ".join(call_chain) if call_chain else "无调用链信息"

    def _rule_based_fault_symptom(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        alert_message: str | None = None,
    ) -> str:
        """LLM 不可用时的规则生成降级"""
        affected = call_chain[-1] if call_chain else "unknown"
        if len(call_chain) > 1:
            chain_str = " -> ".join(call_chain)
            return f"调用链异常 ({chain_str}): {affected} 服务发生故障"
        elif alert_message:
            short_msg = alert_message[:100] + ("..." if len(alert_message) > 100 else "")
            return f"{affected} 服务异常：{short_msg}"
        else:
            return f"{affected} 服务发生故障"

    def analyze_log_correlation(
        self,
        service_name: str,
        alert_message: str,
        alert_time: str,
        logs: list[dict],
    ) -> dict:
        """
        使用 LLM 分析日志与告警的关联性，确定最有可能的 trace_id。

        Args:
            service_name: 微服务名称
            alert_message: 告警信息
            alert_time: 告警时间
            logs: 该服务在告警时间前后 5 分钟内的所有日志

        Returns:
            {
                "trace_id": str,
                "confidence": "high/medium/low",
                "reasoning": str,
                "key_logs": list[str]
            }
        """
        client = self._get_client()
        if not client:
            logger.warning("LLM 不可用，使用规则推理降级")
            return self._rule_based_trace_selection(logs, alert_time)

        system_prompt = LOG_CORRELATION_SYSTEM_PROMPT
        user_prompt = build_log_correlation_prompt(
            service_name, alert_message, alert_time, logs,
        )

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()
            logger.info(f"LLM 日志关联分析响应：{content[:300]}...")

            result = json.loads(content)
            return {
                "trace_id": result.get("trace_id", ""),
                "confidence": result.get("confidence", "medium"),
                "reasoning": result.get("reasoning", ""),
                "key_logs": result.get("key_logs", []),
            }
        except json.JSONDecodeError as e:
            logger.error(f"LLM 返回非 JSON 格式：{e}")
            return self._rule_based_trace_selection(logs, alert_time)
        except Exception as e:
            logger.error(f"LLM 调用失败：{e}")
            return self._rule_based_trace_selection(logs, alert_time)

    def _rule_based_trace_selection(self, logs: list[dict], alert_time: str = "") -> dict:
        """LLM 不可用时的规则推理降级：基于时间接近度和错误级别选择 trace_id"""
        if not logs:
            return {
                "trace_id": "",
                "confidence": "low",
                "reasoning": "无日志数据",
                "key_logs": [],
            }

        # 优先选择 ERROR 级别日志
        error_logs = [l for l in logs if l.get("日志等级", "").upper() == "ERROR" or l.get("level", "").upper() == "ERROR"]
        candidate_logs = error_logs if error_logs else logs

        # 解析告警时间
        alert_dt = None
        if alert_time:
            try:
                alert_dt = datetime.fromisoformat(alert_time.rstrip("Z"))
            except Exception:
                pass

        # 如果有告警时间，选择与告警时间最接近的日志
        if alert_dt:
            def time_diff(log):
                log_time_str = log.get("产生时间", log.get("timestamp", ""))
                if not log_time_str:
                    return float('inf')
                try:
                    log_dt = datetime.fromisoformat(log_time_str.rstrip("Z"))
                    return abs((log_dt - alert_dt).total_seconds())
                except Exception:
                    return float('inf')
            
            # 按时间差排序，选择最接近的
            candidate_logs.sort(key=time_diff)
            selected = candidate_logs[0]
            time_diff_sec = time_diff(selected)
            reasoning = f"基于规则选择：{'ERROR 级别日志' if error_logs else 'INFO 日志'}，与告警时间相差 {time_diff_sec:.1f} 秒"
        else:
            # 没有告警时间，选择第一条
            selected = candidate_logs[0]
            reasoning = f"基于规则选择：{'ERROR 级别日志' if error_logs else 'INFO 日志'}"

        trace_id = selected.get("traceid", selected.get("trace_id", ""))

        return {
            "trace_id": trace_id,
            "confidence": "low",
            "reasoning": reasoning,
            "key_logs": [selected.get("日志内容", selected.get("message", ""))],
        }

    def _rule_based_fallback(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        matched_cases: list[dict],
        error_type: str | None = None,
    ) -> dict:
        """LLM 不可用时的规则推理降级"""
        bottom_service = call_chain[-1] if call_chain else "unknown"
        error_logs = [l for l in all_logs if l.get("level") == "ERROR"]

        if matched_cases:
            best = matched_cases[0]
            chain_str = " -> ".join(call_chain) if len(call_chain) > 1 else call_chain[0]
            root_cause = (
                f"通过调用链 ({chain_str}) 定位到根因服务：{bottom_service}。\n"
                f"参考历史案例「{best.get('title', 'N/A')}」，根因为：{best.get('root_cause', 'N/A')}"
            )
            suggestion = best.get("suggestion", "建议联系运维团队排查")
            confidence = "medium"
        elif error_logs:
            messages = "\n".join(
                f"  - [{l.get('service_name', '?')}] {l.get('message', '?')}"
                for l in error_logs[:5]
            )
            root_cause = (
                f"基于日志直接推理，故障服务：{bottom_service}\n"
                f"错误信息:\n{messages}"
            )
            suggestion = (
                "1. 检查故障服务运行状态和资源使用情况\n"
                "2. 查看服务最近是否有发布变更或配置变更\n"
                "3. 如影响范围较大，考虑服务降级或流量切换"
            )
            confidence = "low"
        else:
            root_cause = "无法判断根因：未找到 ERROR 级别日志，信息不足"
            suggestion = "请检查日志采集是否正常，确认告警时间范围是否准确"
            confidence = "low"

        return {
            "根因分析": root_cause,
            "处置建议": suggestion,
            "confidence": confidence,
        }
