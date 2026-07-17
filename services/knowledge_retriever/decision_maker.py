"""LLM 最终决策模块

基于 Reranker 精排结果，使用 LLM 进行最终相关性判断和答案生成
"""
import json
import logging
from typing import Optional

from services.config import LLM_BASE_URL, LLM_API_KEY, RERANK_THRESHOLD, LLM_DECISION_TOP_K
from services.prompt import (
    RETRIEVAL_DECISION_SYSTEM_PROMPT,
    build_retrieval_decision_prompt,
)

logger = logging.getLogger(__name__)


class DecisionMaker:
    """LLM 最终决策模块"""
    
    def __init__(self):
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    def _get_client(self):
        """懒加载 OpenAI 兼容客户端"""
        if self.client is None:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=LLM_API_KEY,
                    base_url=LLM_BASE_URL,
                )
                self.logger.info("LLM 决策器客户端已初始化")
            except Exception as e:
                self.logger.warning(f"LLM 决策器客户端初始化失败：{e}")
        return self.client
    
    def decide(self, query: str, cases: list[dict]) -> dict:
        """基于召回案例进行最终决策并生成回复
        
        Args:
            query: 用户查询
            cases: Reranker 精排后的案例列表
            
        Returns:
            决策结果字典
        """
        self.logger.info(f"LLM 最终决策：基于 {len(cases)} 个精排案例生成答案")
        
        if not cases:
            return self._empty_decision()
        
        client = self._get_client()
        if not client:
            self.logger.warning("LLM 不可用，使用规则决策降级")
            return self._rule_based_decision(query, cases)
        
        # 构建提示词
        system_prompt = RETRIEVAL_DECISION_SYSTEM_PROMPT.format(max_cases=LLM_DECISION_TOP_K)
        user_prompt = build_retrieval_decision_prompt(query, cases)
        
        try:
            response = client.chat.completions.create(
                model="qwen-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if content is None:
                self.logger.error("LLM 返回空内容")
                return self._rule_based_decision(query, cases)
            content = content.strip()
            self.logger.info(f"LLM 决策响应：{content[:300]}...")
            
            result = json.loads(content)
            # 处理新的 selected_cases 字段（0-3 个选中的案例）
            selected_cases = result.get("selected_cases", [])
            best_match = selected_cases[0] if selected_cases else None
            
            return {
                "has_relevant_knowledge": result.get("has_relevant_knowledge", False),
                "selected_cases": selected_cases,  # 新增：LLM 选中的 0-3 个案例
                "best_match_case_no": best_match.get("case_no") if best_match else result.get("best_match_case_no"),
                "relevance_score": result.get("relevance_score", 0.0),
                "root_cause": result.get("root_cause", "无法判断"),
                "suggestion": result.get("suggestion", "建议联系运维团队进一步排查"),
                "reasoning": result.get("reasoning", ""),
            }
        except json.JSONDecodeError as e:
            self.logger.error(f"LLM 返回非 JSON 格式：{e}")
            return self._rule_based_decision(query, cases)
        except Exception as e:
            self.logger.error(f"LLM 调用失败：{e}")
            return self._rule_based_decision(query, cases)
    
    def _rule_based_decision(self, query: str, cases: list[dict]) -> dict:
        """LLM 不可用时的规则决策降级"""
        if not cases:
            return self._empty_decision()
        
        # 取 rerank 分数最高的案例
        best_case = max(cases, key=lambda x: x.get('rerank_score', x.get('similarity', 0)))
        score = best_case.get('rerank_score', best_case.get('similarity', 0))
        
        # 根据分数决定选中的案例（模拟 LLM 的 0-3 个选择逻辑）
        selected_cases = []
        if score >= 0.7:
            # 高度相关，选择前 LLM_DECISION_TOP_K 个（或全部如果不足）
            selected_cases = [{"case_no": c.get('case_no'), "relevance_score": c.get('rerank_score', c.get('similarity', 0))} 
                             for c in cases[:LLM_DECISION_TOP_K]]
        elif score >= 0.5:
            # 相关性一般，选择前 1-2 个
            selected_cases = [{"case_no": c.get('case_no'), "relevance_score": c.get('rerank_score', c.get('similarity', 0))} 
                             for c in cases[:min(2, LLM_DECISION_TOP_K)]]
        # else: 不相关，selected_cases 保持空列表
        
        return {
            "has_relevant_knowledge": score >= RERANK_THRESHOLD,
            "selected_cases": selected_cases,  # 新增字段
            "best_match_case_no": best_case.get('case_no'),
            "relevance_score": score,
            "root_cause": best_case.get('root_cause', '无法判断'),
            "suggestion": best_case.get('suggestion', '建议联系运维团队排查'),
            "reasoning": f"基于规则选择最佳匹配案例（分数={score:.3f}，选中{len(selected_cases)}个案例）"
        }
    
    def _empty_decision(self) -> dict:
        """空结果决策"""
        return {
            "has_relevant_knowledge": False,
            "best_match_case_no": None,
            "relevance_score": 0.0,
            "root_cause": "知识库中无相关故障案例",
            "suggestion": "建议收集更多故障信息或联系相关技术专家",
            "reasoning": "未检索到相关案例"
        }


# 全局实例
_decision_maker: Optional[DecisionMaker] = None


def get_decision_maker() -> DecisionMaker:
    """获取全局决策器实例"""
    global _decision_maker
    if _decision_maker is None:
        _decision_maker = DecisionMaker()
    return _decision_maker
