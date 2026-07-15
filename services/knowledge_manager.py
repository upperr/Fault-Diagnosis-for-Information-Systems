"""
历史故障知识库生命周期管理

功能：
1. 新故障判定：当召回的历史故障相似度均低于阈值时，判定为新故障
2. 新故障入库：直接使用诊断结果（fault_summary 作为故障现象，排查流程从调用链生成）
"""
import logging
from typing import Optional

from config import (
    VECTOR_SEARCH_THRESHOLD,
    VECTOR_SEARCH_LIMIT,
    NEW_CASE_SIMILARITY_THRESHOLD,
)
from services.knowledge_retriever import get_retriever
from services.llm_client import LLMClient
from services.prompt import build_diagnosis_process_summary_prompt

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """知识库生命周期管理器"""

    def __init__(self):
        self.retriever = get_retriever()
        self.llm = LLMClient()

    def is_new_case(
        self,
        query_text: str,
        custom_threshold: float | None = None,
    ) -> tuple[bool, list[dict], float]:
        """
        判定是否为新的故障案例。

        Args:
            query_text: 当前故障的日志文本
            custom_threshold: 自定义相似度阈值（可选）

        Returns:
            (是否为新案例，最相似的案例列表，最高相似度)
        """
        threshold = custom_threshold or NEW_CASE_SIMILARITY_THRESHOLD

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
            logger.info(f"未检索到任何相似案例，判定为新故障")
            return True, [], 0.0

        max_similarity = max(r.get("similarity", 0) for r in all_results)

        if max_similarity < threshold:
            logger.info(f"最高相似度 {max_similarity:.3f} < 阈值 {threshold}，判定为新故障")
            return True, all_results[:3], max_similarity
        else:
            logger.info(f"最高相似度 {max_similarity:.3f} >= 阈值 {threshold}，使用已有案例")
            return False, all_results[:3], max_similarity

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
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
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
            process = response.choices[0].message.content.strip()
            logger.info(f"生成排查流程：{process[:100]}...")
            return process
        except Exception as e:
            logger.error(f"生成排查流程失败：{e}")
            # 降级：使用调用链
            return " -> ".join(call_chain) if call_chain else "无调用链信息"

    def add_new_case(
        self,
        case_no: int,
        fault_symptom: str,
        diagnosis_process: str,
        root_cause: str,
        suggestion: str,
    ) -> bool:
        """
        将新故障案例添加到知识库。

        Args:
            case_no: 案例编号
            fault_symptom: 故障现象（直接使用 fault_summary）
            diagnosis_process: 排查流程
            root_cause: 根因分析
            suggestion: 处置建议

        Returns:
            是否添加成功
        """
        conn = self.retriever.connect()
        cur = conn.cursor()

        try:
            # 生成向量嵌入
            symptom_embedding = self.retriever.get_embedding(fault_symptom)
            process_embedding = self.retriever.get_embedding(diagnosis_process)
            root_cause_embedding = self.retriever.get_embedding(
                f"{root_cause} {suggestion}"
            )

            if not all([symptom_embedding, process_embedding, root_cause_embedding]):
                logger.error("向量嵌入生成失败")
                return False

            # 插入数据库
            embedding_str = lambda e: "[" + ",".join(map(str, e)) + "]"

            cur.execute(
                """
                INSERT INTO fault_cases 
                (case_no, fault_symptom, diagnosis_process, root_cause, suggestion,
                 symptom_embedding, diagnosis_process_embedding, root_cause_embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector, %s::vector, %s::vector)
                """,
                (
                    case_no,
                    fault_symptom,
                    diagnosis_process,
                    root_cause,
                    suggestion,
                    embedding_str(symptom_embedding),
                    embedding_str(process_embedding),
                    embedding_str(root_cause_embedding),
                ),
            )

            conn.commit()
            logger.info(f"成功添加新案例 #{case_no} 到知识库")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"添加案例失败：{e}")
            return False

    def auto_add_new_case(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        diagnosis_result: dict,
    ) -> tuple[bool, str]:
        """
        自动判定并添加新故障案例。
        故障现象直接使用诊断结果中的 fault_summary。

        Args:
            call_chain: 调用链
            all_logs: 全链路日志
            diagnosis_result: 诊断结果（包含 fault_summary, root_cause, suggestion）

        Returns:
            (是否添加了新案例，消息)
        """
        # 1. 构建查询文本
        query_text = self._build_query_text(all_logs)

        # 2. 判定是否为新故障
        is_new, similar_cases, max_sim = self.is_new_case(query_text)

        if not is_new:
            return False, f"已有相似案例（最高相似度：{max_sim:.3f}）"

        # 3. 直接使用诊断结果中的 fault_summary
        fault_symptom = diagnosis_result.get(
            "fault_summary",
            "未知故障现象",
        )
        logger.info(f"使用诊断结果作为故障现象：{fault_symptom[:50]}...")

        # 4. 生成排查流程
        logger.info("生成排查流程...")
        diagnosis_process = self.generate_diagnosis_process(call_chain, all_logs)

        # 5. 获取下一个案例编号
        case_no = self._get_next_case_no()

        # 6. 添加到知识库
        success = self.add_new_case(
            case_no=case_no,
            fault_symptom=fault_symptom,
            diagnosis_process=diagnosis_process,
            root_cause=diagnosis_result.get("root_cause", ""),
            suggestion=diagnosis_result.get("suggestion", ""),
        )

        if success:
            return True, f"已添加新案例 #{case_no} 到知识库"
        else:
            return False, "添加案例失败"

    def _build_query_text(self, all_logs: list[dict]) -> str:
        """构建用于检索的查询文本"""
        parts = []

        # 日志信息
        for log in all_logs[:10]:
            msg = log.get("message", "")
            level = log.get("level", "?")
            svc = log.get("_source_service", log.get("service_name", "?"))
            parts.append(f"[{level}] {svc}: {msg}")

        return "\n".join(parts)

    def _get_next_case_no(self) -> int:
        """获取下一个案例编号"""
        conn = self.retriever.connect()
        cur = conn.cursor()

        try:
            cur.execute("SELECT MAX(case_no) FROM fault_cases")
            row = cur.fetchone()
            max_no = row[0] if row and row[0] else 0
            return max_no + 1
        except Exception as e:
            logger.error(f"获取案例编号失败：{e}")
            return 1000


# 全局实例
_manager: Optional[KnowledgeManager] = None


def get_manager() -> KnowledgeManager:
    """获取全局知识库管理器实例"""
    global _manager
    if _manager is None:
        _manager = KnowledgeManager()
    return _manager
