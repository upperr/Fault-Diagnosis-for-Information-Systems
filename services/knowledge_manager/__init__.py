"""
历史故障知识库生命周期管理

功能:
1. 新故障判定：两阶段检测
   - 阶段 1: 基于向量相似度阈值初筛 (默认 0.5)
   - 阶段 2: 若相似度高于阈值，使用 LLM 进行语义检测
2. 新故障入库：需用户确认
   - 前端提示可能为新故障
   - 展示 LLM 生成的排查流程
   - 用户确认后添加至知识库
"""
import logging
from typing import Optional

from services.knowledge_manager.case_detector import CaseDetector
from services.knowledge_manager.case_generator import CaseGenerator
from services.knowledge_manager.case_adder import CaseAdder
from services.knowledge_manager.query_builder import QueryBuilder
from services.knowledge_manager.batch_importer import BatchImporter
from services.knowledge_retriever import get_retriever
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """知识库生命周期管理器 - 组合各子模块功能"""

    def __init__(self):
        self.retriever = get_retriever()
        self.llm = LLMClient()
        
        # 初始化各子模块
        self.query_builder = QueryBuilder()
        self.detector = CaseDetector(self.retriever, self.llm)
        self.generator = CaseGenerator(self.llm)
        self.adder = CaseAdder(self.retriever, self.query_builder)
        self.importer = BatchImporter(self.retriever, self.llm)

    # ========== 委托给 CaseDetector ==========
    
    def is_new_case_initial(
        self,
        query_text: str,
        custom_threshold: float | None = None,
    ) -> tuple[bool, list[dict], float]:
        """
        【阶段 1】初筛：基于向量相似度判定是否需要 LLM 复查是否为新故障。
        """
        return self.detector.is_new_case_initial(query_text, custom_threshold)

    def review_with_llm(
        self,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
        similar_cases: list[dict],
    ) -> tuple[bool, dict]:
        """
        【阶段 2】LLM 语义复查：基于语义判断是否为新故障。
        """
        return self.detector.review_with_llm(
            alert_symptom, affected_services, suggestion, similar_cases
        )

    def is_new_case_llm_review(
        self,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
        similar_cases: list[dict],
    ) -> tuple[bool, str | dict, dict]:
        """
        仅执行 LLM 复查（不包含向量检索）。
        """
        return self.detector.is_new_case_llm_review(
            alert_symptom, affected_services, suggestion, similar_cases
        )

    def is_new_case_two_stage(
        self,
        query_text: str,
        alert_symptom: str,
        affected_services: list[str],
        suggestion: str,
    ) -> tuple[bool, list[dict], float, Optional[dict]]:
        """
        两阶段新故障判定（仅用于知识库入库决策，不影响知识召回）。
        """
        return self.detector.is_new_case_two_stage(
            query_text, alert_symptom, affected_services, suggestion
        )

    # ========== 委托给 CaseGenerator ==========

    def generate_diagnosis_process(
        self,
        call_chain: list[str],
        all_logs: list[dict],
    ) -> str:
        """
        使用 LLM 基于微服务多级调用链路总结生成排查流程。
        """
        return self.generator.generate_diagnosis_process(call_chain, all_logs)

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
        """
        return self.generator.generate_new_case_info(
            call_chain, all_logs, diagnosis_result, alert_time, 
            similar_cases, llm_review_result
        )

    # ========== 委托给 CaseAdder ==========

    def confirm_and_add_case(
        self,
        case_data: dict,
    ) -> tuple[bool, str]:
        """
        用户确认后添加新案例到知识库。
        """
        return self.adder.confirm_and_add_case(case_data)

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
        """
        return self.adder.add_new_case(
            case_no, fault_symptom, diagnosis_process, root_cause, suggestion
        )

    def auto_add_new_case(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        diagnosis_result: dict,
        alert_time: str = "",
    ) -> tuple[bool, str | dict, Optional[dict]]:
        """
        自动判定新故障并生成确认信息 (不自动入库，需用户确认)。
        """
        return self.adder.auto_add_new_case(
            call_chain, all_logs, diagnosis_result, alert_time
        )

    # ========== 委托给 BatchImporter ==========

    def check_import_duplicates(
        self,
        cases: list[dict],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        检查导入案例的重复情况
        """
        return self.importer.check_duplicates(cases)

    def import_knowledge_batch(
        self,
        cases: list[dict],
        overwrite_duplicates: bool = False,
    ) -> dict:
        """
        批量导入知识到知识库
        """
        return self.importer.import_cases(cases, overwrite_duplicates)

    def clear_knowledge_base(self) -> dict:
        """
        清空知识库
        """
        return self.importer.clear_knowledge_base()


# 全局实例
_manager: Optional[KnowledgeManager] = None


def get_manager() -> KnowledgeManager:
    """获取全局知识库管理器实例"""
    global _manager
    if _manager is None:
        _manager = KnowledgeManager()
    return _manager
