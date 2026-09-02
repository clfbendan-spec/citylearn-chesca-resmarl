"""
推演剧本行 → CHESCA 源码片段映射（供 Decision Trace 悬停展示）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

_CHECA_ROOT = Path(__file__).resolve().parent.parent

# tag -> 源码位置（1-based 行号，与编辑器一致）
CODE_REF_SPECS: Dict[str, Dict[str, Any]] = {
    'step_start': {
        'file': 'checa/agent.py',
        'start': 193,
        'end': 261,
        'label': 'Agent.predict() 主流程',
    },
    'actual': {
        'file': 'checa/agent.py',
        'start': 293,
        'end': 297,
        'label': '读取本栋 net_electricity_consumption（单栋上步实际）',
    },
    'community': {
        'file': 'checa/trace_exporter.py',
        'start': 671,
        'end': 683,
        'label': '三栋净用电合计（上步实际 + 下步预测）',
    },
    'forecast': {
        'file': 'checa/forecast_agent/forecasting_agent.py',
        'start': 143,
        'end': 180,
        'label': 'ForecastAgent.compute_forecast()',
    },
    'pid_normal': {
        'file': 'checa/cooling_device_controller/cooling_device_controller.py',
        'start': 141,
        'end': 196,
        'label': 'CoolingDeviceController.find_best_action() 正常 PID',
    },
    'pid_outage': {
        'file': 'checa/cooling_device_controller/cooling_device_controller.py',
        'start': 156,
        'end': 196,
        'label': 'CoolingDeviceController.find_best_action() 停电 PID',
    },
    'outage_constraint': {
        'file': 'checa/agent.py',
        'start': 322,
        'end': 357,
        'label': '停电模式可用电力与电池/光伏平衡',
    },
    'rbc_normal': {
        'file': 'checa/agent.py',
        'start': 413,
        'end': 451,
        'label': '正常模式 DHW 规则 + 初稿动作',
    },
    'rbc_outage': {
        'file': 'checa/agent.py',
        'start': 336,
        'end': 361,
        'label': '停电模式 DHW 让路策略',
    },
    'battery_state': {
        'file': 'checa/agent.py',
        'start': 672,
        'end': 693,
        'label': 'compute_pred_battery_consumption() SOC 下限',
    },
    'initial_ele': {
        'file': 'checa/agent.py',
        'start': 434,
        'end': 436,
        'label': '正常工况电池初稿置 0',
    },
    'tree_search': {
        'file': 'checa/agent.py',
        'start': 562,
        'end': 576,
        'label': 'refine_actions_with_battery_controller() 树搜索',
        'extra': {
            'file': 'checa/battery_control_search/battery_controller.py',
            'start': 125,
            'end': 166,
            'label': 'BatteryController.search()',
        },
    },
    'tree_search_skip': {
        'file': 'checa/agent.py',
        'start': 231,
        'end': 238,
        'label': '首步跳过 Refine',
    },
    'pricing': {
        'file': 'checa/agent.py',
        'start': 280,
        'end': 286,
        'label': '读取 electricity_pricing 观测',
    },
    'refine_ele_delta': {
        'file': 'checa/agent.py',
        'start': 662,
        'end': 669,
        'label': '终稿动作 clip',
    },
    'marl_layer': {
        'file': 'checa/agent.py',
        'start': 284,
        'end': 314,
        'label': 'apply_residual_correction() MARL 残差入口',
        'extra': {
            'file': 'checa/residual/corrector.py',
            'start': 87,
            'end': 145,
            'label': 'ResidualCorrector.correct()',
        },
    },
    'residual_gen': {
        'file': 'checa/residual/corrector.py',
        'start': 53,
        'end': 120,
        'label': 'predict_delta() + mask·α 残差生成',
    },
    'safety_skip': {
        'file': 'checa/agent.py',
        'start': 231,
        'end': 238,
        'label': 'Refine 未执行',
    },
    'safety_reduce': {
        'file': 'checa/agent.py',
        'start': 603,
        'end': 618,
        'label': 'B_high 触发减负荷',
    },
    'safety_increase': {
        'file': 'checa/agent.py',
        'start': 627,
        'end': 652,
        'label': 'B_low 触发增负荷',
    },
    'safety_pass': {
        'file': 'checa/agent.py',
        'start': 577,
        'end': 601,
        'label': 'B_high/B_low 阈值计算与判定',
    },
    'consumption_breakdown': {
        'file': 'checa/agent.py',
        'start': 458,
        'end': 467,
        'label': 'compute_elec_consumption_values() 净负荷公式',
    },
    'final_exec': {
        'file': 'checa/agent.py',
        'start': 662,
        'end': 670,
        'label': '终稿动作 clip 并返回',
    },
    'action_chesca': {
        'file': 'checa/agent.py',
        'start': 248,
        'end': 274,
        'label': 'CHESCA a_base（阶段1～4 / Refine 后）',
    },
    'action_marl': {
        'file': 'multi_agent_runner_copy.py',
        'start': 251,
        'end': 273,
        'label': 'MARL 残差 α·mask·Δa',
    },
    'action_resmarl': {
        'file': 'checa/agent.py',
        'start': 299,
        'end': 330,
        'label': 'CHESCA-ResMARL a_final 合成',
    },
}

_SNIPPET_CACHE: Dict[str, str] = {}


def _read_snippet(relative_file: str, start: int, end: int, max_lines: int = 28) -> str:
    cache_key = f'{relative_file}:{start}:{end}'
    if cache_key in _SNIPPET_CACHE:
        return _SNIPPET_CACHE[cache_key]

    path = _CHECA_ROOT / Path(relative_file)
    if not path.is_file():
        snippet = f'# 源码未找到: {relative_file}'
    else:
        lines = path.read_text(encoding='utf-8').splitlines()
        s = max(1, start) - 1
        e = min(len(lines), end)
        if e - s > max_lines:
            e = s + max_lines
            truncated = True
        else:
            truncated = False
        numbered = [f'{i + 1:4d} | {lines[i]}' for i in range(s, e)]
        if truncated:
            numbered.append('     | # ...')
        snippet = '\n'.join(numbered)

    _SNIPPET_CACHE[cache_key] = snippet
    return snippet


def classify_narrative_line(text: str) -> str:
    """根据剧本行文案推断源码 tag。"""
    if text.startswith('[') and '开始计算' in text:
        return 'step_start'
    if '[本步实况]' in text:
        return 'actual'
    if '[社区负荷]' in text:
        return 'community'
    if '[预测层]' in text:
        return 'forecast'
    if '[PID层]' in text or '[制冷(TMP)]' in text:
        return 'pid_outage' if '停电' in text else 'pid_normal'
    if '[停电约束]' in text:
        return 'outage_constraint'
    if '[RBC层]' in text or '[供热(DHW)]' in text:
        return 'rbc_outage' if '停电' in text else 'rbc_normal'
    if '[电池状态]' in text:
        return 'battery_state'
    if '[初稿]' in text:
        return 'initial_ele'
    if '[树搜索层]' in text:
        return 'tree_search_skip' if '跳过' in text else 'tree_search'
    if '[电价观测]' in text:
        return 'pricing'
    if '[Refine 微调]' in text:
        return 'refine_ele_delta'
    if '[MARL层' in text:
        return 'marl_layer'
    if '[残差生成]' in text:
        return 'residual_gen'
    if '[安全审查]' in text:
        if '未执行社区 Refine' in text:
            return 'safety_skip'
        if '设备分解' in text:
            return 'consumption_breakdown'
        if '超过 B_high' in text:
            return 'safety_reduce'
        if '低于 B_low' in text:
            return 'safety_increase'
        return 'safety_pass'
    if text.startswith('> 最终执行') or '最终执行' in text:
        return 'final_exec'
    if '[CHESCA-RESMARL动作]' in text:
        return 'action_resmarl'
    if '[CHESCA动作]' in text:
        return 'action_chesca'
    if '[MARL动作]' in text:
        return 'action_marl'
    return 'step_start'


def build_code_ref(tag: str, include_snippet: bool = True) -> Dict[str, Any]:
    """
    按 tag 生成源码引用元数据。

    include_snippet=False 时不读盘、不嵌入 code_snippet（Decision Trace 瘦身导出用；
    前端用 code_tag / 文案在本地 CODE_REF_META 中补全片段）。
    """
    spec = CODE_REF_SPECS.get(tag, CODE_REF_SPECS['step_start'])
    ref: Dict[str, Any] = {
        'code_tag': tag,
        'source_file': spec['file'],
        'source_line_start': spec['start'],
        'source_line_end': spec['end'],
        'source_label': spec.get('label', tag),
    }
    if include_snippet:
        snippet = _read_snippet(spec['file'], spec['start'], spec['end'])
        extra = spec.get('extra')
        if extra:
            snippet += '\n\n# --- ' + extra['label'] + ' ---\n'
            snippet += _read_snippet(extra['file'], extra['start'], extra['end'], max_lines=18)
        ref['code_snippet'] = snippet
    return ref


def build_narrative_entries(
    lines: List[str],
    include_snippet: bool = False,
) -> List[Dict[str, Any]]:
    """
    剧本行 → 带源码引用的 entries。

    默认 include_snippet=False（瘦身）：只写 text + code_tag + 行列元数据，
    不嵌入重复的 code_snippet。仪表盘悬停时由前端本地补全。
    """
    entries: List[Dict[str, Any]] = []
    for text in lines:
        tag = classify_narrative_line(text)
        entry = {'text': text, **build_code_ref(tag, include_snippet=include_snippet)}
        entries.append(entry)
    return entries
