"""
批量导入历史故障知识
支持：
1. JSON 文件上传和解析（支持中文和英文两种字段格式）
2. 基于故障现象的排重检测
3. 用户确认覆盖或跳过重复案例
4. 批量向量化和存储
"""
import logging
from typing import List, Dict, Tuple, Optional
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


class BatchImporter:
    """批量导入器 - 处理历史故障知识的批量导入"""

    def __init__(self, retriever, llm):
        self.retriever = retriever
        self.llm = llm

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

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        生成向量嵌入（调用 retriever 的 get_embedding 方法）
        """
        return self.retriever.get_embedding(text)

    def _embedding_to_pg_array(self, embedding: List[float]) -> str:
        """
        将向量转换为 PostgreSQL 数组字符串
        格式：[0.1,0.2,0.3,...]
        """
        return "[" + ",".join(map(str, embedding)) + "]"

    def _normalize_case(self, case: Dict) -> Optional[Dict]:
        """
        标准化案例数据，支持中文和英文两种字段格式
        
        Args:
            case: 原始案例数据
        
        Returns:
            标准化后的案例数据（英文字段），如果缺少必填字段则返回 None
        """
        # 支持中文和英文两种字段格式
        fault_symptom = case.get('故障现象') or case.get('fault_symptom')
        diagnosis_process = case.get('排查流程') or case.get('diagnosis_process')
        root_cause = case.get('根因分析') or case.get('根因分析') or case.get('root_cause')
        suggestion = case.get('处置建议') or case.get('suggestion')
        
        # 验证必填字段
        missing = []
        if not fault_symptom:
            missing.append('故障现象/fault_symptom')
        if not diagnosis_process:
            missing.append('排查流程/diagnosis_process')
        if not root_cause:
            missing.append('根因分析/root_cause')
        if not suggestion:
            missing.append('处置建议/suggestion')
        
        if missing:
            return None
        
        # 返回标准化格式（英文字段）
        return {
            'fault_symptom': fault_symptom.strip(),
            'diagnosis_process': diagnosis_process.strip(),
            'root_cause': root_cause.strip(),
            'suggestion': suggestion.strip(),
        }

    def check_duplicates(
        self, 
        cases: List[Dict]
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        检查导入案例与现有知识库的重复情况
        
        Args:
            cases: 待导入的案例列表，每个案例包含：
                   - fault_symptom / 故障现象
                   - diagnosis_process / 排查流程
                   - root_cause / 根因分析
                   - suggestion / 处置建议
        
        Returns:
            (new_cases, duplicate_cases, skip_cases)
            - new_cases: 全新案例（无重复）
            - duplicate_cases: 重复案例（需要用户确认是否覆盖）
            - skip_cases: 跳过的案例（用户选择不覆盖）
        """
        conn = self.retriever.connect()
        cur = conn.cursor()
        
        new_cases = []
        duplicate_cases = []
        
        try:
            for case in cases:
                # 标准化案例数据
                normalized = self._normalize_case(case)
                if not normalized:
                    logger.warning(f"跳过无效案例：缺少必填字段")
                    continue
                
                fault_symptom = normalized['fault_symptom']
                
                # 查询现有知识库中是否有相同故障现象的案例
                cur.execute(
                    """
                    SELECT case_no, fault_symptom, diagnosis_process, root_cause, suggestion
                    FROM fault_cases
                    WHERE fault_symptom = %s
                    """,
                    (fault_symptom,)
                )
                existing = cur.fetchone()
                
                if existing:
                    # 发现重复
                    duplicate_cases.append({
                        'import_case': normalized,
                        'existing_case': {
                            'case_no': existing[0],
                            'fault_symptom': existing[1],
                            'diagnosis_process': existing[2],
                            'root_cause': existing[3],
                            'suggestion': existing[4],
                        }
                    })
                else:
                    # 新案例
                    new_cases.append(normalized)
            
            logger.info(f"排重检测完成：{len(new_cases)} 个新案例，{len(duplicate_cases)} 个重复案例")
            return new_cases, duplicate_cases, []
            
        except Exception as e:
            logger.error(f"排重检测失败：{e}")
            raise e
        finally:
            cur.close()
            conn.close()

    def import_cases(
        self,
        cases: List[Dict],
        overwrite_duplicates: bool = False
    ) -> Dict:
        """
        批量导入案例到知识库
        
        Args:
            cases: 待导入的案例列表
            overwrite_duplicates: 是否覆盖重复案例（默认 False，即跳过重复）
        
        Returns:
            导入结果统计：
            - total: 总案例数
            - success: 成功导入数
            - skipped: 跳过数
            - errors: 错误列表
        """
        result = {
            'total': len(cases),
            'success': 0,
            'skipped': 0,
            'errors': []
        }
        
        conn = self.retriever.connect()
        cur = conn.cursor()
        
        try:
            for idx, original_case in enumerate(cases):
                try:
                    # 标准化案例数据
                    case = self._normalize_case(original_case)
                    if not case:
                        result['errors'].append(f"案例 {idx+1}: 缺少必填字段")
                        result['skipped'] += 1
                        continue
                    
                    fault_symptom = case['fault_symptom']
                    
                    # 检查是否重复
                    cur.execute(
                        "SELECT case_no FROM fault_cases WHERE fault_symptom = %s",
                        (fault_symptom,)
                    )
                    existing = cur.fetchone()
                    
                    if existing:
                        if overwrite_duplicates:
                            # 覆盖现有案例
                            cur.execute(
                                """
                                UPDATE fault_cases
                                SET diagnosis_process = %s, root_cause = %s, suggestion = %s
                                WHERE fault_symptom = %s
                                """,
                                (
                                    case['diagnosis_process'],
                                    case['root_cause'],
                                    case['suggestion'],
                                    fault_symptom
                                )
                            )
                            logger.info(f"覆盖案例：{fault_symptom[:20]}...")
                        else:
                            # 跳过
                            logger.info(f"跳过重复案例：{fault_symptom[:20]}...")
                            result['skipped'] += 1
                            continue
                    else:
                        # 新案例 - 生成向量嵌入
                        symptom_embedding = self._get_embedding(fault_symptom)
                        process_embedding = self._get_embedding(case['diagnosis_process'])
                        root_cause_embedding = self._get_embedding(
                            f"{case['root_cause']} {case['suggestion']}"
                        )
                        
                        if not all([symptom_embedding, process_embedding, root_cause_embedding]):
                            result['errors'].append(f"案例 {idx+1}: 向量嵌入生成失败")
                            result['skipped'] += 1
                            continue
                        
                        # 获取下一个案例编号
                        case_no = self._get_next_case_no()
                        
                        # 插入数据库
                        values = [(
                            case_no,
                            fault_symptom,
                            case['diagnosis_process'],
                            case['root_cause'],
                            case['suggestion'],
                            self._embedding_to_pg_array(symptom_embedding) if symptom_embedding else '[]',
                            self._embedding_to_pg_array(process_embedding) if process_embedding else '[]',
                            self._embedding_to_pg_array(root_cause_embedding) if root_cause_embedding else '[]',
                        )]
                        
                        execute_values(
                            cur,
                            """
                            INSERT INTO fault_cases 
                            (case_no, fault_symptom, diagnosis_process, root_cause, suggestion,
                             symptom_embedding, diagnosis_process_embedding, root_cause_embedding)
                            VALUES %s
                            """,
                            values,
                            template="(%s, %s, %s, %s, %s, %s::vector, %s::vector, %s::vector)",
                        )
                        logger.info(f"成功导入案例 #{case_no}: {fault_symptom[:20]}...")
                    
                    result['success'] += 1
                    
                except Exception as e:
                    error_msg = f"案例 {idx+1} 导入失败：{str(e)}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
                    result['skipped'] += 1
            
            conn.commit()
            logger.info(f"批量导入完成：成功 {result['success']}/{result['total']}, 跳过 {result['skipped']}")
            return result
            
        except Exception as e:
            conn.rollback()
            logger.error(f"批量导入失败：{e}")
            raise e
        finally:
            cur.close()
            conn.close()

    def clear_knowledge_base(self) -> Dict:
        """
        清空知识库
        
        Returns:
            清空结果：
            - deleted_count: 删除的案例数
        """
        conn = self.retriever.connect()
        cur = conn.cursor()
        
        try:
            # 获取删除前的记录数
            cur.execute("SELECT COUNT(*) FROM fault_cases")
            count = cur.fetchone()[0]
            
            # 使用 TRUNCATE 清空表
            cur.execute("TRUNCATE TABLE fault_cases RESTART IDENTITY;")
            conn.commit()
            
            logger.info(f"知识库已清空，删除 {count} 个案例")
            return {'deleted_count': count}
            
        except Exception as e:
            conn.rollback()
            logger.error(f"清空知识库失败：{e}")
            raise e
        finally:
            cur.close()
            conn.close()
