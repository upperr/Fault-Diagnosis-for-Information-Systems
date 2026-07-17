"""
历史故障知识库数据导入脚本

从 Excel 文件读取数据，生成向量嵌入，导入 PostgreSQL 数据库。
使用 OpenAI 兼容 API 调用本地嵌入模型（如 Ollama、vLLM、text-embedding-v2 等）。
"""
import os
import sys
import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI

# 将 code 目录加入 path
CODE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CODE_DIR))

from services.config import (
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    KNOWLEDGE_EXCEL_FILE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("import_knowledge")

EXCEL_FILE = KNOWLEDGE_EXCEL_FILE


def get_embedding(text: str) -> list[float]:
    """
    调用 OpenAI 兼容 API 获取文本向量嵌入。
    支持本地模型（Ollama、vLLM、text-embedding-v2 等）。
    返回指定维度向量。
    """
    client = OpenAI(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
    )
    
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"获取向量嵌入失败：{e}")
        return []


def connect_db():
    """连接 PostgreSQL 数据库"""
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    return conn


def load_excel_data() -> list[dict]:
    """从 Excel 加载数据"""
    if not EXCEL_FILE.exists():
        logger.error(f"Excel 文件不存在：{EXCEL_FILE}")
        sys.exit(1)
    
    df = pd.read_excel(EXCEL_FILE)
    records = []
    
    for _, row in df.iterrows():
        records.append({
            "case_no": int(row.get("序号", 0)),
            "fault_symptom": str(row.get("故障现象", "")),
            "diagnosis_process": str(row.get("排查流程", "")),
            "root_cause": str(row.get("根因", "")),
            "suggestion": str(row.get("处置建议", "")),
        })
    
    logger.info(f"从 Excel 加载 {len(records)} 条故障案例")
    return records


def generate_embeddings(records: list[dict]) -> list[dict]:
    """为每条记录生成向量嵌入（故障现象、排查流程、根因三个字段）"""
    logger.info("开始生成向量嵌入...")
    
    for i, record in enumerate(records):
        # 故障现象向量
        record["symptom_embedding"] = get_embedding(record["fault_symptom"])
        
        # 排查流程向量
        record["diagnosis_process_embedding"] = get_embedding(record["diagnosis_process"])
        
        # 根因向量
        record["root_cause_embedding"] = get_embedding(
            f"{record['root_cause']} {record['suggestion']}"
        )
        
        if (i + 1) % 5 == 0:
            logger.info(f"  已处理 {i + 1}/{len(records)} 条")
    
    # 检查是否有失败的
    failed = sum(
        1 for r in records 
        if not r.get("symptom_embedding") or not r.get("diagnosis_process_embedding") or not r.get("root_cause_embedding")
    )
    if failed:
        logger.warning(f"有 {failed} 条记录的向量生成失败")
    
    return records


def import_to_db(records: list[dict]):
    """导入数据到 PostgreSQL"""
    logger.info(f"开始导入数据到 PostgreSQL ({POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB})...")
    
    conn = connect_db()
    try:
        cur = conn.cursor()
        
        # 清空现有数据
        cur.execute("TRUNCATE TABLE fault_cases RESTART IDENTITY;")
        
        # 批量插入
        values = [
            (
                r["case_no"],
                r["fault_symptom"],
                r["diagnosis_process"],
                r["root_cause"],
                r["suggestion"],
                r.get("symptom_embedding", []),
                r.get("diagnosis_process_embedding", []),
                r.get("root_cause_embedding", []),
            )
            for r in records
            if r.get("symptom_embedding") and r.get("diagnosis_process_embedding") and r.get("root_cause_embedding")
        ]
        
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
        
        conn.commit()
        logger.info(f"成功导入 {len(values)} 条记录")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"导入失败：{e}")
        raise
    finally:
        conn.close()


def test_query():
    """测试向量检索"""
    logger.info("测试向量检索...")
    
    conn = connect_db()
    try:
        cur = conn.cursor()
        
        # 查询所有记录
        cur.execute("SELECT case_no, fault_symptom, root_cause FROM fault_cases LIMIT 5;")
        rows = cur.fetchall()
        
        logger.info("数据库中的故障案例:")
        for row in rows:
            logger.info(f"  [{row[0]}] {row[1][:30]}... -> {row[2][:30]}...")
        
        # 查询表统计
        cur.execute("SELECT COUNT(*) FROM fault_cases;")
        count = cur.fetchone()[0]
        logger.info(f"总记录数：{count}")
        
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("  历史故障知识库数据导入")
    print("=" * 60)
    print(f"  API Base URL: {OPENAI_BASE_URL}")
    print(f"  Embedding Model: {EMBEDDING_MODEL}")
    print(f"  Embedding Dim: {EMBEDDING_DIM}")
    print("=" * 60)
    
    # 1. 加载 Excel 数据
    records = load_excel_data()
    
    # 2. 生成向量嵌入（三个字段）
    records = generate_embeddings(records)
    
    # 3. 导入数据库
    import_to_db(records)
    
    # 4. 测试查询
    test_query()
    
    print("\n" + "=" * 60)
    print("  导入完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
