"""
告警驱动型故障诊断智能体
FastAPI 主入口 - 仅保留 API 路由
"""
import logging
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
env_path = Path(__file__).parent / "config" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载环境变量：{env_path}")
else:
    print(f"未找到 .env 文件：{env_path}")

from fastapi import FastAPI, HTTPException, File
from pydantic import BaseModel, Field

from services.config import (
    SERVER_HOST, SERVER_PORT, LOG_LEVEL, ENABLE_LLM,
    LLM_MODEL, LLM_BASE_URL,
)

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from data import close as close_data_client
from services.api.diagnosis_handler import DiagnosisHandler
from services.api.knowledge_manager.api_handler import KnowledgeHandler
from services.api.warning_graph_handler import WarningGraphHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("diagnosis-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("告警驱动型故障诊断智能体启动")
    logger.info("数据源：本地 Mock API 服务 (localhost:8080)")
    if ENABLE_LLM:
        logger.info(f"LLM 推理：已启用 (model={LLM_MODEL})")
    else:
        logger.info("LLM 推理：未配置 DASHSCOPE_API_KEY，使用规则推理降级")
    logger.info("=" * 60)
    yield
    close_data_client()
    logger.info("智能体关闭")


app = FastAPI(
    title="告警驱动型故障诊断智能体",
    description="自动接收告警、追踪微服务日志、推理根因、生成标准化诊断报告",
    version="1.0.0",
    lifespan=lifespan,
)


class AlertInput(BaseModel):
    """告警输入 - JSON 格式"""
    service_name: str = Field(..., alias="微服务名称")
    alert_message: str | None = Field(None, alias="告警信息")
    alert_time: str = Field(..., alias="告警时间")
    
    class Config:
        populate_by_name = True


class DiagnosisResponse(BaseModel):
    """诊断响应"""
    status: str
    report: dict | None = None
    message: str | None = None


@app.post("/api/diagnose", response_model=DiagnosisResponse, summary="提交告警进行诊断")
async def diagnose_alert(alert: AlertInput):
    """核心接口：接收告警并执行完整诊断流程"""
    alert_data = {
        "微服务名称": alert.service_name,
        "告警信息": alert.alert_message,
        "告警时间": alert.alert_time,
    }
    
    handler = DiagnosisHandler(alert_data)
    result = handler.execute()
    
    return DiagnosisResponse(
        status=result["status"],
        report=result["report"],
        message=result["message"],
    )


@app.post("/api/confirm_new_case", summary="确认添加新故障到知识库")
async def confirm_new_case(case_data: dict):
    handler = KnowledgeHandler()
    success, message = handler.confirm_new_case(case_data)
    
    if success:
        return {"status": "success", "message": message}
    else:
        raise HTTPException(status_code=500, detail=message)


@app.get("/api/knowledge/list", summary="分页查看历史知识库")
async def get_knowledge_list(page: int = 1, page_size: int = 20):
    handler = KnowledgeHandler()
    return handler.get_knowledge_list(page, page_size)


@app.get("/api/knowledge/stats", summary="获取知识库统计信息")
async def get_knowledge_stats():
    handler = KnowledgeHandler()
    return handler.get_knowledge_stats()


@app.post("/api/knowledge/import", summary="上传并预览导入文件")
async def preview_import(file=File(...)):
    handler = KnowledgeHandler()
    try:
        content = await file.read()
        return handler.preview_import(content)
    except Exception as e:
        logger.error(f"导入预览失败：{e}")
        raise HTTPException(status_code=500, detail=f"导入预览失败：{str(e)}")


@app.post("/api/knowledge/import/confirm", summary="确认导入知识库")
async def confirm_import(import_data: dict):
    cases = import_data.get("cases", [])
    overwrite_duplicates = import_data.get("overwrite_duplicates", False)
    handler = KnowledgeHandler()
    return handler.confirm_import(cases, overwrite_duplicates)


@app.post("/api/knowledge/clear", summary="清空知识库")
async def clear_knowledge():
    handler = KnowledgeHandler()
    return handler.clear_knowledge()


@app.delete("/api/knowledge/{case_id}", summary="删除单条知识")
async def delete_knowledge(case_id: int):
    handler = KnowledgeHandler()
    return handler.delete_case(case_id)


@app.post("/api/microservices/graph/warning", summary="获取基于诊断结果的微服务预警图数据")
async def get_microservices_warning_graph(diagnosis_result: dict):
    handler = WarningGraphHandler(CODE_DIR)
    return handler.generate(diagnosis_result)


webui_dir = os.path.join(CODE_DIR, "webui", "dist")
if os.path.exists(webui_dir):
    from fastapi.responses import FileResponse, HTMLResponse
    import mimetypes
    
    @app.get("/{path:path}")
    async def serve_static(path: str):
        if path == "" or path == "index.html":
            file_path = os.path.join(webui_dir, "index.html")
        else:
            file_path = os.path.join(webui_dir, path)
        
        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            return FileResponse(file_path, media_type=mime_type or "application/octet-stream")
        
        return HTMLResponse(content=open(os.path.join(webui_dir, "index.html")).read())
    
    logger.info(f"前端静态文件目录：{webui_dir}")
else:
    logger.warning(f"前端静态文件目录不存在：{webui_dir}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
