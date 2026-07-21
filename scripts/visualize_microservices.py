#!/usr/bin/env python3
"""
微服务依赖关系可视化
基于 mock_data.json 中的日志数据，提取"下游微服务名称"字段构建调用关系图
节点颜色：ERROR 告警→红色，INFO 告警→橙黄色
边颜色：调用日志中有 ERROR→红色，其他→黄色
"""

import json
from collections import defaultdict
import networkx as nx
from pyvis.network import Network

# 读取数据
with open('../dataset/mock_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 提取微服务调用关系，同时记录日志级别
# edges: (source, target) -> {'count': int, 'has_error': bool}
edges = defaultdict(lambda: {'count': 0, 'has_error': False})
nodes = set()
error_services = set()
info_services = set()

for log_entry in data['logs']:
    for key, logs in log_entry.items():
        if logs is None:
            continue
        for log in logs:
            source = log.get('微服务名称', '').strip()
            target = log.get('下游微服务名称', '').strip()
            level = log.get('日志等级', '').strip()
            
            # 记录节点的日志级别
            if source:
                if level == 'error':
                    error_services.add(source)
                elif level == 'info':
                    info_services.add(source)
            
            # 跳过空值
            if not source or not target:
                continue
            
            nodes.add(source)
            nodes.add(target)
            edges[(source, target)]['count'] += 1
            
            # 如果这条调用关系中有 ERROR 日志，标记为有错误
            if level == 'error':
                edges[(source, target)]['has_error'] = True

# 创建有向图
G = nx.DiGraph()

for node in nodes:
    G.add_node(node)

for (source, target), data in edges.items():
    G.add_edge(source, target, weight=data['count'], has_error=data['has_error'])

# 使用 pyvis 创建交互式有向图可视化
net = Network(height='800px', width='100%', bgcolor='#1a1a2e', font_color='white', directed=True)
net.barnes_hut(gravity=-50000, central_gravity=0.5, spring_length=200)

# 定义节点颜色（按告警级别）
def get_node_color(service):
    if service in error_services:
        return '#ff4444'  # 红色 - 有 ERROR 告警
    else:
        return '#4a90d9'  # 蓝色 - 仅 INFO 告警

# 添加节点
for node in G.nodes():
    color = get_node_color(node)
    net.add_node(node, label=node, title=f'{node} ({"ERROR" if node in error_services else "INFO"})', color=color, size=30)

# 添加带箭头的边，根据日志级别设置颜色
for (source, target), edge_data in edges.items():
    count = edge_data['count']
    has_error = edge_data['has_error']
    
    # 所有边都使用浅蓝色
    edge_color = '#87ceeb'  # 浅蓝色
    
    # 根据调用次数设置边的粗细
    if count >= 10:
        edge_width = 4
    elif count >= 4:
        edge_width = 2
    else:
        edge_width = 1
    
    net.add_edge(
        source, target, 
        value=count, 
        title=f'{source} → {target}\n调用次数：{count}\n日志级别：{"ERROR" if has_error else "INFO"}',
        arrows='to',
        color=edge_color,
        width=edge_width
    )

# 设置物理引擎和有向图选项
net.set_options('''
{
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -50000,
      "centralGravity": 0.5,
      "springLength": 200,
      "springConstant": 0.04,
      "damping": 0.09
    },
    "stabilization": {
      "iterations": 200
    }
  },
  "edges": {
    "arrows": {
      "to": {
        "enabled": true,
        "scaleFactor": 1,
        "type": "arrow"
      }
    },
    "smooth": {
      "type": "dynamic",
      "roundness": 0.2
    }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 200,
    "zoomView": true
  }
}
''')

# 保存为 HTML
output_path = 'microservices_graph.html'
net.save_graph(output_path)

print(f'✓ 微服务依赖图已生成：{output_path}')
print(f'\n统计信息:')
print(f'  - 微服务节点数：{len(nodes)}')
print(f'  - 调用关系边数：{len(edges)}')
print(f'\n节点颜色说明:')
print(f'  🔴 红色节点 (ERROR 告警): {sorted(error_services)}')
print(f'  🔵 蓝色节点 (INFO 告警): {sorted(info_services - error_services)}')
print(f'\n调用关系详情:')
for (source, target), data in sorted(edges.items(), key=lambda x: -x[1]['count']):
    level = "ERROR" if data['has_error'] else "INFO"
    print(f'  {source} → {target}: {data["count"]} 次 [{level}]')
