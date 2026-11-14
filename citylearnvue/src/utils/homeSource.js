import { get } from '@/api/http'

export async function getHomeSnapshot(params = {}) {
  const response = await get('/web/home/snapshot', { params, silent: true })
  if (!response.ok) throw new Error(response.message || '首页数据源读取失败')
  return response.data || {}
}

export function realtimeDayBounds(day) {
  // Query with community-local wall time. The server resolves it using the selected community zone.
  if (!day) return {}
  const date = new Date(`${day}T00:00:00Z`)
  if (!Number.isFinite(date.getTime())) return {}
  const next = new Date(date.getTime() + 86400000).toISOString().slice(0, 10)
  return { from: `${day}T00:00:00`, to: `${next}T00:00:00` }
}

export function realtimeFreshness(snapshot) {
  const freshness = snapshot && snapshot.freshness
  if (snapshot && snapshot.dataMode === 'history') {
    if (!freshness || freshness.status === 'empty') return '暂无历史测量 · 非实时数据'
    const timeline = snapshot.timestampKind === 'assigned' ? '约定时间轴' : '实测时间轴'
    return `${timeline} · 历史数据（非实时） · 最新测量 ${freshness.latestTimestamp || ''}`
  }
  if (!freshness || freshness.status === 'empty') return '暂无实时测量'
  const labels = { fresh: '实时数据', stale: '数据已过期', future: '测量时间晚于当前时钟' }
  const timestamp = freshness.latestTimestamp || ''
  return `${labels[freshness.status] || '时间状态未知'} · 最新测量 ${timestamp}`
}
