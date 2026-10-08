<template>
  <div class="data-list-page ha-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">原始数据</h1>
        <p class="page-desc">
          
        </p>
      </div>
      
    </header>

    <el-card shadow="never" class="ha-surface filter-card">
      <div class="filter-toolbar">
        <div class="filter-field filter-field-dataset">
          <label class="filter-label">数据集</label>
          <el-select
            v-model="datasetSchema"
            filterable
            size="small"
            class="filter-select filter-select-wide"
            :loading="datasetLoading"
            placeholder="选择本地数据集"
            @change="onDatasetChange"
          >
            <el-option
              v-for="item in datasetOptions"
              :key="item.schemaKey"
              :label="item.displayName"
              :value="item.schemaKey"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label class="filter-label">建筑</label>
          <el-select v-model="buildingId" size="small" class="filter-select" @change="handleChange">
            <el-option
              v-for="b in buildingOptions"
              :key="b.value"
              :label="b.label"
              :value="b.value"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label class="filter-label">日期</label>
          <el-date-picker
            v-model="dateValue"
            type="date"
            size="small"
            placeholder="全部日期"
            value-format="yyyy-MM-dd"
            clearable
            class="filter-select filter-date"
          />
        </div>
        <div class="filter-field">
          <label class="filter-label">小时</label>
          <el-select v-model="hourValue" size="small" placeholder="全部" clearable class="filter-select filter-select-sm">
            <el-option
              v-for="item in hourOptions"
              :key="'h-' + item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label class="filter-label">星期</label>
          <el-select v-model="dayTypeValue" size="small" placeholder="全部" clearable class="filter-select filter-select-sm">
            <el-option
              v-for="item in dayTypeOptions"
              :key="'d-' + item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </div>
        <div class="filter-actions">
          <el-button type="primary" size="small" icon="el-icon-search" @click="handleChange">搜索</el-button>
          <el-button size="small" icon="el-icon-refresh" @click="resetFilters">重置</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="ha-surface table-card">
   
      <div class="table-wrap" v-loading="loading">
        <el-table
          :data="pagedTableData"
          class="data-table"
          stripe
          :height="tableHeight"
          :header-cell-style="headerCellStyle"
        >
          <el-table-column
            prop="date"
            label="日期"
            width="120"
            fixed="left"
          />
          <el-table-column
            prop="hour"
            label="小时"
            width="72"
            fixed="left"
          />
          <el-table-column
            prop="dayType"
            label="星期"
            width="96"
            fixed="left"
            :formatter="formatDayType"
          />
          <el-table-column
            prop="daylightSavingsStatus"
            label="是否处于夏令时"
            min-width="120"
            :formatter="formatDaylightStatus"
          />
          <el-table-column
            v-for="col in metricColumns"
            :key="col.prop"
            :prop="col.prop"
            :label="col.label"
            :min-width="col.minWidth"
            :formatter="col.formatter"
          />
        </el-table>
      </div>
      <div class="table-pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :current-page.sync="currentPage"
          :page-size.sync="pageSize"
          :page-sizes="[24, 48, 96, 192]"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script>
import axios from 'axios'

const HVAC_MODE_LABELS = {
  0: '关闭',
  1: '制冷',
  2: '供暖'
}

function formatFixed3(value) {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(3)
}

function makeDecimalFormatter() {
  return (row, column, cellValue) => formatFixed3(cellValue)
}

function formatOccupant(row, column, cellValue) {
  if (cellValue == null || cellValue === '') return '—'
  const n = Number(cellValue)
  if (!Number.isFinite(n)) return '—'
  return String(Math.round(n))
}

function formatHvacMode(row, column, cellValue) {
  if (cellValue == null || cellValue === '') return '—'
  const key = Math.round(Number(cellValue))
  return HVAC_MODE_LABELS[key] != null ? HVAC_MODE_LABELS[key] : String(cellValue)
}

/** 度量列：表头带单位；小数值保留 3 位（月/时/星期/夏令时除外） */
const METRIC_COLUMNS = [
  { prop: 'indoorDryBulbTemperature', label: '室内干球温度 (°C)', minWidth: 140 },
  {
    prop: 'averageUnmetCoolingSetpointDifference',
    label: '平均未满足冷却设定点温差 (°C)',
    minWidth: 200
  },
  { prop: 'indoorRelativeHumidity', label: '室内相对湿度 (%)', minWidth: 140 },
  { prop: 'nonShiftableLoad', label: '电器当前消耗电量 (kWh)', minWidth: 160 },
  { prop: 'dhwDemand', label: '供热需求 (kWh)', minWidth: 120 },
  { prop: 'coolingDemand', label: '制冷需求 (kWh)', minWidth: 120 },
  { prop: 'heatingDemand', label: '供暖需求 (kWh)', minWidth: 120 },
  { prop: 'solarGeneration', label: '光伏发电量 (W/kW)', minWidth: 140 },
  {
    prop: 'occupantCount',
    label: '建筑内人员数量 (人)',
    minWidth: 140,
    formatter: formatOccupant
  },
  {
    prop: 'indoorDryBulbTemperatureCoolingSetPoint',
    label: '室内干球温度制冷设定点 (°C)',
    minWidth: 190
  },
  {
    prop: 'indoorDryBulbTemperatureHeatingSetPoint',
    label: '室内干球温度制热设定点 (°C)',
    minWidth: 190
  },
  {
    prop: 'hvacMode',
    label: '暖通模式',
    minWidth: 100,
    formatter: formatHvacMode
  },
  {
    prop: 'carbonIntensity',
    label: '二氧化碳排放率 (kgCO₂/kWh)',
    minWidth: 190
  },
  { prop: 'electricityPricing', label: '单位电价 ($/kWh)', minWidth: 130 },
  { prop: 'electricityPricingPredicted1', label: '预测电价1 ($/kWh)', minWidth: 140 },
  { prop: 'electricityPricingPredicted2', label: '预测电价2 ($/kWh)', minWidth: 140 },
  { prop: 'electricityPricingPredicted3', label: '预测电价3 ($/kWh)', minWidth: 140 },
  { prop: 'outdoorDryBulbTemperature', label: '室外干球温度 (°C)', minWidth: 140 },
  { prop: 'outdoorRelativeHumidity', label: '室外相对湿度 (%)', minWidth: 140 },
  { prop: 'diffuseSolarIrradiance', label: '散射太阳辐照度 (W/m²)', minWidth: 160 },
  { prop: 'directSolarIrradiance', label: '直接太阳辐照度 (W/m²)', minWidth: 160 },
  {
    prop: 'outdoorDryBulbTemperaturePredicted1',
    label: '室外干球温度预测1 (°C)',
    minWidth: 170
  },
  {
    prop: 'outdoorDryBulbTemperaturePredicted2',
    label: '室外干球温度预测2 (°C)',
    minWidth: 170
  },
  {
    prop: 'outdoorDryBulbTemperaturePredicted3',
    label: '室外干球温度预测3 (°C)',
    minWidth: 170
  },
  {
    prop: 'outdoorRelativeHumidityPredicted1',
    label: '室外相对湿度预测1 (%)',
    minWidth: 170
  },
  {
    prop: 'outdoorRelativeHumidityPredicted2',
    label: '室外相对湿度预测2 (%)',
    minWidth: 170
  },
  {
    prop: 'outdoorRelativeHumidityPredicted3',
    label: '室外相对湿度预测3 (%)',
    minWidth: 170
  },
  {
    prop: 'diffuseSolarIrradiancePredicted1',
    label: '漫射太阳辐照度预测1 (W/m²)',
    minWidth: 190
  },
  {
    prop: 'diffuseSolarIrradiancePredicted2',
    label: '漫射太阳辐照度预测2 (W/m²)',
    minWidth: 190
  },
  {
    prop: 'diffuseSolarIrradiancePredicted3',
    label: '漫射太阳辐照度预测3 (W/m²)',
    minWidth: 190
  },
  {
    prop: 'directSolarIrradiancePredicted1',
    label: '直射太阳辐照度预测1 (W/m²)',
    minWidth: 190
  },
  {
    prop: 'directSolarIrradiancePredicted2',
    label: '直射太阳辐照度预测2 (W/m²)',
    minWidth: 190
  },
  {
    prop: 'directSolarIrradiancePredicted3',
    label: '直射太阳辐照度预测3 (W/m²)',
    minWidth: 190
  }
].map((col) => ({
  ...col,
  formatter: col.formatter || makeDecimalFormatter()
}))

export default {
  name: 'DataList',
  data() {
    return {
      metricColumns: METRIC_COLUMNS,
      allRows: [],
      buildingId: 'building1',
      datasetSchema: 'citylearn_challenge_2023_phase_2_local_evaluation',
      datasetOptions: [],
      datasetLoading: false,
      dateValue: '',
      dayTypeValue: '',
      dayTypeOptions: [
        { value: '', label: '全部' },
        { value: '1', label: '星期一' },
        { value: '2', label: '星期二' },
        { value: '3', label: '星期三' },
        { value: '4', label: '星期四' },
        { value: '5', label: '星期五' },
        { value: '6', label: '星期六' },
        { value: '7', label: '星期天' }
      ],
      hourValue: '',
      hourOptions: [
        { value: '', label: '全部' },
        ...Array.from({ length: 24 }, (_, i) => ({
          value: String(i + 1),
          label: String(i + 1)
        }))
      ],
      loading: false,
      pageSize: 24,
      currentPage: 1,
      total: 0,
      tableHeight: 560,
      headerCellStyle: {
        background: 'var(--input-fill-color)',
        color: 'var(--primary-text-color)',
        fontWeight: '500'
      }
    }
  },
  computed: {
    selectedDataset() {
      return this.datasetOptions.find((d) => d.schemaKey === this.datasetSchema) || null
    },
    datasetSchemaLabel() {
      return (this.selectedDataset && this.selectedDataset.displayName) || this.datasetSchema || '—'
    },
    buildingOptions() {
      const n = Math.max(
        1,
        Number((this.selectedDataset && this.selectedDataset.buildingCount) || 3)
      )
      return Array.from({ length: n }, (_, i) => ({
        value: `building${i + 1}`,
        label: `建筑 ${i + 1}`
      }))
    },
    pagedTableData() {
      const start = (this.currentPage - 1) * this.pageSize
      return this.allRows.slice(start, start + this.pageSize)
    }
  },
  created() {
    this.initPage()
  },
  mounted() {
    this.updateTableHeight()
    window.addEventListener('resize', this.updateTableHeight)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.updateTableHeight)
  },
  methods: {
    async initPage() {
      await this.loadDatasetOptions()
      await this.fetchData()
    },
    async loadDatasetOptions() {
      this.datasetLoading = true
      try {
        const response = await axios.get('/api/web/basedata/getDatasetList')
        if (!response.data || response.data.code !== 0) {
          throw new Error((response.data && response.data.message) || '加载数据集列表失败')
        }
        const list = Array.isArray(response.data.data) ? response.data.data : []
        this.datasetOptions = list
        if (!list.some((d) => d.schemaKey === this.datasetSchema) && list.length) {
          this.datasetSchema = list[0].schemaKey
        }
        this.ensureBuildingInRange()
      } catch (e) {
        console.error(e)
        this.$message.error((e && e.message) || '加载数据集列表失败，请确认已执行 citylearn_dataset.sql')
      } finally {
        this.datasetLoading = false
      }
    },
    ensureBuildingInRange() {
      const ok = this.buildingOptions.some((b) => b.value === this.buildingId)
      if (!ok) this.buildingId = this.buildingOptions[0].value
    },
    onDatasetChange() {
      this.ensureBuildingInRange()
      this.currentPage = 1
      this.fetchData()
    },
    updateTableHeight() {
      this.$nextTick(() => {
        const wrap = this.$el && this.$el.querySelector('.table-wrap')
        if (!wrap) {
          this.tableHeight = Math.max(420, window.innerHeight - 360)
          return
        }
        const top = wrap.getBoundingClientRect().top
        // 预留底部分页条 + 页面边距
        const bottomPad = 96
        this.tableHeight = Math.max(360, Math.floor(window.innerHeight - top - bottomPad))
      })
    },
    formatDayType(row, column, cellValue) {
      const map = {
        1: '星期一',
        2: '星期二',
        3: '星期三',
        4: '星期四',
        5: '星期五',
        6: '星期六',
        7: '星期天'
      }
      return map[cellValue] || ''
    },
    formatDaylightStatus(row, column, cellValue) {
      return cellValue ? '是' : '否'
    },
    fetchData() {
      this.loading = true
      axios
        .get('/api/web/basedata/getList', {
          params: {
            buildingId: this.buildingId,
            datasetSchema: this.datasetSchema,
            date: this.dateValue || undefined,
            dayType: this.dayTypeValue || undefined,
            hour: this.hourValue || undefined
          }
        })
        .then((response) => {
          if (!response.data || response.data.code !== 0) {
            throw new Error((response.data && response.data.message) || '加载失败')
          }
          const rows = Array.isArray(response.data.data) ? response.data.data : []
          this.allRows = rows
          this.total = rows.length
          const maxPage = Math.max(1, Math.ceil(this.total / this.pageSize) || 1)
          if (this.currentPage > maxPage) this.currentPage = maxPage
        })
        .catch((error) => {
          console.error('获取数据失败:', error)
          this.allRows = []
          this.total = 0
          this.$message.error((error && error.message) || '数据加载失败')
        })
        .finally(() => {
          this.loading = false
          this.updateTableHeight()
        })
    },
    handleChange() {
      this.currentPage = 1
      this.fetchData()
    },
    resetFilters() {
      this.dateValue = ''
      this.hourValue = ''
      this.dayTypeValue = ''
      this.currentPage = 1
      this.fetchData()
    },
    handleSizeChange(val) {
      this.pageSize = val
      this.currentPage = 1
      this.updateTableHeight()
    },
    handleCurrentChange(val) {
      this.currentPage = val
    }
  }
}
</script>

<style scoped>
.data-list-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  box-sizing: border-box;
  padding: var(--space-5) var(--space-5) var(--space-6);
  background: var(--primary-background-color);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.page-title {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 400;
  line-height: 1.25;
  color: var(--primary-text-color);
}

.page-desc {
  margin: 0;
  max-width: 640px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--secondary-text-color);
}

.header-meta {
  flex-shrink: 0;
  padding-top: 8px;
}

.result-count {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--primary-color);
  background: rgba(var(--rgb-primary-color), 0.1);
}

.ha-surface {
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
  background: var(--card-background-color);
}

.filter-card >>> .el-card__body {
  padding: var(--space-3) var(--space-4);
}

.filter-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 10px 12px;
  overflow-x: auto;
}

.filter-field {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  min-width: 0;
}

.filter-label {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--secondary-text-color);
  white-space: nowrap;
}

.filter-select {
  width: 112px;
}

.filter-select-sm {
  width: 88px;
}

.filter-select-wide {
  width: 200px;
}

.filter-date {
  width: 136px;
}

.filter-date >>> .el-input {
  width: 136px;
}

.filter-field-dataset {
  min-width: 0;
}

.filter-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  margin-left: auto;
  white-space: nowrap;
}

.table-card {
  overflow: visible;
}

.table-card >>> .el-card__body {
  padding: var(--space-4) var(--space-5) var(--space-5);
}

.table-card-head {
  margin-bottom: var(--space-4);
}

.table-card-title {
  font-size: 16px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--primary-text-color);
}

.table-card-hint {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--secondary-text-color);
}

.table-wrap {
  width: 100%;
  min-height: 360px;
}

.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--divider-color);
}

.table-pagination >>> .el-pagination {
  padding: 0;
  font-weight: 400;
}

.data-table {
  width: 100%;
}

.data-table >>> .el-table .cell {
  font-variant-numeric: tabular-nums;
}

.data-table >>> .el-table__body-wrapper {
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.28) transparent;
}

.data-table >>> .el-table__body-wrapper::-webkit-scrollbar {
  height: 8px;
  width: 8px;
}

.data-table >>> .el-table__body-wrapper::-webkit-scrollbar-track {
  background: transparent;
}

.data-table >>> .el-table__body-wrapper::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.22);
  border-radius: 4px;
}

@media (max-width: 900px) {
  .filter-toolbar {
    gap: 8px;
  }

  .filter-select-wide {
    width: 160px;
  }
}
</style>
