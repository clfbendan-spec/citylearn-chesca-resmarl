<template>
  <div class="decision-trace-log">
    <div class="log-toolbar">
      <div class="step-nav">
        <el-button size="mini" icon="el-icon-arrow-left" :disabled="!canPrev" @click="prevStep" />
        <el-slider
          v-model="currentStep"
          class="step-slider-inline"
          :min="stepMin"
          :max="stepMax"
          :format-tooltip="formatStepTooltip"
          @change="onStepChange"
        />
        <el-button size="mini" icon="el-icon-arrow-right" :disabled="!canNext" @click="nextStep" />
      </div>
      <span class="step-label">Step {{ currentStep }} · Hour {{ currentHour }}</span>
      <el-input
        v-model="searchText"
        size="small"
        clearable
        placeholder="搜索推演内容…"
        prefix-icon="el-icon-search"
        class="search-input"
      />
    </div>

    <div v-if="currentNarratives.length" class="narrative-panel">
      <h5 class="sub-title">推演剧本（分层解释）</h5>
      <p class="narrative-hint">悬停任意一行可查看对应 Python 源码片段</p>
      <div
        v-for="item in currentNarratives"
        :key="item.building"
        class="narrative-block"
      >
        <div v-if="filteredBuildings.length > 1" class="narrative-building-label">
          {{ buildingLabel(item.building) }}
        </div>
        <div class="narrative-lines">
          <el-tooltip
            v-for="(entry, idx) in item.entries"
            :key="idx"
            placement="right"
            :open-delay="280"
            popper-class="narrative-code-tooltip"
          >
            <div slot="content" class="code-tooltip-inner">
              <div class="code-tooltip-header">
                {{ entry.source_file }} · L{{ entry.source_line_start }}–{{ entry.source_line_end }}
              </div>
              <div class="code-tooltip-label">{{ entry.source_label }}</div>
              <pre class="code-tooltip-pre">{{ entry.code_snippet }}</pre>
            </div>
            <div class="narrative-line">{{ entry.text }}</div>
          </el-tooltip>
        </div>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="10">
        <div class="phase-panel">
          <h5 class="sub-title">阶段推演</h5>
          <el-timeline v-if="currentStepData">
            <el-timeline-item
              v-for="phase in currentStepData.phases"
              :key="phase.phase"
              :timestamp="`阶段 ${phase.phase}`"
              placement="top"
              :type="phaseType(phase.phase)"
            >
              <p class="phase-name">{{ phase.name }}</p>
              <p class="phase-summary">{{ phase.summary }}</p>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="无该步推演数据" :image-size="64" />
        </div>
      </el-col>

      <el-col :span="14">
        <div class="building-panel">
          <h5 class="sub-title">分建筑决策明细</h5>
          <el-table
            v-if="filteredBuildings.length"
            :data="filteredBuildings"
            size="small"
            border
            stripe
            max-height="520"
          >
            <el-table-column label="建筑" width="72" align="center">
              <template slot-scope="{ row }">{{ buildingLabel(row.building) }}</template>
            </el-table-column>
            <el-table-column label="工况" width="80" align="center">
              <template slot-scope="{ row }">
                <el-tag :type="row.outage_flag ? 'danger' : 'success'" size="mini">
                  {{ row.outage_flag ? '停电' : '正常' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="初稿 DHW/ELE/TMP" min-width="150">
              <template slot-scope="{ row }">
                {{ fmtAction(row.actions && row.actions.init) }}
              </template>
            </el-table-column>
            <el-table-column label="终稿 DHW/ELE/TMP" min-width="150">
              <template slot-scope="{ row }">
                {{ fmtAction(row.actions && row.actions.final) }}
              </template>
            </el-table-column>
            <el-table-column label="残差 ELE" min-width="160">
              <template slot-scope="{ row }">
                <span v-if="row.residual && row.residual.enabled">
                  {{ fmtResidualEle(row.residual) }}
                </span>
                <el-tag v-else type="info" size="mini">关闭</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="α / 应用" width="100" align="center">
              <template slot-scope="{ row }">
                <template v-if="row.residual && row.residual.enabled">
                  {{ fmtNum(row.residual.alpha, 2) }}
                  <el-tag :type="row.residual.applied ? 'warning' : 'info'" size="mini">
                    {{ row.residual.applied ? '已修正' : 'Δ=0' }}
                  </el-tag>
                </template>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="Refine" width="88" align="center">
              <template slot-scope="{ row }">
                <el-tag v-if="row.refine && row.refine.trigger_reduce" type="danger" size="mini">减负荷</el-tag>
                <el-tag v-else-if="row.refine && row.refine.trigger_increase" type="success" size="mini">增负荷</el-tag>
                <el-tag v-else-if="row.refine && row.refine.applied" size="mini">已执行</el-tag>
                <el-tag v-else type="info" size="mini">跳过</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="决策摘要" min-width="220" show-overflow-tooltip>
              <template slot-scope="{ row }">{{ row.decision_summary }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无匹配建筑记录" :image-size="64" />
        </div>
      </el-col>
    </el-row>

    <div v-if="logTableRows.length" class="full-log-wrap">
      <h5 class="sub-title">推演日志流（可检索）</h5>
      <el-table
        :data="pagedLogRows"
        size="mini"
        border
        stripe
        max-height="280"
        @row-click="onLogRowClick"
      >
        <el-table-column prop="step" label="Step" width="64" align="center" />
        <el-table-column prop="hour" label="Hour" width="64" align="center" />
        <el-table-column label="建筑" width="72" align="center">
          <template slot-scope="{ row }">{{ buildingLabel(row.building) }}</template>
        </el-table-column>
        <el-table-column prop="decision_summary" label="决策摘要" min-width="280" show-overflow-tooltip />
        <el-table-column label="推演剧本" min-width="360" show-overflow-tooltip>
          <template slot-scope="{ row }">
            {{ (row.narrative_lines && row.narrative_lines[0]) || row.decision_summary }}
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="logTableRows.length > pageSize"
        small
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="logTableRows.length"
        :current-page.sync="logPage"
        class="log-pagination"
      />
    </div>
  </div>
</template>

<script>
import {
  buildingLabel,
  getDecisionStep,
  listDecisionSteps,
  resolveNarrativeEntries
} from '@/utils/decisionTrace'

export default {
  name: 'DecisionTraceLog',
  props: {
    decisionTrace: { type: Object, default: null },
    selectedEpisode: { type: Number, default: null },
    selectedBuilding: { type: Number, default: null },
    stepRange: { type: Array, default: () => [0, 0] }
  },
  data() {
    return {
      currentStep: 0,
      searchText: '',
      logPage: 1,
      pageSize: 50
    }
  },
  computed: {
    steps() {
      return listDecisionSteps(this.decisionTrace, this.selectedEpisode)
    },
    stepMin() {
      if (!this.steps.length) return 0
      const [rangeMin] = this.stepRange
      const min = this.steps[0].step
      return rangeMin != null && rangeMin >= min ? rangeMin : min
    },
    stepMax() {
      if (!this.steps.length) return 0
      const [, rangeMax] = this.stepRange
      const max = this.steps[this.steps.length - 1].step
      return rangeMax != null && rangeMax <= max ? rangeMax : max
    },
    currentStepData() {
      return getDecisionStep(this.decisionTrace, this.currentStep, this.selectedEpisode)
    },
    currentHour() {
      return this.currentStepData ? this.currentStepData.hour : '-'
    },
    filteredBuildings() {
      if (!this.currentStepData || !this.currentStepData.buildings) {
        return []
      }
      let list = this.currentStepData.buildings
      if (this.selectedBuilding != null) {
        list = list.filter((b) => b.building === this.selectedBuilding)
      }
      const q = (this.searchText || '').trim().toLowerCase()
      if (!q) {
        return list
      }
      return list.filter((b) => {
        const summary = (b.decision_summary || '').toLowerCase()
        const narrative = (b.narrative_lines || []).join('\n').toLowerCase()
        return summary.includes(q) || narrative.includes(q)
      })
    },
    currentNarratives() {
      if (!this.filteredBuildings.length) {
        return []
      }
      return this.filteredBuildings.map((b) => {
        const entries = resolveNarrativeEntries(b)
        const text = entries.length
          ? entries.map((e) => e.text).join('\n')
          : (b.decision_summary || '暂无详细推演文案（请重新运行仿真以生成新版 trace）')
        return {
          building: b.building,
          entries: entries.length
            ? entries
            : [{ text, source_file: 'checa/agent.py', source_line_start: '-', source_line_end: '-', source_label: '暂无源码映射', code_snippet: '请重新运行仿真以生成带源码引用的 decision_trace.json' }],
          text
        }
      })
    },
    logTableRows() {
      if (!this.decisionTrace || !this.decisionTrace.steps) {
        return []
      }
      const rows = []
      this.decisionTrace.steps.forEach((step) => {
        if (this.selectedEpisode != null && step.episode !== this.selectedEpisode) {
          return
        }
        if (step.step < this.stepMin || step.step > this.stepMax) {
          return
        }
        (step.buildings || []).forEach((b) => {
          if (this.selectedBuilding != null && b.building !== this.selectedBuilding) {
            return
          }
          rows.push({
            step: step.step,
            hour: step.hour,
            building: b.building,
            decision_summary: b.decision_summary,
            narrative_lines: b.narrative_lines || []
          })
        })
      })
      const q = (this.searchText || '').trim().toLowerCase()
      if (!q) {
        return rows
      }
      return rows.filter((r) => {
        const summary = (r.decision_summary || '').toLowerCase()
        const narrative = (r.narrative_lines || []).join('\n').toLowerCase()
        return summary.includes(q) || narrative.includes(q)
      })
    },
    pagedLogRows() {
      const start = (this.logPage - 1) * this.pageSize
      return this.logTableRows.slice(start, start + this.pageSize)
    },
    canPrev() {
      return this.currentStep > this.stepMin
    },
    canNext() {
      return this.currentStep < this.stepMax
    }
  },
  watch: {
    decisionTrace: {
      immediate: true,
      handler() {
        this.resetStep()
      }
    },
    selectedEpisode() {
      this.resetStep()
    },
    stepRange: {
      deep: true,
      handler() {
        if (this.currentStep < this.stepMin) {
          this.currentStep = this.stepMin
        }
        if (this.currentStep > this.stepMax) {
          this.currentStep = this.stepMax
        }
      }
    },
    searchText() {
      this.logPage = 1
    }
  },
  methods: {
    buildingLabel,
    resetStep() {
      this.currentStep = this.stepMin
      this.logPage = 1
    },
    formatStepTooltip(val) {
      return `Step ${val}`
    },
    onStepChange(val) {
      this.currentStep = val
    },
    prevStep() {
      if (this.canPrev) {
        this.currentStep -= 1
      }
    },
    nextStep() {
      if (this.canNext) {
        this.currentStep += 1
      }
    },
    phaseType(phase) {
      if (phase === 6) return 'warning'
      if (phase === 4) return 'primary'
      if (phase === 2) return 'success'
      return ''
    },
    fmtNum(v, d = 2) {
      if (v == null || v === '') return '-'
      const n = Number(v)
      return Number.isFinite(n) ? n.toFixed(d) : String(v)
    },
    fmtAction(actions) {
      if (!actions) return '-'
      const f = (v) => (v == null || v === '' ? '-' : Number(v).toFixed(3))
      return `${f(actions.dhw)} / ${f(actions.ele)} / ${f(actions.tmp)}`
    },
    fmtResidualEle(residual) {
      if (!residual) return '-'
      const base = residual.base || {}
      const delta = residual.delta || {}
      const final = residual.final || {}
      return `${this.fmtNum(base.ele, 2)} + Δ${this.fmtNum(delta.ele, 3)} → ${this.fmtNum(final.ele, 2)}`
    },
    onLogRowClick(row) {
      if (row && row.step != null) {
        this.currentStep = row.step
      }
    }
  }
}
</script>

<style scoped>
.decision-trace-log {
  padding: 4px 0 12px;
}
.log-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.step-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 240px;
}
.step-slider-inline {
  flex: 1;
  min-width: 160px;
}
.step-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}
.search-input {
  width: 200px;
}
.sub-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.phase-panel,
.building-panel {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  min-height: 420px;
}
.phase-name {
  margin: 0 0 4px;
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}
.phase-summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}
.full-log-wrap {
  margin-top: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
}
.log-pagination {
  margin-top: 8px;
  text-align: right;
}
.narrative-panel {
  margin-bottom: 16px;
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 12px 16px;
}
.narrative-panel .sub-title {
  color: #e0e0e0;
  margin-bottom: 6px;
}
.narrative-hint {
  margin: 0 0 10px;
  font-size: 11px;
  color: #888;
}
.narrative-building-label {
  font-size: 12px;
  font-weight: 600;
  color: #9cdcfe;
  margin-bottom: 6px;
}
.narrative-lines {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.65;
}
.narrative-line {
  color: #d4d4d4;
  padding: 1px 4px;
  border-radius: 2px;
  cursor: help;
  word-break: break-word;
}
.narrative-line:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.narrative-block + .narrative-block {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #333;
}
</style>

<style>
.narrative-code-tooltip {
  max-width: 620px !important;
  padding: 0 !important;
  border: 1px solid #444 !important;
  background: #1e1e1e !important;
}
.narrative-code-tooltip .code-tooltip-inner {
  padding: 10px 12px;
}
.narrative-code-tooltip .code-tooltip-header {
  font-size: 11px;
  color: #9cdcfe;
  margin-bottom: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
}
.narrative-code-tooltip .code-tooltip-label {
  font-size: 12px;
  color: #ce9178;
  margin-bottom: 8px;
}
.narrative-code-tooltip .code-tooltip-pre {
  margin: 0;
  padding: 8px 10px;
  background: #252526;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.45;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow: auto;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}
</style>
