<template>
  <el-dialog title="发布社区数据集" :visible="visible" width="900px" :close-on-click-modal="false" class="community-dialog" @close="$emit('update:visible', false)">
    <div v-loading="loading" class="community-publisher">
      <el-form v-if="canWrite" label-position="top" size="small" @submit.native.prevent>
        <el-form-item label="数据集名称"><el-input v-model="name" maxlength="160" label="社区数据集名称" /></el-form-item>
        <el-form-item label="建筑">
          <el-select v-model="selectedIds" multiple filterable :multiple-limit="20" placeholder="选择建筑" aria-label="选择社区建筑">
            <el-option v-for="building in availableBuildings" :key="building.id" :label="building.name" :value="building.id" />
          </el-select>
        </el-form-item>
        <div v-for="building in selectedBuildings" :key="building.id" class="source-row">
          <el-form-item :label="building.name + ' · 已发布数据集'">
            <el-select v-model="versions[building.id]" :aria-label="building.name + '的数据集'">
              <el-option v-for="source in optionsFor(building.id)" :key="source.versionId" :label="source.versionName" :value="source.versionId" />
            </el-select>
          </el-form-item>
          <div v-if="chosen(building.id)" class="source-time">{{ time(chosen(building.id).startTime) }} 至 {{ time(chosen(building.id).endTime) }}</div>
        </div>
        <el-alert v-if="selectedIds.length >= 2 && !intersection" title="所选数据集没有至少两个完整小时的共同时间段" type="warning" :closable="false" />
        <template v-if="intersection">
          <div class="intersection"><span>共同时间范围</span><strong>{{ time(intersection.start) }} 至 {{ time(intersection.end) }}</strong></div>
          <el-form-item label="发布时间范围">
            <el-date-picker v-model="range" type="datetimerange" :picker-options="{ disabledDate }" start-placeholder="开始时间" end-placeholder="结束时间" format="yyyy-MM-dd HH:mm" />
          </el-form-item>
        </template>
        <el-alert v-if="preview" :title="preview.ready ? '发布条件满足' : preview.blocker" :type="preview.ready ? 'success' : 'error'" :closable="false" />
        <template v-if="preview && preview.ready">
          <div class="intersection"><span>共享观察量：{{ preview.sharedObservations.length }} 项</span></div>
          <el-collapse><el-collapse-item v-for="(building, index) in preview.buildings" :key="index" :title="building.buildingName" :name="index"><publication-field-summary :fields="building.fields" /><span v-if="!building.fields.length">旧版本未记录字段处理摘要</span></el-collapse-item></el-collapse>
        </template>
        <div class="publish-action"><el-button icon="el-icon-view" :disabled="!validRange" :loading="previewing" @click="check">检查发布内容</el-button><el-button type="primary" icon="el-icon-s-promotion" :disabled="!validRange || !name.trim() || !preview || !preview.ready || previewing" :loading="publishing" @click="publish">发布</el-button></div>
      </el-form>
      <h3>已发布社区数据集</h3>
      <el-table :data="releases" size="small" max-height="300">
        <el-table-column prop="name" label="数据集" min-width="180" show-overflow-tooltip />
        <el-table-column prop="buildingCount" label="建筑数" width="75" />
        <el-table-column label="时间范围" min-width="180"><template slot-scope="s">{{ time(s.row.startTime) }}<br>{{ time(s.row.endTime) }}</template></el-table-column>
        <el-table-column label="创建时间" min-width="165"><template slot-scope="s">{{ time(s.row.createTime) }}</template></el-table-column>
        <el-table-column label="操作" width="100"><template slot-scope="s">
          <el-tooltip content="下载社区数据集"><el-button type="text" icon="el-icon-download" aria-label="下载社区数据集" @click="download(s.row)" /></el-tooltip>
          <el-tooltip v-if="canWrite" content="删除社区数据集"><el-button type="text" icon="el-icon-delete" class="delete-button" aria-label="删除社区数据集" @click="remove(s.row)" /></el-tooltip>
        </template></el-table-column>
      </el-table>
      <el-empty v-if="!loading && !releases.length" description="暂无已发布社区数据集" :image-size="55" />
    </div>
    <div slot="footer"><el-button @click="$emit('update:visible', false)">关闭</el-button></div>
  </el-dialog>
</template>

<script>
import * as api from '../api/building'
import PublicationFieldSummary from './PublicationFieldSummary.vue'
export default {
  name: 'CommunityDatasetPublisher',
  components: { PublicationFieldSummary },
  props: { visible: Boolean, canWrite: Boolean },
  data: () => ({ loading: false, publishing: false, sources: [], releases: [], name: '', selectedIds: [], versions: {}, range: null, preview: null, previewing: false }),
  computed: {
    availableBuildings() {
      const buildings = new Map()
      this.sources.forEach(source => buildings.set(source.buildingId, { id: source.buildingId, name: source.buildingName }))
      return Array.from(buildings.values())
    },
    selectedBuildings() { return this.selectedIds.map(id => this.availableBuildings.find(building => building.id === id)).filter(Boolean) },
    selectedSources() { return this.selectedIds.map(id => this.chosen(id)).filter(Boolean) },
    selectionKey() { return this.selectedSources.map(source => source.versionId).join(',') },
    previewKey() { return JSON.stringify([this.selectionKey, this.range]) },
    intersection() {
      if (this.selectedIds.length < 2 || this.selectedSources.length !== this.selectedIds.length) return null
      const start = Math.max(...this.selectedSources.map(source => new Date(source.startTime).getTime()))
      const end = Math.min(...this.selectedSources.map(source => new Date(source.endTime).getTime()))
      return end - start >= 7200000 ? { start, end } : null
    },
    validRange() {
      if (!this.intersection || !this.range || this.range.length !== 2) return false
      const [start, end] = this.range.map(value => new Date(value).getTime())
      return start >= this.intersection.start && end <= this.intersection.end && end - start >= 7200000 &&
        (start - this.intersection.start) % 3600000 === 0 && (end - start) % 3600000 === 0
    }
  },
  watch: {
    visible(value) { if (value) this.open() },
    previewKey() { this.preview = null },
    selectedIds(ids) {
      const versions = {}
      ids.forEach(id => { versions[id] = this.versions[id] || (this.optionsFor(id)[0] || {}).versionId })
      this.versions = versions
    },
    selectionKey() { this.range = this.intersection ? [new Date(this.intersection.start), new Date(this.intersection.end)] : null }
  },
  methods: {
    time(value) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) },
    optionsFor(id) { return this.sources.filter(source => source.buildingId === id) },
    chosen(id) { return this.sources.find(source => source.buildingId === id && source.versionId === this.versions[id]) },
    disabledDate(date) {
      if (!this.intersection) return true
      const end = new Date(date); end.setHours(23, 59, 59, 999)
      return end.getTime() < this.intersection.start || date.getTime() > this.intersection.end
    },
    async open() {
      this.loading = true; this.selectedIds = []; this.versions = {}; this.range = null; this.name = ''; this.preview = null
      try {
        const [sources, releases] = await Promise.all([api.communitySources(), api.communityDatasets()])
        this.sources = sources.ok ? sources.data : []; this.releases = releases.ok ? releases.data : []
      } finally { this.loading = false }
    },
    request() { return { name: this.name.trim(), sources: this.selectedSources.map(source => ({ buildingId: source.buildingId, versionId: source.versionId })), from: this.range[0].toISOString(), to: this.range[1].toISOString() } },
    async check() {
      if (!this.validRange) return
      const key = this.previewKey
      this.previewing = true; this.preview = null
      try { const result = await api.previewCommunity(this.request()); if (result.ok && key === this.previewKey) this.preview = result.data } finally { this.previewing = false }
    },
    async publish() {
      if (!this.validRange || !this.name.trim() || !this.preview || !this.preview.ready) return
      this.publishing = true
      try {
        const result = await api.publishCommunity(this.request())
        if (result.ok) {
          this.$message.success('社区数据集已发布')
          const releases = await api.communityDatasets(); if (releases.ok) this.releases = releases.data
        }
      } finally { this.publishing = false }
    },
    download(release) { window.location.assign(`/api/web/buildings/community-datasets/${release.id}/bundle`) },
    async remove(release) {
      try { await this.$confirm(`删除“${release.name}”后将停止用于新任务，历史文件保留供追溯。`, '删除社区数据集', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch (_) { return }
      const result = await api.deleteCommunity(release.id)
      if (result.ok) { this.releases = this.releases.filter(item => item.id !== release.id); this.$message.success('社区数据集已删除') }
    }
  }
}
</script>

<style scoped>
.community-publisher{min-width:0}.community-publisher .el-select,.community-publisher .el-date-editor{width:100%;max-width:100%}.community-publisher h3{font-size:15px;margin:28px 0 16px}.source-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:center;border-bottom:1px solid var(--divider-color);margin-bottom:12px}.source-row .el-form-item{min-width:0;margin-bottom:12px}.source-time{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.intersection{padding:16px 0;display:flex;flex-direction:column;gap:8px;font-size:13px}.intersection strong{font-weight:500;overflow-wrap:anywhere}.publish-action{display:flex;justify-content:flex-end;margin-top:16px}.delete-button{color:var(--error-color)}.community-dialog /deep/ .el-dialog{max-width:calc(100% - 24px)}@media(max-width:680px){.source-row{grid-template-columns:1fr;gap:0}.source-time{padding-bottom:12px}.community-dialog /deep/ .el-dialog__body{padding:16px}.community-publisher /deep/ .el-range-input{font-size:11px;min-width:0}.community-publisher /deep/ .el-range-separator{padding:0;width:20px}}
</style>
