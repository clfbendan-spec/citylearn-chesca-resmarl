<template>
  <div class="field-summary">
    <div class="summary-counts"><span v-for="status in statuses" :key="status.key">{{ status.label }} {{ fields.filter(field => field.status === status.key).length }}</span></div>
    <el-collapse><el-collapse-item title="字段处理明细" name="fields">
      <el-table :data="fields" size="mini" max-height="260">
        <el-table-column prop="label" label="字段" min-width="180" />
        <el-table-column label="处理" width="80"><template slot-scope="s"><el-tag size="mini" :type="s.row.status === 'missing' ? 'danger' : s.row.status === 'preserved' ? 'success' : 'info'">{{ label(s.row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="已提供" width="100"><template slot-scope="s">{{ s.row.present }} / {{ s.row.total }}</template></el-table-column>
        <el-table-column v-if="fields.some(field => field.generated !== undefined)" label="模拟补齐" width="90"><template slot-scope="s">{{ s.row.generated === undefined ? '—' : s.row.generated }}</template></el-table-column>
      </el-table>
    </el-collapse-item></el-collapse>
  </div>
</template>
<script>
export default {
  name: 'PublicationFieldSummary',
  props: { fields: { type: Array, default: () => [] } },
  data: () => ({ statuses: [{ key: 'preserved', label: '保留' }, { key: 'generated', label: '生成' }, { key: 'mixed', label: '部分补齐' }, { key: 'disabled', label: '禁用' }, { key: 'missing', label: '缺失' }] }),
  methods: { label(key) { return (this.statuses.find(status => status.key === key) || {}).label || key } }
}
</script>
<style scoped>
.summary-counts{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;margin:14px 0}.field-summary{min-width:0}.field-summary /deep/ .el-collapse-item__header{font-size:13px}
</style>
