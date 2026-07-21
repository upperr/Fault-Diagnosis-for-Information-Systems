"""Reranker 模型客户端 - 使用阿里云 qwen3-rerank 模型"""
import logging
from typing import Optional

from services.config import RERANK_MODEL, RERANK_TOP_K, RERANK_THRESHOLD, RERANK_ENABLED, LLM_API_KEY

logger = logging.getLogger(__name__)


class RerankClient:
    """Reranker 模型客户端"""
    
    def __init__(self):
        self.model = RERANK_MODEL or "qwen3-rerank"
        self.api_key = LLM_API_KEY
        self.enabled = RERANK_ENABLED
        self.logger = logging.getLogger(__name__)
    
    def rerank(self, query: str, cases: list[dict], top_k: int) -> list[dict]:
        """使用 Reranker 模型对案例进行重排序（多字段召回合并策略）
        
        Args:
            query: 查询文本
            cases: 待排序的案例列表
            top_k: 最终返回数量
            
        Returns:
            重排序后的案例列表
        """
        self.logger.info(f"开始 Reranker 精排（多字段），输入 {len(cases)} 个案例，目标 top_k={top_k}")
        
        if not cases:
            self.logger.warning("输入案例列表为空，跳过 Rerank")
            return []
        
        try:
            import dashscope
            from http import HTTPStatus
            
            # 设置 API Key
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
            
            # 多字段检索：对每个字段分别进行 Rerank
            all_rerank_results = {}
            search_fields = ["fault_symptom", "diagnosis_process", "root_cause"]
            
            for field in search_fields:
                # 准备文档列表：使用当前字段的内容
                documents = []
                for case in cases:
                    doc_text = case.get(field, '')
                    if doc_text:
                        documents.append(doc_text[:2000])
                    else:
                        documents.append("")  # 空字段占位
                
                self.logger.debug(f"调用 Reranker API (field={field}): query={query[:50]}..., docs={len(documents)}")
                
                # 同步调用 Reranker API
                resp = dashscope.TextReRank.call(
                    model=self.model,
                    query=query,
                    documents=documents,
                    top_n=len(cases),
                    return_documents=True,
                )
                
                if resp.status_code == HTTPStatus.OK:
                    self.logger.debug(f"Reranker ({field}) 调用成功")
                    field_results = self._parse_rerank_result(resp, cases, len(cases))
                    
                    # 记录该字段的召回结果
                    if field_results:
                        top_scores = [c.get('rerank_score', 0) for c in field_results[:3]]
                        self.logger.info(f"字段 [{field}] Rerank 召回 {len(field_results)} 个案例，最高分：{max(top_scores):.3f}")
                    else:
                        self.logger.info(f"字段 [{field}] Rerank 召回 0 个案例")
                    
                    # 合并结果，保留最高分
                    for case in field_results:
                        case_no = case["case_no"]
                        field_score = case.get('rerank_score', 0)
                        if case_no not in all_rerank_results:
                            all_rerank_results[case_no] = case
                            all_rerank_results[case_no]['best_field'] = field
                        else:
                            # 保留最高分
                            if field_score > all_rerank_results[case_no].get('rerank_score', 0):
                                all_rerank_results[case_no]['rerank_score'] = field_score
                                all_rerank_results[case_no]['best_field'] = field
                else:
                    self.logger.warning(f"Reranker ({field}) 调用失败：{resp.status_code}")
            
            # 按 rerank 分数降序排序
            reranked = list(all_rerank_results.values())
            reranked.sort(key=lambda x: x.get('rerank_score', 0.0), reverse=True)
            
            # 过滤低于阈值的案例
            from services.config import RERANK_THRESHOLD
            filtered = [c for c in reranked if c.get('rerank_score', 0) >= RERANK_THRESHOLD]
            
            # 限制返回数量
            if len(filtered) > top_k:
                filtered = filtered[:top_k]
            
            # 报告精排最终结果
            if filtered:
                top_case = filtered[0]
                self.logger.info(
                    f"Rerank 精排最终结果：保留 {len(filtered)} 个案例 "
                    f"(阈值={RERANK_THRESHOLD}, top_k={top_k}), "
                    f"最高分：{top_case.get('rerank_score', 0):.3f} "
                    f"(字段：{top_case.get('best_field', 'unknown')})"
                )
            else:
                self.logger.warning(
                    f"Rerank 精排最终结果：0 个案例 (阈值={RERANK_THRESHOLD}, top_k={top_k}), "
                    f"所有案例分数均低于阈值"
                )
            
            return filtered
            
        except ImportError:
            self.logger.warning("dashscope 未安装，跳过 Rerank")
            return cases[:top_k]
        except Exception as e:
            self.logger.warning(f"Rerank 失败：{e}，返回原始结果")
            return cases[:top_k]
    
    def _parse_rerank_result(self, resp, original_cases: list[dict], top_k: int) -> list[dict]:
        """解析 Reranker 响应结果
        
        Args:
            resp: Reranker API 响应
            original_cases: 原始案例列表
            top_k: 返回的最大数量
            
        Returns:
            重排序后的案例列表
        """
        try:
            results = resp.output.get('results', [])
            
            if not results:
                self.logger.warning("Reranker 返回空结果")
                return original_cases[:5]
            
            # 根据 index 映射回原始 cases
            reranked = []
            for result in results:
                index = result.get('index', 0)
                if 0 <= index < len(original_cases):
                    case = original_cases[index].copy()
                    case['rerank_score'] = result.get('relevance_score', 0.0)
                    reranked.append(case)
            
            # 只解析结果，不排序和过滤（由 rerank 方法统一处理）
            self.logger.debug(f"Rerank 解析完成：{len(reranked)} 个案例")
            return reranked
            
        except Exception as e:
            self.logger.error(f"解析 Reranker 结果失败：{e}")
            return original_cases[:5]


# 全局实例
_rerank_client: Optional[RerankClient] = None


def get_rerank_client() -> RerankClient:
    """获取全局 Rerank 客户端实例"""
    global _rerank_client
    if _rerank_client is None:
        _rerank_client = RerankClient()
    return _rerank_client
