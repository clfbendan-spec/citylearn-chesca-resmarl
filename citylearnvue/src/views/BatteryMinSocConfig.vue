<template>
  <div class="battery-min-soc-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">小时电池下限配置</h2>
        <p class="page-desc">
          配置 CHESCA 算法（local_evaluation_copy.py）电池 SOC 与负荷平衡参数。
          保存后，通过代码编辑器执行该脚本时，Java 会自动将配置传入算法。
        </p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadConfig">刷新</el-button>
        <el-button @click="handleReset">恢复默认</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never" class="config-card">
      <div class="config-layout">
        <aside class="config-panel">
          <div class="panel-title">SOC 参数配置</div>

          <div class="form-section">
            <div class="section-title">全局上限</div>
            <div class="form-item">
              <label class="form-label">正常时段 SOC 上限 (max_soc_normal)</label>
              <div class="soc-input-row">
                <el-input-number
                  v-model="maxSocNormalPercent"
                  :min="0"
                  :max="100"
                  :step="1"
                  :precision="0"
                  controls-position="right"
                  class="percent-input"
                />
                <span class="percent-suffix">%</span>
              </div>
            </div>
            <div class="form-item">
              <label class="form-label">停电时段 SOC 上限 (max_soc_outage)</label>
              <div class="soc-input-row">
                <el-input-number
                  v-model="maxSocOutagePercent"
                  :min="0"
                  :max="100"
                  :step="1"
                  :precision="0"
                  controls-position="right"
                  class="percent-input"
                />
                <span class="percent-suffix">%</span>
              </div>
            </div>
            <div class="form-item">
              <label class="form-label">停电 SOC 最大降幅 (max_soc_reduction_in_outage)</label>
              <div class="soc-input-row">
                <el-input-number
                  v-model="maxSocReductionInOutagePercent"
                  :min="0"
                  :max="100"
                  :step="1"
                  :precision="0"
                  controls-position="right"
                  class="percent-input"
                />
                <span class="percent-suffix">%</span>
              </div>
            </div>
          </div>

          <div class="form-section">
            <div class="section-title">小时下限</div>
          <div class="form-item">
            <label class="form-label">选择时段</label>
            <el-select
              v-model="selectedHour"
              placeholder="请选择小时"
              class="hour-select"
              filterable
            >
              <el-option
                v-for="row in hourRows"
                :key="row.hour"
                :label="row.hourLabel"
                :value="row.hour"
              />
            </el-select>
          </div>
          <div class="form-item">
            <label class="form-label">电池 SOC 下限</label>
            <div class="soc-input-row">
              <el-input-number
                v-model="currentMinSocPercent"
                :min="0"
                :max="100"
                :step="1"
                :precision="0"
                controls-position="right"
                class="percent-input"
              />
              <span class="percent-suffix">%</span>
            </div>
          </div>
          <div class="form-item hint-block">
            <label class="form-label">说明</label>
            <p class="hint-text">{{ currentHint }}</p>
          </div>
          </div>

          <div class="panel-tip">
            柱状图展示全部 24 小时下限；修改当前时段数值后图表即时更新。
          </div>
        </aside>

        <section class="chart-panel">
          <div class="chart-header">
            <span class="chart-title">24 小时 SOC 下限柱状图</span>
            <span class="chart-subtitle">当前选中：{{ currentHourLabel }}</span>
          </div>
          <div ref="chart" class="soc-chart" />
        </section>
      </div>
    </el-card>

    <el-card v-loading="loading" shadow="never" class="balance-card">
      <div class="balance-panel">
        <div class="panel-title">负荷平衡阈值</div>
        <p class="balance-desc">
          用于 CHESCA 阶段 4 社区负荷平衡：净负荷高于「均值 + B_high×标准差」时削减 DHW/冷机；
          低于「均值 − B_low×标准差」时增加 DHW 加热。
        </p>
        <div class="balance-form">
          <div class="form-item">
            <label class="form-label">B_low（增负荷阈值系数）</label>
            <el-input-number
              v-model="bLow"
              :min="0.01"
              :max="20"
              :step="0.01"
              :precision="2"
              controls-position="right"
              class="number-input"
            />
          </div>
          <div class="form-item">
            <label class="form-label">B_high（减负荷阈值系数）</label>
            <el-input-number
              v-model="bHigh"
              :min="0.01"
              :max="20"
              :step="0.01"
              :precision="2"
              controls-position="right"
              class="number-input"
            />
          </div>
        </div>
      </div>
    </el-card>

    <el-card v-loading="loading" shadow="never" class="balance-card tmp-card">
      <div class="balance-panel">
        <div class="panel-title">冷机削减比例</div>
        <p class="balance-desc">
          净负荷过高触发减负荷时，按该比例削减冷机（TMP）动作；0% 表示不削减，100% 表示可完全关闭冷机出力。
        </p>
        <div class="slider-form">
          <div class="slider-header">
            <label class="form-label">TMP_max_reduction_percent</label>
            <span class="slider-value">{{ tmpMaxReductionPercent }}%</span>
          </div>
          <el-slider
            v-model="tmpMaxReductionPercent"
            :min="0"
            :max="100"
            :step="1"
            :show-tooltip="true"
            :format-tooltip="formatPercentTooltip"
          />
        </div>
      </div>
    </el-card>

    <el-card v-loading="loading" shadow="never" class="balance-card tau-card">
      <div class="balance-panel">
        <div class="panel-title">预测步长</div>
        <p class="balance-desc">
          tau 控制 CHESCA 时序预测与电池树搜索向前看的步数，可选 1、2、3 步。
        </p>
        <div class="form-item tau-form-item">
          <label class="form-label">tau</label>
          <el-select v-model="tau" placeholder="请选择 tau" class="hour-select">
            <el-option
              v-for="option in tauOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>
      </div>
    </el-card>

    <el-card v-loading="loading" shadow="never" class="balance-card balance-type-card">
      <div class="balance-panel balance-type-panel">
        <div class="panel-title">电池树搜索适应度</div>
        <p class="balance-desc">
          balance_type 决定阶段 4 电池树搜索的代价函数形式，影响电池动作如何逼近目标净负荷。
        </p>
        <div class="form-item tau-form-item">
          <label class="form-label">balance_type</label>
          <el-select v-model="balanceType" placeholder="请选择 balance_type" class="hour-select">
            <el-option
              v-for="option in balanceTypeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>
        <div class="balance-type-notes">
          <div
            v-for="option in balanceTypeOptions"
            :key="option.value"
            :class="['type-note', { active: balanceType === option.value }]"
          >
            <div class="type-note-title">{{ option.label }}</div>
            <p class="type-note-desc">{{ option.desc }}</p>
            <p class="type-note-effect"><strong>效果：</strong>{{ option.effect }}</p>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import axios from 'axios'
import * as echarts from 'echarts'

const HOUR_HINTS = {
  0: '深夜低谷',
  5: '清晨抬升',
  10: '上午负荷',
  14: '午后高峰',
  18: '傍晚用电',
  23: '日末收尾'
}

const DEFAULT_MAX_SOC_NORMAL_PERCENT = 99
const DEFAULT_MAX_SOC_OUTAGE_PERCENT = 87
const DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE_PERCENT = 70
const DEFAULT_B_LOW = 1.18
const DEFAULT_B_HIGH = 1.0
const DEFAULT_TMP_MAX_REDUCTION_PERCENT = 0
const DEFAULT_TAU = 1

const TAU_OPTIONS = [
  { value: 1, label: '1 步' },
  { value: 2, label: '2 步' },
  { value: 3, label: '3 步' }
]

const DEFAULT_BALANCE_TYPE = 'C'

const BALANCE_TYPE_OPTIONS = [
  {
    value: 'A',
    label: 'A — 跟踪历史均值',
    desc: '代价 = |历史净负荷均值 − 当前步净负荷|。以长期历史均值为锚点，优先把当前净负荷拉回社区平均水平。',
    effect: '更强调回归历史平均用电水平，适合希望整体负荷围绕长期均值波动的场景。'
  },
  {
    value: 'B',
    label: 'B — 抑制步间波动',
    desc: '代价 = |上一步净负荷 − 当前步净负荷|。只关注相邻时间步之间的变化幅度，不直接参照历史均值。',
    effect: '更强调相邻小时负荷的平滑，对单步跳变惩罚更强，但不一定贴近长期均值。'
  },
  {
    value: 'C',
    label: 'C — 跟踪均值与预测中点（默认）',
    desc: '代价 = |(历史均值 + 预测净负荷) / 2 − 当前步净负荷|。同时考虑历史均值与下一步预测，取二者中点作为目标。',
    effect: 'CHESCA 默认方案，兼顾历史水平与短期预测，通常更有利于降低 ramping（负荷剧烈波动）指标。'
  }
]

/** 0~1 小数 → 百分比整数 */
function ratioToPercent(ratio) {
  return Math.round(Number(ratio) * 100)
}

/** 百分比 → 0~1 小数（保留 4 位，与后端 DECIMAL(6,4) 一致） */
function percentToRatio(percent) {
  return Math.round(Number(percent) * 100) / 10000
}

export default {
  name: 'BatteryMinSocConfig',
  data() {
    return {
      loading: false,
      saving: false,
      selectedHour: 0,
      maxSocNormalPercent: DEFAULT_MAX_SOC_NORMAL_PERCENT,
      maxSocOutagePercent: DEFAULT_MAX_SOC_OUTAGE_PERCENT,
      maxSocReductionInOutagePercent: DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE_PERCENT,
      bLow: DEFAULT_B_LOW,
      bHigh: DEFAULT_B_HIGH,
      tmpMaxReductionPercent: DEFAULT_TMP_MAX_REDUCTION_PERCENT,
      tau: DEFAULT_TAU,
      tauOptions: TAU_OPTIONS,
      balanceType: DEFAULT_BALANCE_TYPE,
      balanceTypeOptions: BALANCE_TYPE_OPTIONS,
      hourRows: [],
      chart: null,
      resizeObserver: null
    }
  },
  computed: {
    currentRow() {
      return this.hourRows.find((row) => row.hour === this.selectedHour) || this.hourRows[0]
    },
    currentMinSocPercent: {
      get() {
        return this.currentRow ? this.currentRow.minSocPercent : 60
      },
      set(value) {
        if (this.currentRow) {
          this.currentRow.minSocPercent = value
        }
      }
    },
    currentHint() {
      return this.currentRow ? this.currentRow.hint : ''
    },
    currentHourLabel() {
      return this.currentRow ? this.currentRow.hourLabel : ''
    }
  },
  watch: {
    hourRows: {
      deep: true,
      handler() {
        this.renderChart()
      }
    },
    selectedHour(val) {
      if (typeof val === 'string') {
        this.selectedHour = Number(val)
        return
      }
      this.renderChart()
    },
    maxSocNormalPercent() {
      this.renderChart()
    },
    maxSocOutagePercent() {
      this.renderChart()
    }
  },
  created() {
    this.initRows()
    this.loadConfig()
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    window.addEventListener('resize', this.handleResize)
    if (typeof ResizeObserver !== 'undefined' && this.$refs.chart) {
      this.resizeObserver = new ResizeObserver(() => this.handleResize())
      this.resizeObserver.observe(this.$refs.chart)
    }
    this.renderChart()
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize)
    if (this.resizeObserver) this.resizeObserver.disconnect()
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    initRows() {
      this.hourRows = Array.from({ length: 24 }, (_, hour) => ({
        hour,
        hourLabel: `${String(hour).padStart(2, '0')}:00 - ${String(hour).padStart(2, '0')}:59`,
        minSocPercent: 60,
        hint: HOUR_HINTS[hour] || '电池树搜索 SOC 下限约束'
      }))
    },
    applyConfig(data) {
      if (!data) return
      if (data.minSocPerHour) {
        this.applyMinSocMap(data.minSocPerHour)
      }
      if (data.maxSocNormal != null) {
        this.maxSocNormalPercent = ratioToPercent(data.maxSocNormal)
      }
      if (data.maxSocOutage != null) {
        this.maxSocOutagePercent = ratioToPercent(data.maxSocOutage)
      }
      if (data.maxSocReductionInOutage != null) {
        this.maxSocReductionInOutagePercent = ratioToPercent(data.maxSocReductionInOutage)
      }
      if (data.bLow != null) {
        this.bLow = Number(data.bLow)
      }
      if (data.bHigh != null) {
        this.bHigh = Number(data.bHigh)
      }
      if (data.tmpMaxReductionPercent != null) {
        this.tmpMaxReductionPercent = ratioToPercent(data.tmpMaxReductionPercent)
      }
      if (data.tau != null) {
        this.tau = Number(data.tau)
      }
      if (data.balanceType != null) {
        this.balanceType = String(data.balanceType).toUpperCase()
      }
    },
    applyMinSocMap(configMap) {
      if (!configMap) return
      this.hourRows.forEach((row) => {
        const key = String(row.hour)
        if (Object.prototype.hasOwnProperty.call(configMap, key)) {
          row.minSocPercent = ratioToPercent(configMap[key])
        }
      })
    },
    buildPayload() {
      const minSocPerHour = {}
      this.hourRows.forEach((row) => {
        minSocPerHour[String(row.hour)] = percentToRatio(row.minSocPercent)
      })
      return {
        minSocPerHour,
        maxSocNormal: percentToRatio(this.maxSocNormalPercent),
        maxSocOutage: percentToRatio(this.maxSocOutagePercent),
        maxSocReductionInOutage: percentToRatio(this.maxSocReductionInOutagePercent),
        bLow: this.bLow,
        bHigh: this.bHigh,
        tmpMaxReductionPercent: percentToRatio(this.tmpMaxReductionPercent),
        tau: this.tau,
        balanceType: this.balanceType
      }
    },
    formatPercentTooltip(value) {
      return `${value}%`
    },
    handleResize() {
      if (this.chart) this.chart.resize()
    },
    renderChart() {
      if (!this.chart || !this.hourRows.length) return

      const hours = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, '0'))
      const values = this.hourRows.map((row) => row.minSocPercent)
      const selectedIndex = Number(this.selectedHour)

      this.chart.setOption({
        animation: true,
        animationDuration: 200,
        grid: {
          left: 48,
          right: 24,
          top: 36,
          bottom: 40
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter(params) {
            const point = Array.isArray(params) ? params[0] : params
            if (!point) return ''
            return `${point.axisValue} 时<br/>SOC 下限：${point.value}%`
          }
        },
        xAxis: {
          type: 'category',
          name: '小时',
          nameLocation: 'middle',
          nameGap: 28,
          data: hours,
          axisLabel: {
            interval: 0
          }
        },
        yAxis: {
          type: 'value',
          name: 'SOC (%)',
          min: 0,
          max: 100,
          splitLine: {
            lineStyle: { type: 'dashed', color: '#e4e7ed' }
          }
        },
        series: [
          {
            name: 'SOC 下限',
            type: 'bar',
            barMaxWidth: 28,
            data: values,
            itemStyle: {
              color: (params) => (params.dataIndex === selectedIndex ? '#E6A23C' : '#409EFF')
            },
            label: {
              show: true,
              position: 'top',
              formatter: (params) => {
                if (params.dataIndex !== selectedIndex) return ''
                return `${params.value}%`
              },
              fontSize: 11,
              color: '#E6A23C'
            },
            markLine: {
              symbol: 'none',
              label: {
                formatter: '{b}',
                fontSize: 11
              },
              data: [
                {
                  name: `正常上限 ${this.maxSocNormalPercent}%`,
                  yAxis: this.maxSocNormalPercent,
                  lineStyle: { color: '#67C23A', type: 'dashed' }
                },
                {
                  name: `停电上限 ${this.maxSocOutagePercent}%`,
                  yAxis: this.maxSocOutagePercent,
                  lineStyle: { color: '#F56C6C', type: 'dashed' }
                }
              ]
            }
          }
        ]
      }, true)
    },
    async loadConfig() {
      this.loading = true
      try {
        const response = await axios.get('/api/web/basedata/getBatteryMinSocConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
        } else {
          this.$message.error((response.data && response.data.message) || '加载配置失败')
        }
      } catch (e) {
        this.$message.error('加载配置失败，请确认已执行 algorithm_config.sql 建表并重启 Java 服务')
      } finally {
        this.loading = false
        this.$nextTick(() => this.renderChart())
      }
    },
    async handleSave() {
      this.saving = true
      try {
        const response = await axios.post('/api/web/basedata/saveBatteryMinSocConfig', this.buildPayload())
        if (response.data && response.data.code === 0) {
          this.$message.success('保存成功')
        } else {
          this.$message.error((response.data && response.data.message) || '保存失败')
        }
      } catch (e) {
        this.$message.error('保存失败')
      } finally {
        this.saving = false
      }
    },
    async handleReset() {
      try {
        await this.$confirm('确定恢复为 CHESCA 算法内置默认值吗？', '提示', { type: 'warning' })
      } catch {
        return
      }
      this.loading = true
      try {
        const response = await axios.post('/api/web/basedata/resetBatteryMinSocConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
          this.$message.success('已恢复默认值')
        } else {
          this.$message.error((response.data && response.data.message) || '恢复失败')
        }
      } catch (e) {
        this.$message.error('恢复失败')
      } finally {
        this.loading = false
        this.$nextTick(() => this.renderChart())
      }
    }
  }
}
</script>

<style scoped>
.battery-min-soc-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: 16px 20px 24px;
  box-sizing: border-box;
  background: #f5f7fa;
}

.page-header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}

.page-title {
  margin: 0 0 6px;
  font-size: 20px;
  color: #303133;
}

.page-desc {
  margin: 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.config-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  min-height: 480px;
}

.config-card >>> .el-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  min-height: 0;
}

.config-layout {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 420px;
}

.config-panel {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #e4e7ed;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  color: #606266;
}

.hour-select {
  width: 100%;
}

.soc-input-row {
  display: flex;
  align-items: center;
  width: 100%;
}

.percent-input {
  flex: 1;
  width: 100%;
}

.percent-input >>> .el-input-number {
  width: 100%;
}

.percent-suffix {
  margin-left: 8px;
  color: #606266;
  font-size: 13px;
}

.hint-block {
  margin-top: 4px;
}

.hint-text {
  margin: 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.panel-tip {
  margin-top: auto;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
  background: #f0f2f5;
  border-radius: 6px;
}

.chart-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 12px 12px 8px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.chart-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.chart-subtitle {
  font-size: 12px;
  color: #909399;
}

.soc-chart {
  flex: 1;
  min-height: 360px;
}

.balance-card {
  margin-top: 12px;
  border-radius: 8px;
}

.balance-card >>> .el-card__body {
  padding: 16px;
}

.balance-panel {
  max-width: 640px;
}

.balance-desc {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.balance-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.number-input {
  width: 100%;
}

.number-input >>> .el-input-number {
  width: 100%;
}

.slider-form {
  max-width: 640px;
}

.slider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.slider-value {
  font-size: 14px;
  font-weight: 600;
  color: #409EFF;
}

.tmp-card {
  margin-top: 12px;
}

.tau-card {
  margin-top: 12px;
}

.tau-form-item {
  max-width: 320px;
}

.balance-type-panel {
  max-width: 720px;
}

.balance-type-notes {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.type-note {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.type-note.active {
  border-color: #409EFF;
  background: #ecf5ff;
}

.type-note-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.type-note-desc,
.type-note-effect {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #606266;
}

.type-note-effect {
  margin-bottom: 0;
  color: #909399;
}

.balance-type-card {
  margin-top: 12px;
}

@media (max-width: 960px) {
  .config-layout {
    flex-direction: column;
  }

  .config-panel {
    flex: none;
    width: 100%;
  }

  .soc-chart {
    min-height: 300px;
  }

  .balance-form {
    grid-template-columns: 1fr;
  }
}
</style>
