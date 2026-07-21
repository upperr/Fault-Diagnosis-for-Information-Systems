"""故障诊断报告模型 — 字段与 output.jsonl 一致

output.jsonl 格式:
  { "故障现象简述": "订单服务调用库存服务超时",
    "受影响服务列表": ["order-service", "inventory-service"],
    "根因分析": "库存服务数据库连接池耗尽",
    "处置建议": "立即重启库存服务，增大连接池大小" }
"""
from pydantic import BaseModel, Field


class DiagnosticReport(BaseModel):
    """
    标准化故障诊断报告（JSON 格式）。
    必须包含字段（与 output.jsonl 一致）:
      故障现象简述，受影响服务列表，根因分析，处置建议
    """
    fault_symptom: str = Field(..., description="故障现象简述")
    affected_services: list[str] = Field(..., description="受影响服务列表（调用链）")
    root_cause: str = Field(..., description="根因分析")
    suggestion: str = Field(..., description="处置建议")

    def to_dict(self) -> dict:
        """返回仅包含 4 个必需字段的 dict（与 output.jsonl 一致，使用中文字段名）"""
        return {
            "故障现象简述": self.fault_symptom,
            "受影响服务列表": self.affected_services,
            "根因分析": self.root_cause,
            "处置建议": self.suggestion,
        }

    def to_json(self) -> str:
        """返回 JSON 字符串（仅包含 4 个必需字段，使用中文字段名）"""
        import json
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
