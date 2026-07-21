<template>
  <div class="microservices-graph-page">
    <header class="header">
      <div class="header-content">
        <button @click="goBack" class="btn-back">← 返回</button>
        <h1>微服务故障预警图</h1>
      </div>
      <div class="header-stats" v-if="stats">
        <span class="stat-item chain">
          <span class="stat-label">追踪链路节点:</span>
          <span class="stat-value">{{ stats.chain_nodes?.length || 0 }}</span>
        </span>
        <span class="stat-item error">
          <span class="stat-label">故障节点:</span>
          <span class="stat-value">{{ stats.chain_error_nodes?.length || 0 }}</span>
        </span>
        <span class="stat-item warning">
          <span class="stat-label">预警节点:</span>
          <span class="stat-value">{{ stats.warning_nodes?.length || 0 }}</span>
        </span>
      </div>
    </header>

    <main class="main">
      <div class="graph-container">
        <div ref="networkContainer" class="network"></div>
      </div>

      <div class="legend">
        <h3>图例说明</h3>
        <div class="legend-items">
          <div class="legend-item">
            <span class="legend-color chain-error"></span>
            <span>ERROR 微服务</span>
          </div>
          <div class="legend-item">
            <span class="legend-color warning"></span>
            <span>预警微服务</span>
          </div>
          <div class="legend-item">
            <span class="legend-color chain-info"></span>
            <span>INFO 微服务</span>
          </div>
        </div>
        <div v-if="callChain" class="call-chain-display">
          <h4>当前诊断链路</h4>
          <div class="chain-flow">
            <span v-for="(svc, index) in callChain" :key="index" class="chain-step">
              <span class="chain-service">{{ svc }}</span>
              <span v-if="index < callChain.length - 1" class="chain-arrow">→</span>
            </span>
          </div>
        </div>
      </div>
    </main>

    <footer class="footer">
      <p>数据来源：mock_data.json + 诊断结果 | 链路内节点和边为彩色，链路外为灰色</p>
    </footer>
  </div>
</template>

<script>
import axios from 'axios'
import { Network, DataSet } from 'vis-network/standalone'

export default {
  name: 'WarningGraph',
  props: {
    diagnosisResult: {
      type: Object,
      default: null
    }
  },
  emits: ['back'],
  data() {
    return {
      network: null,
      graphData: null,
      stats: null,
      loading: true,
      error: null,
      callChain: null
    }
  },
  mounted() {
    // 只支持预警模式，必须有诊断结果
    if (!this.diagnosisResult?.call_chain) {
      this.error = '缺少诊断结果'
      this.loading = false
      return
    }
    this.callChain = this.diagnosisResult.call_chain
    this.loadWarningGraph(this.diagnosisResult)
  },
  beforeUnmount() {
    if (this.network) {
      this.network.destroy()
      this.network = null
    }
  },
  methods: {
    goBack() {
      this.$emit('back')
    },
    async loadWarningGraph(diagnosisResult) {
      this.loading = true
      this.error = null
      try {
        const res = await axios.post('/api/microservices/graph/warning', diagnosisResult)
        this.graphData = res.data
        this.stats = res.data.stats
        this.callChain = res.data.call_chain
        this.renderGraph()
      } catch (e) {
        this.error = '加载失败：' + (e.response?.data?.detail || e.message)
        console.error('加载预警图数据失败:', e)
      } finally {
        this.loading = false
      }
    },
    renderGraph() {
      if (!this.graphData || !this.$refs.networkContainer) return

      const { nodes, edges } = this.graphData

      // 转换节点数据为 vis-network 格式
      const visNodes = nodes.map(node => ({
        id: node.id,
        label: node.label,
        color: node.color,
        font: {
          color: '#ffffff',
          size: 32,
          face: 'Arial',
          strokeWidth: 3,
          strokeColor: '#000000'
        },
        size: node.type === 'chain_error' ? 70 : 60,
        shape: 'dot',  // 所有节点都是圆形
        shadow: {
          enabled: true,
          color: 'rgba(0,0,0,0.5)',
          size: 15
        },
        title: this.getNodeTitle(node)
      }))

      // 转换边数据为 vis-network 格式
      const visEdges = edges.map(edge => ({
        from: edge.source,
        to: edge.target,
        color: {
          color: edge.color || '#666666',
          highlight: edge.color || '#888888'
        },
        width: edge.width || 2,
        arrows: {
          to: {
            enabled: true,
            scaleFactor: 2,
            type: 'arrow'
          }
        },
        title: `${edge.source} → ${edge.target}\\n调用次数：${edge.count || 1}\\n${edge.is_chain_edge ? '【链路内边】' : '【链路外边】'}`,
        smooth: {
          type: 'dynamic',
          roundness: 0.2
        },
        shadow: {
          enabled: true,
          color: 'rgba(0,0,0,0.3)',
          size: 8
        }
      }))

      const data = {
        nodes: new DataSet(visNodes),
        edges: new DataSet(visEdges)
      }

      const options = {
        nodes: {
          borderWidth: 3,
          shadow: {
            enabled: true,
            color: 'rgba(0,0,0,0.5)',
            size: 15
          }
        },
        edges: {
          shadow: {
            enabled: true,
            color: 'rgba(0,0,0,0.3)',
            size: 8
          }
        },
        physics: {
          barnesHut: {
            gravitationalConstant: -100000,
            centralGravity: 0.3,
            springLength: 300,
            springConstant: 0.04,
            damping: 0.09
          },
          stabilization: {
            iterations: 300
          }
        },
        interaction: {
          hover: true,
          tooltipDelay: 200,
          zoomView: true,
          dragNodes: true,
          dragView: true
        }
      }

      this.network = new Network(this.$refs.networkContainer, data, options)

      // 点击节点事件
      this.network.on('click', (params) => {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0]
          const node = nodes.find(n => n.id === nodeId)
          if (node) {
            console.log('点击节点:', node)
            // 可以在这里添加更多交互逻辑
          }
        }
      })
    },
    getNodeTitle(node) {
      const typeMap = {
        chain_error: '【链路 ERROR】',
        chain_info: '【链路 INFO】',
        warning: '【1 跳内 ERROR 服务】',
        normal: ''
      }
      const typeLabel = typeMap[node.type] || ''
      return `${node.label}\\n${typeLabel}`
    }
  }
}
</script>

<style scoped>
.microservices-graph-page {
  width: 100%;
  min-height: 100vh;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  border-bottom: 1px solid #333;
  margin-bottom: 20px;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.btn-back {
  padding: 8px 16px;
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.2), rgba(0, 255, 136, 0.2));
  border: 1px solid rgba(0, 217, 255, 0.5);
  color: #00d9ff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.btn-back:hover {
  background: linear-gradient(135deg, rgba(0, 217, 255, 0.3), rgba(0, 255, 136, 0.3));
  border-color: rgba(0, 217, 255, 0.8);
  transform: translateY(-2px);
}

.header h1 {
  font-size: 1.8em;
  background: linear-gradient(90deg, #00d9ff, #00ff88);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
}

.header-stats {
  display: flex;
  gap: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.stat-label {
  color: #888;
  font-size: 13px;
}

.stat-value {
  color: #00d9ff;
  font-weight: bold;
  font-size: 16px;
}

.stat-item.error .stat-value {
  color: #ff6b6b;
}

.stat-item.warning .stat-value {
  color: #ffa500;
}

.main {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 20px;
  padding: 0 30px 20px;
}

.graph-container {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  border: 1px solid #333;
  overflow: hidden;
  min-height: 600px;
}

.network {
  width: 100%;
  height: 600px;
}

.legend {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  border: 1px solid #333;
  padding: 20px;
}

.legend h3 {
  color: #00d9ff;
  margin-bottom: 15px;
  font-size: 16px;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #ccc;
}

.legend-color {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-block;
}

.legend-color.error {
  background: #ff4444;
}

.legend-color.warning {
  background: #ffa500;
}

.legend-color.info {
  background: #4a90d9;
}

/* 预警模式颜色 */
.legend-color.chain-error {
  background: #ff4444;
  border: 2px solid #ff0000;
}

.legend-color.chain-info {
  background: #4a90d9;
  border: 2px solid #0066cc;
}

.legend-color.warning {
  background: #ffa500;
  border: 2px solid #cc8400;
}

.legend-color.normal {
  background: #666666;
}

.call-chain-display {
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid #333;
}

.call-chain-display h4 {
  color: #00d9ff;
  font-size: 14px;
  margin-bottom: 10px;
}

.chain-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

.chain-step {
  display: flex;
  align-items: center;
  gap: 5px;
}

.chain-service {
  background: rgba(0, 217, 255, 0.2);
  color: #00d9ff;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  border: 1px solid rgba(0, 217, 255, 0.5);
}

.chain-arrow {
  color: #666;
  font-size: 12px;
}

.footer {
  text-align: center;
  padding: 20px;
  border-top: 1px solid #333;
  color: #666;
  font-size: 13px;
}

@media (max-width: 900px) {
  .main {
    grid-template-columns: 1fr;
  }

  .header {
    flex-direction: column;
    gap: 15px;
  }

  .header-stats {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
