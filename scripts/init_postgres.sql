-- PostgreSQL 历史故障知识库初始化脚本
-- 支持 pgvector 向量化存储，用于 RAG 系统

-- 1. 创建扩展（需要超级用户权限）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 创建故障知识表
CREATE TABLE IF NOT EXISTS fault_cases (
    id SERIAL PRIMARY KEY,
    case_no INTEGER UNIQUE NOT NULL,
    fault_symptom TEXT NOT NULL,          -- 故障现象
    diagnosis_process TEXT NOT NULL,      -- 排查流程
    root_cause TEXT NOT NULL,             -- 根因分析
    suggestion TEXT NOT NULL,             -- 处置建议
    symptom_embedding vector(1536),        -- 故障现象向量
    diagnosis_process_embedding vector(1536),  -- 排查流程向量
    root_cause_embedding vector(1536),     -- 根因向量
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建索引
-- 向量相似度索引（余弦相似度）
CREATE INDEX IF NOT EXISTS idx_symptom_embedding ON fault_cases USING ivfflat (symptom_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_diagnosis_process_embedding ON fault_cases USING ivfflat (diagnosis_process_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_root_cause_embedding ON fault_cases USING ivfflat (root_cause_embedding vector_cosine_ops) WITH (lists = 100);

-- 普通文本索引
CREATE INDEX IF NOT EXISTS idx_case_no ON fault_cases(case_no);

-- 4. 创建向量检索函数
-- 按症状相似度检索
CREATE OR REPLACE FUNCTION search_by_symptom(query_embedding vector(1536), match_threshold FLOAT DEFAULT 0.5, match_count INT DEFAULT 5)
RETURNS TABLE (
    case_no INTEGER,
    fault_symptom TEXT,
    diagnosis_process TEXT,
    root_cause TEXT,
    suggestion TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        fc.case_no,
        fc.fault_symptom,
        fc.diagnosis_process,
        fc.root_cause,
        fc.suggestion,
        (1 - (fc.symptom_embedding <=> query_embedding)) AS similarity
    FROM fault_cases fc
    WHERE (1 - (fc.symptom_embedding <=> query_embedding)) > match_threshold
    ORDER BY fc.symptom_embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 按排查流程相似度检索
CREATE OR REPLACE FUNCTION search_by_diagnosis_process(query_embedding vector(1536), match_threshold FLOAT DEFAULT 0.5, match_count INT DEFAULT 5)
RETURNS TABLE (
    case_no INTEGER,
    fault_symptom TEXT,
    diagnosis_process TEXT,
    root_cause TEXT,
    suggestion TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        fc.case_no,
        fc.fault_symptom,
        fc.diagnosis_process,
        fc.root_cause,
        fc.suggestion,
        (1 - (fc.diagnosis_process_embedding <=> query_embedding)) AS similarity
    FROM fault_cases fc
    WHERE (1 - (fc.diagnosis_process_embedding <=> query_embedding)) > match_threshold
    ORDER BY fc.diagnosis_process_embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 按根因相似度检索
CREATE OR REPLACE FUNCTION search_by_root_cause(query_embedding vector(1536), match_threshold FLOAT DEFAULT 0.5, match_count INT DEFAULT 5)
RETURNS TABLE (
    case_no INTEGER,
    fault_symptom TEXT,
    diagnosis_process TEXT,
    root_cause TEXT,
    suggestion TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        fc.case_no,
        fc.fault_symptom,
        fc.diagnosis_process,
        fc.root_cause,
        fc.suggestion,
        (1 - (fc.root_cause_embedding <=> query_embedding)) AS similarity
    FROM fault_cases fc
    WHERE (1 - (fc.root_cause_embedding <=> query_embedding)) > match_threshold
    ORDER BY fc.root_cause_embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 5. 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_fault_cases_updated_at
    BEFORE UPDATE ON fault_cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE fault_cases IS '历史故障知识库 - 存储故障案例及向量化数据';
COMMENT ON COLUMN fault_cases.symptom_embedding IS '故障现象的向量表示（1536 维）';
COMMENT ON COLUMN fault_cases.diagnosis_process_embedding IS '排查流程的向量表示（1536 维）';
COMMENT ON COLUMN fault_cases.root_cause_embedding IS '根因分析的向量表示（1536 维）';
