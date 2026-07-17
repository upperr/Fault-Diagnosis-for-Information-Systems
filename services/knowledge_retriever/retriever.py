"""PostgreSQL 向量知识库检索器

提供基于向量相似度的历史故障案例检索功能。
支持完整检索流程：向量粗排 → Rerank 精排 → LLM 决策
"""
import logging
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

from services.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    EMBEDDING_BASE_URL,
    EMBEDDING_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    RERANK_ENABLED,
    VECTOR_SEARCH_THRESHOLD,
    VECTOR_SEARCH_LIMIT,
    LLM_DECISION_TOP_K,
)
from .rerank_client import get_rerank_client
from .decision_maker import get_decision_maker

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """知识库检索器
    
    支持完整的检索流程：
    1. 向量相似度粗排（PostgreSQL pgvector）
    2. Reranker 模型精排（阿里云 qwen3-rerank）
    3. LLM 最终决策
    """

    def __init__(self):
        self.conn = None
        self.embed_client = OpenAI(
            base_url=EMBEDDING_BASE_URL,
            api_key=EMBEDDING_API_KEY,
        )
        self.rerank_client = None
        self.decision_maker = None

    def get_rerank_client(self):
        """获取或创建 Reranker 客户端"""
        if self.rerank_client is None:
            self.rerank_client = get_rerank_client()
        return self.rerank_client
    
    def get_decision_maker(self):
        """获取或创建决策器"""
        if self.decision_maker is None:
            self.decision_maker = get_decision_maker()
        return self.decision_maker

    def get_embedding(self, text: str) -> list[float]:
        """获取文本向量嵌入"""
        try:
            response = self.embed_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"获取向量嵌入失败：{e}")
            return []

    def connect(self):
        """连接数据库"""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
            )
        return self.conn

    def close(self):
        """关闭连接"""
        if self.conn and not self.conn.closed:
            self.conn.close()
            self.conn = None

    def search_by_embedding(
        self,
        embedding: list[float],
        search_field: str = "symptom",
        threshold: float | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """基于向量相似度检索故障案例（粗排）

        Args:
            embedding: 查询向量
            search_field: 检索字段 ('symptom', 'diagnosis_process', 'root_cause')
            threshold: 相似度阈值，默认使用 VECTOR_SEARCH_THRESHOLD
            limit: 返回数量，默认使用 VECTOR_SEARCH_LIMIT

        Returns:
            匹配的故障案例列表
        """
        threshold = threshold if threshold is not None else VECTOR_SEARCH_THRESHOLD
        limit = limit if limit is not None else VECTOR_SEARCH_LIMIT
        
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            func_name = f"search_by_{search_field}"
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"

            cur.execute(
                f"""
                SELECT * FROM {func_name}(
                    %s::vector({EMBEDDING_DIM}),
                    %s,
                    %s
                )
                """,
                (embedding_str, threshold, limit),
            )

            results = []
            for row in cur.fetchall():
                results.append({
                    "case_no": row["case_no"],
                    "fault_symptom": row["fault_symptom"],
                    "diagnosis_process": row["diagnosis_process"],
                    "root_cause": row["root_cause"],
                    "suggestion": row["suggestion"],
                    "similarity": float(row["similarity"]),
                })

            logger.info(f"检索到 {len(results)} 条相似案例 (field={search_field})")
            return results

        except Exception as e:
            logger.error(f"检索失败：{e}")
            return []

    def retrieve_with_rerank(
        self,
        query: str,
        search_fields: list[str] | None = None,
        use_rerank: bool | None = None,
        use_decision: bool = True,
    ) -> dict:
        """完整检索流程：向量粗排 → Rerank 精排 → LLM 决策
        
        Args:
            query: 用户查询文本
            search_fields: 检索字段列表，默认使用所有字段
            use_rerank: 是否使用 Rerank 精排
            use_decision: 是否使用 LLM 决策
            
        Returns:
            包含各阶段结果的字典
        """
        use_rerank = use_rerank if use_rerank is not None else RERANK_ENABLED
        search_fields = search_fields if search_fields is not None else [
            "symptom", "diagnosis_process", "root_cause"
        ]
        
        pipeline_stages = {
            "source": "vector_search",
            "use_rerank": use_rerank,
            "use_decision": use_decision,
            "search_fields": search_fields,
        }
        
        # ========== 步骤 1: 向量相似度粗排 ==========
        embedding = self.get_embedding(query)
        if not embedding:
            logger.warning("无法获取向量嵌入")
            return {
                "query": query,
                "raw_results": [],
                "reranked_results": [],
                "decision": get_decision_maker().decide(query, []),
                "pipeline_stages": pipeline_stages
            }
        
        # 多字段检索，合并结果去重
        all_raw_results = {}
        for field in search_fields:
            results = self.search_by_embedding(
                embedding=embedding,
                search_field=field,
                threshold=VECTOR_SEARCH_THRESHOLD,
                limit=VECTOR_SEARCH_LIMIT,
            )
            for case in results:
                case_no = case["case_no"]
                if case_no not in all_raw_results:
                    all_raw_results[case_no] = case
                else:
                    # 保留最高相似度
                    all_raw_results[case_no]["similarity"] = max(
                        all_raw_results[case_no]["similarity"],
                        case["similarity"]
                    )
        
        raw_results = list(all_raw_results.values())
        raw_results.sort(key=lambda x: x["similarity"], reverse=True)
        pipeline_stages["raw_count"] = len(raw_results)
        
        logger.info(f"粗排召回 {len(raw_results)} 个唯一案例（阈值={VECTOR_SEARCH_THRESHOLD}, limit={VECTOR_SEARCH_LIMIT}）")
        
        # ========== 步骤 2: Reranker 精排 ==========
        reranked_results = raw_results
        if use_rerank and raw_results:
            rerank_client = self.get_rerank_client()
            from services.config import RERANK_TOP_K
            reranked_results = rerank_client.rerank(query, raw_results, RERANK_TOP_K)
            pipeline_stages["rerank_model"] = RERANK_TOP_K
        else:
            logger.info("跳过 Rerank 精排")
        pipeline_stages["reranked_count"] = len(reranked_results)
        
        # ========== 步骤 3: LLM 最终决策 ==========
        decision_maker = self.get_decision_maker()
        decision = decision_maker.decide(query, reranked_results) if use_decision else {}
        pipeline_stages["decision_made"] = use_decision
        
        return {
            "query": query,
            "raw_results": raw_results,
            "reranked_results": reranked_results,
            "decision": decision,
            "pipeline_stages": pipeline_stages
        }

    def get_case_by_no(self, case_no: int) -> Optional[dict]:
        """根据案例编号获取详情"""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("SELECT * FROM fault_cases WHERE case_no = %s", (case_no,))
            row = cur.fetchone()
            if row:
                return {
                    "case_no": row["case_no"],
                    "fault_symptom": row["fault_symptom"],
                    "diagnosis_process": row["diagnosis_process"],
                    "root_cause": row["root_cause"],
                    "suggestion": row["suggestion"],
                }
            return None
        except Exception as e:
            logger.error(f"查询案例失败：{e}")
            return None

    def get_all_cases(self) -> list[dict]:
        """获取所有故障案例"""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("SELECT * FROM fault_cases ORDER BY case_no")
            return [
                {
                    "case_no": row["case_no"],
                    "fault_symptom": row["fault_symptom"],
                    "diagnosis_process": row["diagnosis_process"],
                    "root_cause": row["root_cause"],
                    "suggestion": row["suggestion"],
                }
                for row in cur.fetchall()
            ]
        except Exception as e:
            logger.error(f"获取所有案例失败：{e}")
            return []

    def delete_case(self, case_no: int) -> bool:
        """删除指定案例
        
        Args:
            case_no: 案例编号
            
        Returns:
            删除成功返回 True，案例不存在返回 False
        """
        conn = self.connect()
        cur = conn.cursor()

        try:
            cur.execute("DELETE FROM fault_cases WHERE case_no = %s", (case_no,))
            deleted = cur.rowcount
            conn.commit()
            
            if deleted > 0:
                logger.info(f"已删除案例 #{case_no}")
                return True
            else:
                logger.warning(f"案例 #{case_no} 不存在")
                return False
        except Exception as e:
            conn.rollback()
            logger.error(f"删除案例失败：{e}")
            return False
        finally:
            cur.close()

    def search_by_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        """基于关键词全文检索"""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute(
                """
                SELECT case_no, fault_symptom, diagnosis_process, root_cause, suggestion
                FROM fault_cases
                WHERE to_tsvector('simple', root_cause) @@ to_tsquery('simple', %s)
                   OR to_tsvector('simple', fault_symptom) @@ to_tsquery('simple', %s)
                   OR to_tsvector('simple', diagnosis_process) @@ to_tsquery('simple', %s)
                LIMIT %s
                """,
                (keyword, keyword, keyword, limit),
            )

            return [
                {
                    "case_no": row["case_no"],
                    "fault_symptom": row["fault_symptom"],
                    "diagnosis_process": row["diagnosis_process"],
                    "root_cause": row["root_cause"],
                    "suggestion": row["suggestion"],
                }
                for row in cur.fetchall()
            ]

        except Exception as e:
            logger.error(f"关键词检索失败：{e}")
            return []


# 全局实例
_retriever: Optional[KnowledgeRetriever] = None


def get_retriever() -> KnowledgeRetriever:
    """获取全局检索器实例"""
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
