<template>
  <div class="app">
    <!-- 主页面：诊断功能 -->
    <div v-if="currentPage === 'home'" class="home-page">
      <header class="header">
        <div class="header-content">
          <h1>告警驱动型故障诊断智能体</h1>
        </div>
        <div class="header-buttons">
          <button @click="goToWarning" class="btn btn-warning">故障预警</button>
          <button @click="goToKnowledge" class="btn btn-knowledge">知识库管理</button>
        </div>
      </header>

      <main class="main">
        <!-- 左侧：输入区域 -->
        <DiagnosisInput
          v-model:serviceName="serviceName"
          v-model:alertMessage="alertMessage"
          v-model:alertTime="alertTime"
          :disabled="diagnosing"
          :error="error"
          @submit="submitDiagnosis"
        />

        <!-- 右侧：结果区域 -->
        <DiagnosisReport
          :report="report"
          :adding-case="addingCase"
          @confirm-add-case="confirmAddCase"
          @cancel-new-case="cancelNewCase"
          @download-json="downloadJSON"
          @copy-report="copyReport"
        />
      </main>

      <footer class="footer">
        <p>国网新员工培训 AI+ 微创新 比武打擂 | 故障诊断智能体 v1.0</p>
      </footer>
    </div>

    <!-- 知识库管理页面 -->
    <KnowledgePage
      v-else-if="currentPage === 'knowledge'"
      :stats="knowledgeStats"
      :selected-file="selectedFile"
      :uploading="uploading"
      :import-preview="importPreview"
      :overwrite-duplicates="overwriteDuplicates"
      v-model:overwrite-duplicates="overwriteDuplicates"
      :confirming="confirming"
      :import-result="importResult"
      :clearing="clearing"
      @back="goToHome"
      @file-select="handleFileSelect"
      @confirm-import="confirmImport"
      @cancel-import="cancelImport"
      @confirm-clear="confirmClear"
      @delete-case="loadKnowledgeStats"
    />
    
    <!-- 故障预警页面 -->
    <WarningGraph
      v-else-if="currentPage === 'warning'"
      :diagnosis-result="diagnosisResultForGraph"
      @back="goToHome"
    />
  </div>
</template>

<script>
import axios from 'axios'
import DiagnosisInput from './components/DiagnosisInput.vue'
import DiagnosisReport from './components/DiagnosisReport.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
import WarningGraph from './pages/WarningGraph.vue'

export default {
  name: 'App',
  components: {
    DiagnosisInput,
    DiagnosisReport,
    KnowledgePage,
    WarningGraph
  },
  data() {
    return {
      currentPage: 'home',
      diagnosing: false,
      addingCase: false,
      serviceName: '',
      alertMessage: '',
      alertTime: '',
      report: null,
      error: null,
      // 知识库管理
      knowledgeStats: { totalCases: 0 },
      selectedFile: null,
      uploading: false,
      importPreview: null,
      overwriteDuplicates: false,
      confirming: false,
      importResult: null,
      clearing: false,
      // 预警图
      diagnosisResultForGraph: null
    }
  },
  methods: {
    goToKnowledge() {
      this.currentPage = 'knowledge'
      this.loadKnowledgeStats()
    },
    goToWarning() {
      // 只有已完成诊断才进入预警图界面
      if (!this.report) {
        alert('请先输入待诊断告警信息并完成诊断')
        return
      }
      this.currentPage = 'warning'
      this.diagnosisResultForGraph = this.report
    },
    goToHome() {
      this.currentPage = 'home'
    },
    async submitDiagnosis() {
      // 微服务名称和告警时间为必填，告警信息为可选
      if (!this.serviceName.trim() || !this.alertTime.trim()) {
        alert('请填写必填字段（微服务名称、告警时间）')
        return
      }
      this.diagnosing = true
      this.error = null
      try {
        const payload = {
          '微服务名称': this.serviceName.trim(),
          '告警时间': this.alertTime.trim()
        }
        // 仅当告警信息存在时才添加
        if (this.alertMessage.trim()) {
          payload['告警信息'] = this.alertMessage.trim()
        }
        const res = await axios.post('/api/diagnose', payload)
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

    async confirmAddCase() {
      if (!this.report?.new_case_info) {
        alert('无新故障信息')
        return
      }
      this.addingCase = true
      try {
        const info = this.report.new_case_info
        const res = await axios.post('/api/confirm_new_case', {
          fault_symptom: info.fault_symptom,
          diagnosis_process: info.diagnosis_process,
          root_cause: info['根因分析'],
          suggestion: info['处置建议'],
          call_chain: info.call_chain,
          alert_time: info.alert_time,
        })
        if (res.data.status === 'success') {
          alert(res.data.message || '添加成功')
          this.report.is_new_case = false
          this.report.new_case_info = null
        } else {
          alert('添加失败:' + (res.data.message || '未知错误'))
        }
      } catch (e) {
        alert('添加失败:' + (e.response?.data?.detail || e.message))
      } finally {
        this.addingCase = false
      }
    },

    cancelNewCase() {
      this.report.is_new_case = false
      this.report.new_case_info = null
      this.report.new_case_message = '用户取消添加新案例'
    },

    downloadJSON() {
      if (!this.report?.new_case_info) {
        alert('无新故障信息')
        return
      }
      const info = this.report.new_case_info
      // 将英文字段映射为中文字段
      const jsonData = {
        '故障现象': info.fault_symptom,
        '排查流程': info.diagnosis_process,
        '根因分析': info['根因分析'],
        '处置建议': info['处置建议'],
      }
      const jsonStr = JSON.stringify(jsonData, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `新故障_${new Date().getTime()}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },

    copyReport() {
      navigator.clipboard.writeText(JSON.stringify(this.report, null, 2))
      alert('已复制到剪贴板')
    },

    // ========== 知识库管理方法 ==========
    
    async loadKnowledgeStats() {
      try {
        const res = await axios.get('/api/knowledge/stats')
        this.knowledgeStats = res.data
      } catch (e) {
        console.error('加载统计信息失败:', e)
        this.knowledgeStats = { totalCases: 0 }
      }
    },

    handleFileSelect(file) {
      if (!file) return
      this.selectedFile = file
      this.uploadFile(file)
    },

    async uploadFile(file) {
      this.uploading = true
      this.importPreview = null
      this.importResult = null
      
      try {
        const formData = new FormData()
        formData.append('file', file)
        
        const res = await axios.post('/api/knowledge/import', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        
        this.importPreview = res.data
      } catch (e) {
        this.importResult = {
          status: 'error',
          message: '上传失败：' + (e.response?.data?.detail || e.message)
        }
      } finally {
        this.uploading = false
      }
    },

    async confirmImport() {
      if (!this.importPreview) return
      
      this.confirming = true
      this.importResult = null
      
      try {
        const allCases = [
          ...this.importPreview.new_cases,
          ...this.importPreview.duplicate_cases.map(d => d.import_case)
        ]
        
        const res = await axios.post('/api/knowledge/import/confirm', {
          cases: allCases,
          overwrite_duplicates: this.overwriteDuplicates
        })
        
        this.importResult = res.data
        this.loadKnowledgeStats()
      } catch (e) {
        this.importResult = {
          status: 'error',
          message: '导入失败：' + (e.response?.data?.detail || e.message)
        }
      } finally {
        this.confirming = false
      }
    },

    cancelImport() {
      this.importPreview = null
      this.selectedFile = null
      this.importResult = null
      this.overwriteDuplicates = false
    },

    async confirmClear() {
      if (!confirm('确定要清空知识库吗？此操作不可逆！')) return
      
      this.clearing = true
      try {
        const res = await axios.post('/api/knowledge/clear')
        alert(res.data.message)
        this.loadKnowledgeStats()
      } catch (e) {
        alert('清空失败：' + (e.response?.data?.detail || e.message))
      } finally {
        this.clearing = false
      }
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

.home-page {
  width: 100%;
}

.btn-warning {
  padding: 10px 20px;
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.2), rgba(0, 255, 136, 0.2));
  border: 1px solid rgba(0, 217, 255, 0.5);
  color: #00d9ff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  white-space: nowrap;
}

.btn-warning:hover {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.3), rgba(0, 255, 136, 0.3));
  border-color: rgba(0, 217, 255, 0.8);
  transform: translateY(-2px);
}

@media (max-width: 768px) {
  .header {
    flex-direction: column;
    gap: 15px;
    padding: 20px;
  }
  
  .header-content {
    text-align: center;
  }
  
  .header-buttons {
    width: 100%;
    justify-content: center;
  }
  
  .btn-knowledge {
    width: auto;
  }
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 30px 40px;
  border-bottom: 1px solid #333;
  margin-bottom: 30px;
}

.header-content {
  flex: 1;
}

.header-buttons {
  display: flex;
  gap: 10px;
}

.header h1 {
  font-size: 2.5em;
  background: linear-gradient(90deg, #00d9ff, #00ff88);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.btn-knowledge {
  padding: 10px 20px;
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.2), rgba(0, 255, 136, 0.2));
  border: 1px solid rgba(0, 217, 255, 0.5);
  color: #00d9ff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  white-space: nowrap;
}

.btn-knowledge:hover {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.3), rgba(0, 255, 136, 0.3));
  border-color: rgba(0, 217, 255, 0.8);
  transform: translateY(-2px);
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

.footer {
  text-align: center;
  padding: 30px 0;
  margin-top: 30px;
  border-top: 1px solid #333;
  color: #666;
  font-size: 13px;
}
</style>
