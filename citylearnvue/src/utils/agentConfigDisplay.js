/**
 * 将 chesca_agent_config.json 整理为看板侧栏可读结构。
 */

import { buildResmarlSummaryFromConfig, parseAgentConfigJson } from './resmarlLabels'

/** @type {{ key: string, label: string, group: string, hint?: string }[]} */
export const AGENT_CONFIG_FIELDS = [
  { key: 'tau', label: '预测步长 τ', group: 'forecast', hint: 'ForecastAgent / 树搜索展望步数' },
  { key: 'balance_type', label: '适应度类型', group: 'balance', hint: '电池树搜索 balance_type（如 C）' },
  { key: 'B_low', label: 'B_low', group: 'balance', hint: '净负荷低于均值 − B_low×σ 时增负荷' },
  { key: 'B_high', label: 'B_high', group: 'balance', hint: '净负荷高于均值 + B_high×σ 时减负荷' },
  {
    key: 'TMP_max_reduction_percent',
    label: '冷机最大削减',
    group: 'balance',
    hint: 'Refine 减负荷时 TMP 最大削减比例'
  },
  { key: 'max_soc_normal', label: '正常 SOC 上限', group: 'battery' },
  { key: 'max_soc_outage', label: '停电 SOC 上限', group: 'battery' },
  {
    key: 'max_soc_reduction_in_outage',
    label: '停电最大 SOC 降幅',
    group: 'battery'
  },
  { key: 'resmarl_enabled', label: '启用 CHESCA-ResMARL', group: 'resmarl' },
  { key: 'marl_mode', label: 'MARL 模式', group: 'resmarl', hint: 'none / multi_agent' },
  {
    key: 'multi_agent_train_epochs',
    label: 'SAC 训练轮数',
    group: 'resmarl',
    hint: '评估前 Multi-Agent SAC 训练 epoch'
  },
  { key: 'multi_agent_explore', label: 'SAC explore', group: 'resmarl' },
  { key: 'residual_alpha', label: '残差强度 α', group: 'resmarl' },
  { key: 'resmarl_after_safety', label: '安全审查后残差', group: 'resmarl' },
  { key: 'residual_action_mask', label: '动作 mask', group: 'resmarl' }
]

const GROUP_META = {
  forecast: { title: '预测层', order: 1 },
  balance: { title: '负荷平衡 / Refine', order: 2 },
  battery: { title: '电池 SOC 约束', order: 3 },
  resmarl: { title: 'CHESCA-ResMARL', order: 4 },
  other: { title: '其它参数', order: 5 }
}

const KNOWN_KEYS = new Set([
  ...AGENT_CONFIG_FIELDS.map((f) => f.key),
  'min_soc_per_hour'
])

/** 旧版配置快照中的废弃键，看板侧栏不再展示 */
const DEPRECATED_KEYS = new Set([
  'multi_agent_checkpoint_path',
  'resmarl_policy_path',
  'multi_agent_enabled',
  'residual_enabled',
  'resmarl_alpha',
  'residual_policy_path'
])

export function formatConfigValue(key, value) {
  if (value == null || value === '') return '—'
  if (key === 'residual_action_mask' && typeof value === 'object') {
    const on = Object.entries(value)
      .filter(([, v]) => !!v)
      .map(([k]) => String(k).toUpperCase())
    return on.length ? on.join(' · ') : '无'
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (key === 'marl_mode') {
    const modeMap = {
      none: '纯 CHESCA',
      multi_agent: 'CHESCA-ResMARL'
    }
    return modeMap[String(value).toLowerCase()] || String(value)
  }
  if (typeof value === 'number') {
    if (key === 'residual_alpha' || key === 'TMP_max_reduction_percent') {
      return Number(value).toFixed(2)
    }
    if (key === 'tau') return String(Math.round(value))
    return Number.isInteger(value) ? String(value) : Number(value).toFixed(4).replace(/\.?0+$/, '')
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (e) {
      return String(value)
    }
  }
  return String(value)
}

/**
 * @param {object|null} cfg
 * @returns {{ hour: number, value: number|null }[]}
 */
export function buildMinSocSeries(cfg) {
  const raw = cfg && cfg.min_soc_per_hour
  if (!raw || typeof raw !== 'object') return []
  const series = []
  for (let h = 0; h < 24; h++) {
    const v = raw[String(h)] != null ? raw[String(h)] : raw[h]
    const n = v == null || v === '' ? null : Number(v)
    series.push({ hour: h, value: Number.isFinite(n) ? n : null })
  }
  return series
}

/**
 * @param {object|string|null} input 对象或 JSON 文本
 */
export function buildAgentConfigView(input) {
  const cfg =
    typeof input === 'string' ? parseAgentConfigJson(input) : input && typeof input === 'object' ? input : null

  if (!cfg) {
    return {
      hasConfig: false,
      resmarl: buildResmarlSummaryFromConfig(null),
      groups: [],
      minSoc: [],
      rawJson: '',
      unknownKeys: []
    }
  }

  const groupsMap = {}
  AGENT_CONFIG_FIELDS.forEach((field) => {
    if (!(field.key in cfg) && field.group === 'resmarl' && cfg.resmarl_enabled == null) {
      // still show with empty if any resmarl key exists
    }
    if (!(field.key in cfg)) return
    if (!groupsMap[field.group]) {
      groupsMap[field.group] = {
        id: field.group,
        title: GROUP_META[field.group].title,
        order: GROUP_META[field.group].order,
        items: []
      }
    }
    groupsMap[field.group].items.push({
      key: field.key,
      label: field.label,
      hint: field.hint || '',
      value: cfg[field.key],
      display: formatConfigValue(field.key, cfg[field.key])
    })
  })

  // ensure resmarl group shows even with defaults-derived summary
  if (!groupsMap.resmarl && (cfg.resmarl_enabled != null || cfg.residual_alpha != null)) {
    groupsMap.resmarl = {
      id: 'resmarl',
      title: GROUP_META.resmarl.title,
      order: GROUP_META.resmarl.order,
      items: []
    }
    ;[
      'resmarl_enabled',
      'marl_mode',
      'multi_agent_train_epochs',
      'multi_agent_explore',
      'residual_alpha',
      'resmarl_after_safety',
      'residual_action_mask'
    ].forEach(
      (key) => {
        if (!(key in cfg)) return
        const field = AGENT_CONFIG_FIELDS.find((f) => f.key === key)
        groupsMap.resmarl.items.push({
          key,
          label: field ? field.label : key,
          hint: field ? field.hint || '' : '',
          value: cfg[key],
          display: formatConfigValue(key, cfg[key])
        })
      }
    )
  }

  const unknownKeys = Object.keys(cfg).filter((k) => !KNOWN_KEYS.has(k) && !DEPRECATED_KEYS.has(k))
  if (unknownKeys.length) {
    groupsMap.other = {
      id: 'other',
      title: GROUP_META.other.title,
      order: GROUP_META.other.order,
      items: unknownKeys.map((key) => ({
        key,
        label: key,
        hint: '',
        value: cfg[key],
        display: formatConfigValue(key, cfg[key])
      }))
    }
  }

  const groups = Object.values(groupsMap).sort((a, b) => a.order - b.order)
  let rawJson = ''
  try {
    rawJson = JSON.stringify(cfg, null, 2)
  } catch (e) {
    rawJson = ''
  }

  return {
    hasConfig: true,
    resmarl: buildResmarlSummaryFromConfig(cfg),
    groups,
    minSoc: buildMinSocSeries(cfg),
    rawJson,
    unknownKeys
  }
}

export { parseAgentConfigJson }
