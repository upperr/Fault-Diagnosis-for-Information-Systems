<template>
  <section class="panel result-panel">
    <h2>诊断报告</h2>
    
    <div v-if="!report" class="empty-state">
      <p>暂无诊断报告</p>
      <p>请在左侧输入告警信息，然后点击"提交诊断"</p>
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
        <h3>故障现象</h3>
        <p class="fault-summary">{{ report['故障现象简述'] || '暂无' }}</p>
      </div>

      <!-- 调用链路 -->
      <div class="report-section">
        <h3>调用链路</h3>
        <div v-if="report.call_chain && report.call_chain.length > 0" class="call-chain">
          <div class="chain-item" v-for="(svc, index) in report.call_chain" :key="index">
            <span :class="['chain-service', getServiceLevelClass(svc)]">{{ svc }}</span>
            <span v-if="index < report.call_chain.length - 1" class="chain-arrow">→</span>
          </div>
        </div>
        <div v-else class="no-data">无调用链信息</div>
      </div>

      <!-- 根因分析 -->
      <div class="report-section">
        <h3>根因分析</h3>
        <p :class="['root-cause', report.is_new_case ? 'new-case' : '']">
          {{ report.根因分析 || '暂无' }}
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
        <h3>处置建议</h3>
        <ul class="suggestions">
          <li v-for="(suggestion, index) in suggestionList" :key="index">
            {{ suggestion }}
          </li>
        </ul>
      </div>

      <!-- 匹配的历史案例 -->
      <div class="report-section">
        <h3>匹配的历史案例</h3>
        <div v-if="report.matched_cases && report.matched_cases.length > 0" class="cases">
          <div v-for="(caseItem, index) in report.matched_cases" :key="index" class="case-card">
            <div class="case-field">
              <label>现象:</label>
              <span>{{ caseItem.fault_symptom }}</span>
            </div>
            <div class="case-field">
              <label>根因:</label>
              <span>{{ caseItem.根因分析 }}</span>
            </div>
            <div class="case-field">
              <label>建议:</label>
              <span>{{ caseItem.处置建议 }}</span>
            </div>
            <div class="case-field">
              <label>相似度:</label>
              <span class="similarity">{{ (caseItem.similarity * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
        <div v-else class="no-matched-cases">
          <p>无匹配的历史故障案例</p>
          <p class="no-match-reason">经大模型决策，知识库中无与此故障相关的历史案例</p>
        </div>
      </div>

      <!-- 全链路日志 -->
      <div v-if="report.logs && report.logs.length > 0" class="report-section">
        <h3>全链路日志</h3>
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
      <div v-if="report.is_new_case && report.new_case_info" class="new-case-alert">
        <h3>检测到新故障</h3>
        <p>{{ report.new_case_message }}</p>
        
        <!-- 新故障信息展示 -->
        <div class="new-case-info">
          <div class="case-card">
            <div class="case-field">
              <label>故障现象:</label>
              <span>{{ report.new_case_info.fault_symptom }}</span>
            </div>
            <div class="case-field">
              <label>排查流程:</label>
              <span>{{ report.new_case_info.diagnosis_process }}</span>
            </div>
            <div class="case-field">
              <label>根因分析:</label>
              <span>{{ report.new_case_info.根因分析 }}</span>
            </div>
            <div class="case-field">
              <label>处置建议:</label>
              <span>{{ report.new_case_info.处置建议 }}</span>
            </div>
          </div>
        </div>
        
        <!-- 操作按钮 -->
        <div class="new-case-actions">
          <p class="action-prompt">是否添加入历史故障知识库？</p>
          <div class="button-row">
            <button @click="$emit('confirm-add-case')" :disabled="addingCase" class="btn btn-success btn-small">
              {{ addingCase ? '添加中...' : '添加' }}
            </button>
            <button @click="$emit('cancel-new-case')" class="btn btn-white btn-small">取消</button>
            <button @click="$emit('download-json')" class="btn btn-white btn-small">下载 JSON</button>
          </div>
        </div>
      </div>
      
      <div v-else-if="report.is_new_case" class="new-case-alert">
        <strong>新故障:</strong> {{ report.new_case_message }}
      </div>

      <!-- JSON 诊断报告 -->
      <div class="report-section">
        <h3>JSON 诊断报告</h3>
        <pre class="json-output">{{ jsonReport }}</pre>
        <button @click="copyJsonReport" class="btn btn-small">复制 JSON</button>
      </div>
    </div>
  </section>
</template>

<script>
export default {
  name: 'DiagnosisReport',
  props: {
    report: { type: Object, default: null },
    addingCase: { type: Boolean, default: false }
  },
  computed: {
    suggestionList() {
      // 后端返回中文字段 '处置建议'
      if (!this.report?.处置建议) return []
      if (Array.isArray(this.report.处置建议)) {
        return this.report.处置建议
      }
      return this.report.处置建议.split(/\n|\r\n/).filter(s => s.trim())
    },
    jsonReport() {
      // 仅输出 4 个核心字段
      if (!this.report) return '{}'
      return JSON.stringify({
        '故障现象简述': this.report['故障现象简述'],
        '受影响服务列表': this.report['受影响服务列表'],
        '根因分析': this.report['根因分析'],
        '处置建议': this.report['处置建议']
      }, null, 2)
    }
  },
  methods: {
    confidenceText(level) {
      const map = { high: '高', medium: '中', low: '低' }
      return map[level] || level
    },
    copyJsonReport() {
      navigator.clipboard.writeText(this.jsonReport)
      alert('已复制 JSON 诊断报告到剪贴板')
    },
    /**
     * 根据服务名称检查该服务是否有 ERROR 级日志
     * @param {string} serviceName - 服务名称
     * @returns {string} - CSS 类名：'error' 或 ''
     */
    getServiceLevelClass(serviceName) {
      if (!this.report?.logs || !Array.isArray(this.report.logs)) {
        return ''
      }
      // 检查该服务是否有 ERROR 级日志
      const hasError = this.report.logs.some(log => {
        const logService = log.微服务名称 || log.service || log._source_service
        const logLevel = log.level || log.日志等级
        return logService === serviceName && logLevel === 'ERROR'
      })
      return hasError ? 'error' : ''
    }
  }
}
</script>

<style scoped>
.result-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid #333;
  width: 100%;
  box-sizing: border-box;
  overflow-x: hidden;
}

.result-panel h2 {
  font-size: 1.5em;
  margin-bottom: 20px;
  color: #00d9ff;
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
  transition: all 0.3s ease;
}

.chain-service.error {
  background: linear-gradient(90deg, #ff4444, #cc0000);
  color: #fff;
  border: 2px solid #ff6666;
  box-shadow: 0 0 10px rgba(255, 68, 68, 0.5);
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

.no-matched-cases {
  background: rgba(255, 200, 0, 0.05);
  border: 1px dashed #ffc800;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
}

.no-matched-cases p {
  color: #ffc800;
  margin-bottom: 8px;
}

.no-matched-cases .no-match-reason {
  color: #888;
  font-size: 13px;
  margin-top: 0;
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

.new-case-alert h3 {
  color: #ffc800;
  font-size: 1.2em;
  margin-bottom: 10px;
}

.new-case-alert p {
  margin-bottom: 15px;
  line-height: 1.5;
}

.new-case-info {
  margin: 15px 0;
}

.new-case-actions {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid rgba(255, 200, 0, 0.3);
}

.action-prompt {
  color: #ffc800;
  font-weight: 600;
  margin-bottom: 10px;
}

.new-case-actions .button-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.new-case-actions .btn {
  flex: 1;
  min-width: 120px;
  justify-content: center;
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
}

.btn-success:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(0, 255, 136, 0.4);
}

.btn-white {
  background: linear-gradient(90deg, #ffffff, #f0f0f0);
  color: #1a1a2e;
}

.btn-white:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(255, 255, 255, 0.4);
}

.btn-small {
  padding: 8px 16px;
  font-size: 12px;
  margin-top: 10px;
}

.button-row {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}
</style>
