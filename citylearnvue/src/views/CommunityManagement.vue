<template>
  <div class="community-page" v-loading="loading">
    <header class="page-header">
      <h1 class="page-title">社区管理</h1>
      <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="refresh">刷新</el-button>
    </header>
    <div class="community-selector">
      <el-select v-model="selectedId" class="community-choice" :title="community.name" filterable placeholder="选择社区" @change="selectCommunity">
        <el-option v-for="item in communities" :key="item.id" :value="item.id" :label="item.name" />
      </el-select>
      <div class="toolbar community-actions">
        <el-button size="small" icon="el-icon-folder-add" :disabled="!community.id" @click="openDatasets">发布数据集</el-button>
        <el-button v-if="canWrite" size="small" type="primary" icon="el-icon-plus" @click="editCommunity()">新增社区</el-button>
          <template v-if="community.id && canWrite">
            <el-button size="small" icon="el-icon-edit" @click="editCommunity(community)">编辑社区</el-button>
            <el-button size="small" type="danger" plain icon="el-icon-delete" @click="removeCommunity">删除社区</el-button>
          </template>
      </div>
    </div>
    <el-empty v-if="!selectedId && !loading" description="暂无社区" />
    <template v-if="community.id">
      <div class="community-content">
          <building-management :key="community.id" :community-id="community.id" :community="community" @changed="loadBuildings" @scope-change="onScopeChange" @edit-community="editCommunity(community)" @delete-community="removeCommunity">
          <template #community-data>
          <el-tabs v-model="sharedTab" class="shared-tabs" @tab-click="onSharedTab">
            <el-tab-pane label="历史数据" name="history">
              <div class="section-toolbar">
                <div class="toolbar data-filters">
                <el-date-picker v-model="range" type="datetimerange" start-placeholder="开始时间（含）" end-placeholder="结束时间（不含）" size="small" @change="loadMeasurements(1)" />
                <el-select v-model="chartField" size="small" aria-label="选择指标" @change="renderChart"><el-option v-for="field in fields" :key="field.key" :value="field.key" :label="field.label + ' (' + field.unit + ')'" /></el-select>
                </div>
                <div class="toolbar"><el-button size="small" icon="el-icon-download" @click="downloadTemplate">标准模板</el-button><el-button v-if="canWrite" size="small" type="primary" icon="el-icon-upload2" @click="openImport">历史导入</el-button></div>
              </div>
              <div class="muted coverage">{{ time(measurements.first) }} 至 {{ time(measurements.last) }} · 共 {{ measurements.count || 0 }} 条 · 第 {{ measurements.page || 1 }} / {{ measurements.pages || 0 }} 页</div>
              <div ref="sharedChart" class="shared-chart" />
              <el-table :data="measurements.samples || []" height="300" size="small">
                <el-table-column label="测量时间" min-width="180"><template slot-scope="s">{{ time(s.row.timestamp) }}</template></el-table-column>
                <el-table-column prop="outdoor_dry_bulb_temperature" label="室外温度 (C)" min-width="130" />
                <el-table-column prop="outdoor_relative_humidity" label="相对湿度 (%)" min-width="130" />
                <el-table-column prop="diffuse_solar_irradiance" label="散射辐照 (W/m2)" min-width="140" />
                <el-table-column prop="direct_solar_irradiance" label="直射辐照 (W/m2)" min-width="140" />
                <el-table-column prop="electricity_pricing" label="电价" min-width="100" />
                <el-table-column prop="carbon_intensity" label="碳强度" min-width="110" />
              </el-table>
              <el-pagination class="data-pagination" background layout="prev, pager, next, total" :current-page="measurements.page || 1" :page-size="measurements.size || 100" :total="measurements.count || 0" @current-change="loadMeasurements" />
            </el-tab-pane>
            <el-tab-pane label="实时接入" name="realtime">
              <el-descriptions title="社区共享 HTTP 数据源" :column="1" border>
                <el-descriptions-item label="接入地址"><code class="wrap-code">{{ ingestUrl }}</code></el-descriptions-item>
                <el-descriptions-item label="认证状态">{{ community.hasToken ? '已配置社区令牌' : '未配置' }}</el-descriptions-item>
                <el-descriptions-item label="采样周期">{{ community.intervalSeconds }} 秒</el-descriptions-item>
              </el-descriptions>
              <div v-if="canWrite" class="section-toolbar"><el-button icon="el-icon-key" @click="newToken">生成 / 轮换社区令牌</el-button></div>
              <template v-if="token"><el-alert title="令牌仅本次显示，轮换后旧令牌立即失效。" type="warning" :closable="false" /><div class="token-row"><el-input :value="token" type="password" show-password readonly aria-label="社区接入令牌" /><el-button size="small" icon="el-icon-document-copy" @click="copyToken">复制令牌</el-button></div></template>
              <h3>请求示例</h3><pre class="request-example">{{ realtimeExample }}</pre>
            </el-tab-pane>
            <el-tab-pane label="数据接入记录" name="batches">
              <h3>字段表</h3>
              <el-table :data="fields" size="small">
                <el-table-column prop="label" label="字段" min-width="140" />
                <el-table-column prop="key" label="标准名称" min-width="260" />
                <el-table-column prop="unit" label="单位" min-width="110" />
              </el-table>
              <h3>接入批次</h3>
              <el-table :data="batchData.batches || []" size="small">
                <el-table-column prop="source" label="来源" width="110" />
                <el-table-column prop="accepted" label="新增" width="90" />
                <el-table-column prop="duplicates" label="重复" width="90" />
                <el-table-column label="接收时间" min-width="160"><template slot-scope="s">{{ time(s.row.createTime) }}</template></el-table-column>
                <el-table-column prop="payloadHash" label="原始数据 SHA-256" min-width="220" show-overflow-tooltip />
              </el-table>
              <el-pagination class="data-pagination" background layout="prev, pager, next, total" :current-page="batchData.page || 1" :page-size="batchData.size || 100" :total="batchData.count || 0" @current-change="loadBatches" />
            </el-tab-pane>
          </el-tabs>
          </template>
          </building-management>
      </div>
      <el-dialog title="发布数据集" :visible.sync="datasetsVisible" width="1200px" :close-on-click-modal="false">
          <div class="section-toolbar"><span class="muted">{{ buildings.length }} 栋社区建筑</span><div class="toolbar"><el-button v-if="canWrite" icon="el-icon-s-operation" @click="ol1GeneratorVisible = true">生成模拟数据</el-button><el-button v-if="canWrite" type="primary" icon="el-icon-folder-add" :disabled="publicationTasks.some(task => ['queued', 'running'].includes(task.status))" @click="openPublish">发布接入数据</el-button></div></div>
          <div v-for="task in publicationTasks.filter(item => item.status !== 'succeeded').slice(0, 3)" :key="task.id" class="publication-task">
            <el-alert :title="publicationStage(task)" :type="task.status === 'failed' ? 'error' : 'info'" :closable="false" />
            <el-progress v-if="task.status === 'running' && task.total" :percentage="Math.min(99, Math.round(task.completed / task.total * 100))" />
          </div>
          <el-table :data="versions" size="small"><el-table-column prop="name" label="版本名称" min-width="180" /><el-table-column label="来源" width="155"><template slot-scope="s"><el-tag size="mini" :type="s.row.sourceMode === 'synthetic_ol1' ? 'warning' : 'info'">{{ s.row.sourceMode === 'synthetic_ol1' ? '模拟数据' : '接入数据快照' }}</el-tag></template></el-table-column><el-table-column prop="buildingCount" label="建筑数" width="85" /><el-table-column label="时间范围" min-width="215"><template slot-scope="s">{{ datasetTime(s.row) }}<br>{{ datasetTime(s.row, true) }}</template></el-table-column><el-table-column label="创建时间" min-width="180"><template slot-scope="s">{{ time(s.row.createTime) }}</template></el-table-column><el-table-column label="操作" min-width="220"><template slot-scope="s"><el-button type="text" icon="el-icon-data-analysis" @click="openAssessment(s.row)">进行初步评估</el-button><el-tooltip content="下载 CityLearn 数据包"><el-button type="text" icon="el-icon-download" aria-label="下载数据集" @click="downloadBundle(s.row)" /></el-tooltip><el-tooltip v-if="canWrite" content="删除数据集"><el-button type="text" icon="el-icon-delete" class="danger" aria-label="删除数据集" @click="removeVersion(s.row)" /></el-tooltip></template></el-table-column></el-table>
          <el-empty v-if="!versions.length" description="暂无已发布数据集" :image-size="72" />
      </el-dialog>
    </template>

    <community-assessment-dialog :visible.sync="assessmentVisible" :community-id="selectedId" :release="assessmentRelease" :can-write="canWrite" />
    <el-dialog :title="form.id ? '编辑社区' : '新增社区'" :visible.sync="editVisible" width="600px" :close-on-click-modal="false">
      <el-form :model="form" label-position="top" size="small" class="community-form">
        <el-form-item label="社区名称" class="full"><el-input v-model="form.name" maxlength="120" /></el-form-item>
        <el-form-item label="时区"><el-select v-model="form.timezone" filterable allow-create default-first-option><el-option v-for="zone in timezones" :key="zone" :value="zone" :label="zone" /></el-select></el-form-item>
        <el-form-item label="采样周期"><el-select v-model="form.intervalSeconds"><el-option v-for="seconds in [60,300,900,1800,3600]" :key="seconds" :value="seconds" :label="seconds / 60 + ' 分钟'" /></el-select></el-form-item>
        <el-form-item label="电价币种"><el-input v-model="form.currency" maxlength="12" /></el-form-item>
        <el-form-item label="时间轴来源"><el-select v-model="form.timestampKind"><el-option label="真实测量时间" value="measured" /><el-option label="约定时间轴（无绝对时间）" value="assigned" /></el-select></el-form-item>
      </el-form>
      <div slot="footer"><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveCommunity">保存</el-button></div>
    </el-dialog>

    <el-dialog title="共享历史数据导入" :visible.sync="importVisible" width="860px" :close-on-click-modal="false">
      <div class="section-toolbar"><label class="file-picker"><i class="el-icon-upload2" />选择 CSV / JSON 文件<input type="file" accept=".csv,.json" multiple @change="readFiles" /></label><el-button icon="el-icon-download" size="small" @click="downloadTemplate">标准模板</el-button></div>
      <div class="muted">{{ importNames.join('、') || '尚未选择文件' }}<span v-if="importRows.length"> · {{ importRows.length }} 行</span></div>
      <el-alert v-if="importError" :title="importError" type="error" :closable="false" />
      <template v-if="importRows.length">
        <el-form label-width="145px" size="small" class="import-clock"><el-form-item label="生成连续时间戳"><el-switch v-model="generateTime" /></el-form-item><el-form-item v-if="generateTime" label="时间轴来源"><el-select v-model="generatedTimeKind" placeholder="请选择并确认时间来源"><el-option label="真实起始时间已确认" value="measured" /><el-option label="约定时间轴（无绝对时间）" value="assigned" /></el-select></el-form-item><el-form-item v-if="generateTime" label="起始时间"><el-date-picker v-model="generatedStart" type="datetime" value-format="yyyy-MM-ddTHH:mm:ss" /></el-form-item></el-form>
        <el-table :data="[{key: 'timestamp',label:'测量时间',unit:'ISO 8601'}, ...fields]" max-height="350" size="small"><el-table-column prop="label" label="目标字段" min-width="155" /><el-table-column label="标准名称" min-width="230"><template slot-scope="s"><span :title="s.row.key">{{ s.row.key }}</span></template></el-table-column><el-table-column label="来源列" min-width="180"><template slot-scope="s"><span v-if="s.row.key === 'timestamp' && generateTime">按社区采样周期生成</span><el-select v-else v-model="mapping[s.row.key]" clearable size="mini" placeholder="未映射"><el-option v-for="column in importColumns" :key="column" :label="column" :value="column" /></el-select></template></el-table-column><el-table-column label="源单位" min-width="130"><template slot-scope="s"><el-select v-if="s.row.key === 'carbon_intensity'" v-model="units[s.row.key]" size="mini"><el-option value="kgCO2/kWh" label="kgCO2/kWh" /><el-option value="gCO2/kWh" label="gCO2/kWh" /></el-select><span v-else>{{ s.row.unit }}</span></template></el-table-column></el-table>
        <h3>文件预览</h3><el-table :data="importRows.slice(0,3)" size="mini" max-height="140"><el-table-column v-for="column in importColumns.slice(0,6)" :key="column" :prop="column" :label="column" min-width="140" show-overflow-tooltip /></el-table>
      </template>
      <div slot="footer"><el-button @click="importVisible = false">取消</el-button><el-button type="primary" icon="el-icon-upload2" :disabled="!importRows.length || !!importError" :loading="importing" @click="submitImport">校验并导入</el-button></div>
    </el-dialog>

    <el-dialog title="发布社区数据集" :visible.sync="publishVisible" width="760px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="版本名称"><el-input v-model="versionName" maxlength="160" /></el-form-item>
        <el-form-item label="社区建筑"><el-checkbox-group v-model="selectedBuildings"><el-checkbox v-for="building in buildings" :key="building.id" :label="building.id">{{ building.name }}</el-checkbox></el-checkbox-group><el-empty v-if="!buildings.length" description="暂无社区建筑" :image-size="48" /></el-form-item>
        <el-form-item label="评估数据范围" v-loading="loadingBounds">
          <el-date-picker v-model="versionRange" type="datetimerange" :disabled="loadingBounds || !publicationBounds || !publicationBounds.ready" :picker-options="{ disabledDate: disabledPublicationDate }" start-placeholder="开始时间（含）" end-placeholder="最后一条数据（含）" format="yyyy-MM-dd HH:mm" />
        </el-form-item>
      </el-form>
      <p v-if="publicationBounds && publicationBounds.ready" class="muted">可选范围：{{ time(publicationBounds.startTime) }} 至 {{ time(new Date(publicationBounds.endTime).getTime() - 3600000) }}。末尾24小时保留用于预测生成。</p>
      <el-alert v-if="publicationBounds && !publicationBounds.ready" :title="publicationBounds.blocker" type="warning" :closable="false" />
      <el-alert v-if="versionRange && publicationBounds && publicationBounds.ready && !validPublicationRange" title="自动生成温度模型至少需要72小时连续整点数据，末尾另须预留24小时。" type="error" :closable="false" />
      <el-alert title="已有预测按小时保留；缺失预测按6／12／24小时补齐为研究用模拟预测，电价采用未来实测值。" type="info" :closable="false" />
      <el-alert v-if="preview" :title="preview.ready ? '发布条件满足 · ' + preview.buildingCount + ' 栋建筑 · ' + preview.timeSteps + ' 小时' : preview.blocker" :type="preview.ready ? 'success' : 'error'" :closable="false" />
      <p v-if="preview && preview.ready" class="muted">实际发布范围：{{ time(preview.startTime) }} 至 {{ time(preview.endTime) }}（结束时间不含）</p>
      <el-alert v-for="(warning, index) in publicationWarnings" :key="'runtime-' + index" :title="warning" type="warning" :closable="false" class="runtime-warning" />
      <template v-if="preview"><section v-for="building in preview.buildings || []" :key="building.buildingId"><h3>{{ building.buildingName }}</h3><publication-field-summary :fields="building.fields || []" /></section></template>
      <div slot="footer"><el-button :disabled="publishing" @click="publishVisible = false">取消</el-button><el-button icon="el-icon-view" :disabled="!validPublicationRange || loadingBounds || publishing" :loading="previewing" @click="previewPublication">检查发布内容</el-button><el-button type="primary" :loading="publishing" :disabled="!validPublicationRange || !versionName.trim() || !preview || !preview.ready || previewing || loadingBounds" @click="publish">发布</el-button></div>
    </el-dialog>
    <ol1-scenario-generator :key="selectedId" :visible.sync="ol1GeneratorVisible" :community-id="selectedId" :buildings="buildings" :can-write="canWrite" @published="loadVersions" />
  </div>
</template>

<script>
import Papa from 'papaparse'
import * as echarts from 'echarts'
import * as api from '../api/community'
import { PERMS } from '../utils/permissions'
import BuildingManagement from './BuildingManagement.vue'
import PublicationFieldSummary from '../components/PublicationFieldSummary.vue'
import CommunityAssessmentDialog from '../components/CommunityAssessmentDialog.vue'
import Ol1ScenarioGenerator from '../components/Ol1ScenarioGenerator.vue'
import { ol1TimeAtStep } from '../utils/ol1TimeRange'

const defaults = () => ({ name: '', timezone: 'Asia/Shanghai', intervalSeconds: 3600, currency: 'CNY', timestampKind: 'measured' })

export default {
  name: 'CommunityManagement',
  components: { BuildingManagement, PublicationFieldSummary, CommunityAssessmentDialog, Ol1ScenarioGenerator },
  inject: ['hasPermission'],
  data() {
    return { communities: [], selectedId: null, community: {}, buildings: [], versions: [], fields: [], assets: [], loading: false,
      datasetsVisible: false, communityScope: true, sharedTab: 'history', range: null, measurements: {}, batchData: {}, chart: null, chartField: 'outdoor_dry_bulb_temperature', timer: null,
      editVisible: false, form: defaults(), saving: false, token: '',
      assessmentVisible: false, assessmentRelease: {}, ol1GeneratorVisible: false,
      timezones: ['Asia/Shanghai','Asia/Tokyo','Asia/Singapore','Asia/Kolkata','Europe/London','Europe/Paris','Europe/Berlin','America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Phoenix','Pacific/Honolulu','Australia/Sydney','UTC'],
      importVisible: false, importRows: [], importNames: [], importColumns: [], sourceFiles: [], mapping: {}, units: {}, importError: '', generateTime: false, generatedStart: '', generatedTimeKind: '', importing: false,
      publicationTasks: [], pollingPublication: false,
      publishVisible: false, versionName: '', versionRange: null, selectedBuildings: [], preview: null, previewing: false, publishing: false,
      publicationBounds: null, loadingBounds: false, boundsRequestId: 0 }
  },
  computed: {
    canWrite() { return this.hasPermission(PERMS.BUILDING_WRITE) },
    ingestUrl() { return `${window.location.origin}/api/ingest/v1/communities/${this.selectedId}/measurements` },
    publicationWarnings() { if (!this.preview) return []; const warnings = this.preview.warnings || this.preview.runtimeWarnings || []; return (Array.isArray(warnings) ? warnings : [warnings]).map(warning => typeof warning === 'string' ? warning : warning.message || JSON.stringify(warning)) },
    realtimeExample() { return 'POST ' + this.ingestUrl + '\nAuthorization: Bearer <COMMUNITY_TOKEN>\nContent-Type: application/json\n\n' + JSON.stringify({ rows: [{ timestamp: '2026-11-11T08:00:00+08:00', outdoor_dry_bulb_temperature: 21, electricity_pricing: 0.5 }], mapping: {}, units: { electricity_pricing: 'currency/kWh' }, sourceFiles: [], timestampKind: this.community.timestampKind }, null, 2) },
    publicationKey() { return JSON.stringify([this.selectedId, this.selectedBuildings, this.versionName, this.versionRange]) },
    publicationSelectionKey() { return JSON.stringify([this.selectedId, this.selectedBuildings]) },
    validPublicationRange() {
      if (!this.publicationBounds || !this.publicationBounds.ready || !this.versionRange || this.versionRange.length !== 2) return false
      const [start, last] = this.versionRange.map(value => new Date(value).getTime())
      const lower = Date.parse(this.publicationBounds.startTime), upper = Date.parse(this.publicationBounds.endTime)
      return start >= lower && last + 3600000 <= upper && last - start >= 71 * 3600000 &&
        (start - lower) % 3600000 === 0 && (last - start) % 3600000 === 0
    },
  },
  watch: {
    publicationKey() { this.preview = null },
    publicationSelectionKey() { if (this.publishVisible) this.loadPublicationBounds() },
    publishVisible(value) { if (value) this.loadPublicationBounds(); else { this.boundsRequestId++; this.loadingBounds = false } }
  },
  async mounted() {
    const result = await api.getFields(); if (result.ok) this.fields = result.data
    await this.refresh(); window.addEventListener('resize', this.resize)
    this.timer = setInterval(() => { if (this.selectedId && this.communityScope && this.sharedTab === 'realtime') this.loadMeasurements(); if (this.selectedId && (this.datasetsVisible || this.publicationTasks.some(task => ['queued', 'running'].includes(task.status)))) this.loadPublicationTasks() }, 3000)
  },
  beforeDestroy() { clearInterval(this.timer); window.removeEventListener('resize', this.resize); if (this.chart) this.chart.dispose() },
  methods: {
    openAssessment(release) { this.assessmentRelease = Object.assign({}, release); this.assessmentVisible = true },
    time(value) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: this.community.timezone || 'Asia/Shanghai', hour12: false }) : '—' },
    datasetTime(row, end = false) {
      if (row.sourceMode !== 'synthetic_ol1') return this.time(end ? row.endTime : row.startTime)
      const value = end ? row.scoreEndStepExclusive : row.scoreStartStep
      if (value == null || String(value).trim() === '') return '—'
      const step = Number(value) - (end ? 1 : 0)
      return Number.isInteger(step) && step >= 0 && step < 2208 ? ol1TimeAtStep(step).slice(0, 16) : '—'
    },
    async refresh() {
      this.loading = true
      try { const result = await api.listCommunities(); if (!result.ok) return; this.communities = result.data; const id = this.communities.some(item => item.id === this.selectedId) ? this.selectedId : (this.communities[0] || {}).id; if (id) { this.selectedId = id; await this.selectCommunity() } else { this.selectedId = null; this.community = {}; this.buildings = []; this.versions = []; this.measurements = {} } } finally { this.loading = false }
    },
    async selectCommunity() {
      this.communityScope = true
      const id = this.selectedId; this.community = {}; this.token = ''; this.range = null; this.preview = null; this.measurements = {}; this.batchData = {}; this.versions = []; this.buildings = []; this.publicationTasks = []
      this.editVisible = false; this.importVisible = false; this.datasetsVisible = false; this.publishVisible = false; this.assessmentVisible = false; this.assessmentRelease = {}; this.ol1GeneratorVisible = false
      if (this.chart) { this.chart.dispose(); this.chart = null }
      const result = await api.getCommunity(id); if (!result.ok || id !== this.selectedId) return
      this.applyDetail(result.data)
      await Promise.all([this.loadBuildings(), this.loadMeasurements(), this.loadVersions(), this.loadPublicationTasks()])
    },
    applyDetail(data) {
      this.community = Object.assign({ count: 0, lastSample: null }, this.communities.find(item => item.id === this.selectedId), data.community || data); this.assets = data.assets || this.community.assets || []
    },
    async loadBuildings() { const id = this.selectedId; if (!id) return; const result = await api.listBuildings(id); if (result.ok && id === this.selectedId) { this.buildings = result.data } },
    async loadMeasurements(page) {
      const id = this.selectedId; if (!id) return
      const requestedPage = page || this.measurements.page || 1
      const params = Object.assign({ page: requestedPage, size: 100 }, this.range ? { from: this.range[0].toISOString(), to: this.range[1].toISOString() } : {})
      const result = await api.measurements(id, params)
      if (result.ok && id === this.selectedId) {
        this.measurements = result.data
        if (!params.from) { this.community.count = result.data.count || 0; this.community.lastSample = result.data.last || null }
        this.renderChart()
      }
    },
    async loadBatches(page) { const id = this.selectedId; if (!id) return; const result = await api.batches(id, { page: page || this.batchData.page || 1, size: 100 }); if (result.ok && id === this.selectedId) this.batchData = result.data },
    onSharedTab() { if (this.sharedTab === 'batches' && !this.batchData.batches) this.loadBatches(1); this.renderChart() },
    onScopeChange(scope) {
      this.communityScope = scope === 'community'
      if (this.communityScope) this.onSharedTab()
      else if (this.chart) { this.chart.dispose(); this.chart = null }
    },
    async loadVersions() { const id = this.selectedId; const result = await api.datasets(id); if (result.ok && id === this.selectedId) this.versions = result.data },
    editCommunity(item) {
      this.form = Object.assign(defaults(), JSON.parse(JSON.stringify(item || {})))
      this.editVisible = true
    },
    async saveCommunity() {
      const id = this.selectedId
      const form = JSON.parse(JSON.stringify(this.form))
      if (!form.name.trim()) return this.$message.warning('请填写社区名称')
      this.saving = true
      try {
        const result = await api.saveCommunity(form.id, form)
        if (result.ok && id === this.selectedId) {
          this.editVisible = false; this.selectedId = result.data.id || form.id
          await this.refresh()
          this.$message.success('社区已保存')
        }
      } finally { this.saving = false }
    },
    async removeCommunity() { const id = this.selectedId; try { await this.$confirm('删除“' + this.community.name + '”后，其共享数据与接入令牌将停止使用。', '删除社区', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch (_) { return } const result = await api.deleteCommunity(id); if (result.ok && id === this.selectedId) { await this.refresh(); this.$message.success('社区已删除') } },
    openDatasets() { this.datasetsVisible = true; this.loadVersions(); this.loadPublicationTasks() },
    resize() { if (this.chart) this.chart.resize() },
    renderChart() { this.$nextTick(() => {
      const container = this.$refs.sharedChart
      if (!container || !this.communityScope || this.sharedTab !== 'history' || !container.clientWidth || !container.clientHeight) return
      if (this.chart && !this.chart.isDisposed() && this.chart.getDom() !== container) { this.chart.dispose(); this.chart = null }
      if (!this.chart || this.chart.isDisposed()) this.chart = echarts.init(container)
      const samples = this.measurements.samples || []; const field = this.fields.find(item => item.key === this.chartField); this.chart.setOption({ animation: false, grid: { left: 65, right: 20, top: 25, bottom: 50 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: samples.map(row => this.time(row.timestamp)), axisLabel: { hideOverlap: true } }, yAxis: { type: 'value', scale: true, name: field ? field.unit : '' }, dataZoom: [{ type: 'inside' }], series: [{ type: 'line', showSymbol: samples.length < 20, connectNulls: false, data: samples.map(row => row[this.chartField] === undefined ? null : row[this.chartField]), lineStyle: { color: getComputedStyle(document.documentElement).getPropertyValue('--energy-grid-consumption-color').trim() }, itemStyle: { color: getComputedStyle(document.documentElement).getPropertyValue('--energy-grid-consumption-color').trim() } }] }, true); this.chart.resize()
    }) },
    async newToken() { const id = this.selectedId; if (this.community.hasToken) { try { await this.$confirm('旧令牌立即失效，已连接数据源需要更换令牌。', '轮换社区令牌', { type: 'warning' }) } catch (_) { return } } if (id !== this.selectedId) return; const result = await api.rotateToken(id); if (result.ok && id === this.selectedId) { this.token = result.data.token; this.$set(this.community, 'hasToken', true) } },
    async copyToken() { try { await navigator.clipboard.writeText(this.token); this.$message.success('已复制') } catch (_) { this.$message.warning('请从输入框手动选择令牌') } },
    downloadTemplate() { const content = '\ufeff' + Papa.unparse({ fields: ['timestamp', ...this.fields.map(field => field.key)], data: [] }); const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'community_measurements.csv'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) },
    openImport() { this.importRows = []; this.importColumns = []; this.importNames = []; this.sourceFiles = []; this.importError = ''; this.generateTime = false; this.generatedStart = ''; this.generatedTimeKind = ''; this.importVisible = true },
    async readFiles(event) {
      const id = this.selectedId; const files = Array.from(event.target.files || []); event.target.value = ''; this.importRows = []; this.importColumns = []; this.sourceFiles = []; this.importError = ''; this.importNames = files.map(file => file.name)
      try {
        if (!files.length) return
        if (files.length > 8 || files.reduce((sum, file) => sum + file.size, 0) > 40 * 1024 * 1024 || files.some(file => file.size > 20 * 1024 * 1024)) throw Error('每批最多 8 个文件，单文件最多 20 MB，合计最多 40 MB')
        const parsed = await Promise.all(files.map(async file => { if (/\.json$/i.test(file.name)) { const value = JSON.parse(await file.text()); const rows = Array.isArray(value) ? value : value.rows; if (!Array.isArray(rows) || !rows.length || rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) throw Error('JSON 需要对象数组或包含 rows 数组'); return { data: rows, columns: [...new Set(rows.flatMap(row => Object.keys(row)))] } } const result = await new Promise((resolve, reject) => Papa.parse(file, { header: true, skipEmptyLines: 'greedy', complete: resolve, error: reject })); if (result.errors.length) throw Error(result.errors[0].message); return { data: result.data, columns: result.meta.fields } }))
        const length = parsed[0].data.length; if (!length || length > 10000) throw Error('每批需要 1–10000 行；更大文件请按连续时间分批')
        const rows = Array.from({ length }, () => ({})); const columns = []
        for (const file of parsed) { if (file.data.length !== length) throw Error('多个文件必须逐行对齐且行数相同'); for (const column of file.columns) { if (columns.includes(column)) throw Error('多个文件有重复列: ' + column); columns.push(column) } file.data.forEach((row, index) => Object.assign(rows[index], row)) }
        const sourceFiles = await Promise.all(files.map(async file => { const bytes = new Uint8Array(await file.arrayBuffer()); const chunks = []; for (let offset = 0; offset < bytes.length; offset += 32768) chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32768))); return { name: file.name, base64: btoa(chunks.join('')) } }))
        if (id !== this.selectedId || !this.importVisible) return
        this.sourceFiles = sourceFiles
        const mapping = {}, units = {}; for (const field of [{ key: 'timestamp' }, ...this.fields]) { mapping[field.key] = columns.find(column => column.toLowerCase().replace(/\s/g, '_') === field.key) || ''; if (field.unit) units[field.key] = field.unit }
        if (!mapping.timestamp) mapping.timestamp = columns.find(column => ['time', 'datetime', 'date'].includes(column.toLowerCase())) || ''
        this.importRows = rows; this.importColumns = columns; this.mapping = mapping; this.units = units; this.generateTime = !mapping.timestamp
      } catch (error) { if (id === this.selectedId && this.importVisible) this.importError = error.message }
    },
    async submitImport() {
      const id = this.selectedId
      if (!this.generateTime && !this.mapping.timestamp) return this.$message.warning('请映射时间戳')
      if (this.generateTime && (!this.generatedStart || !this.generatedTimeKind)) return this.$message.warning('请填写起始时间并确认时间轴来源')
      if (!this.fields.some(field => this.mapping[field.key])) return this.$message.warning('请至少映射一个共享字段')
      const rows = this.importRows.map(row => Object.assign({}, row)); const mapping = Object.fromEntries(Object.entries(this.mapping).filter(([, value]) => value))
      if (this.generateTime) { const start = new Date(this.generatedStart + 'Z').getTime(); rows.forEach((row, index) => { row.__timestamp = new Date(start + index * this.community.intervalSeconds * 1000).toISOString().slice(0, 19) }); mapping.timestamp = '__timestamp' }
      this.importing = true; this.importError = ''
      try { const result = await api.ingest(id, { rows, mapping, units: this.units, sourceFiles: this.sourceFiles, timestampKind: this.generateTime ? this.generatedTimeKind : this.community.timestampKind }); if (id !== this.selectedId) return; if (result.ok) { this.importVisible = false; await this.loadMeasurements(); this.$message.success('共享数据已导入：新增 ' + (result.data.inserted || 0) + ' 条，补齐 ' + (result.data.updated || 0) + ' 条，重复 ' + (result.data.duplicates || 0) + ' 条') } else this.importError = result.message } finally { this.importing = false }
    },
    openPublish() { this.versionName = this.community.name + ' · ' + new Date().toLocaleDateString(); this.selectedBuildings = this.buildings.map(building => building.id); this.versionRange = null; this.publicationBounds = null; this.preview = null; this.publishVisible = true },
    disabledPublicationDate(date) {
      if (!this.publicationBounds || !this.publicationBounds.ready) return true
      const dayEnd = new Date(date); dayEnd.setHours(23, 59, 59, 999)
      return dayEnd.getTime() < Date.parse(this.publicationBounds.startTime) || date.getTime() > Date.parse(this.publicationBounds.endTime) - 3600000
    },
    async loadPublicationBounds() {
      const id = this.selectedId, key = this.publicationSelectionKey, sequence = ++this.boundsRequestId
      this.publicationBounds = null; this.versionRange = null; this.preview = null
      if (!this.selectedBuildings.length) { this.loadingBounds = false; return }
      this.loadingBounds = true
      try {
        const result = await api.publicationRange(id, { buildingIds: this.selectedBuildings.slice() })
        if (sequence !== this.boundsRequestId || key !== this.publicationSelectionKey || !this.publishVisible) return
        this.publicationBounds = result.ok ? result.data : { ready: false, blocker: result.message || '无法读取发布范围，请重新打开发布窗口' }
        if (this.publicationBounds.ready) this.versionRange = [new Date(this.publicationBounds.startTime), new Date(Date.parse(this.publicationBounds.endTime) - 3600000)]
      } finally { if (sequence === this.boundsRequestId) this.loadingBounds = false }
    },
    publicationRequest() {
      if (!this.versionName.trim() || !this.selectedBuildings.length) throw Error('请填写版本名称并选择至少一栋建筑')
      if (!this.validPublicationRange || this.loadingBounds) throw Error('请选择至少72小时连续整点数据，并另保留末尾24小时')
      return { name: this.versionName, buildingIds: this.selectedBuildings.slice(), from: new Date(this.versionRange[0]).toISOString(), to: new Date(new Date(this.versionRange[1]).getTime() + 3600000).toISOString() }
    },
    async previewPublication() { let body; try { body = this.publicationRequest() } catch (error) { return this.$message.warning(error.message) } const key = this.publicationKey; this.preview = null; this.previewing = true; try { const result = await api.preview(this.selectedId, body); if (result.ok && key === this.publicationKey) this.preview = result.data } finally { this.previewing = false } },
    async publish() {
      const id = this.selectedId
      let body
      try { body = this.publicationRequest() } catch (error) { return this.$message.warning(error.message) }
      this.publishing = true
      try { const result = await api.publish(id, body); if (result.ok && id === this.selectedId) { this.publicationTasks.unshift(result.data); this.publishVisible = false; await this.loadPublicationTasks(); this.$message.success('发布任务已提交') } } finally { this.publishing = false }
    },
    publicationStage(task) {
      if (task.status === 'failed') return task.error || '发布失败'
      if (task.status === 'succeeded') return '发布完成'
      if (task.stage === 'generating_models') return '生成温度模型 ' + (task.completed + 1) + ' / ' + task.total
      return task.status === 'queued' ? '等待发布' : '准备数据'
    },
    async loadPublicationTasks() {
      if (this.pollingPublication || !this.selectedId) return
      const id = this.selectedId
      this.pollingPublication = true
      try {
        const response = await api.publicationTasks(id)
        if (!response.ok || id !== this.selectedId) return
        const previous = this.publicationTasks
        this.publicationTasks = response.data
        if (response.data.some(task => task.status === 'succeeded' && previous.some(old => old.id === task.id && old.status !== 'succeeded'))) {
          await this.loadVersions(); this.$message.success('温度模型已生成，数据集已发布')
        }
      } finally { this.pollingPublication = false }
    },
    downloadBundle(version) { window.location.assign(`/api/web/communities/${this.selectedId}/datasets/${version.id}/bundle`) },
    async removeVersion(version) { const id = this.selectedId; try { await this.$confirm('删除“' + version.name + '”后，停止下载及用于新任务。历史记录保留供追溯。', '删除社区数据集', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch (_) { return } const result = await api.deleteDataset(id, version.id); if (result.ok && id === this.selectedId) { await this.loadVersions(); this.$message.success('数据集已删除') } }
  }
}
</script>

<style scoped>
.community-page{color:var(--primary-text-color);min-width:0}.page-header,.toolbar,.section-toolbar,.community-selector{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.page-header,.section-toolbar{justify-content:space-between}.page-header{margin-bottom:20px}h1{font-size:22px;margin:0 0 6px;font-weight:600}h2{font-size:20px;font-weight:600}h3{font-size:15px;margin:20px 0 12px}.muted{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.community-selector{padding:16px 0;border-top:1px solid var(--divider-color);border-bottom:1px solid var(--divider-color)}.community-actions{margin-left:auto}.community-title{margin:22px 0 16px}.toolbar .el-button+.el-button{margin-left:0}.section-toolbar{margin:16px 0}.section-toolbar h3{margin:0}.coverage{margin:12px 0}.shared-chart{height:240px;width:100%}.community-form,.scene-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px}.scene-controls{grid-template-columns:repeat(3,minmax(0,1fr))}.community-form .el-select,.scene-controls .el-select{width:100%}.full{grid-column:1/-1}.file-picker{display:inline-flex;gap:8px;align-items:center;border:1px solid var(--primary-color);color:var(--primary-color);padding:9px 14px;border-radius:4px;font-size:13px;cursor:pointer}.file-picker input{display:none}.request-example{background:var(--input-fill-color);color:var(--primary-text-color);font-size:12px;padding:16px;overflow:auto;max-height:380px;border:1px solid var(--divider-color);border-radius:4px;white-space:pre-wrap;overflow-wrap:anywhere}.wrap-code{white-space:normal;overflow-wrap:anywhere}.token-row{display:flex;gap:12px;align-items:center;max-width:650px;margin:16px 0}.json-editor /deep/ textarea{font-family:var(--ha-font-family-mono);font-size:12px;line-height:1.6;tab-size:2}.import-clock{margin-top:20px}.danger{color:var(--error-color)}.community-page /deep/ .el-dialog{max-width:calc(100% - 24px)}.community-page /deep/ .el-date-editor{max-width:100%}.community-page /deep/ .el-dialog .el-date-editor{width:100%}.community-page /deep/ .el-checkbox{margin:4px 24px 8px 0}.shared-tabs /deep/ .el-tabs__item{font-size:13px}
@media(max-width:780px){.scene-controls{grid-template-columns:1fr}.community-actions{margin-left:0}.community-selector>.el-select{width:100%}.community-form{grid-template-columns:1fr}.community-page /deep/ .el-date-editor--datetimerange{width:100%}.token-row{flex-wrap:wrap}.toolbar{gap:8px}.section-toolbar{align-items:flex-start}.community-page /deep/ .el-dialog__body{padding:16px}.community-page /deep/ .el-tabs__nav-wrap{max-width:100%}}
.community-page{font-family:var(--ha-font-family);color:var(--primary-text-color);background:var(--primary-background-color);padding:var(--space-4) var(--space-4) var(--space-6);box-sizing:border-box;font-size:14px;line-height:1.5}.page-header{margin-bottom:var(--space-5)}h1{font-size:28px;font-weight:500;line-height:1.25;margin:0 0 var(--space-2)}h2{font-size:20px;font-weight:500;line-height:1.3}h3{font-size:16px;font-weight:500;line-height:1.35}.muted{color:var(--secondary-text-color);line-height:1.4}.community-selector{padding:var(--space-4) 0;border-color:var(--divider-color);gap:var(--space-3)}.toolbar,.page-header,.section-toolbar{gap:var(--space-3)}.section-toolbar{margin:var(--space-4) 0}.community-title{margin:var(--space-5) 0 var(--space-4)}.coverage{margin:var(--space-3) 0}.file-picker{color:var(--primary-color);border-color:var(--primary-color);font-weight:500;transition:background 150ms ease}.file-picker:hover{background:var(--sidebar-selected-background)}.danger{color:var(--error-color)}.request-example{background:var(--input-fill-color);color:var(--primary-text-color);border-color:var(--divider-color);font-family:var(--ha-font-family-mono);padding:var(--space-4)}.json-editor /deep/ textarea{font-family:var(--ha-font-family-mono)}.community-page /deep/ .el-table{font-variant-numeric:tabular-nums}.community-page /deep/ .el-table th{background:var(--input-fill-color);color:var(--secondary-text-color);font-weight:500}.community-page /deep/ .el-tabs__content{padding-top:var(--space-2)}.community-page /deep/ .el-dialog{border-radius:var(--ha-card-border-radius);border:1px solid var(--divider-color);box-shadow:none}.community-page /deep/ .el-empty{padding:var(--space-5) 0}.home-source-select{width:100%}.runtime-warning{margin-top:var(--space-3)}.schema-help{margin:12px 0}.schema-help-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 20px}.schema-help-grid>div{overflow-wrap:anywhere}
@media(max-width:780px){.community-page{padding:var(--space-3) var(--space-2) var(--space-5)}.page-header{align-items:flex-start}h1{font-size:28px}.page-header>.toolbar{width:100%}}
@media(max-width:780px){.schema-help-grid{grid-template-columns:1fr}}
.data-pagination{display:flex;justify-content:flex-end;margin:12px 0}
.publication-task{margin:12px 0;overflow-wrap:anywhere}.publication-task .el-progress{margin-top:8px}
.community-page { padding: 20px var(--space-5) var(--space-6); }
.community-choice{flex:1 1 420px;width:100%;max-width:720px;min-width:0}
#app .community-choice /deep/ .el-input__inner{font-size:16px;font-weight:500;height:44px;line-height:44px}
.community-choice /deep/ .el-input__icon{line-height:44px}
.community-actions{flex-shrink:0;max-width:100%}
.community-content{padding-top:16px}
.data-filters{min-width:0;max-width:100%}
@media (max-width: 780px) {
  .community-page { padding: var(--space-4) var(--space-4) var(--space-6); }
}
</style>
