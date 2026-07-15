"""
LLM 提示词管理

集中管理所有 LLM 相关的提示词模板。
"""

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
    "root_cause": "根因分析文本",
    "suggestion": "处置建议文本（分条列出，用\\n 分隔）",
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
# 下游服务检测提示词
# ============================================================

DOWNSTREAM_DETECT_SYSTEM_PROMPT = """你是一个运维日志分析助手。请判断以下日志是否包含对下游微服务的调用。

已知微服务列表：{service_list}

输出格式：请严格按照以下 JSON 格式输出：
{{
    "has_downstream": true/false,
    "service_name": "下游服务名称（如果没有则为 null）"
}}
"""


def build_downstream_detect_prompt(
    message: str,
    stack_trace: str | None = None,
    service_list: str = "未知",
) -> str:
    """
    构建下游服务检测的用户提示词。

    Args:
        message: 日志消息
        stack_trace: 异常堆栈（可选）
        service_list: 已知服务名称列表

    Returns:
        提示词文本
    """
    content = f"""日志消息：
{message}
"""
    if stack_trace:
        content += f"\n堆栈跟踪：\n{stack_trace[:500]}"

    content += f"\n\n已知微服务列表：{service_list}\n\n## 分析结果\n"
    return content


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
