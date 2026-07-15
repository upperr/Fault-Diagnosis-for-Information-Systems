"""根因智能推理模块

使用 PostgreSQL 向量知识库进行相似度检索，结合 LLM 进行根因推理。
支持新故障自动入库功能。
"""
import logging

from config import VECTOR_SEARCH_THRESHOLD, VECTOR_SEARCH_LIMIT, ENABLE_AUTO_LEARN
from services.knowledge_retriever import get_retriever
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class RootCauseAnalyzer:
    """结合向量知识库检索和 LLM 进行根因推理"""

    def __init__(self, auto_learn: bool = False):
        """
        Args:
            auto_learn: 是否启用自动学习（新故障自动入库）
        """
        self.kb_retriever = get_retriever()
        self.llm = LLMClient()
        self.auto_learn = auto_learn or ENABLE_AUTO_LEARN

    def analyze(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        error_type: str | None = None,
        alert_info: dict | None = None,
    ) -> dict:
        """
        分析根因。

        流程：
        1. 从日志中提取关键错误信息
        2. 使用向量检索从 PostgreSQL 知识库中查找相似案例
        3. 调用 LLM 节点，结合日志和相似案例推理根因
        4. 生成 fault_summary
        5. 如果启用了自动学习且判定为新故障，则添加到知识库

        Args:
            call_chain: 调用链
            all_logs: 全链路日志
            error_type: 错误类型
            alert_info: 告警信息（可选，用于日志记录）

        Returns:
            {
                "root_cause": str,
                "suggestion": str,
                "fault_summary": str,  # 故障现象总结
                "matched_cases": list[dict],
                "confidence": str,  # high / medium / low
                "is_new_case": bool,  # 是否为新故障
                "new_case_message": str,  # 新故障入库消息
            }
        """
        # 1. 向量检索（从 PostgreSQL 知识库）
        query_text = self._extract_log_text(all_logs)
        try:
            matched_cases, is_new, max_sim = self._vector_search_with_judge(query_text, error_type, call_chain)
            logger.info(f"向量检索匹配到 {len(matched_cases)} 条相似案例，最高相似度：{max_sim:.3f}")
        except Exception as e:
            logger.warning(f"知识库检索失败（{e}），使用空案例列表继续推理")
            matched_cases, is_new, max_sim = [], True, 0.0

        # 2. 调用 LLM 进行根因推理
        result = self.llm.reason_root_cause(
            call_chain=call_chain,
            all_logs=all_logs,
            matched_cases=matched_cases,
            error_type=error_type,
        )

        # 3. 生成 fault_summary（用于知识库入库）
        result["fault_summary"] = self._generate_fault_summary(
            call_chain=call_chain,
            all_logs=all_logs,
            root_cause=result.get("root_cause", ""),
        )

        result["matched_cases"] = matched_cases
        result["is_new_case"] = is_new
        result["new_case_message"] = ""

        # 4. 如果启用了自动学习且是新故障，添加到知识库
        if self.auto_learn and is_new:
            from services.knowledge_manager import get_manager
            manager = get_manager()
            success, message = manager.auto_add_new_case(
                call_chain=call_chain,
                all_logs=all_logs,
                diagnosis_result=result,  # 包含 fault_summary, root_cause, suggestion
            )
            result["new_case_message"] = message
            logger.info(f"自动学习：{message}")

        return result

    def _generate_fault_summary(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        root_cause: str,
    ) -> str:
        """
        生成故障现象总结（用于知识库入库）。
        格式：调用链 + 关键错误 + 根因简述

        Args:
            call_chain: 调用链
            all_logs: 全链路日志
            root_cause: 根因分析

        Returns:
            fault_summary 文本
        """
        # 提取关键错误信息
        error_messages = []
        for log in all_logs:
            if log.get("level") == "ERROR":
                msg = log.get("message", "")
                svc = log.get("_source_service", "?")
                error_messages.append(f"{svc}: {msg[:50]}")

        # 构建简洁的故障总结
        chain_str = " -> ".join(call_chain) if call_chain else "未知服务"
        error_str = error_messages[0] if error_messages else "未知错误"
        cause_str = root_cause[:50] if root_cause else "原因待查"

        summary = f"调用链异常 ({chain_str}): {error_str}。根因：{cause_str}"
        return summary

    def _extract_log_text(self, logs: list[dict], max_chars: int = 3000) -> str:
        """
        提取日志关键文本（ERROR 级别优先）。
        日志格式：{ "timestamp", "level", "message", "trace_id", "_source_service" }
        """
        error_logs = [l for l in logs if l.get("level") == "ERROR"]
        other_logs = [l for l in logs if l.get("level") != "ERROR"]

        parts = []
        for log in error_logs + other_logs:
            msg = log.get("message", "")
            stack = log.get("stack_trace", "")
            svc = log.get("_source_service", log.get("service_name", "?"))
            if msg:  # 只添加有内容的日志
                parts.append(f"[{log.get('level', '?')}] {svc}: {msg}")
            if stack:
                parts.append(f"  Stack: {stack[:300]}")

        full_text = "\n".join(parts)
        
        # 如果日志为空，使用调用链信息作为备选
        if not full_text.strip():
            full_text = "无日志数据"
        
        return full_text[:max_chars]

    def _vector_search_with_judge(
        self,
        query_text: str,
        error_type: str | None = None,
        call_chain: list[str] | None = None,
    ) -> tuple[list[dict], bool, float]:
        """
        基于向量相似度检索历史案例，并判定是否为新故障。

        Returns:
            (匹配的案例列表，是否为新故障，最高相似度)
        """
        from config import NEW_CASE_SIMILARITY_THRESHOLD

        matched = []
        
        # 如果查询文本太短，跳过向量检索
        if not query_text.strip() or len(query_text.strip()) < 5:
            logger.warning("查询文本过短，跳过向量检索")
            return [], True, 0.0
        
        embedding = self.kb_retriever.get_embedding(query_text)

        # 1. 故障现象向量检索（优先）
        symptom_results = self.kb_retriever.search_by_embedding(
            embedding=embedding,
            search_field="symptom",
            threshold=0.0,  # 先获取所有结果
            limit=VECTOR_SEARCH_LIMIT * 2,
        )
        matched.extend(symptom_results)

        # 2. 如果结果不足，补充排查流程向量检索
        if len(matched) < VECTOR_SEARCH_LIMIT:
            process_results = self.kb_retriever.search_by_embedding(
                embedding=embedding,
                search_field="diagnosis_process",
                threshold=0.0,
                limit=VECTOR_SEARCH_LIMIT,
            )
            # 避免重复
            existing_ids = {c["case_no"] for c in matched}
            for c in process_results:
                if c["case_no"] not in existing_ids:
                    matched.append(c)

        # 3. 计算最高相似度
        max_sim = max((c.get("similarity", 0) for c in matched), default=0.0)

        # 4. 判定是否为新故障
        is_new = max_sim < NEW_CASE_SIMILARITY_THRESHOLD

        # 5. 过滤并返回结果
        filtered = [c for c in matched if c.get("similarity", 0) >= VECTOR_SEARCH_THRESHOLD]

        # 6. 转换为 LLM 需要的格式
        formatted_cases = []
        for case in filtered[:VECTOR_SEARCH_LIMIT]:
            formatted_cases.append({
                "case_id": f"CASE-{case['case_no']}",
                "title": case["fault_symptom"][:50],
                "fault_symptom": case["fault_symptom"],
                "root_cause": case["root_cause"],
                "suggestion": case["suggestion"],
                "similarity": case.get("similarity", 0.0),  # 添加相似度字段
            })

        return formatted_cases, is_new, max_sim
