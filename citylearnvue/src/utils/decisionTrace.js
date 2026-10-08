/**
 * Decision Trace（决策推演日志）解析与聚合。
 */

import { buildingLabel, filterTraceRows, listTraceEpisodes, parseChescaTraceCsv } from './chescaTraceParse'
import { buildNarrativeEntriesFromLines, buildCodeRefForLine, classifyNarrativeLine } from './decisionTraceCodeRefs'

export const DECISION_PHASES = [
  { id: 1, name: '时序预测', icon: 'el-icon-data-analysis' },
  { id: 2, name: '初稿动作', icon: 'el-icon-edit-outline' },
  { id: 3, name: '未来用电估计', icon: 'el-icon-s-marketing' },
  { id: 4, name: '电池 Refine', icon: 'el-icon-s-operation' },
  { id: 5, name: '净负荷更新', icon: 'el-icon-refresh' }
]

/**
 * @param {string} jsonText
 * @returns {{ version: number, n_buildings: number, steps: object[] } | null}
 */
export function parseDecisionTraceJson(jsonText) {
  if (!jsonText || !String(jsonText).trim()) {
    return null
  }
  try {
    const data = JSON.parse(jsonText)
    if (!data || !Array.isArray(data.steps)) {
      return null
    }
    return data
  } catch (e) {
    console.warn('decision_trace.json 解析失败', e)
    return null
  }
}

/**
 * 无 JSON 时从 CSV 行重建按步结构（兼容旧任务）。
 */
export function buildDecisionStepsFromCsvRows(rows) {
  if (!rows || !rows.length) {
    return []
  }
  const grouped = new Map()
  rows.forEach((row) => {
    const key = `${row.episode}-${row.step}`
    if (!grouped.has(key)) {
      grouped.set(key, [])
    }
    grouped.get(key).push(row)
  })

  const steps = []
  ;[...grouped.entries()]
    .sort((a, b) => {
      const [ea, sa] = a[0].split('-').map(Number)
      const [eb, sb] = b[0].split('-').map(Number)
      return ea - eb || sa - sb
    })
    .forEach(([, stepRows]) => {
      const sorted = [...stepRows].sort((a, b) => a.building - b.building)
      const sample = sorted[0]
      const globalRefine = sample.refine_skip_reason !== 'first_step'
      steps.push({
        episode: sample.episode,
        step: sample.step,
        hour: sample.hour,
        refine_applied: globalRefine,
        refine_skip_reason: sample.refine_skip_reason,
        tau: sample.tau,
        balance_type: sample.balance_type,
        B_low: sample.B_low,
        B_high: sample.B_high,
        phases: buildPhasesFromCsvStep(sorted, globalRefine),
        buildings: sorted.map((r) => csvRowToBuildingEntry(r))
      })
    })
  return steps
}

function csvRowToBuildingEntry(r) {
  const narrativeLines = r.decision_narrative
    ? String(r.decision_narrative).split('|||').filter(Boolean)
    : []
  return {
    building: r.building,
    control_mode: r.control_mode || (r.outage_flag ? 'outage' : 'normal'),
    outage_flag: r.outage_flag,
    decision_summary: r.decision_summary || '',
    narrative_lines: narrativeLines,
    battery_soc: r.battery_soc,
    dhw_soc: r.dhw_soc,
    actions: {
      init: { dhw: r.action_dhw_init, ele: r.action_ele_init, tmp: r.action_tmp_init },
      final: { dhw: r.action_dhw_final, ele: r.action_ele_final, tmp: r.action_tmp_final }
    },
    forecast: {
      load_next: r.forecast_load_next,
      solar_next: r.forecast_solar_next,
      dhw_next: r.forecast_dhw_next
    },
    refine: {
      applied: r.refine_applied,
      skip_reason: r.refine_skip_reason,
      trigger_reduce: r.trigger_reduce_load,
      trigger_increase: r.trigger_increase_load,
      net_load_next: r.net_load_next,
      net_load_mean: r.net_load_mean,
      net_load_std: r.net_load_std,
      battery_search_cost: r.battery_search_cost
    },
    residual: {
      enabled: !!r.resmarl_enabled,
      alpha: r.residual_alpha,
      applied: !!r.residual_applied,
      skip_reason: r.residual_skip_reason,
      base: {
        dhw: r.residual_base_dhw,
        ele: r.residual_base_ele,
        tmp: r.residual_base_tmp
      },
      delta: {
        dhw: r.residual_delta_dhw,
        ele: r.residual_delta_ele,
        tmp: r.residual_delta_tmp
      },
      raw_delta: {
        dhw: r.residual_raw_delta_dhw,
        ele: r.residual_raw_delta_ele,
        tmp: r.residual_raw_delta_tmp
      },
      final: {
        dhw: r.residual_final_dhw,
        ele: r.residual_final_ele,
        tmp: r.residual_final_tmp
      }
    }
  }
}

function fmtNum(v, d = 3) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(d) : String(v)
}

function buildPhasesFromCsvStep(stepRows, globalRefine) {
  const sample = stepRows[0]
  const phases = [
    {
      phase: 1,
      name: '时序预测',
      summary: `室外 ${fmtNum(sample.actual_outdoor_temp, 1)}°C → 下步预测 ${fmtNum(sample.forecast_outdoor_next, 1)}°C`
    },
    {
      phase: 2,
      name: '初稿动作',
      summary: stepRows
        .map(
          (r) =>
            `${buildingLabel(r.building)}[${r.control_mode || 'normal'}] ` +
            `DHW ${fmtNum(r.action_dhw_init, 2)} ELE ${fmtNum(r.action_ele_init, 2)} TMP ${fmtNum(r.action_tmp_init, 2)}`
        )
        .join('；')
    },
    {
      phase: 3,
      name: '未来用电估计',
      summary: `滚动预测 tau=${sample.tau ?? 1} 步设备用电`
    },
    {
      phase: 4,
      name: '电池 Refine',
      summary: globalRefine
        ? stepRows
            .map((r) => {
              if (r.outage_flag) return `${buildingLabel(r.building)} 停电跳过`
              const flags = []
              if (r.trigger_reduce_load) flags.push('B_high')
              if (r.trigger_increase_load) flags.push('B_low')
              return `${buildingLabel(r.building)} ELE ${fmtNum(r.action_ele_init, 2)}→${fmtNum(r.action_ele_final, 2)}${flags.length ? ` (${flags.join('+')})` : ''}`
            })
            .join('；')
        : '首步无历史，跳过 Refine'
    },
    {
      phase: 5,
      name: '净负荷更新',
      summary: '更新净用电预测历史'
    }
  ]
  if (sample.resmarl_enabled) {
    phases.push({
      phase: 6,
      name: 'ResMARL 残差',
      summary: stepRows
        .map((r) => {
          if (r.residual_applied) {
            return `${buildingLabel(r.building)} ELE ${fmtNum(r.residual_base_ele, 2)}+Δ${fmtNum(r.residual_delta_ele, 3)}→${fmtNum(r.residual_final_ele, 2)}`
          }
          return `${buildingLabel(r.building)} 跳过`
        })
        .join('；')
    })
  }
  return phases
}

function fmtActionNum(v, d = 3) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(d) : String(v)
}

function actionTripletText(dhw, ele, tmp) {
  return `DHW: ${fmtActionNum(dhw)}  ELE: ${fmtActionNum(ele)}  TMP: ${fmtActionNum(tmp)}`
}

/**
 * 若剧本缺少三行动作对照，用 residual / actions 字段补全（兼容旧 trace）。
 */
export function ensureActionCompareLines(building) {
  if (!building) return building
  const lines = Array.isArray(building.narrative_lines) ? [...building.narrative_lines] : []
  // Multi-agent 剧本已有 [观测动作]/[奖励计算]，勿注入 CHESCA 三行动作对照
  const isMultiAgent = lines.some(
    (ln) => String(ln).includes('[观测动作]') || String(ln).includes('[奖励计算]')
  )
  if (isMultiAgent) {
    return building
  }
  const hasChesca = lines.some((ln) => String(ln).includes('[CHESCA动作]'))
  const hasMarl = lines.some((ln) => String(ln).includes('[MARL动作]'))
  const hasFinal = lines.some((ln) => String(ln).includes('[CHESCA-RESMARL动作]'))

  const residual = building.residual || {}
  const actions = building.actions || {}
  const finalAct = actions.final || {}
  const base = residual.base || {}
  const delta = residual.delta || {}
  const rawDelta = residual.raw_delta || residual.rawDelta || {}
  const resFinal = residual.final || {}
  const enabled = !!residual.enabled

  const pickMarl = (axis) => {
    if (!enabled) return 0
    if (rawDelta[axis] != null && rawDelta[axis] !== '') return rawDelta[axis]
    if (delta[axis] != null && delta[axis] !== '') return delta[axis]
    return 0
  }

  // 已有三行：若有 raw_delta，把 [MARL动作] 换成原始 Δa
  if (hasChesca && hasMarl && hasFinal) {
    if (enabled && (rawDelta.dhw != null || rawDelta.ele != null || rawDelta.tmp != null)) {
      const marlLine = `> [MARL动作] ${actionTripletText(pickMarl('dhw'), pickMarl('ele'), pickMarl('tmp'))}`
      for (let i = 0; i < lines.length; i += 1) {
        if (String(lines[i]).includes('[MARL动作]')) {
          lines[i] = marlLine
          break
        }
      }
    }
    return { ...building, narrative_lines: lines }
  }

  const chescaDhw = base.dhw != null ? base.dhw : finalAct.dhw
  const chescaEle = base.ele != null ? base.ele : finalAct.ele
  const chescaTmp = base.tmp != null ? base.tmp : finalAct.tmp
  const marlDhw = pickMarl('dhw')
  const marlEle = pickMarl('ele')
  const marlTmp = pickMarl('tmp')
  const outDhw = resFinal.dhw != null ? resFinal.dhw : finalAct.dhw
  const outEle = resFinal.ele != null ? resFinal.ele : finalAct.ele
  const outTmp = resFinal.tmp != null ? resFinal.tmp : finalAct.tmp

  const insert = []
  if (!hasChesca) insert.push(`> [CHESCA动作] ${actionTripletText(chescaDhw, chescaEle, chescaTmp)}`)
  if (!hasMarl) insert.push(`> [MARL动作] ${actionTripletText(marlDhw, marlEle, marlTmp)}`)
  if (!hasFinal) insert.push(`> [CHESCA-RESMARL动作] ${actionTripletText(outDhw, outEle, outTmp)}`)

  // 插在「最终执行」之前；若无则追加在末尾
  const idx = lines.findIndex((ln) => String(ln).includes('最终执行'))
  if (idx >= 0) {
    lines.splice(idx, 0, ...insert)
  } else {
    lines.push(...insert)
  }
  return { ...building, narrative_lines: lines }
}

export function resolveNarrativeEntries(building, traceData = null) {
  if (!building) return []
  const enriched = ensureActionCompareLines(building)
  const lines = enriched.narrative_lines || []
  const refOpts = {
    reward_kwargs: (traceData && traceData.reward_kwargs) || null,
    agent: (traceData && traceData.agent) || null
  }
  if (lines.length) {
    return buildNarrativeEntriesFromLines(lines, refOpts)
  }
  const entries = building.narrative_entries || []
  if (!entries.length) return []
  return entries.map((e) => {
    const text = e && e.text != null ? String(e.text) : ''
    // 若 JSON 已嵌入完整 snippet，优先使用
    if (e && e.code_snippet) {
      return {
        text,
        code_tag: e.code_tag || classifyNarrativeLine(text),
        source_file: e.source_file || 'Multi-agent.py',
        source_line_start: e.source_line_start != null ? e.source_line_start : '—',
        source_line_end: e.source_line_end != null ? e.source_line_end : '—',
        source_label: e.source_label || '',
        code_snippet: e.code_snippet
      }
    }
    return { text, ...buildCodeRefForLine(text, refOpts) }
  })
}

export function resolveDecisionTrace({ decisionTraceJson, chescaTraceCsv }) {
  const fromJson = parseDecisionTraceJson(decisionTraceJson)
  if (fromJson && fromJson.steps.length) {
    fromJson.steps = fromJson.steps.map((step) => ({
      ...step,
      buildings: (step.buildings || []).map((b) => ensureActionCompareLines(b))
    }))
    return fromJson
  }
  const rows = parseChescaTraceCsv(chescaTraceCsv)
  if (!rows.length) {
    return null
  }
  return {
    version: 1,
    n_buildings: [...new Set(rows.map((r) => r.building))].length,
    steps: buildDecisionStepsFromCsvRows(rows).map((step) => ({
      ...step,
      buildings: (step.buildings || []).map((b) => ensureActionCompareLines(b))
    }))
  }
}

export function listDecisionSteps(traceData, episode = null) {
  if (!traceData || !traceData.steps) {
    return []
  }
  let steps = traceData.steps
  if (episode != null) {
    steps = steps.filter((s) => s.episode === episode)
  }
  return [...steps].sort((a, b) => a.step - b.step)
}

export function getDecisionStep(traceData, step, episode = null) {
  const steps = listDecisionSteps(traceData, episode)
  return steps.find((s) => s.step === step) || null
}

export function filterTraceRowsForLog(rows, { episode, building, stepRange } = {}) {
  let out = filterTraceRows(rows, { episode, building })
  if (stepRange && stepRange.length === 2) {
    const [min, max] = stepRange
    out = out.filter((r) => r.step >= min && r.step <= max)
  }
  return [...out].sort((a, b) => a.step - b.step || a.building - b.building)
}

export { listTraceEpisodes, buildingLabel }
