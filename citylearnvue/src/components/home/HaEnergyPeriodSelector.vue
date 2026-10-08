<template>
  <div
    class="ha-energy-period"
    :class="{ 'datepicker-open': pickerOpen }"
    :style="{ left: barLeft }"
  >
    <div v-if="pickerOpen" class="ha-energy-period-backdrop" @click="closePicker" />

    <div class="ha-energy-period-bar">
      <div class="period-start">
        <el-select
          v-if="showAggregateMode"
          class="period-agg-select"
          size="mini"
          :value="aggregateMode"
          placeholder="聚合"
          @change="onAggregateChange"
        >
          <el-option label="按天" value="day" />
          <el-option label="按星期" value="week" />
          <el-option label="按月" value="month" />
          <el-option label="全部" value="all" />
        </el-select>

        <template v-if="isDayMode">
          <button
            type="button"
            class="period-date-btn"
            :disabled="!value"
            @click="togglePicker"
          >
            <HaMdiIcon name="calendar" :size="20" class="period-cal-icon" />
            <span class="period-date-label">{{ dateLabel }}</span>
          </button>

          <el-date-picker
            ref="picker"
            class="period-picker-hidden"
            popper-class="ha-energy-period-popper"
            type="date"
            size="mini"
            :value="pickerValue"
            :picker-options="pickerOptions"
            :clearable="false"
            :editable="false"
            format="yyyy-MM-dd"
            value-format="yyyy-MM-dd"
            placement="top-start"
            @input="onPick"
            @blur="onPickerBlur"
          />
        </template>

        <template v-else-if="aggregateMode === 'all'">
          <span class="period-date-btn period-date-static">
            <HaMdiIcon name="calendar" :size="20" class="period-cal-icon" />
            <span class="period-date-label">{{ periodLabel }}</span>
          </span>
        </template>

        <el-select
          v-else
          class="period-range-select"
          size="mini"
          :value="periodKey"
          filterable
          placeholder="选择周期"
          @change="onPeriodKeyChange"
        >
          <el-option
            v-for="p in periods"
            :key="p.key"
            :label="p.label"
            :value="p.key"
          />
        </el-select>
      </div>

      <div
        class="period-center"
        role="tablist"
        :aria-label="useScopeMode ? '选择范围' : '选择建筑'"
      >
        <template v-if="useScopeMode">
          <button
            v-for="opt in scopeOptions"
            :key="opt.value"
            type="button"
            role="tab"
            class="period-building-btn"
            :class="{ active: scope === opt.value }"
            :aria-selected="scope === opt.value"
            @click="selectScope(opt.value)"
          >
            {{ opt.label }}
          </button>
        </template>
        <template v-else>
          <button
            v-for="opt in buildingOptions"
            :key="opt.id"
            type="button"
            role="tab"
            class="period-building-btn"
            :class="{ active: buildingIndex === opt.id }"
            :aria-selected="buildingIndex === opt.id"
            @click="selectBuilding(opt.id)"
          >
            建筑{{ opt.id + 1 }}
          </button>
        </template>
      </div>

      <div class="period-end">
        <button
          type="button"
          class="period-icon-btn"
          :disabled="!canPrev"
          :aria-label="isDayMode ? '前一天' : '上一周期'"
          @click="shift(-1)"
        >
          <HaMdiIcon name="chevronLeft" :size="22" />
        </button>
        <button
          type="button"
          class="period-icon-btn"
          :disabled="!canNext"
          :aria-label="isDayMode ? '后一天' : '下一周期'"
          @click="shift(1)"
        >
          <HaMdiIcon name="chevronRight" :size="22" />
        </button>
        <button
          v-if="isDayMode"
          type="button"
          class="period-now-btn"
          :disabled="!canGoToday || isToday"
          @click="goToday"
        >
          今天
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import dayjs from 'dayjs'
import HaMdiIcon from '@/components/home/HaMdiIcon.vue'
import { todayKeyIn2026 } from '@/utils/dataset2026Clock'

export default {
  name: 'HaEnergyPeriodSelector',
  components: { HaMdiIcon },
  props: {
    /** YYYY-MM-DD（按天） */
    value: { type: String, default: '' },
    /** 可选日期列表 YYYY-MM-DD */
    days: { type: Array, default: () => [] },
    /** 当前建筑索引 0–2（首页） */
    buildingIndex: { type: Number, default: 0 },
    /** [{ id: 0 }, ...] 首页建筑切换 */
    buildingOptions: {
      type: Array,
      default: () => [{ id: 0 }, { id: 1 }, { id: 2 }]
    },
    /** 模型优选：[{ value, label }]，含社区合计 */
    scopeOptions: { type: Array, default: null },
    /** 当前 scope，如 community / building_1 */
    scope: { type: String, default: 'community' },
    /** 显示聚合方式 */
    showAggregateMode: { type: Boolean, default: false },
    /** day | week | month | all */
    aggregateMode: { type: String, default: 'day' },
    /** 非按天时的周期列表 */
    periods: { type: Array, default: () => [] },
    /** 当前周期 key */
    periodKey: { type: String, default: '' }
  },
  data() {
    return {
      pickerOpen: false,
      barLeft: '0px'
    }
  },
  computed: {
    useScopeMode() {
      return Array.isArray(this.scopeOptions) && this.scopeOptions.length > 0
    },
    isDayMode() {
      return !this.showAggregateMode || this.aggregateMode === 'day'
    },
    dayIndex() {
      return this.days.indexOf(this.value)
    },
    periodIndex() {
      return (this.periods || []).findIndex((p) => p.key === this.periodKey)
    },
    canPrev() {
      if (this.aggregateMode === 'all') return false
      if (this.isDayMode) return this.dayIndex > 0
      return this.periodIndex > 0
    },
    canNext() {
      if (this.aggregateMode === 'all') return false
      if (this.isDayMode) {
        return this.dayIndex >= 0 && this.dayIndex < this.days.length - 1
      }
      return this.periodIndex >= 0 && this.periodIndex < this.periods.length - 1
    },
    todayKey() {
      return todayKeyIn2026(new Date())
    },
    isToday() {
      return this.value === this.todayKey
    },
    canGoToday() {
      return this.days.includes(this.todayKey)
    },
    pickerValue() {
      return this.value || null
    },
    periodLabel() {
      const hit = (this.periods || []).find((p) => p.key === this.periodKey)
      return (hit && hit.label) || '全部'
    },
    dateLabel() {
      if (!this.value) return '选择日期'
      if (this.value === this.todayKey) return '今天'
      const d = dayjs(this.value)
      if (!d.isValid()) return this.value
      if (d.year() === dayjs(this.todayKey).year()) {
        return d.format('M月D日')
      }
      return d.format('YYYY年M月D日')
    },
    daySet() {
      return new Set(this.days || [])
    },
    pickerOptions() {
      return {
        disabledDate: (date) => {
          const key = dayjs(date).format('YYYY-MM-DD')
          return !this.daySet.has(key)
        }
      }
    }
  },
  mounted() {
    this.updateBarLeft()
    window.addEventListener('resize', this.updateBarLeft)
    this._mainEl = document.querySelector('.app-main')
    if (this._mainEl) {
      this._ro = typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => this.updateBarLeft())
        : null
      if (this._ro) this._ro.observe(this._mainEl)
    }
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.updateBarLeft)
    if (this._ro && this._mainEl) this._ro.unobserve(this._mainEl)
  },
  methods: {
    updateBarLeft() {
      const main = document.querySelector('.app-main')
      if (!main) {
        this.barLeft = '0px'
        return
      }
      this.barLeft = `${Math.round(main.getBoundingClientRect().left)}px`
    },
    emitDay(day) {
      if (!day || day === this.value) return
      if (!this.days.includes(day)) return
      this.$emit('input', day)
      this.$emit('change', day)
    },
    onAggregateChange(mode) {
      this.$emit('update:aggregateMode', mode)
      this.$emit('aggregate-change', mode)
    },
    onPeriodKeyChange(key) {
      this.$emit('update:periodKey', key)
      this.$emit('period-change', key)
    },
    selectScope(value) {
      if (value === this.scope) return
      this.$emit('update:scope', value)
      this.$emit('scope-change', value)
    },
    selectBuilding(id) {
      if (id === this.buildingIndex) return
      this.$emit('update:buildingIndex', id)
      this.$emit('building-change', id)
    },
    shift(delta) {
      if (this.aggregateMode === 'all') return
      if (this.isDayMode) {
        const i = this.dayIndex + delta
        if (i < 0 || i >= this.days.length) return
        this.emitDay(this.days[i])
        return
      }
      const i = this.periodIndex + delta
      if (i < 0 || i >= this.periods.length) return
      this.onPeriodKeyChange(this.periods[i].key)
    },
    goToday() {
      this.emitDay(this.todayKey)
    },
    togglePicker() {
      if (!this.days.length) return
      const picker = this.$refs.picker
      if (!picker) return
      const opening = !this.pickerOpen
      this.pickerOpen = opening
      this.$nextTick(() => {
        if (opening) {
          if (typeof picker.focus === 'function') picker.focus()
          if (picker.pickerVisible != null) picker.pickerVisible = true
          const input = picker.$el && picker.$el.querySelector('input')
          if (input) {
            input.focus()
            input.click()
          }
        } else {
          this.closePicker()
        }
      })
    },
    closePicker() {
      this.pickerOpen = false
      const picker = this.$refs.picker
      if (!picker) return
      if (picker.pickerVisible != null) picker.pickerVisible = false
      if (typeof picker.handleClose === 'function') picker.handleClose()
    },
    onPick(val) {
      this.closePicker()
      if (val) this.emitDay(val)
    },
    onPickerBlur() {
      setTimeout(() => {
        const picker = this.$refs.picker
        if (picker && picker.pickerVisible) return
        this.pickerOpen = false
      }, 200)
    }
  }
}
</script>

<style scoped>
.ha-energy-period {
  position: fixed;
  bottom: 0;
  right: 0;
  z-index: 100;
  pointer-events: none;
}

.ha-energy-period-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
  pointer-events: auto;
  background: rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.ha-energy-period-bar {
  position: relative;
  z-index: 101;
  pointer-events: auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px 12px;
  min-height: 56px;
  padding: 8px 16px calc(8px + env(safe-area-inset-bottom, 0px));
  background: var(--card-background-color);
  border-top: 1px solid var(--divider-color);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.06);
}

.period-start,
.period-end {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.period-start {
  justify-content: flex-start;
  gap: 8px;
}

.period-end {
  justify-content: flex-end;
}

.period-center {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 3px;
  border-radius: 22px;
  background: rgba(var(--rgb-primary-color), 0.06);
  max-width: 100%;
  overflow-x: auto;
}

.period-building-btn {
  margin: 0;
  padding: 7px 14px;
  border: 0;
  border-radius: 18px;
  background: transparent;
  color: var(--secondary-text-color);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  line-height: 1.2;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.period-building-btn:hover {
  color: var(--primary-text-color);
  background: rgba(var(--rgb-primary-color), 0.08);
}

.period-building-btn.active {
  background: var(--card-background-color);
  color: var(--primary-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.period-agg-select {
  width: 96px;
  flex-shrink: 0;
}

.period-range-select {
  width: min(220px, 42vw);
}

.period-date-static {
  cursor: default;
}

.period-date-static:hover {
  background: transparent;
}

@media (max-width: 640px) {
  .ha-energy-period-bar {
    gap: 6px;
    padding-left: 10px;
    padding-right: 10px;
  }

  .period-building-btn {
    padding: 6px 10px;
    font-size: 12px;
  }

  .period-date-label {
    max-width: 72px;
  }

  .period-now-btn {
    padding: 8px 10px;
  }

  .period-agg-select {
    width: 84px;
  }
}

.period-date-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--primary-text-color);
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  max-width: 100%;
}

.period-date-btn:hover:not(:disabled) {
  background: rgba(var(--rgb-primary-color), 0.08);
}

.period-date-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.period-cal-icon {
  color: var(--primary-color);
}

.period-date-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.period-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--primary-text-color);
  cursor: pointer;
}

.period-icon-btn:hover:not(:disabled) {
  background: rgba(var(--rgb-primary-color), 0.08);
  color: var(--primary-color);
}

.period-icon-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.period-now-btn {
  margin: 0 0 0 4px;
  padding: 8px 14px;
  border: 0;
  border-radius: 18px;
  background: rgba(var(--rgb-primary-color), 0.12);
  color: var(--primary-color);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.period-now-btn:hover:not(:disabled) {
  background: rgba(var(--rgb-primary-color), 0.2);
}

.period-now-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.period-picker-hidden {
  position: absolute;
  width: 0 !important;
  height: 0 !important;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}
</style>

<style>
/* 日期面板向上展开（贴近 HA energy overview） */
.ha-energy-period-popper.el-picker-panel {
  margin-bottom: 8px;
}
</style>
