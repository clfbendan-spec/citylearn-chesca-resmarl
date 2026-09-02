<template>
  <div class="chart-card">
    <div class="chart-header">
      <span class="title">{{ title }}</span>
      <div v-if="showInterval" class="interval-controls">
        <!--<label>间隔(分钟):</label>-->
        <!--<el-input-number v-model="intervalInput" :min="baseInterval" :max="60" size="small" />-->
        <!--<el-button size="small" @click="applyInterval">应用</el-button>-->
      </div>
    </div>
    <div ref="chart" class="chart" />
    <date-range-slider
      v-if="rows.length"
      :min-timestamp="minTs"
      :max-timestamp="maxTs"
      :slider-values="sliderValues"
      @change="onSliderChange"
    />
  </div>
</template>

<script>
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import DateRangeSlider from './DateRangeSlider.vue'
import {
  prepareTimeSeries,
  defaultSliderRange,
  baseIntervalMinutes,
  floorToMidnight,
  ceilToEndOfDay
} from '@/utils/chartTime'

const LEGEND_LABELS = {
  '光伏发电量-kWh': '光伏发电量(Energy Production from PV)-kWh',
  '电动汽车发电量-kWh': '电动汽车发电量(Energy Production from EV)-kWh',
  '不可调负荷-kWh': '不可调负荷(Non-shiftable Load)-kWh',
  '净用电量-kWh': '净用电量(Net Electricity Consumption)-kWh',
  'Est. arrival SOC': '预计到达荷电状态(Est. arrival SOC)',
  'Required dep. SOC': '离开所需荷电状态(Required dep. SOC)',
  '电动汽车荷电状态-%': '电动汽车荷电状态(EV SOC)-%',
  '电池荷电状态-%': '电池荷电状态(Battery SOC)-%',
  '充电桩用电量-kWh': '充电桩用电量(Charger Consumption)-kWh',
  '充电桩发电量-kWh': '充电桩发电量(Charger Production)-kWh',
  '电动汽车预计到达时荷电状态-%': '电动汽车预计到达时荷电状态(EV Estimated SOC Arrival)-%',
  '电动汽车离开时所需荷电状态-%': '电动汽车离开时所需荷电状态(EV Required SOC Departure)-%',
  '电池充放电量-kWh': '电池充放电量(Battery (Dis)Charge)-kWh',
  电价: '电价(electricity_pricing)-$/kWh',
  '6小时预测电价': '6小时预测电价(electricity_pricing_predicted_1)-$/kWh',
  '12小时预测电价': '12小时预测电价(electricity_pricing_predicted_2)-$/kWh',
  '24小时预测电价': '24小时预测电价(electricity_pricing_predicted_3)-$/kWh'
}

const PRICING_SERIES = {
  'electricity_pricing-$/kWh': '电价',
  'electricity_pricing_predicted_1-$/kWh': '6小时预测电价',
  'electricity_pricing_predicted_2-$/kWh': '12小时预测电价',
  'electricity_pricing_predicted_3-$/kWh': '24小时预测电价'
}

export default {
  name: 'SimulationChartCard',
  components: { DateRangeSlider },
  props: {
    data: { type: Array, default: () => [] },
    title: { type: String, default: '' },
    chartType: { type: String, required: true }
  },
  data() {
    return {
      chart: null,
      rows: [],
      sliderValues: [0, 0],
      minTs: 0,
      maxTs: 0,
      baseInterval: 1,
      intervalInput: 1,
      timeInterval: 1,
      showInterval: true,
      lastXRows: []
    }
  },
  watch: {
    data: {
      immediate: true,
      handler() {
        this.initRows()
        this.render()
      }
    },
    chartType() {
      this.initRows()
      this.render()
    },
    timeInterval() { this.render() },
    sliderValues() { this.render() }
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    window.addEventListener('resize', this.resize)
    if (typeof ResizeObserver !== 'undefined' && this.$refs.chart) {
      this.resizeObserver = new ResizeObserver(() => this.resize())
      this.resizeObserver.observe(this.$refs.chart)
    }
    this.initRows()
    this.render()
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resize)
    if (this.resizeObserver) this.resizeObserver.disconnect()
    if (this._labelRaf) cancelAnimationFrame(this._labelRaf)
    if (this._onChartFinished) this.chart?.off('finished', this._onChartFinished)
    if (this.chart) this.chart.dispose()
  },
  methods: {
    resize() {
      if (!this.chart) return
      this.chart.resize()
      this.scheduleNoonDateLabels()
    },
    initRows() {
      this.rows = prepareTimeSeries(this.data)
      if (!this.rows.length) return
      this.baseInterval = baseIntervalMinutes(this.rows)
      this.intervalInput = this.baseInterval
      this.timeInterval = this.baseInterval
      this.minTs = floorToMidnight(this.rows[0].timestamp)
      this.maxTs = ceilToEndOfDay(this.rows[this.rows.length - 1].timestamp)
      this.sliderValues = defaultSliderRange(this.rows, this.baseInterval)
      this.showInterval = this.chartType !== 'pv'
    },
    onSliderChange(v) {
      this.sliderValues = v
    },
    applyInterval() {
      const v = Math.max(this.baseInterval, Math.min(60, this.intervalInput || this.baseInterval))
      this.intervalInput = v
      this.timeInterval = v
    },
    filtered() {
      return this.rows.filter(
        (r) => r.timestamp >= this.sliderValues[0] && r.timestamp <= this.sliderValues[1]
      )
    },
    aggregateBar(data, keys, sum = true) {
      if (!data.length) return []
      const out = []
      let start = data[0].timestamp
      let group = []
      const flush = () => {
        if (!group.length) return
        const row = { timestamp: start, 'Time Step': group[0]['Time Step'] }
        keys.forEach((k) => {
          row[k] = sum
            ? group.reduce((s, i) => s + Number(i[k] || 0), 0)
            : group.reduce((s, i) => s + Number(i[k] || 0), 0) / group.length
        })
        out.push(row)
      }
      data.forEach((item) => {
        if (item.timestamp - start < this.timeInterval * 60000) {
          group.push(item)
        } else {
          flush()
          start = item.timestamp
          group = [item]
        }
      })
      flush()
      return out
    },
    aggregateLineAvg(data, keys) {
      return this.aggregateBar(data, keys, false)
    },
    /** -1 表示充电桩未运行，非真实电量，展示为 0 */
    inactiveChargerKwh(value) {
      if (value == null || value === '') return 0
      const n = Number(value)
      return n === -1 ? 0 : (Number.isFinite(n) ? n : 0)
    },
    normalizeChargerRows(data) {
      return data.map((row) => ({
        ...row,
        'Charger Consumption-kWh': this.inactiveChargerKwh(row['Charger Consumption-kWh']),
        'Charger Production-kWh': this.inactiveChargerKwh(row['Charger Production-kWh'])
      }))
    },
    /** SOC 原始值为 0–1 小数，转为 0–100；-1 / -0.1 为无效值 */
    socPercentValue(value) {
      if (value == null || value === '') return null
      const s = String(value)
      if (s === '-1' || s === '-1.00' || s === '-1.0' || s === '-0.1' || s === '-0.10') return null
      const n = Number(value)
      if (!Number.isFinite(n) || n === -1 || n === -0.1) return null
      return Math.abs(n) <= 1 ? n * 100 : n
    },
    normalizeBatterySocRows(data) {
      return data.map((row) => ({
        ...row,
        'Battery Soc-%': this.socPercentValue(row['Battery Soc-%'])
      }))
    },
    normalizeChargerSocRows(data) {
      return data.map((row) => ({
        ...row,
        'EV Estimated SOC Arrival-%': this.socPercentValue(row['EV Estimated SOC Arrival-%']),
        'EV Required SOC Departure-%': this.socPercentValue(row['EV Required SOC Departure-%']),
        'EV SOC-%': this.socPercentValue(row['EV SOC-%'])
      }))
    },
    normalizeEvSocRows(data) {
      return data.map((row) => ({
        ...row,
        electric_vehicle_estimated_soc_arrival: this.socPercentValue(row.electric_vehicle_estimated_soc_arrival),
        electric_vehicle_required_soc_departure: this.socPercentValue(row.electric_vehicle_required_soc_departure),
        electric_vehicle_soc: this.socPercentValue(row.electric_vehicle_soc)
      }))
    },
    groupRowsByDay(rows) {
      const byDay = new Map()
      rows.forEach((r, i) => {
        const dayKey = dayjs(r.timestamp).format('YYYY-MM-DD')
        if (!byDay.has(dayKey)) byDay.set(dayKey, [])
        byDay.get(dayKey).push(i)
      })
      return byDay
    },
    orderedDayKeys(rows) {
      const keys = []
      const seen = new Set()
      rows.forEach((r) => {
        const dayKey = dayjs(r.timestamp).format('YYYY-MM-DD')
        if (!seen.has(dayKey)) {
          seen.add(dayKey)
          keys.push(dayKey)
        }
      })
      return keys
    },
    /** 按时间跨度与绘图区宽度决定横坐标日期间隔（天） */
    dayLabelStep(rows, plotWidth) {
      const dayKeys = this.orderedDayKeys(rows)
      if (dayKeys.length <= 1) return 1

      const spanDays = Math.max(
        1,
        (rows[rows.length - 1].timestamp - rows[0].timestamp) / 86400000
      )
      const minGapPx = 72
      const maxLabels = Math.max(2, Math.floor(plotWidth / minGapPx))
      let step = Math.max(1, Math.ceil(dayKeys.length / maxLabels))

      if (spanDays > 90) step = Math.max(step, 14)
      else if (spanDays > 60) step = Math.max(step, 7)
      else if (spanDays > 30) step = Math.max(step, 5)
      else if (spanDays > 14) step = Math.max(step, 3)
      else if (spanDays > 7) step = Math.max(step, 2)

      const intervalMinutes = Math.max(1, this.timeInterval)
      if (intervalMinutes >= 60 && spanDays > 3) {
        step = Math.max(step, 2)
      }

      return step
    },
    visibleDayKeys(rows, plotWidth) {
      const dayKeys = this.orderedDayKeys(rows)
      if (dayKeys.length <= 1) return dayKeys

      const step = this.dayLabelStep(rows, plotWidth)
      if (step <= 1) return dayKeys

      const visible = []
      dayKeys.forEach((dayKey, i) => {
        if (i === 0 || i === dayKeys.length - 1 || i % step === 0) {
          visible.push(dayKey)
        }
      })
      const last = dayKeys[dayKeys.length - 1]
      if (visible[visible.length - 1] !== last) visible.push(last)
      return visible
    },
    noonMs(dayKey) {
      return dayjs(dayKey, 'YYYY-MM-DD').hour(12).minute(0).second(0).millisecond(0).valueOf()
    },
    pixelAtIndex(index) {
      const pt = this.chart.convertToPixel({ seriesIndex: 0 }, [index, 0])
      if (pt && Number.isFinite(pt[0])) return pt[0]
      const x = this.chart.convertToPixel({ xAxisIndex: 0 }, index)
      return Number.isFinite(x) ? x : null
    },
    pixelAtNoon(rows, noon) {
      if (!rows.length) return null
      if (noon <= rows[0].timestamp) return this.pixelAtIndex(0)
      const last = rows.length - 1
      if (noon >= rows[last].timestamp) return this.pixelAtIndex(last)
      for (let i = 0; i < last; i++) {
        if (rows[i].timestamp <= noon && rows[i + 1].timestamp >= noon) {
          const span = rows[i + 1].timestamp - rows[i].timestamp
          const t = span > 0 ? (noon - rows[i].timestamp) / span : 0
          const x0 = this.pixelAtIndex(i)
          const x1 = this.pixelAtIndex(i + 1)
          if (x0 == null || x1 == null) return null
          return x0 + t * (x1 - x0)
        }
      }
      return null
    },
    xAxisFromRows(rows) {
      return {
        type: 'category',
        data: rows.map((_, i) => String(i)),
        axisTick: { show: false },
        axisLabel: { show: false }
      }
    },
    applyNoonDateLabels() {
      const rows = this.lastXRows
      if (!this.chart || !rows?.length || this.chartType === 'pv') {
        if (this.chart) {
          this.chart.setOption({ graphic: [] }, { replaceMerge: ['graphic'] })
        }
        return
      }
      const gridModel = this.chart.getModel().getComponent('grid', 0)
      const rect = gridModel?.coordinateSystem?.getRect()
      if (!rect) return

      const layout = this.bottomLayout()
      const labelY = rect.y + rect.height + layout.dateOffset
      const elements = []

      this.visibleDayKeys(rows, rect.width).forEach((dayKey) => {
        const x = this.pixelAtNoon(rows, this.noonMs(dayKey))
        if (x == null) return
        elements.push({
          type: 'text',
          left: x,
          top: labelY,
          style: {
            text: dayKey,
            fill: '#606266',
            fontSize: layout.dateFontSize,
            textAlign: 'center',
            textVerticalAlign: 'top'
          },
          silent: true,
          z: 100
        })
      })

      this.chart.setOption({ graphic: elements }, { replaceMerge: ['graphic'] })
    },
    scheduleNoonDateLabels() {
      if (this._labelRaf) cancelAnimationFrame(this._labelRaf)
      this._labelRaf = requestAnimationFrame(() => {
        requestAnimationFrame(() => this.applyNoonDateLabels())
      })
    },
    legendDescription(name) {
      return LEGEND_LABELS[name] || name
    },
    legendTooltip() {
      return {
        show: true,
        confine: true,
        formatter: (param) => {
          const name = typeof param === 'string' ? param : param?.name
          return this.legendDescription(name)
        }
      }
    },
    legendOption() {
      return {
        bottom: 4,
        left: 'center',
        tooltip: this.legendTooltip()
      }
    },
    /** charger 图例分两行，避免与日期重叠 */
    chargerLegend() {
      const tip = this.legendTooltip()
      const rowStyle = { itemGap: 12, textStyle: { fontSize: 11 } }
      return [
        {
          ...rowStyle,
          bottom: 34,
          left: 'center',
          data: ['充电桩用电量-kWh', '充电桩发电量-kWh'],
          tooltip: tip
        },
        {
          ...rowStyle,
          bottom: 8,
          left: 'center',
          data: [
            '电动汽车预计到达时荷电状态-%',
            '电动汽车离开时所需荷电状态-%',
            '电动汽车荷电状态-%'
          ],
          tooltip: tip
        }
      ]
    },
    chartGrid() {
      return { left: 12, right: 16, top: 36, bottom: 64, containLabel: true }
    },
    kwhYAxis() {
      return { type: 'value' }
    },
    percentYAxis(opts = {}) {
      return {
        type: 'value',
        position: 'right',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
        ...opts
      }
    },
    formatTooltipValue(value, asPercent) {
      if (value == null || value === '' || Number.isNaN(Number(value))) return '-'
      return asPercent ? `${Number(value).toFixed(1)}%` : Number(value).toFixed(3)
    },
    bottomLayout() {
      if (this.chartType === 'charger') {
        return { gridBottom: 108, dateOffset: 6, dateFontSize: 12 }
      }
      return { gridBottom: 64, dateOffset: 14, dateFontSize: 12 }
    },
    applyBottomLayout(option) {
      if (!option.series) return
      const layout = this.bottomLayout()
      option.grid = { ...this.chartGrid(), bottom: layout.gridBottom }
    },
    axisTooltip(rows, options = {}) {
      const percentYAxisIndex = options.percentYAxisIndex
      return {
        trigger: 'axis',
        formatter: (params) => {
          if (!params?.length) return ''
          const i = params[0].dataIndex
          const head =
            i != null && rows[i]
              ? dayjs(rows[i].timestamp).format('YYYY-MM-DD HH:mm')
              : params[0].axisValue
          let html = `${head}<br/>`
          params.forEach((p) => {
            const asPercent =
              percentYAxisIndex != null &&
              (p.yAxisIndex === percentYAxisIndex ||
                String(p.seriesName || '').includes('荷电状态'))
            const label = this.legendDescription(p.seriesName)
            html += `${p.marker}${label}: ${this.formatTooltipValue(p.value, asPercent)}<br/>`
          })
          return html
        }
      }
    },
    buildOption() {
      const data = this.filtered()
      let xRows = []

      const configs = {
        production: () => {
          const agg = this.aggregateBar(data, [
            'Energy Production from PV-kWh',
            'Energy Production from EV-kWh',
            'Energy Production From EV-kWh'
          ])
          const evKey = agg[0] && 'Energy Production from EV-kWh' in agg[0]
            ? 'Energy Production from EV-kWh'
            : 'Energy Production From EV-kWh'
          xRows = agg
          return {
            tooltip: this.axisTooltip(agg),
            legend: this.legendOption(),
            xAxis: this.xAxisFromRows(agg),
            yAxis: this.kwhYAxis(),
            series: [
              { name: '光伏发电量-kWh', type: 'bar', stack: 'a', data: agg.map((r) => r['Energy Production from PV-kWh']) },
              { name: '电动汽车发电量-kWh', type: 'bar', stack: 'a', data: agg.map((r) => r[evKey]) }
            ]
          }
        },
        consumption: () => {
          const agg = this.aggregateBar(data, ['Non-shiftable Load-kWh', 'Net Electricity Consumption-kWh'])
          xRows = agg
          return {
            tooltip: this.axisTooltip(agg),
            legend: this.legendOption(),
            xAxis: this.xAxisFromRows(agg),
            yAxis: this.kwhYAxis(),
            series: [
              { name: '不可调负荷-kWh', type: 'bar', stack: 'a', data: agg.map((r) => r['Non-shiftable Load-kWh']) },
              { name: '净用电量-kWh', type: 'bar', stack: 'a', data: agg.map((r) => r['Net Electricity Consumption-kWh']) }
            ]
          }
        },
        ev: () => {
          const norm = this.normalizeEvSocRows(data)
          const agg = this.aggregateLineAvg(norm, [
            'electric_vehicle_estimated_soc_arrival',
            'electric_vehicle_required_soc_departure',
            'electric_vehicle_soc'
          ])
          xRows = agg
          return {
            tooltip: this.axisTooltip(agg, { percentYAxisIndex: 0 }),
            legend: this.legendOption(),
            xAxis: this.xAxisFromRows(agg),
            yAxis: this.percentYAxis({ position: 'left' }),
            series: [
              { name: '电动汽车预计到达时荷电状态-%', type: 'line', data: agg.map((r) => r.electric_vehicle_estimated_soc_arrival) },
              { name: '电动汽车离开时所需荷电状态-%', type: 'line', data: agg.map((r) => r.electric_vehicle_required_soc_departure) },
              { name: '电动汽车荷电状态-%', type: 'line', data: agg.map((r) => r.electric_vehicle_soc) }
            ]
          }
        },
        charger: () => {
          const chargerData = this.normalizeChargerRows(data)
          const socData = this.normalizeChargerSocRows(data)
          const agg = this.aggregateBar(chargerData, ['Charger Consumption-kWh', 'Charger Production-kWh'])
          const soc = this.aggregateLineAvg(socData, [
            'EV Estimated SOC Arrival-%',
            'EV Required SOC Departure-%',
            'EV SOC-%'
          ])
          const axisRows = agg.length ? agg : soc
          xRows = axisRows
          return {
            tooltip: this.axisTooltip(axisRows, { percentYAxisIndex: 1 }),
            legend: this.chargerLegend(),
            xAxis: this.xAxisFromRows(axisRows),
            yAxis: [this.kwhYAxis(), this.percentYAxis()],
            series: [
              { name: '充电桩用电量-kWh', type: 'bar', stack: 'a', yAxisIndex: 0, data: agg.map((r) => r['Charger Consumption-kWh']) },
              { name: '充电桩发电量-kWh', type: 'bar', stack: 'a', yAxisIndex: 0, data: agg.map((r) => r['Charger Production-kWh']) },
              { name: '电动汽车预计到达时荷电状态-%', type: 'line', yAxisIndex: 1, data: soc.map((r) => r['EV Estimated SOC Arrival-%']) },
              { name: '电动汽车离开时所需荷电状态-%', type: 'line', yAxisIndex: 1, data: soc.map((r) => r['EV Required SOC Departure-%']) },
              { name: '电动汽车荷电状态-%', type: 'line', yAxisIndex: 1, data: soc.map((r) => r['EV SOC-%']) }
            ]
          }
        },
        battery: () => {
          const agg = this.aggregateBar(data, ['Battery (Dis)Charge-kWh'])
          const soc = this.aggregateLineAvg(this.normalizeBatterySocRows(data), ['Battery Soc-%'])
          xRows = agg
          return {
            tooltip: this.axisTooltip(agg, { percentYAxisIndex: 1 }),
            legend: this.legendOption(),
            xAxis: this.xAxisFromRows(agg),
            yAxis: [this.kwhYAxis(), this.percentYAxis()],
            series: [
              { name: '电池充放电量-kWh', type: 'bar', data: agg.map((r) => r['Battery (Dis)Charge-kWh']) },
              { name: '电池荷电状态-%', type: 'line', yAxisIndex: 1, data: soc.map((r) => r['Battery Soc-%']) }
            ]
          }
        },
        pricing: () => {
          const keys = [
            'electricity_pricing-$/kWh',
            'electricity_pricing_predicted_1-$/kWh',
            'electricity_pricing_predicted_2-$/kWh',
            'electricity_pricing_predicted_3-$/kWh'
          ].filter((k) => data[0] && k in data[0])

          const agg = this.aggregateLineAvg(data, keys)
          xRows = agg
          return {
            tooltip: this.axisTooltip(agg),
            legend: this.legendOption(),
            xAxis: this.xAxisFromRows(agg),
            yAxis: { type: 'value' },
            series: keys.map((k) => ({
              name: PRICING_SERIES[k] || k,
              type: 'line',
              data: agg.map((r) => r[k]),
              showSymbol: false
            }))
          }
        },
        pv: () => {
          const last = data[data.length - 1] || {}
          const keys = ['pv', 'uv', 'amt'].filter((k) => k in last)
          return {
            tooltip: {},
            xAxis: { type: 'category', data: keys },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: keys.map((k) => Number(last[k] || 0)) }]
          }
        }
      }

      const fn = configs[this.chartType]
      const option = fn ? fn() : { title: { text: '不支持的图表类型' } }
      this.lastXRows = xRows
      this.applyBottomLayout(option)
      return option
    },
    render() {
      if (!this.chart) return
      this.chart.setOption(this.buildOption(), true)
      if (this._onChartFinished) this.chart.off('finished', this._onChartFinished)
      this._onChartFinished = () => this.scheduleNoonDateLabels()
      this.chart.on('finished', this._onChartFinished)
      this.scheduleNoonDateLabels()
    }
  }
}
</script>

<style scoped>
.chart-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 480px;
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.title { font-weight: 600; }
.interval-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.chart {
  flex: 1;
  width: 100%;
  min-height: 480px;
  height: min(780px, calc(100vh - 220px));
}
</style>
