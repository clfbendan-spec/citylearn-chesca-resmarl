<template>
  <el-dialog title="社区初步评估" :visible="visible" width="1000px" class="assessment-dialog" :close-on-click-modal="false" @update:visible="$emit('update:visible', $event)" @closed="stopPolling">
    <div class="assessment-toolbar"><div><h3>{{ release.name }}</h3></div><div class="toolbar"><el-button icon="el-icon-refresh" size="small" :loading="loading" @click="loadRuns">刷新</el-button><el-button v-if="canWrite" type="primary" icon="el-icon-caret-right" size="small" :loading="starting" :disabled="hasActiveRun" @click="start">开始评估</el-button></div></div>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <el-table :data="runs" size="small" highlight-current-row @current-change="selectRun" class="assessment-runs" max-height="220" v-loading="loading">
      <el-table-column label="状态" width="100"><template slot-scope="s"><el-tag :type="statusType(s.row.status)" size="small">{{ statusName(s.row.status) }}</el-tag></template></el-table-column>
      <el-table-column label="算法" width="120"><template slot-scope="s">{{ s.row.config && s.row.config.algorithm || 'NoControl / 诊断' }}</template></el-table-column>
      <el-table-column label="任务编号" min-width="245" show-overflow-tooltip><template slot-scope="s">{{ s.row.config && s.row.config.taskId || '—' }}</template></el-table-column>
      <el-table-column label="创建时间" min-width="170"><template slot-scope="s">{{ time(s.row.createTime) }}</template></el-table-column>
      <el-table-column label="操作" width="90"><template slot-scope="s"><el-button type="text" @click="selectRun(s.row)">查看结果</el-button></template></el-table-column>
    </el-table>
    <el-empty v-if="!runs.length && !loading" description="暂无评估记录" :image-size="64" />
    <section v-if="current.id" class="assessment-current">
      <div class="assessment-toolbar"><h3>{{ current.config && current.config.algorithm ? current.config.algorithm + ' 评估结果' : (baselineReady ? 'NoControl 基线结果' : statusName(current.status)) }}</h3><div class="toolbar"><el-button v-if="canWrite && isActive(current.status)" size="small" type="danger" plain icon="el-icon-close" :loading="cancelling" @click="cancel">取消评估</el-button><el-button v-if="result && successful(current.status)" size="small" icon="el-icon-download" @click="downloadReport">下载 Markdown 报告</el-button></div></div>
      <el-progress v-if="isActive(current.status)" :percentage="percentage" :status="current.status === 'CANCEL_REQUESTED' ? 'warning' : undefined" />
      <p v-if="progress.message" class="muted">{{ progress.message }}</p>
      <el-alert v-if="current.error" :title="current.error" type="error" :closable="false" />
      <template v-if="result">
        <section v-if="baselineReady" class="baseline-result">
          <el-table :data="baselineKpiRows" size="small" class="assessment-results" stripe>
            <el-table-column prop="label" label="指标" fixed min-width="240" />
            <el-table-column v-for="column in baselineKpiColumns" :key="column" :label="column === 'District' ? '社区汇总' : formatColumnName(column)" min-width="130" align="right"><template slot-scope="s">{{ metricNumber(s.row[column], s.row.percent) }}</template></el-table-column>
          </el-table>
          <el-empty v-if="!baselineKpiRows.length" description="NoControl 已完成，但没有可展示的官方指标" :image-size="56" />
          <section class="optimization-result">
            <div class="optimization-heading"><h4>后续优化空间</h4></div>
            <el-table v-if="optimizationRows.length" :data="optimizationRows" size="small" class="optimization-table" stripe>
              <el-table-column label="建筑" width="100"><template slot-scope="s">{{ formatColumnName(s.row.building) }}</template></el-table-column>
              <el-table-column prop="direction" label="可优化的地方" min-width="145" />
              <el-table-column label="参考数值" min-width="230">
                <template slot-scope="s">
                  <div v-for="item in s.row.metrics" :key="item.label" class="opportunity-metric">
                    <span class="opportunity-label">{{ item.label }}</span>
                    <el-tooltip :content="item.explanation" placement="top" :open-delay="200">
                      <span class="opportunity-number" tabindex="0"><strong>{{ item.value }}</strong><span class="opportunity-unit">{{ item.unit }}</span><i class="el-icon-info" aria-label="数值说明" /></span>
                    </el-tooltip>
                  </div>
                  <span v-if="!s.row.metrics.length" class="muted">{{ s.row.emptyText }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="原因与建议" min-width="280" />
            </el-table>
            <el-empty v-else description="此评估记录未保存优化空间筛查，请重新运行 NoControl 评估" :image-size="48" />
          </section>
        </section>
      </template>
    </section>
    <div slot="footer"><el-button @click="$emit('update:visible', false)">关闭</el-button></div>
  </el-dialog>
</template>

<script>
import * as api from '../api/community'
import { formatColumnName } from '../utils/kpiLabels'
import { assessmentMatrix, assessmentOpportunities } from '../utils/assessmentMetrics'
const active = ['QUEUED', 'PENDING', 'RUNNING', 'CANCEL_REQUESTED', 'CANCELLING']
export default {
  name: 'CommunityAssessmentDialog',
  props: { visible: Boolean, communityId: { type: [Number, String], default: null }, release: { type: Object, default: () => ({}) }, canWrite: Boolean },
  data: () => ({ runs: [], current: {}, loading: false, starting: false, cancelling: false, loadError: '', pollTimer: null, epoch: 0, detailRequest: 0 }),
  computed: {
    contextKey() { return JSON.stringify([this.visible, this.communityId, this.release.id]) },
    hasActiveRun() { return this.runs.some(run => this.isActive(run.status)) },
    result() { return this.current.result || null },
    baseline() { return this.result && this.result.baseline || null },
    baselineReady() { return !!(this.baseline && this.baseline.status === 'succeeded' && this.baseline.metrics) },
    baselineMetrics() { return this.baselineReady ? this.baseline.metrics : {} },
    baselineMatrix() { return assessmentMatrix(this.baseline) },
    baselineKpiColumns() { return this.baselineMatrix.columns },
    baselineKpiRows() { return this.baselineMatrix.rows },
    optimizationRows() { return assessmentOpportunities(this.baseline) },
    progress() { const value = this.current.progress; return value && typeof value === 'object' ? value : {} },
    percentage() { const progress = this.progress; if (typeof this.current.progress === 'number') return Math.min(100, Math.max(0, this.current.progress)); return progress.total > 0 ? Math.min(100, Math.round(100 * progress.completed / progress.total)) : 0 }
  },
  watch: { contextKey: { immediate: true, handler() { this.stopPolling(); this.epoch++; this.detailRequest++; this.runs = []; this.current = {}; this.loading = false; this.starting = false; this.cancelling = false; this.loadError = ''; if (this.visible && this.communityId && this.release.id) this.loadRuns() } } },
  beforeDestroy() { this.epoch++; this.stopPolling() },
  methods: {
    isActive(status) { return active.includes(String(status || '').toUpperCase()) },
    successful(status) { return ['SUCCEEDED', 'SUCCESS', 'COMPLETED'].includes(String(status || '').toUpperCase()) },
    statusName(status) { const key = String(status || '').toUpperCase(); return ({ QUEUED: '排队中', PENDING: '等待中', RUNNING: '评估中', SUCCEEDED: '已完成', SUCCESS: '已完成', COMPLETED: '已完成', FAILED: '失败', CANCELLED: '已取消', CANCELED: '已取消', CANCEL_REQUESTED: '取消中', CANCELLING: '取消中', SKIPPED: '已跳过', OK: '已完成' })[key] || status || '—' },
    statusType(status) { return this.successful(status) ? 'success' : this.isActive(status) ? 'warning' : String(status).toUpperCase() === 'FAILED' ? 'danger' : 'info' },
    time(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' },
    metricNumber(value, percent) { return typeof value === 'number' && Number.isFinite(value) ? (percent ? (value * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 }) + '%' : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })) : '—' },
    formatColumnName(key) { return formatColumnName(key) },
    stopPolling() { clearTimeout(this.pollTimer); this.pollTimer = null },
    schedule() { this.stopPolling(); if (this.visible && this.hasActiveRun) this.pollTimer = setTimeout(() => this.loadRuns(false), 2500) },
    async loadRuns(showLoading = true) { const epoch = this.epoch, id = this.communityId, release = this.release.id; if (!this.visible || !release) return; if (showLoading) this.loading = true; try { const result = await api.listAssessments(id, release); if (epoch !== this.epoch || !this.visible) return; if (!result.ok) { this.loadError = result.message; return } this.runs = (result.data || []).filter(run => String(run.config && run.config.algorithm || '').toUpperCase() !== 'CHESCA'); this.loadError = ''; const selected = this.runs.find(run => run.id === this.current.id) || this.runs[0]; if (selected) await this.loadDetail(selected.id, epoch); else this.current = {}; this.schedule() } finally { if (epoch === this.epoch) this.loading = false } },
    async loadDetail(runId, epoch = this.epoch) { const request = ++this.detailRequest; const result = await api.getAssessment(this.communityId, this.release.id, runId); if (epoch !== this.epoch || request !== this.detailRequest || !this.visible) return; if (result.ok) this.current = result.data; else this.loadError = result.message },
    async selectRun(run) { if (!run) return; const epoch = this.epoch; this.current = run; await this.loadDetail(run.id, epoch) },
    async start() { const epoch = this.epoch, id = this.communityId, release = this.release.id; this.starting = true; try { const result = await api.startAssessment(id, release); if (!result.ok || epoch !== this.epoch || !this.visible) return; this.current = (result.data.runs || [])[0] || {}; await this.loadRuns(); this.$message.success('已建立 NOCONTROL 评估任务') } finally { if (epoch === this.epoch) this.starting = false } },
    async cancel() { const epoch = this.epoch, id = this.communityId, release = this.release.id, run = this.current.id; this.cancelling = true; try { const result = await api.cancelAssessment(id, release, run); if (result.ok && epoch === this.epoch && this.visible) await this.loadRuns() } finally { if (epoch === this.epoch) this.cancelling = false } },
    downloadReport() { window.location.assign(`/api/web/communities/${this.communityId}/datasets/${this.release.id}/assessments/${this.current.id}/report`) }
  }
}
</script>

<style scoped>
.opportunity-metric+.opportunity-metric{margin-top:var(--space-2)}
.opportunity-label{display:block;color:var(--secondary-text-color);font-size:12px;line-height:1.5}
.opportunity-number{display:inline-flex;align-items:baseline;gap:6px;max-width:100%;flex-wrap:wrap}
.opportunity-number strong{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--primary-text-color)}
.opportunity-unit,.opportunity-number i{font-size:12px;color:var(--secondary-text-color)}
.opportunity-number i{cursor:help}
.assessment-dialog{color:var(--primary-text-color);font-family:var(--ha-font-family)}.assessment-dialog /deep/ .el-dialog{max-width:calc(100% - 24px);border-radius:var(--ha-card-border-radius)}.assessment-toolbar,.toolbar{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap}.assessment-toolbar{margin-bottom:var(--space-4)}h3{font-size:16px;font-weight:500;line-height:1.35;margin:var(--space-5) 0 var(--space-3)}.assessment-toolbar h3{margin:0 0 var(--space-1)}.muted{color:var(--secondary-text-color);font-size:12px;line-height:1.4}.assessment-runs{margin-top:var(--space-4)}.assessment-current{margin-top:var(--space-5);padding-top:var(--space-5);border-top:1px solid var(--divider-color)}.baseline-result{margin-top:var(--space-4)}.optimization-result{margin-top:var(--space-5);padding-top:var(--space-4);border-top:1px solid var(--divider-color)}.optimization-heading{display:flex;align-items:baseline;gap:var(--space-3);flex-wrap:wrap;margin-bottom:var(--space-3)}h4{font-size:14px;font-weight:600;line-height:1.4;margin:0}.optimization-table{width:100%}.assessment-dialog /deep/ .el-dialog__body{padding-top:var(--space-4)}.assessment-dialog /deep/ .el-table{font-variant-numeric:tabular-nums}.toolbar .el-button+.el-button{margin-left:0}@media(max-width:680px){.assessment-dialog /deep/ .el-dialog__body{padding:var(--space-3)}.assessment-dialog /deep/ .el-dialog{margin-top:5vh!important}.assessment-toolbar{align-items:flex-start}}
</style>
