import axios from 'axios'
import Papa from 'papaparse'
import { hourIndexIn2026, timestampAtHourIndex } from '@/utils/dataset2026Clock'

/** 首页控制动作固定使用的仿真 taskId */
export const HOME_ACTION_TASK_ID = '2c81b4f639aa45d9b253f06383f91d55'

let cachedPayload = null
let loadingPromise = null

function toNumber(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function parseTraceRows(csvText) {
  if (!csvText || !String(csvText).trim()) return []
  const parsed = Papa.parse(String(csvText).trim(), {
    header: true,
    skipEmptyLines: true
  })
  return (parsed.data || []).map((raw) => ({
    episode: toNumber(raw.episode) ?? 1,
    step: toNumber(raw.step),
    hour: toNumber(raw.hour),
    building: toNumber(raw.building),
    action_dhw_final: toNumber(raw.action_dhw_final),
    action_ele_final: toNumber(raw.action_ele_final),
    action_tmp_final: toNumber(raw.action_tmp_final)
  })).filter((r) => r.step != null && r.building != null)
}

/**
 * 加载固定 taskId 对应仿真的 chesca_trace（首页动作卡片专用）。
 */
export async function loadLatestActionTrace(force = false) {
  if (!force && cachedPayload) return cachedPayload
  if (!force && loadingPromise) return loadingPromise

  loadingPromise = (async () => {
    const detailRes = await axios.get('/api/web/basedata/getDashboardSimulationDetail', {
      params: { taskId: HOME_ACTION_TASK_ID }
    })
    if (!detailRes.data || detailRes.data.code !== 0) {
      cachedPayload = {
        rows: [],
        taskId: HOME_ACTION_TASK_ID,
        groupName: null,
        message:
          (detailRes.data && detailRes.data.message) ||
          `无法加载固定任务 ${HOME_ACTION_TASK_ID}`
      }
      return cachedPayload
    }

    const detail = detailRes.data.data || {}
    const rows = parseTraceRows(detail.chescaTraceCsv)
    if (!rows.length) {
      cachedPayload = {
        rows: [],
        taskId: detail.taskId || HOME_ACTION_TASK_ID,
        groupName: detail.groupName || null,
        message: `任务 ${HOME_ACTION_TASK_ID} 无 chesca_trace.csv`
      }
      return cachedPayload
    }

    cachedPayload = {
      rows,
      taskId: detail.taskId || HOME_ACTION_TASK_ID,
      groupName: detail.groupName || null,
      message: null
    }
    return cachedPayload
  })().finally(() => {
    loadingPromise = null
  })

  return loadingPromise
}

function resolveTargetStep(buildingRows, now) {
  const target = hourIndexIn2026(now)
  const steps = buildingRows
    .map((r) => r.step)
    .filter((s) => s != null)
  if (!steps.length) return { step: null, mode: 'empty' }
  const maxStep = Math.max(...steps)
  if (target <= maxStep) {
    return { step: target, mode: 'calendar' }
  }
  // 短 episode：按小时环映射到仿真步
  return { step: target % (maxStep + 1), mode: 'modulo' }
}

/**
 * @param {'day'|'24h'} range
 */
export async function getActionSnapshot(
  now = new Date(),
  range = 'day',
  buildingIndex = 0
) {
  const payload = await loadLatestActionTrace()
  const bIdx = Math.max(0, Math.min(2, Number(buildingIndex) || 0))
  const buildingRows = (payload.rows || [])
    .filter((r) => r.building === bIdx)
    .sort((a, b) => a.step - b.step)

  if (!buildingRows.length) {
    return {
      current: null,
      history: [],
      currentStep: null,
      buildingIndex: bIdx,
      taskId: payload.taskId,
      groupName: payload.groupName,
      message: payload.message || '当前建筑无动作 trace',
      mapMode: 'empty'
    }
  }

  const { step: targetStep, mode } = resolveTargetStep(buildingRows, now)
  const byStep = new Map(buildingRows.map((r) => [r.step, r]))
  const currentRow = byStep.get(targetStep) || null

  let startStep = 0
  if (range === '24h') {
    startStep = Math.max(0, targetStep - 23)
  } else if (range === 'day') {
    startStep = targetStep - (targetStep % 24)
  }

  const history = []
  for (let s = startStep; s <= targetStep; s += 1) {
    const row = byStep.get(s)
    if (!row) continue
    history.push({
      index: s,
      step: s,
      time: timestampAtHourIndex(s).toDate(),
      action_dhw_final: row.action_dhw_final,
      action_ele_final: row.action_ele_final,
      action_tmp_final: row.action_tmp_final
    })
  }

  const current = currentRow
    ? {
        index: currentRow.step,
        step: currentRow.step,
        time: timestampAtHourIndex(currentRow.step).toDate(),
        hour: currentRow.hour,
        action_dhw_final: currentRow.action_dhw_final,
        action_ele_final: currentRow.action_ele_final,
        action_tmp_final: currentRow.action_tmp_final
      }
    : null

  return {
    current,
    history,
    currentStep: targetStep,
    buildingIndex: bIdx,
    taskId: payload.taskId,
    groupName: payload.groupName,
    message: current
      ? null
      : `trace 中无 step=${targetStep}（映射模式 ${mode}）`,
    mapMode: mode
  }
}
