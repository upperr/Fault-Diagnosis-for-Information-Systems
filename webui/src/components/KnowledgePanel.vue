<template>
  <section class="panel knowledge-panel" v-if="visible">
    <div class="panel-header">
      <h2>历史故障知识库管理</h2>
      <button @click="$emit('close')" class="btn btn-small btn-secondary">关闭</button>
    </div>
    
    <!-- 知识库统计 -->
    <div class="knowledge-stats">
      <div class="stat-card">
        <div class="stat-value">{{ stats.totalCases }}</div>
        <div class="stat-label">案例总数</div>
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
                  <strong>故障现象：</strong>{{ dup.import_case.故障现象 }}
                </div>
                <div class="duplicate-compare">
                  <div class="existing">
                    <strong>现有案例根因：</strong>{{ dup.existing_case.根因分析 }}
                  </div>
                  <div class="importing">
                    <strong>导入案例根因：</strong>{{ dup.import_case.根因分析 }}
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

    <!-- 清空知识库 -->
    <div class="card danger-zone">
      <div class="card-header">
        <div class="card-title">⚠️ 危险操作</div>
      </div>
      <div class="danger-section">
        <p>清空知识库将删除所有历史故障案例，此操作不可逆！</p>
        <button @click="$emit('confirm-clear')" class="btn btn-danger" :disabled="clearing">
          {{ clearing ? '清空中...' : '清空知识库' }}
        </button>
      </div>
    </div>
  </section>
</template>

<script>
export default {
  name: 'KnowledgePanel',
  props: {
    visible: { type: Boolean, default: false },
    stats: { type: Object, default: () => ({ totalCases: 0 }) },
    selectedFile: { type: Object, default: null },
    uploading: { type: Boolean, default: false },
    importPreview: { type: Object, default: null },
    overwriteDuplicates: { type: Boolean, default: false },
    confirming: { type: Boolean, default: false },
    importResult: { type: Object, default: null },
    clearing: { type: Boolean, default: false }
  },
  data() {
    return {
      localOverwriteDuplicates: this.overwriteDuplicates
    }
  },
  watch: {
    overwriteDuplicates(val) {
      this.localOverwriteDuplicates = val
    }
  },
  methods: {
    handleFileSelect(event) {
      this.$emit('file-select', event.target.files[0])
      // 清空文件选择，允许重复选择同一文件
      this.$refs.fileInput.value = ''
    }
  }
}
</script>

<style scoped>
.knowledge-panel {
  margin-top: 20px;
  background: rgba(30, 30, 50, 0.8);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid #333;
  width: 100%;
  box-sizing: border-box;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #333;
}

.panel-header h2 {
  margin: 0;
  color: #00d9ff;
}

.knowledge-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.1), rgba(0, 255, 136, 0.1));
  border: 1px solid rgba(0, 217, 255, 0.3);
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  min-width: 150px;
}

.stat-value {
  font-size: 2.5em;
  font-weight: 700;
  color: #00d9ff;
  margin-bottom: 5px;
}

.stat-label {
  color: #888;
  font-size: 14px;
}

.import-section {
  padding: 10px 0;
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
  padding: 15px;
  margin-top: 15px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
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
  padding: 15px;
  margin-bottom: 15px;
}

.duplicate-section h5 {
  color: #ffc800;
  margin: 0 0 10px 0;
}

.duplicate-hint {
  color: #888;
  font-size: 13px;
  margin-bottom: 15px;
}

.duplicate-options {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
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
  max-height: 300px;
  overflow-y: auto;
}

.duplicate-item {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #333;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
}

.duplicate-field {
  margin-bottom: 8px;
  color: #e0e0e0;
  font-size: 14px;
}

.duplicate-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
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
  gap: 10px;
  margin-top: 15px;
}

.import-result {
  margin-top: 15px;
  padding: 12px;
  border-radius: 6px;
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
  margin-top: 10px;
  padding-left: 20px;
}

.error-item {
  color: #ff6464;
  font-size: 13px;
  margin-bottom: 5px;
}

.card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 15px;
}

.card-header {
  margin-bottom: 10px;
}

.card-title {
  color: #00d9ff;
  font-size: 1.1em;
  font-weight: 600;
}

.danger-zone {
  margin-top: 20px;
  border: 1px solid rgba(255, 100, 100, 0.3);
  background: rgba(255, 100, 100, 0.05);
}

.danger-section {
  padding: 15px;
}

.danger-section p {
  color: #ff6464;
  margin-bottom: 15px;
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

.btn-small {
  padding: 8px 16px;
  font-size: 12px;
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
</style>
