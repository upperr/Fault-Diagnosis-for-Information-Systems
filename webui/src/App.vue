<template>
  <div class="app">
    <header class="header">
      <h1>⚡ 告警驱动型故障诊断智能体</h1>
      <p class="subtitle">输入告警 JSON → 追踪日志链路 → 推理根因 → 生成诊断报告</p>
    </header>

    <main class="main">
      <!-- 左侧:输入区域 -->
      <section class="panel input-panel">
        <h2>📥 告警输入</h2>
        
        <div class="input-section">
          <h3>填写告警信息</h3>
          
          <!-- 微服务名称输入框 -->
          <div class="form-group">
            <label for="serviceName">微服务名称 *</label>
            <input 
              id="serviceName"
              v-model="serviceName" 
              placeholder="如：用户服务、订单服务、网关服务"
              :disabled="diagnosing"
              class="form-input"
            />
          </div>
          
          <!-- 告警信息输入框 -->
          <div class="form-group">
            <label for="alertMessage">告警信息 *</label>
            <input 
              id="alertMessage"
              v-model="alertMessage" 
              placeholder="如：配置加载异常、调用超时、空指针异常"
              :disabled="diagnosing"
              class="form-input"
            />
          </div>
          
          <!-- 告警时间输入框 -->
          <div class="form-group">
            <label for="alertTime">告警时间 *</label>
            <input 
              id="alertTime"
              v-model="alertTime" 
              placeholder="如：2026-06-01T10:20:10Z 或 2026-06-01 10:20:10"
              :disabled="diagnosing"
              class="form-input"
            />
          </div>
          
          <div class="button-row">
            <button @click="submitDiagnosis" :disabled="!isValid || diagnosing" class="btn btn-success">
              {{ diagnosing ? '诊断中...' : '提交诊断' }}
            </button>
          </div>
        </div>

        <!-- 告警预览 -->
        <div v-if="isValid" class="parsed-alert">
          <h3>✅ 告警预览</h3>
          <pre>{{ alertPreview }}</pre>
        </div>

        <!-- 错误提示 -->
        <div v-if="error" class="error-box">
          <strong>❌ 错误:</strong> {{ error }}
        </div>

        <!-- 使用说明 -->
        <div class="help-section">
          <h3>📖 输入说明</h3>
          <p>请填写以上三个必填字段，系统将自动拼接为 JSON 格式并提交诊断。</p>
          <ul>
            <li><code>微服务名称</code> - 发生故障的微服务名称</li>
            <li><code>告警信息</code> - 具体的错误或异常描述</li>
            <li><code>告警时间</code> - 告警发生的时间，支持 ISO 8601 格式</li>
          </ul>
        </div>
      </section>

      <!-- 右侧:结果区域 -->
      <section class="panel result-panel">
        <h2>📊 诊断报告</h2>
        
        <div v-if="!report" class="empty-state">
          <p>暂无诊断报告</p>
          <p>请在左侧输入告警 JSON,然后点击"提交诊断"</p>
        </div>

        <div v-else class="report-content">
          <!-- 报告头部 -->
          <div class="report-header">
            <div class="report-field">
              <label>诊断状态:</label>
              <span :class="['status', report.status]">{{ report.status }}</span>
            </div>
          </div>

          <!-- 故障现象 -->
          <div class="report-section">
            <h3>🔍 故障现象</h3>
            <p class="fault-summary">{{ report.fault_summary || '暂无' }}</p>
          </div>

          <!-- 调用链路 -->
          <div class="report-section">
            <h3>🔗 调用链路</h3>
            <div v-if="report.call_chain && report.call_chain.length > 0" class="call-chain">
              <div class="chain-item" v-for="(svc, index) in report.call_chain" :key="index">
                <span class="chain-service">{{ svc }}</span>
                <span v-if="index < report.call_chain.length - 1" class="chain-arrow">→</span>
              </div>
            </div>
            <div v-else class="no-data">无调用链信息</div>
          </div>

          <!-- 根因分析 -->
          <div class="report-section">
            <h3>🎯 根因分析</h3>
            <p :class="['root-cause', report.is_new_case ? 'new-case' : '']">
              {{ report.root_cause || '暂无' }}
            </p>
            <div v-if="report.confidence" class="confidence">
              <label>置信度:</label>
              <span :class="['confidence-level', report.confidence]">
                {{ confidenceText(report.confidence) }}
              </span>
            </div>
          </div>

          <!-- 处置建议 -->
          <div class="report-section">
            <h3>💡 处置建议</h3>
            <ul class="suggestions">
              <li v-for="(suggestion, index) in suggestionList" :key="index">
                {{ suggestion }}
              </li>
            </ul>
          </div>

          <!-- 匹配的历史案例 -->
          <div v-if="report.matched_cases && report.matched_cases.length > 0" class="report-section">
            <h3>📚 匹配的历史案例</h3>
            <div class="cases">
              <div v-for="(caseItem, index) in report.matched_cases" :key="index" class="case-card">
                <div class="case-field">
                  <label>现象:</label>
                  <span>{{ caseItem.fault_symptom }}</span>
                </div>
                <div class="case-field">
                  <label>根因:</label>
                  <span>{{ caseItem.root_cause }}</span>
                </div>
                <div class="case-field">
                  <label>建议:</label>
                  <span>{{ caseItem.suggestion }}</span>
                </div>
                <div class="case-field">
                  <label>相似度:</label>
                  <span class="similarity">{{ (caseItem.similarity * 100).toFixed(1) }}%</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 日志详情 -->
          <div v-if="report.logs && report.logs.length > 0" class="report-section">
            <h3>📝 全链路日志</h3>
            <div class="logs">
              <div v-for="(log, index) in report.logs" :key="index" :class="['log-entry', log.level]">
                <span class="log-level">{{ log.level }}</span>
                <span class="log-service">{{ log.微服务名称 || log.service || log._source_service }}</span>
                <span class="log-message">{{ log.日志内容 || log.message }}</span>
                <span class="log-time">{{ log.产生时间 || log.timestamp }}</span>
              </div>
            </div>
          </div>

          <!-- 新故障提示 -->
          <div v-if="report.is_new_case" class="new-case-alert">
            <strong>ℹ️ 新故障:</strong> {{ report.new_case_message }}
          </div>

          <!-- 原始 JSON -->
          <div class="report-section">
            <h3>📄 原始 JSON</h3>
            <pre class="json-output">{{ JSON.stringify(report, null, 2) }}</pre>
            <button @click="copyReport" class="btn btn-small">复制 JSON</button>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <p>国网新员工培训 AI+ 微创新 比武打擂 | 故障诊断智能体 v1.0</p>
    </footer>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'App',
  data() {
    return {
      diagnosing: false,
      // 三个独立输入框
      serviceName: '',
      alertMessage: '',
      alertTime: '',
      report: null,
      error: null
    }
  },
  computed: {
    // 验证输入是否完整
    isValid() {
      return this.serviceName.trim() && this.alertMessage.trim() && this.alertTime.trim()
    },
    // 告警预览 JSON
    alertPreview() {
      if (!this.isValid) return ''
      return JSON.stringify({
        '微服务名称': this.serviceName.trim(),
        '告警信息': this.alertMessage.trim(),
        '告警时间': this.alertTime.trim()
      }, null, 2)
    },
    suggestionList() {
      if (!this.report?.suggestion) return []
      if (Array.isArray(this.report.suggestion)) {
        return this.report.suggestion
      }
      return this.report.suggestion.split(/\\n|\n/).filter(s => s.trim())
    }
  },
  methods: {
    async submitDiagnosis() {
      if (!this.isValid) {
        alert('请填写完整的告警信息（微服务名称、告警信息、告警时间）')
        return
      }
      this.diagnosing = true
      this.error = null
      try {
        const res = await axios.post('/api/diagnose', {
          '微服务名称': this.serviceName.trim(),
          '告警信息': this.alertMessage.trim(),
          '告警时间': this.alertTime.trim()
        })
        // res.data 结构：{ status, report, message }
        // 需要将 report 对象赋值给 this.report，同时保留 status
        this.report = {
          ...res.data.report,
          status: res.data.status
        }
      } catch (e) {
        this.error = '诊断失败:' + (e.response?.data?.detail || e.message)
      } finally {
        this.diagnosing = false
      }
    },

    confidenceText(level) {
      const map = { high: '高', medium: '中', low: '低' }
      return map[level] || level
    },

    copyReport() {
      navigator.clipboard.writeText(JSON.stringify(this.report, null, 2))
      alert('已复制到剪贴板')
    }
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  min-height: 100vh;
  color: #e0e0e0;
}

.app {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  box-sizing: border-box;
  overflow-x: hidden;
}

.header {
  text-align: center;
  padding: 30px 0;
  border-bottom: 1px solid #333;
  margin-bottom: 30px;
}

.header h1 {
  font-size: 2.5em;
  background: linear-gradient(90deg, #00d9ff, #00ff88);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 10px;
}

.subtitle {
  color: #888;
  font-size: 1.1em;
}

.main {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 20px;
  width: 100%;
}

@media (max-width: 900px) {
  .main {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid #333;
  width: 100%;
  box-sizing: border-box;
  overflow-x: hidden;
}

.panel h2 {
  font-size: 1.5em;
  margin-bottom: 20px;
  color: #00d9ff;
}

.input-section {
  margin-bottom: 20px;
}

.input-section h3 {
  font-size: 1.1em;
  margin-bottom: 10px;
  color: #aaa;
}

/* 表单样式 */
.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  color: #00d9ff;
  font-size: 14px;
  font-weight: 600;
}

.form-input {
  width: 100%;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 12px 15px;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 14px;
  transition: border-color 0.3s;
}

.form-input:focus {
  outline: none;
  border-color: #00d9ff;
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

textarea {
  width: 100%;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 15px;
  color: #e0e0e0;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 13px;
  resize: vertical;
}

textarea:focus {
  outline: none;
  border-color: #00d9ff;
}

.button-row {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #333;
  color: #e0e0e0;
}

.btn-secondary:hover:not(:disabled) {
  background: #444;
}

.btn-success {
  background: linear-gradient(90deg, #00ff88, #00cc6a);
  color: #000;
  flex: 1;
}

.btn-success:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(0, 255, 136, 0.4);
}

.btn-small {
  padding: 8px 16px;
  font-size: 12px;
  margin-top: 10px;
}

.parsed-alert {
  background: #0d1117;
  border: 1px solid #00ff88;
  border-radius: 8px;
  padding: 15px;
  margin-top: 15px;
}

.parsed-alert h3 {
  color: #00ff88;
  font-size: 1em;
  margin-bottom: 10px;
}

.parsed-alert pre {
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  color: #00ff88;
}

.error-box {
  background: rgba(255, 0, 0, 0.1);
  border: 1px solid #ff4444;
  border-radius: 8px;
  padding: 15px;
  margin-top: 15px;
  color: #ff4444;
}

.help-section {
  margin-top: 20px;
  padding: 15px;
  background: rgba(0, 217, 255, 0.05);
  border: 1px solid #333;
  border-radius: 8px;
}

.help-section h3 {
  color: #00d9ff;
  font-size: 1em;
  margin-bottom: 10px;
}

.help-section p {
  color: #aaa;
  margin-bottom: 10px;
}

.help-section ul {
  list-style: none;
  padding-left: 0;
}

.help-section li {
  margin-bottom: 5px;
  color: #888;
}

.help-section code {
  background: #0d1117;
  padding: 2px 8px;
  border-radius: 4px;
  color: #00d9ff;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 12px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.report-header {
  padding-bottom: 15px;
  border-bottom: 1px solid #333;
  margin-bottom: 20px;
}

.report-field {
  display: flex;
  gap: 10px;
}

.report-field label {
  color: #888;
}

.status {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status.success {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.status.incomplete {
  background: rgba(255, 200, 0, 0.2);
  color: #ffc800;
}

.report-section {
  margin-bottom: 25px;
}

.report-section h3 {
  font-size: 1.1em;
  color: #00d9ff;
  margin-bottom: 12px;
}

.fault-summary {
  background: #0d1117;
  padding: 15px;
  border-radius: 8px;
  border-left: 4px solid #00d9ff;
  word-wrap: break-word;
  white-space: pre-wrap;
  word-break: break-word;
}

.call-chain {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.chain-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.chain-service {
  background: linear-gradient(90deg, #00d9ff, #0099ff);
  color: #000;
  padding: 6px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 13px;
}

.chain-arrow {
  color: #666;
}

.no-data {
  color: #666;
  font-style: italic;
}

.root-cause {
  background: #0d1117;
  padding: 15px;
  border-radius: 8px;
  border-left: 4px solid #ff6b6b;
  line-height: 1.6;
  word-wrap: break-word;
  white-space: pre-wrap;
  word-break: break-word;
}

.root-cause.new-case {
  border-left-color: #ffc800;
}

.confidence {
  margin-top: 10px;
  font-size: 13px;
}

.confidence label {
  color: #888;
  margin-right: 8px;
}

.confidence-level {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.confidence-level.high {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.confidence-level.medium {
  background: rgba(255, 200, 0, 0.2);
  color: #ffc800;
}

.confidence-level.low {
  background: rgba(255, 100, 100, 0.2);
  color: #ff6464;
}

.suggestions {
  list-style: none;
  padding-left: 0;
}

.suggestions li {
  background: #0d1117;
  padding: 12px 15px;
  margin-bottom: 8px;
  border-radius: 8px;
  border-left: 3px solid #00ff88;
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
  word-break: break-word;
}

.cases {
  display: grid;
  gap: 15px;
}

.case-card {
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 15px;
  max-width: 100%;
  overflow-wrap: break-word;
}

.case-field {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}

.case-field label {
  color: #888;
  min-width: 60px;
}

.case-field .similarity {
  color: #00ff88;
  font-weight: 600;
}

.logs {
  max-height: 300px;
  overflow-y: auto;
}

.log-entry {
  display: grid;
  grid-template-columns: 50px minmax(120px, 150px) 1fr minmax(120px, 140px);
  gap: 10px;
  padding: 10px;
  margin-bottom: 8px;
  border-radius: 6px;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  align-items: start;
  min-width: 0;
}

.log-entry.ERROR {
  background: rgba(255, 0, 0, 0.1);
  border: 1px solid rgba(255, 0, 0, 0.3);
}

.log-entry.WARN {
  background: rgba(255, 200, 0, 0.1);
  border: 1px solid rgba(255, 200, 0, 0.3);
}

.log-entry.INFO {
  background: rgba(0, 217, 255, 0.1);
  border: 1px solid rgba(0, 217, 255, 0.3);
}

.log-level {
  font-weight: 700;
  min-width: 50px;
}

.log-entry.ERROR .log-level { color: #ff4444; }
.log-entry.WARN .log-level { color: #ffc800; }
.log-entry.INFO .log-level { color: #00d9ff; }

.log-service {
  color: #00d9ff;
  min-width: 100px;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-message {
  color: #e0e0e0;
  flex: 1;
  word-break: break-word;
}

.log-time {
  color: #888;
  font-size: 11px;
  min-width: 120px;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.new-case-alert {
  background: rgba(255, 200, 0, 0.1);
  border: 1px solid #ffc800;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 20px;
  color: #ffc800;
}

.json-output {
  background: #0d1117;
  padding: 15px;
  border-radius: 8px;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  color: #00d9ff;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
  max-width: 100%;
  box-sizing: border-box;
}

.footer {
  text-align: center;
  padding: 30px 0;
  margin-top: 30px;
  border-top: 1px solid #333;
  color: #666;
  font-size: 13px;
}
</style>
