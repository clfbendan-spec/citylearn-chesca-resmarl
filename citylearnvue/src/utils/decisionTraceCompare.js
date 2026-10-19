/**
 * 决策同步回放：把两条 trace 的每一步对齐成一帧，供左右并排比较。
 *
 * 为什么单独一层
 * --------------
 * CHESCA / Multi-agent / District 三线的 decision_trace.json 顶层结构一致（v2：steps[]），
 * 但**每步里能拿到的量不同**：
 *   · district 有 `district.community_net_kw` / `peak_target_kw` / `is_peak_step`；
 *   · CHESCA / Multi-agent 没有区域块 ⇒ 社区净负荷得从每栋 `[观测动作]` 行的 `net=` 反解；
 *   · 动作维数有 3（dhw/ele/tmp）或 4（+a_peak_resp）两种。
 * 这里统一成一个 frame 结构，组件只负责画，不再各自判断字段来源。
 *
 * 对齐规则：按 **step 数值** 对齐，不按数组下标 ——
 * 两边的记录起点/抽稀可能不同（district 允许 --decision-log-stride），
 * 按下标会把 step 100 和 step 200 并排显示，比不出来。
 */

const NET_FIELD_RE = /net=([-+]?\d+(?:\.\d+)?)/i
// CHESCA 剧本把本步净负荷写在安全审查行：`[安全审查] 净负荷：4.549 kWh，B_high 警戒线：…`
const NET_REVIEW_RE = /净负荷[：:]\s*([-+]?\d+(?:\.\d+)?)/
// 社区级滞后兜底：`[社区负荷] 三栋实际上步净用电合计 0.000 kWh，预测下步净用电合计 9.866 kWh`
const NET_COMMUNITY_RE = /上步净用电合计\s*([-+]?\d+(?:\.\d+)?)/
const ACTION_DIM_NAMES = ['dhw', 'ele', 'tmp', 'a_peak_resp']

function num(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function fmtNum(v, d = 2) {
  const n = num(v)
  return n == null ? '—' : n.toFixed(d)
}

/**
 * 缺 `district.community_net_kw` 时，从剧本里反解本步社区净负荷。
 *
 * 三种来源的优先级（按「是否本步、是否社区合计」排）：
 *   ① Multi-agent / District 通用出口：每栋 `[观测动作] … net=4.25 …` ⇒ 逐栋求和
 *   ② CHESCA 剧本：每栋 `[安全审查] 净负荷：4.549 kWh` ⇒ 逐栋求和（含设备分解，是本步值）
 *   ③ `[社区负荷] … 上步净用电合计 X kWh` ⇒ 社区合计，但**滞后一步**，只作最后兜底
 */
function netFromNarrative(step) {
  const buildings = (step && step.buildings) || []
  let sumObserved = 0
  let hasObserved = false
  let sumReviewed = 0
  let hasReviewed = false
  let communityLast = null

  buildings.forEach((b) => {
    const lines = b.narrative_lines || []
    const lineObs = lines.find((ln) => String(ln).includes('[观测动作]'))
    if (lineObs) {
      const m = String(lineObs).match(NET_FIELD_RE)
      if (m) {
        const v = Number(m[1])
        if (Number.isFinite(v)) {
          sumObserved += v
          hasObserved = true
        }
      }
    }
    const lineRev = lines.find(
      (ln) => String(ln).includes('[安全审查]') && String(ln).includes('净负荷')
    )
    if (lineRev) {
      const m = String(lineRev).match(NET_REVIEW_RE)
      if (m) {
        const v = Number(m[1])
        if (Number.isFinite(v)) {
          sumReviewed += v
          hasReviewed = true
        }
      }
    }
    if (communityLast == null) {
      const lineCom = lines.find((ln) => String(ln).includes('[社区负荷]'))
      if (lineCom) {
        const m = String(lineCom).match(NET_COMMUNITY_RE)
        if (m) {
          const v = Number(m[1])
          if (Number.isFinite(v)) communityLast = v
        }
      }
    }
  })

  if (hasObserved) return sumObserved
  if (hasReviewed) return sumReviewed
  return communityLast
}

/** 取该步的动作维名（district 写进步骤里；其它线按长度推）。 */
function resolveDimNames(step, buildings) {
  const declared = step && step.district && step.district.action_dims
  if (Array.isArray(declared) && declared.length) return declared.slice()
  const first = buildings[0]
  const len = first && first.actions && first.actions.final
    ? Object.keys(first.actions.final).length
    : 3
  return ACTION_DIM_NAMES.slice(0, Math.max(3, len))
}

/**
 * 单步 → 统一 frame。
 * @returns {{
 *   step:number, hour:any, episode:number,
 *   netKw:number|null, peakTargetKw:number|null, peakRatio:number|null, isPeakStep:boolean,
 *   dimNames:string[], buildings:object[], summary:string
 * }}
 */
export function summarizeStep(step) {
  const district = (step && step.district) || {}
  const rawBuildings = (step && step.buildings) || []
  const dimNames = resolveDimNames(step, rawBuildings)

  // district 把「实际执行动作」按 agent 汇总在 district.exec_actions / raw_actions 里，
  // 长度随 action_dims（3 或 4）。这是最准的来源 —— building 条目只固定存 dhw/ele/tmp 三键。
  const execMap = district.exec_actions || null
  const rawMap = district.raw_actions || null
  const execKeys = execMap ? Object.keys(execMap) : []
  const rawKeys = rawMap ? Object.keys(rawMap) : []
  const pickVec = (map, keys, i) => {
    if (!map) return null
    const key = keys.includes(`agent_${i}`) ? `agent_${i}` : keys[i]
    if (key == null) return null
    const v = map[key]
    return Array.isArray(v) ? v : null
  }

  let netKw = num(district.community_net_kw)
  if (netKw == null) netKw = netFromNarrative(step)

  const buildings = rawBuildings.map((b, i) => {
    const actions = b.actions || {}
    const fin = actions.final || {}
    const raw = actions.raw || {}
    const execVec = pickVec(execMap, execKeys, i)
    const rawVec = pickVec(rawMap, rawKeys, i)

    const dims = (execVec && execVec.length >= dimNames.length)
      ? dimNames.map((_name, di) => num(execVec[di]))
      : dimNames.map((name, di) => {
        if (name === 'dhw' || name === 'ele' || name === 'tmp') return num(fin[name])
        const vec = Array.isArray(b.action_vector) ? b.action_vector : null
        return vec && vec.length > di ? num(vec[di]) : null
      })

    const rawDims = (rawVec && rawVec.length >= dimNames.length)
      ? dimNames.map((_name, di) => num(rawVec[di]))
      : dimNames.map((name) => {
        if (name === 'dhw' || name === 'ele' || name === 'tmp') return num(raw[name])
        return null
      })

    return {
      id: b.building,
      outage: !!b.outage_flag,
      soc: num(b.battery_soc),
      dhwSoc: num(b.dhw_soc),
      dims,
      rawDims,
      summary: String(b.decision_summary || '')
    }
  })

  const peakTargetKw = num(district.peak_target_kw)
  let peakRatio = num(district.peak_ratio)
  if (peakRatio == null && netKw != null && peakTargetKw) {
    peakRatio = netKw / peakTargetKw
  }
  // district 专有：本步占「本段实测峰值」的比例（peak_target 常为 null，这个几乎总有）
  const ratioVsSegmentPeak = num(district.ratio_vs_segment_peak)

  return {
    step: step ? step.step : null,
    hour: step ? step.hour : null,
    episode: step && step.episode != null ? step.episode : 0,
    netKw,
    peakTargetKw,
    peakRatio,
    ratioVsSegmentPeak,
    isPeakStep: !!district.is_peak_step,
    dimNames,
    buildings,
    summary: buildings.length ? buildings[0].summary : ''
  }
}

/** trace → Map(step → frame)；同一 step 出现多次时保留第一条（与界面单线回放一致）。 */
export function buildFrameMap(trace) {
  const map = new Map()
  const steps = (trace && Array.isArray(trace.steps)) ? trace.steps : []
  steps.forEach((step) => {
    const key = Number(step && step.step)
    if (!Number.isFinite(key) || map.has(key)) return
    map.set(key, summarizeStep(step))
  })
  return map
}

/**
 * 两边按 step 并集对齐。
 * @returns {Array<{step:number, left:object|null, right:object|null}>}
 */
export function alignFrames(leftTrace, rightTrace) {
  const leftMap = buildFrameMap(leftTrace)
  const rightMap = buildFrameMap(rightTrace)
  const keys = [...new Set([...leftMap.keys(), ...rightMap.keys()])].sort((a, b) => a - b)
  return keys.map((step) => ({
    step,
    left: leftMap.get(step) || null,
    right: rightMap.get(step) || null
  }))
}

/** 对齐后两边各有多少步、共多少帧、有没有完全对不上的区间。 */
export function frameCoverage(leftTrace, rightTrace) {
  const leftMap = buildFrameMap(leftTrace)
  const rightMap = buildFrameMap(rightTrace)
  const leftSteps = [...leftMap.keys()].sort((a, b) => a - b)
  const rightSteps = [...rightMap.keys()].sort((a, b) => a - b)
  const union = [...new Set([...leftSteps, ...rightSteps])]
  const both = leftSteps.filter((s) => rightMap.has(s))
  return {
    leftCount: leftSteps.length,
    rightCount: rightSteps.length,
    unionCount: union.length,
    bothCount: both.length,
    leftOnlyCount: leftSteps.length - both.length,
    rightOnlyCount: rightSteps.length - both.length,
    leftStart: leftSteps.length ? leftSteps[0] : null,
    leftEnd: leftSteps.length ? leftSteps[leftSteps.length - 1] : null,
    rightStart: rightSteps.length ? rightSteps[0] : null,
    rightEnd: rightSteps.length ? rightSteps[rightSteps.length - 1] : null
  }
}

/** 逐维做差（只在两边都有该栋、该维时给数）。 */
export function diffFrames(left, right) {
  if (!left || !right) return null
  const n = Math.min(left.buildings.length, right.buildings.length)
  const dimNames = left.dimNames.length >= right.dimNames.length
    ? left.dimNames
    : right.dimNames
  const buildings = []
  for (let i = 0; i < n; i += 1) {
    const a = left.buildings[i]
    const b = right.buildings[i]
    const dimDiffs = dimNames.map((_name, di) => {
      const va = a.dims[di]
      const vb = b.dims[di]
      return (va == null || vb == null) ? null : (vb - va)
    })
    buildings.push({
      leftId: a.id,
      rightId: b.id,
      dims: dimDiffs,
      soc: (a.soc == null || b.soc == null) ? null : (b.soc - a.soc),
      net: null
    })
  }
  return {
    netKw: (left.netKw == null || right.netKw == null) ? null : (right.netKw - left.netKw),
    peakRatio: (left.peakRatio == null || right.peakRatio == null)
      ? null
      : (right.peakRatio - left.peakRatio),
    buildings
  }
}

/** 差异显著性：只用于界面着色，不参与任何统计结论。 */
export function diffLevel(delta, scale = 1) {
  if (delta == null) return 'none'
  const abs = Math.abs(delta) / (scale || 1)
  if (abs < 1e-9) return 'zero'
  if (abs < 0.02) return 'small'
  if (abs < 0.15) return 'medium'
  return 'large'
}

/**
 * 全段净负荷趋势（左右两条线共享同一 y 轴，才比得出高低）。
 * 采样到最多 maxPoints 个点 —— 2208 步全画会产生超长 path，浏览器白掉。
 *
 * @returns {{leftPath:string, rightPath:string, min:number|null, max:number|null}}
 */
export function buildNetSparkPaths(frames, width = 600, height = 64, maxPoints = 320) {
  const n = (frames && frames.length) || 0
  const empty = { leftPath: '', rightPath: '', min: null, max: null }
  if (!n) return empty

  const stepN = Math.max(1, Math.floor(n / maxPoints))
  const values = []
  for (let i = 0; i < n; i += stepN) {
    const f = frames[i]
    if (!f) continue
    if (f.left && f.left.netKw != null) values.push(f.left.netKw)
    if (f.right && f.right.netKw != null) values.push(f.right.netKw)
  }
  if (!values.length) return empty

  let min = values[0]
  let max = values[0]
  values.forEach((v) => {
    if (v < min) min = v
    if (v > max) max = v
  })
  const span = (max - min) || 1
  const pad = 6
  const toY = (v) => pad + (1 - (v - min) / span) * (height - pad * 2)
  const toX = (i) => (n <= 1 ? 0 : (i / (n - 1)) * width)

  const build = (side) => {
    let d = ''
    let open = false
    for (let i = 0; i < n; i += stepN) {
      const f = frames[i]
      const frame = f ? f[side] : null
      const v = frame && frame.netKw != null ? frame.netKw : null
      if (v == null) {
        open = false
        continue
      }
      d += `${open ? ' L' : 'M'}${toX(i).toFixed(2)},${toY(v).toFixed(2)}`
      open = true
    }
    return d
  }

  return { leftPath: build('left'), rightPath: build('right'), min, max }
}

/** 游标 x 坐标（与 buildNetSparkPaths 的 toX 同一映射）。 */
export function sparkCursorX(idx, total, width = 600) {
  if (!total || total <= 1) return 0
  return (Math.max(0, Math.min(idx, total - 1)) / (total - 1)) * width
}

export { fmtNum }
