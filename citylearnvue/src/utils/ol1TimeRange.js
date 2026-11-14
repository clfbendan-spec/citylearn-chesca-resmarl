const HOUR = 3600000
const START = Date.UTC(2023, 5, 1)
const HOURS = 2208

// OL1 has month/hour fields without a year; 2023 is a display calendar.
export function ol1TimeAtStep(step) {
  return new Date(START + step * HOUR).toISOString().slice(0, 19).replace('T', ' ')
}

export const freshOl1Range = () => [ol1TimeAtStep(0), ol1TimeAtStep(167)]

export function ol1RangeConfiguration(range) {
  if (!Array.isArray(range) || range.length !== 2) throw new Error('请选择评估数据范围')
  const steps = range.map(value => {
    const parts = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):00:00$/.exec(value)
    if (!parts) throw new Error('评估数据范围的起止时间请选择整点')
    const time = Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]), Number(parts[4]))
    const step = (time - START) / HOUR
    if (step < 0 || step >= HOURS || ol1TimeAtStep(step) !== value) {
      throw new Error('评估数据范围须在 2023-06-01 00:00 至 2023-08-31 23:00 之间')
    }
    return step
  })
  if (steps[1] <= steps[0]) throw new Error('评估数据范围至少包含连续两个小时')
  return { startStep: steps[0], steps: steps[1] - steps[0] + 1 }
}

export function disabledOl1Date(date) {
  const day = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  return day < START || day >= START + HOURS * HOUR
}
