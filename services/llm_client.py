"""大语言模型推理客户端"""
from __future__ import annotations
import json
import logging

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS
from services.prompt import (
    ROOT_CAUSE_SYSTEM_PROMPT,
    build_root_cause_user_prompt,
    DOWNSTREAM_DETECT_SYSTEM_PROMPT,
    build_downstream_detect_prompt,
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
                    f"LLM客户端已初始化: model={LLM_MODEL}, base_url={LLM_BASE_URL}"
                )
            except ImportError:
                logger.warning("openai 库未安装，将使用规则推理降级")
            except Exception as e:
                logger.warning(f"LLM客户端初始化失败: {e}，将使用规则推理降级")
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
            {"root_cause": str, "suggestion": str, "confidence": str}
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
            logger.info(f"LLM响应: {content[:300]}...")

            result = json.loads(content)
            return {
                "root_cause": result.get("root_cause", "无法判断"),
                "suggestion": result.get("suggestion", "建议联系运维团队进一步排查"),
                "confidence": result.get("confidence", "medium"),
            }
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回非JSON格式: {e}")
            return self._rule_based_fallback(call_chain, all_logs, matched_cases, error_type)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return self._rule_based_fallback(call_chain, all_logs, matched_cases, error_type)

    def detect_downstream_service(
        self,
        message: str,
        stack_trace: str | None = None,
        known_services: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """
        使用 LLM 语义理解判断日志是否包含下游服务调用。

        Args:
            message: 日志消息
            stack_trace: 异常堆栈（可选）
            known_services: 已知服务名称列表，用于提示 LLM

        Returns:
            (has_downstream, service_name)
        """
        client = self._get_client()
        if not client:
            return False, None

        service_list = ", ".join(known_services) if known_services else "未知"
        system_prompt = DOWNSTREAM_DETECT_SYSTEM_PROMPT.format(service_list=service_list)
        user_prompt = build_downstream_detect_prompt(message, stack_trace, service_list)

        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=128,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            if result.get("has_downstream"):
                svc = result.get("service_name")
                return True, svc if svc else None
            return False, None
        except Exception as e:
            logger.debug(f"LLM下游检测失败: {e}")
            return False, None

    def _rule_based_fallback(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        matched_cases: list[dict],
        error_type: str | None = None,
    ) -> dict:
        """LLM不可用时的规则推理降级"""
        bottom_service = call_chain[-1] if call_chain else "unknown"
        error_logs = [l for l in all_logs if l.get("level") == "ERROR"]

        if matched_cases:
            best = matched_cases[0]
            chain_str = " -> ".join(call_chain) if len(call_chain) > 1 else call_chain[0]
            root_cause = (
                f"通过调用链 ({chain_str}) 定位到根因服务: {bottom_service}。\n"
                f"参考历史案例「{best.get('title', 'N/A')}」，根因为: {best.get('root_cause', 'N/A')}"
            )
            suggestion = best.get("suggestion", "建议联系运维团队排查")
            confidence = "medium"
        elif error_logs:
            messages = "\n".join(
                f"  - [{l.get('service_name', '?')}] {l.get('message', '?')}"
                for l in error_logs[:5]
            )
            root_cause = (
                f"基于日志直接推理，故障服务: {bottom_service}\n"
                f"错误信息:\n{messages}"
            )
            suggestion = (
                "1. 检查故障服务运行状态和资源使用情况\n"
                "2. 查看服务最近是否有发布变更或配置变更\n"
                "3. 如影响范围较大，考虑服务降级或流量切换"
            )
            confidence = "low"
        else:
            root_cause = "无法判断根因：未找到ERROR级别日志，信息不足"
            suggestion = "请检查日志采集是否正常，确认告警时间范围是否准确"
            confidence = "low"

        return {
            "root_cause": root_cause,
            "suggestion": suggestion,
            "confidence": confidence,
        }
