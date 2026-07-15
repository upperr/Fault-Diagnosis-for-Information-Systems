#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量告警诊断脚本
从 dataset/mock_data.json 读取所有告警，逐一调用主程序进行诊断，输出综合诊断报告
"""
import json
import time
from pathlib import Path
from datetime import datetime
import httpx

# 配置
MAIN_API_BASE_URL = "http://localhost:8000"
DIAGNOSE_ENDPOINT = f"{MAIN_API_BASE_URL}/api/diagnose"
MOCK_DATA_FILE = Path(__file__).parent / "../dataset/mock_data.json"
OUTPUT_DIR = Path(__file__).parent / "diagnosis_results"
REPORT_FILE = OUTPUT_DIR / "batch_diagnosis_report.md"
DETAILS_FILE = OUTPUT_DIR / "batch_diagnosis_details.json"


def load_alerts():
    """从 mock_data.json 加载所有告警"""
    if not MOCK_DATA_FILE.exists():
        print(f"✗ 错误：{MOCK_DATA_FILE} 不存在")
        return []
    
    with open(MOCK_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    alerts = data.get("alerts", [])
    print(f"✓ 加载告警数据：{len(alerts)} 条")
    return alerts


def diagnose_alert(alert, client):
    """
    调用主程序诊断单个告警
    返回：(告警信息，诊断结果，成功标记)
    """
    service_name = alert.get("微服务名称", "")
    alert_message = alert.get("告警信息", "")
    alert_time = alert.get("告警时间", "")
    
    # 跳过微服务名称为空的告警
    if not service_name:
        return {
            "alert": alert,
            "result": {"status": "skipped", "message": "微服务名称为空，跳过诊断"},
            "success": False
        }
    
    try:
        response = client.post(
            DIAGNOSE_ENDPOINT,
            json={
                "微服务名称": service_name,
                "告警信息": alert_message,
                "告警时间": alert_time
            },
            timeout=60.0
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                "alert": alert,
                "result": result,
                "success": result.get("status") == "success"
            }
        else:
            return {
                "alert": alert,
                "result": {"status": "error", "message": f"HTTP {response.status_code}"},
                "success": False
            }
            
    except httpx.ConnectError as e:
        return {
            "alert": alert,
            "result": {"status": "error", "message": f"无法连接到主程序：{str(e)}"},
            "success": False
        }
    except Exception as e:
        return {
            "alert": alert,
            "result": {"status": "error", "message": str(e)},
            "success": False
        }


def generate_markdown_report(results, output_path):
    """生成 Markdown 格式的综合诊断报告"""
    total = len(results)
    success_count = sum(1 for r in results if r["success"])
    skipped_count = sum(1 for r in results if r["result"].get("status") == "skipped")
    error_count = sum(1 for r in results if r["result"].get("status") == "error")
    failed_count = total - success_count - skipped_count - error_count
    
    lines = []
    lines.append("# 批量告警诊断报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 统计摘要")
    lines.append("")
    lines.append(f"| 指标 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总告警数 | {total} |")
    lines.append(f"| 诊断成功 | {success_count} |")
    lines.append(f"| 已跳过 (微服务名称为空) | {skipped_count} |")
    lines.append(f"| 诊断失败 | {failed_count} |")
    lines.append(f"| 连接/系统错误 | {error_count} |")
    lines.append("")
    
    # 按服务分组统计
    service_stats = {}
    for r in results:
        service = r["alert"].get("微服务名称", "未知")
        if service not in service_stats:
            service_stats[service] = {"total": 0, "success": 0, "failed": 0}
        service_stats[service]["total"] += 1
        if r["success"]:
            service_stats[service]["success"] += 1
        elif r["result"].get("status") != "skipped":
            service_stats[service]["failed"] += 1
    
    lines.append("## 按服务统计")
    lines.append("")
    lines.append("| 服务名称 | 总数 | 成功 | 失败 |")
    lines.append("|----------|------|------|------|")
    for service in sorted(service_stats.keys()):
        stats = service_stats[service]
        lines.append(f"| {service} | {stats['total']} | {stats['success']} | {stats['failed']} |")
    lines.append("")
    
    # 详细诊断结果
    lines.append("## 详细诊断结果")
    lines.append("")
    
    for i, r in enumerate(results, 1):
        alert = r["alert"]
        result = r["result"]
        service = alert.get("微服务名称", "未知")
        alert_msg = alert.get("告警信息", "未知")
        alert_time = alert.get("告警时间", "未知")
        
        lines.append(f"### {i}. [{service}] {alert_msg}")
        lines.append("")
        lines.append(f"- **告警时间**: {alert_time}")
        lines.append(f"- **诊断状态**: {result.get('status', 'unknown')}")
        
        if r["success"] and result.get("report"):
            report = result["report"]
            lines.append(f"- **根因**: {report.get('root_cause', 'N/A')}")
            lines.append(f"- **置信度**: {result.get('confidence', 'N/A')}")
            lines.append(f"- **调用链**: {' → '.join(report.get('call_chain', []))}")
            
            # 处理建议
            suggestions = report.get("suggestions", [])
            if suggestions:
                lines.append("- **处理建议**:")
                for sug in suggestions:
                    lines.append(f"  - {sug}")
            
            # 是否为新案例
            if result.get("is_new_case"):
                lines.append(f"- **注意**: {result.get('new_case_message', '发现新案例')}")
        else:
            lines.append(f"- **错误信息**: {result.get('message', 'N/A')}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 错误汇总
    errors = [r for r in results if r["result"].get("status") == "error"]
    if errors:
        lines.append("## 错误汇总")
        lines.append("")
        for r in errors:
            alert = r["alert"]
            lines.append(f"- [{alert.get('微服务名称', '未知')}] {alert.get('告警信息', '未知')}: {r['result'].get('message', 'N/A')}")
        lines.append("")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return total, success_count


def main():
    """主函数"""
    print("=" * 60)
    print("批量告警诊断脚本")
    print("=" * 60)
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 加载告警
    alerts = load_alerts()
    if not alerts:
        print("✗ 没有告警数据，退出")
        return
    
    print(f"\n开始诊断 {len(alerts)} 条告警...")
    print(f"主程序地址：{DIAGNOSE_ENDPOINT}")
    print("-" * 60)
    
    results = []
    start_time = time.time()
    
    with httpx.Client() as client:
        for i, alert in enumerate(alerts, 1):
            service = alert.get("微服务名称", "未知")
            alert_msg = alert.get("告警信息", "未知")
            
            print(f"[{i}/{len(alerts)}] 诊断：[{service}] {alert_msg}...", end=" ")
            
            result = diagnose_alert(alert, client)
            results.append(result)
            
            if result["success"]:
                print("✓ 成功")
            elif result["result"].get("status") == "skipped":
                print("⊘ 跳过")
            else:
                print(f"✗ 失败：{result['result'].get('message', '未知错误')}")
    
    elapsed = time.time() - start_time
    print("-" * 60)
    print(f"诊断完成，耗时：{elapsed:.2f} 秒")
    
    # 生成报告
    print("\n生成诊断报告...")
    total, success_count = generate_markdown_report(results, REPORT_FILE)
    
    # 保存详细 JSON 结果
    with open(DETAILS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "success": success_count,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 报告已保存:")
    print(f"  - Markdown 报告：{REPORT_FILE}")
    print(f"  - JSON 详情：{DETAILS_FILE}")
    print("\n" + "=" * 60)
    
    # 打印摘要
    skipped = sum(1 for r in results if r["result"].get("status") == "skipped")
    errors = sum(1 for r in results if r["result"].get("status") == "error")
    failed = total - success_count - skipped - errors
    
    print(f"诊断摘要:")
    print(f"  总计：{total} 条")
    print(f"  成功：{success_count} 条")
    print(f"  跳过：{skipped} 条 (微服务名称为空)")
    print(f"  失败：{failed} 条")
    print(f"  错误：{errors} 条 (连接/系统错误)")
    print("=" * 60)


if __name__ == "__main__":
    main()
