"""
故障预警图服务 - 基于诊断结果生成微服务预警图数据
"""
import logging
import os
import json
from collections import defaultdict
from typing import Dict, Any, List

logger = logging.getLogger("diagnosis-agent")


class WarningGraphHandler:
    """故障预警图处理器 - 基于诊断结果生成微服务预警图数据"""
    
    def __init__(self, code_dir: str):
        self.code_dir = code_dir
    
    def generate(self, diagnosis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于诊断结果生成微服务预警图数据
        
        Args:
            diagnosis_result: 诊断结果，包含 call_chain 和 logs
        
        Returns:
            预警图数据，包含 nodes, edges, stats 等
        
        Raises:
            HTTPException: 当缺少 call_chain 或文件不存在时
        """
        from fastapi import HTTPException
        
        call_chain = diagnosis_result.get("call_chain", [])
        if not call_chain:
            raise HTTPException(status_code=400, detail="缺少 call_chain 参数")
        
        logger.info(f"处理 call_chain: {' -> '.join(call_chain)}")
        
        # 读取 mock_data.json
        data_path = os.path.join(self.code_dir, "dataset", "mock_data.json")
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="未找到 mock_data.json 文件")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"JSON 解析失败：{str(e)}")
        
        # 1. 构建完整的有向图（邻接表）
        graph = defaultdict(set)  # 正向图：谁调用了谁
        reverse_graph = defaultdict(set)  # 反向图：谁被谁调用
        all_nodes = set()
        error_services = set()  # 出现过 ERROR 日志的服务
        
        for log in data.get('logs', []):
            if log is None or isinstance(log, str):
                continue
            
            source = log.get('微服务名称', '').strip()
            target = log.get('下游微服务名称', '').strip()
            level = log.get('日志等级', '').strip()
            
            if source:
                all_nodes.add(source)
                if level == 'error':
                    error_services.add(source)
            
            if target:
                all_nodes.add(target)
            
            if source and target:
                graph[source].add(target)
                reverse_graph[target].add(source)
        
        logger.info(f"构建完成有向图：{len(all_nodes)} 个节点，{sum(len(v) for v in graph.values())} 条边")
        logger.info(f"ERROR 服务节点：{error_services}")
        
        # 2. 标记链路中的节点（INFO/ERROR）
        chain_nodes = set(call_chain)
        chain_error_nodes = set()
        chain_info_nodes = set(chain_nodes)  # 默认所有链路节点都是 INFO
        
        # 优先使用诊断结果中的日志，回退到 mock_data.json
        diagnosis_logs = diagnosis_result.get('logs', [])
        logs_for_chain_judgment = diagnosis_logs if diagnosis_logs else data.get('logs', [])
        logger.info(f"使用{'诊断结果中的' if diagnosis_logs else 'mock_data.json 中的'}日志来判断链路节点颜色")
        
        # 根据日志更新 ERROR 节点
        for log in logs_for_chain_judgment:
            if log is None or isinstance(log, str):
                continue
            # 支持两种字段名格式
            service = log.get('微服务名称', '').strip() or log.get('_source_service', '').strip()
            level = log.get('日志等级', '').strip() or log.get('level', '').strip()
            if service in chain_nodes:
                if level.lower() == 'error':
                    chain_error_nodes.add(service)
                    chain_info_nodes.discard(service)
        
        logger.info(f"链路中 ERROR 节点：{chain_error_nodes}")
        logger.info(f"链路中 INFO 节点：{chain_info_nodes}")
        
        # 3. 检测潜在故障预警节点
        # 规则：仅对于链路内 ERROR 节点，检查其下游节点是否有 ERROR 日志
        warning_nodes = set()
        for node in chain_error_nodes:
            downstream_nodes = graph.get(node, set())
            for down_node in downstream_nodes:
                if down_node in error_services:
                    warning_nodes.add(down_node)
        
        # 预警节点排除所有链路节点
        warning_nodes -= chain_nodes
        
        logger.info(f"潜在故障预警节点（链路节点的下游 ERROR 服务）: {warning_nodes}")
        
        # 4. 构建边数据
        edges_data = []
        edge_set = set()
        for source, targets in graph.items():
            for target in targets:
                edge_key = (source, target)
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    
                    is_chain_edge = (source in chain_nodes) and (target in chain_nodes)
                    
                    # 计算调用次数
                    count = 1
                    for log in data.get('logs', []):
                        if log is None or isinstance(log, str):
                            continue
                        if log.get('微服务名称') == source and log.get('下游微服务名称') == target:
                            count += 1
                    
                    # 根据调用次数设置边宽度
                    if count >= 20:
                        edge_width = 8
                    elif count >= 10:
                        edge_width = 5
                    elif count >= 4:
                        edge_width = 3
                    else:
                        edge_width = 1
                    
                    # 确定边的颜色
                    if target in chain_error_nodes:
                        edge_color = '#ff4444' if source in chain_nodes else '#666666'
                    elif target in warning_nodes:
                        edge_color = '#ffa500' if source in chain_nodes else '#666666'
                    elif target in chain_info_nodes:
                        edge_color = '#4a90d9' if source in chain_nodes else '#666666'
                    else:
                        edge_color = '#666666'
                    
                    edges_data.append({
                        "source": source,
                        "target": target,
                        "is_chain_edge": is_chain_edge,
                        "color": edge_color,
                        "width": edge_width,
                        "count": count
                    })
        
        # 5. 构建节点数据（颜色优先级：红色 > 橙色 > 蓝色 > 灰色）
        nodes_data = []
        for node in all_nodes:
            if node in chain_error_nodes:
                nodes_data.append({
                    "id": node,
                    "label": node,
                    "type": "chain_error",
                    "color": "#ff4444"
                })
            elif node in warning_nodes:
                nodes_data.append({
                    "id": node,
                    "label": node,
                    "type": "warning",
                    "color": "#ffa500"
                })
            elif node in chain_info_nodes:
                nodes_data.append({
                    "id": node,
                    "label": node,
                    "type": "chain_info",
                    "color": "#4a90d9"
                })
            else:
                nodes_data.append({
                    "id": node,
                    "label": node,
                    "type": "normal",
                    "color": "#666666"
                })
        
        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "stats": {
                "total_nodes": len(all_nodes),
                "total_edges": len(edges_data),
                "chain_nodes": list(chain_nodes),
                "chain_error_nodes": list(chain_error_nodes),
                "chain_info_nodes": list(chain_info_nodes),
                "warning_nodes": list(warning_nodes),
                "error_services": list(error_services)
            },
            "call_chain": call_chain
        }
