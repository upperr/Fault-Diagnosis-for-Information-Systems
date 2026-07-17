<template>
  <div class="knowledge-page">
    <header class="page-header">
      <div class="header-left">
        <button @click="$emit('back')" class="btn btn-back">← 返回</button>
        <h1>历史故障知识库管理</h1>
      </div>
      <div class="header-right">
        <div class="stats-display">
          <span class="stat-label">案例总数：</span>
          <span class="stat-value">{{ totalCases }}</span>
        </div>
      </div>
    </header>

    <main class="page-main">
      <!-- 知识库列表 -->
      <div class="card knowledge-list-card">
        <div class="card-header">
          <div class="card-title">知识库案例列表</div>
          <button @click="handleClear" class="btn btn-clear" :disabled="clearing">
            {{ clearing ? '清空中...' : '🗑️ 清空知识库' }}
          </button>
        </div>
        
        <div v-if="loading" class="loading-state">
          <span class="loading-spinner">⏳</span>
          <span>加载中...</span>
        </div>
        
        <div v-else-if="cases.length === 0" class="empty-state">
          <p>暂无知识库案例</p>
          <p class="empty-hint">请通过下方"批量导入"功能添加案例</p>
        </div>
        
        <div v-else class="table-container">
          <table class="knowledge-table">
            <thead>
              <tr>
                <th class="col-id">序号</th>
                <th class="col-symptom">故障现象</th>
                <th class="col-process">排查流程</th>
                <th class="col-cause">根因分析</th>
                <th class="col-suggestion">处置建议</th>
                <th class="col-action">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(caseItem, index) in cases" :key="caseItem.case_no || index" class="case-row">
                <td class="col-id">{{ caseItem.case_no || index + 1 }}</td>
                <td class="col-symptom">{{ caseItem.fault_symptom || '-' }}</td>
                <td class="col-process">{{ caseItem.diagnosis_process || '-' }}</td>
                <td class="col-cause">{{ caseItem.root_cause || '-' }}</td>
                <td class="col-suggestion">{{ caseItem.suggestion || '-' }}</td>
                <td class="col-action">
                  <button @click="handleDelete(caseItem.case_no)" class="btn btn-delete" :disabled="deleting" title="删除案例">
                    🗑️
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          
          <!-- 分页控件 -->
          <div class="pagination">
            <button 
              @click="changePage(currentPage - 1)" 
              :disabled="currentPage <= 1"
              class="btn btn-page"
            >
              ← 上一页
            </button>
            
            <div class="page-info">
              第 <span class="page-num">{{ currentPage }}</span> 页，共 {{ totalPages }} 页
              <span v-if="totalCases > 0">（{{ totalCases }} 条记录）</span>
            </div>
            
            <button 
              @click="changePage(currentPage + 1)" 
              :disabled="currentPage >= totalPages"
              class="btn btn-page"
            >
              下一页 →
            </button>
          </div>
        </div>
      </div>

      <!-- 导入功能 -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">批量导入知识库</div>
        </div>
        <div class="import-section">
          <p class="import-hint">上传 JSON 文件，格式：[{ "故障现象": "...", "排查流程": "...", "根因分析": "...", "处置建议": "..." }]</p>
          
          <div class="file-upload">
            <input 
              type="file" 
              ref="fileInput" 
              @change="handleFileSelect" 
              accept=".json"
              style="display:none"
            />
            <button @click="$refs.fileInput.click()" class="btn btn-primary" :disabled="uploading">
              {{ uploading ? '上传中...' : '选择 JSON 文件' }}
            </button>
            <span v-if="selectedFile" class="file-name">{{ selectedFile.name }}</span>
          </div>

          <!-- 导入预览 -->
          <div v-if="importPreview" class="import-preview">
            <div class="preview-header">
              <h4>导入预览</h4>
              <div class="preview-stats">
                <span class="stat-new">新案例：{{ importPreview.new_cases_count }}</span>
                <span class="stat-duplicate" v-if="importPreview.duplicate_cases_count > 0">重复：{{ importPreview.duplicate_cases_count }}</span>
              </div>
            </div>

            <!-- 重复案例处理 -->
            <div v-if="importPreview.has_duplicates" class="duplicate-section">
              <h5>发现重复案例</h5>
              <p class="duplicate-hint">以下案例与现有知识库中的案例故障现象相同，请选择处理方式：</p>
              
              <div class="duplicate-options">
                <label class="radio-option">
                  <input type="radio" v-model="localOverwriteDuplicates" :value="false" />
                  <span>跳过重复案例（仅导入新案例）</span>
                </label>
                <label class="radio-option">
                  <input type="radio" v-model="localOverwriteDuplicates" :value="true" />
                  <span>覆盖重复案例（用新数据替换现有数据）</span>
                </label>
              </div>

              <div class="duplicate-list">
                <div v-for="(dup, idx) in importPreview.duplicate_cases" :key="idx" class="duplicate-item">
                  <div class="duplicate-field">
                    <strong>故障现象：</strong>{{ dup.import_case.fault_symptom }}
                  </div>
                  <div class="duplicate-compare">
                    <div class="existing">
                      <strong>现有案例根因：</strong>{{ dup.existing_case.root_cause }}
                    </div>
                    <div class="importing">
                      <strong>导入案例根因：</strong>{{ dup.import_case.root_cause }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="preview-actions">
              <button @click="$emit('confirm-import')" class="btn btn-success" :disabled="confirming">
                {{ confirming ? '导入中...' : '确认导入' }}
              </button>
              <button @click="$emit('cancel-import')" class="btn btn-secondary">取消</button>
            </div>
          </div>

          <!-- 导入结果 -->
          <div v-if="importResult" :class="['import-result', importResult.status]">
            <strong>{{ importResult.status === 'success' ? '✅' : '❌' }}</strong>
            {{ importResult.message }}
            <div v-if="importResult.import_result?.errors?.length > 0" class="error-list">
              <div v-for="(err, idx) in importResult.import_result.errors" :key="idx" class="error-item">
                {{ err }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <footer class="page-footer">
      <p>国网新员工培训 AI+ 微创新 比武打擂 | 故障诊断智能体 v1.0</p>
    </footer>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'KnowledgePage',
  props: {
    stats: { type: Object, default: () => ({ totalCases: 0 }) },
    selectedFile: { type: Object, default: null },
    uploading: { type: Boolean, default: false },
    importPreview: { type: Object, default: null },
    overwriteDuplicates: { type: Boolean, default: false },
    confirming: { type: Boolean, default: false },
    importResult: { type: Object, default: null },
    clearing: { type: Boolean, default: false }
  },
  emits: ['back', 'file-select', 'confirm-import', 'cancel-import', 'confirm-clear', 'update:overwrite-duplicates', 'delete-case'],
  data() {
    return {
      localOverwriteDuplicates: this.overwriteDuplicates,
      // 知识库列表
      cases: [],
      totalCases: 0,
      currentPage: 1,
      totalPages: 0,
      pageSize: 20,
      loading: false,
      deleting: false,
      deletingCaseId: null
    }
  },
  watch: {
    overwriteDuplicates(val) {
      this.localOverwriteDuplicates = val
    },
    localOverwriteDuplicates(val) {
      this.$emit('update:overwrite-duplicates', val)
    }
  },
  mounted() {
    this.loadCases()
  },
  methods: {
    async loadCases() {
      this.loading = true
      try {
        const res = await axios.get('/api/knowledge/list', {
          params: {
            page: this.currentPage,
            page_size: this.pageSize
          }
        })
        this.cases = res.data.cases || []
        this.totalCases = res.data.total || 0
        this.totalPages = res.data.total_pages || 0
      } catch (e) {
        console.error('加载知识库列表失败:', e)
        this.cases = []
        this.totalCases = 0
        this.totalPages = 0
      } finally {
        this.loading = false
      }
    },
    
    changePage(newPage) {
      if (newPage < 1 || newPage > this.totalPages) return
      this.currentPage = newPage
      this.loadCases()
    },
    
    handleFileSelect(event) {
      this.$emit('file-select', event.target.files[0])
      this.$refs.fileInput.value = ''
    },
    
    handleClear() {
      if (confirm('确定要清空知识库吗？\n\n此操作将删除所有历史故障案例，且不可逆！')) {
        this.$emit('confirm-clear')
      }
    },
    
    async handleDelete(caseNo) {
      if (!confirm(`确定要删除案例 #${caseNo} 吗？\n\n此操作不可逆！`)) {
        return
      }
      
      this.deleting = true
      this.deletingCaseId = caseNo
      
      try {
        const res = await axios.delete(`/api/knowledge/${caseNo}`)
        alert(res.data.message || '删除成功')
        this.$emit('delete-case')
        this.loadCases()
      } catch (e) {
        alert('删除失败：' + (e.response?.data?.detail || e.message))
      } finally {
        this.deleting = false
        this.deletingCaseId = null
      }
    }
  }
}
</script>

<style scoped>
.knowledge-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  border-bottom: 1px solid #333;
  background: rgba(30, 30, 50, 0.5);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-right {
  display: flex;
  align-items: center;
}

.btn-back {
  padding: 8px 16px;
  background: rgba(0, 217, 255, 0.2);
  border: 1px solid rgba(0, 217, 255, 0.5);
  color: #00d9ff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.btn-back:hover {
  background: rgba(0, 217, 255, 0.3);
  border-color: rgba(0, 217, 255, 0.8);
}

.page-header h1 {
  font-size: 1.8em;
  background: linear-gradient(90deg, #00d9ff, #00ff88);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
}

.stats-display {
  background: rgba(0, 217, 255, 0.1);
  border: 1px solid rgba(0, 217, 255, 0.3);
  border-radius: 8px;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.stat-label {
  color: #888;
  font-size: 14px;
}

.stat-value {
  color: #00d9ff;
  font-size: 1.5em;
  font-weight: 700;
}

.page-main {
  flex: 1;
  padding: 30px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 25px;
  margin-bottom: 25px;
  border: 1px solid #333;
}

.knowledge-list-card {
  padding: 0;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 25px;
  margin: 0;
  border-bottom: 1px solid #333;
}

.card-title {
  color: #00d9ff;
  font-size: 1.2em;
  font-weight: 600;
}

.btn-clear {
  padding: 8px 16px;
  background: rgba(255, 100, 100, 0.15);
  border: 1px solid rgba(255, 100, 100, 0.4);
  color: #ff6464;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.btn-clear:hover:not(:disabled) {
  background: rgba(255, 100, 100, 0.25);
  border-color: rgba(255, 100, 100, 0.7);
}

.btn-clear:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #888;
  font-size: 16px;
}

.loading-spinner {
  font-size: 32px;
  margin-bottom: 15px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #888;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 15px;
}

.empty-hint {
  font-size: 13px;
  color: #666;
  margin-top: 8px;
}

/* 表格样式 */
.table-container {
  overflow-x: auto;
}

.knowledge-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.knowledge-table thead {
  background: rgba(0, 217, 255, 0.1);
}

.knowledge-table th {
  padding: 15px 12px;
  text-align: center;
  font-weight: 600;
  color: #00d9ff;
  border-bottom: 2px solid rgba(0, 217, 255, 0.3);
  white-space: nowrap;
}

.knowledge-table td {
  padding: 14px 12px;
  border-bottom: 1px solid #333;
  color: #e0e0e0;
  vertical-align: middle;
  text-align: left;
}

.knowledge-table td.col-id,
.knowledge-table td.col-action {
  text-align: center;
}

.knowledge-table tbody tr {
  transition: background 0.2s;
}

.knowledge-table tbody tr:hover {
  background: rgba(0, 217, 255, 0.05);
}

.knowledge-table tbody tr:last-child td {
  border-bottom: none;
}

.col-id {
  width: 60px;
  text-align: center;
  color: #888;
}

.col-symptom {
  width: 20%;
  min-width: 150px;
}

.col-process {
  width: 30%;
  min-width: 200px;
}

.col-cause {
  width: 25%;
  min-width: 180px;
}

.col-suggestion {
  width: 25%;
  min-width: 180px;
}

.col-action {
  width: 60px;
  text-align: center;
}

.btn-delete {
  padding: 6px 10px;
  background: rgba(255, 100, 100, 0.15);
  border: 1px solid rgba(255, 100, 100, 0.4);
  color: #ff6464;
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.3s;
  min-width: 36px;
}

.btn-delete:hover:not(:disabled) {
  background: rgba(255, 100, 100, 0.25);
  border-color: rgba(255, 100, 100, 0.7);
}

.btn-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 分页样式 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 25px;
  border-top: 1px solid #333;
  background: rgba(0, 0, 0, 0.2);
}

.btn-page {
  padding: 8px 16px;
  background: rgba(0, 217, 255, 0.15);
  border: 1px solid rgba(0, 217, 255, 0.4);
  color: #00d9ff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.btn-page:hover:not(:disabled) {
  background: rgba(0, 217, 255, 0.25);
  border-color: rgba(0, 217, 255, 0.7);
}

.btn-page:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  color: #888;
  font-size: 14px;
}

.page-num {
  color: #00d9ff;
  font-weight: 600;
}

/* 导入区域样式 */
.import-section {
  padding: 20px 25px;
}

.import-hint {
  color: #888;
  font-size: 13px;
  margin-bottom: 15px;
  font-family: 'Monaco', 'Consolas', monospace;
}

.file-upload {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}

.file-name {
  color: #00ff88;
  font-size: 14px;
}

.import-preview {
  background: rgba(0, 217, 255, 0.05);
  border: 1px solid rgba(0, 217, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
  margin-top: 20px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.preview-header h4 {
  color: #00d9ff;
  margin: 0;
}

.preview-stats {
  display: flex;
  gap: 15px;
}

.stat-new {
  color: #00ff88;
  font-weight: 600;
}

.stat-duplicate {
  color: #ffc800;
  font-weight: 600;
}

.duplicate-section {
  background: rgba(255, 200, 0, 0.05);
  border: 1px solid rgba(255, 200, 0, 0.3);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.duplicate-section h5 {
  color: #ffc800;
  margin: 0 0 15px 0;
}

.duplicate-hint {
  color: #888;
  font-size: 13px;
  margin-bottom: 15px;
}

.duplicate-options {
  display: flex;
  gap: 25px;
  margin-bottom: 20px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #e0e0e0;
}

.radio-option input[type="radio"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.duplicate-list {
  max-height: 350px;
  overflow-y: auto;
}

.duplicate-item {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #333;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 12px;
}

.duplicate-field {
  margin-bottom: 10px;
  color: #e0e0e0;
  font-size: 14px;
}

.duplicate-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  font-size: 13px;
}

.existing {
  color: #888;
}

.importing {
  color: #00ff88;
}

.preview-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.import-result {
  margin-top: 20px;
  padding: 15px;
  border-radius: 8px;
  font-size: 14px;
}

.import-result.success {
  background: rgba(0, 255, 136, 0.1);
  border: 1px solid rgba(0, 255, 136, 0.3);
  color: #00ff88;
}

.import-result.error {
  background: rgba(255, 100, 100, 0.1);
  border: 1px solid rgba(255, 100, 100, 0.3);
  color: #ff6464;
}

.error-list {
  margin-top: 12px;
  padding-left: 20px;
}

.error-item {
  color: #ff6464;
  font-size: 13px;
  margin-bottom: 5px;
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

.btn-primary {
  background: linear-gradient(90deg, #00d9ff, #0099ff);
  color: #000;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(0, 217, 255, 0.4);
}

.btn-danger {
  background: linear-gradient(135deg, rgba(255, 100, 100, 0.2), rgba(255, 50, 50, 0.2));
  border: 1px solid rgba(255, 100, 100, 0.5);
  color: #ff6464;
}

.btn-danger:hover {
  background: linear-gradient(135deg, rgba(255, 100, 100, 0.3), rgba(255, 50, 50, 0.3));
  border-color: rgba(255, 100, 100, 0.8);
}

.page-footer {
  text-align: center;
  padding: 20px 30px;
  border-top: 1px solid #333;
  color: #666;
  font-size: 13px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 15px;
    padding: 15px 20px;
  }

  .header-left {
    flex-direction: column;
    gap: 12px;
    width: 100%;
  }

  .page-header h1 {
    font-size: 1.4em;
  }

  .page-main {
    padding: 15px;
  }

  .card-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .btn-clear {
    width: 100%;
  }

  .duplicate-compare {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .duplicate-options {
    flex-direction: column;
    gap: 12px;
  }
  
  .pagination {
    flex-direction: column;
    gap: 12px;
  }
  
  .knowledge-table th,
  .knowledge-table td {
    padding: 10px 8px;
    font-size: 12px;
  }
  
  .col-id {
    width: 45px;
  }
}
</style>
