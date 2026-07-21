"""
LLM 提示词管理

统一管理所有 LLM 相关的提示词模板。
"""
from datetime import datetime


# ============================================================
# 知识检索与决策提示词
# ============================================================

RETRIEVAL_DECISION_SYSTEM_PROMPT = """你是一个专业的运维故障诊断专家。请根据用户查询和检索到的故障案例，判断是否有高度相关的知识，并给出最终答案。

分析步骤：
1. 仔细阅读用户查询，理解故障现象和关键信息
2. 逐一分析每个检索到的案例（已按 Rerank 分数排序），评估与查询的相关性
3. 从精排结果中筛选出 0 到 {max_cases} 个最相关的案例作为最终答案依据：
   - 如果有高度相关的案例（相关性>0.7），选择最匹配的 1-{max_cases} 个
   - 如果相关性一般（0.5-0.7），综合选择 1-2 个案例给出答案
   - 如果都不相关（<0.5），返回 0 个案例，基于通用经验给出建议
4. 提取选中案例的根因和建议作为答案

输出格式：请严格按照以下 JSON 格式输出：
{{
    "has_relevant_knowledge": true/false,
    "selected_cases": [{{"case_no": 案例编号，"relevance_score": 0.0-1.0}}, ...],  // 0-{max_cases} 个选中的案例
    "best_match_case_no": 案例编号或 null,
    "relevance_score": 0.0-1.0,
    "root_cause": "根因分析",
    "suggestion": "处置建议",
    "reasoning": "判断理由和依据，说明为什么选择这些案例"
}}
"""


def build_retrieval_decision_prompt(
    query: str,
    retrieved_cases: list[dict],
) -> str:
    """
    构建检索决策的用户提示词。
    
    Args:
        query: 用户查询
        retrieved_cases: 检索到的案例列表（已包含 rerank 分数）
    
    Returns:
        提示词文本
    """
    cases_text = ""
    for i, case in enumerate(retrieved_cases, 1):
        score = case.get("rerank_score", case.get("similarity", 0))
        cases_text += f"""
【案例{i}】编号：{case.get('case_no', 'N/A')} | 相关性分数：{score:.3f}
故障现象：{case.get('fault_symptom', 'N/A')}
排查流程：{case.get('diagnosis_process', 'N/A')}
根因：{case.get('root_cause', 'N/A')}
建议：{case.get('suggestion', 'N/A')}
---
"""
    
    if not retrieved_cases:
        cases_text = "  无检索到的案例"
    
    prompt = f"""## 用户查询
{query}

## 检索到的故障案例（按相关性排序）
{cases_text}

## 分析任务
请判断检索到的案例是否与用户查询相关，并给出最终答案。

## 分析结果
"""
    return prompt


# ============================================================
# 根因分析提示词
# ============================================================

ROOT_CAUSE_SYSTEM_PROMPT = """你是一个专业的运维故障分析专家。请分析以下故障信息，推断根本原因并给出处置建议。

要求：
1. 根因分析要具体，指出是哪个组件/配置/代码的问题
2. 处置建议要可操作，分条列出
3. 如果有相似案例，参考其根因和建议
4. 如果无法确定根因，说明缺失的信息

输出格式：请严格按照以下 JSON 格式输出：
{
    "根因分析": "根因分析文本",
    "处置建议": "处置建议文本（分条列出，用\\n 分隔）",
    "confidence": "high/medium/low"
}
"""


def build_root_cause_user_prompt(
    call_chain: list[str],
    all_logs: list[dict],
    matched_cases: list[dict],
    error_type: str | None = None,
) -> str:
    """
    构建根因分析的用户提示词。

    Args:
        call_chain: 调用链列表
        all_logs: 全链路日志列表
        matched_cases: 匹配的历史案例
        error_type: 错误类型

    Returns:
        提示词文本
    """
    # 格式化调用链
    chain_text = " -> ".join(call_chain) if call_chain else "无调用链信息"

    # 格式化日志
    log_lines = []
    for log in all_logs[:20]:
        level = log.get("level", "?")
        svc = log.get("_source_service", log.get("service_name", "?"))
        msg = log.get("message", "")
        stack = log.get("stack_trace", "")
        line = f"  [{level}] {svc}: {msg}"
        if stack:
            line += f"\n    Stack: {stack[:200]}"
        log_lines.append(line)
    logs_text = "\n".join(log_lines)

    # 格式化历史案例
    cases_text = ""
    if matched_cases:
        for i, case in enumerate(matched_cases[:3], 1):
            cases_text += f"""
相似案例 {i}:
  现象：{case.get('fault_symptom', 'N/A')[:100]}
  根因：{case.get('root_cause', 'N/A')[:100]}
  建议：{case.get('suggestion', 'N/A')[:100]}
"""
    else:
        cases_text = "  无相似历史案例"

    prompt = f"""## 服务调用链
{chain_text}

## 全链路日志
{logs_text}

## 错误类型
{error_type or "未知"}

## 相似历史案例
{cases_text}

## 分析结果
"""
    return prompt


# ============================================================
# 故障现象总结提示词
# ============================================================


def build_fault_symptom_summary_prompt(
    call_chain: list[str],
    all_logs: list[dict],
    alert_message: str | None = None,
) -> str:
    """
    构建故障现象总结的提示词。

    Args:
        call_chain: 调用链列表
        all_logs: 全链路日志列表
        alert_message: 告警信息（可选）

    Returns:
        提示词文本
    """
    # 格式化调用链
    chain_text = " -> ".join(call_chain) if call_chain else "无调用链信息"

    # 按服务分组日志，提取关键错误
    logs_by_service = {}
    for log in all_logs:
        svc = log.get("_source_service", log.get("service_name", "unknown"))
        if svc not in logs_by_service:
            logs_by_service[svc] = []
        level = log.get("level", "?")
        msg = log.get("message", "")
        logs_by_service[svc].append(f"    [{level}] {msg}")

    logs_text = ""
    for svc, logs in logs_by_service.items():
        logs_text += f"\n  {svc}:\n" + "\n".join(logs)

    alert_info = f"\n告警信息：{alert_message}" if alert_message else "\n无告警信息"

    prompt = f"""你是一个专业的运维故障分析专家。请根据以下调用链、日志和告警信息，总结故障现象。

## 服务调用链
{chain_text}

## 各服务日志
{logs_text}

## 告警信息{alert_info}

## 任务
请简要总结此故障的现象，要求：
1. 描述清楚哪个服务出现了什么问题
2. 提及关键的错误信息
3. 控制在 50 字以内
4. 使用简洁的专业语言

## 故障现象总结
"""
    return prompt


# ============================================================
# 排查流程总结提示词
# ============================================================


def build_diagnosis_process_summary_prompt(
    call_chain: list[str],
    all_logs: list[dict],
) -> str:
    """
    构建排查流程总结的提示词。

    Args:
        call_chain: 调用链列表
        all_logs: 全链路日志列表

    Returns:
        提示词文本
    """
    # 格式化调用链
    chain_text = " -> ".join(call_chain) if call_chain else "无调用链信息"

    # 按服务分组日志
    logs_by_service = {}
    for log in all_logs:
        svc = log.get("_source_service", log.get("service_name", "unknown"))
        if svc not in logs_by_service:
            logs_by_service[svc] = []
        level = log.get("level", "?")
        msg = log.get("message", "")
        logs_by_service[svc].append(f"    [{level}] {msg}")

    logs_text = ""
    for svc, logs in logs_by_service.items():
        logs_text += f"\n  {svc}:\n" + "\n".join(logs)

    prompt = f"""你是一个专业的运维故障分析专家。请根据以下调用链和日志信息，总结排查流程。

## 服务调用链
{chain_text}

## 各服务日志
{logs_text}

## 任务
请总结排查此故障的流程步骤，要求：
1. 按照调用链顺序描述排查步骤
2. 每一步说明检查了什么、发现了什么
3. 体现从上游到下游的排查思路
4. 使用编号列表格式
5. 控制在 200 字以内

## 排查流程总结
"""
    return prompt


# ============================================================
# 日志关联分析与 Trace ID 确定提示词
# ============================================================

LOG_CORRELATION_SYSTEM_PROMPT = """你是一个专业的运维故障分析专家。请分析以下日志内容，根据日志与告警的关联性以及时间相近程度，锁定最有可能的一条日志链路，确定 trace_id。

分析原则：
1. 时间相近优先：优先选择与告警时间差较小的日志
2. 错误类型匹配：日志内容中的错误信息应与告警信息语义相关
3. 调用链完整性：优先选择能形成完整调用链的 trace_id
4. 错误级别优先：在时间接近度相近的情况下，ERROR 级别日志比 INFO 级别更值得关注

输出格式：请严格按照以下 JSON 格式输出：
{
    "trace_id": "确定的 trace_id",
    "confidence": "high/medium/low",
    "reasoning": "选择该 trace_id 的理由，包括时间差异、错误关联性等分析",
    "key_logs": ["关键日志 1", "关键日志 2", ...]
}
"""


def build_log_correlation_prompt(
    service_name: str,
    alert_message: str,
    alert_time: str,
    logs: list[dict],
) -> str:
    """
    构建日志关联分析的用户提示词。

    Args:
        service_name: 微服务名称
        alert_message: 告警信息
        alert_time: 告警时间
        logs: 该服务在告警时间前后 5 分钟内的所有日志

    Returns:
        提示词文本
    """
    # 解析告警时间
    alert_dt = None
    if alert_time:
        try:
            alert_dt = datetime.fromisoformat(alert_time.rstrip("Z"))
        except Exception:
            pass
    
    # 格式化日志列表
    log_lines = []
    for i, log in enumerate(logs, 1):
        level = log.get("日志等级", log.get("level", "?")).upper()
        timestamp = log.get("产生时间", log.get("timestamp", "?"))
        message = log.get("日志内容", log.get("message", ""))
        trace_id = log.get("traceid", log.get("trace_id", "N/A"))
        downstream = log.get("下游微服务名称", log.get("downstream_service", ""))
        
        # 计算与告警的时间差
        time_diff_str = ""
        if alert_dt:
            log_time_str = timestamp.rstrip("Z") if timestamp else ""
            try:
                log_dt = datetime.fromisoformat(log_time_str)
                diff_sec = abs((log_dt - alert_dt).total_seconds())
                if diff_sec < 60:
                    time_diff_str = f"相差 {diff_sec:.0f} 秒"
                else:
                    time_diff_str = f"相差 {diff_sec/60:.1f} 分钟"
            except Exception:
                time_diff_str = "时间差未知"
        
        line = f"{i}. [{level}] {timestamp} | trace_id={trace_id}"
        if time_diff_str:
            line += f" | 与告警时间{time_diff_str}"
        line += f"\n   内容：{message}"
        if downstream:
            line += f"\n   下游服务：{downstream}"
        log_lines.append(line)
    
    logs_text = "\n".join(log_lines)
    
    prompt = f"""## 告警信息
微服务名称：{service_name}
告警信息：{alert_message}
告警时间：{alert_time}

## 待分析日志（告警时间前后 5 分钟内）
{logs_text}

## 分析任务
请分析以上日志与告警的关联性，确定最有可能的 trace_id。
注意：每条日志已标注与告警时间的差值，请优先选择时间差最小的日志。

## 分析结果
"""
    return prompt


# ============================================================
# 新故障语义检测提示词
# ============================================================

NEW_CASE_REVIEW_SYSTEM_PROMPT = """你是一个专业的运维故障诊断专家。请判断当前告警是否代表一个新的故障类型，还是与某个历史故障本质相同。

分析步骤:
1. 仔细阅读当前告警的故障现象、受影响服务链和处置建议
2. 逐一对比每个相似历史案例的故障现象、根因和建议
3. 评估语义相似性，不仅看表面关键词，更要看故障本质:
   - 如果是同一类问题的不同表现 (如都是数据库连接池耗尽，只是服务不同)，判定为已有故障
   - 如果是全新的故障模式 (如新的错误类型、新的根因、需要不同的排查方法)，判定为新故障
4. 给出置信度评分 (0.0-1.0)，分数越高表示越确定是已有故障

输出格式：请严格按照以下 JSON 格式输出:
{
    "is_existing_case": true/false,
    "confidence_score": 0.0-1.0,
    "most_similar_case_no": 最相似的案例编号或 null,
    "similarity_reason": "相似性分析理由",
    "difference_analysis": "如果有差异，说明差异在哪里",
    "recommendation": "建议 (如：'可参考案例 X 的处置方法' 或 '需要新的排查流程')"
}
"""


def build_new_case_review_prompt(
    alert_symptom: str,
    affected_services: list[str],
    suggestion: str,
    similar_cases: list[dict],
) -> str:
    """
    构建新故障语义检测的用户提示词。
    
    Args:
        alert_symptom: 当前告警的故障现象
        affected_services: 受影响的服务链
        suggestion: 处置建议
        similar_cases: 初筛得到的相似历史案例
    
    Returns:
        提示词文本
    """
    services_text = " -> ".join(affected_services) if affected_services else "未知"
    
    cases_text = ""
    for i, case in enumerate(similar_cases, 1):
        cases_text += f"""
【案例{i}】编号：{case.get('case_no', 'N/A')} | 向量相似度：{case.get('similarity', 0):.3f}
故障现象：{case.get('fault_symptom', 'N/A')}
根因：{case.get('root_cause', 'N/A')}
建议：{case.get('suggestion', 'N/A')}
---
"""
    
    if not similar_cases:
        cases_text = "  无相似历史案例"
    
    prompt = f"""## 当前告警信息
故障现象：{alert_symptom}
受影响服务链：{services_text}
处置建议：{suggestion}

## 相似历史案例 (向量相似度初筛)
{cases_text}

## 分析任务
请判断当前告警是否代表一个新的故障类型，还是与某个历史案例本质相同。
注意：不仅要看表面关键词，更要分析故障的本质 (根因、排查方法、处置方式)。

## 分析结果
"""
    return prompt


# ============================================================
# 新故障确认提示词 (用户确认环节)
# ============================================================

NEW_CASE_CONFIRMATION_PROMPT_TEMPLATE = """## 新故障检测通知

系统检测到以下告警可能是一个**新的故障类型**,与现有知识库中的案例都不匹配。

## 告警信息
- **故障现象**: {symptom}
- **受影响服务**: {services}
- **告警时间**: {alert_time}

## 系统生成的排查流程
{diagnosis_process}

## 处置建议
{suggestion}

## 操作建议
1. 如果确认这是新故障类型，点击"确认添加"将其加入历史故障知识库
2. 如果认为这是已有故障的变体，点击"取消"并参考相似案例处置

## 相似案例参考 (供对比)
{similar_cases_text}
"""


def build_new_case_confirmation_prompt(
    symptom: str,
    services: list[str],
    alert_time: str,
    diagnosis_process: str,
    suggestion: str,
    similar_cases: list[dict],
) -> str:
    """
    构建新故障用户确认提示词。
    
    Args:
        symptom: 故障现象
        services: 受影响服务链
        alert_time: 告警时间
        diagnosis_process: 排查流程
        suggestion: 处置建议
        similar_cases: 相似案例列表
    
    Returns:
        格式化后的确认提示文本
    """
    services_text = " -> ".join(services) if services else "未知"
    
    similar_cases_text = ""
    for i, case in enumerate(similar_cases[:3], 1):
        similar_cases_text += f"""
{i}. 案例 #{case.get('case_no', 'N/A')} (相似度：{case.get('similarity', 0):.3f})
   现象：{case.get('fault_symptom', 'N/A')[:80]}
   根因：{case.get('root_cause', 'N/A')[:60]}
"""
    
    if not similar_cases:
        similar_cases_text = "无相似案例"
    
    return NEW_CASE_CONFIRMATION_PROMPT_TEMPLATE.format(
        symptom=symptom,
        services=services_text,
        alert_time=alert_time,
        diagnosis_process=diagnosis_process,
        suggestion=suggestion,
        similar_cases_text=similar_cases_text,
    )
