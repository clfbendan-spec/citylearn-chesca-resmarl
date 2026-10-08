# -*- coding: utf-8 -*-
# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
"""CHESCA 的配置层：默认值 + 参数校验 + 配置组装（2026-10-08 从 CHESCA.py 抽出 ✓）。

为什么单独成模块 ✓：CHESCA.py 原本自己带着 200+ 行"读配置 / 校验 / 拼默认值" ✗，
而其中**校验**（`_parse_threshold` 这类"检查数值合理"的小函数 ✓）和**默认值**
都是别处也想复用的东西 ✓ ⇒ 抽到这里 ✓，CHESCA.py 只留 `parse_args` + 一行调用 ✓。

谁在用 ✓：
  · `CHESCA.py`（纯 CHESCA 入口 ✓）：参数**全部来自命令行** ⇒ `build_agent_config(...)` ✓；
    参数表 `AGENT_PARAM_KEYS` 与「命令行 → 配置覆盖字典」的 `_cli_overrides_from_args` 也
    在本模块 ✓（2026-10-08 从 CHESCA.py 抽进来 ✓，那边只留 `parse_args` ✓）；
  · `CHESCA_ResMARL.py` / `20260914153739.py` / `ablation_resmarl.py` /
    `tests/test_residual_phase0.py` ✓：仍按老方式读 `chesca_agent_config.json` ⇒
    `load_agent_config(path)` ✓（兼容保留 ✓）—— 它们**直接从本模块 import** ✓
    （2026-10-08 起不再经 `CHESCA.py` 反导出 ✗：CHESCA.py 自己不用这个名字）。

取值优先级 ✓：**命令行 > 配置文件 > 本模块默认值**（纯 CHESCA 没有"配置文件"这一步 ✓）。
"""

import json
import re
from pathlib import Path

# CHESCA 的默认配置（52 个键 ✓；由旧版实跑导出 ✓ —— 与 Java 侧默认值同源 ✓）
DEFAULTS = {
    'B_high':                                  1.0,
    'B_low':                                   1.18,
    'TMP_max_reduction_percent':               0.0,
    'balance_type':                            'C',
    'clear_open_loop_floor_when_under_setpoint': False,
    'cooling_demand_feedforward_frac':         0.1,
    'demand_feedforward_only_when_overheat':   False,
    'lagged_indoor_hotter_margin_c':           0.3,
    'lagged_indoor_only_when_hotter':          False,
    'marl_mode':                               'none',
    'max_soc_normal':                          0.99,
    'max_soc_outage':                          0.87,
    'max_soc_reduction_in_outage':             0.7,
    'min_cool_per_c_outdoor_gap':              0.03,
    'min_cool_per_c_overheat':                 0.12,
    'min_soc_per_hour':                        {'0': 0.6, '1': 0.65, '2': 0.72, '3': 0.78, '4': 0.8, '5': 0.85, '6': 0.8, '7': 0.75, '8': 0.7, '9': 0.6, '10': 0.5, '11': 0.6, '12': 0.65, '13': 0.65, '14': 0.7, '15': 0.7, '16': 0.7, '17': 0.65, '18': 0.7, '19': 0.6, '20': 0.6, '21': 0.6, '22': 0.6, '23': 0.55},
    'multi_agent_checkpoint':                  '',
    'multi_agent_explore':                     False,
    'multi_agent_train_epochs':                20,
    'outdoor_floor_allow_when_under_setpoint': True,
    'outdoor_floor_max_overheat_c':            0.5,
    'outdoor_gap_deadband_c':                  5.0,
    'post_outage_forbid_charge_when_overheat': True,
    'post_outage_max_ele_charge':              0.15,
    'post_outage_overheat_c':                  0.5,
    'post_outage_relax_steps':                 4,
    'post_outage_soft_charge_enabled':         True,
    'post_outage_tmp_cap_enabled':             True,
    'post_outage_tmp_cap_steps':               4,
    'post_outage_tmp_max_start':               0.4,
    'post_outage_tmp_ramp':                    True,
    'post_outage_tmp_stagger':                 True,
    'post_outage_waive_min_soc':               True,
    'price_aware_battery_enabled':             True,
    'price_global_reserve_enabled':            True,
    'price_high_discharge_ele':                0.15,
    'price_high_forbid_charge':                True,
    'price_high_force_discharge':              True,
    'price_high_quantile':                     0.75,
    'price_high_soc_threshold':                0.7,
    'price_history_min_steps':                 48,
    'price_low_charge_ele':                    0.25,
    'price_low_quantile':                      0.25,
    'price_low_search_boost':                  True,
    'price_low_target_soc':                    0.8,
    'price_min_reserve_soc':                   0.55,
    'residual_action_mask':                    {'dhw': False, 'ele': True, 'tmp': False},
    'residual_alpha':                          0.0,
    'resmarl_after_safety':                    True,
    'resmarl_enabled':                         False,
    'tau':                                     1,
    'use_lagged_dynamics_indoor':              True,
}

# 没给 min_soc_per_hour 时用的默认 24 小时电量下限（= DEFAULTS 里那一份 ✓）
DEFAULT_MIN_SOC_PER_HOUR = DEFAULTS['min_soc_per_hour']

# CHESCA-ResMARL 残差三项的内置默认（2026-10-08 从 CHESCA_ResMARL.py 抽到这里）
DEFAULT_RESIDUAL_ALPHA = 0.15
DEFAULT_RESIDUAL_MASK = dict(DEFAULTS['residual_action_mask'])


def _parse_min_soc_map(raw):
    # 键先**规范化**成 "0"~"23" 再校验 ✓
    normalized = {}
    for key, value in (raw or {}).items():
        text = str(key).strip().strip('"\'')
        try:
            text = str(int(float(text)))
        except Exception:
            pass
        normalized.setdefault(text, value)
    result = {}
    for hour in range(24):
        key = str(hour)
        if key not in normalized:
            raise ValueError(
                'min_soc_per_hour 缺少时间段 %d（收到的键：%s%s）'
                % (hour, sorted(normalized)[:8], '…' if len(normalized) > 8 else '')
            )
        value = float(normalized[key])
        if value < 0 or value > 1:
            raise ValueError(f'{hour}的SOC对应值应在 0~1 之间，当前: {value}')
        result[key] = value
    return result


def _parse_soc_limit(value, name):
    soc = float(value)
    if soc < 0 or soc > 1:
        raise ValueError(f'{name} 须在 0~1 之间，当前: {soc}')
    return soc


def _parse_threshold(value, name):
    threshold = float(value)
    if threshold <= 0 or threshold > 20:
        raise ValueError(f'{name} 须在0~20之间，当前: {threshold}')
    return threshold


def _parse_nonneg_float(value, name, max_value=None):
    # 非负浮点；可选上限。用于冷机保底系数等。
    number = float(value)
    if number < 0:
        raise ValueError(f'{name} 须 ≥ 0，当前: {number}')
    if max_value is not None and number > max_value:
        raise ValueError(f'{name} 须 ≤ {max_value}，当前: {number}')
    return number


def _parse_tau(value):
    tau = int(value)
    if tau not in (1, 2, 3):
        raise ValueError(f'tau 须为 1、2、3，当前: {tau}')
    return tau


def _parse_balance_type(value):
    balance_type = str(value).strip().upper()
    if balance_type not in ('A', 'B', 'C'):
        raise ValueError(f'balance_type 须为 A、B、C，当前: {balance_type}')
    return balance_type


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ('1', 'true', 'yes', 'on'):
        return True
    if s in ('0', 'false', 'no', 'off', ''):
        return False
    return default


def _parse_residual_alpha(value):
    alpha = float(value)
    if alpha < 0 or alpha > 1:
        raise ValueError(f'residual_alpha 须在 [0, 1] 之间，当前: {alpha}')
    return alpha


def _parse_mask_loosely(text):
    """兜底解析"没加引号"的掩码写法，认不出返回 None。"""
    normalized = re.sub(r'([{\[,]\s*)([A-Za-z_]\w*)\s*[:=]', r'\1"\2":', text)
    normalized = re.sub(r'("(?:key|value)"\s*:\s*)([A-Za-z_]\w*)', r'\1"\2"', normalized)
    try:
        return json.loads(normalized.replace("'", '"'))
    except Exception:
        pairs = re.findall(
            r'(dhw|ele|tmp)\s*[:=]?\s*[\s,;]*["\']?(?:value\s*[:=]\s*)?["\']?(true|false|1|0)\b',
            text, re.IGNORECASE)
        return dict(pairs) if pairs else None


def _parse_residual_mask(value):
    # 掩码支持三种写法（与 --min_soc_per_hour 同一套容错，见 _parse_min_soc_cli）：
    #   ① {"dhw": false, "ele": true, "tmp": false}   —— 配置页 / 直接传 dict
    #   ② [{"key":"ele","value":"true"}, ...]         —— 配置弹窗「键值对」控件
    #   ③ 上面两种的 JSON 字符串（Java 按字符串透传 ⇒ 实际走的是这条）
    # 只认识的键（dhw/ele/tmp）参与覆盖，其余忽略；没给过的维度保持默认。
    mask = dict(DEFAULT_RESIDUAL_MASK)
    if value is None:
        return mask
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return mask
        try:
            value = json.loads(text)
        except Exception:
            # 宽松兜底：配置页存的是 [{key:dhw,value:true}, …] 这种没给键值加引号的写法，
            # 见 _parse_mask_loosely；再认不出才报错（报错信息带上原文，便于定位）
            value = _parse_mask_loosely(text)
            if value is None:
                raise ValueError(f'无法解析 residual_action_mask 的取值: {text[:160]!r}')
    if isinstance(value, (list, tuple)):
        value = {item.get('key'): item.get('value')
                 for item in value if isinstance(item, dict) and item.get('key') is not None}
    if not isinstance(value, dict):
        return mask
    for key in ('dhw', 'ele', 'tmp'):
        if key in value:
            mask[key] = _parse_bool(value[key], mask[key])
    return mask


def _parse_marl_mode(value):
    # 解析 MARL 运行模式。
    # none         — 纯 CHESCA，不用 RL 残差
    mode = str(value).strip().lower()
    if mode == 'central_residual':
        return 'multi_agent'
    if mode not in ('none', 'multi_agent'):
        raise ValueError(f'marl_mode 须为 none / multi_agent，当前: {value}')
    return mode


def _read_agent_config_raw(config_path):
    # 只负责"把配置读成 dict"（没路径/空文件 ⇒ 空 dict ✓）；校验与默认值在下面 ✓
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f'电池 SOC 配置文件不存在: {path}')
    with path.open(encoding='utf-8') as f:
        loaded = json.load(f)
    return dict(loaded) if isinstance(loaded, dict) else {}


def load_agent_config(config_path, cli_overrides=None):
    # {
    # "min_soc_per_hour": {"0": 0.6, ...},
    # 命令行传来的配置（代码编辑器「配置」弹窗 ✓；None = 没传任何一项 ✓）
    raw = _read_agent_config_raw(config_path)
    if cli_overrides:
        raw = {**raw, **cli_overrides}
        if 'min_soc_per_hour' not in raw:
            # 只给了命令行、没有配置 JSON ⇒ 用内置默认 SOC 表补齐（否则走不到"逐项配置"那条分支 ✗）
            raw['min_soc_per_hour'] = dict(DEFAULT_MIN_SOC_PER_HOUR)
    if not raw:
        return None

    if isinstance(raw, dict) and 'min_soc_per_hour' in raw:
        min_soc = _parse_min_soc_map(raw['min_soc_per_hour'])
        max_normal = _parse_soc_limit(raw.get('max_soc_normal', 0.99), 'max_soc_normal')
        max_outage = _parse_soc_limit(raw.get('max_soc_outage', 0.87), 'max_soc_outage')
        max_soc_reduction = _parse_soc_limit(
            raw.get('max_soc_reduction_in_outage', 0.70),
            'max_soc_reduction_in_outage',
        )
        b_low = _parse_threshold(raw.get('B_low', raw.get('b_low', 1.18)), 'B_low')
        b_high = _parse_threshold(raw.get('B_high', raw.get('b_high', 1.0)), 'B_high')
        tmp_max_reduction = _parse_soc_limit(
            raw.get('TMP_max_reduction_percent', raw.get('tmp_max_reduction_percent', 0.0)),
            'TMP_max_reduction_percent',
        )
        # 冷机开环保底（可选；缺省用收紧后的默认）
        min_cool_per_c_overheat = _parse_nonneg_float(
            raw.get('min_cool_per_c_overheat', 0.12), 'min_cool_per_c_overheat', max_value=2.0
        )
        min_cool_per_c_outdoor_gap = _parse_nonneg_float(
            raw.get('min_cool_per_c_outdoor_gap', 0.03), 'min_cool_per_c_outdoor_gap', max_value=1.0
        )
        outdoor_gap_deadband_c = _parse_nonneg_float(
            raw.get('outdoor_gap_deadband_c', 5.0), 'outdoor_gap_deadband_c', max_value=30.0
        )
        outdoor_floor_max_overheat_c = _parse_nonneg_float(
            raw.get('outdoor_floor_max_overheat_c', 0.5), 'outdoor_floor_max_overheat_c', max_value=10.0
        )
        cooling_demand_feedforward_frac = _parse_nonneg_float(
            raw.get('cooling_demand_feedforward_frac', 0.10),
            'cooling_demand_feedforward_frac',
            max_value=1.0,
        )
        demand_feedforward_only_when_overheat = _parse_bool(
            raw.get('demand_feedforward_only_when_overheat', False), default=False
        )
        outdoor_floor_allow_when_under_setpoint = _parse_bool(
            raw.get('outdoor_floor_allow_when_under_setpoint', True), default=True
        )
        clear_open_loop_floor_when_under_setpoint = _parse_bool(
            raw.get('clear_open_loop_floor_when_under_setpoint', False), default=False
        )
        use_lagged_dynamics_indoor = _parse_bool(
            raw.get('use_lagged_dynamics_indoor', True), default=True
        )
        lagged_indoor_only_when_hotter = _parse_bool(
            raw.get('lagged_indoor_only_when_hotter', False), default=False
        )
        lagged_indoor_hotter_margin_c = _parse_nonneg_float(
            raw.get('lagged_indoor_hotter_margin_c', 0.3),
            'lagged_indoor_hotter_margin_c',
            max_value=10.0,
        )
        post_outage_soft_charge_enabled = _parse_bool(
            raw.get('post_outage_soft_charge_enabled', True), default=True
        )
        post_outage_relax_steps = int(raw.get('post_outage_relax_steps', 4))
        post_outage_relax_steps = max(0, min(48, post_outage_relax_steps))
        post_outage_waive_min_soc = _parse_bool(
            raw.get('post_outage_waive_min_soc', True), default=True
        )
        post_outage_max_ele_charge = _parse_soc_limit(
            raw.get('post_outage_max_ele_charge', 0.15),
            'post_outage_max_ele_charge',
        )
        post_outage_forbid_charge_when_overheat = _parse_bool(
            raw.get('post_outage_forbid_charge_when_overheat', True), default=True
        )
        post_outage_overheat_c = _parse_nonneg_float(
            raw.get('post_outage_overheat_c', 0.5),
            'post_outage_overheat_c',
            max_value=20.0,
        )
        post_outage_tmp_cap_enabled = _parse_bool(
            raw.get('post_outage_tmp_cap_enabled', True), default=True
        )
        post_outage_tmp_cap_steps = int(raw.get('post_outage_tmp_cap_steps', 4))
        post_outage_tmp_cap_steps = max(0, min(48, post_outage_tmp_cap_steps))
        post_outage_tmp_max_start = _parse_soc_limit(
            raw.get('post_outage_tmp_max_start', 0.40),
            'post_outage_tmp_max_start',
        )
        post_outage_tmp_ramp = _parse_bool(
            raw.get('post_outage_tmp_ramp', True), default=True
        )
        post_outage_tmp_stagger = _parse_bool(
            raw.get('post_outage_tmp_stagger', True), default=True
        )
        price_aware_battery_enabled = _parse_bool(
            raw.get('price_aware_battery_enabled', True), default=True
        )
        price_high_quantile = _parse_nonneg_float(
            raw.get('price_high_quantile', 0.75), 'price_high_quantile', max_value=0.99
        )
        price_low_quantile = _parse_nonneg_float(
            raw.get('price_low_quantile', 0.25), 'price_low_quantile', max_value=0.5
        )
        price_history_min_steps = int(raw.get('price_history_min_steps', 48))
        price_history_min_steps = max(8, min(720, price_history_min_steps))
        price_high_soc_threshold = _parse_soc_limit(
            raw.get('price_high_soc_threshold', 0.70), 'price_high_soc_threshold'
        )
        price_high_forbid_charge = _parse_bool(
            raw.get('price_high_forbid_charge', True), default=True
        )
        price_high_force_discharge = _parse_bool(
            raw.get('price_high_force_discharge', True), default=True
        )
        price_high_discharge_ele = _parse_soc_limit(
            raw.get('price_high_discharge_ele', 0.15), 'price_high_discharge_ele'
        )
        price_min_reserve_soc = _parse_soc_limit(
            raw.get('price_min_reserve_soc', 0.55), 'price_min_reserve_soc'
        )
        price_global_reserve_enabled = _parse_bool(
            raw.get('price_global_reserve_enabled', True), default=True
        )
        price_low_target_soc = _parse_soc_limit(
            raw.get('price_low_target_soc', 0.80), 'price_low_target_soc'
        )
        price_low_charge_ele = _parse_soc_limit(
            raw.get('price_low_charge_ele', 0.25), 'price_low_charge_ele'
        )
        price_low_search_boost = _parse_bool(
            raw.get('price_low_search_boost', True), default=True
        )
        tau = _parse_tau(raw.get('tau', 1))
        balance_type = _parse_balance_type(raw.get('balance_type', 'C'))
        resmarl_enabled = _parse_bool(raw.get('resmarl_enabled', raw.get('residual_enabled', False)))
        residual_alpha = _parse_residual_alpha(raw.get('residual_alpha', raw.get('resmarl_alpha', 0.0)))
        residual_action_mask = _parse_residual_mask(raw.get('residual_action_mask'))
        resmarl_after_safety = _parse_bool(raw.get('resmarl_after_safety', True), default=True)
        marl_mode = raw.get('marl_mode')
        if marl_mode is not None:
            marl_mode = _parse_marl_mode(marl_mode)
        multi_agent_train_epochs = int(raw.get('multi_agent_train_epochs', 20))
        multi_agent_explore = _parse_bool(raw.get('multi_agent_explore', False))
        multi_agent_checkpoint = str(raw.get('multi_agent_checkpoint') or '').strip()
        eval_schema = raw.get('eval_schema')
        eval_episode_time_steps = raw.get('eval_episode_time_steps')
        if eval_episode_time_steps is not None:
            eval_episode_time_steps = int(eval_episode_time_steps)
    else:
        min_soc = _parse_min_soc_map(raw)
        max_normal = 0.99
        max_outage = 0.87
        max_soc_reduction = 0.70
        b_low = 1.18
        b_high = 1.0
        tmp_max_reduction = 0.0
        min_cool_per_c_overheat = 0.12
        min_cool_per_c_outdoor_gap = 0.03
        outdoor_gap_deadband_c = 5.0
        outdoor_floor_max_overheat_c = 0.5
        cooling_demand_feedforward_frac = 0.10
        demand_feedforward_only_when_overheat = False
        outdoor_floor_allow_when_under_setpoint = True
        clear_open_loop_floor_when_under_setpoint = False
        use_lagged_dynamics_indoor = True
        lagged_indoor_only_when_hotter = False
        lagged_indoor_hotter_margin_c = 0.3
        post_outage_soft_charge_enabled = True
        post_outage_relax_steps = 4
        post_outage_waive_min_soc = True
        post_outage_max_ele_charge = 0.15
        post_outage_forbid_charge_when_overheat = True
        post_outage_overheat_c = 0.5
        post_outage_tmp_cap_enabled = True
        post_outage_tmp_cap_steps = 4
        post_outage_tmp_max_start = 0.40
        post_outage_tmp_ramp = True
        post_outage_tmp_stagger = True
        price_aware_battery_enabled = True
        price_high_quantile = 0.75
        price_low_quantile = 0.25
        price_history_min_steps = 48
        price_high_soc_threshold = 0.70
        price_high_forbid_charge = True
        price_high_force_discharge = True
        price_high_discharge_ele = 0.15
        price_min_reserve_soc = 0.55
        price_global_reserve_enabled = True
        price_low_target_soc = 0.80
        price_low_charge_ele = 0.25
        price_low_search_boost = True
        tau = 1
        balance_type = 'C'
        resmarl_enabled = False
        residual_alpha = 0.0
        residual_action_mask = dict(DEFAULT_RESIDUAL_MASK)
        resmarl_after_safety = True
        marl_mode = None
        multi_agent_train_epochs = 20
        multi_agent_explore = False
        multi_agent_checkpoint = ''
        eval_schema = None
        eval_episode_time_steps = None

    # 配置页里的 RL 修正字段仍写进结果，留给 CHESCA_ResMARL.py 用；
    # 直接运行本文件时，_resolve_marl_mode(cli) 会强制走纯 CHESCA（不叠加 RL）
    resolved_marl_mode = 'none'

    result = {
        'min_soc_per_hour': min_soc,
        'max_soc_normal': max_normal,
        'max_soc_outage': max_outage,
        'max_soc_reduction_in_outage': max_soc_reduction,
        'B_low': b_low,
        'B_high': b_high,
        'TMP_max_reduction_percent': tmp_max_reduction,
        'min_cool_per_c_overheat': min_cool_per_c_overheat,
        'min_cool_per_c_outdoor_gap': min_cool_per_c_outdoor_gap,
        'outdoor_gap_deadband_c': outdoor_gap_deadband_c,
        'outdoor_floor_max_overheat_c': outdoor_floor_max_overheat_c,
        'cooling_demand_feedforward_frac': cooling_demand_feedforward_frac,
        'demand_feedforward_only_when_overheat': demand_feedforward_only_when_overheat,
        'outdoor_floor_allow_when_under_setpoint': outdoor_floor_allow_when_under_setpoint,
        'clear_open_loop_floor_when_under_setpoint': clear_open_loop_floor_when_under_setpoint,
        'use_lagged_dynamics_indoor': use_lagged_dynamics_indoor,
        'lagged_indoor_only_when_hotter': lagged_indoor_only_when_hotter,
        'lagged_indoor_hotter_margin_c': lagged_indoor_hotter_margin_c,
        'post_outage_soft_charge_enabled': post_outage_soft_charge_enabled,
        'post_outage_relax_steps': post_outage_relax_steps,
        'post_outage_waive_min_soc': post_outage_waive_min_soc,
        'post_outage_max_ele_charge': post_outage_max_ele_charge,
        'post_outage_forbid_charge_when_overheat': post_outage_forbid_charge_when_overheat,
        'post_outage_overheat_c': post_outage_overheat_c,
        'post_outage_tmp_cap_enabled': post_outage_tmp_cap_enabled,
        'post_outage_tmp_cap_steps': post_outage_tmp_cap_steps,
        'post_outage_tmp_max_start': post_outage_tmp_max_start,
        'post_outage_tmp_ramp': post_outage_tmp_ramp,
        'post_outage_tmp_stagger': post_outage_tmp_stagger,
        'price_aware_battery_enabled': price_aware_battery_enabled,
        'price_high_quantile': price_high_quantile,
        'price_low_quantile': price_low_quantile,
        'price_history_min_steps': price_history_min_steps,
        'price_high_soc_threshold': price_high_soc_threshold,
        'price_high_forbid_charge': price_high_forbid_charge,
        'price_high_force_discharge': price_high_force_discharge,
        'price_high_discharge_ele': price_high_discharge_ele,
        'price_min_reserve_soc': price_min_reserve_soc,
        'price_global_reserve_enabled': price_global_reserve_enabled,
        'price_low_target_soc': price_low_target_soc,
        'price_low_charge_ele': price_low_charge_ele,
        'price_low_search_boost': price_low_search_boost,
        'tau': tau,
        'balance_type': balance_type,
        'resmarl_enabled': resmarl_enabled,
        'residual_alpha': residual_alpha,
        'residual_action_mask': residual_action_mask,
        'resmarl_after_safety': resmarl_after_safety,
        'marl_mode': resolved_marl_mode,
        'multi_agent_train_epochs': multi_agent_train_epochs,
        'multi_agent_explore': multi_agent_explore,
        'multi_agent_checkpoint': multi_agent_checkpoint,
    }
    if eval_schema:
        result['eval_schema'] = str(eval_schema).strip()
    if eval_episode_time_steps is not None:
        result['eval_episode_time_steps'] = eval_episode_time_steps
    return result


def apply_resmarl_cli_overrides(agent_config, args):
    # 将命令行残差参数覆盖到 agent_config（供 CHESCA_ResMARL / CLI 调用）。
    # 若 marl_mode 不是 multi_agent，则强制关闭残差。
    cfg = dict(agent_config or {})
    mode = getattr(args, 'marl_mode', None)
    if mode != 'multi_agent':
        cfg['resmarl_enabled'] = False
        cfg['marl_mode'] = 'none'
        cfg['residual_alpha'] = 0.0
        return cfg

    cfg['resmarl_enabled'] = True
    cfg['marl_mode'] = 'multi_agent'
    if getattr(args, 'residual_alpha', None) is not None:
        cfg['residual_alpha'] = _parse_residual_alpha(args.residual_alpha)
    if getattr(args, 'multi_agent_checkpoint', None):
        cfg['multi_agent_checkpoint'] = str(args.multi_agent_checkpoint).strip()
    if getattr(args, 'resmarl_after_safety', None) is not None:
        cfg['resmarl_after_safety'] = _parse_bool(args.resmarl_after_safety, default=True)
    if getattr(args, 'residual_action_mask', None):
        # 字符串 / dict / [{key,value}] 三种写法都由 _parse_residual_mask 统一吃下
        # （原先这里自己 json.loads，遇到配置弹窗的 [{key,value}] 形状会静默退回默认掩码）
        cfg['residual_action_mask'] = _parse_residual_mask(args.residual_action_mask)
    if getattr(args, 'multi_agent_explore', None) is not None:
        cfg['multi_agent_explore'] = _parse_bool(args.multi_agent_explore, default=False)
    return cfg


# 纯 CHESCA 入口用：命令行参数就是全部配置 ✓（默认值已在 argparse 里给好 ✓）
def build_agent_config(cli_overrides=None):
    return load_agent_config(None, cli_overrides)


# 命令行里属于框架、不属于 CHESCA 配置的参数名
_FRAMEWORK_DESTS = frozenset({
    'output_dir', 'render_session', 'min_soc_config', 'episode_time_steps', 'no_render',
    'train_task_id',
})


# 智能体认得的所有参数名，与 CHESCA.py 的 parse_args 一一对应
AGENT_PARAM_KEYS = (
    'tau',
    'min_soc_per_hour',
    'max_soc_normal',
    'max_soc_outage',
    'max_soc_reduction_in_outage',
    'B_low',
    'B_high',
    'TMP_max_reduction_percent',
    'min_cool_per_c_overheat',
    'min_cool_per_c_outdoor_gap',
    'outdoor_gap_deadband_c',
    'outdoor_floor_max_overheat_c',
    'cooling_demand_feedforward_frac',
    'demand_feedforward_only_when_overheat',
    'outdoor_floor_allow_when_under_setpoint',
    'clear_open_loop_floor_when_under_setpoint',
    'use_lagged_dynamics_indoor',
    'lagged_indoor_only_when_hotter',
    'lagged_indoor_hotter_margin_c',
    'post_outage_soft_charge_enabled',
    'post_outage_relax_steps',
    'post_outage_waive_min_soc',
    'post_outage_max_ele_charge',
    'post_outage_forbid_charge_when_overheat',
    'post_outage_overheat_c',
    'post_outage_tmp_cap_enabled',
    'post_outage_tmp_cap_steps',
    'post_outage_tmp_max_start',
    'post_outage_tmp_ramp',
    'post_outage_tmp_stagger',
    'price_aware_battery_enabled',
    'price_high_quantile',
    'price_low_quantile',
    'price_history_min_steps',
    'price_high_soc_threshold',
    'price_high_forbid_charge',
    'price_high_force_discharge',
    'price_high_discharge_ele',
    'price_min_reserve_soc',
    'price_global_reserve_enabled',
    'price_low_target_soc',
    'price_low_charge_ele',
    'price_low_search_boost',
    'balance_type',
)


# 把小时键统一成 '0' 这种写法，认不出来就原样返回
def _norm_hour_key(key):
    text = str(key).strip().strip('"\'')
    try:
        return str(int(float(text)))
    except Exception:
        return text


# 解析 --min_soc_per_hour 的取值，得到「小时 -> 电量下限」的字典
def _parse_min_soc_cli(value):
    if isinstance(value, dict):
        return {_norm_hour_key(k): v for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        out = {}
        for item in value:
            if isinstance(item, dict) and item.get('key') is not None:
                out[_norm_hour_key(item['key'])] = item.get('value')
        if not out and len(value) % 2 == 0 and all(not isinstance(x, (list, tuple, dict))
                                                   for x in value):
            # 也接受扁平写法，如 '0','0.6','1','0.65'
            for i in range(0, len(value), 2):
                out[_norm_hour_key(value[i])] = value[i + 1]
        if out:
            return out
    text = str(value).strip()
    # 先按标准 JSON 解析
    try:
        obj = json.loads(text)
    except Exception:
        obj = None
    if obj is not None:
        return _parse_min_soc_cli(obj)
    # 兼容字段名没加引号的写法，如 {key:0, value:0.6}
    pairs = re.findall(
        r'''key\s*[:=]\s*["']?(\d+(?:\.\d+)?)["']?[^}\]]{0,60}?'''
        r'''value\s*[:=]\s*["']?(\d*\.?\d+)["']?''',
        text, re.IGNORECASE)
    if pairs:
        return {_norm_hour_key(k): v for k, v in pairs}
    # 最后按 键=值 或 键:值 解析，只认数字键
    body = text.strip('{}[]() ')
    out = {}
    for part in body.replace(';', ',').split(','):
        for sep in ('=', ':'):
            if sep in part:
                key, _, val = part.partition(sep)
                key = _norm_hour_key(key)
                if re.fullmatch(r'\d+', key):
                    out[key] = val.strip().strip('"\'')
                break
    if out:
        return out
    raise ValueError(
        '无法解析 --min_soc_per_hour 的取值。期望的写法之一：'
        '{"0":0.6,…} / [{"key":"0","value":"0.6"},…] / {0=0.6,…} / {key:0, value:0.6}…；'
        '实际收到：%r' % (text[:160],)
    )


# 把命令行参数翻成「配置覆盖字典」，只有显式传了的项才会出现
def _cli_overrides_from_args(args):
    """把命令行参数翻成「配置覆盖字典」，只有显式传了的项才会出现。"""
    overrides = {}
    for key, value in vars(args).items():
        if value is None or key in _FRAMEWORK_DESTS:
            continue
        if key == 'min_soc_per_hour':
            value = _parse_min_soc_cli(value)
        overrides[key] = value
    return overrides


