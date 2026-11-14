<template>
  <div class="building-page" :class="{ embedded: !!communityId }">
    <div class="building-workspace">
      <aside class="building-list">
        <button v-if="communityId" class="building-item community-item" :class="{ selected: !selectedId }" @click="selectCommunityData">
          <i class="el-icon-office-building"></i>
          <span><strong>社区</strong><small>{{ community.count || 0 }} 条记录</small>
            <small>{{ community.lastSample ? time(community.lastSample, community.timezone) : '尚未接入数据' }}</small></span>
        </button>
        <el-empty v-if="!buildings.length && !loading" description="暂无建筑" :image-size="72" />
        <button v-for="b in buildings" :key="b.id" class="building-item"
                :class="{ selected: selectedId === b.id }" @click="select(b.id)">
          <i class="el-icon-office-building"></i>
          <span><strong>{{ b.name }}</strong><small>{{ b.count }} 条记录</small>
            <small>{{ b.lastSample ? time(b.lastSample, b.timezone) : '尚未接入数据' }}</small></span>
        </button>
      </aside>
      <main v-loading="detailLoading" class="building-detail">
        <div v-if="communityId" v-show="!selectedId" class="community-detail">
          <div class="detail-title">
            <h2>社区</h2>
            <div v-if="canWrite" class="toolbar">
              <el-button size="small" type="primary" icon="el-icon-plus" @click="edit()">新增建筑</el-button>
              <el-button size="small" icon="el-icon-edit" @click="$emit('edit-community')">编辑社区</el-button>
              <el-button size="small" type="danger" plain icon="el-icon-delete" @click="$emit('delete-community')">删除社区</el-button>
            </div>
          </div>
          <slot name="community-data" />
        </div>
        <el-empty v-if="!selectedId && !communityId" description="选择或新增建筑">
          <el-button v-if="!communityId" size="small" icon="el-icon-refresh" :loading="loading" @click="refresh">刷新</el-button>
          <el-button v-if="canWrite" size="small" type="primary" icon="el-icon-plus" @click="edit()">新增建筑</el-button>
        </el-empty>
        <template v-if="selectedId && detail.building">
          <div class="detail-title">
            <div><h2>{{ detail.building.name }}</h2></div>
            <div v-if="canWrite" class="toolbar">
              <el-button v-if="!communityId" size="small" icon="el-icon-refresh" :loading="loading" @click="refresh">刷新</el-button>
              <el-button size="small" type="primary" icon="el-icon-plus" @click="edit()">新增建筑</el-button>
              <el-button size="small" icon="el-icon-edit" @click="edit(detail.building)">编辑建筑</el-button>
              <el-button size="small" type="danger" plain icon="el-icon-delete" @click="removeBuilding">删除建筑</el-button>
            </div>
            <div v-else-if="!communityId" class="toolbar">
              <el-button size="small" icon="el-icon-refresh" :loading="loading" @click="refresh">刷新</el-button>
            </div>
          </div>
          <el-tabs v-model="tab" @tab-click="renderChart">
            <el-tab-pane label="建筑数据" name="measurements">
              <el-alert v-if="detail.truncated" title="仅展示最近 200000 条数据；请选择时间范围查看质量统计与图表。" type="warning" :closable="false" />
              <div class="section-toolbar">
                <div class="toolbar data-filters">
                <el-date-picker v-model="range" type="datetimerange" start-placeholder="开始时间（含）" end-placeholder="结束时间（不含）"
                                size="small" @change="loadDetail(1)" />
                <el-select v-model="chartField" size="small" aria-label="选择指标" @change="renderChart">
                  <el-option v-for="f in fields" :key="f.key" :label="f.label + ' (' + f.unit + ')'" :value="f.key" />
                </el-select>
                </div>
                <div class="toolbar">
                  <el-button icon="el-icon-download" size="small" @click="downloadTemplate">标准模板</el-button>
                  <el-button v-if="canWrite" type="primary" icon="el-icon-upload2" size="small" @click="openImport">历史导入</el-button>
                </div>
              </div>
              <div class="coverage muted">数据时间：{{ time(detail.first) }} 至 {{ time(detail.last) }} · 采样周期 {{ detail.building.intervalSeconds }} 秒</div>
              <div class="chart-toolbar">
                <span class="muted">共 {{ detail.displayCount || 0 }} 条 · 第 {{ detail.page || 1 }} / {{ detail.pages || 0 }} 页</span>
              </div>
              <div ref="chart" class="measurement-chart" />
              <el-table :data="detail.samples || []" height="300" size="small">
                <el-table-column label="测量时间" min-width="180"><template slot-scope="s">{{ time(s.row.timestamp) }}</template></el-table-column>
                <el-table-column prop="non_shiftable_load" label="不可移峰 (kWh)" min-width="130" />
                <el-table-column prop="indoor_dry_bulb_temperature" label="室温 (C)" min-width="100" />
                <el-table-column prop="electricity_pricing" label="电价" min-width="90" />
                <el-table-column prop="solar_generation" label="光伏 (W/kW)" min-width="120" />
              </el-table>
              <el-pagination class="data-pagination" background layout="prev, pager, next, total" :current-page="detail.page || 1" :page-size="detail.size || 100" :total="detail.displayCount || 0" @current-change="loadMeasurementPage" />
            </el-tab-pane>
            <el-tab-pane label="实时接入" name="realtime">
              <el-descriptions title="HTTP 数据源" :column="1" border>
                <el-descriptions-item label="接入地址"><code class="wrap-code">{{ ingestUrl }}</code></el-descriptions-item>
                <el-descriptions-item label="认证状态">{{ detail.building.hasToken ? '已配置令牌' : '未配置' }}</el-descriptions-item>
                <el-descriptions-item label="字段与单位"><el-button type="text" icon="el-icon-download" @click="downloadTemplate">下载标准 CSV 模板</el-button></el-descriptions-item>
                <el-descriptions-item label="采样周期">{{ detail.building.intervalSeconds }} 秒</el-descriptions-item>
              </el-descriptions>
              <div class="section-toolbar" v-if="canWrite"><el-button icon="el-icon-key" @click="newToken">生成 / 轮换接入令牌</el-button></div>
              <template v-if="token">
                <el-alert title="令牌仅本次显示，轮换后旧令牌立即失效。" type="warning" :closable="false" />
                <el-input :value="token" readonly show-password type="password" class="token-input" aria-label="接入令牌" />
                <el-button size="small" icon="el-icon-document-copy" @click="copy(token)">复制令牌</el-button>
              </template>
              <h3>请求示例</h3>
              <pre class="request-example">{{ realtimeExample }}</pre>
            </el-tab-pane>
            <el-tab-pane label="数据接入记录" name="quality">
              <el-alert v-if="detail.blocker" :title="detail.blocker" type="warning" :closable="false" />
              <el-table :data="fields" size="small">
                <el-table-column prop="label" label="字段" min-width="140" />
                <el-table-column prop="key" label="标准名称" min-width="260" />
                <el-table-column prop="unit" label="单位" min-width="110" />
                <el-table-column label="缺失记录" width="110"><template slot-scope="s"><span :class="{ danger: detail.missing && detail.missing[s.row.key] }">{{ (detail.missing || {})[s.row.key] || 0 }}</span></template></el-table-column>
              </el-table>
              <h3>接入批次</h3>
              <el-table :data="detail.batches || []" size="small">
                <el-table-column prop="source" label="来源" width="110" />
                <el-table-column prop="accepted" label="新增" width="90" />
                <el-table-column prop="duplicates" label="重复" width="90" />
                <el-table-column label="接收时间" min-width="160"><template slot-scope="s">{{ time(s.row.createTime) }}</template></el-table-column>
                <el-table-column prop="payloadHash" label="原始数据 SHA-256" min-width="220" show-overflow-tooltip />
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </template>
      </main>
    </div>

    <el-dialog :title="form.id ? '编辑建筑' : '新增建筑'" :visible.sync="editVisible" width="660px" :close-on-click-modal="false">
      <el-form :model="form" label-position="top" size="small" class="building-form">
        <el-form-item label="建筑名称"><el-input v-model="form.name" maxlength="120" /></el-form-item>
        <el-form-item label="时区"><el-select v-model="form.timezone" filterable :disabled="!!communityId || !!(form.id && selectedBuilding && selectedBuilding.count)">
          <el-option v-for="zone in timezoneOptions" :key="zone.value" :label="zone.label" :value="zone.value" />
        </el-select></el-form-item>
        <el-form-item label="时间轴来源"><el-select v-model="form.timestampKind" :disabled="!!communityId"><el-option label="真实测量时间" value="measured" /><el-option label="约定时间轴（原数据无绝对时间）" value="assigned" /></el-select></el-form-item>
        <el-form-item label="采样周期"><el-select v-model="form.intervalSeconds" :disabled="!!communityId || !!(form.id && selectedBuilding && selectedBuilding.count)">
          <el-option v-for="v in [60,300,900,1800,3600]" :key="v" :label="v / 60 + ' 分钟'" :value="v" />
        </el-select></el-form-item>
        <el-form-item label="建筑面积 (m2)"><el-input-number v-model="form.area" :min="0" /></el-form-item>
        <el-form-item label="电价币种"><el-input v-model="form.currency" maxlength="12" :disabled="!!communityId" /></el-form-item>
        <el-form-item label="备注" class="full-width"><el-input v-model="form.description" type="textarea" maxlength="1000" /></el-form-item>
        <div class="full-width">
          <el-alert v-if="legacyEditing" title="此建筑使用旧版固定 COP。保存后，新导出将改用下方热泵参数；已发布版本保持不变。" type="warning" :closable="false" />
          <el-tag v-if="equipmentOrigin" class="equipment-origin" type="info" size="small">{{ equipmentOrigin }}</el-tag>
          <schema-equipment-form v-if="form.devices" :key="equipmentRevision" ref="equipmentEditor" v-model="form.devices" :templates="equipmentTemplate" />
        </div>
      </el-form>
      <div slot="footer"><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></div>
    </el-dialog>

    <el-dialog title="历史数据导入" :visible.sync="importVisible" width="840px" :close-on-click-modal="false">
      <div class="section-toolbar">
        <label class="file-picker"><i class="el-icon-upload2"></i> 选择 CSV 文件<input type="file" accept=".csv" multiple @change="readFiles"></label>
        <el-button icon="el-icon-download" size="small" @click="downloadTemplate">标准模板</el-button>
      </div>
      <div class="muted">{{ importNames.join('、') || '尚未选择文件' }} <span v-if="importRows.length"> · {{ importRows.length }} 行</span></div>
      <el-alert v-if="importError" :title="importError" type="error" :closable="false" />
      <template v-if="importRows.length">
        <el-form label-position="left" label-width="140px" size="small" class="import-clock">
          <el-form-item label="生成连续时间戳"><el-switch v-model="generateTime" /></el-form-item>
          <el-form-item v-if="generateTime" label="时间轴来源"><el-select v-model="generatedTimeKind" placeholder="请选择并确认时间来源"><el-option label="真实起始时间已确认" value="measured" /><el-option label="约定时间轴（无绝对时间）" value="assigned" /></el-select></el-form-item>
          <el-form-item v-if="generateTime" label="起始时间"><el-date-picker v-model="generatedStart" type="datetime" value-format="yyyy-MM-ddTHH:mm:ss" /></el-form-item>
        </el-form>
        <el-table :data="[{key:'timestamp', label:'测量时间',unit:'ISO 8601'}, ...fields]" max-height="340" size="small">
          <el-table-column prop="label" label="目标字段" min-width="140" />
          <el-table-column label="要求" width="65"><template slot-scope="s">{{ s.row.required || s.row.key === 'timestamp' ? '必需' : '可选' }}</template></el-table-column>
          <el-table-column label="来源列" min-width="230"><template slot-scope="s">
            <span v-if="s.row.key === 'timestamp' && generateTime">按建筑采样周期生成</span>
            <el-select v-else v-model="mapping[s.row.key]" clearable placeholder="未映射" size="mini">
              <el-option v-for="column in importColumns" :key="column" :label="column" :value="column" />
            </el-select>
          </template></el-table-column>
          <el-table-column label="源单位" min-width="150"><template slot-scope="s">
            <el-select v-if="energyFields.includes(s.row.key)" v-model="units[s.row.key]" size="mini">
              <el-option v-for="unit in ['kWh','Wh','kW','W']" :key="unit" :value="unit" :label="unit" />
            </el-select>
            <el-select v-else-if="s.row.key === 'carbon_intensity'" v-model="units[s.row.key]" size="mini">
              <el-option label="kgCO2/kWh" value="kgCO2/kWh" /><el-option label="gCO2/kWh" value="gCO2/kWh" />
            </el-select><span v-else>{{ s.row.unit }}</span>
          </template></el-table-column>
        </el-table>
        <h3>文件预览</h3>
        <el-table :data="importRows.slice(0,3)" size="mini" max-height="130">
          <el-table-column v-for="column in importColumns.slice(0,6)" :key="column" :prop="column" :label="column" min-width="140" show-overflow-tooltip />
        </el-table>
      </template>
      <div slot="footer"><el-button @click="importVisible = false">取消</el-button><el-button type="primary" icon="el-icon-upload2" :disabled="!importRows.length || !!importError" :loading="importing" @click="submitImport">校验并导入</el-button></div>
    </el-dialog>

  </div>
</template>

<script>
import Papa from 'papaparse'
import * as echarts from 'echarts'
import * as api from '../api/building'
import * as communityApi from '../api/community'
import { PERMS } from '../utils/permissions'
import SchemaEquipmentForm from '../components/SchemaEquipmentForm.vue'
import { themeColor } from '../utils/theme'

const defaults = () => ({ name: '', timezone: 'Asia/Shanghai', intervalSeconds: 3600,
  area: 0, description: '', currency: 'CNY', timestampKind: 'measured' })
const energyFields = ['non_shiftable_load', 'cooling_demand', 'heating_demand', 'dhw_demand']
const commonTimezones = [
  ['Asia/Shanghai', '北京时间'], ['Asia/Hong_Kong', '香港'], ['Asia/Taipei', '台北'],
  ['Asia/Tokyo', '东京'], ['Asia/Seoul', '首尔'], ['Asia/Singapore', '新加坡'],
  ['Asia/Bangkok', '曼谷'], ['Asia/Kolkata', '印度'], ['Asia/Dubai', '迪拜'],
  ['Europe/London', '伦敦'], ['Europe/Paris', '巴黎'], ['Europe/Berlin', '柏林'],
  ['Europe/Moscow', '莫斯科'], ['America/New_York', '纽约'], ['America/Chicago', '芝加哥'],
  ['America/Denver', '丹佛'], ['America/Los_Angeles', '洛杉矶'], ['America/Phoenix', '凤凰城'],
  ['America/Toronto', '多伦多'], ['America/Sao_Paulo', '圣保罗'], ['Pacific/Honolulu', '檀香山'],
  ['Australia/Sydney', '悉尼'], ['Australia/Perth', '珀斯'], ['Pacific/Auckland', '奥克兰'],
  ['Africa/Johannesburg', '约翰内斯堡'], ['UTC', '协调世界时']
]

export default {
  name: 'BuildingManagement',
  props: { communityId: { type: [Number, String], default: null }, community: { type: Object, default: () => ({}) } },
  components: { SchemaEquipmentForm },
  inject: ['hasPermission'],
  data() {
    return { buildings: [], fields: [], selectedId: null, detail: {}, tab: 'measurements', range: null,
      loading: false, detailLoading: false, chartField: 'non_shiftable_load', chart: null, timer: null,
      editVisible: false, form: defaults(), saving: false, token: '', equipmentTemplate: {}, legacyEditing: false,
      equipmentOrigin: '', equipmentRevision: 0,
      importVisible: false, importRows: [], importColumns: [], importNames: [], sourceFiles: [], mapping: {}, units: {},
      energyFields, importError: '', generateTime: false, generatedStart: '', generatedTimeKind: '', importing: false }
  },
  computed: {
    timezoneOptions() {
      const options = commonTimezones.map(([value, name]) => ({ value, label: `${name} (${value})` }))
      if (this.form.timezone && !options.some(zone => zone.value === this.form.timezone)) {
        options.push({ value: this.form.timezone, label: this.form.timezone })
      }
      return options
    },
    canWrite() { return this.hasPermission(PERMS.BUILDING_WRITE) },
    selectedBuilding() { return this.buildings.find(b => b.id === this.selectedId) },
    ingestUrl() { return `${window.location.origin}/api/ingest/v1/buildings/${this.selectedId}/measurements` },
    realtimeExample() {
      return 'POST ' + this.ingestUrl + '\nAuthorization: Bearer <BUILDING_TOKEN>\nContent-Type: application/json\n\n' +
        JSON.stringify({ rows: [{ timestamp: '2026-11-10T08:00:00+08:00', non_shiftable_load: 0.5,
          outdoor_dry_bulb_temperature: 21 }] }, null, 2)
    },
  },
  async mounted() {
    const result = await api.getFields()
    if (result.ok) this.fields = result.data
    const equipment = await api.getEquipmentTemplate()
    if (equipment.ok) this.equipmentTemplate = equipment.data
    await this.refresh()
    window.addEventListener('resize', this.resize)
    this.timer = setInterval(() => {
      if (this.selectedId && this.tab === 'realtime') {
        this.loadMeasurementPage(this.detail.page || 1)
      }
    }, 5000)
  },
  beforeDestroy() {
    clearInterval(this.timer)
    window.removeEventListener('resize', this.resize)
    if (this.chart) this.chart.dispose()
  },
  methods: {
    time(value, timezone) {
      if (!value) return '—'
      return new Date(value).toLocaleString('zh-CN', { timeZone: timezone || (this.detail.building || {}).timezone || 'Asia/Shanghai', hour12: false })
    },
    async refresh() {
      this.loading = true
      try {
        const result = await (this.communityId ? communityApi.listBuildings(this.communityId) : api.listBuildings())
        if (!result.ok) return
        this.buildings = result.data
        if (this.communityId && !this.selectedId) return
        if (!this.buildings.some(b => b.id === this.selectedId)) {
          if (this.communityId) this.selectCommunityData()
          else if (this.buildings.length) await this.select(this.buildings[0].id)
          else {
            this.selectedId = null; this.detail = {}; this.token = ''; this.range = null
            if (this.chart) { this.chart.dispose(); this.chart = null }
          }
        } else await this.loadDetail()
      } finally { this.loading = false }
    },
    async select(id) {
      if (this.chart) { this.chart.dispose(); this.chart = null }
      this.selectedId = id; this.token = ''; this.range = null; this.detail = {}
      this.$emit('scope-change', 'building')
      await this.loadDetail()
    },
    selectCommunityData() {
      if (this.chart) { this.chart.dispose(); this.chart = null }
      this.selectedId = null; this.detail = {}; this.token = ''; this.range = null; this.detailLoading = false
      this.$nextTick(() => this.$emit('scope-change', 'community'))
    },
    async loadDetail(page) {
      if (!this.selectedId) return
      const id = this.selectedId
      const params = Object.assign({ page: page || this.detail.page || 1, size: 100 }, this.range ? { from: this.range[0].toISOString(), to: this.range[1].toISOString() } : {})
      this.detailLoading = true
      try {
        const result = await api.getBuilding(id, params)
        if (id !== this.selectedId) return
        if (result.ok) { this.detail = result.data; this.renderChart() }
      } finally { if (id === this.selectedId) this.detailLoading = false }
    },
    async loadMeasurementPage(page) {
      if (!this.selectedId) return
      const id=this.selectedId, params=Object.assign({ page: page || 1, size: 100 },this.range ? { from:this.range[0].toISOString(),to:this.range[1].toISOString() } : {})
      this.detailLoading=true
      try { const result=await api.getBuildingMeasurements(id,params); if(id!==this.selectedId)return; if(result.ok){this.detail=Object.assign({},this.detail,result.data);this.renderChart()} }
      finally { if(id===this.selectedId)this.detailLoading=false }
    },
    edit(building) {
      if (!this.equipmentTemplate.electrical_storage) return this.$message.error('设备参数模板未加载，请刷新页面')
      this.form = Object.assign(defaults(), JSON.parse(JSON.stringify(building || {})))
      if (this.communityId) Object.assign(this.form, { communityId: this.communityId, timezone: this.community.timezone, intervalSeconds: this.community.intervalSeconds, currency: this.community.currency, timestampKind: this.community.timestampKind })
      this.legacyEditing = !!(building && !building.devices)
      this.equipmentOrigin = building && building.devices ? '建筑设备配置' : ''
      if (!this.form.devices) {
        this.$set(this.form, 'devices', JSON.parse(JSON.stringify(this.equipmentTemplate)))
        if (building) {
          this.$set(this.form.devices, 'heating_device', JSON.parse(JSON.stringify(this.equipmentTemplate.cooling_device)))
          const attrs = this.form.devices.electrical_storage.attributes
          Object.assign(attrs, { capacity: building.batteryCapacity, nominal_power: building.batteryPower, efficiency: building.batteryEfficiency })
          this.form.devices.pv.attributes.nominal_power = building.pvPower
          this.form.devices.dhw_device.attributes.efficiency = building.dhwEfficiency
        }
      }
      this.equipmentRevision++; this.editVisible = true
    },
    async save() {
      if (!this.form.name.trim()) return this.$message.warning('请填写建筑名称')
      try { this.form.devices = this.$refs.equipmentEditor.configuration() } catch (error) { return this.$message.error(error.message) }
      this.saving = true
      try {
        const result = await (this.communityId && !this.form.id ? communityApi.createBuilding(this.communityId, this.form) : api.saveBuilding(this.form.id, this.form))
        if (result.ok) { this.editVisible = false; await this.refresh(); await this.select(result.data.id); this.$message.success('建筑已保存') }
        if (result.ok) this.$emit('changed')
      } finally { this.saving = false }
    },
    async removeBuilding() {
      const id = this.selectedId
      const name = this.detail.building.name
      try {
        await this.$confirm(`删除“${name}”后，将从列表移除，接入令牌失效，其数据集不再用于新任务。历史数据和实验记录保留供追溯。`, '删除建筑', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
      } catch (_) { return }
      const result = await api.deleteBuilding(id)
      if (result.ok) { await this.refresh(); this.$emit('changed'); this.$message.success('建筑已删除') }
    },
    async removeVersion(version) {
      const id = this.selectedId
      try {
        await this.$confirm(`删除“${version.name}”后，将从发布列表移除，并停止下载及用于新任务。历史实验记录保留供追溯。`, '删除数据集', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
      } catch (_) { return }
      const result = await api.deleteVersion(id, version.id)
      if (result.ok) {
        if (this.selectedId === id) await this.loadDetail()
        this.$message.success('数据集已删除')
      }
    },
    async newToken() {
      if (this.detail.building.hasToken) {
        try { await this.$confirm('旧令牌将立即失效，已连接设备需要更换令牌。', '轮换接入令牌', { type: 'warning' }) }
        catch (_) { return }
      }
      const result = await api.rotateToken(this.selectedId)
      if (result.ok) { this.token = result.data.token; await this.loadDetail() }
    },
    async copy(value) {
      try { await navigator.clipboard.writeText(value); this.$message.success('已复制') }
      catch (_) { this.$message.warning('请从输入框手动选择令牌') }
    },
    download(content, name, type) {
      const url = URL.createObjectURL(new Blob([content], { type }))
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
    downloadTemplate() {
      const fields = ['timestamp', ...this.fields.map(f => f.key)]
      this.download('\ufeff' + Papa.unparse({ fields, data: [] }), 'building_measurements.csv', 'text/csv;charset=utf-8')
    },
    downloadBundle(version) { window.location.assign(`/api/web/buildings/${this.selectedId}/versions/${version.id}/bundle`) },
    openImport() {
      this.importRows = []; this.importNames = []; this.importColumns = []; this.sourceFiles = []; this.importError = ''
      this.generateTime = false; this.generatedStart = ''; this.generatedTimeKind = ''; this.importVisible = true
    },
    async readFiles(event) {
      const files = Array.from(event.target.files || [])
      event.target.value = ''
      this.importError = ''; this.importRows = []; this.importColumns = []; this.sourceFiles = []; this.importNames = files.map(f => f.name)
      try {
        if (!files.length) return
        if (files.length > 8 || files.reduce((sum, file) => sum + file.size, 0) > 40 * 1024 * 1024) throw new Error('每批最多8个文件，合计最多40 MB')
        if (files.some(f => f.size > 20 * 1024 * 1024)) throw new Error('单文件最多 20 MB')
        const parsed = await Promise.all(files.map(file => new Promise((resolve, reject) => {
          Papa.parse(file, { header: true, skipEmptyLines: 'greedy', complete: resolve, error: reject })
        })))
        const length = parsed[0].data.length
        if (!length || length > 10000) throw new Error('每批需要 1–10000 行；更大文件请按连续时间分批')
        const merged = Array.from({ length }, () => ({}))
        const columns = []
        for (const file of parsed) {
          if (file.errors.length) throw new Error(file.errors[0].message)
          if (file.data.length !== length) throw new Error('多个文件必须逐行对齐且行数相同')
          for (const column of file.meta.fields) {
            if (columns.includes(column)) throw new Error('多个文件有重复列: ' + column)
            columns.push(column)
          }
          file.data.forEach((row, index) => Object.assign(merged[index], row))
        }
        this.sourceFiles = await Promise.all(files.map(async file => {
          const bytes = new Uint8Array(await file.arrayBuffer()), chunks = []
          for (let offset = 0; offset < bytes.length; offset += 32768) chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32768)))
          return { name: file.name, base64: btoa(chunks.join('')) }
        }))
        this.importRows = merged; this.importColumns = columns
        const mapping = {}; const units = {}
        for (const field of [{ key: 'timestamp' }, ...this.fields]) {
          mapping[field.key] = columns.find(c => c.toLowerCase().replace(/\s/g, '_') === field.key) || ''
          if (field.unit) units[field.key] = field.unit
        }
        if (!mapping.timestamp) mapping.timestamp = columns.find(c => ['time', 'datetime', 'date'].includes(c.toLowerCase())) || ''
        this.mapping = mapping; this.units = units; this.generateTime = !mapping.timestamp
      } catch (e) { this.importError = e.message }
    },
    async submitImport() {
      this.importError = ''
      if (!this.generateTime && !this.mapping.timestamp) return this.$message.warning('请映射时间戳')
      if (this.generateTime && !this.generatedStart) return this.$message.warning('请填写起始时间')
      if (this.generateTime && !this.generatedTimeKind) return this.$message.warning('请确认时间轴来源')
      const mapping = Object.fromEntries(Object.entries(this.mapping).filter(([, value]) => value))
      const rows = this.importRows.map(row => Object.assign({}, row))
      if (this.generateTime) {
        // Keep naive local ISO strings for server-side timezone/DST validation.
        const start = new Date(this.generatedStart + 'Z').getTime()
        rows.forEach((row, index) => { row.__timestamp = new Date(start + index * this.detail.building.intervalSeconds * 1000).toISOString().slice(0, 19) })
        mapping.timestamp = '__timestamp'
      }
      this.importing = true
      try {
        const result = await api.ingestHistory(this.selectedId, { rows, mapping, units: this.units, sourceFiles: this.sourceFiles,
          timestampKind: this.generateTime ? this.generatedTimeKind : (this.detail.building.timestampKind || 'measured') })
        if (result.ok) {
          this.importVisible = false; this.$message.success(`新增 ${result.data.inserted} 条，补齐 ${result.data.updated} 条，重复 ${result.data.duplicates} 条`)
          await this.refresh()
        } else this.importError = result.message
      } finally { this.importing = false }
    },
    resize() { if (this.chart) this.chart.resize() },
    renderChart() {
      this.$nextTick(() => {
        if (!this.$refs.chart || this.tab !== 'measurements') return
        if (!this.chart || this.chart.isDisposed()) this.chart = echarts.init(this.$refs.chart)
        const samples = this.detail.samples || []
        const field = this.fields.find(f => f.key === this.chartField)
        this.chart.setOption({ animation: false, grid: { left: 64, right: 20, top: 25, bottom: 55 },
          tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: samples.map(r => this.time(r.timestamp)), axisLabel: { hideOverlap: true } },
          yAxis: { type: 'value', name: field ? field.unit : '', scale: true },
          dataZoom: [{ type: 'inside' }], series: [{ type: 'line', showSymbol: samples.length < 20,
            connectNulls: false, data: samples.map(r => r[this.chartField] === undefined ? null : r[this.chartField]), lineStyle: { color: themeColor('primary-color') }, itemStyle: { color: themeColor('primary-color') } }]
        }, true); this.chart.resize()
      })
    }
  }
}
</script>

<style scoped>
.building-page { min-height: 100%; min-width: 0; color: var(--primary-text-color); padding: 20px var(--space-5) var(--space-6); }
.building-page.embedded { padding: 0; }
.building-header, .detail-title, .section-toolbar, .chart-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.building-header { margin-bottom: 20px; }
h1 { font-size: 22px; margin: 0 0 6px; font-weight: 600; }
h2 { font-size: 20px; margin: 0 0 8px; }
h3 { font-size: 15px; margin: 22px 0 12px; }
.muted { font-size: 12px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar .el-button + .el-button { margin-left: 0; }
.data-filters { min-width: 0; max-width: 100%; }
.building-workspace { display: grid; grid-template-columns: 238px minmax(0, 1fr); min-height: 680px; }
.building-list { padding: 0 16px 16px 0; border-right: 1px solid var(--divider-color); min-width: 0; }
.building-item { width: 100%; display: flex; text-align: left; gap: 10px; padding: 16px 10px; margin-top: 8px; border: 0; border-left: 3px solid transparent; background: transparent; cursor: pointer; color: var(--primary-text-color); border-radius: 4px; }
.building-item:hover { background: var(--ha-hover-background); }
.building-item.selected { background: var(--sidebar-selected-background); border-left-color: var(--primary-color); }
.building-item > i { font-size: 21px; margin-top: 2px; color: var(--secondary-text-color); }
.building-item span { min-width: 0; }
.building-item strong, .building-item small { display: block; overflow-wrap: anywhere; }
.building-item strong { font-size: 14px; }
.building-item small { color: var(--secondary-text-color); font-size: 11px; margin-top: 6px; }
.building-detail { padding: 0 0 0 24px; min-width: 0; }
.section-toolbar { margin: 16px 0; }
.coverage { margin: 12px 0; }
.chart-toolbar { margin-top: 20px; }
.measurement-chart { height: 240px; width: 100%; }
.danger { color: var(--error-color); }
.wrap-code { overflow-wrap: anywhere; white-space: normal; }
.request-example { background: var(--input-fill-color); color: var(--primary-text-color); font-size: 12px; padding: 16px; overflow: auto; max-height: 350px; border: 1px solid var(--divider-color); border-radius: 4px; white-space: pre-wrap; overflow-wrap: anywhere; }
.token-input { max-width: 420px; margin: 14px 10px 14px 0; }
.building-form { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); column-gap: 20px; }
.building-form .el-input-number, .building-form .el-select { width: 100%; }
.full-width { grid-column: 1 / -1; }
.file-picker { display: inline-flex; gap: 8px; align-items: center; border: 1px solid var(--primary-color); color: var(--primary-color); padding: 9px 14px; border-radius: 4px; font-size: 13px; cursor: pointer; }
.file-picker input { display: none; }
.import-clock { margin-top: 20px; }
.log-output { background: var(--input-fill-color); color: var(--success-color); }
.publication-dialog /deep/ .el-dialog{max-width:calc(100% - 24px)}.publication-dialog .el-date-editor{width:100%;max-width:100%}
@media(max-width: 1000px) {
  .building-workspace { grid-template-columns: 190px minmax(0,1fr); }
  .building-detail { padding-left: 16px; }
}
@media(max-width: 680px) {
  .building-page { padding: var(--space-4); }
  .building-page.embedded { padding: 0; }
  .building-workspace { display: block; }
  .building-list { border-right: 0; border-bottom: 1px solid var(--divider-color); padding-right: 0; max-height: 200px; overflow-y: auto; }
  .building-detail { padding-left: 0; }
  .building-form { grid-template-columns: 1fr; }
  .building-page /deep/ .el-dialog { width: calc(100% - 24px) !important; }
  .building-page /deep/ .el-date-editor { max-width: 100%; }
}
.data-pagination{display:flex;justify-content:flex-end;margin:12px 0}
</style>
