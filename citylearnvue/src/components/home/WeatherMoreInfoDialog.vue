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
            :style="{ color: sensor.color, background: sensor.bg }"
          >
            <HaMdiIcon :name="sensor.icon" :size="28" />
          </div>
          <div class="mi-header-text">
            <div class="mi-entity-name">{{ sensor.name }}</div>
            <div class="mi-entity-id">{{ entityIdDisplay }}</div>
          </div>
        </div>
        <button type="button" class="mi-close" aria-label="关闭" @click="visibleProxy = false">
          <HaMdiIcon name="close" :size="22" />
        </button>
      </header>

      <section class="mi-state" v-if="current">
        <div class="mi-state-value">
          {{ stateDisplay }}
          <span class="mi-state-unit">{{ sensor.unit }}</span>
        </div>
        <div class="mi-state-meta" v-if="sensor.group === 'action' || sensor.group === 'pricing'">
          <span>{{ currentTimeLabel }}</span>
        </div>
        <div class="mi-state-meta" v-else>
          <HaMdiIcon
            :name="condition.icon"
            :size="20"
            :style="{ color: condition.color }"
          />
          <span>{{ condition.label }}</span>
          <span class="sep">·</span>
          <span>{{ currentTimeLabel }}</span>
        </div>
      </section>

      <section class="mi-history">
        <div class="mi-history-head">
          <div class="mi-history-title">
            <HaMdiIcon name="chartLine" :size="18" />
            <span>历史</span>
          </div>
          <el-radio-group v-model="range" size="mini" @change="renderChart">
            <el-radio-button label="day">今日</el-radio-button>
            <el-radio-button label="24h">24 小时</el-radio-button>
          </el-radio-group>
        </div>
        <p class="mi-history-hint"></p>
        <div ref="chart" class="mi-chart" />
      </section>
    </div>
  </el-dialog>
</template>

<script>
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import { getWeatherSnapshot } from '@/utils/weather2026'
import { getActionSnapshot } from '@/utils/homeActions'
import { formatHourLabel, metricsViewNow } from '@/utils/dataset2026Clock'
import { resolveWeatherCondition } from '@/utils/haIcons'
import {
  HOME_SENSORS,
  HOME_SENSOR_KEYS,
  formatSensorValue
} from '@/utils/homeSensors'

export default {
  name: 'WeatherMoreInfoDialog',
  components: { HaMdiIcon },
  props: {
    visible: { type: Boolean, default: false },
    focus: {
      type: String,
      default: 'temperature',
      validator: (v) => HOME_SENSOR_KEYS.includes(v)
    },
    buildingIndex: { type: Number, default: 0 },
    /** 首页选中日；早于今天时弹窗取该日 23:00 */
    selectedDay: { type: String, default: '' }
  },
  data() {
    return {
      range: 'day',
      current: null,
      history: [],
      currentIndex: 0,
      condition: resolveWeatherCondition(null),
      chart: null,
      loading: false,
      localFocus: this.focus
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
      return HOME_SENSOR_KEYS.includes(this.localFocus)
        ? this.localFocus
        : 'temperature'
    },
    sensor() {
      return HOME_SENSORS[this.activeFocus]
    },
    entityIdDisplay() {
      const base = this.sensor.entityId
      if (this.sensor.group === 'building' || this.sensor.group === 'action') {
        return `${base}_b${this.buildingIndex + 1}`
      }
      return base
    },
    stateDisplay() {
      if (!this.current) return '—'
      return formatSensorValue(this.sensor, this.current[this.sensor.field])
    },
    currentTimeLabel() {
      if (this.current == null) return '—'
      const idx = this.currentIndex != null ? this.currentIndex : this.current.index
      if (idx == null) return '—'
      return formatHourLabel(idx, 'YYYY-MM-DD HH:mm')
    }
  },
  watch: {
    visible(v) {
      if (v) {
        this.localFocus = this.focus
        this.loadAndRender()
      }
    },
    focus(v) {
      this.localFocus = v
      if (this.visible) this.renderChart()
    },
    buildingIndex() {
      if (this.visible) this.loadAndRender()
    },
    selectedDay() {
      if (this.visible) this.loadAndRender()
    }
  },
  beforeDestroy() {
    this.disposeChart()
    window.removeEventListener('resize', this.onResize)
  },
  methods: {
    async onOpened() {
      window.addEventListener('resize', this.onResize)
      this.localFocus = this.focus
      await this.$nextTick()
      this.ensureChart()
      await this.loadAndRender()
    },
    onClosed() {
      window.removeEventListener('resize', this.onResize)
    },
    onResize() {
      if (this.chart) this.chart.resize()
    },
    ensureChart() {
      if (!this.$refs.chart) return
      if (!this.chart) this.chart = echarts.init(this.$refs.chart)
    },
    disposeChart() {
      if (this.chart) {
        this.chart.dispose()
        this.chart = null
      }
    },
    async fetchSnapshot() {
      const now = metricsViewNow(this.selectedDay, new Date())
      if (this.sensor.group === 'action') {
        const snap = await getActionSnapshot(
          now,
          this.range,
          this.buildingIndex
        )
        this.current = snap.current
        this.history = snap.history
        this.currentIndex = snap.currentStep
        this.condition = resolveWeatherCondition(null)
        return snap
      }
      const snap = await getWeatherSnapshot(
        now,
        this.range,
        this.buildingIndex
      )
      this.current = snap.current
      this.history = snap.history
      this.currentIndex = snap.currentIndex
      this.condition = snap.condition
      return snap
    },
    async loadAndRender() {
      this.loading = true
      try {
        await this.fetchSnapshot()
        await this.$nextTick()
        this.renderChart()
      } catch (e) {
        this.$message.error(e.message || '加载历史失败')
      } finally {
        this.loading = false
      }
    },
    async renderChart() {
      try {
        await this.fetchSnapshot()
      } catch (e) {
        return
      }

      this.ensureChart()
      if (!this.chart) return

      const sensor = this.sensor
      const times = this.history.map((r) => dayjs(r.time).format('HH:mm'))
      const extras = Array.isArray(sensor.extraSeries) ? sensor.extraSeries : []
      const seriesDefs = [
        {
          name: sensor.name,
          field: sensor.field,
          color: sensor.chartColor,
          area: extras.length === 0
        },
        ...extras.map((s) => ({
          name: s.name,
          field: s.field,
          color: s.color,
          area: false
        }))
      ]
      const yName = sensor.unit || ''
      const colors = seriesDefs.map((s) => s.color)

      this.chart.setOption(
        {
          color: colors,
          tooltip: {
            trigger: 'axis',
            backgroundColor: '#fff',
            borderColor: 'rgba(0,0,0,0.12)',
            borderWidth: 1,
            textStyle: { color: '#212121', fontSize: 12 },
            formatter: (params) => {
              if (!params || !params.length) return ''
              const head = params[0].axisValue
              const unit = sensor.unit ? ` ${sensor.unit}` : ''
              const lines = params.map((p) => {
                const val =
                  p.data == null
                    ? '—'
                    : formatSensorValue(sensor, p.data)
                return `${p.marker}${p.seriesName} <b>${val}${unit}</b>`
              })
              return `${head}<br/>${lines.join('<br/>')}`
            }
          },
          legend: extras.length
            ? {
                data: seriesDefs.map((s) => s.name),
                bottom: 0,
                textStyle: { color: '#727272', fontSize: 11 }
              }
            : undefined,
          grid: {
            left: 52,
            right: 16,
            top: 24,
            bottom: extras.length ? 48 : 36
          },
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
            name: yName,
            nameTextStyle: { color: '#727272', fontSize: 11 },
            scale: true,
            min: sensor.key === 'humidity' ? 0 : null,
            max: sensor.key === 'humidity' ? 100 : null,
            axisLabel: { color: '#727272', fontSize: 11 },
            splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
            axisLine: { show: false }
          },
          series: seriesDefs.map((s) => {
            const series = {
              name: s.name,
              type: 'line',
              smooth: true,
              showSymbol: false,
              data: this.history.map((r) => r[s.field]),
              lineStyle: { width: s.area ? 2.5 : 2 }
            }
            if (s.area) {
              series.areaStyle = {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: this.hexToRgba(s.color, 0.22) },
                  { offset: 1, color: this.hexToRgba(s.color, 0.02) }
                ])
              }
            }
            return series
          })
        },
        true
      )
      this.chart.resize()
    },
    hexToRgba(hex, a) {
      const h = hex.replace('#', '')
      const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
      const n = parseInt(full, 16)
      const r = (n >> 16) & 255
      const g = (n >> 8) & 255
      const b = n & 255
      return `rgba(${r},${g},${b},${a})`
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
  padding: 4px 0 12px;
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

.mi-entity-name {
  font-size: 18px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.mi-entity-id {
  margin-top: 2px;
  font-size: 12px;
  color: var(--secondary-text-color);
  font-family: var(--ha-font-family-mono);
  word-break: break-all;
}

.mi-close {
  border: 0;
  background: transparent;
  color: var(--secondary-text-color);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.mi-close:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--primary-text-color);
}

.mi-state {
  text-align: center;
  padding: 8px 0 20px;
}

.mi-state-value {
  font-size: 40px;
  font-weight: 400;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  color: var(--primary-text-color);
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

.mi-history-hint {
  margin: 6px 0 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
}

.mi-chart {
  width: 100%;
  height: 260px;
}
</style>

<style>
.ha-more-info-dialog {
  border-radius: 12px;
  overflow: hidden;
}

.ha-more-info-dialog .el-dialog__header {
  display: none;
}

.ha-more-info-dialog .el-dialog__body {
  padding: 16px 20px 20px;
}
</style>
