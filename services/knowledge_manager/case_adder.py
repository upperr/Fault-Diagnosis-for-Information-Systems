"""
案例添加器 - 负责将新故障案例添加到知识库
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CaseAdder:
    """案例添加器 - 负责将新故障案例添加到知识库"""

    def __init__(self, retriever, query_builder):
        self.retriever = retriever
        self.query_builder = query_builder

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
            fault_symptom: 故障现象
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

    def confirm_and_add_case(
        self,
        case_data: dict,
    ) -> tuple[bool, str]:
        """
        用户确认后添加新案例到知识库。

        Args:
            case_data: 新案例数据 (来自 generate_new_case_info 的返回值)
            支持两种 key 格式：英文 (root_cause, suggestion) 或中文 (根因分析，处置建议)

        Returns:
            (是否添加成功，消息)
        """
        case_no = self._get_next_case_no()

        # 支持两种 key 格式（前端可能用英文或中文）
        root_cause = case_data.get("根因分析") or case_data.get("root_cause") or ""
        suggestion = case_data.get("处置建议") or case_data.get("suggestion") or ""

        success = self.add_new_case(
            case_no=case_no,
            fault_symptom=case_data.get("fault_symptom", ""),
            diagnosis_process=case_data.get("diagnosis_process", ""),
            root_cause=root_cause,
            suggestion=suggestion,
        )

        if success:
            logger.info(f"【知识库更新】成功添加新案例 #{case_no} 到知识库")
            return True, f"已添加新案例 #{case_no} 到知识库"
        else:
            logger.error(f"【知识库更新】添加案例 #{case_no} 失败")
            return False, "添加案例失败"

    def auto_add_new_case(
        self,
        call_chain: list[str],
        all_logs: list[dict],
        diagnosis_result: dict,
        alert_time: str = "",
    ) -> tuple[bool, str | dict, Optional[dict]]:
        """
        自动判定新故障并生成确认信息 (不自动入库，需用户确认)。

        流程:
        1. 向量相似度初筛 (阈值 0.5)
           - >= 0.5: 已有故障，返回相似案例
           - < 0.5: 进入 LLM 复查
        2. LLM 语义复查
           - LLM 认为是新故障：生成确认信息，返回待确认
           - LLM 认为是已有故障：返回相似案例

        Args:
            call_chain: 调用链
            all_logs: 全链路日志
            diagnosis_result: 诊断结果（包含 fault_summary, root_cause, suggestion）
            alert_time: 告警时间

        Returns:
            (是否需要用户确认，消息/确认信息，附加数据)
            - 如果 is_new_case=False: (False, "已有相似案例", similar_cases)
            - 如果 is_new_case=True: (True, new_case_info_dict, None)
        """
        # 1. 构建查询文本
        query_text = self.query_builder.build_query_text(all_logs)

        # 2. 两阶段判定 (需要导入 detector，避免循环依赖)
        from services.knowledge_manager.case_detector import CaseDetector
        from services.llm_client import LLMClient
        
        llm_client = LLMClient()
        detector = CaseDetector(self.retriever, llm_client)
        
        is_new, similar_cases, max_sim, llm_result = detector.is_new_case_two_stage(
            query_text=query_text,
            alert_symptom=diagnosis_result.get("故障现象", ""),
            affected_services=call_chain,
            suggestion=diagnosis_result.get("处置建议", ""),
        )

        if not is_new:
            # 判定为已有故障
            logger.info(f"【知识库更新检测】已有相似案例（最高相似度：{max_sim:.3f}），不触发入库")
            return False, f"已有相似案例（最高相似度：{max_sim:.3f}）", {
                "similar_cases": similar_cases,
                "llm_review_result": llm_result,
            }

        # 3. 生成新故障确认信息
        logger.info(f"【知识库更新检测】检测到可能的新故障（最高相似度：{max_sim:.3f}），等待用户确认")
        
        from services.knowledge_manager.case_generator import CaseGenerator
        
        generator = CaseGenerator(llm_client)
        new_case_info = generator.generate_new_case_info(
            call_chain=call_chain,
            all_logs=all_logs,
            diagnosis_result=diagnosis_result,
            alert_time=alert_time,
            similar_cases=similar_cases,
            llm_review_result=llm_result,
        )

        return True, new_case_info, None
