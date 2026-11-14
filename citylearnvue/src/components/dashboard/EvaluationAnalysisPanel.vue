<template>
  <section class="evaluation-analysis" aria-label="评估评分">
    <div class="analysis-row">
      <el-tooltip placement="top" effect="light" popper-class="nocontrol-score-tooltip">
        <div slot="content" class="score-tooltip-content">
          <p>{{ formulaText }}</p>
          <p>{{ penaltyText }}</p>
          <p>{{ scoringRules }}</p>
          <p v-for="row in perBuildingRows" :key="row.building">{{ substitution(row) }}</p>
          <p v-if="scoreAvailable">社区评分 = 各栋得分之和 ÷ {{ perBuildingRows.length }} = {{ scoreLabel }}</p>
          <p v-else>{{ reasonText }}</p>
        </div>
        <button class="score-explanation" type="button" :aria-expanded="expanded" @click="expanded = !expanded">评分 <strong :class="{ unavailable: !scoreAvailable }">{{ scoreLabel }}</strong></button>
      </el-tooltip>
      <span v-if="!isNoControl" class="analysis-muted">{{ comfortLabel }}</span>
    </div>
    <p v-if="!scoreAvailable" class="analysis-muted">{{ reasonText }}</p>
    <div v-if="expanded" class="score-details">
      <p>{{ formulaText }}</p>
      <p>{{ penaltyText }}</p>
      <p>{{ scoringRules }}</p>
      <p>NoControl 基准：{{ score.reference_id || '未找到匹配基准' }}；α=1；任务：{{ taskId || '未知' }}</p>
      <p v-if="protocolSummary">协议：{{ protocolSummary }}</p>
      <div v-if="perBuildingRows.length" class="analysis-table-wrap">
        <table>
          <thead><tr><th>建筑</th><th>费用项</th><th>舒适项</th><th>评分</th></tr></thead>
          <tbody><tr v-for="row in perBuildingRows" :key="row.building"><td>{{ row.building }}</td><td>{{ number(row.cost_term) }}</td><td>{{ number(row.comfort_term) }}</td><td>{{ number(row.score) }}</td></tr></tbody>
        </table>
      </div>
      <p v-if="score.sensitivity && score.sensitivity.length">敏感性：<span v-for="row in score.sensitivity" :key="row.alpha">α={{ row.alpha }}：{{ number(row.score) }}； </span></p>
    </div>
    <el-dialog title="AI 优化分析资料" :visible.sync="adviceVisible" width="760px" append-to-body custom-class="evaluation-advice-dialog">
      <p>当前任务 {{ taskId }}；本地资料已生成，未调用外部 AI。</p>
      <el-input :value="adviceText" type="textarea" :rows="15" readonly aria-label="AI 分析提示词与证据" />
      <span slot="footer">
        <el-button icon="el-icon-document-copy" @click="copyAdvice">复制</el-button>
        <el-button icon="el-icon-download" @click="downloadAdvice('markdown')">下载 Markdown</el-button>
        <el-button icon="el-icon-download" @click="downloadAdvice('json')">下载 JSON</el-button>
      </span>
    </el-dialog>
  </section>
</template>

<script>
const reasons = {
  missing_evaluation_manifest: '该历史记录没有统一评估清单，请重新评估。',
  incomplete_evaluation_evidence: '本次评估产物不完整或回合未完整结束，请检查任务日志并重新评估。',
  artifact_hash_mismatch: '评估产物文件校验失败，不能使用已改变的数据进行评分。',
  missing_anchor: '未登记与本次协议匹配的固定 Anchor，不能用 NoControl 或其他场景代替。',
  missing_independent_nocontrol: '尚无同数据、时间范围、设备及初始状态的完整 NoControl 评估。',
  multiple_matching_nocontrol: '存在多条匹配的 NoControl 记录，尚未确定唯一基准。',
  incomparable_baseline_protocol: '当前记录与 NoControl 的物理评估协议不一致。',
  zero_nocontrol_bill: 'NoControl 费用为零，费用比例无法计算。',
  incomparable_occupied_samples: '当前记录与 NoControl 的有效占用样本数不一致。',
  missing_or_invalid_metric: '费用或舒适指标缺失或无效。',
  unreadable_nocontrol_evidence: '无法读取或核验 NoControl 评估证据。',
  comfort_gate_failed: '至少一栋建筑舒适度未通过门槛，仅保留诊断分。',
  missing_protocol: '评估协议信息缺失。',
  incomparable_protocol: '当前记录与 Anchor 的完整评估协议不一致，不能进入正式排名。',
  missing_occupied_samples: '缺少有效占用样本，不能判断舒适资格。',
  different_or_unknown_policies: '三个场景不是同一个冻结策略，不能汇总。',
  incomplete_online_scenarios: 'Online 场景不完整，不能汇总。'
}
export default {
  name: 'EvaluationAnalysisPanel',
  props: { analysis: { type: Object, default: () => ({}) }, simName: { type: String, default: '' } },
  data: () => ({ expanded: false, adviceVisible: false }),
  computed: {
    isNoControl() {
      const result = this.analysis.result || {}
      const manifest = this.analysis.manifest || {}
      const algorithm = result.algorithm || manifest.algorithm
      return algorithm ? String(algorithm).replace(/[ _-]/g, '').toLowerCase() === 'nocontrol'
        : /^nocontrol(?:\b|_)/i.test(this.simName)
    },
    score() { return this.analysis.status === 'available' ? this.analysis.nocontrolScore || { reason_codes: ['missing_independent_nocontrol'] } : {} },
    scoreAvailable() { return this.score.status === 'available' && typeof this.score.score === 'number' && Number.isFinite(this.score.score) },
    scoreLabel() { return this.scoreAvailable ? this.score.score.toFixed(3) : '不可评分' },
    taskId() { return this.analysis.manifest && this.analysis.manifest.task_id },
    protocolSummary() {
      const protocol = this.analysis.manifest && this.analysis.manifest.protocol
      if (!protocol) return ''
      const full = this.analysis.manifest.protocol_id || '未知'
      const physical = this.analysis.manifest.physical_protocol_id || '未记录'
      const order = protocol.environment_step_order || '未记录'
      const access = protocol.information_access || '未记录'
      return `完整 ${full}；物理 ${physical}；步序 ${order}；信息 ${access}`
    },
    comfortLabel() {
      if (this.score.comfort_qualified === false) return '舒适资格：不合格（诊断分不进入合格榜）'
      if (this.score.comfort_qualified === true) return '舒适资格：通过'
      return '舒适资格：评分证据未齐备'
    },
    reasonText() {
      const codes = this.analysis.status === 'available'
        ? this.score.reason_codes || [] : [this.analysis.reason || 'missing_evaluation_manifest']
      return codes.map(code => reasons[code] || reasons[String(code).split(':')[0]] || String(code)).join('；')
    },
    formulaText() {
      return '分数越高越好，NoControl 自身为 0 分。逐栋 S = 100 × (1 − B/B₀) + α × [P(d₀) − P(d)]，α=1。B 为当前算法实际正费用账单，B₀ 为同条件 NoControl 账单；D 为占用不适比例，d=100D，d=6 表示 6%，d₀ 为 NoControl 不适百分数值。第一项是节费得分，第二项是舒适改善得分。'
    },
    penaltyText() { return 'P(d)：0≤d≤3 时为 d；3<d≤5 时为 3+3(d−3)；5<d≤8 时为 9+5(d−5)；8<d≤100 时为 24+10(d−8)。跨区间逐段累计。' },
    scoringRules() { return '社区分数为各栋分数的等权平均；正分优于 NoControl，负分劣于 NoControl，不是百分制，也不是节费百分比。每栋 D 必须严格小于 10% 才具备舒适资格，超标仍显示诊断分。缺有效占用样本或 B₀=0 时不可评分。' },
    perBuildingRows() {
      return Object.entries(this.score.per_building || {}).map(([building, row]) => ({ building, ...row }))
    },
    canExport() {
      const advice = this.analysis.advice
      return this.analysis.status === 'available' && !!this.taskId && !!advice && !!advice.markdown &&
        !!advice.evidence && advice.evidence.task_id === this.taskId
    },
    adviceText() { return this.canExport ? this.analysis.advice.markdown : '' }
  },
  watch: {
    taskId() { this.adviceVisible = false; this.expanded = false }
  },
  methods: {
    substitution(row) {
      return `${row.building}：B=${this.number(row.positive_bill)}，B₀=${this.number(row.baseline_positive_bill)}；d=${this.number(row.discomfort_proportion * 100)}%，d₀=${this.number(row.baseline_discomfort_proportion * 100)}%。S = 100×(1−B/B₀) + ${this.number(row.baseline_penalty)} − ${this.number(row.penalty)} = ${this.number(row.cost_term)} + (${this.number(row.comfort_term)}) = ${this.number(row.score)}。`
    },
    number(value, digits = 3) { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '未知' },
    async copyAdvice() {
      try {
        await navigator.clipboard.writeText(this.adviceText)
        this.$message.success('分析资料已复制')
      } catch (_) { this.$message.warning('剪贴板不可用，请下载资料') }
    },
    downloadAdvice(format) {
      if (!this.canExport) return
      const json = format === 'json'
      const content = json ? JSON.stringify(this.analysis.advice, null, 2) : this.adviceText
      const url = URL.createObjectURL(new Blob([content], { type: json ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8' }))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `ai-analysis-${String(this.taskId).replace(/[^A-Za-z0-9_-]/g, '_')}.${json ? 'json' : 'md'}`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  }
}
</script>

<style scoped>
.evaluation-analysis { border-top: 1px solid var(--divider-color); margin-top: 16px; padding-top: 12px; font-size: 13px; overflow-wrap: anywhere; }
.analysis-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.score-explanation { border: 0; border-bottom: 1px dotted currentColor; padding: 2px 0; color: var(--primary-text-color); background: transparent; cursor: pointer; font: inherit; }
.score-explanation:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
.analysis-muted, .unavailable { color: var(--secondary-text-color); }
.analysis-muted { line-height: 1.7; margin: 8px 0 0; }
.score-details { line-height: 1.7; margin-top: 12px; }
.analysis-table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--divider-color); text-align: left; }
</style>
<style>
.nocontrol-score-tooltip { max-width: min(700px, calc(100vw - 32px)); }
.score-tooltip-content { line-height: 1.7; overflow-wrap: anywhere; }
.score-tooltip-content p { margin: 5px 0; }
.evaluation-advice-dialog { max-width: calc(100% - 24px); }
.evaluation-advice-dialog .el-dialog__footer { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.evaluation-advice-dialog .el-textarea__inner { font-family: var(--ha-font-family-mono); }
</style>
