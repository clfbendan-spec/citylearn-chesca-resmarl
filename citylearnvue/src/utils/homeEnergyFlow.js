import axios from 'axios'
import { HOME_ACTION_TASK_ID } from '@/utils/homeActions'
import {
  DATASET_YEAR,
  hourIndexIn2026,
  timestampAtHourIndex
} from '@/utils/dataset2026Clock'

let progressiveGen = 0

function untilTsFromNow(now = new Date()) {
  return timestampAtHourIndex(hourIndexIn2026(now)).format('YYYY-MM-DD HH:mm:ss')
}

function emptyPayload(extra = {}) {
  return {
    flows: {},
    days: [],
    buildings: [],
    untilTs: null,
    taskId: HOME_ACTION_TASK_ID,
    groupName: null,
    message: null,
    partial: false,
    ...extra
  }
}

async function fetchHomeEnergyFlow(mode, untilTs) {
  const res = await axios.get('/api/web/basedata/getHomeEnergyFlow', {
    params: {
      taskId: HOME_ACTION_TASK_ID,
      untilTs,
      datasetYear: DATASET_YEAR,
      mode
    }
  })
  if (!res.data || res.data.code !== 0) {
    throw new Error((res.data && res.data.message) || `加载能源分配失败（${mode}）`)
  }
  return res.data.data || {}
}

function toPayload(data, partial) {
  const flows = data.flows || {}
  const days = data.days || Object.keys(flows).sort()
  return {
    flows,
    days,
    buildings: data.buildings || [],
    untilTs: data.untilTs || null,
    taskId: data.taskId || HOME_ACTION_TASK_ID,
    groupName: data.groupName || null,
    message: days.length ? null : '截止当前时刻暂无能源分配数据',
    partial
  }
}

function mergeHistory(todayPayload, historyData) {
  const flows = { ...(historyData.flows || {}) }
  // 当日以后端 today 为准（含截止当前小时）
  Object.assign(flows, todayPayload.flows || {})
  const daySet = new Set([
    ...(historyData.days || []),
    ...(todayPayload.days || [])
  ])
  const days = [...daySet].sort()
  return {
    flows,
    days,
    buildings: todayPayload.buildings.length
      ? todayPayload.buildings
      : historyData.buildings || [],
    untilTs: todayPayload.untilTs || historyData.untilTs,
    taskId: todayPayload.taskId,
    groupName: todayPayload.groupName || historyData.groupName,
    message: days.length ? null : '截止当前时刻暂无能源分配数据',
    partial: false
  }
}

/**
 * 渐进加载：先当日预聚合（小响应），再历史预聚合。
 */
export async function loadHomeEnergyProgressive(
  now = new Date(),
  handlers = {}
) {
  const gen = ++progressiveGen
  const { onToday, onComplete } = handlers
  const untilTs = untilTsFromNow(now)

  try {
    const todayData = await fetchHomeEnergyFlow('today', untilTs)
    if (gen !== progressiveGen) return null
    const todayPayload = toPayload(todayData, true)
    onToday && onToday(todayPayload)

    const historyData = await fetchHomeEnergyFlow('history', untilTs)
    if (gen !== progressiveGen) return todayPayload
    const completePayload = mergeHistory(todayPayload, historyData)
    onComplete && onComplete(completePayload)
    return completePayload
  } catch (e) {
    if (gen !== progressiveGen) return null
    const fail = emptyPayload({
      untilTs,
      message: e.message || '能源分配加载失败'
    })
    onToday && onToday(fail)
    onComplete && onComplete(fail)
    return fail
  }
}

export async function getHomeEnergyFolderData(now = new Date()) {
  return loadHomeEnergyProgressive(now, {})
}

/**
 * 指定日 / 范围的逐小时家庭耗电（家庭图标 more-info）。
 * @param {{ day: string, scope?: string, untilTs?: string, now?: Date }} opts
 */
export async function fetchHomeEnergyHourly(opts = {}) {
  const now = opts.now || new Date()
  const untilTs = opts.untilTs || untilTsFromNow(now)
  const day = opts.day
  if (!day) throw new Error('day 不能为空')
  const scope = opts.scope || 'community'
  const res = await axios.get('/api/web/basedata/getHomeEnergyHourly', {
    params: {
      taskId: HOME_ACTION_TASK_ID,
      day,
      scope,
      untilTs,
      datasetYear: DATASET_YEAR
    }
  })
  if (!res.data || res.data.code !== 0) {
    throw new Error((res.data && res.data.message) || '加载当日耗电失败')
  }
  return res.data.data || { points: [], totalHome: 0, day, scope }
}

