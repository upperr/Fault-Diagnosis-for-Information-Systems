"""
知识库 API 处理器 - 为 FastAPI 路由提供接口封装
"""
import logging
import json
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("diagnosis-agent")


class KnowledgeAPIHandler:
    """知识库 API 处理器 - 封装知识库管理操作供 API 路由调用"""
    
    def __init__(self):
        from services.api.knowledge_manager import get_manager
        from services.knowledge_retriever import get_retriever
        self.manager = get_manager()
        self.retriever = get_retriever()
    
    def confirm_new_case(self, case_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        确认添加新故障到知识库
        
        Args:
            case_data: 案例数据
        
        Returns:
            (success, message) 元组
        """
        logger.info(f"收到确认添加新故障请求：{case_data.get('fault_symptom', '')[:50]}...")
        return self.manager.confirm_and_add_case(case_data)
    
    def get_knowledge_list(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        分页列出历史故障知识库案例
        
        Args:
            page: 页码
            page_size: 每页数量
        
        Returns:
            分页结果字典
        """
        all_cases = self.retriever.get_all_cases()
        
        total = len(all_cases)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        
        start = (page - 1) * page_size
        end = start + page_size
        cases = all_cases[start:end]
        
        return {
            "total": total,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "cases": cases
        }
    
    def get_knowledge_stats(self) -> Dict[str, int]:
        """
        获取知识库统计信息
        
        Returns:
            统计信息字典
        """
        all_cases = self.retriever.get_all_cases()
        return {"totalCases": len(all_cases)}
    
    def preview_import(self, file_content: bytes) -> Dict[str, Any]:
        """
        上传 JSON 文件并预览导入结果（排重检测）
        
        Args:
            file_content: 文件内容（bytes）
        
        Returns:
            预览结果字典
        
        Raises:
            HTTPException: 当 JSON 格式无效时
        """
        from fastapi import HTTPException
        
        logger.info(f"收到导入文件预览请求")
        
        try:
            data = json.loads(file_content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败：{str(e)}")
        
        # 支持数组或对象两种格式
        if isinstance(data, dict):
            cases = [data]
        elif isinstance(data, list):
            cases = data
        else:
            raise HTTPException(status_code=400, detail="无效的 JSON 格式，应为案例对象或数组")
        
        new_cases, duplicate_cases, skip_cases = self.manager.check_import_duplicates(cases)
        
        return {
            "total": len(cases),
            "new_cases": new_cases,
            "duplicate_cases": duplicate_cases,
            "skip_cases": skip_cases,
            "new_cases_count": len(new_cases),
            "duplicate_cases_count": len(duplicate_cases),
            "skip_cases_count": len(skip_cases),
            "has_duplicates": len(duplicate_cases) > 0,
        }
    
    def confirm_import(self, cases: List[Dict[str, Any]], overwrite_duplicates: bool = False) -> Dict[str, Any]:
        """
        确认导入案例到知识库
        
        Args:
            cases: 案例列表
            overwrite_duplicates: 是否覆盖重复案例
        
        Returns:
            导入结果字典
        
        Raises:
            HTTPException: 当没有可导入的案例时
        """
        from fastapi import HTTPException
        
        logger.info(f"收到确认导入请求：{len(cases)} 个案例，overwrite={overwrite_duplicates}")
        
        if not cases:
            raise HTTPException(status_code=400, detail="没有可导入的案例")
        
        result = self.manager.import_knowledge_batch(cases, overwrite_duplicates)
        
        return {
            "status": "success",
            "message": f"导入完成：成功 {result['success']}/{result['total']}, 跳过 {result['skipped']}",
            "result": result,
        }
    
    def clear_knowledge(self) -> Dict[str, Any]:
        """
        清空知识库（删除所有案例）
        
        Returns:
            操作结果字典
        """
        logger.info("收到清空知识库请求")
        result = self.manager.clear_knowledge_base()
        
        return {
            "status": "success",
            "message": f"知识库已清空，共删除 {result['deleted_count']} 个案例",
        }
    
    def delete_case(self, case_id: int) -> Dict[str, Any]:
        """
        删除知识库中的单条案例
        
        Args:
            case_id: 案例 ID
        
        Returns:
            操作结果字典
        
        Raises:
            HTTPException: 当案例不存在时
        """
        from fastapi import HTTPException
        
        logger.info(f"收到删除知识请求：case_id={case_id}")
        
        success = self.retriever.delete_case(case_id)
        
        if success:
            return {
                "status": "success",
                "message": f"案例 #{case_id} 已删除",
            }
        else:
            raise HTTPException(status_code=404, detail=f"案例 #{case_id} 不存在")


# 别名以便从 api 层统一导入
KnowledgeHandler = KnowledgeAPIHandler
