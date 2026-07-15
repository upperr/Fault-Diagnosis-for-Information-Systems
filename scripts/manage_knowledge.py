#!/usr/bin/env python3
"""
知识库管理 CLI 工具

功能：
- 查看知识库统计
- 手动添加案例
- 导出/导入知识库
- 清理低质量案例
"""
import sys
import json
import argparse
from pathlib import Path

# 将 code 目录加入 path
CODE_DIR = Path(__file__).parent
sys.path.insert(0, str(CODE_DIR))

from services.knowledge_retriever import get_retriever
from services.knowledge_manager import get_manager


def cmd_stats(args):
    """查看知识库统计"""
    retriever = get_retriever()
    cases = retriever.get_all_cases()
    
    print("=" * 60)
    print("  知识库统计")
    print("=" * 60)
    print(f"  总案例数：{len(cases)}")
    
    if cases:
        print(f"  案例编号范围：{min(c['case_no'] for c in cases)} - {max(c['case_no'] for c in cases)}")
        print("\n  最近添加的案例:")
        for c in cases[-5:]:
            print(f"    [{c['case_no']}] {c['fault_symptom'][:50]}...")
    
    print("=" * 60)


def cmd_add(args):
    """手动添加案例"""
    manager = get_manager()
    
    print("请输入案例信息（直接回车使用默认值）：")
    
    case_no = input(f"案例编号 [{manager._get_next_case_no()}]: ").strip()
    if not case_no:
        case_no = manager._get_next_case_no()
    else:
        case_no = int(case_no)
    
    fault_symptom = input("故障现象（fault_summary）:").strip()
    diagnosis_process = input("排查流程：").strip()
    root_cause = input("根因分析：").strip()
    suggestion = input("处置建议：").strip()
    
    success = manager.add_new_case(
        case_no=case_no,
        fault_symptom=fault_symptom,
        diagnosis_process=diagnosis_process,
        root_cause=root_cause,
        suggestion=suggestion,
    )
    
    if success:
        print(f"✅ 成功添加案例 #{case_no}")
    else:
        print("❌ 添加失败")


def cmd_export(args):
    """导出知识库"""
    retriever = get_retriever()
    cases = retriever.get_all_cases()
    
    output_file = args.output or "knowledge_export.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已导出 {len(cases)} 条案例到 {output_file}")


def cmd_import(args):
    """导入知识库"""
    import_file = args.input
    
    if not Path(import_file).exists():
        print(f"❌ 文件不存在：{import_file}")
        return
    
    with open(import_file, "r", encoding="utf-8") as f:
        cases = json.load(f)
    
    manager = get_manager()
    conn = manager.retriever.connect()
    cur = conn.cursor()
    
    count = 0
    for case in cases:
        try:
            symptom_emb = manager.retriever.get_embedding(case["fault_symptom"])
            process_emb = manager.retriever.get_embedding(case["diagnosis_process"])
            root_emb = manager.retriever.get_embedding(f"{case['root_cause']} {case['suggestion']}")
            
            if all([symptom_emb, process_emb, root_emb]):
                emb_str = lambda e: "[" + ",".join(map(str, e)) + "]"
                cur.execute(
                    """
                    INSERT INTO fault_cases 
                    (case_no, fault_symptom, diagnosis_process, root_cause, suggestion,
                     symptom_embedding, diagnosis_process_embedding, root_cause_embedding)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s::vector, %s::vector)
                    ON CONFLICT (case_no) DO NOTHING
                    """,
                    (
                        case["case_no"],
                        case["fault_symptom"],
                        case["diagnosis_process"],
                        case["root_cause"],
                        case["suggestion"],
                        emb_str(symptom_emb),
                        emb_str(process_emb),
                        emb_str(root_emb),
                    ),
                )
                count += 1
        except Exception as e:
            print(f"  跳过案例 {case.get('case_no', '?')}: {e}")
    
    conn.commit()
    print(f"✅ 已导入 {count} 条案例")


def cmd_test_new_case(args):
    """测试新故障判定"""
    manager = get_manager()
    
    query_text = args.text or "数据库连接超时，连接池耗尽"
    
    is_new, similar_cases, max_sim = manager.is_new_case(query_text)
    
    print("=" * 60)
    print("  新故障判定测试")
    print("=" * 60)
    print(f"  查询文本：{query_text[:50]}...")
    print(f"  最高相似度：{max_sim:.3f}")
    print(f"  判定结果：{'新故障' if is_new else '已有相似案例'}")
    
    if similar_cases:
        print(f"\n  最相似的 {len(similar_cases)} 条案例:")
        for c in similar_cases:
            print(f"    [{c['case_no']}] 相似度={c['similarity']:.3f}")
            print(f"      现象：{c['fault_symptom'][:50]}...")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="知识库管理工具")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # stats 命令
    stats_parser = subparsers.add_parser("stats", help="查看知识库统计")
    stats_parser.set_defaults(func=cmd_stats)
    
    # add 命令
    add_parser = subparsers.add_parser("add", help="手动添加案例")
    add_parser.set_defaults(func=cmd_add)
    
    # export 命令
    export_parser = subparsers.add_parser("export", help="导出知识库")
    export_parser.add_argument("-o", "--output", help="输出文件路径")
    export_parser.set_defaults(func=cmd_export)
    
    # import 命令
    import_parser = subparsers.add_parser("import", help="导入知识库")
    import_parser.add_argument("-i", "--input", required=True, help="输入文件路径")
    import_parser.set_defaults(func=cmd_import)
    
    # test-new-case 命令
    test_parser = subparsers.add_parser("test-new-case", help="测试新故障判定")
    test_parser.add_argument("-t", "--text", help="测试文本")
    test_parser.set_defaults(func=cmd_test_new_case)
    
    args = parser.parse_args()
    
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
