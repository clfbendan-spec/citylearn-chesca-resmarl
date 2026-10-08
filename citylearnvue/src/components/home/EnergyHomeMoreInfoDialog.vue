<template>
  <el-dialog
    :visible.sync="visibleProxy"
    custom-class="ha-more-info-dialog"
    width="560px"
    top="6vh"
    append-to-body
    :lock-scroll="false"
    :show-close="false"
    :close-on-click-modal="true"
    @opened="onOpened"
    @closed="onClosed"
  >
    <div class="mi-root" v-loading="loading">
      <header class="mi-header">
        <div class="mi-header-main">
          <div
            class="mi-header-icon"
            :style="{ color: focusMeta.color, background: focusMeta.bg }"
          >
            <HaMdiIcon :name="focusMeta.icon" :size="28" />
          </div>
          <div class="mi-header-text">
            <div class="mi-entity-name">{{ focusMeta.name }}</div>
            <div class="mi-entity-id">{{ entityIdDisplay }}</div>
          </div>
        </div>
        <button type="button" class="mi-close" aria-label="关闭" @click="visibleProxy = false">
          <HaMdiIcon name="close" :size="22" />
        </button>
      </header>

      <section class="mi-state">
        <div class="mi-state-value">
          {{ totalDisplay }}
          <span class="mi-state-unit">kWh</span>
        </div>
        <div class="mi-state-meta" v-if="secondaryMeta">
          <span>{{ secondaryMeta }}</span>
          <span class="sep">·</span>
          <span>{{ scopeLabel }}</span>
          <span class="sep">·</span>
          <span>{{ dayLabel }}</span>
        </div>
        <div class="mi-state-meta" v-else>
          <span>{{ scopeLabel }}</span>
          <span class="sep">·</span>
          <span>{{ dayLabel }}</span>
        </div>
      </section>

      <section class="mi-history">
        <div class="mi-history-head">
          <div class="mi-history-title">
            <HaMdiIcon name="chartLine" :size="18" />
            <span>{{ focusMeta.historyTitle }}</span>
          </div>
        </div>
        <div class="mi-history-hint-row">
          <p class="mi-history-hint">{{ historyHint }}</p>
          <p v-if="homeLoadSideMeta" class="mi-history-side">{{ homeLoadSideMeta }}</p>
        </div>
        <div ref="chart" class="mi-chart" />
      </section>

      <section v-if="showPricingChart" class="mi-history mi-pricing">
        <div class="mi-history-head">
          <div class="mi-history-title">
            <HaMdiIcon name="currencyUsd" :size="18" />
            <span>电价</span>
          </div>
        </div>
        <p class="mi-history-hint">{{ pricingHint }}</p>
        <div ref="pricingChart" class="mi-chart" />
      </section>
    </div>
  </el-dialog>
</template>

<script>
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import { fetchHomeEnergyHourly } from '@/utils/homeEnergyFlow'
import { PRICING_CHART_SERIES } from '@/utils/homePricing'

const FOCUS_META = {
  home: {
    name: '家庭用电',
    entity: 'home_energy',
    icon: 'homeOutline',
    color: '#44739E',
    bg: 'rgba(68,115,158,0.12)',
    historyTitle: '耗电曲线',
    hint: '逐小时家庭用电构成（kWh）',
    hintDay: '按日家庭用电构成（kWh）',
    totalKey: 'home'
  },
  solar: {
    name: '太阳能',
    entity: 'solar_energy',
    icon: 'solarPower',
    color: '#FDD835',
    bg: 'rgba(253,216,53,0.16)',
    historyTitle: '发电去向',
    hint: '逐小时光伏分配：家庭 / 电网 / 电池（kWh）',
    hintDay: '按日光伏分配：家庭 / 电网 / 电池（kWh）',
    totalKey: 'pv'
  },
  grid: {
    name: '电网',
    entity: 'grid_energy',
    icon: 'flash',
    color: '#44739E',
    bg: 'rgba(68,115,158,0.12)',
    historyTitle: '购售电',
    hint: '逐小时电网购入与外送（kWh）',
    hintDay: '按日电网购入与外送（kWh）',
    totalKey: 'gridIn'
  },
  battery: {
    name: '电池',
    entity: 'battery_energy',
    icon: 'battery',
    color: '#43A047',
    bg: 'rgba(67,160,71,0.12)',
    historyTitle: '充放电',
    hint: '逐小时电池充电与放电（kWh）',
    hintDay: '按日电池充电与放电（kWh）',
    totalKey: 'batOut'
  },
  load: {
    name: '不可调负荷',
    entity: 'non_shiftable_load',
    icon: 'flash',
    color: '#5C6BC0',
    bg: 'rgba(92,107,192,0.12)',
    historyTitle: '负荷与净用电',
    hint: '逐小时不可调负荷与净用电量（kWh）',
    hintDay: '按日不可调负荷与净用电量（kWh）',
    totalKey: 'nonShiftable'
  }
}

function sumKey(points, key) {
  return (points || []).reduce((s, p) => s + (Number(p[key]) || 0), 0)
}

function formatKwh(n) {
  if (n == null || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  if (v >= 100) return v.toFixed(1)
  if (v >= 1) return v.toFixed(2)
  return v.toFixed(3)
}

export default {
  name: 'EnergyHomeMoreInfoDialog',
  components: { HaMdiIcon },
  props: {
    visible: { type: Boolean, default: false },
    day: { type: String, default: '' },
    scope: { type: String, default: 'community' },
    untilTs: { type: String, default: '' },
    /** 本地曲线点（模型优选）；有值时不走首页 API */
    localPoints: { type: Array, default: null },
    /** hour | day */
    grain: { type: String, default: 'hour' },
    /** 周期展示文案（周/月/全部） */
    periodLabel: { type: String, default: '' },
    /** 电网详情下方电价曲线（模型优选） */
    pricingPoints: { type: Array, default: null },
    /** home | solar | grid | battery | load */
    focus: {
      type: String,
      default: 'home',
      validator: (v) => ['home', 'solar', 'grid', 'battery', 'load'].includes(v)
    }
  },
  data() {
    return {
      loading: false,
      points: [],
      chart: null,
      pricingChart: null
    }
  },
  computed: {
    visibleProxy: {
      get() {
        return this.visible
      },
      set(v) {
        this.$emit('update:visible', v)
      }
    },
    activeFocus() {
      return FOCUS_META[this.focus] ? this.focus : 'home'
    },
    focusMeta() {
      return FOCUS_META[this.activeFocus]
    },
    historyHint() {
      if (this.grain === 'day' && this.focusMeta.hintDay) return this.focusMeta.hintDay
      return this.focusMeta.hint
    },
    showPricingChart() {
      return (
        this.activeFocus === 'grid' &&
        Array.isArray(this.pricingPoints) &&
        this.pricingPoints.length > 0
      )
    },
    pricingHint() {
      return this.grain === 'day'
        ? '按日均电价及 6/12/24 小时预测（$/kWh）'
        : '逐小时电价及 6/12/24 小时预测（$/kWh）'
    },
    entityIdDisplay() {
      const base = `sensor.${this.focusMeta.entity}`
      const s = (this.scope || 'community').toLowerCase()
      if (s === 'community') return `${base}_community`
      const n = s.match(/\d+/)
      return n ? `${base}_b${n[0]}` : `${base}_${s}`
    },
    scopeLabel() {
      const s = (this.scope || 'community').toLowerCase()
      if (s === 'community') return '社区'
      const n = s.match(/\d+/)
      return n ? `建筑 ${n[0]}` : s
    },
    dayLabel() {
      return this.periodLabel || this.day || '—'
    },
    useLocalPoints() {
      return Array.isArray(this.localPoints)
    },
    totalValue() {
      if (this.activeFocus === 'grid') return sumKey(this.points, 'gridIn')
      if (this.activeFocus === 'battery') return sumKey(this.points, 'batOut')
      if (this.activeFocus === 'solar') return sumKey(this.points, 'pv')
      if (this.activeFocus === 'load') return sumKey(this.points, 'nonShiftable')
      return sumKey(this.points, 'home')
    },
    totalDisplay() {
      return formatKwh(this.totalValue)
    },
    secondaryMeta() {
      if (this.activeFocus === 'grid') {
        return `外送 ${formatKwh(sumKey(this.points, 'gridOut'))} kWh`
      }
      if (this.activeFocus === 'battery') {
        return `充电 ${formatKwh(sumKey(this.points, 'batIn'))} kWh`
      }
      if (this.activeFocus === 'load') {
        return `净用电 ${formatKwh(sumKey(this.points, 'net'))} kWh`
      }
      return ''
    },
    /** 家庭详情：提示右侧显示不可调负荷 / 其他用电合计 */
    homeLoadSideMeta() {
      if (this.activeFocus !== 'home' || !(this.points || []).length) return ''
      const home = sumKey(this.points, 'home')
      let nonShiftable = sumKey(this.points, 'nonShiftable')
      let otherLoad = this.points.some((p) => p.otherLoad != null)
        ? sumKey(this.points, 'otherLoad')
        : home - nonShiftable
      if (otherLoad < 0.05) otherLoad = 0
      const loadShown = Math.min(nonShiftable, home || nonShiftable)
      if (loadShown + otherLoad > home && home > 0) {
        otherLoad = Math.max(home - loadShown, 0)
      }
      nonShiftable = home > 0 ? loadShown : nonShiftable
      return `不可调负荷 ${formatKwh(nonShiftable)} kWh · 其他用电 ${formatKwh(otherLoad)} kWh`
    }
  },
  watch: {
    visible(v) {
      if (v) this.loadAndRender()
    },
    day() {
      if (this.visible) this.loadAndRender()
    },
    scope() {
      if (this.visible) this.loadAndRender()
    },
    untilTs() {
      if (this.visible) this.loadAndRender()
    },
    localPoints: {
      deep: true,
      handler() {
        if (this.visible) this.loadAndRender()
      }
    },
    grain() {
      if (this.visible) this.renderChart()
    },
    focus() {
      if (this.visible) this.renderChart()
    },
    pricingPoints: {
      deep: true,
      handler() {
        if (this.visible) this.$nextTick(() => this.renderPricingChart())
      }
    }
  },
  beforeDestroy() {
    this.disposeChart()
    this.disposePricingChart()
    window.removeEventListener('resize', this.onResize)
  },
  methods: {
    async onOpened() {
      window.addEventListener('resize', this.onResize)
      await this.$nextTick()
      // 弹窗每次打开都重建图表，避免第二次挂到已销毁/隐藏的 DOM
      this.disposeChart()
      this.disposePricingChart()
      this.ensureChart()
      await this.loadAndRender()
    },
    onClosed() {
      window.removeEventListener('resize', this.onResize)
      this.disposeChart()
      this.disposePricingChart()
    },
    onResize() {
      if (this.chart && !(this.chart.isDisposed && this.chart.isDisposed())) {
        this.chart.resize()
      }
      if (this.pricingChart && !(this.pricingChart.isDisposed && this.pricingChart.isDisposed())) {
        this.pricingChart.resize()
      }
    },
    ensureChart() {
      const el = this.$refs.chart
      if (!el) return
      if (this.chart) {
        const dead =
          (this.chart.isDisposed && this.chart.isDisposed()) ||
          this.chart.getDom() !== el
        if (dead) {
          try {
            if (!(this.chart.isDisposed && this.chart.isDisposed())) this.chart.dispose()
          } catch (e) { /* ignore */ }
          this.chart = null
        }
      }
      if (!this.chart) this.chart = echarts.init(el)
    },
    ensurePricingChart() {
      const el = this.$refs.pricingChart
      if (!el) return
      if (this.pricingChart) {
        const dead =
          (this.pricingChart.isDisposed && this.pricingChart.isDisposed()) ||
          this.pricingChart.getDom() !== el
        if (dead) {
          try {
            if (!(this.pricingChart.isDisposed && this.pricingChart.isDisposed())) {
              this.pricingChart.dispose()
            }
          } catch (e) { /* ignore */ }
          this.pricingChart = null
        }
      }
      if (!this.pricingChart) this.pricingChart = echarts.init(el)
    },
    disposeChart() {
      if (this.chart) {
        try {
          if (!(this.chart.isDisposed && this.chart.isDisposed())) this.chart.dispose()
        } catch (e) { /* ignore */ }
        this.chart = null
      }
    },
    disposePricingChart() {
      if (this.pricingChart) {
        try {
          if (!(this.pricingChart.isDisposed && this.pricingChart.isDisposed())) {
            this.pricingChart.dispose()
          }
        } catch (e) { /* ignore */ }
        this.pricingChart = null
      }
    },
    async loadAndRender() {
      this.loading = true
      try {
        if (this.useLocalPoints) {
          this.points = this.localPoints || []
        } else {
          if (!this.day) return
          const data = await fetchHomeEnergyHourly({
            day: this.day,
            scope: this.scope,
            untilTs: this.untilTs || undefined
          })
          this.points = data.points || []
        }
        await this.$nextTick()
        this.renderChart()
        // 电价区是 v-if，需等 DOM 挂载后再初始化
        await this.$nextTick()
        await this.$nextTick()
        this.renderPricingChart()
      } catch (e) {
        this.points = []
        this.$message.error(e.message || '加载能源曲线失败')
      } finally {
        this.loading = false
      }
    },
    seriesConfig() {
      const n = (key) => this.points.map((p) => Number(p[key]) || 0)
      if (this.activeFocus === 'solar') {
        return {
          legend: ['→ 家庭', '→ 电网', '→ 电池'],
          colors: ['#FDD835', '#A0CADB', '#43A047'],
          series: [
            { name: '→ 家庭', stack: 'solar', data: n('solarToHome'), color: '#FDD835' },
            { name: '→ 电网', stack: 'solar', data: n('solarToGrid'), color: '#A0CADB' },
            { name: '→ 电池', stack: 'solar', data: n('solarToBattery'), color: '#43A047' }
          ]
        }
      }
      if (this.activeFocus === 'grid') {
        return {
          legend: ['购入', '外送'],
          colors: ['#44739E', '#A0CADB'],
          series: [
            { name: '购入', data: n('gridIn'), color: '#44739E' },
            { name: '外送', data: n('gridOut'), color: '#A0CADB' }
          ]
        }
      }
      if (this.activeFocus === 'battery') {
        return {
          legend: ['放电', '充电'],
          colors: ['#43A047', '#81C784'],
          series: [
            { name: '放电', data: n('batOut'), color: '#43A047' },
            { name: '充电', data: n('batIn'), color: '#81C784' }
          ]
        }
      }
      if (this.activeFocus === 'load') {
        return {
          legend: ['不可调负荷', '净用电量'],
          colors: ['#5C6BC0', '#44739E'],
          series: [
            {
              name: '不可调负荷',
              data: n('nonShiftable'),
              color: '#5C6BC0'
            },
            {
              name: '净用电量',
              data: n('net'),
              color: '#44739E'
            }
          ]
        }
      }
      return {
        legend: ['光伏', '电网', '电池'],
        colors: ['#FDD835', '#44739E', '#43A047'],
        series: [
          { name: '光伏', stack: 'home', data: n('solarToHome'), color: '#FDD835' },
          { name: '电网', stack: 'home', data: n('gridToHome'), color: '#44739E' },
          { name: '电池', stack: 'home', data: n('batteryToHome'), color: '#43A047' }
        ]
      }
    },
    /**
     * 避免接近 0 的数值把 Y 轴压到极小，导致条形视觉上“铺满”图表。
     * @returns {{ min: number, max: number }}
     */
    resolveYAxisExtent(seriesList) {
      const list = seriesList || []
      if (!list.length) return { min: 0, max: 1 }
      const len = Math.max(0, ...list.map((s) => (s.data || []).length))
      let peak = 0
      let trough = 0
      const stackKeys = [...new Set(list.map((s) => s.stack).filter(Boolean))]
      if (stackKeys.length) {
        for (let i = 0; i < len; i += 1) {
          stackKeys.forEach((sk) => {
            let sum = 0
            list
              .filter((s) => s.stack === sk)
              .forEach((s) => {
                sum += Number((s.data || [])[i]) || 0
              })
            if (sum > peak) peak = sum
            if (sum < trough) trough = sum
          })
        }
      } else {
        list.forEach((s) => {
          const data = s.data || []
          data.forEach((v) => {
            const n = Number(v) || 0
            if (n > peak) peak = n
            if (n < trough) trough = n
          })
        })
      }
      const padMax = !(peak > 0) ? 1 : (() => {
        const padded = peak * 1.15
        if (peak < 0.05) return Math.max(padded, 0.2)
        if (peak < 0.5) return Math.max(padded, 0.5)
        if (peak < 2) return Math.max(padded, 2)
        return Number(padded.toFixed(3))
      })()
      const padMin = trough >= 0 ? 0 : Number((trough * 1.15).toFixed(3))
      return { min: padMin, max: padMax }
    },
    resolveYAxisMax(seriesList) {
      return this.resolveYAxisExtent(seriesList).max
    },
    renderChart() {
      this.ensureChart()
      if (!this.chart) return

      const times = this.points.map((p) =>
        this.grain === 'day'
          ? dayjs(p.ts).format('MM-DD')
          : dayjs(p.ts).format('HH:mm')
      )
      const cfg = this.seriesConfig()
      const isGrouped =
        this.activeFocus === 'grid' ||
        this.activeFocus === 'battery' ||
        this.activeFocus === 'load'
      const yExtent = this.resolveYAxisExtent(cfg.series)

      this.chart.setOption(
        {
          color: cfg.colors,
          tooltip: {
            trigger: 'axis',
            backgroundColor: '#fff',
            borderColor: 'rgba(0,0,0,0.12)',
            borderWidth: 1,
            textStyle: { color: '#212121', fontSize: 12 },
            formatter: (params) => {
              if (!params || !params.length) return ''
              const head = params[0].axisValue
              const lines = params.map((p) => {
                const v = p.data == null ? '—' : Number(p.data).toFixed(3)
                return `${p.marker}${p.seriesName} <b>${v} kWh</b>`
              })
              return `${head}<br/>${lines.join('<br/>')}`
            }
          },
          legend: {
            data: cfg.legend,
            bottom: 0,
            textStyle: { color: '#727272', fontSize: 11 }
          },
          grid: { left: 52, right: 16, top: 24, bottom: 48 },
          xAxis: {
            type: 'category',
            data: times,
            axisLine: { lineStyle: { color: 'rgba(0,0,0,0.12)' } },
            axisLabel: { color: '#727272', fontSize: 11, hideOverlap: true },
            axisTick: { show: false }
          },
          yAxis: {
            type: 'value',
            name: 'kWh',
            nameTextStyle: { color: '#727272', fontSize: 11 },
            min: yExtent.min,
            max: yExtent.max,
            scale: false,
            axisLabel: { color: '#727272', fontSize: 11 },
            splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
            axisLine: { show: false }
          },
          series: cfg.series.map((s) => ({
            name: s.name,
            type: 'bar',
            stack: s.stack,
            data: s.data,
            barMaxWidth: isGrouped ? 12 : 18,
            itemStyle: { color: s.color },
            emphasis: { focus: 'series' }
          }))
        },
        true
      )
      this.chart.resize()
    },
    renderPricingChart() {
      if (!this.showPricingChart) {
        this.disposePricingChart()
        return
      }
      this.ensurePricingChart()
      if (!this.pricingChart) return

      const rows = this.pricingPoints || []
      const times = rows.map((p) =>
        this.grain === 'day'
          ? dayjs(p.ts).format('MM-DD')
          : dayjs(p.ts).format('HH:mm')
      )
      const series = PRICING_CHART_SERIES.map((s) => ({
        name: s.name,
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map((r) => (r[s.field] == null ? null : Number(r[s.field]))),
        lineStyle: { width: s.field === 'electricity_pricing' ? 2.5 : 2 },
        itemStyle: { color: s.color }
      }))

      this.pricingChart.setOption(
        {
          color: PRICING_CHART_SERIES.map((s) => s.color),
          tooltip: {
            trigger: 'axis',
            backgroundColor: '#fff',
            borderColor: 'rgba(0,0,0,0.12)',
            borderWidth: 1,
            textStyle: { color: '#212121', fontSize: 12 },
            formatter: (params) => {
              if (!params || !params.length) return ''
              const head = params[0].axisValue
              const lines = params.map((p) => {
                const v = p.data == null ? '—' : Number(p.data).toFixed(3)
                return `${p.marker}${p.seriesName} <b>${v} $/kWh</b>`
              })
              return `${head}<br/>${lines.join('<br/>')}`
            }
          },
          legend: {
            data: PRICING_CHART_SERIES.map((s) => s.name),
            bottom: 0,
            textStyle: { color: '#727272', fontSize: 11 }
          },
          grid: { left: 52, right: 16, top: 24, bottom: 48 },
          xAxis: {
            type: 'category',
            data: times,
            boundaryGap: false,
            axisLine: { lineStyle: { color: 'rgba(0,0,0,0.12)' } },
            axisLabel: { color: '#727272', fontSize: 11, hideOverlap: true },
            axisTick: { show: false }
          },
          yAxis: {
            type: 'value',
            name: '$/kWh',
            nameTextStyle: { color: '#727272', fontSize: 11 },
            scale: true,
            axisLabel: { color: '#727272', fontSize: 11 },
            splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
            axisLine: { show: false }
          },
          series
        },
        true
      )
      this.pricingChart.resize()
    }
  }
}
</script>

<style scoped>
.mi-root {
  min-height: 200px;
}

.mi-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.mi-header-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.mi-header-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mi-header-text {
  min-width: 0;
}

.mi-entity-name {
  font-size: 18px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.mi-entity-id {
  margin-top: 2px;
  font-size: 12px;
  color: var(--secondary-text-color);
  word-break: break-all;
}

.mi-close {
  margin: 0;
  padding: 6px;
  border: none;
  background: transparent;
  color: var(--secondary-text-color);
  cursor: pointer;
  border-radius: 50%;
  line-height: 0;
}

.mi-close:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--primary-text-color);
}

.mi-state {
  margin-bottom: 16px;
}

.mi-state-value {
  font-size: 36px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--primary-text-color);
  font-variant-numeric: tabular-nums;
}

.mi-state-unit {
  font-size: 16px;
  color: var(--secondary-text-color);
  margin-left: 4px;
}

.mi-state-meta {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--secondary-text-color);
  flex-wrap: wrap;
}

.mi-state-meta .sep {
  opacity: 0.5;
}

.mi-history {
  padding-top: 8px;
  border-top: 1px solid var(--divider-color);
}

.mi-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mi-history-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.mi-history-hint-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 6px 0 4px;
}

.mi-history-hint {
  margin: 0;
  font-size: 12px;
  color: var(--secondary-text-color);
}

.mi-history-side {
  margin: 0;
  font-size: 12px;
  color: var(--secondary-text-color);
  text-align: right;
  white-space: nowrap;
}

.mi-chart {
  width: 100%;
  height: 280px;
}

.mi-pricing {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--divider-color);
}
</style>
