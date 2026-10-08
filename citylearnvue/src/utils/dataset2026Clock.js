import dayjs from 'dayjs'

/** 2026 数据集仿真年：0 = 2026-01-01 00:00，共 8760 小时 */
export const DATASET_YEAR = 2026
export const DATASET_HOURS = 8760

/**
 * 将「此刻」的月/日/时映射到 2026 年小时下标（忽略真实年份，便于任意机器演示）。
 * 超出 1/1～12/31 时钳制到 [0, 8759]。
 */
export function hourIndexIn2026(now = new Date()) {
  const d = dayjs(now)
  const mapped = dayjs(
    `${DATASET_YEAR}-${d.format('MM-DD')}T${d.format('HH')}:00:00`
  )
  if (!mapped.isValid()) {
    return 0
  }
  const start = dayjs(`${DATASET_YEAR}-01-01T00:00:00`)
  let idx = mapped.diff(start, 'hour')
  if (idx < 0) return 0
  if (idx >= DATASET_HOURS) return DATASET_HOURS - 1
  return idx
}

export function timestampAtHourIndex(index) {
  return dayjs(`${DATASET_YEAR}-01-01T00:00:00`).add(index, 'hour')
}

export function formatHourLabel(index, fmt = 'MM-DD HH:mm') {
  return timestampAtHourIndex(index).format(fmt)
}

/** 当前时钟映射到 2026 的日历日 YYYY-MM-DD */
export function todayKeyIn2026(now = new Date()) {
  return timestampAtHourIndex(hourIndexIn2026(now)).format('YYYY-MM-DD')
}

/**
 * 首页指标查看时刻：
 * - 选中日早于「今天」→ 该日 23:00
 * - 否则 → 真实当前时刻（映射当前小时）
 */
export function metricsViewNow(selectedDay, now = new Date()) {
  const today = todayKeyIn2026(now)
  if (selectedDay && String(selectedDay) < today) {
    const d = dayjs(`${selectedDay}T23:00:00`)
    return d.isValid() ? d.toDate() : now
  }
  return now
}
