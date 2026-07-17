"""
新故障检测器 - 两阶段检测逻辑

功能:
1. 阶段 1: 基于向量相似度阈值初筛 (默认 0.5)
2. 阶段 2: 若相似度高于阈值，使用 LLM 进行语义检测
"""
import logging
import json
from typing import Optional

from services.config import (
    VECTOR_SEARCH_LIMIT,
    NEW_CASE_INITIAL_THRESHOLD,
    NEW_CASE_LLM_REVIEW_ENABLED,
    NEW_CASE_LLM_THRESHOLD,
    LLM_MODEL,
)
from services.prompt import (
    build_new_case_review_prompt,
    NEW_CASE_REVIEW_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class CaseDetector:
    """新故障检测器 - 负责两阶段新故障判定"""

    def __init__(self, retriever, llm_client):
        self.retriever = retriever
        self.llm = llm_client
        self._llm_client = None  # 懒加载的 LLM 客户端

    def _get_llm_client(self):
        """获取 LLM 客户端 (懒加载)"""
        if self._llm_client is None:
            self._llm_client = self.llm._get_client()
        return self._llm_client

    def is_new_case_initial(
        self,
        query_text: str,
        custom_threshold: float | None = None,
    ) -> tuple[bool, list[dict], float]:
        """
        【阶段 1】初筛：基于向量相似度判定是否需要 LLM 复查是否为新故障。

        注意：此方法仅用于判断是否需要进入"新故障入库"的复查流程，
        不影响知识召回机制（知识召回在任何情况下都会正常检索相似案例）。

        Args:
            query_text: 当前故障的日志文本
            custom_threshold: 自定义相似度阈值（可选）

        Returns:
            (是否需要 LLM 复查，最相似的案例列表，最高相似度)
            - need_review=True: 相似度低于阈值，可能为新故障，需要 LLM 复查是否入库
            - need_review=False: 相似度高于阈值，已有相似案例，无需复查入库
        """
        threshold = custom_threshold or NEW_CASE_INITIAL_THRESHOLD

        # 从故障现象和排查流程两个维度检索
        embedding = self.retriever.get_embedding(query_text)

        # 检索故障现象
        symptom_results = self.retriever.search_by_embedding(
            embedding=embedding,
            search_field="symptom",
            threshold=0.0,
            limit=VECTOR_SEARCH_LIMIT,
        )

        # 检索排查流程
        process_results = self.retriever.search_by_embedding(
            embedding=embedding,
            search_field="diagnosis_process",
            threshold=0.0,
            limit=VECTOR_SEARCH_LIMIT,
        )

        # 合并结果，取最高相似度
        all_results = symptom_results + process_results
        if not all_results:
            logger.info(f"未检索到任何相似案例，需要 LLM 复查是否入库")
            return True, [], 0.0  # 需要 LLM 复查

        max_similarity = max(r.get("similarity", 0) for r in all_results)

        if max_similarity < threshold:
            logger.info(f"最高相似度 {max_similarity:.3f} < 阈值 {threshold}，需要 LLM 复查是否入库")
            return True, all_results[:3], max_similarity  # 需要 LLM 复查
        else:
            logger.info(f"最高相似度 {max_similarity:.3f} >= 阈值 {threshold}，已有相似案例，无需复查入库")
            return False, all_results[:3], max_similarity  # 已有相似案例，无需复查入库

    def review_with_llm(
        self,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
        similar_cases: list[dict],
    ) -> tuple[bool, dict]:
        """
        【阶段 2】LLM 语义复查：基于语义判断是否为新故障。

        Args:
            alert_symptom: 当前告警的故障现象
            affected_services: 受影响的服务链
            suggestion: 处置建议
            similar_cases: 初筛得到的相似案例

        Returns:
            (是否为新故障，LLM 复查结果)
            - is_new=True: LLM 确认为新故障
            - is_new=False: LLM 认为是已有故障
        """
        if not similar_cases:
            logger.info("无相似案例，LLM 确认为新故障")
            return True, {
                "is_new_case": True,
                "confidence_score": 1.0,
                "reason": "无相似历史案例",
            }

        prompt = build_new_case_review_prompt(
            alert_symptom=alert_symptom,
            affected_services=affected_services,
            suggestion=suggestion,
            similar_cases=similar_cases,
        )

        try:
            client = self._get_llm_client()
            if not client:
                logger.warning("LLM 不可用，降级为新故障")
                return True, {
                    "is_new_case": True,
                    "confidence_score": 0.0,
                    "error": "LLM 不可用",
                }

            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": NEW_CASE_REVIEW_SYSTEM_PROMPT,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            content = response.choices[0].message.content
            if not content:
                logger.warning("LLM 返回空内容")
                content = "{}"
            content = content.strip()
            
            # 解析 JSON 响应
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"LLM 响应解析失败，使用默认值：{content[:100]}")
                result = {
                    "is_new_case": True,
                    "confidence_score": 0.5,
                    "reason": "解析失败",
                }

            # LLM 返回的是 is_existing_case，需要转换为 is_new_case
            is_existing = result.get("is_existing_case", False)
            confidence = result.get("confidence_score", 0.0)

            # 如果 LLM 认为是已有故障 (is_existing=True 且 confidence >= 阈值)，则不是新故障
            # 否则是新故障
            if is_existing and confidence >= NEW_CASE_LLM_THRESHOLD:
                logger.info(f"LLM 判定为已有故障 (置信度：{confidence:.3f})")
                return False, result
            else:
                logger.info(f"LLM 确认为新故障 (is_existing={is_existing}, confidence={confidence:.3f})")
                return True, result

        except Exception as e:
            logger.error(f"LLM 语义复查失败：{e}，降级为新故障")
            return True, {
                "is_new_case": True,
                "confidence_score": 0.0,
                "error": str(e),
            }

    def is_new_case_llm_review(
        self,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
        similar_cases: list[dict],
    ) -> tuple[bool, str | dict, dict]:
        """
        仅执行 LLM 复查（不包含向量检索）。

        用于 root_cause.py 复用知识召回的检索结果，避免重复检索。

        Args:
            alert_symptom: 告警故障现象
            affected_services: 受影响服务链
            suggestion: 处置建议
            similar_cases: 知识召回的相似案例结果

        Returns:
            (是否需要用户确认，消息/确认信息，LLM 复查结果)
        """
        if not NEW_CASE_LLM_REVIEW_ENABLED:
            logger.info("LLM 复查已禁用，按新故障处理，待用户确认入库")
            return True, "LLM 复查已禁用", {}

        is_new, llm_result = self.review_with_llm(
            alert_symptom=alert_symptom,
            affected_services=affected_services,
            suggestion=suggestion,
            similar_cases=similar_cases,
        )

        if is_new:
            logger.info(f"LLM 确认为新故障，待用户确认入库")
            return True, "LLM 确认为新故障", llm_result
        else:
            logger.info(f"LLM 判定为已有故障，不触发入库流程")
            return False, "LLM 判定为已有故障", llm_result

    def is_new_case_two_stage(
        self,
        query_text: str,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
    ) -> tuple[bool, list[dict], float, Optional[dict]]:
        """
        两阶段新故障判定（仅用于知识库入库决策，不影响知识召回）。

        流程:
        1. 向量相似度初筛 (阈值 0.5)
           - >= 0.5: 已有相似案例，无需复查入库
           - < 0.5: 进入 LLM 复查是否入库
        2. LLM 语义复查
           - LLM 确认为新故障：返回待确认信息（前端询问用户）
           - LLM 判定为已有故障：不入库

        注意：此方法仅决定是否触发"新故障入库"流程，
        不影响知识召回机制（知识召回在任何情况下都会正常检索相似案例用于诊断）。

        Args:
            query_text: 用于向量检索的查询文本
            alert_symptom: 告警故障现象 (用于 LLM 复查)
            affected_services: 受影响服务链
            suggestion: 处置建议

        Returns:
            (是否为新故障待确认，相似案例列表，最高相似度，LLM 复查结果)
            - is_new_case=True: 新故障，需要用户确认是否入库
            - is_new_case=False: 已有相似案例或 LLM 判定不入库，不触发确认流程
        """
        # 阶段 1: 向量相似度初筛
        need_review, similar_cases, max_sim = self.is_new_case_initial(query_text)

        if not need_review:
            # 相似度 >= 阈值，已有相似案例，无需复查入库
            # 注意：知识召回仍然正常返回相似案例用于诊断
            return False, similar_cases, max_sim, None

        # 阶段 2: LLM 语义复查 (仅在相似度低于阈值时执行)
        if not NEW_CASE_LLM_REVIEW_ENABLED:
            logger.info("LLM 复查已禁用，按新故障处理，待用户确认入库")
            return True, similar_cases, max_sim, None

        # LLM 复查：判断是否真的是新故障（用于入库决策）
        is_new, llm_result = self.review_with_llm(
            alert_symptom=alert_symptom,
            affected_services=affected_services,
            suggestion=suggestion,
            similar_cases=similar_cases,
        )

        if is_new:
            # LLM 确认为新故障，待用户确认入库
            logger.info(f"LLM 确认为新故障，待用户确认入库")
            return True, similar_cases, max_sim, llm_result
        else:
            # LLM 判定为已有故障，不触发入库流程
            logger.info(f"LLM 判定为已有故障，不触发入库流程")
            return False, similar_cases, max_sim, llm_result
