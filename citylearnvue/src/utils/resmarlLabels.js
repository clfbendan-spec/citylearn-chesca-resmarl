/**
 * 从任务 chesca_agent_config / resmarlSummary 生成看板标签。
 */

export function formatResmarlLabel(summary) {
  if (!summary || typeof summary !== 'object') {
    return '未标注'
  }
  if (summary.label) {
    return String(summary.label)
  }
  if (!summary.enabled) {
    return '纯 CHESCA'
  }
  const alpha = Number(summary.alpha)
  if (!Number.isFinite(alpha) || alpha <= 0) {
    return 'CHESCA-ResMARL α=0'
  }
  return `CHESCA-ResMARL α=${alpha.toFixed(2)}`
}

export function parseAgentConfigJson(text) {
  if (!text || !String(text).trim()) {
    return null
  }
  try {
    return JSON.parse(text)
  } catch (e) {
    return null
  }
}

export function buildResmarlSummaryFromConfig(cfg) {
  if (!cfg || typeof cfg !== 'object') {
    return { enabled: false, marlMode: 'none', alpha: 0, label: '纯 CHESCA' }
  }
  const enabled = !!cfg.resmarl_enabled
  let marlMode = cfg.marl_mode != null ? String(cfg.marl_mode).trim().toLowerCase() : 'none'
  if (marlMode === 'central_residual') marlMode = 'multi_agent'
  if (enabled && (!marlMode || marlMode === 'none')) {
    marlMode = 'multi_agent'
  }
  const alpha = Number(cfg.residual_alpha) || 0
  let label = '纯 CHESCA'
  if (!enabled || marlMode === 'none') {
    label = '纯 CHESCA'
  } else if (alpha <= 0) {
    label = 'CHESCA-ResMARL α=0'
  } else {
    const epochs = cfg.multi_agent_train_epochs != null ? cfg.multi_agent_train_epochs : 20
    const split = cfg.schema_split_enabled !== false
    const evalShort = split && cfg.eval_schema
      ? String(cfg.eval_schema).replace('citylearn_challenge_2023_', '')
      : ''
    const splitHint = split && evalShort ? ` · eval=${evalShort}` : ''
    label = `CHESCA-ResMARL α=${alpha.toFixed(2)}(SAC ${epochs}轮${splitHint})`
  }
  const schemaSplit = cfg.schema_split_enabled !== false
  return {
    enabled,
    marlMode,
    alpha,
    label,
    schemaSplit,
    trainSchema: cfg.train_schema,
    evalSchema: cfg.eval_schema,
  }
}
