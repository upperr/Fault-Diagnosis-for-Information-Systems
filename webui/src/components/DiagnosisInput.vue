<template>
  <section class="panel input-panel">
    <h2>告警输入</h2>
    
    <!-- 输入模式切换 -->
    <div class="mode-toggle">
      <button 
        :class="['mode-btn', { active: inputMode === 'form' }]" 
        @click="inputMode = 'form'"
      >
        表单输入
      </button>
      <button 
        :class="['mode-btn', { active: inputMode === 'json' }]" 
        @click="inputMode = 'json'"
      >
        JSON 输入
      </button>
    </div>

    <!-- 表单输入模式 -->
    <div v-if="inputMode === 'form'" class="input-section">
      <h3>填写告警信息</h3>
      
      <!-- 微服务名称输入框 -->
      <div class="form-group">
        <label for="serviceName">微服务名称 *</label>
        <input 
          id="serviceName"
          v-model="localServiceName" 
          placeholder="如：用户服务、订单服务、网关服务"
          :disabled="disabled"
          class="form-input"
          @input="emitChange"
        />
      </div>
      
      <!-- 告警时间输入框 -->
      <div class="form-group">
        <label for="alertTime">告警时间 *</label>
        <input 
          id="alertTime"
          v-model="localAlertTime" 
          placeholder="如：2026-06-01T10:20:10Z 或 2026-06-01 10:20:10"
          :disabled="disabled"
          class="form-input"
          @input="emitChange"
        />
      </div>
      
      <!-- 告警信息输入框 -->
      <div class="form-group">
        <label for="alertMessage">告警信息</label>
        <input 
          id="alertMessage"
          v-model="localAlertMessage" 
          placeholder="如：配置加载异常、调用超时、空指针异常（可选，留空时仅基于日志分析）"
          :disabled="disabled"
          class="form-input"
          @input="emitChange"
        />
      </div>
      
      <div class="button-row">
        <button @click="$emit('submit')" :disabled="!isValid || disabled" class="btn btn-success">
          {{ disabled ? '诊断中...' : '提交诊断' }}
        </button>
      </div>
    </div>

    <!-- JSON 输入模式 -->
    <div v-else class="input-section">
      <h3>粘贴 JSON 告警数据</h3>
      
      <div class="form-group">
        <label for="jsonInput">JSON 格式告警数据</label>
        <textarea 
          id="jsonInput"
          v-model="jsonInputText" 
          placeholder='{&#10;  "微服务名称": "用户服务",&#10;  "告警时间": "2026-06-01T10:20:10Z",&#10;  "告警信息": "配置加载异常（可选）"&#10;}'
          :disabled="disabled"
          class="form-textarea"
          rows="8"
          @input="parseJsonInput"
        ></textarea>
      </div>
      
      <!-- JSON 解析状态 -->
      <div v-if="jsonParseStatus" :class="['parse-status', jsonParseStatus.type]">
        <strong>{{ jsonParseStatus.type === 'error' ? '❌' : '✅' }}</strong>
        {{ jsonParseStatus.message }}
      </div>
      
      <div class="button-row">
        <button @click="$emit('submit')" :disabled="!isValid || disabled" class="btn btn-success">
          {{ disabled ? '诊断中...' : '提交诊断' }}
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-box">
      <strong>❌ 错误:</strong> {{ error }}
    </div>

    <!-- 使用说明 -->
    <div class="help-section">
      <h3>输入说明</h3>
      <p v-if="inputMode === 'form'">请填写以上字段，<strong>微服务名称</strong>和<strong>告警时间</strong>为必填项，<strong>告警信息</strong>为可选项（留空时系统将仅基于微服务链路日志进行分析）。</p>
      <p v-else>请直接粘贴 JSON 格式的告警数据，支持以下字段名称：</p>
      <ul v-if="inputMode === 'form'">
        <li><code>微服务名称</code> <span class="field-desc">- 发生故障的微服务名称（必填）</span></li>
        <li><code>告警时间</code> <span class="field-desc">- 告警发生的时间，支持 ISO 8601 格式（必填）</span></li>
        <li><code>告警信息</code> <span class="field-desc">- 具体的错误或异常描述（可选）</span></li>
      </ul>
      <ul v-else>
        <li><code>微服务名称</code> / <code>service_name</code> / <code>serviceName</code></li>
        <li><code>告警信息</code> / <code>alert_message</code> / <code>alertMessage</code> / <code>message</code></li>
        <li><code>告警时间</code> / <code>alert_time</code> / <code>alertTime</code> / <code>time</code></li>
      </ul>
    </div>
  </section>
</template>

<script>
export default {
  name: 'DiagnosisInput',
  props: {
    serviceName: { type: String, default: '' },
    alertMessage: { type: String, default: '' },
    alertTime: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    error: { type: String, default: null }
  },
  data() {
    return {
      inputMode: 'form',
      localServiceName: this.serviceName,
      localAlertMessage: this.alertMessage,
      localAlertTime: this.alertTime,
      jsonInputText: '',
      jsonParseStatus: null
    }
  },
  watch: {
    serviceName(val) { this.localServiceName = val },
    alertMessage(val) { this.localAlertMessage = val },
    alertTime(val) { this.localAlertTime = val }
  },
  computed: {
    isValid() {
      // 微服务名称和告警时间为必填，告警信息为可选
      return this.localServiceName.trim() && this.localAlertTime.trim()
    }
  },
  methods: {
    emitChange() {
      this.$emit('update:serviceName', this.localServiceName)
      this.$emit('update:alertMessage', this.localAlertMessage)
      this.$emit('update:alertTime', this.localAlertTime)
    },
    parseJsonInput() {
      this.jsonParseStatus = null
      if (!this.jsonInputText.trim()) {
        this.localServiceName = ''
        this.localAlertMessage = ''
        this.localAlertTime = ''
        return
      }
      
      try {
        const parsed = JSON.parse(this.jsonInputText)
        
        // 支持多种字段名称
        const serviceName = parsed['微服务名称'] || parsed['service_name'] || parsed['serviceName'] || ''
        const alertMessage = parsed['告警信息'] || parsed['alert_message'] || parsed['alertMessage'] || parsed['message'] || ''
        const alertTime = parsed['告警时间'] || parsed['alert_time'] || parsed['alertTime'] || parsed['time'] || ''
        
        // 微服务名称和告警时间为必填，告警信息为可选
        if (!serviceName || !alertTime) {
          const missing = []
          if (!serviceName) missing.push('微服务名称')
          if (!alertTime) missing.push('告警时间')
          this.jsonParseStatus = {
            type: 'error',
            message: `缺少必填字段：${missing.join('、')}`
          }
          this.localServiceName = ''
          this.localAlertMessage = ''
          this.localAlertTime = ''
          return
        }
        
        this.localServiceName = serviceName
        this.localAlertMessage = alertMessage
        this.localAlertTime = alertTime
        this.jsonParseStatus = {
          type: 'success',
          message: 'JSON 解析成功，已自动填充表单字段'
        }
        this.emitChange()
      } catch (e) {
        this.jsonParseStatus = {
          type: 'error',
          message: 'JSON 格式错误：' + e.message
        }
        this.localServiceName = ''
        this.localAlertMessage = ''
        this.localAlertTime = ''
      }
    }
  }
}
</script>

<style scoped>
.input-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid #333;
  width: 100%;
  box-sizing: border-box;
  overflow-x: hidden;
}

.input-panel h2 {
  font-size: 1.5em;
  margin-bottom: 20px;
  color: #00d9ff;
}

/* 输入模式切换按钮 */
.mode-toggle {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.mode-btn {
  flex: 1;
  padding: 12px 20px;
  background: rgba(0, 217, 255, 0.1);
  border: 1px solid #333;
  border-radius: 8px;
  color: #888;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}

.mode-btn:hover {
  background: rgba(0, 217, 255, 0.2);
  border-color: #00d9ff;
  color: #00d9ff;
}

.mode-btn.active {
  background: linear-gradient(90deg, rgba(0, 217, 255, 0.3), rgba(0, 255, 136, 0.3));
  border-color: #00d9ff;
  color: #00ff88;
}

.input-section {
  margin-bottom: 20px;
}

.input-section h3 {
  font-size: 1.1em;
  margin-bottom: 10px;
  color: #aaa;
}

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

.form-textarea {
  width: 100%;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 12px 15px;
  color: #e0e0e0;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 13px;
  transition: border-color 0.3s;
  resize: vertical;
}

.form-textarea:focus {
  outline: none;
  border-color: #00d9ff;
}

.form-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* JSON 解析状态提示 */
.parse-status {
  padding: 10px 15px;
  border-radius: 8px;
  margin-bottom: 15px;
  font-size: 14px;
}

.parse-status.success {
  background: rgba(0, 255, 136, 0.1);
  border: 1px solid #00ff88;
  color: #00ff88;
}

.parse-status.error {
  background: rgba(255, 68, 68, 0.1);
  border: 1px solid #ff4444;
  color: #ff4444;
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

.btn-success {
  background: linear-gradient(90deg, #00ff88, #00cc6a);
  color: #000;
  flex: 1;
}

.btn-success:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(0, 255, 136, 0.4);
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

.field-desc {
  color: #888;
  font-size: 12px;
}
</style>
