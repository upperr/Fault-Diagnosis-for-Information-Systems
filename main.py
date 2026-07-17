"""
告警驱动型故障诊断智能体
FastAPI 主入口
"""
import logging
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

# 加载 .env 文件 (优先从 config/.env 加载)
from dotenv import load_dotenv
env_path = Path(__file__).parent / "config" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载环境变量：{env_path}")
else:
    print(f"未找到 .env 文件：{env_path}")

from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel

from services.config import (
    SERVER_HOST, SERVER_PORT, LOG_LEVEL, ENABLE_LLM,
    LLM_MODEL, LLM_BASE_URL,
)

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from data import close as close_data_client
from services.alert_parser import AlertParser
from services.log_tracker import LogTracker
from services.root_cause import RootCauseAnalyzer
from services.report_gen import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("diagnosis-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("告警驱动型故障诊断智能体启动")
    logger.info("数据源:本地 Mock API 服务 (localhost:8080)")
    if ENABLE_LLM:
        logger.info(f"LLM 推理:已启用 (model={LLM_MODEL})")
    else:
        logger.info("LLM 推理:未配置 DASHSCOPE_API_KEY,使用规则推理降级")
    logger.info("=" * 60)
    yield
    # 关闭时清理 HTTP 客户端
    close_data_client()
    logger.info("智能体关闭")


app = FastAPI(
    title="告警驱动型故障诊断智能体",
    description="自动接收告警、追踪微服务日志、推理根因、生成标准化诊断报告",
    version="1.0.0",
    lifespan=lifespan,
)


class AlertInput(BaseModel):
    """告警输入 — JSON 格式"""
    微服务名称:str
    告警信息:str | None = None
    告警时间:str


class DiagnosisResponse(BaseModel):
    """诊断响应"""
    status: str
    report: dict | None = None
    message: str | None = None


@app.post("/api/diagnose", response_model=DiagnosisResponse, summary="提交告警进行诊断")
async def diagnose_alert(alert: AlertInput):
    """核心接口：接收告警并执行完整诊断流程"""
    alert_data = {
        "微服务名称": alert.微服务名称,
        "告警信息": alert.告警信息,
        "告警时间": alert.告警时间,
    }
    if alert.告警信息:
        logger.info(f"收到诊断请求：服务={alert_data['微服务名称']}, 时间={alert_data['告警时间']}, 告警信息={alert.告警信息}")
    else:
        logger.info(f"收到诊断请求：服务={alert_data['微服务名称']}, 时间={alert_data['告警时间']} (无告警信息，仅基于日志分析)")

    parsed_alert, error_report = AlertParser.parse(alert_data)
    if error_report:
        return DiagnosisResponse(
            status="incomplete",
            report=error_report.to_dict(),
            message=error_report.根因分析,
        )

    tracker = LogTracker()
    trace_result = tracker.trace(
        service_name=parsed_alert.微服务名称,
        start_time=parsed_alert.normalized_time,
    )
    logger.info(f"调用链:{' -> '.join(trace_result['call_chain'])}")

    analyzer = RootCauseAnalyzer()
    root_cause_result = analyzer.analyze(
        call_chain=trace_result["call_chain"],
        all_logs=trace_result["all_logs"],
        alert_info={
            "alert_message": alert.告警信息 or "",
            "alert_time": alert.告警时间,
        },
    )

    report = ReportGenerator.generate(
        alert_error_message=parsed_alert.告警信息,
        call_chain=trace_result["call_chain"],
        root_cause_analysis=root_cause_result,
        all_logs=trace_result["all_logs"],
    )

    # 构建响应数据，包含日志信息
    response_report = report.to_dict()
    response_report["call_chain"] = trace_result["call_chain"]
    response_report["logs"] = trace_result["all_logs"]
    response_report["matched_cases"] = root_cause_result.get("matched_cases", [])
    response_report["confidence"] = root_cause_result.get("confidence", "medium")
    response_report["is_new_case"] = root_cause_result.get("is_new_case", False)
    response_report["new_case_message"] = root_cause_result.get("new_case_message", "")
    response_report["new_case_info"] = root_cause_result.get("new_case_info")

    return DiagnosisResponse(status="success", report=response_report, message="诊断完成")


@app.post("/api/confirm_new_case", summary="确认添加新故障到知识库")
async def confirm_new_case(case_data: dict):
    """用户确认添加新故障到知识库"""
    from services.knowledge_manager import get_manager
    
    logger.info(f"收到确认添加新故障请求：{case_data.get('fault_symptom', '')[:50]}...")
    
    manager = get_manager()
    success, message = manager.confirm_and_add_case(case_data)
    
    if success:
        return {"status": "success", "message": message}
    else:
        raise HTTPException(status_code=500, detail=message)


@app.get("/api/knowledge/list", summary="分页查看历史知识库")
async def get_knowledge_list(page: int = 1, page_size: int = 20):
    """分页列出历史故障知识库案例"""
    from services.knowledge_retriever import get_retriever
    retriever = get_retriever()
    all_cases = retriever.get_all_cases()
    
    total = len(all_cases)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    cases = all_cases[start:end]
    
    return {"total": total, "total_pages": total_pages, "page": page, "page_size": page_size, "cases": cases}


@app.get("/api/knowledge/stats", summary="获取知识库统计信息")
async def get_knowledge_stats():
    """获取知识库统计信息（案例总数等）"""
    from services.knowledge_retriever import get_retriever
    retriever = get_retriever()
    all_cases = retriever.get_all_cases()
    return {"totalCases": len(all_cases)}


@app.post("/api/knowledge/import", summary="上传并预览导入文件")
async def preview_import(file=File(...)):
    """上传 JSON 文件并预览导入结果（排重检测）"""
    from services.knowledge_manager import get_manager
    import json
    
    logger.info(f"收到导入文件预览请求")
    
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # 支持数组或对象两种格式
        if isinstance(data, dict):
            cases = [data]
        elif isinstance(data, list):
            cases = data
        else:
            raise HTTPException(status_code=400, detail="无效的 JSON 格式，应为案例对象或数组")
        
        manager = get_manager()
        new_cases, duplicate_cases, skip_cases = manager.check_import_duplicates(cases)
        
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
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败：{str(e)}")
    except Exception as e:
        logger.error(f"导入预览失败：{e}")
        raise HTTPException(status_code=500, detail=f"导入预览失败：{str(e)}")


@app.post("/api/knowledge/import/confirm", summary="确认导入知识库")
async def confirm_import(import_data: dict):
    """确认导入案例到知识库"""
    from services.knowledge_manager import get_manager
    
    cases = import_data.get("cases", [])
    overwrite_duplicates = import_data.get("overwrite_duplicates", False)
    
    logger.info(f"收到确认导入请求：{len(cases)} 个案例，overwrite={overwrite_duplicates}")
    
    if not cases:
        raise HTTPException(status_code=400, detail="没有可导入的案例")
    
    manager = get_manager()
    result = manager.import_knowledge_batch(cases, overwrite_duplicates)
    
    return {
        "status": "success",
        "message": f"导入完成：成功 {result['success']}/{result['total']}, 跳过 {result['skipped']}",
        "result": result,
    }


@app.post("/api/knowledge/clear", summary="清空知识库")
async def clear_knowledge():
    """清空知识库（删除所有案例）"""
    from services.knowledge_manager import get_manager
    
    logger.info("收到清空知识库请求")
    
    manager = get_manager()
    result = manager.clear_knowledge_base()
    
    return {
        "status": "success",
        "message": f"知识库已清空，共删除 {result['deleted_count']} 个案例",
    }


@app.delete("/api/knowledge/{case_id}", summary="删除单条知识")
async def delete_knowledge(case_id: int):
    """删除知识库中的单条案例"""
    from services.knowledge_retriever import get_retriever
    
    logger.info(f"收到删除知识请求：case_id={case_id}")
    
    retriever = get_retriever()
    success = retriever.delete_case(case_id)
    
    if success:
        return {
            "status": "success",
            "message": f"案例 #{case_id} 已删除",
        }
    else:
        raise HTTPException(status_code=404, detail=f"案例 #{case_id} 不存在")


# 挂载静态文件目录（前端页面）- 使用 catch-all 路由确保 API 路由优先
webui_dir = os.path.join(CODE_DIR, "webui", "dist")
if os.path.exists(webui_dir):
    from fastapi.responses import FileResponse, HTMLResponse
    import mimetypes
    
    @app.get("/{path:path}")
    async def serve_static(path: str):
        """Serve 静态文件作为回退（API 路由优先）"""
        if path == "" or path == "index.html":
            file_path = os.path.join(webui_dir, "index.html")
        else:
            file_path = os.path.join(webui_dir, path)
        
        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            return FileResponse(file_path, media_type=mime_type or "application/octet-stream")
        
        # 如果文件不存在，返回 index.html（支持 SPA 前端路由）
        return HTMLResponse(content=open(os.path.join(webui_dir, "index.html")).read())
    
    logger.info(f"前端静态文件目录：{webui_dir}")
else:
    logger.warning(f"前端静态文件目录不存在：{webui_dir}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
