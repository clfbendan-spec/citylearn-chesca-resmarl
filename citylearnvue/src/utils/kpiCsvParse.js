/**
 * 解析 exported_kpis.csv，保证每行具备完整列（不依赖 Papa，避免浏览器解析差异）。
 */
export function parseKpiCsvText(text) {
  if (!text || !String(text).trim()) {
    return []
  }
  const clean = String(text).trim().replace(/^\ufeff/, '')
  const lines = clean.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length < 2) {
    return []
  }

  const headers = lines[0].split(',').map((h) => h.trim().replace(/^\ufeff/, ''))
  if (!headers.length) {
    return []
  }
  const kpiKey = headers[0] || 'KPI'
  const rows = []

  for (let i = 1; i < lines.length; i++) {
    const fields = lines[i].split(',')
    const kpiName = (fields[0] || '').trim()
    if (!kpiName) {
      continue
    }
    const row = { [kpiKey]: kpiName }
    for (let col = 1; col < headers.length; col++) {
      const raw = fields[col]
      row[headers[col]] = raw === undefined || raw === null ? '' : String(raw).trim()
    }
    rows.push(row)
  }
  return rows
}

/**
 * 将接口返回的 kpiRows 规范为数组（兼容单条对象、类数组对象等）。
 */
export function normalizeKpiRows(raw) {
  if (!raw) {
    return []
  }
  if (Array.isArray(raw)) {
    return raw.filter((row) => row && typeof row === 'object')
  }
  if (typeof raw === 'object') {
    if (raw.KPI != null || raw.cost_function != null) {
      return [raw]
    }
    if (typeof raw.length === 'number' && raw.length > 0) {
      const arr = []
      for (let i = 0; i < raw.length; i++) {
        if (raw[i] && typeof raw[i] === 'object') {
          arr.push(raw[i])
        }
      }
      if (arr.length) {
        return arr
      }
    }
    const vals = Object.values(raw).filter(
      (v) => v && typeof v === 'object' && (v.KPI != null || v.cost_function != null)
    )
    if (vals.length) {
      return vals
    }
  }
  return []
}

/** 合并多行对象的全部列名，KPI 列在前，Building_* 居中，District 最后 */
export function collectKpiTableColumns(rows) {
  const keySet = new Set()
  rows.forEach((row) => {
    Object.keys(row).forEach((k) => keySet.add(k))
  })
  const cols = [...keySet]
  const order = (c) => {
    if (c === 'KPI' || c === 'cost_function') return 0
    const bm = /^Building_(\d+)$/.exec(c)
    if (bm) return parseInt(bm[1], 10)
    if (c === 'District') return 100
    return 50
  }
  return cols.sort((a, b) => order(a) - order(b))
}

export function formatKpiCellValue(val) {
  if (val === null || val === undefined || val === '') {
    return '—'
  }
  return val
}
