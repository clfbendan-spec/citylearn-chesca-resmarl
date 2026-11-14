<template>
  <el-dialog :visible="visible" :title="sensor.name || '实时测量'" width="min(720px, 94vw)" append-to-body @update:visible="$emit('update:visible', $event)" @opened="draw">
    <p class="source-caption">{{ communityName }} · {{ timezone }} · {{ day || '最新日期' }}</p>
    <div v-if="points.length" ref="chart" class="measured-chart" />
    <el-empty v-else :description="dataMode === 'simulation' ? '该评估未保存此字段' : dataMode === 'history' ? '此日期没有该字段的历史测量' : '此日期未接入该字段的实时测量'" :image-size="72" />
    <el-table v-if="points.length" :data="points" size="mini" max-height="240">
      <el-table-column prop="localTime" :label="dataMode === 'simulation' ? '仿真时间' : '社区当地测量时间'" min-width="170" />
      <el-table-column prop="value" :label="sensor.unit ? `${sensor.name} (${sensor.unit})` : sensor.name" min-width="140" />
    </el-table>
  </el-dialog>
</template>

<script>
import { themeColor } from '@/utils/theme'

import * as echarts from 'echarts'
export default {
  name: 'HomeRealtimeMoreInfo',
  props: {
    visible: Boolean, sensor: { type: Object, default: () => ({}) },
    samples: { type: Array, default: () => [] }, day: String, communityName: String, timezone: String, dataMode: String
  },
  computed: {
    points() {
      return this.samples.filter(row => (!this.day || String(row.localTime).slice(0, 10) === this.day) && row[this.sensor.field] != null)
        .map(row => ({ localTime: String(row.localTime).replace('T', ' '), value: row[this.sensor.field] }))
    }
  },
  watch: { points() { this.$nextTick(this.draw) }, visible(value) { if (!value && this.chart) this.chart.clear() } },
  beforeDestroy() { if (this.chart) this.chart.dispose() },
  methods: {
    draw() {
      if (!this.visible || !this.$refs.chart || !this.points.length) return
      if (!this.chart) this.chart = echarts.init(this.$refs.chart)
      this.chart.setOption({
        animation: false, grid: { left: 52, right: 20, top: 20, bottom: 50 },
        tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: this.points.map(point => point.localTime.slice(11, 16)) },
        yAxis: { type: 'value', name: this.sensor.unit || '', scale: true },
        series: [{ type: 'line', data: this.points.map(point => point.value), connectNulls: false, symbolSize: 5, lineStyle: { color: this.sensor.chartColor || themeColor('primary-color') } }]
      }, true)
      this.chart.resize()
    }
  }
}
</script>

<style scoped>
.source-caption { color: var(--secondary-text-color); margin-top: 0; }
.measured-chart { height: 230px; width: 100%; }
</style>
