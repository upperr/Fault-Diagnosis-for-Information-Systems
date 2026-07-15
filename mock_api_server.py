#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Mock API 服务
从 mock_data.json 读取数据，提供与 http://27.8.31.7:8002 相同的接口

接口:
  GET  /api/alerts  - 返回随机一条告警
  POST /api/trace   - 根据 serviceName 和 alertTime 查询日志链路

启动:
  python mock_api_server.py
  
访问:
  http://localhost:8080
"""

import json
import random
from pathlib import Path
from flask import Flask, request, Response
from urllib.parse import unquote

app = Flask(__name__)


def json_response(data, status=200):
    """返回中文不转义的 JSON 响应"""
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype='application/json; charset=utf-8'
    )

# ============================================================
# 数据加载
# ============================================================

MOCK_DATA_FILE = Path(__file__).parent / "dataset/mock_data.json"


def load_mock_data():
    """从 mock_data.json 加载数据"""
    if not MOCK_DATA_FILE.exists():
        print(f"⚠️  警告：{MOCK_DATA_FILE} 不存在，将使用空数据")
        return [], []
    
    try:
        with open(MOCK_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        alerts = data.get("alerts", [])
        logs_raw = data.get("logs", [])
        
        # logs 是嵌套结构：[{ "服务名 时间": [日志列表] }, ...]
        # 需要展平成单一的日志列表
        logs = []
        for item in logs_raw:
            if isinstance(item, dict):
                for key, log_list in item.items():
                    if isinstance(log_list, list):
                        logs.extend(log_list)
        
        print(f"✓ 加载告警数据：{len(alerts)} 条")
        print(f"✓ 加载日志数据：{len(logs)} 条")
        return alerts, logs
        
    except Exception as e:
        print(f"✗ 加载数据失败：{e}")
        return [], []


# 全局数据存储
ALERTS_STORE, LOGS_STORE = load_mock_data()

# 构建日志索引：按 (微服务名称，产生时间) 快速查找
LOGS_INDEX = {}
for log in LOGS_STORE:
    service = log.get("微服务名称", "")
    time = log.get("产生时间", "")
    if service and time:
        key = f"{service}|{time}"
        if key not in LOGS_INDEX:
            LOGS_INDEX[key] = []
        LOGS_INDEX[key].append(log)


# ============================================================
# API 接口
# ============================================================

@app.route("/")
def index():
    """服务首页"""
    return json_response({
        "service": "Mock API Server",
        "version": "1.0.0",
        "data_source": str(MOCK_DATA_FILE),
        "endpoints": {
            "GET /api/alerts": "获取随机一条告警信息",
            "GET /api/alerts/all": "获取所有告警信息",
            "POST /api/trace": "查询日志链路 (URL params: serviceName, alertTime)",
            "GET /api/services": "获取所有服务列表",
            "GET /api/stats": "获取数据统计"
        },
        "data_stats": {
            "total_alerts": len(ALERTS_STORE),
            "total_logs": len(LOGS_STORE)
        }
    })


@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    """
    获取随机一条告警信息
    每次调用返回随机一条，需循环调用获取全部
    """
    if not ALERTS_STORE:
        return json_response({
            "code": 500,
            "message": "No alerts available",
            "data": None
        })
    
    # 随机返回一条
    alert = random.choice(ALERTS_STORE)
    
    return json_response({
        "code": 200,
        "message": "success",
        "data": [alert]
    })


@app.route("/api/trace", methods=["POST"])
def query_trace():
    """
    根据微服务名称和告警时间查询日志链路
    请求方式：POST + URL params（httpx 会自动编码中文）
    """
    # 从 URL query params 获取参数
    service_name = request.args.get("serviceName")
    alert_time = request.args.get("alertTime")
    
    # 标准化时间格式（处理 Z 后缀）
    alert_time_normalized = alert_time.rstrip("Z")
    
    # 策略 1: 精确匹配 (serviceName + alertTime)
    exact_key = f"{service_name}|{alert_time}"
    normalized_key = f"{service_name}|{alert_time_normalized}"
    
    matched_logs = LOGS_INDEX.get(exact_key, [])
    if not matched_logs:
        matched_logs = LOGS_INDEX.get(normalized_key, [])
    
    # 策略 2: 分钟级模糊匹配（忽略秒级差异）
    # 例如：告警 10:05:08Z → 匹配日志 10:05:00Z
    if not matched_logs:
        # 提取告警时间的分钟部分（YYYY-MM-DDTHH:MM）
        alert_minute = alert_time_normalized[:16]  # "2026-06-01T10:05"
        
        # 查找同服务同分钟的所有日志
        for key, logs in LOGS_INDEX.items():
            if key.startswith(f"{service_name}|"):
                log_time = key.split("|")[1]
                log_minute = log_time[:16]  # 提取分钟部分
                if log_minute == alert_minute:
                    matched_logs = logs
                    break
    
    # 如果未找到任何日志，返回错误
    if not matched_logs:
        return json_response({
            "code": 400,
            "message": "serviceName is required",
            "data": None
        })
    
    return json_response({
        "code": 200,
        "message": "success",
        "data": matched_logs
    })


@app.route("/api/services", methods=["GET"])
def get_services():
    """获取所有服务列表"""
    services = set()
    for alert in ALERTS_STORE:
        if alert.get("微服务名称"):
            services.add(alert["微服务名称"])
    for log in LOGS_STORE:
        if log.get("微服务名称"):
            services.add(log["微服务名称"])
    
    return json_response({
        "code": 200,
        "message": "success",
        "data": {
            "services": sorted(list(services))
        }
    })


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """获取数据统计信息"""
    # 统计每个服务的告警数
    service_alert_count = {}
    for alert in ALERTS_STORE:
        service = alert.get("微服务名称", "")
        if service:
            service_alert_count[service] = service_alert_count.get(service, 0) + 1
    
    return json_response({
        "code": 200,
        "message": "success",
        "data": {
            "total_alerts": len(ALERTS_STORE),
            "total_logs": len(LOGS_STORE),
            "services": len(service_alert_count),
            "alerts_by_service": service_alert_count
        }
    })


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Mock API Server 启动中...")
    print("=" * 60)
    print(f"数据文件：{MOCK_DATA_FILE}")
    print(f"告警数据：{len(ALERTS_STORE)} 条")
    print(f"日志数据：{len(LOGS_STORE)} 条")
    print()
    print("API 接口:")
    print("  GET  http://localhost:8080/api/alerts  - 获取随机告警")
    print("  POST http://localhost:8080/api/trace?serviceName=xxx&alertTime=xxx - 查询日志 (URL params)")
    print("  GET  http://localhost:8080/api/services - 服务列表")
    print("  GET  http://localhost:8080/api/stats    - 统计信息")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=8080, debug=False)
