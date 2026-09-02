/**
 * 将 α 扫描 summary 转为看板曲线序列。
 */

export function pickBaselineKpi(detail, kpiName) {
  const baseline = detail && detail.baseline
  if (!baseline || !baseline.district_kpis) return null
  const v = baseline.district_kpis[kpiName]
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * @returns {{ alphas: number[], series: { name: string, kpi: string, data: (number|null)[], baseline: number|null }[] }}
 */
export function buildAlphaKpiSeries(detail, kpiNames) {
  const points = ((detail && detail.points) || []).filter(
    (p) => p && p.kind !== 'baseline' && p.name !== 'chesca_baseline'
  )
  const sorted = [...points].sort(
    (a, b) => Number(a.residual_alpha) - Number(b.residual_alpha)
  )
  const alphas = sorted.map((p) => Number(p.residual_alpha))
  const names = kpiNames && kpiNames.length ? kpiNames : detail.default_chart_kpis || []

  const series = names.map((kpi) => ({
    name: kpi,
    kpi,
    baseline: pickBaselineKpi(detail, kpi),
    data: sorted.map((p) => {
      const v = p.district_kpis && p.district_kpis[kpi]
      const n = Number(v)
      return Number.isFinite(n) ? n : null
    })
  }))

  return { alphas, series, sortedPoints: sorted }
}

export function buildAlphaTableRows(detail, kpiNames) {
  const points = (detail && detail.points) || []
  const names = kpiNames && kpiNames.length ? kpiNames : detail.default_chart_kpis || []
  return [...points]
    .sort((a, b) => {
      const ka = a.kind === 'baseline' || a.name === 'chesca_baseline' ? -1 : 0
      const kb = b.kind === 'baseline' || b.name === 'chesca_baseline' ? -1 : 0
      if (ka !== kb) return ka - kb
      return Number(a.residual_alpha) - Number(b.residual_alpha)
    })
    .map((p) => {
      const row = {
        name: p.name,
        label: p.label,
        kind: p.kind || (p.name === 'chesca_baseline' ? 'baseline' : 'resmarl'),
        residual_alpha: p.residual_alpha,
        resmarl_enabled: !!p.resmarl_enabled,
        elapsed_sec: p.elapsed_sec
      }
      names.forEach((k) => {
        const v = p.district_kpis && p.district_kpis[k]
        const n = Number(v)
        row[k] = Number.isFinite(n) ? n : null
      })
      return row
    })
}

export function formatKpi(value, digits = 4) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return Number(value).toFixed(digits)
}
