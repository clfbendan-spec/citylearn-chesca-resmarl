import Papa from 'papaparse'
import { getLatestCommunityChescaHomeData } from '@/api/dashboard'

let cached = null
let pending = null
let cachedAt = 0
const CACHE_TTL_MS = 5 * 60 * 1000

function number(value) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export async function loadCommunityHomeTrace(force = false) {
  if (!force && cached && cached.rows.length && Date.now() - cachedAt < CACHE_TTL_MS) return cached
  if (!force && pending) return pending
  pending = (async () => {
    const response = await getLatestCommunityChescaHomeData({ silent: true })
    if (!response.ok || !response.data) {
      return { rows: [], groupName: null, taskId: null }
    }
    const detail = response.data
    const parsed = Papa.parse(String(detail.chescaTraceCsv || ''), {
      header: true,
      skipEmptyLines: true
    })
    const rows = (parsed.data || []).map(row => ({
      episode: number(row.episode) ?? 1,
      step: number(row.step),
      hour: number(row.hour),
      building: number(row.building),
      actual_outdoor_temp: number(row.actual_outdoor_temp),
      actual_solar: number(row.actual_solar),
      actual_load: number(row.actual_load),
      actual_dhw: number(row.actual_dhw),
      action_dhw_final: number(row.action_dhw_final),
      action_ele_final: number(row.action_ele_final),
      action_tmp_final: number(row.action_tmp_final)
    })).filter(row => row.step != null && row.building != null)
    cached = { rows, groupName: detail.groupName || null, taskId: detail.taskId || null }
    cachedAt = Date.now()
    return cached
  })().finally(() => { pending = null })
  return pending
}
