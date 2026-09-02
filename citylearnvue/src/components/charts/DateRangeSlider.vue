<template>
  <div>
    <div class="date-range-labels">
      <span>开始: {{ formatDate(sliderValues[0]) }}</span>
      <span>结束: {{ formatDate(sliderValues[1]) }}</span>
    </div>
    <el-slider
      v-model="inner"
      range
      :min="minTimestamp"
      :max="maxTimestamp"
      :step="dayStep"
      :format-tooltip="formatDate"
      @change="onChange"
    />
  </div>
</template>

<script>
import dayjs from 'dayjs'

export default {
  name: 'DateRangeSlider',
  props: {
    minTimestamp: { type: Number, required: true },
    maxTimestamp: { type: Number, required: true },
    sliderValues: { type: Array, required: true }
  },
  data() {
    return {
      dayStep: 24 * 60 * 60 * 1000,
      inner: [...this.sliderValues]
    }
  },
  watch: {
    sliderValues(v) {
      this.inner = [...v]
    }
  },
  methods: {
    formatDate(ts) {
      return dayjs(ts).format('YYYY-MM-DD')
    },
    onChange(v) {
      this.$emit('change', v)
    }
  }
}
</script>

<style scoped>
.date-range-labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
}
</style>
