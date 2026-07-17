"""故障诊断报告模型 — 字段与 output.jsonl 一致

output.jsonl 格式:
  { "故障现象": "订单服务调用库存服务超时",
    "排查流程": ["order-service", "inventory-service"],
    "根因分析": "库存服务数据库连接池耗尽",
    "处置建议": "立即重启库存服务,增大连接池大小" }
"""
from pydantic import BaseModel, Field


class DiagnosticReport(BaseModel):
    """
    标准化故障诊断报告（JSON 格式）。
    必须包含字段（与 output.jsonl 一致）:
      故障现象,排查流程,根因分析,处置建议
    """
    故障现象:str = Field(..., description="故障现象简述")
    排查流程:list[str] = Field(..., description="受影响服务列表（调用链）")
    根因分析:str = Field(..., description="根因分析")
    处置建议:str = Field(..., description="处置建议")

    def to_dict(self) -> dict:
        """返回仅包含 4 个必需字段的 dict（与 output.jsonl 一致）"""
        return {
            "故障现象": self.故障现象,
            "排查流程": self.排查流程,
            "根因分析": self.根因分析,
            "处置建议": self.处置建议,
        }

    def to_json(self) -> str:
        """返回 JSON 字符串（仅包含 4 个必需字段）"""
        import json
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
