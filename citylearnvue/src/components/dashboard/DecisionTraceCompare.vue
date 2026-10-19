<template>
  <div class="dt-compare">
    <div class="cmp-head">
      <div class="cmp-head-title">
        <h5>同步回放 · 两个 run 并排</h5>
        <p class="cmp-head-hint">
          同一 step 对齐（不按下标）· 左=参照，右=对照 · Δ 只在两边都有该步时给出
        </p>
      </div>
      <el-tag v-if="coverage.bothCount" size="mini" type="info">
        共同步 {{ coverage.bothCount }} / 并集 {{ coverage.unionCount }}
      </el-tag>
    </div>

    <div v-if="!options.length" class="cmp-empty">
      <el-empty description="当前分组只加载了 1 个模型的决策日志；请先在「选择对比模型」里多选一个" :image-size="64" />
    </div>

    <template v-else>
      <div class="cmp-pick">
        <span class="pick-tag pick-left">左</span>
        <el-select v-model="leftSim" size="small" class="pick-select" placeholder="参照 run">
          <el-option
            v-for="s in options"
            :key="'L-' + s"
            :label="s"
            :value="s"
            :disabled="s === rightSim"
          />
        </el-select>
        <span class="pick-vs">对比</span>
        <span class="pick-tag pick-right">右</span>
        <el-select v-model="rightSim" size="small" class="pick-select" placeholder="对照 run">
          <el-option
            v-for="s in options"
            :key="'R-' + s"
            :label="s"
            :value="s"
            :disabled="s === leftSim"
          />
        </el-select>
      </div>

      <p v-if="coverageHint" :class="['cmp-cover-hint', { 'is-warn': coverageWarn }]">{{ coverageHint }}</p>

      <div v-if="spark.leftPath || spark.rightPath" class="cmp-spark">
        <svg viewBox="0 0 600 64" preserveAspectRatio="none" class="spark-svg">
          <path :d="spark.leftPath" fill="none" stroke="#409eff" stroke-width="1.2" vector-effect="non-scaling-stroke" />
          <path :d="spark.rightPath" fill="none" stroke="#67c23a" stroke-width="1.2" vector-effect="non-scaling-stroke" />
          <line :x1="cursorX" y1="0" :x2="cursorX" y2="64" stroke="#f56c6c" stroke-width="1" stroke-dasharray="3 2" />
        </svg>
        <div class="spark-axis">
          <span>全段社区净负荷 · 蓝=左 / 绿=右</span>
          <span v-if="spark.min != null">
            {{ spark.min.toFixed(1) }} ~ {{ spark.max.toFixed(1) }} kW
          </span>
        </div>
      </div>

      <div v-if="frames.length" class="cmp-nav">
        <el-button-group>
          <el-button size="mini" icon="el-icon-arrow-left" :disabled="idx <= 0" @click="stepBy(-1)" />
          <el-button
            size="mini"
            :icon="playing ? 'el-icon-video-pause' : 'el-icon-video-play'"
            @click="togglePlay"
          />
          <el-button
            size="mini"
            icon="el-icon-arrow-right"
            :disabled="idx >= frames.length - 1"
            @click="stepBy(1)"
          />
        </el-button-group>
        <el-slider
          v-model="idx"
          class="cmp-slider"
          :min="0"
          :max="Math.max(0, frames.length - 1)"
          :format-tooltip="formatIdxTooltip"
          @change="onIdxChange"
        />
        <span class="cmp-steplabel">
          Step {{ cur.step == null ? '—' : cur.step }}
          <span class="cmp-hour" v-if="hourLabel">· {{ hourLabel }}</span>
        </span>
        <el-radio-group v-model="speed" size="mini" @change="restartTimer">
          <el-radio-button :label="1">1×</el-radio-button>
          <el-radio-button :label="2">2×</el-radio-button>
          <el-radio-button :label="4">4×</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="frames.length" class="cmp-grid">
        <div class="cmp-side side-left">
          <div class="side-head">
            <span class="side-dot dot-left" />
            <span class="side-name" :title="leftSim">{{ leftSim || '—' }}</span>
          </div>
          <div v-if="cur.left" class="side-body">
            <div class="side-metric">
              <span class="metric-label">社区净负荷</span>
              <span class="metric-value">
                {{ fmt(cur.left.netKw, 2) }}<small> kW</small>
              </span>
              <span v-if="cur.left.peakRatio != null" class="metric-sub">
                峰值比 {{ pct(cur.left.peakRatio) }}
              </span>
              <span v-else-if="cur.left.ratioVsSegmentPeak != null" class="metric-sub">
                占全段峰值 {{ pct(cur.left.ratioVsSegmentPeak) }}
              </span>
              <el-tag v-if="cur.left.isPeakStep" size="mini" type="danger">峰步</el-tag>
            </div>
            <div class="side-soc">
              <span>电池 SOC <b>{{ fmt(cur.left.buildings[0] && cur.left.buildings[0].soc, 3) }}</b></span>
              <span>DHW SOC <b>{{ fmt(cur.left.buildings[0] && cur.left.buildings[0].dhwSoc, 3) }}</b></span>
            </div>
            <table class="side-table">
              <thead>
                <tr>
                  <th>建筑</th>
                  <th v-for="d in cur.left.dimNames" :key="'lh-' + d">{{ d }}</th>
                  <th>SOC</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in cur.left.buildings" :key="'lb-' + b.id">
                  <td class="cell-bid">{{ b.id }}</td>
                  <td v-for="(v, di) in b.dims" :key="'ld-' + b.id + '-' + di">{{ fmt(v, 3) }}</td>
                  <td>{{ fmt(b.soc, 3) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="side-missing">该 run 在这一步没有记录</div>
        </div>

        <div class="cmp-side side-right">
          <div class="side-head">
            <span class="side-dot dot-right" />
            <span class="side-name" :title="rightSim">{{ rightSim || '—' }}</span>
          </div>
          <div v-if="cur.right" class="side-body">
            <div class="side-metric">
              <span class="metric-label">社区净负荷</span>
              <span class="metric-value">
                {{ fmt(cur.right.netKw, 2) }}<small> kW</small>
              </span>
              <span v-if="cur.right.peakRatio != null" class="metric-sub">
                峰值比 {{ pct(cur.right.peakRatio) }}
              </span>
              <el-tag v-if="cur.right.isPeakStep" size="mini" type="danger">峰步</el-tag>
            </div>
            <div class="side-soc">
              <span>电池 SOC <b>{{ fmt(cur.right.buildings[0] && cur.right.buildings[0].soc, 3) }}</b></span>
              <span>DHW SOC <b>{{ fmt(cur.right.buildings[0] && cur.right.buildings[0].dhwSoc, 3) }}</b></span>
            </div>
            <table class="side-table">
              <thead>
                <tr>
                  <th>建筑</th>
                  <th v-for="d in cur.right.dimNames" :key="'rh-' + d">{{ d }}</th>
                  <th>SOC</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in cur.right.buildings" :key="'rb-' + b.id">
                  <td class="cell-bid">{{ b.id }}</td>
                  <td v-for="(v, di) in b.dims" :key="'rd-' + b.id + '-' + di">{{ fmt(v, 3) }}</td>
                  <td>{{ fmt(b.soc, 3) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="side-missing">该 run 在这一步没有记录</div>
        </div>
      </div>

      <div v-if="frames.length" class="cmp-diff">
        <div class="diff-head">
          <span class="diff-title">本步差异（右 − 左）</span>
          <span class="diff-net">
            净负荷
            <b :class="['delta', deltaClass(diff && diff.netKw, 'net')]">
              {{ signed(diff && diff.netKw, 2) }}
            </b>
            kW
            <template v-if="diff && diff.peakRatio != null">
              · 峰值比 <b :class="['delta', deltaClass(diff.peakRatio, 'ratio')]">{{ signedPct(diff.peakRatio) }}</b>
            </template>
          </span>
        </div>
        <table v-if="diff && diff.buildings.length" class="diff-table">
          <thead>
            <tr>
              <th>建筑</th>
              <th v-for="(d, di) in diffDimNames" :key="'dh-' + di">Δ{{ d }}</th>
              <th>ΔSOC</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(b, bi) in diff.buildings" :key="'db-' + bi">
              <td class="cell-bid">{{ b.leftId }}</td>
              <td v-for="(v, di) in b.dims" :key="'dd-' + bi + '-' + di">
                <span :class="['delta', deltaClass(v, 'act')]">{{ signed(v, 3) }}</span>
              </td>
              <td><span :class="['delta', deltaClass(b.soc, 'soc')]">{{ signed(b.soc, 3) }}</span></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="diff-missing">两边都缺该步的数据，无法做差</p>
      </div>
    </template>
  </div>
</template>

<script>
import {
  alignFrames,
  buildNetSparkPaths,
  diffFrames,
  diffLevel,
  fmtNum,
  frameCoverage,
  sparkCursorX
} from '@/utils/decisionTraceCompare'

const BASE_INTERVAL_MS = 900

export default {
  name: 'DecisionTraceCompare',
  props: {
    decisionTraceBySim: { type: Object, default: () => ({}) },
    simNames: { type: Array, default: () => [] },
    activeSim: { type: String, default: '' }
  },
  data() {
    return {
      leftSim: '',
      rightSim: '',
      idx: 0,
      speed: 1,
      playing: false,
      timer: null
    }
  },
  computed: {
    options() {
      const declared = (this.simNames || []).filter((s) => !!s)
      if (declared.length) return declared
      return Object.keys(this.decisionTraceBySim || {})
    },
    leftTrace() {
      return this.decisionTraceBySim[this.leftSim] || null
    },
    rightTrace() {
      return this.decisionTraceBySim[this.rightSim] || null
    },
    frames() {
      if (!this.leftTrace && !this.rightTrace) return []
      return alignFrames(this.leftTrace, this.rightTrace)
    },
    coverage() {
      return frameCoverage(this.leftTrace, this.rightTrace)
    },
    coverageHint() {
      const c = this.coverage
      if (!c.leftCount || !c.rightCount) {
        return '至少一侧没有决策日志；该侧每步都会显示「无记录」。'
      }
      const lEnd = c.leftEnd || 0
      const rEnd = c.rightEnd || 0
      const bigger = Math.max(lEnd, rEnd)
      if (bigger > 0 && Math.abs(lEnd - rEnd) > bigger * 0.1) {
        return `⚠ 两侧封面差异大（左 ${c.leftCount} 步 / 右 ${c.rightCount} 步，最远 step ${lEnd} vs ${rEnd}），`
          + '很可能来自不同数据集（典型为 local 720 步 / online 2208 步）。'
          + '这类组合**不可比 KPI**，本页只做逐步过程对照。'
      }
      const parts = []
      if (c.leftOnlyCount) parts.push(`仅左侧有 ${c.leftOnlyCount} 步`)
      if (c.rightOnlyCount) parts.push(`仅右侧有 ${c.rightOnlyCount} 步`)
      if (!parts.length) return ''
      return `两侧封面略有差异：${parts.join('，')}；这些步的 Δ 会留空（不做差）。`
    },
    coverageWarn() {
      const c = this.coverage
      if (!c.leftCount || !c.rightCount) return false
      const lEnd = c.leftEnd || 0
      const rEnd = c.rightEnd || 0
      return Math.max(lEnd, rEnd) > 0 && Math.abs(lEnd - rEnd) > Math.max(lEnd, rEnd) * 0.1
    },
    spark() {
      return buildNetSparkPaths(this.frames, 600, 64)
    },
    cursorX() {
      return sparkCursorX(this.idx, this.frames.length, 600)
    },
    cur() {
      return this.frames[this.idx] || { step: null, left: null, right: null }
    },
    diff() {
      return diffFrames(this.cur.left, this.cur.right)
    },
    diffDimNames() {
      const l = this.cur.left && this.cur.left.dimNames
      const r = this.cur.right && this.cur.right.dimNames
      if (!l || !r) return (l || r || [])
      return l.length >= r.length ? l : r
    },
    hourLabel() {
      const h = this.cur.left && this.cur.left.hour != null
        ? this.cur.left.hour
        : (this.cur.right ? this.cur.right.hour : null)
      if (h == null || h === '') return ''
      const n = Number(h)
      if (!Number.isFinite(n)) return String(h)
      return `${String(Math.floor(n)).padStart(2, '0')}:00`
    }
  },
  watch: {
    options: {
      immediate: true,
      handler() {
        this.initSides()
      }
    },
    activeSim() {
      this.initSides()
    },
    frames() {
      const max = Math.max(0, this.frames.length - 1)
      if (this.idx > max) this.idx = max
      if (this.idx < 0) this.idx = 0
    },
    leftSim() {
      this.idx = 0
      this.stop()
    },
    rightSim() {
      this.idx = 0
      this.stop()
    }
  },
  beforeDestroy() {
    this.stop()
  },
  methods: {
    fmt(v, d = 2) {
      return fmtNum(v, d)
    },
    pct(v) {
      const n = Number(v)
      return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '—'
    },
    signed(v, d = 2) {
      const n = Number(v)
      if (!Number.isFinite(n)) return '—'
      const s = n.toFixed(d)
      return n > 0 ? `+${s}` : s
    },
    signedPct(v) {
      const n = Number(v)
      if (!Number.isFinite(n)) return '—'
      const s = `${(n * 100).toFixed(2)}%`
      return n > 0 ? `+${s}` : s
    },
    deltaClass(v, kind) {
      if (v == null || !Number.isFinite(Number(v))) return 'd-none'
      const level = diffLevel(Number(v), 1)
      const base = `d-${level}`
      const n = Number(v)
      if (Math.abs(n) < 1e-9) return `${base} d-zero`
      if (kind === 'net') return `${base} ${n > 0 ? 'd-up' : 'd-down'}`
      return base
    },
    initSides() {
      const opts = this.options
      if (!opts.length) {
        this.leftSim = ''
        this.rightSim = ''
        return
      }
      if (!opts.includes(this.leftSim)) {
        this.leftSim = (this.activeSim && opts.includes(this.activeSim))
          ? this.activeSim
          : opts[0]
      }
      if (!opts.includes(this.rightSim) || this.rightSim === this.leftSim) {
        const other = opts.find((s) => s !== this.leftSim)
        this.rightSim = other || this.leftSim
      }
    },
    stepBy(delta) {
      const next = this.idx + delta
      if (next < 0 || next > this.frames.length - 1) return
      this.idx = next
    },
    onIdxChange() {
      this.stop()
    },
    formatIdxTooltip(v) {
      const f = this.frames[v]
      return f && f.step != null ? `Step ${f.step}` : `#${v}`
    },
    togglePlay() {
      if (this.playing) {
        this.stop()
        return
      }
      if (this.idx >= this.frames.length - 1) this.idx = 0
      this.playing = true
      this.startTimer()
    },
    startTimer() {
      this.clearTimer()
      const interval = Math.max(80, Math.round(BASE_INTERVAL_MS / (this.speed || 1)))
      this.timer = setInterval(() => {
        if (this.idx >= this.frames.length - 1) {
          this.stop()
          return
        }
        this.idx += 1
      }, interval)
    },
    restartTimer() {
      if (this.playing) this.startTimer()
    },
    clearTimer() {
      if (this.timer) {
        clearInterval(this.timer)
        this.timer = null
      }
    },
    stop() {
      this.playing = false
      this.clearTimer()
    }
  }
}
</script>

<style scoped>
.dt-compare {
  padding: 4px 0 8px;
}
.cmp-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.cmp-head-title h5 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.cmp-head-hint {
  margin: 0;
  font-size: 12px;
  color: #909399;
}
.cmp-empty {
  padding: 12px 0 4px;
}
.cmp-pick {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.pick-tag {
  font-size: 12px;
  padding: 1px 7px;
  border-radius: 3px;
  color: #fff;
}
.pick-left {
  background: #409eff;
}
.pick-right {
  background: #67c23a;
}
.pick-vs {
  font-size: 12px;
  color: #909399;
}
.pick-select {
  width: 210px;
}
.cmp-cover-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #e6a23c;
}
.cmp-cover-hint.is-warn {
  color: #f56c6c;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  padding: 6px 10px;
  line-height: 1.6;
}
.cmp-spark {
  margin-bottom: 10px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
  padding: 6px 8px 4px;
}
.spark-svg {
  display: block;
  width: 100%;
  height: 64px;
}
.spark-axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #909399;
  padding: 2px 2px 0;
}
.cmp-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.cmp-slider {
  flex: 1;
  min-width: 180px;
}
.cmp-steplabel {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}
.cmp-hour {
  color: #909399;
}
.cmp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.cmp-side {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
  padding: 10px 12px;
  min-height: 210px;
}
.side-left {
  border-top: 2px solid #409eff;
}
.side-right {
  border-top: 2px solid #67c23a;
}
.side-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.side-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.dot-left {
  background: #409eff;
}
.dot-right {
  background: #67c23a;
}
.side-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-metric {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.metric-label {
  font-size: 12px;
  color: #909399;
}
.metric-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.metric-value small {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.metric-sub {
  font-size: 12px;
  color: #606266;
}
.side-soc {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}
.side-soc b {
  color: #303133;
  font-weight: 600;
}
.side-table,
.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.side-table th,
.diff-table th {
  text-align: right;
  font-weight: 500;
  color: #909399;
  padding: 4px 6px;
  border-bottom: 1px solid #ebeef5;
  white-space: nowrap;
}
.side-table th:first-child,
.diff-table th:first-child {
  text-align: left;
}
.side-table td,
.diff-table td {
  text-align: right;
  padding: 4px 6px;
  border-bottom: 1px solid #f5f7fa;
  color: #303133;
  font-variant-numeric: tabular-nums;
}
.side-table td.cell-bid,
.diff-table td.cell-bid {
  text-align: left;
  color: #606266;
}
.side-missing,
.diff-missing {
  font-size: 12px;
  color: #c0c4cc;
  padding: 24px 0;
  text-align: center;
}
.cmp-diff {
  margin-top: 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fafafa;
  padding: 10px 12px;
}
.diff-head {
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.diff-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.diff-net {
  font-size: 12px;
  color: #606266;
}
.delta {
  font-variant-numeric: tabular-nums;
}
.d-none,
.d-zero {
  color: #c0c4cc;
}
.d-small {
  color: #909399;
}
.d-medium {
  color: #e6a23c;
}
.d-large {
  color: #f56c6c;
  font-weight: 600;
}
.d-up {
  color: #f56c6c;
}
.d-down {
  color: #67c23a;
}
</style>
