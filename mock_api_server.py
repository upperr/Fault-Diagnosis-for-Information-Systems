#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Mock API 服务 (适配 mock_data2.json 新格式)
从 mock_data2.json 读取数据，提供与 http://27.8.31.7:8000 相同的接口

接口:
  GET  /api/alerts  - 返回随机一条告警
  POST /api/trace   - 根据 serviceName 和 alertTime 查询日志链路

数据格式变化:
  - logs 字段现在是扁平列表，每条日志直接包含：
    {
      "微服务名称": "...",
      "日志等级": "...",
      "日志内容": "...",
      "产生时间": "...",
      "下游微服务名称": "...",
      "traceid": "..."
    }

启动:
  python mock_api_server.py
  
访问:
  http://localhost:8080
"""

import json
import random
from pathlib import Path
from flask import Flask, request, Response
from datetime import datetime, timedelta

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
    """从 mock_data2.json 加载数据"""
    if not MOCK_DATA_FILE.exists():
        print(f"⚠️  警告：{MOCK_DATA_FILE} 不存在，将使用空数据")
        return [], []
    
    try:
        with open(MOCK_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        alerts = data.get("alerts", [])
        # 新格式：logs 直接是扁平列表，无需展平
        logs = data.get("logs", [])
        
        print(f"✓ 加载告警数据：{len(alerts)} 条")
        print(f"✓ 加载日志数据：{len(logs)} 条")
        return alerts, logs
        
    except Exception as e:
        print(f"✗ 加载数据失败：{e}")
        return [], []


# 全局数据存储
ALERTS_STORE, LOGS_STORE = load_mock_data()

# 构建日志索引：按 (微服务名称) 组织，便于快速查找
# 新格式下每条日志直接包含 "微服务名称" 字段
LOGS_INDEX_BY_SERVICE = {}
for log in LOGS_STORE:
    service = log.get("微服务名称", "")
    if service:
        if service not in LOGS_INDEX_BY_SERVICE:
            LOGS_INDEX_BY_SERVICE[service] = []
        LOGS_INDEX_BY_SERVICE[service].append(log)


# ============================================================
# API 接口
# ============================================================

@app.route("/")
def index():
    """服务首页"""
    return json_response({
        "service": "Mock API Server v2",
        "version": "2.0.0",
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
    
    功能：检索指定服务在告警时间前后 5 分钟内的所有日志
    """
    try:
        # 从 URL query params 获取参数
        service_name = request.args.get("serviceName")
        alert_time = request.args.get("alertTime")
        
        # 参数验证
        if not service_name:
            return json_response({
                "code": 400,
                "message": "缺少 serviceName 参数",
                "data": None
            })
        
        if not alert_time:
            return json_response({
                "code": 400,
                "message": "缺少 alertTime 参数",
                "data": None
            })
        
        # 标准化时间格式（处理 Z 后缀）
        alert_time_normalized = alert_time.rstrip("Z")
        
        # 解析告警时间
        try:
            alert_dt = datetime.fromisoformat(alert_time_normalized)
        except Exception as e:
            return json_response({
                "code": 400,
                "message": f"时间格式错误：{e}",
                "data": None
            })
        
        # 计算时间范围：告警时间前后 5 分钟
        start_dt = alert_dt - timedelta(minutes=5)
        end_dt = alert_dt + timedelta(minutes=5)
        
        start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        
        print(f"查询服务 [{service_name}] 时间范围：{start_str} ~ {end_str}")
        
        # 从索引中获取该服务的所有日志
        service_logs = LOGS_INDEX_BY_SERVICE.get(service_name, [])
        
        # 筛选时间范围内的日志
        matched_logs = []
        for log in service_logs:
            log_time_raw = log.get("产生时间", "")
            log_time_normalized = log_time_raw.rstrip("Z")
            
            # 比较时间（字符串比较即可，因为格式一致）
            if start_str <= log_time_normalized <= end_str:
                matched_logs.append(log)
        
        # 如果未找到任何日志，返回错误
        if not matched_logs:
            return json_response({
                "code": 400,
                "message": f"未找到服务 {service_name} 在告警时间前后 5 分钟内的日志",
                "data": None
            })
        
        return json_response({
            "code": 200,
            "message": "success",
            "data": matched_logs
        })
        
    except Exception as e:
        import traceback
        print(f"[ERROR] /api/trace 内部错误：{e}")
        print(f"[ERROR] 堆栈跟踪:\n{traceback.format_exc()}")
        return json_response({
            "code": 500,
            "message": f"服务器内部错误：{str(e)}",
            "data": None
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
    print("Mock API Server v2 启动中...")
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
