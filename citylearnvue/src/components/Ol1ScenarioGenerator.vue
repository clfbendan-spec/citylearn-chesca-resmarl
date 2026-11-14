<template>
  <el-dialog title="生成模拟数据" :visible.sync="dialogVisible" width="900px" :close-on-click-modal="false" @closed="onClosed">
    <el-form label-position="top" size="small" class="generator-form">
      <el-form-item label="版本名称"><el-input v-model="name" maxlength="160" :disabled="busy" /></el-form-item>
      <el-form-item label="社区建筑">
        <el-checkbox-group v-model="selectedBuildings" :disabled="busy">
          <el-checkbox v-for="building in buildings" :key="building.id" :label="building.id">{{ building.name }}</el-checkbox>
        </el-checkbox-group>
        <el-empty v-if="!buildings.length" description="暂无社区建筑" :image-size="48" />
      </el-form-item>
      <el-form-item label="评估数据范围">
        <el-date-picker
          v-model="evaluationRange"
          type="datetimerange"
          :disabled="busy"
          :picker-options="{ disabledDate: disabledDate }"
          start-placeholder="开始时间（含）"
          end-placeholder="最后一条数据（含）"
          format="yyyy-MM-dd HH:mm"
          value-format="yyyy-MM-dd HH:mm:ss"
          :default-time="['00:00:00', '23:00:00']"
          size="small"
          class="evaluation-range"
        />
      </el-form-item>
    </el-form>

    <el-alert v-if="preview && !preview.ready" :title="preview.blocker" type="error" :closable="false" />
    <template v-if="preview && preview.ready">
      <el-alert :title="'输入预览 · ' + preview.buildingCount + ' 栋 · 总运行 ' + preview.timeSteps + ' 小时 · 计分 ' + preview.scoreSteps + ' 小时'" type="success" :closable="false" />
      <el-alert v-for="(warning, i) in previewWarnings" :key="i" :title="warningText(warning)" type="warning" :closable="false" class="generator-warning" />
      <div class="chart-controls">
        <el-select v-model="chartBuilding" size="small" @change="renderChart">
          <el-option v-for="key in Object.keys(preview.curves || {})" :key="key" :label="key" :value="key" />
        </el-select>
      </div>
      <div ref="curveChart" class="curve-chart" />
    </template>

    <el-divider v-if="tasks.length" content-position="left">生成任务</el-divider>
    <el-table v-if="tasks.length" :data="tasks" size="mini" max-height="180">
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column prop="stage" label="阶段" width="130" />
      <el-table-column label="进度" min-width="150"><template slot-scope="s">{{ s.row.completed || 0 }} / {{ s.row.total || 0 }}</template></el-table-column>
      <el-table-column prop="error" label="错误" min-width="200" show-overflow-tooltip />
      <el-table-column label="" width="90"><template slot-scope="s"><el-button v-if="['queued','running'].includes(s.row.status)" type="text" class="danger" @click="cancel(s.row)">取消</el-button></template></el-table-column>
    </el-table>

    <div slot="footer">
      <el-button @click="dialogVisible = false">关闭</el-button>
      <el-button type="primary" icon="el-icon-s-operation" :loading="busy" :disabled="!selectedBuildings.length || !canWrite || tasks.some(task => ['queued','running'].includes(task.status))" @click="start">生成并验证</el-button>
    </div>
  </el-dialog>
</template>

<script>
import * as echarts from 'echarts'
import * as api from '../api/community'
import { themeColor } from '../utils/theme'
import { disabledOl1Date, freshOl1Range, ol1RangeConfiguration, ol1TimeAtStep } from '../utils/ol1TimeRange'

const warningTranslations = {
  'Prototype-derived sensitivity scenario; not a newly calibrated building.': '模拟数据基于原始建筑模型生成，用于分析配置变化的影响，未针对新建筑重新校准。'
}
const hiddenWarnings = new Set([
  'History is retained; downstream evaluation must apply the declared score window.',
  'Raw full-window startup and warmed-window scores must not be mixed.',
  '已保留评估开始前的历史数据，后续评估应仅统计所选评估时间范围内的结果。',
  '直接从初始状态开始评估与先运行历史数据再评估，得到的评分口径不同，不应混合比较。'
])

export default {
  name: 'Ol1ScenarioGenerator',
  props: { visible: Boolean, communityId: [String, Number], buildings: { type: Array, default: () => [] }, canWrite: Boolean },
  data: () => ({ name: '', evaluationRange: freshOl1Range(), selectedBuildings: [], preview: null, previewing: false, starting: false, tasks: [], notifiedTasks: new Set(), timer: null, chart: null, chartBuilding: '', session: 0, polling: false }),
  computed: {
    busy() { return this.previewing || this.starting },
    previewWarnings() { return ((this.preview && this.preview.warnings) || []).filter(warning => !hiddenWarnings.has(warning)) },
    dialogVisible: { get() { return this.visible }, set(value) { this.$emit('update:visible', value) } }
  },
  watch: {
    visible(value) {
      this.session++
      if (value) {
        this.name = ''; this.evaluationRange = freshOl1Range(); this.selectedBuildings = this.buildings.map(building => building.id)
        this.preview = null; this.tasks = []; this.notifiedTasks = new Set()
      } else this.stopPolling()
    },
    evaluationRange() { this.preview = null },
    selectedBuildings() { this.preview = null },
    'preview.curves'() { this.$nextTick(this.renderChart) }
  },
  beforeDestroy() { this.stopPolling(); if (this.chart) this.chart.dispose() },
  methods: {
    warningText(warning) { return warningTranslations[warning] || warning },
    disabledDate: disabledOl1Date,
    requestConfig() {
      return Object.assign({}, ol1RangeConfiguration(this.evaluationRange), { buildingIds: this.selectedBuildings.slice() })
    },
    async makePreview() {
      const session = this.session
      this.previewing = true
      try {
        const result = await api.previewOl1Scenario(this.communityId, this.requestConfig())
        if (!this.visible || session !== this.session) return false
        if (result.ok) { this.preview = result.data; this.chartBuilding = Object.keys(result.data.curves || {})[0] || '' }
        await this.$nextTick()
        this.renderChart()
        return result.ok && result.data.ready
      } finally { this.previewing = false }
    },
    async start() {
      if (this.busy) return
      if (!this.name.trim()) return this.$message.warning('请填写版本名称')
      if (!this.selectedBuildings.length) return this.$message.warning('请选择社区建筑')
      try { this.requestConfig() } catch (error) { return this.$message.warning(error.message) }
      const session = this.session
      this.starting = true
      try {
        if (!await this.makePreview() || !this.visible || session !== this.session) return
        const result = await api.startOl1Scenario(this.communityId, { name: this.name, configuration: this.requestConfig() })
        if (!this.visible || session !== this.session) return
        if (result.ok) { this.tasks.unshift(result.data); this.$message.success('模拟数据生成任务已提交'); this.startPolling() }
      } finally { this.starting = false }
    },
    async loadTasks() {
      if (this.polling || !this.visible) return
      this.polling = true
      const community = this.communityId
      const session = this.session
      try {
        const results = await Promise.all(this.tasks.map(task => api.getOl1ScenarioTask(community, task.id)))
        if (this.visible && session === this.session && String(community) === String(this.communityId)) {
          this.tasks = this.tasks.map((task, index) => results[index].ok ? results[index].data : task)
          this.tasks.filter(task => task.status === 'succeeded' && task.result && !this.notifiedTasks.has(task.id)).forEach(task => {
            this.notifiedTasks.add(task.id)
            this.$emit('published', task.result)
            this.$message.success('模拟数据已验证并发布')
          })
        }
        if (this.tasks.some(task => ['queued', 'running'].includes(task.status))) this.startPolling()
        else this.stopPolling()
      } finally { this.polling = false }
    },
    startPolling() {
      if (this.timer) return
      this.timer = setInterval(() => this.loadTasks(), 1500)
    },
    stopPolling() { if (this.timer) { clearInterval(this.timer); this.timer = null } },
    async cancel(task) {
      const result = await api.cancelOl1ScenarioTask(this.communityId, task.id)
      if (result.ok) { await this.loadTasks(); this.$message.success('已取消生成任务') }
    },
    renderChart() {
      if (!this.preview || !this.$refs.curveChart) return
      if (this.chart && this.chart.getDom() !== this.$refs.curveChart) { this.chart.dispose(); this.chart = null }
      if (!this.chart) this.chart = echarts.init(this.$refs.curveChart)
      const rows = this.preview.curves[this.chartBuilding] || []
      this.chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['原始普通用电', '模拟普通用电', '原始光伏', '模拟光伏'] },
        grid: { left: 56, right: 20, top: 40, bottom: 34 },
        xAxis: { type: 'category', data: rows.map(row => ol1TimeAtStep(row.step).slice(5, 16)) },
        yAxis: { type: 'value', name: 'kWh / 小时' },
        series: [
          { name: '原始普通用电', type: 'line', itemStyle: { color: themeColor('secondary-text-color') }, lineStyle: { type: 'dashed' }, showSymbol: false, data: rows.map(row => row.sourceLoad) },
          { name: '模拟普通用电', type: 'line', itemStyle: { color: themeColor('secondary-text-color') }, showSymbol: false, data: rows.map(row => row.load) },
          { name: '原始光伏', type: 'line', itemStyle: { color: themeColor('energy-solar-color') }, lineStyle: { type: 'dashed' }, showSymbol: false, data: rows.map(row => row.sourcePv) },
          { name: '模拟光伏', type: 'line', itemStyle: { color: themeColor('energy-solar-color') }, showSymbol: false, data: rows.map(row => row.pv) }
        ]
      }, true)
      this.chart.resize()
    },
    onClosed() { this.stopPolling(); if (this.chart) { this.chart.dispose(); this.chart = null } }
  }
}
</script>

<style scoped>
.generator-form{margin-bottom:14px}.generator-form /deep/ .el-select{width:100%}.generator-form .evaluation-range{width:100%;max-width:460px}.chart-controls{display:flex;justify-content:flex-end;margin:12px 0 4px}.curve-chart{height:280px;width:100%}.generator-warning{margin-top:8px}.danger{color:var(--error-color)}@media(max-width:680px){.curve-chart{height:230px}}
</style>
