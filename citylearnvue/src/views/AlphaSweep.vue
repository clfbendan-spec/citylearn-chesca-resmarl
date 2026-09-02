<template>
  <div class="alpha-sweep-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">α–KPI 扫描曲线</h2>
        <p class="page-desc">
          读取 <code>ablation_resmarl.py --alpha-sweep</code> 入库的
          <code>registry/index.json</code>，绘制残差强度 α 与 District KPI 的关系曲线；
          虚线为纯 CHESCA 基线参考。
        </p>
      </div>
      <div class="header-actions">
        <el-button type="primary" icon="el-icon-refresh" :loading="loadingList" @click="loadRuns">
          刷新列表
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="mb-16"
      title="如何生成数据"
      description="cd citylearnpy → python ablation_resmarl.py --alpha-sweep 0,0.05,0.1,0.15,0.2 --policy checkpoints/resmarl_policy.pt --steps 720。已有消融结果可用 --register-existing ablation_results 入库。"
    />

    <el-empty
      v-if="!loadingList && !runs.length"
      description="暂无 α 扫描记录。请先运行 ablation_resmarl.py --alpha-sweep 或 --register-existing"
      class="empty-block"
    />

    <template v-else-if="runs.length">
      <div class="filters">
        <span class="filter-label">扫描批次</span>
        <el-select
          v-model="selectedRunId"
          size="small"
          class="run-select"
          filterable
          placeholder="选择 run"
          @change="onRunChange"
        >
          <el-option
            v-for="r in runs"
            :key="r.run_id"
            :label="runOptionLabel(r)"
            :value="r.run_id"
          />
        </el-select>
        <span class="filter-label">KPI</span>
        <el-select
          v-model="selectedKpis"
          size="small"
          class="kpi-select"
          multiple
          collapse-tags
          placeholder="选择 KPI"
        >
          <el-option v-for="k in availableKpis" :key="k" :label="k" :value="k" />
        </el-select>
      </div>

      <div v-loading="loadingDetail">
        <template v-if="detail">
          <el-row :gutter="12" class="meta-row">
            <el-col :span="6">
              <div class="meta-card">
                <div class="meta-label">步数</div>
                <div class="meta-value">{{ detail.episode_time_steps || '—' }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="meta-card">
                <div class="meta-label">α 点数</div>
                <div class="meta-value">{{ (detail.alphas || []).length }}</div>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="meta-card">
                <div class="meta-label">策略</div>
                <div class="meta-value meta-path" :title="detail.policy_path">
                  {{ shortPath(detail.policy_path) }}
                </div>
              </div>
            </el-col>
          </el-row>

          <el-card shadow="never" class="panel-card">
            <div slot="header" class="panel-header">α → KPI 曲线</div>
            <div ref="chart" class="chart-box" />
            <p class="chart-hint">横轴 residual_alpha；纵轴 District KPI。灰色虚线 = 纯 CHESCA 基线。</p>
          </el-card>

          <el-card shadow="never" class="panel-card mt-16">
            <div slot="header" class="panel-header">数值表</div>
            <el-table :data="tableRows" size="small" border stripe max-height="420">
              <el-table-column prop="label" label="方案" min-width="140" fixed />
              <el-table-column label="α" width="80" align="center">
                <template slot-scope="{ row }">
                  <span v-if="row.kind === 'baseline'">—</span>
                  <span v-else>{{ Number(row.residual_alpha).toFixed(2) }}</span>
                </template>
              </el-table-column>
              <el-table-column
                v-for="k in selectedKpis"
                :key="k"
                :label="k"
                min-width="120"
                align="center"
              >
                <template slot-scope="{ row }">{{ formatKpi(row[k]) }}</template>
              </el-table-column>
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
import {
  buildAlphaKpiSeries,
  buildAlphaTableRows,
  formatKpi
} from '@/utils/alphaSweepParse'

const COLORS = ['#5470c6', '#91cc75', '#ee6666', '#fac858', '#73c0de', '#3ba272', '#fc8452']

export default {
  name: 'AlphaSweep',
  data() {
    return {
      loadingList: false,
      loadingDetail: false,
      runs: [],
      selectedRunId: '',
      detail: null,
      selectedKpis: [],
      chart: null
    }
  },
  computed: {
    availableKpis() {
      if (!this.detail) return []
      return this.detail.kpi_names || this.detail.default_chart_kpis || []
    },
    tableRows() {
      if (!this.detail) return []
      return buildAlphaTableRows(this.detail, this.selectedKpis)
    }
  },
  watch: {
    selectedKpis() {
      this.$nextTick(() => this.renderChart())
    },
    detail() {
      this.$nextTick(() => this.renderChart())
    }
  },
  mounted() {
    this.loadRuns()
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
    formatKpi,
    isApiSuccess(response) {
      return response && response.data && Number(response.data.code) === 0
    },
    runOptionLabel(r) {
      const alphas = Array.isArray(r.alphas) ? r.alphas.join(',') : ''
      return `${r.run_id} · ${r.label || alphas}`
    },
    shortPath(p) {
      if (!p) return '—'
      const s = String(p).replace(/\\/g, '/')
      const parts = s.split('/')
      return parts.slice(-2).join('/') || s
    },
    async loadRuns() {
      this.loadingList = true
      try {
        const response = await axios.get('/api/web/basedata/getAlphaSweepRuns')
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '加载 α 扫描列表失败')
          return
        }
        this.runs = response.data.data || []
        if (!this.runs.length) {
          this.selectedRunId = ''
          this.detail = null
          return
        }
        if (!this.selectedRunId || !this.runs.some((r) => r.run_id === this.selectedRunId)) {
          this.selectedRunId = this.runs[0].run_id
        }
        await this.loadDetail(this.selectedRunId)
      } catch (e) {
        console.error(e)
        this.$message.error('加载 α 扫描列表失败（请确认 Java 已重启）')
      } finally {
        this.loadingList = false
      }
    },
    async onRunChange(runId) {
      await this.loadDetail(runId)
    },
    async loadDetail(runId) {
      if (!runId) return
      this.loadingDetail = true
      try {
        const response = await axios.get('/api/web/basedata/getAlphaSweepDetail', {
          params: { runId }
        })
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '加载详情失败')
          this.detail = null
          return
        }
        this.detail = response.data.data
        const defaults = this.detail.default_chart_kpis || []
        const all = this.detail.kpi_names || []
        this.selectedKpis = (defaults.length ? defaults : all.slice(0, 4)).filter((k) =>
          all.includes(k)
        )
        if (!this.selectedKpis.length && all.length) {
          this.selectedKpis = all.slice(0, 4)
        }
      } catch (e) {
        console.error(e)
        this.$message.error('加载 α 扫描详情失败')
        this.detail = null
      } finally {
        this.loadingDetail = false
      }
    },
    renderChart() {
      if (!this.$refs.chart || !this.detail || !this.selectedKpis.length) return
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.chart)
      }
      const { alphas, series } = buildAlphaKpiSeries(this.detail, this.selectedKpis)
      if (!alphas.length) {
        this.chart.clear()
        return
      }

      const echartsSeries = []
      series.forEach((s, idx) => {
        const color = COLORS[idx % COLORS.length]
        echartsSeries.push({
          name: s.name,
          type: 'line',
          data: s.data,
          showSymbol: true,
          symbolSize: 8,
          itemStyle: { color },
          lineStyle: { width: 2, color }
        })
        if (s.baseline != null) {
          echartsSeries.push({
            name: `${s.name} · CHESCA`,
            type: 'line',
            data: alphas.map(() => s.baseline),
            showSymbol: false,
            lineStyle: { type: 'dashed', width: 1.5, color, opacity: 0.55 },
            itemStyle: { color },
            tooltip: { show: true }
          })
        }
      })

      this.chart.setOption(
        {
          tooltip: {
            trigger: 'axis',
            formatter: (params) => {
              if (!params || !params.length) return ''
              const alpha = alphas[params[0].dataIndex]
              let html = `α = ${Number(alpha).toFixed(2)}<br/>`
              params.forEach((p) => {
                const val =
                  p.value == null || Number.isNaN(p.value) ? '—' : Number(p.value).toFixed(4)
                html += `${p.marker}${p.seriesName}: ${val}<br/>`
              })
              return html
            }
          },
          legend: { type: 'scroll', bottom: 0 },
          grid: { left: 56, right: 24, top: 40, bottom: 72, containLabel: true },
          xAxis: {
            type: 'category',
            name: 'α',
            data: alphas.map((a) => Number(a).toFixed(2))
          },
          yAxis: { type: 'value', name: 'KPI', scale: true },
          series: echartsSeries
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
.alpha-sweep-page {
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
  max-width: 760px;
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
.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.filter-label {
  font-size: 13px;
  color: #606266;
}
.run-select {
  min-width: 360px;
}
.kpi-select {
  min-width: 280px;
}
.meta-row {
  margin-bottom: 12px;
}
.meta-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 14px;
  border-top: 3px solid #5470c6;
  margin-bottom: 8px;
}
.meta-label {
  font-size: 12px;
  color: #909399;
}
.meta-value {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.meta-path {
  font-size: 13px;
  font-weight: 500;
  word-break: break-all;
}
.panel-card {
  border: 1px solid #e4e7ed;
}
.panel-header {
  font-weight: 600;
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
.empty-block {
  margin-top: 60px;
}
.mb-16 {
  margin-bottom: 16px;
}
.mt-16 {
  margin-top: 16px;
}
</style>
