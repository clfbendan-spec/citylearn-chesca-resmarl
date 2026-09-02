export function floorToMidnight(ts) {
  const d = new Date(ts)
  if (d.getHours() !== 0 || d.getMinutes() !== 0 || d.getSeconds() !== 0) {
    d.setHours(0, 0, 0, 0)
  }
  return d.getTime()
}

export function ceilToEndOfDay(ts) {
  const d = new Date(ts)
  if (d.getHours() !== 23 || d.getMinutes() !== 59 || d.getSeconds() !== 59) {
    d.setHours(23, 59, 59, 999)
  }
  return d.getTime()
}

export function prepareTimeSeries(data) {
  return (data || []).map((item) => ({
    ...item,
    'Time Step': item.timestamp,
    timestamp: new Date(item.timestamp).getTime()
  }))
}

export function defaultSliderRange(rows, baseIntervalMinutes) {
  if (!rows.length) return [0, 0]
  const min = floorToMidnight(rows[0].timestamp)
  const max = ceilToEndOfDay(rows[rows.length - 1].timestamp)
  const ppd = Math.max(1, Math.floor((24 * 60) / Math.max(1, baseIntervalMinutes)))
  const endIdx = Math.min(rows.length - 1, ppd * 10)
  return [min, ceilToEndOfDay(rows[endIdx]?.timestamp || max)]
}

export function baseIntervalMinutes(rows) {
  if (rows.length < 2) return 1
  return Math.round((rows[1].timestamp - rows[0].timestamp) / 60000)
}
