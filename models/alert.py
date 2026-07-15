"""告警数据模型"""
from pydantic import BaseModel, Field


class Alert(BaseModel):
    """告警信息模型"""
    微服务名称:str = Field(..., description="微服务名称")
    告警信息:str = Field(..., description="告警信息")
    告警时间:str = Field(..., description="告警时间")

    @property
    def service(self) -> str:
        """兼容属性:微服务名称"""
        return self.微服务名称

    @property
    def error_message(self) -> str:
        """兼容属性:告警信息"""
        return self.告警信息

    @property
    def time(self) -> str:
        """兼容属性:告警时间"""
        return self.告警时间

    @property
    def normalized_time(self) -> str:
        """统一时间格式:移除 Z 后缀，空格 -> T"""
        if not self.告警时间:
            return ""
        t = self.告警时间.strip().replace("Z", "").replace(" ", "T", 1)
        return t

    def validate_completeness(self) -> tuple[bool, list[str]]:
        """检查告警信息是否完整"""
        missing = []
        if not self.微服务名称:
            missing.append("微服务名称")
        if not self.告警时间:
            missing.append("告警时间")
        if not self.告警信息:
            missing.append("告警信息")
        return len(missing) == 0, missing
