<template>
  <div class="forecast-mape-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">预测误差 MAPE</h2>
        <p class="page-desc">
          基于 CHESCA <code>chesca_trace.csv</code> 中的
          <code>abs_pct_error_*</code>，汇总 ForecastAgent
          （室外温 / 光伏 / 不可调负荷 / 热水）整局平均绝对百分比误差，便于论文对比与答辩展示。
        </p>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          icon="el-icon-refresh"
          :loading="loadingList"
          @click="loadShowSimulations"
        >
          加载展示数据
        </el-button>
        <el-button
          v-if="simulationFolders.length"
          type="success"
          :disabled="loadingDetail"
          @click="showSelect = true"
        >
          选择分组
        </el-button>
      </div>
    </div>

    <select-simulation-modal
      v-model="showSelect"
      :simulation-list="simulationFolders"
      @confirm="onSimulationsSelected"
    />

    <el-empty
      v-if="!selectedSimulations.length"
      description="请先加载并选择带有 chesca_trace.csv 的 CHESCA 仿真分组"
      class="empty-block"
    />

    <template v-else>
      <el-tabs v-model="activeTab" type="border-card" class="sim-tabs">
        <el-tab-pane
          v-for="sim in selectedSimulationsSorted"
          :key="sim"
          :label="sim"
          :name="sim"
        />
      </el-tabs>

      <div v-loading="loadingDetail" class="content">
        <el-alert
          v-if="activeSim && !hasTrace"
          type="warning"
          :closable="false"
          show-icon
          title="当前分组无 chesca_trace.csv"
          description="请使用 CHESCA.py 重新运行 CHESCA 任务后再加载。"
          class="mb-16"
        />

        <template v-else-if="summary">
          <div class="filters">
            <span class="filter-label">Episode</span>
            <el-select v-model="selectedEpisode" size="small" class="filter-ctrl" clearable placeholder="全部">
              <el-option
                v-for="ep in summary.episodes"
                :key="ep"
                :label="`Episode ${ep}`"
                :value="ep"
              />
            </el-select>
            <span class="filter-label">建筑</span>
            <el-select v-model="selectedBuilding" size="small" class="filter-ctrl" clearable placeholder="全部建筑">
              <el-option
                v-for="b in summary.buildings"
                :key="b"
                :label="buildingLabel(b)"
                :value="b"
              />
            </el-select>
            <span class="sample-hint">有效样本行：{{ summary.sampleCount }}</span>
          </div>

          <el-row :gutter="16" class="card-row">
            <el-col :xs="24" :sm="12" :md="8" :lg="4">
              <div class="mape-card mape-card-overall">
                <div class="mape-card-label">综合 MAPE</div>
                <div class="mape-card-value">{{ formatMape(summary.overall) }}</div>
                <div class="mape-card-sub">四变量算术平均</div>
              </div>
            </el-col>
            <el-col
              v-for="m in summary.metrics"
              :key="m.key"
              :xs="24"
              :sm="12"
              :md="8"
              :lg="5"
            >
              <div class="mape-card" :class="'mape-' + m.key">
                <div class="mape-card-label">{{ m.label }}</div>
                <div class="mape-card-value">{{ formatMape(m.mape) }}</div>
                <div class="mape-card-sub">n = {{ m.count }}</div>
              </div>
            </el-col>
          </el-row>

          <el-row :gutter="16" class="mt-16">
            <el-col :span="14">
              <el-card shadow="never" class="panel-card">
                <div slot="header" class="panel-header">分建筑 × 变量 MAPE</div>
                <el-table :data="summary.byBuilding" size="small" border stripe>
                  <el-table-column prop="buildingLabel" label="建筑" width="90" align="center" />
                  <el-table-column
                    v-for="m in metricColumns"
                    :key="m.key"
                    :label="m.label"
                    min-width="110"
                    align="center"
                  >
                    <template slot-scope="{ row }">
                      {{ formatMape(row.metrics[m.key] && row.metrics[m.key].mape) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="建筑均值" width="100" align="center">
                    <template slot-scope="{ row }">{{ formatMape(row.overall) }}</template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>
            <el-col :span="10">
              <el-card shadow="never" class="panel-card">
                <div slot="header" class="panel-header">变量 MAPE 柱状图</div>
                <div ref="barChart" class="chart-box" />
              </el-card>
            </el-col>
          </el-row>

          <el-card
            v-if="selectedSimulationsSorted.length > 1"
            shadow="never"
            class="panel-card mt-16"
          >
            <div slot="header" class="panel-header">多分组对比（当前筛选口径）</div>
            <el-table :data="comparisonRows" size="small" border stripe>
              <el-table-column prop="sim" label="分组" min-width="160" />
              <el-table-column label="综合" width="100" align="center">
                <template slot-scope="{ row }">{{ formatMape(row.overall) }}</template>
              </el-table-column>
              <el-table-column
                v-for="m in metricColumns"
                :key="'cmp-' + m.key"
                :label="m.label"
                min-width="100"
                align="center"
              >
                <template slot-scope="{ row }">
                  {{ formatMape(row.metrics[m.key]) }}
                </template>
              </el-table-column>
              <el-table-column label="样本行" width="90" align="center" prop="sampleCount" />
            </el-table>
          </el-card>

          <p class="formula-hint">
            MAPE = mean(|y − ŷ| / max(|y|, ε)) × 100%，由 trace 中逐步
            <code>abs_pct_error_*</code> 取平均。光伏夜间真实值接近 0 时单步误差可能偏大，属常见现象。
          </p>
        </template>
      </div>
    </template>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import axios from 'axios'
import SelectSimulationModal from '@/components/shared/SelectSimulationModal.vue'
import { parseChescaTraceCsv } from '@/utils/chescaTraceParse'
import {
  TRACE_METRICS,
  buildMapeSummary,
  buildingLabel,
  formatMape
} from '@/utils/mapeSummary'

export default {
  name: 'ForecastMape',
  components: { SelectSimulationModal },
  data() {
    return {
      loadingList: false,
      loadingDetail: false,
      showSelect: false,
      simulationFolders: [],
      simulationMeta: {},
      selectedSimulations: [],
      parsedTrace: {},
      activeTab: '',
      selectedEpisode: null,
      selectedBuilding: null,
      chart: null,
      metricColumns: TRACE_METRICS
    }
  },
  computed: {
    selectedSimulationsSorted() {
      return [...this.selectedSimulations].sort()
    },
    activeSim() {
      return this.activeTab
    },
    hasTrace() {
      const rows = this.parsedTrace[this.activeSim]
      return !!(rows && rows.length)
    },
    summary() {
      const rows = this.parsedTrace[this.activeSim]
      if (!rows || !rows.length) return null
      return buildMapeSummary(rows, {
        episode: this.selectedEpisode,
        building: this.selectedBuilding
      })
    },
    comparisonRows() {
      return this.selectedSimulationsSorted.map((sim) => {
        const rows = this.parsedTrace[sim] || []
        const s = buildMapeSummary(rows, {
          episode: this.selectedEpisode,
          building: this.selectedBuilding
        })
        const metrics = {}
        s.metrics.forEach((m) => {
          metrics[m.key] = m.mape
        })
        return {
          sim,
          overall: s.overall,
          metrics,
          sampleCount: s.sampleCount
        }
      })
    }
  },
  watch: {
    summary: {
      handler() {
        this.$nextTick(() => this.renderChart())
      },
      deep: true
    },
    activeTab() {
      this.selectedEpisode = null
      this.selectedBuilding = null
      this.$nextTick(() => this.renderChart())
    }
  },
  mounted() {
    this.loadShowSimulations()
    window.addEventListener('resize', this.onResize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.onResize)
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    formatMape,
    buildingLabel,

    isApiSuccess(response) {
      return response && response.data && Number(response.data.code) === 0
    },

    async loadShowSimulations() {
      this.loadingList = true
      try {
        const response = await axios.get('/api/web/basedata/getDashboardSimulations')
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '加载展示数据失败')
          return
        }
        const list = response.data.data || []
        this.simulationMeta = {}
        this.simulationFolders = list.map((item) => {
          this.simulationMeta[item.groupName] = {
            taskId: item.taskId,
            pyId: item.pyId
          }
          return item.groupName
        })
        this.parsedTrace = {}
        this.selectedSimulations = []
        this.activeTab = ''
        if (!this.simulationFolders.length) {
          this.$message.warning('暂无展示数据：请先在代码编辑器「记录」页将执行完成的记录设为【展示】')
        } else {
          this.$message.success(`已加载 ${this.simulationFolders.length} 个展示分组`)
          this.showSelect = true
        }
      } catch (error) {
        console.error(error)
        this.$message.error('加载展示数据失败')
      } finally {
        this.loadingList = false
      }
    },

    async loadSimulationDetail(groupName) {
      const meta = this.simulationMeta[groupName]
      if (!meta || !meta.taskId) return null
      const response = await axios.get('/api/web/basedata/getDashboardSimulationDetail', {
        params: { taskId: meta.taskId }
      })
      if (!this.isApiSuccess(response) || !response.data.data) {
        throw new Error(response.data.message || '加载仿真详情失败')
      }
      return response.data.data
    },

    async onSimulationsSelected(list) {
      this.selectedSimulations = list
      this.activeTab = [...list].sort()[0]
      this.selectedEpisode = null
      this.selectedBuilding = null
      this.loadingDetail = true
      const loading = this.$loading({
        lock: true,
        text: '正在加载 trace 数据…',
        spinner: 'el-icon-loading'
      })
      try {
        for (const sim of list) {
          if (this.parsedTrace[sim]) continue
          const detail = await this.loadSimulationDetail(sim)
          const rows = parseChescaTraceCsv(detail && detail.chescaTraceCsv)
          this.$set(this.parsedTrace, sim, rows)
          if (!rows.length) {
            this.$message.warning(`${sim}：未找到 chesca_trace.csv`)
          }
        }
      } catch (error) {
        console.error(error)
        this.$message.error(error.message || '加载仿真详情失败')
      } finally {
        loading.close()
        this.loadingDetail = false
        this.$nextTick(() => this.renderChart())
      }
    },

    renderChart() {
      if (!this.$refs.barChart || !this.summary) {
        return
      }
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.barChart)
      }
      const metrics = this.summary.metrics
      this.chart.setOption({
        tooltip: {
          trigger: 'axis',
          formatter: (params) => {
            const p = params[0]
            const m = metrics[p.dataIndex]
            const n = m ? m.count : 0
            return `${p.name}<br/>MAPE: ${formatMape(p.value)}<br/>样本: ${n}`
          }
        },
        grid: { left: 48, right: 16, top: 32, bottom: 40 },
        xAxis: {
          type: 'category',
          data: metrics.map((m) => m.label),
          axisLabel: { interval: 0, rotate: 20 }
        },
        yAxis: {
          type: 'value',
          name: 'MAPE (%)',
          min: 0
        },
        series: [
          {
            type: 'bar',
            barMaxWidth: 48,
            data: metrics.map((m) => (m.mape == null ? null : Number(m.mape.toFixed(2)))),
            itemStyle: {
              color: (params) => {
                const colors = {
                  solar: '#91cc75',
                  load: '#5470c6',
                  dhw: '#fac858',
                  outdoor_temp: '#ee6666'
                }
                const key = metrics[params.dataIndex] && metrics[params.dataIndex].key
                return colors[key] || '#5470c6'
              }
            },
            label: {
              show: true,
              position: 'top',
              formatter: (p) => (p.value == null ? '' : `${p.value}%`)
            }
          }
        ]
      })
    },

    onResize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>

<style scoped>
.forecast-mape-page {
  padding: 20px 24px 32px;
  min-height: 100%;
  background: linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: #1f2d3d;
}

.page-desc {
  margin: 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.page-desc code {
  padding: 1px 4px;
  background: #e8edf5;
  border-radius: 3px;
  font-size: 12px;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.empty-block {
  margin-top: 80px;
}

.sim-tabs {
  margin-bottom: 16px;
}

.content {
  min-height: 200px;
}

.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.filter-label {
  font-size: 13px;
  color: #606266;
}

.filter-ctrl {
  width: 140px;
}

.sample-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.card-row {
  margin-bottom: 4px;
}

.mape-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
  border-top: 3px solid #5470c6;
}

.mape-card-overall {
  border-top-color: #303133;
}

.mape-solar {
  border-top-color: #91cc75;
}

.mape-load {
  border-top-color: #5470c6;
}

.mape-dhw {
  border-top-color: #fac858;
}

.mape-outdoor_temp {
  border-top-color: #ee6666;
}

.mape-card-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.mape-card-value {
  font-size: 26px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.mape-card-sub {
  margin-top: 4px;
  font-size: 11px;
  color: #c0c4cc;
}

.panel-card {
  border: 1px solid #e4e7ed;
}

.panel-header {
  font-weight: 600;
  color: #303133;
}

.chart-box {
  height: 320px;
  width: 100%;
}

.mt-16 {
  margin-top: 16px;
}

.mb-16 {
  margin-bottom: 16px;
}

.formula-hint {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

.formula-hint code {
  padding: 1px 4px;
  background: #e8edf5;
  border-radius: 3px;
}
</style>
