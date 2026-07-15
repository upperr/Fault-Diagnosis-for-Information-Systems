"""
告警驱动型故障诊断智能体
FastAPI 主入口
"""
import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import (
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
    告警信息:str
    告警时间:str


class DiagnosisResponse(BaseModel):
    """诊断响应"""
    status: str
    report: dict | None = None
    message: str | None = None


@app.get("/health", summary="健康检查")
async def health():
    """健康检查"""
    return {"service": "告警驱动型故障诊断智能体", "version": "1.0.0", "status": "running"}


@app.post("/api/diagnose", response_model=DiagnosisResponse, summary="提交告警进行诊断")
async def diagnose_alert(alert: AlertInput):
    """核心接口：接收告警并执行完整诊断流程"""
    alert_data = {
        "微服务名称": alert.微服务名称,
        "告警信息": alert.告警信息,
        "告警时间": alert.告警时间,
    }
    logger.info(f"收到诊断请求：服务={alert_data['微服务名称']}, 时间={alert_data['告警时间']}")

    parsed_alert, error_report = AlertParser.parse(alert_data)
    if error_report:
        return DiagnosisResponse(
            status="incomplete",
            report=error_report.to_dict(),
            message=error_report.root_cause,
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
    )

    report = ReportGenerator.generate(
        alert_error_message=parsed_alert.告警信息,
        call_chain=trace_result["call_chain"],
        root_cause_analysis=root_cause_result,
        all_logs=trace_result["all_logs"],
    )

    # 构建响应数据,包含日志信息
    response_report = report.to_dict()
    response_report["call_chain"] = trace_result["call_chain"]
    response_report["logs"] = trace_result["all_logs"]
    response_report["matched_cases"] = root_cause_result.get("matched_cases", [])
    response_report["confidence"] = root_cause_result.get("confidence", "medium")
    response_report["is_new_case"] = root_cause_result.get("is_new_case", False)
    response_report["new_case_message"] = root_cause_result.get("new_case_message", "")

    return DiagnosisResponse(status="success", report=response_report, message="诊断完成")


@app.get("/api/knowledge", summary="查看历史知识库")
async def get_knowledge():
    """列出历史故障知识库中的所有案例"""
    from services.knowledge_retriever import get_retriever
    retriever = get_retriever()
    cases = retriever.get_all_cases()
    return {"count": len(cases), "cases": cases}


# 挂载静态文件目录（前端页面）- 放在所有路由之后
webui_dir = os.path.join(CODE_DIR, "webui", "dist")
if os.path.exists(webui_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=webui_dir, html=True), name="static")
    logger.info(f"前端静态文件目录：{webui_dir}")
else:
    logger.warning(f"前端静态文件目录不存在：{webui_dir}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
