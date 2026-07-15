# 故障诊断智能体 - 前端界面

基于 Vue3 + Vite 构建的 Web 前端，通过 FastAPI 静态文件服务集成到主应用中。

## 🚀 快速启动

### 生产模式（推荐）

前端已构建到 `dist/` 目录，由 FastAPI 直接服务：

```bash
# 启动 Mock API
python mock_api_server.py

# 启动主服务（包含前端）
python main.py
```

访问 **http://localhost:8000**

### 开发模式（热更新）

```bash
# 终端 1
python mock_api_server.py

# 终端 2
python main.py

# 终端 3
cd webui
npm run dev
```

访问 **http://localhost:3000**

## 📥 输入格式

在前端页面输入 JSON 格式告警：

```json
{
  "request_id": "REQ001",
  "service": "order-service",
  "error_message": "调用 inventory-service 超时，耗时 3100ms",
  "time": "2025-03-20 10:23:05"
}
```

### 必填字段

| 字段 | 说明 |
|------|------|
| `request_id` | 告警请求 ID |
| `service` | 微服务名称 |
| `error_message` | 错误信息 |
| `time` | 告警时间 |

## 📤 输出格式

诊断报告包含：

- `status` - 诊断状态
- `request_id` - 请求 ID
- `fault_summary` - 故障现象
- `call_chain` - 调用链路
- `root_cause` - 根因分析
- `suggestion` - 处置建议
- `confidence` - 置信度
- `matched_cases` - 匹配的历史案例
- `logs` - 关键日志

## 🛠️ 开发

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build

# 预览构建结果
npm run preview
```

## 📦 技术栈

- Vue 3
- Vite 5
- Axios

## 📝 功能特性

- ✅ 手动输入 JSON 告警
- ✅ 内置示例（点击"加载示例"）
- ✅ 自动解析和验证
- ✅ 实时诊断状态
- ✅ 可视化调用链路
- ✅ 一键复制 JSON 报告
- ✅ 响应式设计
