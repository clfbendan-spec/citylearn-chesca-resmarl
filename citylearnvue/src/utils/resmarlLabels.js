/**
 * 从任务 chesca_agent_config / resmarlSummary 生成看板标签。
 * 纯基线（未启用残差）不展示「纯 CHESCA」字样，返回空字符串。
 */

function sanitizeLabel(label) {
  const text = label == null ? '' : String(label).trim()
  if (!text || text === '纯 CHESCA') {
    return ''
  }
  return text
}

export function formatResmarlLabel(summary) {
  if (!summary || typeof summary !== 'object') {
    return ''
  }
  const fromSummary = sanitizeLabel(summary.label)
  if (fromSummary) {
    return fromSummary
  }
  if (!summary.enabled) {
    return ''
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
    return { enabled: false, marlMode: 'none', alpha: 0, label: '' }
  }
  const enabled = !!cfg.resmarl_enabled
  let marlMode = cfg.marl_mode != null ? String(cfg.marl_mode).trim().toLowerCase() : 'none'
  if (marlMode === 'central_residual') marlMode = 'multi_agent'
  if (enabled && (!marlMode || marlMode === 'none')) {
    marlMode = 'multi_agent'
  }
  const alpha = Number(cfg.residual_alpha) || 0
  let label = ''
  if (!enabled || marlMode === 'none') {
    label = ''
  } else if (alpha <= 0) {
    label = 'CHESCA-ResMARL α=0'
  } else {
    const ckpt = cfg.multi_agent_checkpoint != null ? String(cfg.multi_agent_checkpoint).trim() : ''
    label = ckpt
      ? `CHESCA-ResMARL α=${alpha.toFixed(2)}(预存模型)`
      : `CHESCA-ResMARL α=${alpha.toFixed(2)}(缺 checkpoint)`
  }
  return {
    enabled,
    marlMode,
    alpha,
    label,
    evalSchema: cfg.eval_schema,
    trainSchema: cfg.train_schema,
    multiAgentEvalSchema: cfg.multi_agent_eval_schema,
  }
}
