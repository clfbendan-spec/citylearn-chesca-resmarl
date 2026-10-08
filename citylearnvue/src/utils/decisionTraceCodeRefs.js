/**
 * 推演剧本行 → 源码引用（前端 fallback，与 checa/narrative_code_refs.py 对齐）
 */

const CODE_REF_META = {
  step_start: {
    source_file: 'checa/agent.py',
    source_line_start: 193,
    source_line_end: 261,
    source_label: 'Agent.predict() 主流程',
    code_snippet: [
      '193 | def predict(self, observations, deterministic=None):',
      '212 |     # --- 阶段 1：时序预测 ---',
      '216 |     self.forecasts = self.forecast_agent.compute_forecast(observations)',
      '218 |     # --- 阶段 2：各建筑独立生成动作初稿 ---',
      '222 |     action_proposals = self.initial_actions(observations)',
      '231 |     # --- 阶段 4：社区级负荷平衡（电池树搜索 refine）---',
      '235 |     refine_applied = self.seen_steps >= 1',
      '261 |     return [action_proposals]'
    ].join('\n')
  },
  actual: {
    source_file: 'checa/agent.py',
    source_line_start: 293,
    source_line_end: 297,
    source_label: '本栋（单栋）上步实际净用电',
    code_snippet: [
      '293 | self.cur_battery_soc[b] = observations[...]',
      '295 | net_electricity_consumption = observations[...]  # 单栋',
      '296 | self.elec_consumption_history[b].append(net_electricity_consumption)'
    ].join('\n')
  },
  community: {
    source_file: 'checa/trace_exporter.py',
    source_line_start: 671,
    source_line_end: 683,
    source_label: '三栋净用电合计',
    code_snippet: [
      '671 | community_actual_net = 0.0',
      '674 | community_actual_net += float(observations[...])  # 三栋求和',
      '677 | community_pred_net += load + cooling + dhw + battery - solar'
    ].join('\n')
  },
  forecast: {
    source_file: 'checa/forecast_agent/forecasting_agent.py',
    source_line_start: 143,
    source_line_end: 180,
    source_label: 'ForecastAgent.compute_forecast()',
    code_snippet: [
      '143 | def compute_forecast(self, observations):',
      '166 | cur_states = self.save_data_and_get_cur_states(observations)',
      '169 | if self.seen_steps > 0:',
      '170 |     self.update_weights(observations)',
      '172 | for b in range(self.n_buildings):',
      '     |     ... ensemble_models[...].predict()'
    ].join('\n')
  },
  pid_normal: {
    source_file: 'checa/cooling_device_controller/cooling_device_controller.py',
    source_line_start: 113,
    source_line_end: 250,
    source_label: 'find_best_action() 正常 PID→TMP',
    code_snippet: [
      '121 | indoor_temp / temp_setpoint = observation_value(...)',
      '163 | demand_action = self.pid_controller.get_actions(...)',
      '195 | if demand_action > expected_available_elec:  # 可用电封顶',
      '216 | action = demand_action / cooling_nominal_powers  # → TMP'
    ].join('\n')
  },
  pid_outage: {
    source_file: 'checa/cooling_device_controller/cooling_device_controller.py',
    source_line_start: 113,
    source_line_end: 250,
    source_label: 'find_best_action() 停电 PID→TMP',
    code_snippet: [
      '166 | demand_action = get_actions(... outage / saturation ...)',
      '195 | if demand_action > expected_available_elec:',
      '196 |     demand_action = expected_available_elec',
      '216 | action = demand_action / cooling_nominal_powers'
    ].join('\n')
  },
  pid_get_actions: {
    source_file: 'checa/cooling_device_controller/pid_controller.py',
    source_line_start: 35,
    source_line_end: 140,
    source_label: 'PIDController.get_actions() 入参与 P/I/D',
    code_snippet: [
      '71 | error = setpoint_value - cur_value',
      '90 | P = Kp * error;  I += Ki*error*dt;  D = ...',
      '106 | pid_output = P + I + D   # 正→要制冷',
      '121 | self._trace_last = {pid_error, pid_P, pid_I, pid_D, ...}'
    ].join('\n')
  },
  hot_discomfort: {
    source_file: 'checa/utils.py',
    source_line_start: 61,
    source_line_end: 150,
    source_label: 'compute_step_hot_discomfort() 对齐 CityLearn KPI',
    code_snippet: [
      'cooling_delta = indoor - cooling_set_point',
      'band = comfort_band  # 默认 2.0°C',
      'occupied = occupant_count > 0',
      'is_hot = occupied and (cooling_delta > band)'
    ].join('\n')
  },
  outage_constraint: {
    source_file: 'checa/agent.py',
    source_line_start: 322,
    source_line_end: 357,
    source_label: '停电可用电力预算',
    code_snippet: [
      '322 | available_soc = max(cur_battery_soc - min_battery_soc, 0)',
      '324 | max_elec_in_battery = battery_capacities * max_soc_reduction',
      '327 | expected_available_elec = max_elec_in_battery + solar[0]',
      '344 | diff_energy = solar - (cooling + load) ...'
    ].join('\n')
  },
  rbc_normal: {
    source_file: 'checa/agent.py',
    source_line_start: 413,
    source_line_end: 451,
    source_label: 'DHW 规则控制',
    code_snippet: [
      '421 | heat_water = dhw_demand < avg_dhw_demand and dhw_soc < 0.9',
      '423 | if heat_water:',
      '424 |     DHW_action = action_space.high * 0.20',
      '416 | else:',
      '417 |     DHW_action = -0.83  # 释放储热'
    ].join('\n')
  },
  rbc_outage: {
    source_file: 'checa/agent.py',
    source_line_start: 336,
    source_line_end: 361,
    source_label: '停电 DHW 让路',
    code_snippet: [
      '337 | if dhw_demand < dhw_soc * capacity:',
      '338 |     dhw_demand = 0.0',
      '341 | DHW_action = action_space.low[3*b]'
    ].join('\n')
  },
  battery_state: {
    source_file: 'checa/agent.py',
    source_line_start: 672,
    source_line_end: 693,
    source_label: '电池 SOC 下限约束',
    code_snippet: [
      '688 | else:  # 放电',
      '689 |     soc_difference = cur_battery_soc - min_battery_soc',
      '690 |     energy_limit_wrt_dod = -max(soc_difference * capacity * eff, 0)'
    ].join('\n')
  },
  initial_ele: {
    source_file: 'checa/agent.py',
    source_line_start: 434,
    source_line_end: 436,
    source_label: '电池初稿置 0',
    code_snippet: [
      '434 | # 电池初稿故意置 0',
      '435 | ELE_action = 0.0'
    ].join('\n')
  },
  tree_search: {
    source_file: 'checa/agent.py',
    source_line_start: 562,
    source_line_end: 576,
    source_label: '电池树搜索 Refine',
    code_snippet: [
      '564 | state = [avg_balance, cur_soc, *consumption_forecast[b,:]]',
      '565 | action, cost = self.battery_controller[b].search(state, hour)',
      '566 | ele_after_search = float(action[0])',
      '',
      '# BatteryController.search()',
      '125 | def search(self, state, hour):',
      '138 | heapq.heappush(priority_queue, (self.root.cost, self.root))',
      '166 | return self.find_actions(self.best_final_node), cost'
    ].join('\n')
  },
  tree_search_skip: {
    source_file: 'checa/agent.py',
    source_line_start: 231,
    source_line_end: 238,
    source_label: '首步跳过 Refine',
    code_snippet: [
      '235 | refine_applied = self.seen_steps >= 1',
      '237 | if refine_applied:',
      '238 |     action_proposals = self.refine_actions_with_battery_controller(...)'
    ].join('\n')
  },
  pricing: {
    source_file: 'checa/agent.py',
    source_line_start: 280,
    source_line_end: 286,
    source_label: '电价观测',
    code_snippet: [
      '281 | electricity_pricing = observation_value(..., \'electricity_pricing\')',
      '286 | self._trace_step_pricing = electricity_pricing'
    ].join('\n')
  },
  refine_ele_delta: {
    source_file: 'checa/agent.py',
    source_line_start: 662,
    source_line_end: 669,
    source_label: '终稿 clip',
    code_snippet: [
      '667 | final_actions[3*b+1] = np.clip(ELE_action, low, high)'
    ].join('\n')
  },
  marl_layer: {
    source_file: 'checa/agent.py',
    source_line_start: 284,
    source_line_end: 314,
    source_label: 'apply_residual_correction() MARL 入口',
    code_snippet: [
      '284 | def apply_residual_correction(self, action_proposals, observations):',
      '306 | a_final = self.residual_corrector.correct(a_base, ...)',
      '313 | self._trace_residual_meta = self.residual_corrector.last_trace.to_dict()'
    ].join('\n')
  },
  residual_gen: {
    source_file: 'checa/residual/corrector.py',
    source_line_start: 53,
    source_line_end: 120,
    source_label: '残差 Δa = α · mask · predict_delta()',
    code_snippet: [
      '53 | def predict_delta(...):  # 阶段1 恒为 0',
      '67 | def _masked_delta(self, delta):',
      '87 | def correct(...):',
      '    |     final = a_base + alpha * masked_delta'
    ].join('\n')
  },
  safety_skip: {
    source_file: 'checa/agent.py',
    source_line_start: 231,
    source_line_end: 238,
    source_label: 'Refine 未执行',
    code_snippet: [
      '235 | refine_applied = self.seen_steps >= 1  # 首步为 False'
    ].join('\n')
  },
  safety_reduce: {
    source_file: 'checa/agent.py',
    source_line_start: 603,
    source_line_end: 618,
    source_label: 'B_high 减负荷',
    code_snippet: [
      '604 | if next_step_total > avg + B_high * std:',
      '605 |     trace_meta[\'trigger_reduce_load\'] = True',
      '573 | if DHW_action > 0: final_actions[dhw] = low',
      '582 | final_actions[tmp] *= (1 - TMP_max_reduction_percent)'
    ].join('\n')
  },
  safety_increase: {
    source_file: 'checa/agent.py',
    source_line_start: 627,
    source_line_end: 652,
    source_label: 'B_low 增负荷',
    code_snippet: [
      '628 | elif next_step_total < avg - B_low * std:',
      '629 |     trace_meta[\'trigger_increase_load\'] = True',
      '642 | if dhw_demand < avg and dhw_soc < 0.95:',
      '650 |     final_actions[dhw] = action_space.high'
    ].join('\n')
  },
  safety_pass: {
    source_file: 'checa/agent.py',
    source_line_start: 577,
    source_line_end: 601,
    source_label: '阈值带内',
    code_snippet: [
      '577 | b_high_threshold = avg_balance + B_high * std_balance',
      '578 | b_low_threshold = avg_balance - B_low * std_balance',
      '551 | next_step_total = consumption_forecast[b,1] + battery_demand'
    ].join('\n')
  },
  consumption_breakdown: {
    source_file: 'checa/agent.py',
    source_line_start: 458,
    source_line_end: 467,
    source_label: '净负荷分解公式',
    code_snippet: [
      '452 | predicted = non_shiftable + cooling + dhw + battery - solar'
    ].join('\n')
  },
  final_exec: {
    source_file: 'checa/agent.py',
    source_line_start: 662,
    source_line_end: 670,
    source_label: '终稿执行',
    code_snippet: [
      '663 | for b in range(n_buildings):',
      '667 |     final_actions[...] = np.clip(...)',
      '670 | return final_actions'
    ].join('\n')
  },
  action_chesca: {
    source_file: 'checa/agent.py',
    source_line_start: 248,
    source_line_end: 274,
    source_label: 'CHESCA a_base',
    code_snippet: [
      '251 | action_proposals = self.initial_actions(observations)',
      '267 | action_proposals = self.refine_actions_with_battery_controller(...)',
      '274 | # a_base 进入阶段 5 残差'
    ].join('\n')
  },
  action_marl: {
    source_file: 'multi_agent_runner_copy.py',
    source_line_start: 251,
    source_line_end: 273,
    source_label: 'MARL α·mask·Δa',
    code_snippet: [
      '270 | raw_delta = self.predict_delta(...)  # 日志 [MARL动作] = 原始 Δa',
      '271 | masked = self._masked_delta(raw_delta)',
      '272 | scaled = alpha * masked'
    ].join('\n')
  },
  action_resmarl: {
    source_file: 'checa/agent.py',
    source_line_start: 299,
    source_line_end: 330,
    source_label: 'CHESCA-ResMARL a_final',
    code_snippet: [
      '303 | # a_final = clip(a_base + α · mask · Δa)',
      '324 | a_final = self.residual_corrector.correct(...)'
    ].join('\n')
  },
  // ---- Multi-agent SAC（SymmetricComfortReward）----
  marl_obs: {
    source_file: 'Multi-agent.py',
    source_line_start: 102,
    source_line_end: 126,
    source_label: 'REWARD_KWARGS（悬停显示本任务实际超参）',
    code_snippet: [
      'REWARD_KWARGS = { ... }  # 见 decision_trace.json → reward_kwargs',
      '# 本行字段：T coolSP dT band occ out act_cool act_bat cool_kWh cool_dem net price SOC R'
    ].join('\n')
  },
  marl_kappa: {
    source_file: 'Multi-agent.py',
    source_line_start: 277,
    source_line_end: 360,
    source_label: 'κ-EMA 跨楼能力估计（每步 O(1)）',
    code_snippet: [
      '# 路径 A（有 act）：sample = cool_elec / act；上修 α↑、下修 α↓，且 κ ≥ κ_floor',
      '# 路径 B（无 act）：只在 cool_elec > κ 时上修下界，禁止把弱制冷写成 κ',
      '# E_ref = max(κ, κ_floor) · a_ref（不再与 weak_cool_elec=0.15 混合）',
      '# cold_tol = max(cool_when_cold_elec, cold_tol_frac · E_ref)',
      '# 不存历史轨迹；每栋仅 κ / cool_cap / updates 三个标量'
    ].join('\n')
  },
  marl_reward: {
    source_file: 'Multi-agent.py',
    source_line_start: 400,
    source_line_end: 480,
    source_label: 'SymmetricComfortReward 计算过程',
    code_snippet: [
      'κ_b ← 非对称 EMA(cool_elec / act)，且 κ ≥ κ_floor',
      'E_ref = max(κ_b, κ_floor) · a_ref',
      'δ = |T − SP|；R_temp = −δ^exponent（带外，band 不变）',
      '过热：deficit=(E_ref−E)/E_ref → R_act_hot，|R_act_hot| ≤ act_penalty_cap',
      '过冷：E>cold_tol → R_act_cold；带内 T<SP 仍制冷 → R_below',
      '冷侧合计用 cold_penalty_cap，不跟热侧共用 cap',
      'R = R_temp + R_act_hot + R_act_cold + R_below'
    ].join('\n')
  }
}

function formatRewardKwargsSnippet(rewardKwargs) {
  if (!rewardKwargs || typeof rewardKwargs !== 'object') {
    return null
  }
  const lines = ['REWARD_KWARGS = {']
  Object.keys(rewardKwargs).forEach((k) => {
    const v = rewardKwargs[k]
    let vv
    if (typeof v === 'number') {
      vv = String(v)
    } else if (Array.isArray(v)) {
      vv = JSON.stringify(v)
    } else {
      vv = JSON.stringify(v)
    }
    lines.push(`    '${k}': ${vv},`)
  })
  lines.push('}')
  lines.push('')
  lines.push('# R = R_temp + R_act；E_ref=max(κ,κ_floor)·a_ref')
  lines.push('# 热侧只受 act_penalty_cap；冷侧用 cold_penalty_cap')
  lines.push('# 悬停来源：decision_trace.json → reward_kwargs')
  return lines.join('\n')
}

export function classifyNarrativeLine(text) {
  const line = String(text || '')
  if (line.includes('[观测动作]')) return 'marl_obs'
  if (line.includes('[κ-EMA]') || line.includes('[k-EMA]')) return 'marl_kappa'
  if (line.includes('[奖励计算]')) return 'marl_reward'
  if (/^\[\d{2}:\d{2}\]/.test(line) && line.includes('开始计算')) return 'step_start'
  if (line.includes('[本步实况]')) return 'actual'
  if (line.includes('[社区负荷]')) return 'community'
  if (line.includes('[预测层]')) return 'forecast'
  if (line.includes('[冷机PID推演]')) return 'pid_get_actions'
  if (line.includes('[高温不适判定]')) return 'hot_discomfort'
  if (line.includes('[空调控制]') || line.includes('[PID层]') || line.includes('[制冷(TMP)]')) {
    return line.includes('停电') ? 'pid_outage' : 'pid_normal'
  }
  if (line.includes('[停电约束]') || line.includes('[停电供电盘点]')) return 'outage_constraint'
  if (line.includes('[RBC层]') || line.includes('[供热(DHW)]')) {
    return line.includes('停电') ? 'rbc_outage' : 'rbc_normal'
  }
  if (line.includes('[电池状态]')) return 'battery_state'
  if (line.includes('[初稿]')) return 'initial_ele'
  if (line.includes('[树搜索层]')) return line.includes('跳过') ? 'tree_search_skip' : 'tree_search'
  if (line.includes('[电价观测]')) return 'pricing'
  if (line.includes('[Refine 微调]')) return 'refine_ele_delta'
  if (line.includes('[MARL层')) return 'marl_layer'
  if (line.includes('[残差生成]')) return 'residual_gen'
  if (line.includes('[安全审查]')) {
    if (line.includes('未执行社区 Refine')) return 'safety_skip'
    if (line.includes('设备分解')) return 'consumption_breakdown'
    if (line.includes('超过 B_high')) return 'safety_reduce'
    if (line.includes('低于 B_low')) return 'safety_increase'
    return 'safety_pass'
  }
  if (line.includes('最终执行')) return 'final_exec'
  if (line.includes('[CHESCA-RESMARL动作]')) return 'action_resmarl'
  if (line.includes('[CHESCA动作]')) return 'action_chesca'
  if (line.includes('[MARL动作]')) return 'action_marl'
  return 'step_start'
}

export function buildCodeRefForLine(text, options = {}) {
  const tag = classifyNarrativeLine(text)
  const meta = { ...(CODE_REF_META[tag] || CODE_REF_META.step_start) }
  // Multi-agent：[观测动作] 悬停展示本任务实际 REWARD_KWARGS
  if (tag === 'marl_obs') {
    const snip = formatRewardKwargsSnippet(options.reward_kwargs)
    if (snip) {
      meta.source_label = 'REWARD_KWARGS（本任务实际超参）'
      meta.code_snippet = snip
      meta.source_file = 'Multi-agent.py · REWARD_KWARGS'
      meta.source_line_start = '—'
      meta.source_line_end = '—'
    }
  }
  return { code_tag: tag, ...meta }
}

export function buildNarrativeEntriesFromLines(lines, options = {}) {
  if (!lines || !lines.length) return []
  return lines.map((text) => ({
    text,
    ...buildCodeRefForLine(text, options)
  }))
}
