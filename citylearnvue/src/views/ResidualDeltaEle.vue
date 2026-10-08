<template>
  <div class="residual-delta-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">残差 ΔELE 时序</h2>
        <p class="page-desc">
          展示 ResMARL 对电池动作的修正量
          <code>residual_delta_ele</code>（公式：
          <code>a_final = clip(a_base + α · Δa)</code>）。
          数据来自任务目录 <code>chesca_trace.csv</code>。
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
      description="请先加载并选择带有 chesca_trace.csv 的 CHESCA / ResMARL 仿真分组"
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
          description="请使用 CHESCA.py 重新运行后再加载。"
          class="mb-16"
        />

        <el-alert
          v-else-if="chartData && !chartData.resmarlHint.enabled"
          type="info"
          :closable="false"
          show-icon
          title="本组仿真未启用 ResMARL"
          description="ΔELE 多为 0。若需看残差曲线，请在 ResMARL 配置页启用并加载策略后重跑仿真。"
          class="mb-16"
        />

        <template v-if="chartData">
          <div class="filters">
            <span class="filter-label">Episode</span>
            <el-select v-model="selectedEpisode" size="small" class="filter-ctrl" clearable placeholder="全部">
              <el-option
                v-for="ep in (fullSeriesMeta && fullSeriesMeta.episodes) || []"
                :key="ep"
                :label="`Episode ${ep}`"
                :value="ep"
              />
            </el-select>
            <span class="filter-label">建筑</span>
            <el-select
              v-model="selectedBuildings"
              size="small"
              class="filter-ctrl-wide"
              multiple
              collapse-tags
              placeholder="全部建筑"
            >
              <el-option
                v-for="b in (fullSeriesMeta && fullSeriesMeta.buildings) || []"
                :key="b"
                :label="buildingLabel(b)"
                :value="b"
              />
            </el-select>
            <el-checkbox v-model="showBase" size="small">叠加 base ELE</el-checkbox>
            <el-checkbox v-model="showFinal" size="small">叠加 final ELE</el-checkbox>
            <el-tag v-if="chartData.resmarlHint.enabled" size="mini" type="warning">
              ResMARL α={{ formatAlpha(chartData.resmarlHint.alpha) }}
            </el-tag>
          </div>

          <div v-if="stepRangeMax > 0" class="step-slider">
            <span class="filter-label">步数范围</span>
            <el-slider
              v-model="stepRange"
              range
              :min="0"
              :max="stepRangeMax"
              :format-tooltip="(v) => `step ${v}`"
            />
          </div>

          <el-row :gutter="16" class="card-row">
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-label">mean |ΔELE|</div>
                <div class="stat-value">{{ formatDelta(chartData.stats.meanAbs) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-label">max |ΔELE|</div>
                <div class="stat-value">{{ formatDelta(chartData.stats.maxAbs) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-label">残差应用率</div>
                <div class="stat-value">{{ formatPct(chartData.stats.appliedRate) }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-label">有效点数</div>
                <div class="stat-value">{{ chartData.stats.n }}</div>
              </div>
            </el-col>
          </el-row>

          <el-card shadow="never" class="panel-card">
            <div slot="header" class="panel-header">ΔELE 折线图</div>
            <div ref="deltaChart" class="chart-box" />
            <p class="chart-hint">
              实线为各建筑残差修正量 ΔELE；可选叠加虚线 base / 点线 final。
              实际施加修正约为 α · ΔELE（mask 允许时）。
            </p>
          </el-card>

          <el-card
            v-if="selectedSimulationsSorted.length > 1"
            shadow="never"
            class="panel-card mt-16"
          >
            <div slot="header" class="panel-header">多分组 · mean |ΔELE| 对比</div>
            <el-table :data="comparisonRows" size="small" border stripe>
              <el-table-column prop="sim" label="分组" min-width="160" />
              <el-table-column label="ResMARL" width="120" align="center">
                <template slot-scope="{ row }">
                  <el-tag :type="row.enabled ? 'warning' : 'info'" size="mini">
                    {{ row.enabled ? `α=${formatAlpha(row.alpha)}` : '关闭' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="mean |ΔELE|" width="120" align="center">
                <template slot-scope="{ row }">{{ formatDelta(row.meanAbs) }}</template>
              </el-table-column>
              <el-table-column label="max |ΔELE|" width="120" align="center">
                <template slot-scope="{ row }">{{ formatDelta(row.maxAbs) }}</template>
              </el-table-column>
              <el-table-column label="应用率" width="100" align="center">
                <template slot-scope="{ row }">{{ formatPct(row.appliedRate) }}</template>
              </el-table-column>
              <el-table-column prop="n" label="点数" width="80" align="center" />
            </el-table>
          </el-card>
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
  buildResidualEleSeries,
  buildingLabel,
  formatDelta,
  formatPct
} from '@/utils/residualDelta'

export default {
  name: 'ResidualDeltaEle',
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
      selectedBuildings: [],
      showBase: false,
      showFinal: false,
      stepRange: [0, 0],
      stepRangeMax: 0,
      chart: null
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
    chartData() {
      const rows = this.parsedTrace[this.activeSim]
      if (!rows || !rows.length) return null
      return buildResidualEleSeries(rows, {
        episode: this.selectedEpisode,
        buildings: this.selectedBuildings.length ? this.selectedBuildings : null,
        showBase: this.showBase,
        showFinal: this.showFinal,
        stepRange: this.stepRangeMax > 0 ? this.stepRange : null
      })
    },
    fullSeriesMeta() {
      const rows = this.parsedTrace[this.activeSim]
      if (!rows || !rows.length) return null
      return buildResidualEleSeries(rows, {
        episode: this.selectedEpisode,
        buildings: null,
        showBase: false,
        showFinal: false,
        stepRange: null
      })
    },
    comparisonRows() {
      return this.selectedSimulationsSorted.map((sim) => {
        const rows = this.parsedTrace[sim] || []
        const data = buildResidualEleSeries(rows, {
          episode: this.selectedEpisode,
          buildings: this.selectedBuildings.length ? this.selectedBuildings : null,
          stepRange: null
        })
        return {
          sim,
          enabled: data.resmarlHint.enabled,
          alpha: data.resmarlHint.alpha,
          meanAbs: data.stats.meanAbs,
          maxAbs: data.stats.maxAbs,
          appliedRate: data.stats.appliedRate,
          n: data.stats.n
        }
      })
    }
  },
  watch: {
    fullSeriesMeta: {
      handler(meta) {
        if (!meta || !meta.steps.length) {
          this.stepRangeMax = 0
          this.stepRange = [0, 0]
          return
        }
        const max = Math.max(...meta.steps)
        if (this.stepRangeMax !== max) {
          this.stepRangeMax = max
          this.stepRange = [0, max]
        }
      },
      immediate: true
    },
    chartData: {
      handler() {
        this.$nextTick(() => this.renderChart())
      },
      deep: true
    },
    activeTab() {
      this.selectedEpisode = null
      this.selectedBuildings = []
      this.showBase = false
      this.showFinal = false
      this.stepRangeMax = 0
      this.stepRange = [0, 0]
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
    formatDelta,
    formatPct,
    buildingLabel,
    formatAlpha(v) {
      if (v == null || !Number.isFinite(Number(v))) return '—'
      return Number(v).toFixed(2)
    },

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
      this.selectedBuildings = []
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
      if (!this.$refs.deltaChart || !this.chartData) return
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.deltaChart)
      }
      const { labels, series } = this.chartData
      if (!series.length) {
        this.chart.clear()
        return
      }
      this.chart.setOption(
        {
          title: {
            text: 'ResMARL 残差 ΔELE',
            left: 'center',
            textStyle: { fontSize: 14 }
          },
          tooltip: {
            trigger: 'axis',
            formatter: (params) => {
              if (!params || !params.length) return ''
              const idx = params[0].dataIndex
              let html = `${labels[idx] || params[0].axisValue}<br/>`
              params.forEach((p) => {
                const val =
                  p.value == null || Number.isNaN(p.value) ? '—' : Number(p.value).toFixed(4)
                html += `${p.marker}${p.seriesName}: ${val}<br/>`
              })
              return html
            }
          },
          legend: {
            type: 'scroll',
            bottom: 0,
            data: series.map((s) => s.name)
          },
          grid: { left: 56, right: 24, top: 48, bottom: 72, containLabel: true },
          xAxis: {
            type: 'category',
            name: '仿真步',
            data: labels,
            axisLabel: {
              fontSize: 10,
              interval: Math.max(0, Math.floor(labels.length / 24) - 1)
            }
          },
          yAxis: {
            type: 'value',
            name: '动作 / Δ',
            scale: true
          },
          dataZoom: [
            { type: 'inside', start: 0, end: 100 },
            { type: 'slider', start: 0, end: 100, height: 18, bottom: 36 }
          ],
          series: series.map((s) => ({
            name: s.name,
            type: 'line',
            showSymbol: labels.length <= 48,
            symbolSize: 4,
            data: s.data,
            itemStyle: { color: s.color },
            lineStyle: s.lineStyle || { width: 2, color: s.color }
          }))
        },
        true
      )
    },

    onResize() {
      if (this.chart) this.chart.resize()
    }
  }
}
</script>

<style scoped>
.residual-delta-page {
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
  gap: 10px;
  margin-bottom: 12px;
}

.filter-label {
  font-size: 13px;
  color: #606266;
}

.filter-ctrl {
  width: 140px;
}

.filter-ctrl-wide {
  min-width: 180px;
}

.step-slider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.step-slider .el-slider {
  flex: 1;
  margin: 0 12px;
}

.card-row {
  margin-bottom: 16px;
}

.stat-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px 16px;
  border-top: 3px solid #e6a23c;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  font-variant-numeric: tabular-nums;
}

.panel-card {
  border: 1px solid #e4e7ed;
}

.panel-header {
  font-weight: 600;
  color: #303133;
}

.chart-box {
  height: 420px;
  width: 100%;
}

.chart-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
}

.mt-16 {
  margin-top: 16px;
}

.mb-16 {
  margin-bottom: 16px;
}
</style>
