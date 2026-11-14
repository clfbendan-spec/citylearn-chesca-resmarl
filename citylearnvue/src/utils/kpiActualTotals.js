function numberOrNull(value) {
  if (value == null || String(value).trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

/** Reconstruct load metrics from aligned building series before aggregating peaks. */
export function actualKpiLoadMetric(files, column, key) {
  const entries = Object.entries(files || {}).filter(([name]) => /^building_\d+_ep0$/i.test(name))
  const selected = String(column).toLowerCase() === 'district'
    ? entries : entries.filter(([name]) => name.toLowerCase() === `${String(column).toLowerCase()}_ep0`)
  if (!selected.length) return null
  const count = selected[0][1].length
  if (!count || selected.some(([, rows]) => rows.length !== count)) return null
  const reference = selected[0][1]
  const totals = new Array(count).fill(0)
  for (const [, rows] of selected) {
    for (let i = 0; i < count; i++) {
      if (rows[i].timestamp !== reference[i].timestamp) return null
      const energy = numberOrNull(rows[i].net_electricity_consumption ?? rows[i]['Net Electricity Consumption-kWh'])
      if (energy === null) return null
      totals[i] += energy
    }
  }
  if (key === 'zero_net_energy') return totals.reduce((sum, value) => sum + value, 0)
  if (key === 'ramping_average') {
    return count < 2 ? null : totals.slice(1).reduce((sum, value, i) => sum + Math.max(value - totals[i], 0), 0)
  }
  if (count < 2) return null
  const hours = (Date.parse(reference[1].timestamp) - Date.parse(reference[0].timestamp)) / 3600000
  if (!(hours > 0)) return null
  for (let i = 1; i < count; i++) {
    if ((Date.parse(reference[i].timestamp) - Date.parse(reference[i - 1].timestamp)) / 3600000 !== hours) return null
  }
  if (key === 'all_time_peak_average') return totals.reduce((peak, value) => Math.max(peak, value / hours), -Infinity)
  const window = key === 'monthly_one_minus_load_factor_average' ? 730 : 24
  const values = []
  for (let offset = 0; offset < count; offset += window) {
    const group = totals.slice(offset, offset + window)
    const peak = Math.max(...group)
    if (key === 'daily_peak_average') values.push(peak / hours)
    else if (peak !== 0) values.push(1 - group.reduce((sum, value) => sum + value, 0) / group.length / peak)
  }
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

/** Clip each building's export credit before summing, as CityLearn does. */
export function actualKpiTotal(files, result, column, key) {
  const perBuilding = result && result.per_building
  const district = String(column).toLowerCase() === 'district'
  const entries = Object.entries(files || {}).filter(([name]) => /^building_\d+_ep0$/i.test(name))
  const selected = district ? entries : entries.filter(
    ([name]) => name.toLowerCase() === `${String(column).toLowerCase()}_ep0`
  )
  const expected = result && result.protocol && result.protocol.building_ids
  const buildings = district
    ? (expected || (perBuilding && Object.keys(perBuilding)) || selected.map(([name]) => name.replace(/_ep0$/i, '')))
    : [column]
  if (!buildings.length) return null
  // Native bills cover all evaluation states; prefer them to exported transition rows.
  if (key === 'cost_total' && perBuilding) {
    const bills = buildings.map(name => {
      const match = Object.keys(perBuilding).find(k => k.toLowerCase() === String(name).toLowerCase())
      return numberOrNull(match && perBuilding[match].native_positive_bill)
    })
    if (bills.every(value => value !== null)) return bills.reduce((a, b) => a + b, 0)
  }
  if (!selected.length || (district && selected.length !== buildings.length)) return null
  let total = 0
  for (const [, rows] of selected) {
    if (!rows.length) return null
    for (const row of rows) {
      const energy = numberOrNull(row.net_electricity_consumption ?? row['Net Electricity Consumption-kWh'])
      const factor = key === 'electricity_consumption_total' ? 1
        : numberOrNull(row[key === 'cost_total' ? 'electricity_pricing' : 'carbon_intensity'])
      if (energy === null || factor === null) return null
      total += Math.max(energy * factor, 0)
    }
  }
  return total
}
