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
        """使用 Reranker 模型对案例进行重排序
        
        Args:
            query: 查询文本
            cases: 待排序的案例列表
            top_k: 最终返回数量
            
        Returns:
            重排序后的案例列表
        """
        self.logger.info(f"开始 Reranker 精排，输入 {len(cases)} 个案例，目标 top_k={top_k}")
        
        if not cases:
            return []
        
        try:
            import dashscope
            from http import HTTPStatus
            
            # 设置 API Key
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
            
            # 准备文档列表：组合故障现象和根因作为检索文本
            documents = []
            for case in cases:
                doc_text = f"故障现象：{case.get('fault_symptom', '')}\n根因：{case.get('root_cause', '')}"
                documents.append(doc_text[:2000])
            
            self.logger.debug(f"调用 Reranker API: query={query[:50]}..., docs={len(documents)}")
            
            # 同步调用 Reranker API
            resp = dashscope.TextReRank.call(
                model=self.model,
                query=query,
                documents=documents,
                top_n=top_k,
                return_documents=True,
            )
            
            if resp.status_code == HTTPStatus.OK:
                self.logger.info("Reranker 调用成功")
                return self._parse_rerank_result(resp, cases, top_k)
            else:
                self.logger.warning(f"Reranker 调用失败：{resp.status_code}")
                return cases[:top_k]
                
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
            
            # 按 rerank 分数降序排序
            reranked.sort(key=lambda x: x.get('rerank_score', 0.0), reverse=True)
            
            # 过滤低于阈值的案例
            filtered = [c for c in reranked if c.get('rerank_score', 0) >= RERANK_THRESHOLD]
            
            self.logger.info(f"Rerank 精排后保留 {len(filtered)} 个案例（阈值={RERANK_THRESHOLD}）")
            return filtered
            
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
