"""
PostgreSQL 向量知识库检索模块

提供基于向量相似度的历史故障案例检索功能。
使用 OpenAI 兼容 API 调用本地嵌入模型。
支持三个检索字段：symptom（故障现象）、diagnosis_process（排查流程）、root_cause（根因）。
"""
import logging
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

from config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
)

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """知识库检索器"""

    def __init__(self):
        self.conn = None
        self.embed_client = OpenAI(
            base_url=OPENAI_BASE_URL,
            api_key=OPENAI_API_KEY,
        )

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
        threshold: float = 0.5,
        limit: int = 5,
    ) -> list[dict]:
        """
        基于向量相似度检索故障案例。

        Args:
            embedding: 查询向量（768 维）
            search_field: 检索字段 ('symptom', 'diagnosis_process', 'root_cause')
            threshold: 相似度阈值 (0-1)
            limit: 返回数量

        Returns:
            匹配的故障案例列表
        """
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

            logger.info(f"检索到 {len(results)} 条相似案例 (field={search_field}, threshold={threshold})")
            return results

        except Exception as e:
            logger.error(f"检索失败：{e}")
            return []

    def get_case_by_no(self, case_no: int) -> Optional[dict]:
        """根据案例编号获取详情"""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute(
                "SELECT * FROM fault_cases WHERE case_no = %s",
                (case_no,),
            )
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

    def search_by_keyword(self, keyword: str, limit: int = 10) -> list[dict]:
        """
        基于关键词全文检索。

        Args:
            keyword: 搜索关键词
            limit: 返回数量

        Returns:
            匹配的故障案例列表
        """
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
