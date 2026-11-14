"""Identity-free AAC-derived experiment; fixed 2023 local, no capacity/ID inputs.

Independent from installed AAC. Joint replay, shared actor/attention critic,
correct action-head indexing and one optimizer step for the shared actor.
All measured features use current/previous completed readings, never simulator
thermal states, ideal load or name-indexed preprocessing.
"""
import argparse
import copy
import csv
import gzip
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

# Evaluations launch this file in a fresh interpreter from a task directory.
# The shared recorder lives one directory above, outside Python's script path.
_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
if str(_PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_ROOT))

import numpy as np
from assessment_trace import settled_energy
from evaluation_contract import capture_context, collect_environment_metrics
from aacmadrl.control_profiles import HISTORICAL_PROFILE, configure_profile
import torch
from torch import nn
from torch.nn import functional as F

try:
    import train_remote_2023_short as legacy
except ModuleNotFoundError as error:
    if error.name != 'citylearn.agents.aac_madrl':
        raise
    legacy = None

VERSION = 'shared_history_aac_v5_separate_objective_critic'
COMPATIBLE_VERSIONS = (
    'shared_history_aac_v1',
    'shared_history_aac_v2',
    'shared_history_aac_v3_thermal_potential',
    'shared_history_aac_v4_actor_architecture',
    VERSION,
)
CLASSES = (21, 21, 11)
ACTION_NAMES = ('dhw_storage', 'electrical_storage', 'cooling_device')
FEATURE_NAMES = ('hour_sin', 'hour_cos', 'day_sin', 'day_cos', 'outdoor_temperature',
                 'temperature', 'cold_margin', 'hot_margin', 'occupied',
                 'non_shiftable_load', 'solar_generation', 'net_electricity',
                 'electricity_price', 'dhw_soc', 'battery_soc', 'outage',
                 'cooling_meter', 'dhw_meter', 'cooling_setpoint',
                 'heating_setpoint', 'comfort_band')
HISTORY_NAMES = ('temperature_before', 'temperature_after', 'dhw_command',
                 'battery_command', 'cooling_command', 'cooling_meter_after', 'valid')


def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.05 * (attempt + 1))


def normalize_undefined_resilience_kpis(result, outage_steps, occupied_outage_steps=None):
    """Export confirmed zero-denominator resilience ratios as null, never zero."""
    occupied_outage_steps = outage_steps if occupied_outage_steps is None else occupied_outage_steps
    allowed = {'power_outage_normalized_unserved_energy_total',
               'one_minus_thermal_resilience_proportion'}
    missing = []
    for building, metrics in result['per_building'].items():
        for name in allowed:
            counts = occupied_outage_steps if name == 'one_minus_thermal_resilience_proportion' else outage_steps
            if name in metrics and not math.isfinite(metrics[name]) and counts[building] == 0:
                metrics[name] = None
                missing.append(f'per_building.{building}.{name}')
    for row in result['official_kpi']:
        counts = occupied_outage_steps if row['cost_function'] == 'one_minus_thermal_resilience_proportion' else outage_steps
        count = (sum(counts.values()) if row['level'] == 'district'
                 else counts.get(row['name']))
        if row['cost_function'] in allowed and not math.isfinite(row['value']) and count == 0:
            row['value'] = None
            missing.append(f'official_kpi.{row["name"]}.{row["cost_function"]}')
    if missing:
        result['undefined_kpis'] = dict(
            reason='Native resilience ratio has no eligible outage samples (thermal resilience requires occupied outage samples)',
            json_value=None, fields=missing, outage_steps_by_building=outage_steps,
            occupied_outage_steps_by_building=occupied_outage_steps)
    return result


def make_env(start_time_step=0, end_time_step=719, seed=41):
    if legacy is None:
        raise RuntimeError(
            'The Phase 2 CityLearn custom agent package is unavailable in this environment'
        )
    legacy.REWARD_MODE = legacy.KPIAlignedComfortCostReward.version
    return legacy.make_env(start_time_step, end_time_step, seed)


def readings(env):
    # Physical meters exposed by observations; no capacity, ideal demand or LSTM data.
    return [b.observations(include_all=True, normalize=False,
                           periodic_normalization=False) for b in env.buildings]


def thermal_potential(obs):
    """Occupied thermal distance outside the active comfort band."""
    values = []
    for o in obs:
        temp = float(o['indoor_dry_bulb_temperature'])
        cool = float(o['indoor_dry_bulb_temperature_cooling_set_point'])
        heat = float(o['indoor_dry_bulb_temperature_heating_set_point'])
        band = float(o['comfort_band'])
        occupied = float(o['occupant_count']) > 0.0
        hot = max(temp - cool - band, 0.0)
        cold = max(heat - band - temp, 0.0)
        values.append(((hot + cold) / 10.0)
                      if occupied else 0.0)
    return np.asarray(values, dtype=np.float32)


def occupied_hot_margin_potential(obs, margin=1.0):
    """Occupied hot-risk distance, including a buffer inside the comfort band."""
    if not np.isfinite(margin) or margin < 0.0:
        raise ValueError('Hot-risk margin must be finite and non-negative')
    values = []
    for o in obs:
        temp = float(o['indoor_dry_bulb_temperature'])
        cool = float(o['indoor_dry_bulb_temperature_cooling_set_point'])
        band = float(o['comfort_band'])
        occupied = float(o['occupant_count']) > 0.0
        hot_risk = max(temp - (cool + band - margin), 0.0)
        values.append(hot_risk / 10.0 if occupied else 0.0)
    return np.asarray(values, dtype=np.float32)


def symmetric_plus_hot_margin_potential(obs, hot_weight=0.25, margin=1.0):
    """Keep symmetric comfort shaping and add a weaker occupied hot buffer."""
    if not np.isfinite(hot_weight) or hot_weight < 0.0:
        raise ValueError('Hot-risk weight must be finite and non-negative')
    return (
        thermal_potential(obs)
        + hot_weight * occupied_hot_margin_potential(obs, margin=margin)
    ).astype(np.float32)


def comfort_boundary_risk(obs, margin=1.0):
    """Occupied distance into a one-degree buffer inside the comfort limits."""
    values = []
    for o in obs:
        temp = float(o['indoor_dry_bulb_temperature'])
        band = float(o['comfort_band'])
        hot = max(temp - (float(o['indoor_dry_bulb_temperature_cooling_set_point'])
                          + band - margin), 0.0)
        cold = max((float(o['indoor_dry_bulb_temperature_heating_set_point'])
                    - band + margin) - temp, 0.0)
        values.append((hot + cold) / 10.0 if float(o['occupant_count']) > 0.0 else 0.0)
    return np.asarray(values, dtype=np.float32)


def boundary_risk_penalty(obs, weight, margin=1.0):
    """Return a non-negative cost component for occupied boundary risk."""
    return float(weight) * comfort_boundary_risk(obs, margin=margin)


def storage_reversal_penalty(actions, prices, previous_actions, previous_prices,
                             weight, epsilon=1.e-8):
    """Return a non-negative cost for reversals unless current price improves.

    CityLearn storage actions are positive for charge and negative for discharge.
    The returned per-building reward is non-positive and only applies to a
    reversal at an equal or less favorable price than the preceding action.
    """
    actions = np.asarray(actions, dtype=float)
    previous_actions = np.asarray(previous_actions, dtype=float)
    prices = np.asarray(prices, dtype=float).reshape(-1)
    previous_prices = np.asarray(previous_prices, dtype=float).reshape(-1)
    if (actions.ndim != 2 or actions.shape[1] != 2
            or previous_actions.shape != actions.shape
            or prices.shape != (len(actions),)
            or previous_prices.shape != prices.shape):
        raise ValueError('Storage reversal inputs must align by building and device')
    penalty = np.zeros(len(actions), dtype=np.float32)
    if weight <= 0.:
        return penalty
    for device in range(2):
        previous = previous_actions[:, device]
        current = actions[:, device]
        charge_then_discharge = (
            (previous > epsilon) & (current < -epsilon)
            & (prices <= previous_prices + epsilon)
        )
        discharge_then_charge = (
            (previous < -epsilon) & (current > epsilon)
            & (prices >= previous_prices - epsilon)
        )
        reversal_amount = np.minimum(np.abs(previous), np.abs(current))
        penalty += (float(weight) * reversal_amount
                    * (charge_then_discharge | discharge_then_charge))
    return penalty


def common_grids(env):
    names = [tuple(b.active_actions) for b in env.buildings]
    if any(n != ACTION_NAMES for n in names):
        raise ValueError('This registered pilot requires the same three device types')
    lo = np.max(np.asarray([s.low for s in env.action_space]), axis=0)
    hi = np.min(np.asarray([s.high for s in env.action_space]), axis=0)
    if not np.all(lo < hi):
        raise ValueError('No shared legal action interval')
    grids = []
    for lower, upper, count in zip(lo, hi, CLASSES):
        if lower < 0 < upper:
            half = (count-1)//2
            g = np.r_[np.linspace(float(lower), 0., half+1),
                      np.linspace(0., float(upper), count-half)[1:]]
        else:
            g = np.linspace(float(lower), float(upper), count)
        grids.append(g.astype(np.float32))
    return grids


def checkpoint_grids(env, saved_grids):
    """Reuse checkpoint categorical values when runtime physical bounds allow them."""
    if not isinstance(saved_grids, (list, tuple)) or len(saved_grids) != len(ACTION_NAMES):
        raise ValueError('Checkpoint action grid shape is invalid')
    grids = []
    for index, values in enumerate(saved_grids):
        grid = np.asarray(values, dtype=np.float32).reshape(-1)
        if grid.size < 2 or not np.isfinite(grid).all() or np.any(np.diff(grid) <= 0):
            raise ValueError(f'Checkpoint action grid {ACTION_NAMES[index]} is invalid')
        low = max(float(space.low[index]) for space in env.action_space)
        high = min(float(space.high[index]) for space in env.action_space)
        if np.any(grid < low - 1e-6) or np.any(grid > high + 1e-6):
            raise ValueError(f'Checkpoint action grid {ACTION_NAMES[index]} exceeds runtime legal bounds')
        grids.append(grid)
    return grids


class FeatureHistory:
    # 把每栋楼的物理读数整理成网络输入，不负责预测环境下一状态。
    # n=楼栋数；默认每楼21维当前特征+4段*7维已发生历史，共49维。
    # 温度/40、负荷/10等只是数值缩放，不是改变物理单位或设备容量。
    # 缺少的历史填0且valid=0；advance后才会写入这一步真实执行的转移。
    def __init__(self, n, history_steps=4, history_enabled=True, dilation=1):
        if history_steps < 1 or dilation < 1:
            raise ValueError('History steps and dilation must be positive')
        self.n = n; self.k = history_steps; self.enabled = history_enabled
        self.dilation = int(dilation)
        self.span = 1 + (self.k - 1) * self.dilation
        self.reset()

    def reset(self):
        self.history = [deque(maxlen=self.span) for _ in range(self.n)]

    def encode(self, obs):
        # 输入obs是按楼排列的字典列表；输出形状为[楼栋数, 特征数]的float32。
        # 小时用sin/cos表示，使23点与0点在特征空间中相邻，而不是相距23。
        output = []
        for i, o in enumerate(obs):
            temp = float(o['indoor_dry_bulb_temperature'])
            hsp = float(o['indoor_dry_bulb_temperature_heating_set_point'])
            csp = float(o['indoor_dry_bulb_temperature_cooling_set_point'])
            band = float(o['comfort_band'])
            hour = float(o['hour']); day = float(o['day_type'])
            current = [math.sin(2*math.pi*hour/24), math.cos(2*math.pi*hour/24),
                       math.sin(2*math.pi*day/8), math.cos(2*math.pi*day/8),
                       float(o['outdoor_dry_bulb_temperature'])/40, temp/40,
                       (temp-hsp+band)/10, (csp+band-temp)/10,
                       float(float(o['occupant_count']) > 0),
                       float(o['non_shiftable_load'])/10,
                       float(o['solar_generation'])/10,
                       float(o['net_electricity_consumption'])/10,
                       float(o['electricity_pricing'])*10,
                       float(o['dhw_storage_soc']), float(o['electrical_storage_soc']),
                       float(o['power_outage']),
                       float(o['cooling_electricity_consumption'])/10,
                       float(o['dhw_electricity_consumption'])/10,
                       csp/40, hsp/40, band/10]
            hist = list(self.history[i]) if self.enabled else []
            sampled = []
            for slot in range(self.k):
                index = len(hist) - 1 - (self.k - 1 - slot) * self.dilation
                sampled.append(
                    hist[index] if index >= 0
                    else [0.] * len(HISTORY_NAMES))
            padded = (sampled if self.enabled else
                      [[0.] * len(HISTORY_NAMES)] * self.k)
            output.append(current + [v for row in padded for v in row])
        result = np.asarray(output, dtype=np.float32)
        if not np.isfinite(result).all():
            raise ValueError('Non-finite measured features')
        return result

    def advance(self, before, actions, after):
        # 必须在env.step之后调用：before/after是真实前后读数，actions是执行命令。
        # encode当前状态时不会提前看到这一步尚未发生的after。
        for i in range(self.n):
            self.history[i].append([
                float(before[i]['indoor_dry_bulb_temperature'])/40,
                float(after[i]['indoor_dry_bulb_temperature'])/40,
                *[float(x) for x in actions[i]],
                float(after[i]['cooling_electricity_consumption'])/10, 1.])


class SharedActor(nn.Module):
    # Actor是“提动作的网络”。所有楼共用权重，但读数不同可以得到不同动作。
    # 末层是三个动作头的分数，不是直接输出三个设备的物理功率。
    def __init__(self, dim):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim, 64), nn.LeakyReLU(),
                                 nn.Linear(64, 64), nn.LeakyReLU(),
                                 nn.Linear(64, sum(CLASSES)))

    def forward(self, x):
        return self.net(x)

    def sample(self, x, deterministic=False):
        # 每个头先softmax得到档位概率。训练通常按概率采样，固定评估取最大概率档。
        # indices是档位下标，onehot供Critic读动作，logs供策略损失使用。
        # 真正传给CityLearn的连续命令还要通过Learner.actions中的grids查表。
        splits = self(x).split(CLASSES, dim=-1)
        probs = [F.softmax(v, dim=-1) for v in splits]
        if deterministic:
            indices = torch.stack([p.argmax(dim=-1) for p in probs], dim=-1)
        else:
            indices = torch.stack([torch.distributions.Categorical(probs=p).sample()
                                   for p in probs], dim=-1)
        logs = torch.stack([F.log_softmax(v, dim=-1).gather(
            -1, indices[..., h:h+1]).squeeze(-1) for h, v in enumerate(splits)], dim=-1)
        onehot = torch.cat([F.one_hot(indices[..., h], n) for h, n in
                            enumerate(CLASSES)], dim=-1).float()
        return indices, onehot, logs, probs


class FrozenCoolingActor(nn.Module):
    """Train storage on actual history while an immutable full actor controls cooling."""
    def __init__(self, actor):
        super().__init__()
        self.trainable_actor = actor
        self.cooling_teacher = copy.deepcopy(actor).eval()
        for parameter in self.cooling_teacher.parameters():
            parameter.requires_grad_(False)

    def forward(self, x):
        logits = self.trainable_actor(x)
        with torch.no_grad():
            cooling = self.cooling_teacher(x)[..., -CLASSES[2]:]
        return torch.cat((logits[..., :sum(CLASSES[:2])], cooling), dim=-1)

    def sample(self, x, deterministic=False):
        splits = self(x).split(CLASSES, dim=-1)
        probs = [F.softmax(v, dim=-1) for v in splits]
        indices = torch.stack([
            p.argmax(-1) if deterministic or h == 2 else
            torch.distributions.Categorical(probs=p).sample()
            for h, p in enumerate(probs)
        ], dim=-1)
        # Cooling is a deterministic policy, not a sampled trainable distribution.
        probs[2] = F.one_hot(indices[..., 2], CLASSES[2]).to(x.dtype)
        logs = torch.stack([
            F.log_softmax(v, dim=-1).gather(-1, indices[..., h:h+1]).squeeze(-1)
            if h != 2 else torch.zeros_like(indices[..., 2], dtype=x.dtype)
            for h, v in enumerate(splits)
        ], dim=-1)
        onehot = torch.cat([F.one_hot(indices[..., h], n)
                            for h, n in enumerate(CLASSES)], -1).float()
        return indices, onehot, logs, probs


class BuildingHeadActor(nn.Module):
    """Shared per-building encoder with a separate action head per building."""
    def __init__(self, dim, building_count=3):
        super().__init__()
        if int(building_count) < 1:
            raise ValueError('Building count must be positive')
        self.building_count = int(building_count)
        self.encoder = nn.Sequential(nn.Linear(dim, 64), nn.LeakyReLU(),
                                     nn.Linear(64, 64), nn.LeakyReLU())
        self.heads = nn.ModuleList(
            nn.Linear(64, sum(CLASSES)) for _ in range(self.building_count)
        )

    def initialize_from_shared_actor(self, state_dict):
        required = ('net.0.weight', 'net.0.bias', 'net.2.weight',
                    'net.2.bias', 'net.4.weight', 'net.4.bias')
        if any(name not in state_dict for name in required):
            raise ValueError('Shared actor checkpoint is missing expected layers')
        own = self.state_dict()
        mapping = {
            'encoder.0.weight': 'net.0.weight',
            'encoder.0.bias': 'net.0.bias',
            'encoder.2.weight': 'net.2.weight',
            'encoder.2.bias': 'net.2.bias',
        }
        for target, source in mapping.items():
            if own[target].shape != state_dict[source].shape:
                raise ValueError(f'Incompatible shared actor layer: {source}')
            own[target] = state_dict[source].detach().clone()
        for index in range(self.building_count):
            for parameter in ('weight', 'bias'):
                target = f'heads.{index}.{parameter}'
                source = f'net.4.{parameter}'
                if own[target].shape != state_dict[source].shape:
                    raise ValueError(f'Incompatible shared actor output: {source}')
                own[target] = state_dict[source].detach().clone()
        self.load_state_dict(own, strict=True)

    def forward(self, x):
        encoded = self.encoder(x)
        if x.ndim == 2:
            if x.shape[0] != self.building_count:
                raise ValueError(
                    f'Expected {self.building_count} buildings, got {x.shape[0]}'
                )
            return torch.stack([head(encoded[i]) for i, head in enumerate(self.heads)], dim=0)
        if x.ndim != 3 or x.shape[1] != self.building_count:
            raise ValueError(
                f'Expected batched observations for {self.building_count} buildings'
            )
        return torch.stack([head(encoded[:, i]) for i, head in enumerate(self.heads)], dim=1)

    def sample(self, x, deterministic=False):
        splits = self(x).split(CLASSES, dim=-1)
        probs = [F.softmax(v, dim=-1) for v in splits]
        if deterministic:
            indices = torch.stack([p.argmax(dim=-1) for p in probs], dim=-1)
        else:
            indices = torch.stack([torch.distributions.Categorical(probs=p).sample()
                                   for p in probs], dim=-1)
        logs = torch.stack([F.log_softmax(v, dim=-1).gather(
            -1, indices[..., h:h+1]).squeeze(-1) for h, v in enumerate(splits)], dim=-1)
        onehot = torch.cat([F.one_hot(indices[..., h], n) for h, n in
                            enumerate(CLASSES)], dim=-1).float()
        return indices, onehot, logs, probs


class SharedAttentionCritic(nn.Module):
    # Critic是“训练时评价动作的网络”，不是负责预测明天气温的物理模型。
    # 输入states=[batch,楼,特征]，actions=[batch,楼,各动作头onehot拼接]。
    # 每楼用query与其它楼的key计算相关程度，再加权汇总它们的value作为社区上下文。
    # 输出各楼各动作档位的Q估计；Q是带折扣的长期训练收益估计，不是最终现金账单。
    def __init__(self, dim):
        super().__init__()
        self.state = nn.Sequential(nn.Linear(dim, 64), nn.LeakyReLU())
        self.state_action = nn.Sequential(nn.Linear(dim+sum(CLASSES), 64), nn.LeakyReLU())
        self.query = nn.Linear(64, 64, bias=False)
        self.key = nn.Linear(64, 64, bias=False)
        self.value = nn.Sequential(nn.Linear(64, 64, bias=False), nn.LeakyReLU())
        self.head = nn.Sequential(nn.Linear(128, 64), nn.LeakyReLU(),
                                  nn.Linear(64, sum(CLASSES)))

    def forward(self, states, actions):
        own = self.state(states)
        others = self.state_action(torch.cat([states, actions], dim=-1))
        score = self.query(own) @ self.key(others).transpose(1, 2) / 8.
        diagonal = torch.eye(states.shape[1], dtype=torch.bool, device=states.device)
        # 屏蔽自己的注意力位置：本楼信息已有own分支，上下文主要汇总其它楼。
        weight = score.masked_fill(diagonal.unsqueeze(0), -1.e9).softmax(dim=-1)
        context = weight @ self.value(others)
        return self.head(torch.cat([own, context], dim=-1))


class SeparateObjectiveSharedAttentionCritic(nn.Module):
    """Shared state-action encoder with independently weighted objective heads."""
    # 可选分目标版本：共用编码器，分别估计费用、舒适、整形等价值。
    # 目的在于保留目标分解，随后按训练权重组合；不等于模型优选评分的逐栋分解。
    def __init__(self, dim, objective_count=3, own_action_context='none'):
        super().__init__()
        if int(objective_count) < 1:
            raise ValueError('objective_count must be positive')
        self.objective_count = int(objective_count)
        if own_action_context not in ('none', 'other_heads'):
            raise ValueError('Unknown own-action context')
        self.own_action_context = own_action_context
        self.state = nn.Sequential(nn.Linear(dim, 64), nn.LeakyReLU())
        self.state_action = nn.Sequential(nn.Linear(dim+sum(CLASSES), 64), nn.LeakyReLU())
        self.query = nn.Linear(64, 64, bias=False)
        self.key = nn.Linear(64, 64, bias=False)
        self.value = nn.Sequential(nn.Linear(64, 64, bias=False), nn.LeakyReLU())
        self.head_trunk = nn.Sequential(nn.Linear(128, 64), nn.LeakyReLU())
        self.objective_heads = nn.ModuleList(
            nn.Linear(64, sum(CLASSES)) for _ in range(self.objective_count)
        )
        if own_action_context == 'other_heads':
            # Preserve paired-run RNG streams and exact original initial outputs.
            rng_state = torch.get_rng_state()
            self.own_action_residuals = nn.ModuleList([
                nn.Sequential(nn.Linear(64 + sum(CLASSES), 32), nn.LeakyReLU(),
                              nn.Linear(32, count))
                for _ in range(self.objective_count) for count in CLASSES
            ])
            for branch in self.own_action_residuals:
                nn.init.zeros_(branch[-1].weight)
                nn.init.zeros_(branch[-1].bias)
            torch.set_rng_state(rng_state)

    def forward(self, states, actions):
        own = self.state(states)
        others = self.state_action(torch.cat([states, actions], dim=-1))
        score = self.query(own) @ self.key(others).transpose(1, 2) / 8.
        diagonal = torch.eye(states.shape[1], dtype=torch.bool, device=states.device)
        weight = score.masked_fill(diagonal.unsqueeze(0), -1.e9).softmax(dim=-1)
        context = weight @ self.value(others)
        encoded = self.head_trunk(torch.cat([own, context], dim=-1))
        base = torch.cat([head(encoded) for head in self.objective_heads], dim=-1)
        if self.own_action_context == 'none':
            return base
        corrections = []
        for objective in range(self.objective_count):
            offset = 0
            for head, count in enumerate(CLASSES):
                mask = torch.ones(sum(CLASSES), dtype=actions.dtype, device=actions.device)
                mask[offset:offset + count] = 0
                context = torch.cat([encoded, actions * mask], dim=-1)
                corrections.append(self.own_action_residuals[objective * 3 + head](context))
                offset += count
        return base + torch.cat(corrections, dim=-1)

    def load_compatible_state_dict(self, state_dict):
        """Only allow missing zero-initialized residuals when upgrading a base critic."""
        expected = self.state_dict()
        missing = set(expected) - set(state_dict)
        unexpected = set(state_dict) - set(expected)
        if unexpected or any(not key.startswith('own_action_residuals.') for key in missing):
            raise ValueError('Incompatible critic keys')
        self.load_state_dict({**expected, **state_dict})

    def initialize_from_scalarized(self, state_dict):
        own = self.state_dict()
        for name, value in state_dict.items():
            if name.startswith('head.'):
                continue
            if name in own and own[name].shape == value.shape:
                own[name] = value
        for index in range(len(self.objective_heads)):
            own[f'objective_heads.{index}.weight'] = torch.zeros_like(
                own[f'objective_heads.{index}.weight'])
            own[f'objective_heads.{index}.bias'] = torch.zeros_like(
                own[f'objective_heads.{index}.bias'])
        own['head_trunk.0.weight'] = state_dict['head.0.weight']
        own['head_trunk.0.bias'] = state_dict['head.0.bias']
        self.load_state_dict(own)


def branch_values(all_q, indices):
    # Split BEFORE gathering; head 1/2 indices cannot address head 0.
    return torch.stack([q.gather(-1, indices[..., h:h+1]).squeeze(-1)
                        for h, q in enumerate(all_q.split(CLASSES, dim=-1))], dim=-1)


def branch_values_multi(all_q, indices):
    width = sum(CLASSES)
    count = all_q.shape[-1] // width
    if all_q.shape[-1] % width:
        raise ValueError('Objective critic output is not action-grid aligned')
    values = [branch_values(all_q[..., i*width:(i+1)*width], indices)
              for i in range(count)]
    return torch.stack(values, dim=-1)


def weighted_reward(components, cost_weights, discomfort_weights):
    return -10. * (components[..., 0] * cost_weights
                   + components[..., 1] * discomfort_weights
                   + components[..., 2])


class JointReplay:
    # 经验回放是“已经发生的联合转移记事本”：一条记录同时含所有楼，而非单楼碎片。
    # state/nxt形状[楼,特征]，indices形状[楼,3]，components含费用/舒适/整形项。
    # 环形覆盖限制内存；抽一批旧经验学习，不代表让环境重新执行那些动作。
    def __init__(self, capacity=100000):
        self.capacity = capacity; self.rows = []; self.position = 0

    def push(self, state, indices, components, nxt, done, episode, step, n_steps=1):
        row = (state.copy(), indices.copy(), components.copy(), nxt.copy(),
               bool(done), int(episode), int(step), int(n_steps))
        if len(self.rows) < self.capacity:
            self.rows.append(row)
        else:
            self.rows[self.position] = row
        self.position = (self.position+1) % self.capacity

    def sample(self, batch):
        ids = random.sample(range(len(self.rows)), batch)
        rows = [self.rows[i] for i in ids]
        return tuple(np.stack(v) for v in zip(*rows)), ids

    def battery_balanced_probabilities(self):
        """Half uniform, half uniform-building/uniform-present-battery-bin."""
        count = len(self.rows)
        if not count:
            raise ValueError('Cannot sample an empty replay')
        bins = np.stack([row[1][:, 1] for row in self.rows])
        probability = np.full(count, .5 / count, dtype=np.float64)
        for building in range(bins.shape[1]):
            _, inverse, counts = np.unique(bins[:, building], return_inverse=True, return_counts=True)
            probability += .5 / bins.shape[1] / len(counts) / counts[inverse]
        return probability


class NStepAccumulator:
    # 可选n步回报：把连续几步奖励分量按discount折扣后相加，再交给回放池。
    # 回合结束要flush尾部，不能把下一回合的状态接到上一回合的经验后面。
    def __init__(self, n_step, discount):
        if int(n_step) < 1:
            raise ValueError('n_step must be positive')
        self.n_step = int(n_step)
        self.discount = float(discount)
        self.rows = deque()

    def reset(self):
        self.rows.clear()

    def append(self, state, indices, components, nxt, done, episode, step,
               episode_end=None):
        self.rows.append((state.copy(), indices.copy(), components.copy(),
                          nxt.copy(), bool(done), int(episode), int(step)))
        ready = []
        if len(self.rows) >= self.n_step:
            ready.append(self._emit(self.n_step))
        if done or (episode_end is not None and episode_end):
            ready.extend(self.flush())
        return ready

    def flush(self):
        ready = []
        while self.rows:
            ready.append(self._emit(len(self.rows)))
        return ready

    def _emit(self, count):
        rows = list(self.rows)[:count]
        state, indices = rows[0][0], rows[0][1]
        components = sum((self.discount ** i) * row[2]
                         for i, row in enumerate(rows))
        nxt, done = rows[-1][3], rows[-1][4]
        episode, step = rows[0][5], rows[0][6]
        self.rows.popleft()
        return state, indices, components.astype(np.float32), nxt, done, episode, step, count


class Learner:
    # Learner持有Actor、Critic、它们的慢更新副本、优化器和回放池。
    # actions()只产生动作；update()才通过梯度改变权重，二者不能混为一谈。
    def __init__(self, dim, grids, actor_lr=1.e-3, entropy_penalty=0.0,
                 critic_lr=1.e-3, discount=.99, tau=.005, reward_scale=10.,
                 behavior_kl_penalty=0.0, actor_architecture='shared',
                 critic_objective='scalarized', actor_building_count=3,
                 split_thermal_discomfort=False, batch_size=256,
                 freeze_actor_updates=False, critic_own_action_context='none',
                 target_action_policy='categorical', critic_replay_sampling='uniform',
                 critic_replay_seed=0):
        if actor_architecture not in ('shared', 'building_heads'):
            raise ValueError(f'Unknown actor architecture: {actor_architecture}')
        if critic_objective not in ('scalarized', 'separate'):
            raise ValueError(f'Unknown critic objective: {critic_objective}')
        if critic_own_action_context != 'none' and critic_objective != 'separate':
            raise ValueError('Own-action context requires separate critic')
        if target_action_policy not in ('categorical', 'greedy'):
            raise ValueError(f'Unknown target action policy: {target_action_policy}')
        self.target_action_policy = target_action_policy
        if critic_replay_sampling not in ('uniform', 'battery_balanced_is'):
            raise ValueError(f'Unknown critic replay sampling: {critic_replay_sampling}')
        self.critic_replay_sampling = critic_replay_sampling
        self.critic_replay_rng = np.random.default_rng(critic_replay_seed)
        actor_type = SharedActor if actor_architecture == 'shared' else BuildingHeadActor
        self.actor_architecture = actor_architecture
        self.actor_building_count = (
            3 if actor_architecture == 'shared' else int(actor_building_count)
        )
        critic_type = (SharedAttentionCritic if critic_objective == 'scalarized'
                       else SeparateObjectiveSharedAttentionCritic)
        self.critic_objective = critic_objective
        self.split_thermal_discomfort = bool(split_thermal_discomfort)
        self.objective_count = (
            4 if critic_objective == 'separate' and self.split_thermal_discomfort
            else 3 if critic_objective == 'separate' else 1
        )
        self.actor = (
            actor_type(dim) if actor_architecture == 'shared'
            else actor_type(dim, self.actor_building_count)
        )
        self.critic = (
            critic_type(dim, objective_count=self.objective_count,
                        own_action_context=critic_own_action_context)
            if critic_objective == 'separate'
            else critic_type(dim)
        )
        self.target_actor = copy.deepcopy(self.actor); self.target_critic = copy.deepcopy(self.critic)
        self.actor_opt = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(), lr=critic_lr, weight_decay=1.e-3)
        self.grids = grids; self.replay = JointReplay(); self.updates = 0
        self.last_losses = {}; self.discount = float(discount); self.tau = float(tau)
        self.reward_scale = float(reward_scale)
        self.diagnostics_interval = 0
        self.last_update_diagnostics = {}
        self.entropy_penalty = float(entropy_penalty)
        self.behavior_kl_penalty = float(behavior_kl_penalty)
        self.freeze_actor_updates = bool(freeze_actor_updates)
        self.reference_actor = None
        self.cost_weights = np.ones(3, dtype=np.float32)
        self.discomfort_weights = np.ones(3, dtype=np.float32)
        self.hot_discomfort_weights = np.ones(3, dtype=np.float32)
        self.cold_discomfort_weights = np.ones(3, dtype=np.float32)
        self.actor_cost_objective_scale = 1.0
        self.batch_size = int(batch_size)
        if self.batch_size < 1:
            raise ValueError('Batch size must be positive')
        self.fixed_cooling_schedule = None
        self.battery_post_soc_floor = None
        self.battery_post_soc_floor_building_index = None
        self.battery_storage_devices = None

    def fixed_cooling_ids(self, indices, time_indices):
        """Apply the logged per-step cooling sequence to a batch of action ids."""
        if self.fixed_cooling_schedule is None:
            return indices
        time_indices = np.clip(
            np.asarray(time_indices, dtype=np.int64),
            0, len(self.fixed_cooling_schedule) - 1)
        fixed = torch.as_tensor(
            self.fixed_cooling_schedule[time_indices],
            dtype=torch.long, device=indices.device)
        result = indices.clone()
        result[..., 2] = fixed
        return result

    def configure_battery_post_soc_floor(self, floor, building_index,
                                         storage_devices):
        if floor is None:
            return
        if not 0. <= float(floor) <= 1.:
            raise ValueError("Battery SOC floor must be between zero and one")
        if (not 0 <= int(building_index) < len(storage_devices)
                or len(storage_devices) != self.actor_building_count):
            raise ValueError("Battery SOC floor needs a valid building scope")
        self.battery_post_soc_floor = float(floor)
        self.battery_post_soc_floor_building_index = int(building_index)
        self.battery_storage_devices = list(storage_devices)

    def _battery_floor_action_map(self, features):
        if self.battery_post_soc_floor is None:
            return None
        values = features.detach().cpu().numpy()
        if values.ndim != 3 or values.shape[-1] < 16:
            raise ValueError("Battery floor mapping requires [batch, buildings, features]")
        batch = values.shape[0]
        count = len(self.grids[1])
        mapping = np.tile(np.arange(count, dtype=np.int64), (batch, 1))
        building = self.battery_post_soc_floor_building_index
        grid = np.asarray(self.grids[1], dtype=float)
        for row in range(batch):
            if float(values[row, building, 15]) >= .5:
                continue
            soc = float(values[row, building, 14])
            device = self.battery_storage_devices[building]
            eta = float(device.round_trip_efficiency)
            for action_index, action in enumerate(grid):
                if action >= 0.:
                    continue
                predicted = predict_next_electrical_storage_soc(
                    device, soc, float(action), eta)
                if predicted >= self.battery_post_soc_floor - 1e-7:
                    continue
                for alternative_index in range(action_index + 1, count):
                    alternative = float(grid[alternative_index])
                    alternative_soc = predict_next_electrical_storage_soc(
                        device, soc, alternative, eta)
                    if alternative_soc >= self.battery_post_soc_floor - 1e-7:
                        mapping[row, action_index] = alternative_index
                        break
                else:
                    mapping[row, action_index] = count - 1
        return torch.as_tensor(mapping, dtype=torch.long)

    def filter_battery_floor_indices(self, indices, features):
        mapping = self._battery_floor_action_map(features)
        if mapping is None:
            return indices
        squeeze = indices.ndim == 2
        result = indices.unsqueeze(0).clone() if squeeze else indices.clone()
        building = self.battery_post_soc_floor_building_index
        proposed = result[:, building, 1]
        result[:, building, 1] = mapping.gather(
            1, proposed.unsqueeze(-1)).squeeze(-1)
        return result.squeeze(0) if squeeze else result

    def filter_battery_floor_probabilities(self, probabilities, features):
        mapping = self._battery_floor_action_map(features)
        if mapping is None:
            return probabilities
        result = list(probabilities)
        building = self.battery_post_soc_floor_building_index
        source = probabilities[1][:, building, :]
        mapped = torch.zeros_like(source).scatter_add(1, mapping, source)
        battery = probabilities[1].clone()
        battery[:, building, :] = mapped
        result[1] = battery
        return result

    def actions(self, state, deterministic=False, explore=False,
                behavior_policy='categorical', epsilon=0.0):
        # state形状[楼,特征]；返回ids和actions，二者都是[楼,3]。
        # 本实现固定顺序为热水储能、电池、制冷，运行时须验证数据集动作契约。
        # 电池正数表示充电命令、负数表示放电；制冷为设备开度，不是温度设定点。
        # 命令仍会受环境的SOC/功率/停电等物理约束，不能等同实际耗电kWh。
        if behavior_policy not in ('uniform', 'categorical', 'epsilon_greedy'):
            raise ValueError(f'Unknown behavior policy: {behavior_policy}')
        if explore and behavior_policy == 'uniform':
            ids = np.stack([np.random.randint(n, size=len(state)) for n in CLASSES], axis=-1)
        else:
            with torch.no_grad():
                greedy = self.actor.sample(
                    torch.from_numpy(state), deterministic=True
                )[0].numpy()
                if explore and behavior_policy == 'epsilon_greedy':
                    ids = greedy.copy()
                    random_ids = np.stack(
                        [np.random.randint(n, size=len(state)) for n in CLASSES],
                        axis=-1
                    )
                    choose_random = np.random.random(ids.shape) < float(epsilon)
                    ids[choose_random] = random_ids[choose_random]
                else:
                    ids = self.actor.sample(
                        torch.from_numpy(state), deterministic
                    )[0].numpy()
        if isinstance(self.actor, FrozenCoolingActor):
            # Even uniform/epsilon exploration must not override the frozen controller.
            with torch.no_grad():
                ids[:, 2] = self.actor.cooling_teacher(
                    torch.from_numpy(state))[..., -CLASSES[2]:].argmax(-1).numpy()
        actions = np.stack([g[ids[:, h]] for h, g in enumerate(self.grids)], axis=-1)
        return ids, actions

    def freeze_cooling_policy(self):
        if isinstance(self.actor, FrozenCoolingActor):
            raise ValueError('Cooling policy is already frozen')
        self.actor = FrozenCoolingActor(self.actor)
        self.target_actor = FrozenCoolingActor(self.target_actor)
        # Both behavior and bootstrap use exactly the same immutable anchor.
        self.target_actor.cooling_teacher.load_state_dict(self.actor.cooling_teacher.state_dict())
        self.actor_opt = torch.optim.Adam(
            [p for p in self.actor.parameters() if p.requires_grad],
            lr=self.actor_opt.param_groups[0]['lr'])

    def update(self):
        # 一次更新路线：抽经验 -> 构造价值目标 -> 更新Critic -> 更新Actor -> 软更新。
        # states形状[batch,楼,特征]；一个batch是多条历史联合转移，不是多个未来时刻。
        update_started = time.perf_counter()
        diagnose = (self.diagnostics_interval > 0
                    and (self.updates + 1) % self.diagnostics_interval == 0)
        self.last_update_diagnostics = {}
        if diagnose:
            parameter_before = {
                name: [p.detach().clone() for p in module.parameters() if p.requires_grad]
                for name, module in (('actor', self.actor), ('critic', self.critic))
            }
        (states, ids, components, nxt, done, episodes, steps, n_steps), sample_ids = self.replay.sample(self.batch_size)
        actor_batch = (states, ids, steps.copy())
        importance = None
        if self.critic_replay_sampling == 'battery_balanced_is':
            probability = self.replay.battery_balanced_probabilities()
            critic_ids = self.critic_replay_rng.choice(len(probability), self.batch_size, replace=True, p=probability)
            rows = [self.replay.rows[int(i)] for i in critic_ids]
            states, ids, components, nxt, done, episodes, steps, n_steps = tuple(np.stack(v) for v in zip(*rows))
            importance = torch.as_tensor(1. / (len(probability) * probability[critic_ids]), dtype=torch.float32)
        states = torch.from_numpy(states); ids = torch.from_numpy(ids).long()
        nxt = torch.from_numpy(nxt)
        component_tensor = torch.from_numpy(components)
        onehot = torch.cat([F.one_hot(ids[..., h], n) for h, n in enumerate(CLASSES)], -1).float()
        with torch.no_grad():
            # 慢更新网络估计下一状态的价值；no_grad意味着目标不参与反向传播。
            # 目标大意=已发生奖励+折扣*未来估计；真正终止时not_done=0，不接未来价值。
            ni, na, nl, _ = self.target_actor.sample(
                nxt, deterministic=self.target_action_policy == 'greedy')
            if self.fixed_cooling_schedule is not None:
                target_steps = steps.astype(np.int64) + n_steps.astype(np.int64) - 1
                ni = self.fixed_cooling_ids(ni, target_steps)
            ni = self.filter_battery_floor_indices(ni, nxt)
            na = torch.cat([
                F.one_hot(ni[..., head], width)
                for head, width in enumerate(CLASSES)
            ], -1).float()
            gamma = self.discount ** torch.from_numpy(n_steps).float()
            not_done = (1.-torch.from_numpy(done).float()).view(-1,1,1)
            if self.critic_objective == 'separate':
                nq = branch_values_multi(self.target_critic(nxt, na), ni)
                rewards = -self.reward_scale * component_tensor
                y = torch.stack([
                    rewards[..., objective].unsqueeze(-1)
                    + gamma.view(-1,1,1) * not_done * nq[..., objective]
                    for objective in range(self.objective_count)
                ], dim=-1)
            else:
                rewards = torch.from_numpy(weighted_reward(
                    components, self.cost_weights, self.discomfort_weights))
                nq = branch_values(self.target_critic(nxt, na), ni)
                y = rewards.unsqueeze(-1) + gamma.view(-1,1,1)*not_done*(nq-nl/self.reward_scale)
        if self.critic_objective == 'separate':
            q = branch_values_multi(self.critic(states, onehot), ids)
        else:
            q = branch_values(self.critic(states, onehot), ids)
        critic_loss = (F.mse_loss(q, y) if importance is None else
                       ((q-y).square().flatten(1).mean(-1)*importance).mean())
        # Critic拟合目标y，降低预测q与y的误差；裁剪梯度用于限制单次更新幅度。
        # 损失下降只表示更贴合当前训练目标，不直接证明最终费用/舒适KPI改善。
        if not torch.isfinite(critic_loss): raise ValueError('Non-finite critic loss')
        self.critic_opt.zero_grad(); critic_loss.backward()
        critic_grad_norm = nn.utils.clip_grad_norm_(self.critic.parameters(), 10.)
        self.critic_opt.step()
        if importance is not None:
            states = torch.from_numpy(actor_batch[0])
            ids = torch.from_numpy(actor_batch[1]).long()
            actor_steps = actor_batch[2]
        else:
            actor_steps = steps
        if self.freeze_actor_updates:
            with torch.no_grad():
                si, sa, logs, probs = self.actor.sample(states)
                if self.fixed_cooling_schedule is not None:
                    si = self.fixed_cooling_ids(si, actor_steps.astype(np.int64) - 1)
                si = self.filter_battery_floor_indices(si, states)
                sa = torch.cat([
                    F.one_hot(si[..., head], width)
                    for head, width in enumerate(CLASSES)
                ], -1).float()
            loss = torch.zeros((), dtype=states.dtype)
            entropy = torch.zeros((), dtype=states.dtype)
            kl = torch.zeros((), dtype=states.dtype)
        else:
            si, sa, logs, probs = self.actor.sample(states)
            if self.fixed_cooling_schedule is not None:
                si = self.fixed_cooling_ids(si, actor_steps.astype(np.int64) - 1)
                si = self.filter_battery_floor_indices(si, states)
                sa = torch.cat([
                    F.one_hot(si[..., head], width)
                    for head, width in enumerate(CLASSES)
                ], -1).float()
                probs = list(probs)
                if self.fixed_cooling_schedule is not None:
                    probs[2] = F.one_hot(si[..., 2], CLASSES[2]).to(states.dtype)
                probs = self.filter_battery_floor_probabilities(probs, states)
            with torch.no_grad():
                all_q = self.critic(states, sa)
                # advantage比较“所选动作价值”与当前策略平均价值。
                # Actor据此调整各档位概率；这不是CHESCA式的规则命中解释。
                if self.critic_objective == 'separate':
                    selected = branch_values_multi(all_q, si)
                    objective_q = [
                        all_q[..., i*sum(CLASSES):(i+1)*sum(CLASSES)]
                        for i in range(self.objective_count)
                    ]
                    values = []
                    for q_objective in objective_q:
                        values.append(torch.stack([
                            (p.detach()*v).sum(-1)
                            for p, v in zip(probs, q_objective.split(CLASSES, -1))
                        ], -1))
                    values = torch.stack(values, dim=-1)
                    if self.split_thermal_discomfort:
                        objective_weights = [
                            self.cost_weights * self.actor_cost_objective_scale,
                            self.hot_discomfort_weights,
                            self.cold_discomfort_weights,
                            np.ones_like(self.cost_weights),
                        ]
                    else:
                        objective_weights = [
                            self.cost_weights * self.actor_cost_objective_scale,
                            self.discomfort_weights,
                            np.ones_like(self.cost_weights),
                        ]
                    weights = torch.from_numpy(
                        np.stack(objective_weights, axis=-1)
                    ).to(dtype=states.dtype)
                    advantage = ((selected-values)*weights.unsqueeze(0).unsqueeze(2)).sum(-1)
                else:
                    selected = branch_values(all_q, si)
                    values = torch.stack([(p.detach()*v).sum(-1) for p,v in
                                          zip(probs, all_q.split(CLASSES, -1))], -1)
                    advantage = selected-values
            entropy = torch.stack([-(p * (p.clamp_min(1.e-8).log())).sum(-1)
                                   for p in probs], -1).mean()
            kl = torch.zeros((), dtype=states.dtype)
            if self.reference_actor is not None and self.behavior_kl_penalty > 0:
                with torch.no_grad():
                    ref_probs = [F.softmax(v, dim=-1)
                                 for v in self.reference_actor(states).split(CLASSES, -1)]
                    ref_probs = self.filter_battery_floor_probabilities(
                        ref_probs, states)
                kl = torch.stack([(p.clamp_min(1.e-8) *
                                   (p.clamp_min(1.e-8).log() -
                                    q.clamp_min(1.e-8).log())).sum(-1)
                                  if not isinstance(self.actor, FrozenCoolingActor) or h != 2
                                  else torch.zeros_like(p[..., 0])
                                  for h, (p, q) in enumerate(zip(probs, ref_probs))], -1).mean()
            if self.critic_objective == 'separate':
                loss = ((logs*(logs/self.reward_scale-advantage).detach()).mean()
                        + self.entropy_penalty * entropy)
            else:
                loss = ((logs*(logs/self.reward_scale-advantage).detach()).mean()
                        + self.entropy_penalty * entropy)
            loss = loss + self.behavior_kl_penalty * kl
            if not torch.isfinite(loss): raise ValueError('Non-finite actor loss')
            self.actor_opt.zero_grad(); loss.backward()
            actor_grad_norm = nn.utils.clip_grad_norm_(self.actor.parameters(), .5)
            self.actor_opt.step()
        with torch.no_grad():
            target_pairs = [(self.target_critic, self.critic)]
            # 软更新：target <- (1-tau)*target + tau*source。
            # 目标网络缓慢跟随学习网络，避免每一步学习目标都剧烈变化。
            if not self.freeze_actor_updates:
                target_pairs.append((self.target_actor, self.actor))
            for target, source in target_pairs:
                for tp, sp in zip(target.parameters(),source.parameters()):
                    if not sp.requires_grad:
                        continue
                    tp.mul_(1-self.tau).add_(sp,alpha=self.tau)
        self.updates += 1
        self.last_losses = dict(actor=float(loss), critic=float(critic_loss),
                                entropy=float(entropy), behavior_kl=float(kl),
                                actor_update_skipped=self.freeze_actor_updates,
                                actor_cost_objective_scale=float(
                                    self.actor_cost_objective_scale),
                                critic_replay_sampling=self.critic_replay_sampling,
                                critic_importance_min=1. if importance is None else float(importance.min()),
                                critic_importance_max=1. if importance is None else float(importance.max()),
                                sampled_joint_rows=len(sample_ids),
                                joint_sample_id_sha256=hashlib.sha256(np.asarray(sample_ids,dtype='<i8').tobytes()).hexdigest())
        if diagnose:
            with torch.no_grad():
                diagnostic = dict(
                    updates=self.updates, batch_size=self.batch_size,
                    replay_size=len(self.replay.rows),
                    actor_lr=self.actor_opt.param_groups[0]['lr'],
                    critic_lr=self.critic_opt.param_groups[0]['lr'],
                    actor_grad_norm_preclip=(0. if self.freeze_actor_updates
                                             else float(actor_grad_norm)),
                    critic_grad_norm_preclip=float(critic_grad_norm),
                    actor_gradient_clipped=(False if self.freeze_actor_updates
                                             else bool(actor_grad_norm > .5)),
                    critic_gradient_clipped=bool(critic_grad_norm > 10.),
                    **self.last_losses,
                )
                for name, module in (('actor', self.actor), ('critic', self.critic)):
                    pairs = list(zip(parameter_before[name],
                                     [p for p in module.parameters() if p.requires_grad]))
                    size = sum(float(old.square().sum()) for old, _ in pairs) ** .5
                    delta = sum(float((new.detach() - old).square().sum())
                                for old, new in pairs) ** .5
                    diagnostic[name + '_parameter_norm_before'] = size
                    diagnostic[name + '_parameter_update_l2'] = delta
                    diagnostic[name + '_relative_parameter_update'] = delta / max(size, 1e-12)
                residual = (q - y).detach()
                objective_names = (
                    ('cost', 'hot', 'cold', 'shaping') if self.split_thermal_discomfort
                    else ('cost', 'discomfort', 'shaping')
                ) if self.critic_objective == 'separate' else ('scalarized',)
                for objective, name in enumerate(objective_names):
                    pred = q[..., objective] if self.critic_objective == 'separate' else q
                    target = y[..., objective] if self.critic_objective == 'separate' else y
                    error = residual[..., objective] if self.critic_objective == 'separate' else residual
                    diagnostic['td_' + name + '_rmse'] = float(error.square().mean().sqrt())
                    diagnostic['td_' + name + '_abs_q95'] = float(torch.quantile(error.abs().flatten(), .95))
                    diagnostic['q_' + name + '_mean'] = float(pred.mean())
                    diagnostic['target_' + name + '_mean'] = float(target.mean())
                post_probs = [v.softmax(-1) for v in self.actor(states).split(CLASSES, -1)]
                for head, name in enumerate(('dhw', 'battery', 'cooling')):
                    old_p = probs[head].detach()
                    new_p = post_probs[head]
                    diagnostic[name + '_update_kl'] = float(
                        (old_p * (old_p.clamp_min(1e-8).log()
                                  - new_p.clamp_min(1e-8).log())).sum(-1).mean())
                    diagnostic[name + '_argmax_change_fraction'] = float(
                        (old_p.argmax(-1) != new_p.argmax(-1)).float().mean())
                if self.critic_objective == 'separate' and not self.freeze_actor_updates:
                    discomfort_q = objective_q[1][..., -CLASSES[2]:]
                    if self.split_thermal_discomfort:
                        discomfort_q = discomfort_q + objective_q[2][..., -CLASSES[2]:]
                    for label, mask in (
                        ('hot', (states[..., 8] > .5) & (states[..., 7] < 0)),
                        ('cold', (states[..., 8] > .5) & (states[..., 6] < 0)),
                    ):
                        diagnostic[label + '_state_count'] = int(mask.sum())
                        if mask.any():
                            diagnostic[label + '_discomfort_q_best_cooling_bin'] = float(
                                discomfort_q.argmax(-1)[mask].float().mean())
                            diagnostic[label + '_actor_cooling_bin'] = float(
                                probs[2].argmax(-1)[mask].float().mean())
                diagnostic['update_elapsed_s_including_diagnostics'] = time.perf_counter() - update_started
                self.last_update_diagnostics = diagnostic

    def save(self, path, protocol, episode):
        value = dict(version=VERSION, protocol=protocol, episode=episode,
                     actor=self.actor.state_dict(), critic=self.critic.state_dict(),
                     target_actor=self.target_actor.state_dict(), target_critic=self.target_critic.state_dict(),
                     actor_optimizer=self.actor_opt.state_dict(), critic_optimizer=self.critic_opt.state_dict(),
                     replay_rows=self.replay.rows, replay_position=self.replay.position,
                     updates=self.updates, python_rng=random.getstate(), numpy_rng=np.random.get_state(),
                     torch_rng=torch.get_rng_state(), fixed_feature_scaling=True,
                     critic_replay_rng_state=self.critic_replay_rng.bit_generator.state,
                     episode_boundary=True, dual_multipliers=dict(
                         cost=self.cost_weights.tolist(),
                         discomfort=self.discomfort_weights.tolist(),
                         hot_discomfort=self.hot_discomfort_weights.tolist(),
                         cold_discomfort=self.cold_discomfort_weights.tolist()))
        temp = Path(str(path)+'.tmp'); torch.save(value,temp); os.replace(temp,path)


def target_kpis(env, discomfort_target=.10, cost_target=.90):
    rows = env.evaluate().to_dict(orient='records')
    per = {b.name:{r['cost_function']:float(r['value']) for r in rows
                   if r['name']==b.name and r['level']=='building'} for b in env.buildings}
    passed = all(v['cost_total']<cost_target
                 and v['discomfort_proportion']<discomfort_target
                 for v in per.values())
    comfort_passed = all(v['discomfort_proportion']<discomfort_target
                         for v in per.values())
    return dict(per_building=per, all_buildings_meet_targets=passed, official_kpi=rows,
                all_buildings_meet_comfort_target=comfort_passed,
                terminal_soc={b.name:float(b.electrical_storage.soc[b.time_step]) for b in env.buildings})


def update_constraint_weights(cost_weights, discomfort_weights, per_building,
                              building_names, learning_rate, maximum,
                              cost_target=.90, discomfort_target=.10,
                              discomfort_learning_rate=None):
    metrics = [per_building[name] for name in building_names]
    cost = np.asarray([m['cost_total'] / cost_target - 1. for m in metrics])
    discomfort = np.asarray([m['discomfort_proportion'] / discomfort_target - 1. for m in metrics])
    if not np.isfinite(cost).all() or not np.isfinite(discomfort).all():
        raise ValueError('Non-finite constraint metric')
    discomfort_learning_rate = (learning_rate if discomfort_learning_rate is None
                                else discomfort_learning_rate)
    if learning_rate < 0 or discomfort_learning_rate < 0:
        raise ValueError('Constraint learning rates must be non-negative')
    return (np.clip(cost_weights + learning_rate * cost, 0., maximum).astype(np.float32),
            np.clip(discomfort_weights + discomfort_learning_rate * discomfort,
                    0., maximum).astype(np.float32))


def update_comfort_priority_scale(current_scale, per_building, building_names,
                                  discomfort_target=.10, release_target=.09,
                                  passing_evaluations=0, release_patience=2,
                                  maximum_scale=1.):
    if not (0. < release_target <= discomfort_target <= 1.):
        raise ValueError('Comfort release target must not exceed the discomfort target')
    if release_patience < 1:
        raise ValueError('Comfort release patience must be positive')
    if not (0. <= maximum_scale <= 1.):
        raise ValueError('Maximum actor cost scale must be between 0 and 1')
    values = np.asarray(
        [per_building[name]['discomfort_proportion'] for name in building_names],
        dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Comfort metrics must be finite')
    if current_scale > 0.:
        if np.any(values >= discomfort_target):
            return 0., 0
        return maximum_scale, release_patience
    if np.all(values < release_target):
        passing_evaluations += 1
        if passing_evaluations >= release_patience:
            return maximum_scale, passing_evaluations
        return 0., passing_evaluations
    return 0., 0


def apply_actor_cost_advantage_freeze(scale, frozen):
    return 0. if frozen else float(scale)


def _json_value(value):
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def flat_observation_fields(before, after):
    fields = {}
    for prefix, observation in (('before', before), ('after', after)):
        for name, value in observation.items():
            if isinstance(value, (str, int, float, bool, np.generic)):
                fields[f'{prefix}_{name}'] = _json_value(value)
    before_temp = before.get('indoor_dry_bulb_temperature')
    after_temp = after.get('indoor_dry_bulb_temperature')
    if before_temp is not None and after_temp is not None:
        fields['indoor_temperature_delta_C'] = float(after_temp) - float(before_temp)
    return fields


def dataset_digest(directory):
    directory = Path(directory).resolve()
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob('*') if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def apply_unoccupied_cooling_gate(before, proposed_actions, cooling_grid, step,
                                  enabled=False, reduction_bins=1,
                                  building_index=None,
                                  min_unoccupied_steps=0,
                                  unoccupied_streak=None,
                                  comfort_margin=.5,
                                  price_threshold=0.02914999984204769,
                                  second_bin_comfort_margin=None,
                                  second_bin_allowed_hours=None,
                                  max_cooling_demand=None,
                                  min_cooling_demand_exclusive=None):
    """Fixed execution mapping: replay/Q indices remain in proposal space.

    Only current public observations and elapsed action count are read. History
    must receive the returned executed commands, never the proposal instead.
    """
    actions=proposed_actions.copy()
    active=np.zeros(len(before),dtype=bool)
    if not enabled:
        return actions,active
    if reduction_bins not in (1,2):
        raise ValueError('Cooling execution reduction must be one or two bins')
    if min_unoccupied_steps < 0:
        raise ValueError('Minimum unoccupied duration must be nonnegative')
    if unoccupied_streak is not None and len(unoccupied_streak) != len(before):
        raise ValueError('Unoccupied duration requires one value per building')
    if (max_cooling_demand is not None
            and (not np.isfinite(max_cooling_demand)
                 or max_cooling_demand < 0.)):
        raise ValueError('Maximum cooling demand must be finite and nonnegative')
    if (min_cooling_demand_exclusive is not None
            and (not np.isfinite(min_cooling_demand_exclusive)
                 or min_cooling_demand_exclusive < 0.)):
        raise ValueError(
            'Minimum exclusive cooling demand must be finite and nonnegative')
    if (max_cooling_demand is not None
            and min_cooling_demand_exclusive is not None
            and max_cooling_demand <= min_cooling_demand_exclusive):
        raise ValueError('Cooling demand interval must have positive width')
    if second_bin_comfort_margin is not None:
        if (not np.isfinite(second_bin_comfort_margin)
                or second_bin_comfort_margin < comfort_margin):
            raise ValueError(
                'Second-bin comfort margin must be finite and at least the gate margin')
    if second_bin_allowed_hours is not None:
        second_bin_allowed_hours = {int(hour) for hour in second_bin_allowed_hours}
        if any(hour < 0 or hour > 24 for hour in second_bin_allowed_hours):
            raise ValueError('Second-bin allowed hours must be in [0, 24]')
    for i,obs in enumerate(before):
        if ((building_index is None or i == building_index)
                and (unoccupied_streak is None
                     or unoccupied_streak[i] >= min_unoccupied_steps)
                and step>=25 and obs['occupant_count']<=0 and obs['power_outage']<.5
                and obs['indoor_dry_bulb_temperature']<=
                    obs['indoor_dry_bulb_temperature_cooling_set_point']
                    + obs['comfort_band'] - comfort_margin
                and obs['electricity_pricing']>=price_threshold
                and (max_cooling_demand is None
                     or obs['cooling_demand'] <= max_cooling_demand)
                and (min_cooling_demand_exclusive is None
                     or obs['cooling_demand']
                     > min_cooling_demand_exclusive)
                and proposed_actions[i,2]>=.2-1e-7):
            index=int(np.abs(cooling_grid-proposed_actions[i,2]).argmin())
            if index<1 or abs(float(cooling_grid[index])-float(proposed_actions[i,2]))>1e-7:
                raise ValueError('Cooling gate requires legal discrete proposal')
            bins = reduction_bins
            if (reduction_bins == 2
                    and second_bin_comfort_margin is not None
                    and obs['indoor_dry_bulb_temperature'] >
                    obs['indoor_dry_bulb_temperature_cooling_set_point']
                    + obs['comfort_band'] - second_bin_comfort_margin):
                bins = 1
            if (reduction_bins == 2
                    and second_bin_allowed_hours is not None
                    and int(obs['hour']) not in second_bin_allowed_hours):
                bins = 1
            actions[i,2]=cooling_grid[max(0,index-bins)]
            active[i]=True
    return actions,active


def apply_high_price_charge_gate(before, proposed_actions, step,
                                 enabled=False, price_threshold=0.02915,
                                 reserve_soc=0.20):
    """Suppress only nonessential high-price battery charging."""
    actions = proposed_actions.copy()
    active = np.zeros(len(before), dtype=bool)
    if not enabled:
        return actions, active
    for i, obs in enumerate(before):
        if (float(obs['electricity_pricing']) + 1e-7 >= float(price_threshold)
                and float(obs['power_outage']) < .5
                and float(obs['electrical_storage_soc']) >= float(reserve_soc) - 1e-7
                and proposed_actions[i, 1] > 0.):
            actions[i, 1] = 0.
            active[i] = True
    return actions, active


def apply_high_price_discharge_rule(before, proposed_actions, battery_grid,
                                    enabled=False, price_threshold=0.05867,
                                    reserve_soc=0.50,
                                    action=-0.04878788,
                                    building_index=None,
                                    storage_devices=None,
                                    post_soc_floor=None,
                                    post_soc_floor_by_building=None):
    """Apply a minimal causal discharge only for high-price positive imports."""
    actions = proposed_actions.copy()
    active = np.zeros(len(before), dtype=bool)
    post_soc_blocked = np.zeros(len(before), dtype=bool)
    predicted_post_soc = np.full(len(before), np.nan, dtype=float)
    if not enabled:
        return actions, active, post_soc_blocked, predicted_post_soc
    floor_overrides = {
        int(index): float(floor)
        for index, floor in (post_soc_floor_by_building or {}).items()
    }
    if (any(index < 0 or index >= len(before) for index in floor_overrides)
            or any(not np.isfinite(floor) or not 0. <= floor <= 1.
                   for floor in floor_overrides.values())):
        raise ValueError("Building-specific post-action SOC floors must be in [0, 1]")
    if (post_soc_floor is not None or floor_overrides) and (
            storage_devices is None or len(storage_devices) != len(before)):
        raise ValueError(
            "Post-action SOC floor requires one battery model per building")
    grid = np.asarray(battery_grid, dtype=float)
    index = int(np.abs(grid - float(action)).argmin())
    legal_action = float(grid[index])
    if abs(legal_action - float(action)) > 1e-7 or legal_action >= 0:
        raise ValueError("High-price discharge action must be a legal negative grid value")
    for i, obs in enumerate(before):
        if building_index is not None and i != int(building_index):
            continue
        if (float(obs['electricity_pricing']) + 1e-7 >= float(price_threshold)
                and float(obs['power_outage']) < .5
                and float(obs['electrical_storage_soc']) + 1e-7
                >= float(reserve_soc)
                and float(obs['net_electricity_consumption']) > 0.
                and float(proposed_actions[i, 1]) > legal_action):
            effective_floor = floor_overrides.get(i, post_soc_floor)
            if effective_floor is not None:
                device = storage_devices[i]
                predicted_post_soc[i] = predict_next_electrical_storage_soc(
                    device,
                    float(obs['electrical_storage_soc']),
                    legal_action,
                    float(device.round_trip_efficiency),
                )
                if predicted_post_soc[i] < float(effective_floor) - 1e-7:
                    post_soc_blocked[i] = True
                    continue
            actions[i, 1] = legal_action
            active[i] = True
    return actions, active, post_soc_blocked, predicted_post_soc


def apply_predicted_price_discharge_gate(before, proposed_actions,
                                         enabled=False, min_price_spread=0.0,
                                         building_index=None):
    """Hold low-price discharge when the observed next-step price forecast rises."""
    actions = proposed_actions.copy()
    active = np.zeros(len(before), dtype=bool)
    if not enabled:
        return actions, active
    if not np.isfinite(float(min_price_spread)) or float(min_price_spread) < 0.:
        raise ValueError("Minimum predicted price spread must be finite and nonnegative")
    for i, obs in enumerate(before):
        if building_index is not None and i != int(building_index):
            continue
        current_price = float(obs['electricity_pricing'])
        next_price = obs.get('electricity_pricing_predicted_1')
        if next_price is None or not np.isfinite(float(next_price)):
            continue
        if (float(obs['power_outage']) < .5
                and float(obs['net_electricity_consumption']) > 0.
                and float(proposed_actions[i, 1]) < 0.
                and float(next_price) - current_price
                >= float(min_price_spread)):
            actions[i, 1] = 0.
            active[i] = True
    return actions, active


def apply_predicted_price_charge_rule(
        before, proposed_actions, battery_grid, enabled=False,
        max_current_price=0.03025, min_price_spread=0.005,
        max_soc=0.30, action=None, building_index=None):
    """Add one legal charge bin before a forecast price rise at low SOC."""
    actions = proposed_actions.copy()
    active = np.zeros(len(before), dtype=bool)
    if not enabled:
        return actions, active
    if (not np.isfinite(float(max_current_price))
            or float(max_current_price) < 0.
            or not np.isfinite(float(min_price_spread))
            or float(min_price_spread) < 0.
            or not np.isfinite(float(max_soc))
            or not 0. <= float(max_soc) <= 1.):
        raise ValueError("Predicted-price charge parameters are out of range")
    grid = np.asarray(battery_grid, dtype=float)
    if action is None:
        legal_charges = grid[grid > 0.]
        if not len(legal_charges):
            raise ValueError("Battery grid has no legal charging action")
        legal_action = float(legal_charges[0])
    else:
        index = int(np.abs(grid - float(action)).argmin())
        legal_action = float(grid[index])
        if (abs(legal_action - float(action)) > 1e-7
                or legal_action <= 0.):
            raise ValueError(
                "Predicted-price charge action must be a legal positive grid value")
    for i, obs in enumerate(before):
        if building_index is not None and i != int(building_index):
            continue
        next_price = obs.get('electricity_pricing_predicted_1')
        if next_price is None or not np.isfinite(float(next_price)):
            continue
        current_price = float(obs['electricity_pricing'])
        if (current_price <= float(max_current_price) + 1e-7
                and float(next_price) - current_price >= float(min_price_spread)
                and float(obs['power_outage']) < .5
                and float(obs['electrical_storage_soc']) <= float(max_soc) + 1e-7
                and float(obs['net_electricity_consumption']) > 0.
                and float(proposed_actions[i, 1]) < legal_action - 1e-7):
            actions[i, 1] = legal_action
            active[i] = True
    return actions, active


def apply_battery_post_soc_floor(before, proposed_actions, battery_grid,
                                 storage_devices, post_soc_floor,
                                 building_index=None):
    """Limit non-outage battery commands that cross a post-action SOC floor."""
    if not 0. <= float(post_soc_floor) <= 1.:
        raise ValueError("Post-action SOC floor must be between zero and one")
    actions = proposed_actions.copy()
    blocked = np.zeros(len(before), dtype=bool)
    predicted_post_soc = np.full(len(before), np.nan, dtype=float)
    if len(storage_devices) != len(before):
        raise ValueError("SOC floor requires one battery model per building")
    grid = np.asarray(battery_grid, dtype=float)
    for i, obs in enumerate(before):
        if (building_index is not None and i != int(building_index)):
            continue
        if float(obs.get("power_outage", 0.)) >= .5:
            continue
        proposed = float(actions[i, 1])
        if proposed >= 0.:
            continue
        device = storage_devices[i]
        soc = float(obs["electrical_storage_soc"])
        eta = float(device.round_trip_efficiency)
        predicted_post_soc[i] = predict_next_electrical_storage_soc(
            device, soc, proposed, eta)
        if predicted_post_soc[i] >= float(post_soc_floor) - 1e-7:
            continue

        blocked[i] = True
        for alternative in grid[grid > proposed + 1e-7]:
            alternative_soc = predict_next_electrical_storage_soc(
                device, soc, float(alternative), eta)
            if alternative_soc >= float(post_soc_floor) - 1e-7:
                actions[i, 1] = float(alternative)
                predicted_post_soc[i] = alternative_soc
                break
        else:
            # If even the largest grid command cannot restore the floor, keep
            # the least-discharge command and report its predicted SOC.
            alternative = float(grid[-1])
            actions[i, 1] = alternative
            predicted_post_soc[i] = predict_next_electrical_storage_soc(
                device, soc, alternative, eta)
    return actions, blocked, predicted_post_soc


def predict_next_electrical_storage_soc(device, soc, action, previous_eta):
    """Predict one storage transition from CityLearn battery curves."""
    capacity = float(device.capacity)
    initial = float(soc) * capacity * (1.0 - float(device.loss_coefficient))
    power = float(device.nominal_power) * float(np.interp(
        initial / capacity, device.capacity_power_curve[0],
        device.capacity_power_curve[1]))
    request = float(action) * capacity
    efficiency = float(np.interp(
        min(abs(request), power) / float(device.nominal_power),
        device.power_efficiency_curve[0],
        device.power_efficiency_curve[1])) ** .5
    if request >= 0.:
        charge = min(
            request, power, float(device.nominal_power),
            max(float(device.degraded_capacity) - initial, 0.),
        )
        energy = min(initial + charge * efficiency, capacity)
    else:
        dod_limit = -max(
            (float(soc) - (1.0 - float(device.depth_of_discharge)))
            * capacity * float(previous_eta),
            0.,
        )
        discharge = max(request, -power, dod_limit)
        energy = max(initial + discharge / efficiency, 0.)
    return energy / capacity


def load_fixed_cooling_action_schedule(path, building_names, cooling_grid,
                                       transition_count):
    """Load a fixed, legal per-building cooling command for each transition."""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = {
        (name, step)
        for step in range(1, int(transition_count) + 1)
        for name in building_names
    }
    schedule = {}
    grid = np.asarray(cooling_grid, dtype=float)
    for row in rows:
        key = (row["building"], int(row["step"]))
        if key in schedule:
            raise ValueError(f"Duplicate cooling schedule row: {key}")
        value = float(row["cooling_action"])
        index = int(np.abs(grid - value).argmin())
        if abs(float(grid[index]) - value) > 1e-7:
            raise ValueError(f"Cooling schedule action is outside the action grid: {key}")
        schedule[key] = index
    if set(schedule) != expected:
        missing = sorted(expected - set(schedule))[:5]
        extra = sorted(set(schedule) - expected)[:5]
        raise ValueError(
            f"Cooling schedule coverage mismatch; missing={missing}, extra={extra}"
        )
    return np.asarray([
        [schedule[(name, step)] for name in building_names]
        for step in range(1, int(transition_count) + 1)
    ], dtype=np.int64)


def apply_fixed_cooling_action_schedule(actions, action_ids, schedule,
                                        transition_index, cooling_grid):
    if schedule is None:
        return actions, action_ids
    indices = np.asarray(schedule[int(transition_index)], dtype=np.int64)
    actions[:, 2] = np.asarray(cooling_grid, dtype=float)[indices]
    action_ids[:, 2] = indices
    return actions, action_ids


def load_fixed_dhw_action_schedule(path, building_names, dhw_grid,
                                  transition_count):
    """Load a fixed, legal per-building DHW command for each transition."""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = {
        (name, step)
        for step in range(1, int(transition_count) + 1)
        for name in building_names
    }
    schedule = {}
    grid = np.asarray(dhw_grid, dtype=float)
    for row in rows:
        key = (row["building"], int(row["step"]))
        if key in schedule:
            raise ValueError(f"Duplicate DHW schedule row: {key}")
        value = float(row["dhw_action"])
        index = int(np.abs(grid - value).argmin())
        if abs(float(grid[index]) - value) > 1e-7:
            raise ValueError(f"DHW schedule action is outside the action grid: {key}")
        schedule[key] = index
    if set(schedule) != expected:
        missing = sorted(expected - set(schedule))[:5]
        extra = sorted(set(schedule) - expected)[:5]
        raise ValueError(
            f"DHW schedule coverage mismatch; missing={missing}, extra={extra}"
        )
    return np.asarray([
        [schedule[(name, step)] for name in building_names]
        for step in range(1, int(transition_count) + 1)
    ], dtype=np.int64)


def apply_fixed_dhw_action_schedule(actions, action_ids, schedule,
                                    transition_index, dhw_grid):
    if schedule is None:
        return actions, action_ids
    indices = np.asarray(schedule[int(transition_index)], dtype=np.int64)
    actions[:, 0] = np.asarray(dhw_grid, dtype=float)[indices]
    action_ids[:, 0] = indices
    return actions, action_ids


def apply_cooling_action_cap(actions, cooling_grid, max_action=None):
    """Limit evaluation cooling commands to the highest legal grid value <= cap."""
    executed = actions.copy()
    active = np.zeros(len(actions), dtype=bool)
    if max_action is None:
        return executed, active
    if not np.isfinite(max_action):
        raise ValueError("Cooling action cap must be finite")
    legal = np.asarray(cooling_grid, dtype=float)
    eligible = legal[legal <= float(max_action) + 1e-7]
    if not len(eligible):
        raise ValueError("Cooling action cap is below the minimum legal action")
    cap_value = float(eligible[-1])
    active = executed[:, 2] > cap_value + 1e-7
    executed[active, 2] = cap_value
    return executed, active


def apply_b1_occupied_low_demand_cap(before, actions, cooling_grid, enabled=False):
    """Evaluation experiment: cap B1 only using the current observable state."""
    if not enabled:
        return actions.copy(), np.zeros(len(actions), dtype=bool)
    observation = before[0]
    if (float(observation['occupant_count']) <= 0
            or bool(observation['power_outage'])
            or not np.isfinite(float(observation['cooling_demand']))
            or not 0. <= float(observation['cooling_demand']) <= 2.):
        return actions.copy(), np.zeros(len(actions), dtype=bool)
    executed = actions.copy()
    capped, active_b1 = apply_cooling_action_cap(actions[:1], cooling_grid, .6)
    executed[0] = capped[0]
    active = np.zeros(len(actions), dtype=bool)
    active[0] = active_b1[0]
    return executed, active


def evaluate(checkpoint, output, start_time_step=0, end_time_step=719, seed=41,
             evaluation_dataset_override=None,
             expected_evaluation_dataset_sha256=None,
             high_price_charge_gate_override=None,
             fixed_cooling_action_schedule_path=None,
             allow_fixed_cooling_schedule_hash_override=False,
             high_price_charge_threshold_override=None,
             high_price_charge_reserve_soc_override=None,
             high_price_discharge_rule_override=None,
             high_price_discharge_reserve_soc_override=None,
             high_price_discharge_building_index=None,
             high_price_discharge_post_soc_floor=None,
             disable_checkpoint_fixed_cooling_schedule=False,
             battery_post_soc_floor=None,
             battery_post_soc_floor_building_index=None,
             disable_checkpoint_battery_post_soc_floor=False,
             unoccupied_cooling_gate_override=None,
             unoccupied_cooling_gate_building_index=None,
             unoccupied_cooling_gate_min_steps_override=None,
             unoccupied_cooling_gate_comfort_margin_override=None,
             unoccupied_cooling_gate_price_threshold_override=None,
             unoccupied_cooling_gate_bins_override=None,
             fixed_dhw_action_schedule_path=None,
             high_price_discharge_threshold_override=None,
             high_price_discharge_action_override=None,
             unoccupied_cooling_gate_second_bin_comfort_margin_override=None,
             unoccupied_cooling_gate_second_bin_risk_profile_path=None,
             unoccupied_cooling_gate_second_bin_risk_threshold=None,
             predicted_price_discharge_gate_override=None,
             predicted_price_discharge_min_spread_override=None,
             predicted_price_discharge_building_index=None,
             predicted_price_charge_rule_override=None,
             predicted_price_charge_max_current_price_override=None,
             predicted_price_charge_min_spread_override=None,
             predicted_price_charge_max_soc_override=None,
             predicted_price_charge_building_index=None,
             predicted_price_charge_additional_building_index=None,
             predicted_price_charge_action_override=None,
             unoccupied_cooling_gate_max_demand_override=None,
             cooling_action_cap_override=None,
             unoccupied_cooling_gate_extra_building_index=None,
             unoccupied_cooling_gate_extra_min_demand_exclusive=None,
             unoccupied_cooling_gate_extra_max_demand=None,
             unoccupied_cooling_gate_extra_bins=None,
             high_price_discharge_post_soc_floor_building_index=None,
             high_price_discharge_post_soc_floor_building_override=None,
             unoccupied_cooling_gate_extra_2_building_index=None,
             unoccupied_cooling_gate_extra_2_min_demand_exclusive=None,
             unoccupied_cooling_gate_extra_2_max_demand=None,
             unoccupied_cooling_gate_extra_2_bins=None,
             unoccupied_cooling_gate_extra_3_building_index=None,
             unoccupied_cooling_gate_extra_3_min_demand_exclusive=None,
             unoccupied_cooling_gate_extra_3_max_demand=None,
             unoccupied_cooling_gate_extra_3_bins=None,
             unoccupied_cooling_gate_temp_rise_block_threshold=None,
             b1_occupied_low_demand_cap=False,
             outage_risk_pulse=False,
             diagnostic_battery_fork_path=None):
    # 固定评估：加载权重 -> reset -> 特征编码 -> 确定性动作及可选规则 -> env.step。
    # 此函数不调用learner.update；重复执行环境不等于继续训练。
    # 标准窗口含end-start+1个状态，但只有end-start次实际动作转移。
    global CLASSES
    if legacy is None:
        raise RuntimeError(
            'Phase 2 checkpoint evaluation requires the Phase 2 training environment'
        )
    saved = torch.load(checkpoint,map_location='cpu',weights_only=False)
    if saved['version'] not in COMPATIBLE_VERSIONS:
        raise ValueError('Checkpoint version mismatch')
    p = saved['protocol']
    if ((high_price_discharge_post_soc_floor_building_index is None)
            != (high_price_discharge_post_soc_floor_building_override is None)):
        raise ValueError(
            'Building-specific high-price SOC floor requires both index and value')
    high_price_floor_by_building = {}
    if high_price_discharge_post_soc_floor_building_index is not None:
        floor = float(high_price_discharge_post_soc_floor_building_override)
        if not np.isfinite(floor) or not 0. <= floor <= 1.:
            raise ValueError('Building-specific high-price SOC floor must be in [0, 1]')
        high_price_floor_by_building[
            int(high_price_discharge_post_soc_floor_building_index)
        ] = floor
    if disable_checkpoint_battery_post_soc_floor:
        if battery_post_soc_floor is not None:
            raise ValueError(
                'Cannot combine SOC-floor disable and explicit SOC-floor override'
            )
        battery_post_soc_floor = None
        battery_post_soc_floor_building_index = None
    elif battery_post_soc_floor is None:
        battery_post_soc_floor = p.get('battery_post_soc_floor')
        if battery_post_soc_floor_building_index is None:
            battery_post_soc_floor_building_index = p.get(
                'battery_post_soc_floor_building_index')
    training_dataset = Path(
        p.get('training_dataset_path', legacy.DATA)
    ).resolve()
    training_dataset_sha256 = p.get('dataset_sha256', legacy.EXPECTED)
    evaluation_dataset = Path(
        evaluation_dataset_override or p.get('evaluation_dataset_path')
        or training_dataset
    ).resolve()
    evaluation_dataset_sha256 = dataset_digest(evaluation_dataset)
    expected_evaluation_hash = (
        expected_evaluation_dataset_sha256 or p.get('evaluation_dataset_sha256')
    )
    if expected_evaluation_hash and evaluation_dataset_sha256 != expected_evaluation_hash:
        raise ValueError(
            'Evaluation dataset SHA-256 mismatch: ' + evaluation_dataset_sha256
        )
    if evaluation_dataset == training_dataset:
        if evaluation_dataset_sha256 != legacy.EXPECTED:
            raise ValueError('Locked local training dataset SHA-256 mismatch')
    else:
        schema_path = evaluation_dataset / 'schema.json'
        if not schema_path.is_file():
            raise FileNotFoundError(schema_path)
        legacy.DATA = evaluation_dataset
        schema = json.loads(schema_path.read_text(encoding='utf-8'))
        if end_time_step is None:
            end_time_step = int(schema['simulation_end_time_step'])
    if end_time_step is None:
        end_time_step = 719
    seed_all(seed)
    CLASSES = tuple(len(grid) for grid in p['action_grids'])
    env = make_env(start_time_step, end_time_step, seed)
    env.reset(seed=seed)
    # Optional execution rules consume the observed price forecast even when
    # the neural policy itself uses only current meters and local history.
    information_access = (
        'current_observations_local_history_and_declared_price_forecasts'
        if (predicted_price_charge_rule_override
            or predicted_price_discharge_gate_override)
        else 'current_observations_and_local_history')
    platform_context = capture_context(
        env, information_access=information_access)
    hist = FeatureHistory(len(env.buildings),4,p['history_enabled'],
                          p.get('history_dilation',1))
    before = readings(env); state = hist.encode(before)
    # 后续可选固定动作/保护规则会修改网络提案，日志应分别保留提案和执行命令。
    # 这些规则属于候选策略的一部分，不能在比较结果时忽略或隐去。
    fixed_cooling_schedule = None
    schedule_path = fixed_cooling_action_schedule_path
    if schedule_path is None and not disable_checkpoint_fixed_cooling_schedule:
        schedule_path = p.get("fixed_cooling_action_schedule_path")
    if schedule_path:
        expected_schedule_hash = p.get(
            "fixed_cooling_action_schedule_sha256")
        if (expected_schedule_hash
                and not allow_fixed_cooling_schedule_hash_override
                and hashlib.sha256(Path(schedule_path).read_bytes()).hexdigest()
                != expected_schedule_hash):
            raise ValueError("Fixed cooling action schedule hash mismatch")
        fixed_cooling_schedule = load_fixed_cooling_action_schedule(
            schedule_path, [b.name for b in env.buildings],
            common_grids(env)[2], end_time_step - start_time_step)
    fixed_dhw_schedule = None
    if fixed_dhw_action_schedule_path is not None:
        fixed_dhw_schedule = load_fixed_dhw_action_schedule(
            fixed_dhw_action_schedule_path, [b.name for b in env.buildings],
            common_grids(env)[0], end_time_step - start_time_step)
    actor_architecture = p.get('actor_architecture', 'shared')
    critic_objective = p.get('critic_objective', 'scalarized')
    runtime_grids = checkpoint_grids(env, p['action_grids'])
    learner = Learner(state.shape[-1], runtime_grids,
                      actor_architecture=actor_architecture,
                      critic_objective=critic_objective,
                      target_action_policy=p.get('target_action_policy', 'categorical'),
                      critic_replay_sampling=p.get('critic_replay_sampling', 'uniform'),
                      critic_replay_seed=p.get('seed', 0))
    if p.get('freeze_cooling_policy', False):
        learner.freeze_cooling_policy()
    learner.actor.load_state_dict(saved['actor'])
    if p.get('action_grids') != [grid.tolist() for grid in learner.grids]:
        raise ValueError('Evaluation action grids do not match the checkpoint')
    trajectory=[]; done=trunc=False; count=0
    evaluation_policy = p.get('evaluation_policy', 'argmax')
    if evaluation_policy != 'argmax':
        raise ValueError(f'Unsupported evaluation policy: {evaluation_policy}')
    high_price_charge_gate_enabled = (
        p.get('high_price_charge_gate', False)
        if high_price_charge_gate_override is None
        else high_price_charge_gate_override
    )
    high_price_charge_threshold = (
        float(p.get('high_price_charge_threshold', .02915))
        if high_price_charge_threshold_override is None
        else float(high_price_charge_threshold_override)
    )
    high_price_charge_reserve_soc = (
        float(p.get('high_price_charge_reserve_soc', .20))
        if high_price_charge_reserve_soc_override is None
        else float(high_price_charge_reserve_soc_override)
    )
    high_price_discharge_rule_enabled = bool(
        high_price_discharge_rule_override)
    high_price_discharge_reserve_soc = (
        .50 if high_price_discharge_reserve_soc_override is None
        else float(high_price_discharge_reserve_soc_override)
    )
    high_price_discharge_threshold = (
        .05867 if high_price_discharge_threshold_override is None
        else float(high_price_discharge_threshold_override)
    )
    high_price_discharge_action = (
        float(learner.grids[1][
            np.flatnonzero(learner.grids[1] < 0)[-1]
        ]) if high_price_discharge_action_override is None
        else float(high_price_discharge_action_override)
    )
    predicted_price_discharge_gate_enabled = bool(
        predicted_price_discharge_gate_override)
    predicted_price_discharge_min_spread = (
        0.0 if predicted_price_discharge_min_spread_override is None
        else float(predicted_price_discharge_min_spread_override))
    predicted_price_charge_rule_enabled = bool(
        predicted_price_charge_rule_override)
    predicted_price_charge_max_current_price = (
        0.03025 if predicted_price_charge_max_current_price_override is None
        else float(predicted_price_charge_max_current_price_override))
    predicted_price_charge_min_spread = (
        0.005 if predicted_price_charge_min_spread_override is None
        else float(predicted_price_charge_min_spread_override))
    predicted_price_charge_max_soc = (
        0.30 if predicted_price_charge_max_soc_override is None
        else float(predicted_price_charge_max_soc_override))
    predicted_price_charge_action = predicted_price_charge_action_override
    unoccupied_cooling_gate_enabled = (
        bool(p.get('unoccupied_cooling_gate', False))
        if unoccupied_cooling_gate_override is None
        else bool(unoccupied_cooling_gate_override)
    )
    unoccupied_cooling_gate_bins = int(
        p.get('unoccupied_cooling_gate_bins', 1)
        if unoccupied_cooling_gate_bins_override is None
        else unoccupied_cooling_gate_bins_override)
    unoccupied_cooling_gate_extra_bins = (
        unoccupied_cooling_gate_bins
        if unoccupied_cooling_gate_extra_bins is None
        else int(unoccupied_cooling_gate_extra_bins))
    if unoccupied_cooling_gate_extra_bins not in (1, 2):
        raise ValueError('Extra cooling gate reduction must be one or two bins')
    unoccupied_cooling_gate_building_index = (
        p.get('unoccupied_cooling_gate_building_index')
        if unoccupied_cooling_gate_building_index is None
        else unoccupied_cooling_gate_building_index)
    unoccupied_cooling_gate_min_steps = int(
        p.get('unoccupied_cooling_gate_min_steps', 0)
        if unoccupied_cooling_gate_min_steps_override is None
        else unoccupied_cooling_gate_min_steps_override)
    unoccupied_cooling_gate_comfort_margin = float(
        p.get('unoccupied_cooling_gate_comfort_margin', .5)
        if unoccupied_cooling_gate_comfort_margin_override is None
        else unoccupied_cooling_gate_comfort_margin_override)
    unoccupied_cooling_gate_price_threshold = float(
        p.get('unoccupied_cooling_gate_price_threshold', .02914999984204769)
        if unoccupied_cooling_gate_price_threshold_override is None
        else unoccupied_cooling_gate_price_threshold_override)
    unoccupied_cooling_gate_max_demand = (
        p.get('unoccupied_cooling_gate_max_cooling_demand')
        if unoccupied_cooling_gate_max_demand_override is None
        else unoccupied_cooling_gate_max_demand_override)
    if (unoccupied_cooling_gate_max_demand is not None
            and (not np.isfinite(unoccupied_cooling_gate_max_demand)
                 or unoccupied_cooling_gate_max_demand < 0.)):
        raise ValueError('Maximum cooling demand must be finite and nonnegative')
    if unoccupied_cooling_gate_extra_building_index is not None:
        if not unoccupied_cooling_gate_enabled:
            raise ValueError('The extra building gate requires the base cooling gate')
        if (unoccupied_cooling_gate_extra_min_demand_exclusive is None
                or unoccupied_cooling_gate_extra_max_demand is None
                or not np.isfinite(
                    unoccupied_cooling_gate_extra_min_demand_exclusive)
                or unoccupied_cooling_gate_extra_min_demand_exclusive < 0.
                or not np.isfinite(unoccupied_cooling_gate_extra_max_demand)
                or unoccupied_cooling_gate_extra_max_demand
                <= unoccupied_cooling_gate_extra_min_demand_exclusive):
            raise ValueError('The extra building gate requires a valid demand interval')
    if unoccupied_cooling_gate_extra_2_building_index is not None:
        if not unoccupied_cooling_gate_enabled:
            raise ValueError('The second extra building gate requires the base cooling gate')
        if (unoccupied_cooling_gate_extra_2_min_demand_exclusive is None
                or unoccupied_cooling_gate_extra_2_max_demand is None
                or unoccupied_cooling_gate_extra_2_min_demand_exclusive < 0.
                or unoccupied_cooling_gate_extra_2_max_demand
                <= unoccupied_cooling_gate_extra_2_min_demand_exclusive
                or unoccupied_cooling_gate_extra_2_bins not in (1, 2)):
            raise ValueError('The second extra building gate requires a valid demand interval')
    if unoccupied_cooling_gate_extra_3_building_index is not None:
        if not unoccupied_cooling_gate_enabled:
            raise ValueError('The third extra building gate requires the base cooling gate')
        if (unoccupied_cooling_gate_extra_3_min_demand_exclusive is None
                or unoccupied_cooling_gate_extra_3_max_demand is None
                or unoccupied_cooling_gate_extra_3_min_demand_exclusive < 0.
                or unoccupied_cooling_gate_extra_3_max_demand
                <= unoccupied_cooling_gate_extra_3_min_demand_exclusive
                or unoccupied_cooling_gate_extra_3_bins not in (1, 2)):
            raise ValueError('The third extra building gate requires a valid demand interval')
    unoccupied_cooling_gate_second_bin_comfort_margin = (
        p.get('unoccupied_cooling_gate_second_bin_comfort_margin')
        if unoccupied_cooling_gate_second_bin_comfort_margin_override is None
        else unoccupied_cooling_gate_second_bin_comfort_margin_override)
    if unoccupied_cooling_gate_second_bin_comfort_margin is not None:
        if (unoccupied_cooling_gate_bins != 2
                or not np.isfinite(
                    unoccupied_cooling_gate_second_bin_comfort_margin)
                or unoccupied_cooling_gate_second_bin_comfort_margin
                < unoccupied_cooling_gate_comfort_margin):
            raise ValueError(
                'Second-bin cooling margin requires two-bin reduction and '
                'must be at least the gate comfort margin')
    risk_profile_path = (
        unoccupied_cooling_gate_second_bin_risk_profile_path
        if unoccupied_cooling_gate_second_bin_risk_profile_path is not None
        else p.get('unoccupied_cooling_gate_second_bin_risk_profile_path'))
    risk_threshold = (
        unoccupied_cooling_gate_second_bin_risk_threshold
        if unoccupied_cooling_gate_second_bin_risk_threshold is not None
        else p.get('unoccupied_cooling_gate_second_bin_risk_threshold'))
    second_bin_allowed_hours = None
    risk_profile_sha256 = None
    risk_profile_payload = None
    if risk_profile_path is not None:
        if unoccupied_cooling_gate_bins != 2:
            raise ValueError('Occupancy risk profile requires two-bin cooling reduction')
        if risk_threshold is None or not np.isfinite(risk_threshold) or not 0. <= risk_threshold <= 1.:
            raise ValueError('Occupancy risk threshold must be in [0, 1]')
        risk_profile_path = Path(risk_profile_path).resolve()
        risk_profile_payload = json.loads(
            risk_profile_path.read_text(encoding='utf-8'))
        if risk_profile_payload.get('schema_version') != 1:
            raise ValueError('Unsupported cooling occupancy risk profile version')
        if risk_profile_payload.get('building_index') != unoccupied_cooling_gate_building_index:
            raise ValueError('Occupancy risk profile building scope mismatch')
        risk_values = risk_profile_payload.get('risk_probability_by_hour')
        if not isinstance(risk_values, dict) or not risk_values:
            raise ValueError('Occupancy risk profile has no hourly probabilities')
        parsed_risks = {}
        for hour, probability in risk_values.items():
            hour = int(hour)
            probability = float(probability)
            if hour < 0 or hour > 24 or not np.isfinite(probability) or not 0. <= probability <= 1.:
                raise ValueError('Invalid occupancy probability in risk profile')
            parsed_risks[hour] = probability
        second_bin_allowed_hours = {
            hour for hour, probability in parsed_risks.items()
            if probability < risk_threshold
        }
        risk_profile_sha256 = hashlib.sha256(
            risk_profile_path.read_bytes()).hexdigest()
    elif risk_threshold is not None:
        raise ValueError('Occupancy risk threshold requires a risk profile')
    unoccupied_streak = np.zeros(len(env.buildings), dtype=int)
    previous_temperature_delta = np.full(len(env.buildings), np.nan, dtype=float)
    outage_pulse_controller = None
    diagnostic_battery_fork = None
    diagnostic_fork_sha256 = None
    if outage_risk_pulse or diagnostic_battery_fork_path is not None:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent / 'experiments' /
                               'historical_piecewise_calibration_20261109'))
    if diagnostic_battery_fork_path is not None:
        if outage_risk_pulse:
            raise ValueError('Cannot combine a single-action diagnostic with a pulse policy')
        from diagnostic_battery_fork import DiagnosticBatteryFork
        diagnostic_path = Path(diagnostic_battery_fork_path)
        diagnostic_fork_sha256 = hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()
        diagnostic_battery_fork = DiagnosticBatteryFork(
            json.loads(diagnostic_path.read_text(encoding='utf-8')),
            evaluation_dataset_sha256)
    if outage_risk_pulse:
        from run_local_risk_pulse import Pulse
        outage_pulse_controller = Pulse()
    while not (done or trunc):
        proposal_ids, actions = learner.actions(state, deterministic=True)
        unoccupied_streak = np.where(
            np.asarray([o['occupant_count'] <= 0 for o in before]),
            unoccupied_streak + 1, 0)
        actions[:, 2] = np.clip(
            actions[:, 2] + float(p.get('cooling_offset', 0.0)),
            learner.grids[2].min(), learner.grids[2].max())
        actor_proposed_actions = actions.copy()
        executed_ids = proposal_ids.copy()
        actions, executed_ids = apply_fixed_cooling_action_schedule(
            actions, executed_ids, fixed_cooling_schedule, count,
            learner.grids[2])
        actions, executed_ids = apply_fixed_dhw_action_schedule(
            actions, executed_ids, fixed_dhw_schedule, count,
            learner.grids[0])
        proposed_actions=actions.copy()
        actions,cooling_gate=apply_unoccupied_cooling_gate(
            before,proposed_actions,learner.grids[2],count+1,
            enabled=unoccupied_cooling_gate_enabled,
            reduction_bins=unoccupied_cooling_gate_bins,
            building_index=unoccupied_cooling_gate_building_index,
            min_unoccupied_steps=unoccupied_cooling_gate_min_steps,
            unoccupied_streak=unoccupied_streak,
            comfort_margin=unoccupied_cooling_gate_comfort_margin,
            price_threshold=unoccupied_cooling_gate_price_threshold,
            second_bin_comfort_margin=(
                unoccupied_cooling_gate_second_bin_comfort_margin),
            second_bin_allowed_hours=second_bin_allowed_hours,
            max_cooling_demand=unoccupied_cooling_gate_max_demand)
        extra_cooling_gate = np.zeros(len(before), dtype=bool)
        if unoccupied_cooling_gate_extra_building_index is not None:
            extra_actions, extra_cooling_gate = apply_unoccupied_cooling_gate(
                before, proposed_actions, learner.grids[2], count + 1,
                enabled=unoccupied_cooling_gate_enabled,
                reduction_bins=unoccupied_cooling_gate_extra_bins,
                building_index=unoccupied_cooling_gate_extra_building_index,
                min_unoccupied_steps=unoccupied_cooling_gate_min_steps,
                unoccupied_streak=unoccupied_streak,
                comfort_margin=unoccupied_cooling_gate_comfort_margin,
                price_threshold=unoccupied_cooling_gate_price_threshold,
                second_bin_comfort_margin=(
                    unoccupied_cooling_gate_second_bin_comfort_margin),
                second_bin_allowed_hours=second_bin_allowed_hours,
                max_cooling_demand=(
                    unoccupied_cooling_gate_extra_max_demand),
                min_cooling_demand_exclusive=(
                    unoccupied_cooling_gate_extra_min_demand_exclusive))
            actions[extra_cooling_gate, 2] = extra_actions[
                extra_cooling_gate, 2]
            cooling_gate |= extra_cooling_gate
        extra_cooling_gate_2 = np.zeros(len(before), dtype=bool)
        if unoccupied_cooling_gate_extra_2_building_index is not None:
            extra_actions_2, extra_cooling_gate_2 = apply_unoccupied_cooling_gate(
                before, proposed_actions, learner.grids[2], count + 1,
                enabled=unoccupied_cooling_gate_enabled,
                reduction_bins=unoccupied_cooling_gate_extra_2_bins,
                building_index=unoccupied_cooling_gate_extra_2_building_index,
                min_unoccupied_steps=unoccupied_cooling_gate_min_steps,
                unoccupied_streak=unoccupied_streak,
                comfort_margin=unoccupied_cooling_gate_comfort_margin,
                price_threshold=unoccupied_cooling_gate_price_threshold,
                second_bin_comfort_margin=(
                    unoccupied_cooling_gate_second_bin_comfort_margin),
                second_bin_allowed_hours=second_bin_allowed_hours,
                max_cooling_demand=(
                    unoccupied_cooling_gate_extra_2_max_demand),
                min_cooling_demand_exclusive=(
                    unoccupied_cooling_gate_extra_2_min_demand_exclusive))
            actions[extra_cooling_gate_2, 2] = extra_actions_2[
                extra_cooling_gate_2, 2]
            cooling_gate |= extra_cooling_gate_2
        extra_cooling_gate_3 = np.zeros(len(before), dtype=bool)
        if unoccupied_cooling_gate_extra_3_building_index is not None:
            extra_actions_3, extra_cooling_gate_3 = apply_unoccupied_cooling_gate(
                before, proposed_actions, learner.grids[2], count + 1,
                enabled=unoccupied_cooling_gate_enabled,
                reduction_bins=unoccupied_cooling_gate_extra_3_bins,
                building_index=unoccupied_cooling_gate_extra_3_building_index,
                min_unoccupied_steps=unoccupied_cooling_gate_min_steps,
                unoccupied_streak=unoccupied_streak,
                comfort_margin=unoccupied_cooling_gate_comfort_margin,
                price_threshold=unoccupied_cooling_gate_price_threshold,
                second_bin_comfort_margin=(
                    unoccupied_cooling_gate_second_bin_comfort_margin),
                second_bin_allowed_hours=second_bin_allowed_hours,
                max_cooling_demand=(
                    unoccupied_cooling_gate_extra_3_max_demand),
                min_cooling_demand_exclusive=(
                    unoccupied_cooling_gate_extra_3_min_demand_exclusive))
            actions[extra_cooling_gate_3, 2] = extra_actions_3[
                extra_cooling_gate_3, 2]
            cooling_gate |= extra_cooling_gate_3
        cooling_gate_thermal_trend_blocked = np.zeros(
            len(before), dtype=bool)
        if unoccupied_cooling_gate_temp_rise_block_threshold is not None:
            threshold = float(
                unoccupied_cooling_gate_temp_rise_block_threshold)
            if not np.isfinite(threshold) or threshold < 0.:
                raise ValueError(
                    'Cooling temperature-rise threshold must be finite and nonnegative')
            cooling_gate_thermal_trend_blocked = (
                cooling_gate
                & np.isfinite(previous_temperature_delta)
                & (previous_temperature_delta >= threshold))
            actions[cooling_gate_thermal_trend_blocked, 2] = proposed_actions[
                cooling_gate_thermal_trend_blocked, 2]
            cooling_gate &= ~cooling_gate_thermal_trend_blocked
        cooling_action_before_cap = actions[:, 2].copy()
        actions,cooling_action_cap=apply_cooling_action_cap(
            actions, learner.grids[2], cooling_action_cap_override)
        actions, b1_cap_active = apply_b1_occupied_low_demand_cap(
            before, actions, learner.grids[2], b1_occupied_low_demand_cap)
        cooling_action_cap |= b1_cap_active
        actions,charge_gate=apply_high_price_charge_gate(
            before,actions,count+1,
            enabled=high_price_charge_gate_enabled,
            price_threshold=high_price_charge_threshold,
            reserve_soc=high_price_charge_reserve_soc)
        (actions, predicted_price_charge_rule
         ) = apply_predicted_price_charge_rule(
            before, actions, learner.grids[1],
            enabled=predicted_price_charge_rule_enabled,
            max_current_price=predicted_price_charge_max_current_price,
            min_price_spread=predicted_price_charge_min_spread,
            max_soc=predicted_price_charge_max_soc,
            action=predicted_price_charge_action,
            building_index=predicted_price_charge_building_index)
        predicted_price_charge_additional_rule = np.zeros(
            len(before), dtype=bool)
        if predicted_price_charge_additional_building_index is not None:
            (actions, predicted_price_charge_additional_rule
             ) = apply_predicted_price_charge_rule(
                before, actions, learner.grids[1],
                enabled=predicted_price_charge_rule_enabled,
                max_current_price=predicted_price_charge_max_current_price,
                min_price_spread=predicted_price_charge_min_spread,
                max_soc=predicted_price_charge_max_soc,
                action=predicted_price_charge_action,
                building_index=predicted_price_charge_additional_building_index)
            predicted_price_charge_rule |= predicted_price_charge_additional_rule
        (actions, predicted_price_discharge_gate
         ) = apply_predicted_price_discharge_gate(
            before, actions,
            enabled=predicted_price_discharge_gate_enabled,
            min_price_spread=predicted_price_discharge_min_spread,
            building_index=predicted_price_discharge_building_index)
        discharge_action = high_price_discharge_action
        (actions, high_price_discharge_gate,
         high_price_discharge_post_soc_blocked,
         predicted_post_soc_for_discharge_rule
         ) = apply_high_price_discharge_rule(
            before, actions, learner.grids[1],
            enabled=high_price_discharge_rule_enabled,
            price_threshold=high_price_discharge_threshold,
            reserve_soc=high_price_discharge_reserve_soc,
            action=discharge_action,
            building_index=high_price_discharge_building_index,
            storage_devices=[building.electrical_storage
                             for building in env.buildings],
            post_soc_floor=high_price_discharge_post_soc_floor,
            post_soc_floor_by_building=high_price_floor_by_building)
        for i in np.flatnonzero(cooling_gate | cooling_action_cap):
            executed_ids[i, 2] = int(np.abs(
                learner.grids[2] - actions[i, 2]).argmin())
        for i in np.flatnonzero(charge_gate):
            executed_ids[i, 1] = int(np.abs(
                learner.grids[1] - actions[i, 1]).argmin())
        if high_price_discharge_gate.any():
            executed_ids[high_price_discharge_gate, 1] = int(
                np.flatnonzero(
                    np.isclose(learner.grids[1], discharge_action, atol=1e-7)
                )[0]
            )
        if predicted_price_discharge_gate.any():
            executed_ids[predicted_price_discharge_gate, 1] = int(
                np.flatnonzero(np.isclose(learner.grids[1], 0., atol=1e-7))[0]
            )
        if predicted_price_charge_rule.any():
            for i in np.flatnonzero(predicted_price_charge_rule):
                executed_ids[i, 1] = int(np.abs(
                    learner.grids[1] - actions[i, 1]).argmin())
        battery_post_soc_floor_blocked = np.zeros(
            len(before), dtype=bool)
        predicted_post_soc_for_battery_floor = np.full(
            len(before), np.nan, dtype=float)
        if battery_post_soc_floor is not None:
            (actions, battery_post_soc_floor_blocked,
             predicted_post_soc_for_battery_floor
             ) = apply_battery_post_soc_floor(
                before, actions, learner.grids[1],
                [building.electrical_storage for building in env.buildings],
                battery_post_soc_floor,
                battery_post_soc_floor_building_index)
            for i in np.flatnonzero(battery_post_soc_floor_blocked):
                executed_ids[i, 1] = int(np.abs(
                    learner.grids[1] - actions[i, 1]).argmin())
        outage_pulse_reason = 'disabled'
        outage_pulse_gap = outage_pulse_credit = 0.
        outage_pulse_planned = float(actions[2, 1])
        if outage_pulse_controller is not None:
            device = env.buildings[2].electrical_storage
            a, outage_pulse_reason, outage_pulse_gap, _ = outage_pulse_controller.choose(
                before[2], device, learner.grids[1], outage_pulse_planned)
            actions[2, 1] = a
            executed_ids[2, 1] = int(np.abs(learner.grids[1] - a).argmin())
            outage_pulse_credit = outage_pulse_controller.credit
        diagnostic_fork_applied = False
        diagnostic_fork_planned = float(actions[2, 1])
        if diagnostic_battery_fork is not None:
            a, diagnostic_fork_applied = diagnostic_battery_fork.choose(
                before[2], env.buildings[2].electrical_storage, learner.grids[1],
                diagnostic_fork_planned, count + 1, predict_next_electrical_storage_soc)
            actions[2, 1] = a
            executed_ids[2, 1] = int(np.abs(learner.grids[1] - a).argmin())
        next_observation, rewards, done, trunc, info = env.step(actions.tolist())
        after=readings(env); count+=1
        if outage_pulse_controller is not None:
            outage_pulse_controller.settle(
                float(before[2]['electrical_storage_soc']),
                float(after[2]['electrical_storage_soc']),
                env.buildings[2].electrical_storage)
        previous_temperature_delta = np.asarray([
            float(after[i]['indoor_dry_bulb_temperature'])
            - float(before[i]['indoor_dry_bulb_temperature'])
            for i in range(len(before))
        ], dtype=float)
        hist.advance(before,actions,after); state=hist.encode(after)
        for i,(b,o) in enumerate(zip(env.buildings,after)):
            expected_energy = float(
                b.cooling_demand[b.time_step]
                + b.heating_demand[b.time_step]
                + b.dhw_demand[b.time_step]
                + b.non_shiftable_load[b.time_step])
            served_energy = float(
                b.energy_from_cooling_device[b.time_step]
                + b.energy_from_cooling_storage[b.time_step]
                + b.energy_from_heating_device[b.time_step]
                + b.energy_from_heating_storage[b.time_step]
                + b.energy_from_dhw_device[b.time_step]
                + b.energy_from_dhw_storage[b.time_step]
                + b.energy_to_non_shiftable_load[b.time_step])
            temp=float(o['indoor_dry_bulb_temperature']); band=float(o['comfort_band'])
            cold=temp<float(o['indoor_dry_bulb_temperature_heating_set_point'])-band
            hot=temp>float(o['indoor_dry_bulb_temperature_cooling_set_point'])+band
            trajectory.append(dict(step=count,building=b.name,
                source_timestep_before=start_time_step + count - 1,
                source_timestep_after=start_time_step + count,
                observation_json=json.dumps(_json_value(before[i]), sort_keys=True),
                next_observation_json=json.dumps(_json_value(after[i]), sort_keys=True),
                action_json=json.dumps({
                    'dhw_storage': float(actions[i, 0]),
                    'electrical_storage': float(actions[i, 1]),
                    'cooling_device': float(actions[i, 2]),
                }, sort_keys=True),
                reward=float(np.asarray(rewards).reshape(-1)[i]),
                terminated=bool(done),truncated=bool(trunc),
                environment_info_json=json.dumps(_json_value(info), sort_keys=True),
                proposed_action_ids_json=json.dumps(proposal_ids[i].tolist()),
                executed_action_ids_json=json.dumps(executed_ids[i].tolist()),
                proposed_action_json=json.dumps(
                    actor_proposed_actions[i].tolist()),
                proposed_cooling_action=float(actor_proposed_actions[i,2]),
                after_expected_energy=expected_energy,
                after_served_energy=served_energy,
                after_unserved_energy=max(expected_energy - served_energy, 0.0),
                after_cooling_demand_raw=float(b.cooling_demand[b.time_step]),
                after_heating_demand_raw=float(b.heating_demand[b.time_step]),
                after_dhw_demand_raw=float(b.dhw_demand[b.time_step]),
                after_non_shiftable_load_raw=float(b.non_shiftable_load[b.time_step]),
                execution_cooling_gate=bool(cooling_gate[i]),
                execution_cooling_gate_extra=bool(extra_cooling_gate[i]),
                execution_cooling_gate_extra_2=bool(extra_cooling_gate_2[i]),
                execution_cooling_gate_extra_3=bool(extra_cooling_gate_3[i]),
                execution_cooling_gate_thermal_trend_blocked=bool(
                    cooling_gate_thermal_trend_blocked[i]),
                before_previous_temperature_delta=(
                    float(previous_temperature_delta[i])
                    if np.isfinite(previous_temperature_delta[i]) else None),
                cooling_action_before_cap=float(cooling_action_before_cap[i]),
                execution_cooling_action_cap=bool(cooling_action_cap[i]),
                execution_high_price_charge_gate=bool(charge_gate[i]),
                execution_predicted_price_charge_rule=bool(
                    predicted_price_charge_rule[i]),
                execution_predicted_price_discharge_gate=bool(
                    predicted_price_discharge_gate[i]),
                execution_high_price_discharge_rule=bool(
                    high_price_discharge_gate[i]),
                execution_high_price_discharge_post_soc_blocked=bool(
                    high_price_discharge_post_soc_blocked[i]),
                predicted_post_soc_for_discharge_rule=(
                    float(predicted_post_soc_for_discharge_rule[i])
                    if np.isfinite(predicted_post_soc_for_discharge_rule[i])
                    else None),
                execution_battery_post_soc_floor_blocked=bool(
                    battery_post_soc_floor_blocked[i]),
                predicted_post_soc_for_battery_floor=(
                    float(predicted_post_soc_for_battery_floor[i])
                    if np.isfinite(predicted_post_soc_for_battery_floor[i])
                    else None),
                execution_fixed_cooling_action_schedule=(
                    fixed_cooling_schedule is not None),
                execution_fixed_dhw_action_schedule=(
                    fixed_dhw_schedule is not None),
                temperature=temp,
                occupied=int(float(o['occupant_count'])>0),cold=int(cold),hot=int(hot),
                net=float(o['net_electricity_consumption']),price=float(o['electricity_pricing']),
                cooling=float(o['cooling_electricity_consumption']),
                heating=float(o['heating_electricity_consumption']),dhw=float(o['dhw_electricity_consumption']),
                battery=float(o['electrical_storage_electricity_consumption']),
                dhw_storage=float(o['dhw_storage_electricity_consumption']),
                non_shiftable=float(o['non_shiftable_load']),solar=float(o['solar_generation']),
                dhw_action=float(actions[i,0]),battery_action=float(actions[i,1]),cooling_action=float(actions[i,2]),
                outage_risk_pulse_enabled=bool(outage_risk_pulse and i == 2),
                outage_risk_pulse_reason=outage_pulse_reason if i == 2 else 'not_target',
                outage_risk_pulse_planned_action=outage_pulse_planned if i == 2 else float(actions[i,1]),
                outage_risk_pulse_shortage_proxy_kwh=outage_pulse_gap if i == 2 else 0.,
                outage_risk_pulse_credit_dc_kwh=outage_pulse_credit if i == 2 else 0.,
                diagnostic_battery_fork_applied=bool(diagnostic_fork_applied and i == 2),
                diagnostic_battery_fork_mode=(
                    diagnostic_battery_fork.spec['mode']
                    if diagnostic_battery_fork is not None and i == 2 else 'disabled'),
                diagnostic_battery_fork_planned_action=(
                    diagnostic_fork_planned if i == 2 else float(actions[i,1])),
                environment_step_order=platform_context['protocol']['environment_step_order'],
                **settled_energy(b, platform_context['protocol']['environment_step_order']),
                **flat_observation_fields(before[i], after[i])))
        before=after
    if diagnostic_battery_fork is not None:
        diagnostic_battery_fork.finish()
    if count != end_time_step - start_time_step:
        raise ValueError(
            f'Expected {end_time_step - start_time_step} transitions, observed {count}'
        )
    training_dynamics_hashes = {
        name: hashlib.sha256((training_dataset / f'{name}.pth').read_bytes()).hexdigest()
        for name in (b.name for b in env.buildings)
        if (training_dataset / f'{name}.pth').is_file()
    }
    evaluation_dynamics_hashes = {
        name: hashlib.sha256((evaluation_dataset / f'{name}.pth').read_bytes()).hexdigest()
        for name in (b.name for b in env.buildings)
        if (evaluation_dataset / f'{name}.pth').is_file()
    }
    dataset_is_distinct = evaluation_dataset_sha256 != training_dataset_sha256
    result=dict(episode=saved['episode'],transitions=count,
                dataset_sha256=evaluation_dataset_sha256,
                training_dataset_sha256=training_dataset_sha256,
                training_dataset_path=str(training_dataset),
                evaluation_dataset_path=str(evaluation_dataset),
                evaluation_dataset_name=evaluation_dataset.name,
                evaluation_dataset_is_distinct=dataset_is_distinct,
                training_dynamics_model_sha256=training_dynamics_hashes,
                evaluation_dynamics_model_sha256=evaluation_dynamics_hashes,
                dynamics_assets_match_training_dataset=(
                    training_dynamics_hashes == evaluation_dynamics_hashes),
                simulation_window=[start_time_step, end_time_step],
                window_role=(
                    'distinct_dataset_shared_dynamics_assets'
                    if dataset_is_distinct and
                    training_dynamics_hashes == evaluation_dynamics_hashes
                    else 'distinct_dataset'
                    if dataset_is_distinct else
                    p.get('window_role', 'full_trajectory_historical_replay')),
                heldout_evaluated=dataset_is_distinct,
                checkpoint_sha256=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),
                evaluation_action_overrides={
                    'high_price_charge_gate': high_price_charge_gate_enabled,
                    'high_price_charge_threshold': high_price_charge_threshold,
                    'high_price_charge_reserve_soc': high_price_charge_reserve_soc,
                    'high_price_discharge_rule': (
                        high_price_discharge_rule_enabled),
                    'high_price_discharge_threshold': (
                        high_price_discharge_threshold),
                    'high_price_discharge_reserve_soc': (
                        high_price_discharge_reserve_soc),
                    'high_price_discharge_action': (
                        high_price_discharge_action),
                    'high_price_discharge_building_index': (
                        high_price_discharge_building_index),
                    'high_price_discharge_post_soc_floor': (
                        high_price_discharge_post_soc_floor),
                    'high_price_discharge_post_soc_floor_building_index': (
                        high_price_discharge_post_soc_floor_building_index),
                    'high_price_discharge_post_soc_floor_building_override': (
                        high_price_discharge_post_soc_floor_building_override),
                    'predicted_price_discharge_gate': (
                        predicted_price_discharge_gate_enabled),
                    'predicted_price_discharge_min_spread': (
                        predicted_price_discharge_min_spread),
                    'predicted_price_discharge_building_index': (
                        predicted_price_discharge_building_index),
                    'predicted_price_charge_rule': (
                        predicted_price_charge_rule_enabled),
                    'predicted_price_charge_max_current_price': (
                        predicted_price_charge_max_current_price),
                    'predicted_price_charge_min_spread': (
                        predicted_price_charge_min_spread),
                    'predicted_price_charge_max_soc': (
                        predicted_price_charge_max_soc),
                    'predicted_price_charge_building_index': (
                        predicted_price_charge_building_index),
                    'predicted_price_charge_additional_building_index': (
                        predicted_price_charge_additional_building_index),
                    'predicted_price_charge_action': (
                        predicted_price_charge_action),
                    'battery_post_soc_floor': battery_post_soc_floor,
                    'battery_post_soc_floor_building_index': (
                        battery_post_soc_floor_building_index),
                    'unoccupied_cooling_gate': (
                        unoccupied_cooling_gate_enabled),
                    'unoccupied_cooling_gate_bins': (
                        unoccupied_cooling_gate_bins),
                    'unoccupied_cooling_gate_min_steps': (
                        unoccupied_cooling_gate_min_steps),
                    'unoccupied_cooling_gate_comfort_margin': (
                        unoccupied_cooling_gate_comfort_margin),
                    'unoccupied_cooling_gate_price_threshold': (
                        unoccupied_cooling_gate_price_threshold),
                    'unoccupied_cooling_gate_max_cooling_demand': (
                        unoccupied_cooling_gate_max_demand),
                    'unoccupied_cooling_gate_second_bin_comfort_margin': (
                        unoccupied_cooling_gate_second_bin_comfort_margin),
                    'unoccupied_cooling_gate_second_bin_risk_profile_path': (
                        str(risk_profile_path)
                        if risk_profile_path is not None else None),
                    'unoccupied_cooling_gate_second_bin_risk_profile_sha256': (
                        risk_profile_sha256),
                    'unoccupied_cooling_gate_second_bin_risk_threshold': (
                        risk_threshold),
                    'unoccupied_cooling_gate_second_bin_allowed_hours': (
                        sorted(second_bin_allowed_hours)
                        if second_bin_allowed_hours is not None else None),
                    'unoccupied_cooling_gate_temp_rise_block_threshold': (
                        unoccupied_cooling_gate_temp_rise_block_threshold),
                    'unoccupied_cooling_gate_building_index': (
            unoccupied_cooling_gate_building_index),
                    'unoccupied_cooling_gate_extra_building_index': (
                        unoccupied_cooling_gate_extra_building_index),
                    'unoccupied_cooling_gate_extra_min_demand_exclusive': (
                        unoccupied_cooling_gate_extra_min_demand_exclusive),
                    'unoccupied_cooling_gate_extra_max_demand': (
                        unoccupied_cooling_gate_extra_max_demand),
                    'unoccupied_cooling_gate_extra_bins': (
                        unoccupied_cooling_gate_extra_bins
                        if unoccupied_cooling_gate_extra_building_index is not None
                        else None),
                    'unoccupied_cooling_gate_extra_2_building_index': (
                        unoccupied_cooling_gate_extra_2_building_index),
                    'unoccupied_cooling_gate_extra_2_min_demand_exclusive': (
                        unoccupied_cooling_gate_extra_2_min_demand_exclusive),
                    'unoccupied_cooling_gate_extra_2_max_demand': (
                        unoccupied_cooling_gate_extra_2_max_demand),
                    'unoccupied_cooling_gate_extra_2_bins': (
                        unoccupied_cooling_gate_extra_2_bins
                        if unoccupied_cooling_gate_extra_2_building_index is not None
                        else None),
                    'unoccupied_cooling_gate_extra_3_building_index': (
                        unoccupied_cooling_gate_extra_3_building_index),
                    'unoccupied_cooling_gate_extra_3_min_demand_exclusive': (
                        unoccupied_cooling_gate_extra_3_min_demand_exclusive),
                    'unoccupied_cooling_gate_extra_3_max_demand': (
                        unoccupied_cooling_gate_extra_3_max_demand),
                    'unoccupied_cooling_gate_extra_3_bins': (
                        unoccupied_cooling_gate_extra_3_bins
                        if unoccupied_cooling_gate_extra_3_building_index is not None
                        else None),
                    'cooling_action_cap': cooling_action_cap_override,
                    'b1_occupied_low_demand_cap': bool(b1_occupied_low_demand_cap),
                    'outage_risk_pulse': bool(outage_risk_pulse),
                    'diagnostic_battery_fork_path': (
                        str(Path(diagnostic_battery_fork_path).resolve())
                        if diagnostic_battery_fork_path else None),
                    'diagnostic_battery_fork_sha256': diagnostic_fork_sha256,
                    'fixed_cooling_action_schedule': bool(
                        fixed_cooling_schedule is not None),
                    'fixed_dhw_action_schedule': bool(
                        fixed_dhw_schedule is not None),
                    'fixed_dhw_action_schedule_path': (
                        str(Path(fixed_dhw_action_schedule_path).resolve())
                        if fixed_dhw_action_schedule_path else None),
                    'fixed_dhw_action_schedule_sha256': (
                        hashlib.sha256(
                            Path(fixed_dhw_action_schedule_path).read_bytes()
                        ).hexdigest()
                        if fixed_dhw_action_schedule_path else None),
                },
                **target_kpis(env, p.get('discomfort_target', .10),
                              p.get('cost_target', .90)))
    result['mechanism']={}
    for b in env.buildings:
        rows=[r for r in trajectory if r['building']==b.name]
        base=np.asarray(b.net_electricity_consumption_cost_without_storage_and_partial_load,dtype=float)
        bill=np.asarray(b.net_electricity_consumption_cost,dtype=float)
        denominator=float(np.maximum(base,0).sum()); cost=float(np.maximum(bill,0).sum()/denominator)
        temp=np.asarray(b.indoor_dry_bulb_temperature); occupied=np.asarray(b.occupant_count)>0
        cold=temp < np.asarray(b.indoor_dry_bulb_temperature_heating_set_point)-np.asarray(b.comfort_band)
        hot=temp > np.asarray(b.indoor_dry_bulb_temperature_cooling_set_point)+np.asarray(b.comfort_band)
        discomfort=float((occupied & (cold|hot)).sum()/occupied.sum())
        if abs(cost-result['per_building'][b.name]['cost_total'])>1.e-7 or abs(discomfort-result['per_building'][b.name]['discomfort_proportion'])>1.e-12:
            raise ValueError('Independent official KPI recomputation failed')
        result['mechanism'][b.name]=dict(occupied_cold=int((occupied&cold).sum()),occupied_hot=int((occupied&hot).sum()),
            occupied_count=int(occupied.sum()),baseline_cost=denominator,positive_bill=float(np.maximum(bill,0).sum()),
            training_cost_baseline=float(legacy.BASELINE_COSTS[b.name]),
            training_cost_baseline_relative_error=(
                float(legacy.BASELINE_COSTS[b.name]) / denominator - 1.),
            cooling_kwh=sum(r['cooling'] for r in rows),dhw_kwh=sum(r['dhw'] for r in rows),
            battery_charge_kwh=sum(max(r['battery'],0) for r in rows),
            battery_discharge_kwh=-sum(min(r['battery'],0) for r in rows),
            cost_recompute_error=abs(cost-result['per_building'][b.name]['cost_total']),
            discomfort_recompute_error=abs(discomfort-result['per_building'][b.name]['discomfort_proportion']))
    result['audit_log'] = dict(
        file=str(Path(output).with_suffix(
            '.csv.gz' if p.get('trajectory_log_compression') == 'gzip' else '.csv'
        ).resolve()),
        rows=len(trajectory), expected_rows=count * len(env.buildings),
        fields=['action_json','reward','observation_json','next_observation_json',
                'environment_info_json','terminated','truncated'])
    if len(trajectory) != count * len(env.buildings):
        raise ValueError('Per-step audit row count mismatch')
    normalize_undefined_resilience_kpis(result, {
        b.name: int(np.count_nonzero(np.asarray(b.power_outage_signal) > .5))
        for b in env.buildings}, {
        b.name: int(np.count_nonzero((np.asarray(b.power_outage_signal) > .5)
                                    & (np.asarray(b.occupant_count) > 0)))
        for b in env.buildings})
    from evaluation_contract import collect_runtime_audit
    platform_context['runtime_audit'] = collect_runtime_audit(env, platform_context)
    result['platform_context'] = platform_context
    result['platform_result'] = dict(
        algorithm='AACMADRL', policy_id=result['checkpoint_sha256'],
        protocol=platform_context['protocol'], per_building=collect_environment_metrics(env))
    result['platform_terminated'] = bool(env.terminated)
    output=Path(output);write_json(output,result)
    trajectory_path = Path(result['audit_log']['file'])
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    if p.get('trajectory_log_compression') == 'gzip':
        stream = gzip.open(trajectory_path, 'wt', newline='', encoding='utf-8')
    else:
        stream = trajectory_path.open('w', newline='', encoding='utf-8')
    with stream as f:
        w=csv.DictWriter(f,fieldnames=list(trajectory[0]));w.writeheader();w.writerows(trajectory)
    env.close()
    print(json.dumps(dict(state='evaluated',episode=saved['episode'],per_building=result['per_building'],
                         passed=result['all_buildings_meet_targets'])),flush=True)


def self_test():
    seed_all(41); d=49; actor=SharedActor(d); critic=SharedAttentionCritic(d)
    x=torch.randn(7,3,d); order=torch.tensor([2,0,1])
    ids,actions,_,_=actor.sample(x,True)
    torch.testing.assert_close(actor(x[:,order]),actor(x)[:,order],rtol=0,atol=0)
    torch.testing.assert_close(critic(x[:,order],actions[:,order]),critic(x,actions)[:,order],rtol=1.e-5,atol=1.e-6)
    same=x[:,0:1].expand(-1,3,-1)
    torch.testing.assert_close(actor(same)[:,0],actor(same)[:,2],rtol=0,atol=0)
    building_actor=BuildingHeadActor(d)
    assert building_actor(x).shape == (7,3,sum(CLASSES))
    assert len(building_actor.heads) == 3
    shared_source=SharedActor(d)
    six_head_actor=BuildingHeadActor(d,building_count=6)
    six_head_actor.initialize_from_shared_actor(shared_source.state_dict())
    six_states=torch.randn(2,6,d)
    shared_logits=shared_source(six_states.reshape(-1,d)).reshape(
        2,6,sum(CLASSES))
    torch.testing.assert_close(
        six_head_actor(six_states),shared_logits,rtol=1.e-5,atol=1.e-6)
    six_head_indices=torch.stack(
        [part.argmax(dim=-1) for part in six_head_actor(six_states).split(CLASSES,-1)],
        dim=-1)
    shared_indices=torch.stack(
        [part.argmax(dim=-1) for part in shared_logits.split(CLASSES,-1)],
        dim=-1)
    torch.testing.assert_close(six_head_indices,shared_indices,rtol=0,atol=0)
    assert six_head_actor(six_states).shape==(2,6,sum(CLASSES))
    six_head_learner=Learner(
        d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES],
        actor_architecture='building_heads',actor_building_count=6,
        critic_objective='separate')
    six_head_learner.actor.initialize_from_shared_actor(shared_source.state_dict())
    six_head_learner.reference_actor=copy.deepcopy(six_head_learner.actor)
    six_head_learner.behavior_kl_penalty=1.0
    six_head_learner.cost_weights=np.ones(6,dtype=np.float32)
    six_head_learner.discomfort_weights=np.ones(6,dtype=np.float32)
    six_replay=JointReplay()
    for step in range(300):
        six_replay.push(
            np.full((6,d),step,dtype=np.float32),
            np.zeros((6,3),dtype=np.int64),
            np.tile(np.asarray([.1,.2,.3],dtype=np.float32),(6,1)),
            np.full((6,d),step+1,dtype=np.float32),False,1,step)
    six_head_learner.replay=six_replay
    six_head_learner.update()
    assert all(torch.isfinite(parameter).all()
               for parameter in six_head_learner.actor.parameters())
    assert all(torch.isfinite(parameter).all()
               for parameter in six_head_learner.critic.parameters())
    q=torch.arange(sum(CLASSES)).float().view(1,1,-1)
    selected=branch_values(q,torch.tensor([[[2,3,4]]]))
    torch.testing.assert_close(selected,torch.tensor([[[2.,24.,46.]]]))
    q_multi=torch.cat([q,q+100.,q+200.],dim=-1)
    selected_multi=branch_values_multi(q_multi,torch.tensor([[[2,3,4]]]))
    torch.testing.assert_close(
        selected_multi,
        torch.tensor([[[[2.,102.,202.],[24.,124.,224.],[46.,146.,246.]]]]))
    replay=JointReplay()
    for t in range(300):
        replay.push(np.full((3,d),t,dtype=np.float32),np.zeros((3,3),dtype=np.int64),
                    np.zeros((3,3),dtype=np.float32),np.full((3,d),t+1,dtype=np.float32),False,1,t)
    (s,_,_,_,_,_,steps,_),_=replay.sample(256)
    assert np.all(s[:,:,0] == steps[:,None])
    accumulator=NStepAccumulator(3,.99)
    r0=np.zeros((3,3),dtype=np.float32)
    ready=accumulator.append(np.zeros((3,d),np.float32),np.zeros((3,3),np.int64),
                             r0,np.ones((3,d),np.float32),False,1,1)
    assert not ready
    accumulator.append(np.ones((3,d),np.float32),np.zeros((3,3),np.int64),
                       r0,np.ones((3,d),np.float32)*2,False,1,2)
    ready=accumulator.append(np.ones((3,d),np.float32)*2,np.zeros((3,3),np.int64),
                             r0,np.ones((3,d),np.float32)*3,True,1,3)
    assert len(ready)==3 and ready[0][-1]==3 and ready[-1][-1]==1
    truncated=NStepAccumulator(3,.99)
    for t in range(3):
        ready=truncated.append(
            np.full((3,d),t,dtype=np.float32),np.zeros((3,3),np.int64),
            np.full((3,3),t+1,dtype=np.float32),
            np.full((3,d),t+1,dtype=np.float32),False,2,t+1,
            episode_end=(t==2))
    assert len(ready)==3
    assert [row[-1] for row in ready]==[3,2,1]
    assert all(row[4] is False for row in ready)
    assert all(row[3][0,0]==3 for row in ready)
    learner=Learner(d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES]);learner.replay=replay
    old=[v.detach().clone() for v in learner.actor.parameters()];learner.update()
    assert any(not torch.equal(a,b) for a,b in zip(old,learner.actor.parameters()))
    assert all(torch.isfinite(v).all() for v in learner.actor.parameters())
    head_learner=Learner(
        d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES],
        actor_architecture='building_heads')
    head_learner.replay=replay
    head_old=[v.detach().clone() for v in head_learner.actor.parameters()]
    head_learner.update()
    assert any(not torch.equal(a,b) for a,b in zip(head_old,head_learner.actor.parameters()))
    assert all(torch.isfinite(v).all() for v in head_learner.actor.parameters())
    separate_learner=Learner(
        d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES],
        critic_objective='separate')
    separate_learner.critic.initialize_from_scalarized(learner.critic.state_dict())
    torch.testing.assert_close(
        separate_learner.critic.state.state_dict()['0.weight'],
        learner.critic.state.state_dict()['0.weight'])
    assert all(torch.count_nonzero(head.weight) == 0
               and torch.count_nonzero(head.bias) == 0
               for head in separate_learner.critic.objective_heads)
    multi_replay=JointReplay()
    for t in range(300):
        multi_replay.push(
            np.full((3,d),t,dtype=np.float32),np.zeros((3,3),dtype=np.int64),
            np.tile(np.asarray([.1,.2,.3],dtype=np.float32),(3,1)),
            np.full((3,d),t+1,dtype=np.float32),False,1,t)
    separate_learner.replay=multi_replay
    separate_old=[v.detach().clone() for v in separate_learner.actor.parameters()]
    separate_learner.update()
    assert any(not torch.equal(a,b) for a,b in zip(
        separate_old,separate_learner.actor.parameters()))
    assert all(torch.isfinite(v).all() for v in separate_learner.actor.parameters())
    assert all(torch.isfinite(v).all() for v in separate_learner.critic.parameters())
    frozen_learner=Learner(
        d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES],
        critic_objective='separate',freeze_actor_updates=True)
    frozen_learner.replay=multi_replay
    frozen_actor=[v.detach().clone() for v in frozen_learner.actor.parameters()]
    frozen_target_actor=[v.detach().clone()
                         for v in frozen_learner.target_actor.parameters()]
    frozen_critic=[v.detach().clone() for v in frozen_learner.critic.parameters()]
    frozen_learner.update()
    assert all(torch.equal(old,new) for old,new in zip(
        frozen_actor,frozen_learner.actor.parameters()))
    assert all(torch.equal(old,new) for old,new in zip(
        frozen_target_actor,frozen_learner.target_actor.parameters()))
    assert any(not torch.equal(old,new) for old,new in zip(
        frozen_critic,frozen_learner.critic.parameters()))
    assert frozen_learner.last_losses['actor_update_skipped']
    kl_learner=Learner(
        d,[np.linspace(-1,1,n).astype(np.float32) for n in CLASSES],
        behavior_kl_penalty=.1)
    kl_learner.replay=replay
    kl_learner.reference_actor=copy.deepcopy(kl_learner.actor)
    for parameter in kl_learner.reference_actor.parameters():
        parameter.requires_grad_(False)
    with torch.no_grad():
        kl_learner.actor.net[-1].bias[0].add_(1.)
    kl_learner.update()
    assert kl_learner.last_losses['behavior_kl'] > 0.
    assert all(parameter.grad is None for parameter in kl_learner.reference_actor.parameters())
    metrics = {'a': {'cost_total': 1.8, 'discomfort_proportion': 0.2},
               'b': {'cost_total': 0.45, 'discomfort_proportion': 0.05},
               'c': {'cost_total': 0.9, 'discomfort_proportion': 0.1}}
    cw,dw=update_constraint_weights(np.ones(3),np.ones(3),metrics,['a','b','c'],.2,1.1)
    np.testing.assert_allclose(cw,[1.1,.9,1.],atol=1.e-6)
    np.testing.assert_allclose(dw,[1.1,.9,1.],atol=1.e-6)
    cw_margin,dw_margin=update_constraint_weights(
        np.ones(3),np.ones(3),metrics,['a','b','c'],.2,4.,.85,.08)
    assert cw_margin[2]>1. and dw_margin[2]>1.
    cw_separate,dw_separate=update_constraint_weights(
        np.ones(3),np.ones(3),metrics,['a','b','c'],.2,4.,.85,.08,.4)
    np.testing.assert_allclose(cw_separate, cw_margin, atol=1.e-6)
    np.testing.assert_allclose(dw_separate, 1. + 2. * (dw_margin - 1.), atol=1.e-6)
    assert update_comfort_priority_scale(
        0., metrics, ['a','b','c'], .10, .08) == (0., 0)
    release_metrics = {
        'a': {'discomfort_proportion': .079},
        'b': {'discomfort_proportion': .071},
        'c': {'discomfort_proportion': .02},
    }
    assert update_comfort_priority_scale(
        0., release_metrics, ['a','b','c'], .10, .10, 0, 2) == (0., 1)
    assert update_comfort_priority_scale(
        0., release_metrics, ['a','b','c'], .10, .08, 1, 2) == (1., 2)
    assert update_comfort_priority_scale(
        0., release_metrics, ['a','b','c'], .10, .08, 1, 2, .25) == (.25, 2)
    assert update_comfort_priority_scale(
        .25, release_metrics, ['a','b','c'], .10, .08, 2, 2, .25) == (.25, 2)
    wobble_metrics = dict(release_metrics, a={'discomfort_proportion': .095})
    assert update_comfort_priority_scale(
        1., wobble_metrics, ['a','b','c'], .10, .08) == (1., 2)
    wobble_metrics['a']['discomfort_proportion'] = .10
    assert update_comfort_priority_scale(
        1., wobble_metrics, ['a','b','c'], .10, .08) == (0., 0)
    assert apply_actor_cost_advantage_freeze(1., True) == 0.
    assert apply_actor_cost_advantage_freeze(.5, False) == .5
    sample=np.array([[[1.,2.,.5],[3.,4.,.25],[5.,6.,0.]]],dtype=np.float32)
    np.testing.assert_allclose(weighted_reward(sample,np.ones(3),np.ones(3)),
                               [[-35.,-72.5,-110.]])
    np.testing.assert_allclose(weighted_reward(sample,np.array([2.,1.,1.]),
                                               np.array([1.,.5,1.])),
                               [[-45.,-52.5,-110.]])
    relabel_replay=JointReplay(capacity=1)
    relabel_replay.push(np.zeros((3,d),np.float32),np.zeros((3,3),np.int64),
                        sample[0],np.ones((3,d),np.float32),False,3,7)
    sampled= relabel_replay.sample(1)[0][2]
    updated_cost,updated_discomfort=update_constraint_weights(
        np.ones(3),np.ones(3),
        {'a':{'cost_total':1.8,'discomfort_proportion':.2},
         'b':{'cost_total':.45,'discomfort_proportion':.05},
         'c':{'cost_total':.9,'discomfort_proportion':.1}},
        ['a','b','c'],.2,4.)
    np.testing.assert_allclose(weighted_reward(
        sampled,updated_cost,updated_discomfort),
        [[-41.,-65.5,-110.]],atol=1.e-5)
    base=dict(indoor_dry_bulb_temperature=25.5,
              indoor_dry_bulb_temperature_cooling_set_point=24.,
              indoor_dry_bulb_temperature_heating_set_point=20.,
              comfort_band=2.,occupant_count=1.)
    np.testing.assert_allclose(comfort_boundary_risk([base,dict(base,occupant_count=0.)]),
                               [.05,0.],atol=1.e-7)
    risk_cost = boundary_risk_penalty([base], .1)
    np.testing.assert_allclose(risk_cost, [.005], atol=1.e-7)
    np.testing.assert_allclose(boundary_risk_penalty([base], 0.), [0.], atol=1.e-7)
    assert weighted_reward(np.array([[0., 0., risk_cost[0]]]), np.ones(3),
                           np.ones(3))[0] < weighted_reward(
                               np.zeros((1,3)), np.ones(3), np.ones(3))[0]
    storage_reversal = storage_reversal_penalty(
        [[-.3, .4]], [.10], [[.4, -.2]], [.10], .02)
    np.testing.assert_allclose(storage_reversal, [.01], atol=1.e-7)
    assert weighted_reward(np.array([[0., 0., storage_reversal[0]]]), np.ones(3),
                           np.ones(3))[0] < weighted_reward(
                               np.zeros((1,3)), np.ones(3), np.ones(3))[0]
    np.testing.assert_allclose(storage_reversal_penalty(
        [[-.3, 0.]], [.11], [[.4, 0.]], [.10], .02), [0.], atol=1.e-7)
    np.testing.assert_allclose(storage_reversal_penalty(
        [[0., .4]], [.09], [[0., -.2]], [.10], .02), [0.], atol=1.e-7)
    np.testing.assert_allclose(
        occupied_hot_margin_potential([base,dict(base,occupant_count=0.)]),
        [.05,0.],atol=1.e-7)
    cold_only=dict(base,indoor_dry_bulb_temperature=16.)
    np.testing.assert_allclose(occupied_hot_margin_potential([cold_only]),[0.])
    np.testing.assert_allclose(
        occupied_hot_margin_potential(
            [dict(base,indoor_dry_bulb_temperature=27.)]),
        [.2],atol=1.e-7)
    np.testing.assert_allclose(
        symmetric_plus_hot_margin_potential([base]),[.0125],atol=1.e-7)
    np.testing.assert_allclose(
        symmetric_plus_hot_margin_potential([cold_only]),
        thermal_potential([cold_only]),atol=1.e-7)
    probe=np.zeros((3,d),dtype=np.float32)
    greedy,_=learner.actions(probe, deterministic=True)
    guided,_=learner.actions(probe, explore=True, behavior_policy='epsilon_greedy', epsilon=0.0)
    np.testing.assert_array_equal(greedy,guided)
    _,guided_random=learner.actions(probe, explore=True,
                                    behavior_policy='epsilon_greedy', epsilon=1.0)
    assert guided_random.shape == (3, 3)
    env=make_env();env.reset(seed=41);obs=readings(env)
    hist=FeatureHistory(len(env.buildings),4,True)
    encoded=hist.encode(obs);assert encoded.shape==(3,49)
    grids=common_grids(env)
    for space in env.action_space:
        for h,g in enumerate(grids):
            assert g.min()>=space.low[h]-1.e-7 and g.max()<=space.high[h]+1.e-7
    actions=[[0.,0.,0.] for _ in env.buildings]
    env.step(actions);after=readings(env);hist.advance(obs,actions,after)
    assert np.all(hist.encode(after)[:,-1]==1.)
    hist.reset();assert np.all(hist.encode(after)[:,len(FEATURE_NAMES):]==0.)
    long_hist=FeatureHistory(1,4,True,dilation=3)
    long_hist.history[0].extend(
        [[float(i)] * len(HISTORY_NAMES) for i in range(10)])
    np.testing.assert_array_equal(
        long_hist.encode([obs[0]])[0, len(FEATURE_NAMES):],
        np.asarray([[0.] * 7, [3.] * 7, [6.] * 7, [9.] * 7]).reshape(-1))
    env.close()
    print(json.dumps(dict(state='self_test_passed',checks=['shared_actor_identity','permutation_equivariance',
          'action_head_offsets','joint_replay_time_alignment','finite_real_optimizer_update',
          'real_environment_feature_interface','common_legal_grids','episode_history_reset',
          'projected_dual_update','replay_reward_reweighting','comfort_boundary_risk',
          'comfort_priority_hysteresis',
          'occupied_hot_margin_potential',
          'symmetric_plus_hot_margin_potential',
          'building_specific_actor_heads','nonzero_behavior_kl_update',
          'separate_objective_critic_update','actor_freeze_critic_update',
          'scalarized_critic_warmstart',
          'dilated_history_sampling','six_building_actor_head_warmstart',
          'six_building_separate_critic_update'])),flush=True)


def train(args):
    global CLASSES
    # 总路线：设置种子/数据 -> 建环境及学习器 -> 初始评估 -> 探索采样/更新 -> 逐轮评估。
    # env.step推进建筑状态，learner.update改变网络，两种“更新”发生在不同对象上。
    # 参数与检查点必须一起保存，否则无法说明评估模型究竟怎样训练得到。
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    if legacy is None:
        raise RuntimeError(
            'Phase 2 training requires the Phase 2 CityLearn custom agent package'
        )
    if legacy.digest_data()!=legacy.EXPECTED: raise ValueError('Locked data hash mismatch')
    schema = json.loads((legacy.DATA / 'schema.json').read_text(encoding='utf-8'))
    if not (int(schema.get('simulation_start_time_step', 0)) <= args.simulation_start_time_step
            < args.simulation_end_time_step <= int(schema['simulation_end_time_step'])):
        raise ValueError('Simulation window exceeds selected dataset bounds')
    seed_all(args.seed)
    env=make_env(args.simulation_start_time_step, args.simulation_end_time_step, args.seed)
    env.reset(seed=args.seed);before=readings(env)
    potential_before=thermal_potential(before)
    history=FeatureHistory(
        len(env.buildings),4,args.history,args.history_dilation)
    state=history.encode(before)
    if (not np.isfinite(args.actor_lr) or args.actor_lr <= 0
            or not np.isfinite(args.critic_lr) or args.critic_lr <= 0):
        raise ValueError('Actor and critic learning rates must be finite and positive')
    if (not np.isfinite(args.discount) or not 0. <= args.discount <= 1.
            or not np.isfinite(args.tau) or not 0. < args.tau <= 1.
            or not np.isfinite(args.reward_scale) or args.reward_scale <= 0.):
        raise ValueError('Discount/tau/reward scale are outside valid ranges')
    if not np.isfinite(args.entropy_penalty) or args.entropy_penalty < 0:
        raise ValueError('Entropy penalty must be finite and non-negative')
    if not np.isfinite(args.behavior_kl_penalty) or args.behavior_kl_penalty < 0:
        raise ValueError('Behavior KL penalty must be finite and non-negative')
    if args.init_checkpoint and not args.init_checkpoint.is_file():
        raise FileNotFoundError(args.init_checkpoint)
    if args.behavior_kl_penalty > 0 and not args.init_checkpoint:
        raise ValueError('Behavior KL penalty requires --init-checkpoint')
    if args.freeze_cooling_policy and not args.init_checkpoint:
        raise ValueError('--freeze-cooling-policy requires an anchor --init-checkpoint')
    if args.fixed_cooling_action_schedule and not args.freeze_cooling_policy:
        raise ValueError(
            '--fixed-cooling-action-schedule requires --freeze-cooling-policy'
        )
    saved_init = None
    training_grids = common_grids(env)
    if args.init_checkpoint:
        saved_init = torch.load(args.init_checkpoint, map_location='cpu', weights_only=False)
        if saved_init['version'] not in COMPATIBLE_VERSIONS:
            raise ValueError('Initialization checkpoint version mismatch')
        # A categorical head's index denotes the checkpoint's physical command,
        # not a new runtime linspace. Match evaluation's legal-bound validation.
        training_grids = checkpoint_grids(env, saved_init.get('protocol', {}).get('action_grids'))
        CLASSES = tuple(len(grid) for grid in training_grids)
    learner=Learner(state.shape[-1],training_grids,actor_lr=args.actor_lr,
                    critic_lr=args.critic_lr, discount=args.discount,
                    tau=args.tau, reward_scale=args.reward_scale,
                    entropy_penalty=args.entropy_penalty,
                    behavior_kl_penalty=args.behavior_kl_penalty,
                    actor_architecture=args.actor_architecture,
                    actor_building_count=len(env.buildings),
                    critic_objective=args.critic_objective,
                    critic_own_action_context=args.critic_own_action_context,
                    target_action_policy=args.target_action_policy,
                    critic_replay_sampling=args.critic_replay_sampling,
                    critic_replay_seed=args.seed,
                    batch_size=args.batch_size,
                    freeze_actor_updates=args.freeze_actor_updates)
    fixed_cooling_schedule = None
    if args.fixed_cooling_action_schedule:
        fixed_cooling_schedule = load_fixed_cooling_action_schedule(
            args.fixed_cooling_action_schedule,
            [b.name for b in env.buildings],
            learner.grids[2],
            args.simulation_end_time_step - args.simulation_start_time_step,
        )
        learner.fixed_cooling_schedule = fixed_cooling_schedule
    if args.battery_post_soc_floor is not None:
        if args.critic_objective != 'separate':
            raise ValueError(
                'Battery SOC floor training requires --critic-objective separate'
            )
        if fixed_cooling_schedule is None:
            raise ValueError(
                'Battery SOC floor training requires a fixed cooling schedule'
            )
        learner.configure_battery_post_soc_floor(
            args.battery_post_soc_floor,
            args.battery_post_soc_floor_building_index,
            [building.electrical_storage for building in env.buildings],
        )
    if args.comfort_priority and args.critic_objective != 'separate':
        raise ValueError('--comfort-priority requires --critic-objective separate')
    if args.init_checkpoint:
        init_grids=saved_init.get('protocol',{}).get('action_grids')
        if init_grids != [g.tolist() for g in learner.grids]:
            raise ValueError('Initialization action grids do not match')
        saved_frozen = saved_init.get('protocol', {}).get('freeze_cooling_policy', False)
        if saved_frozen:
            if not args.freeze_cooling_policy:
                raise ValueError('Cannot discard a saved frozen cooling controller')
            learner.freeze_cooling_policy()
        learner.actor.load_state_dict(saved_init['actor'])
        learner.target_actor.load_state_dict(saved_init.get('target_actor',saved_init['actor']))
        saved_critic_objective = saved_init.get('protocol', {}).get(
            'critic_objective', 'scalarized')
        saved_critic = saved_init['critic']
        saved_target_critic = saved_init.get('target_critic', saved_critic)
        if learner.critic_objective == saved_critic_objective:
            if learner.critic_objective == 'separate':
                learner.critic.load_compatible_state_dict(saved_critic)
                learner.target_critic.load_compatible_state_dict(saved_target_critic)
            else:
                learner.critic.load_state_dict(saved_critic)
                learner.target_critic.load_state_dict(saved_target_critic)
        elif (learner.critic_objective == 'separate'
              and saved_critic_objective == 'scalarized'):
            learner.critic.initialize_from_scalarized(saved_critic)
            learner.target_critic.initialize_from_scalarized(saved_target_critic)
        else:
            raise ValueError('Cannot warm-start between these critic objectives')
        if args.freeze_cooling_policy and not saved_frozen:
            learner.freeze_cooling_policy()
        if args.behavior_kl_penalty > 0:
            learner.reference_actor=copy.deepcopy(learner.actor)
            for parameter in learner.reference_actor.parameters():
                parameter.requires_grad_(False)
    if args.n_step < 1:
        raise ValueError('n_step must be positive')
    accumulator=NStepAccumulator(args.n_step, learner.discount)
    learner.discomfort_weights.fill(args.discomfort_weight)
    if args.comfort_priority:
        learner.actor_cost_objective_scale = 0.0
    if args.freeze_actor_cost_advantage and not args.comfort_priority:
        raise ValueError('--freeze-actor-cost-advantage requires --comfort-priority')
    if args.init_checkpoint and saved_init.get('dual_multipliers'):
        multipliers = saved_init['dual_multipliers']
        cost_weights = np.asarray(multipliers['cost'], dtype=np.float32)
        discomfort_weights = np.asarray(multipliers['discomfort'], dtype=np.float32)
        if (cost_weights.shape != (len(env.buildings),)
                or discomfort_weights.shape != (len(env.buildings),)
                or not np.isfinite(cost_weights).all()
                or not np.isfinite(discomfort_weights).all()
                or (cost_weights < 0).any()
                or (discomfort_weights < 0).any()):
            raise ValueError('Invalid initialization dual multipliers')
        learner.cost_weights = cost_weights
        learner.discomfort_weights = discomfort_weights
    discomfort_dual_lr = (args.dual_lr if args.discomfort_dual_lr is None
                          else args.discomfort_dual_lr)
    if (args.dual_lr < 0 or discomfort_dual_lr < 0
            or args.dual_max <= 0 or args.discomfort_weight < 0
            or args.dual_start_episode < 1
            or not (0 < args.dual_cost_target <= .9)
            or not (0 < args.dual_discomfort_target <= .1)):
        raise ValueError('Invalid constraint weight settings')
    if args.behavior_policy not in ('categorical', 'epsilon_greedy'):
        raise ValueError(f'Unsupported training behavior policy: {args.behavior_policy}')
    protocol=dict(version=VERSION,history_enabled=args.history,history_steps=4,
        history_dilation=args.history_dilation,
        history_span_transitions=1+3*args.history_dilation,seed=args.seed,
        episodes=args.episodes,eval_episodes=[0,5,10,20,30],dataset_sha256=legacy.EXPECTED,
        training_dataset_path=str(Path(legacy.DATA).resolve()),
        evaluation_dataset_path=(
            str(args.evaluation_dataset) if args.evaluation_dataset else None),
        evaluation_dataset_sha256=(
            args.evaluation_dataset_sha256 if args.evaluation_dataset else None),
        evaluation_dataset_name=(
            args.evaluation_dataset.name if args.evaluation_dataset else None),
        trajectory_log_compression='gzip',
        training_feedback_dataset='local_training_dataset_only',
        state_window=[args.simulation_start_time_step,args.simulation_end_time_step],
        transitions_per_episode=args.simulation_end_time_step-args.simulation_start_time_step,
        window_role=args.window_role, heldout_evaluated=False,
        discomfort_target=float(args.discomfort_target),
        cost_target=float(args.cost_target),
        feature_names=FEATURE_NAMES,
        history_feature_names=HISTORY_NAMES,input_dimension=int(state.shape[-1]),
        preprocessing='same fixed physical scales for all buildings; no fitted statistics',
        actor_architecture=args.actor_architecture,
        actor=('one shared 64x64 network' if args.actor_architecture == 'shared'
               else 'shared 64x64 encoder with three building-specific action heads'),
        critic_objective=args.critic_objective,
        critic_own_action_context=args.critic_own_action_context,
        critic=('shared encoders and one-head attention with a scalarized value head'
                if args.critic_objective == 'scalarized'
                else 'shared encoders and one-head attention with separate cost, discomfort, and shaping value heads'),
        action_grids=[g.tolist() for g in learner.grids],
        action_grid_rule=('saved checkpoint commands within shared legal bounds'
                          if args.init_checkpoint else 'same intersection of legal bounds for every building'),
        reward=('fixed-baseline cost proxy and official discomfort component, plus optional '
                'potential shaping; -10*sum(components)'),
        training_cost_baseline_by_building={
            name: float(legacy.BASELINE_COSTS[name])
            for name in [b.name for b in env.buildings]},
        training_occupied_counts_by_building={
            b.name: float(env.reward_function.occupied_counts[i])
            for i, b in enumerate(env.buildings)},
        cost_normalization_note=(
            'Training uses a fixed baseline-cost reference. Official cost_total '
            'recomputes its denominator from each evaluated policy trajectory; '
            'the training cost proxy is therefore not exactly identical to the KPI.'),
        discomfort_training_weight=float(args.discomfort_weight),
        dual_learning_rate=float(args.dual_lr),
        discomfort_dual_learning_rate=float(discomfort_dual_lr),
        dual_maximum=float(args.dual_max),
        dual_start_episode=int(args.dual_start_episode),
        dual_cost_target=float(args.dual_cost_target),
        dual_discomfort_target=float(args.dual_discomfort_target),
        cooling_offset=float(args.cooling_offset),
        fixed_cooling_action_schedule_path=(
            str(args.fixed_cooling_action_schedule.resolve())
            if args.fixed_cooling_action_schedule else None),
        fixed_cooling_action_schedule_sha256=(
            hashlib.sha256(args.fixed_cooling_action_schedule.read_bytes()).hexdigest()
            if args.fixed_cooling_action_schedule else None),
        unoccupied_cooling_gate=bool(args.unoccupied_cooling_gate),
        unoccupied_cooling_gate_bins=int(args.unoccupied_cooling_gate_bins),
        unoccupied_cooling_gate_building_index=(
            args.unoccupied_cooling_gate_training_building_index),
        unoccupied_cooling_gate_min_steps=int(
            args.unoccupied_cooling_gate_training_min_unoccupied_steps),
        unoccupied_cooling_gate_comfort_margin=float(
            args.unoccupied_cooling_gate_training_comfort_margin),
        unoccupied_cooling_gate_second_bin_comfort_margin=(
            args.unoccupied_cooling_gate_training_second_bin_comfort_margin),
        unoccupied_cooling_gate_max_cooling_demand=(
            args.unoccupied_cooling_gate_training_max_demand),
        high_price_charge_gate=bool(args.high_price_charge_gate),
        high_price_charge_threshold=float(args.high_price_charge_threshold),
        high_price_charge_reserve_soc=float(args.high_price_charge_reserve_soc),
        predicted_price_charge_rule_training=bool(
            args.predicted_price_charge_rule_training),
        predicted_price_charge_training_max_current_price=float(
            args.predicted_price_charge_training_max_current_price),
        predicted_price_charge_training_min_spread=float(
            args.predicted_price_charge_training_min_spread),
        predicted_price_charge_training_max_soc=float(
            args.predicted_price_charge_training_max_soc),
        predicted_price_charge_training_building_index=(
            args.predicted_price_charge_training_building_index),
        predicted_price_charge_training_action=(
            args.predicted_price_charge_training_action),
        battery_post_soc_floor=(
            None if args.battery_post_soc_floor is None
            else float(args.battery_post_soc_floor)),
        battery_post_soc_floor_building_index=(
            args.battery_post_soc_floor_building_index),
        replay_action_semantics=(
            'replay stores executed discrete action indices; audit retains actor '
            'proposals and executed environment commands'),
        early_stop_on_official_pass=not args.no_early_stop,
        dual_rule='per-building projected update using deterministic official KPI after each training episode; replay relabeled at sampling',
        thermal_potential_shaping_weight=float(args.thermal_shaping_weight),
        thermal_potential='occupied (hot excess + cold excess) outside official comfort band divided by 10',
        boundary_risk_weight=float(args.boundary_risk_weight),
        boundary_risk='occupied excess beyond limits shifted inward by one degree divided by 10',
        storage_cycling_penalty_weight=float(args.storage_penalty_weight),
        storage_reversal_penalty_weight=float(args.storage_reversal_penalty_weight),
        storage_reversal_rule=(
            'penalize adjacent sign reversal only when electricity price is equal '
            'or less favorable; positive storage action charges, negative discharges'),
        behavior_policy=args.behavior_policy,
        behavior_policy_warmup=f'{args.warmup_policy} until replay has {args.learning_starts} rows',
        epsilon_schedule=dict(start=args.epsilon_start, end=args.epsilon_end,
                              decay_steps=args.epsilon_decay_steps),
        evaluation_policy='argmax',
        learning_starts=int(args.learning_starts),batch=args.batch_size,batch_size=args.batch_size,
        updates_per_step=int(args.optimizer_updates_per_step),
        actor_lr=args.actor_lr,
        critic_lr=args.critic_lr, discount=learner.discount, tau=learner.tau,
        reward_scale=learner.reward_scale,
        entropy_penalty=float(args.entropy_penalty),
        behavior_kl_penalty=float(args.behavior_kl_penalty),
        init_checkpoint=str(args.init_checkpoint.resolve()) if args.init_checkpoint else None,
        initialization_state=('actor_critic_and_dual_multipliers; optimizer_and_replay_reset'
                              if args.init_checkpoint else 'fresh'),
        initial_dual_multipliers=dict(
            cost=learner.cost_weights.tolist(),
            discomfort=learner.discomfort_weights.tolist()),
        n_step=int(args.n_step),
        comfort_priority=bool(args.comfort_priority),
        freeze_actor_cost_advantage=bool(args.freeze_actor_cost_advantage),
        freeze_actor_updates=bool(args.freeze_actor_updates),
        freeze_cooling_policy=bool(args.freeze_cooling_policy),
        target_action_policy=args.target_action_policy,
        critic_replay_sampling=args.critic_replay_sampling,
        comfort_cost_release_target=float(args.comfort_cost_release_target),
        comfort_release_patience=int(args.comfort_release_patience),
        comfort_cost_advantage_max_scale=float(args.comfort_cost_advantage_max_scale),
        actor_cost_objective_scale=float(learner.actor_cost_objective_scale),
        prohibited_inputs=['building_id','identity_embedding','rated_capacity','ideal_load','a_ref','simulator_hidden_state'],
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        note='AAC-derived implementation; changed sharing, features, critic action indexing and losses; not isolated proof of one mechanism')
    protocol['control_profile'] = args.control_profile
    write_json(out/'protocol.json',protocol)
    evaluations=[];started=time.time(); global_step=0
    eligible_update_steps=0
    comfort_release_streak = 0

    def evaluate_episode(episode):
        checkpoint=out/f'checkpoint_{episode:02d}.pt'
        learner.save(checkpoint,protocol,episode)
        def run_evaluation(eval_path, dataset, expected_hash, start_time_step,
                           end_time_step):
            evaluation_args = [
                sys.executable, __file__, '--evaluate', str(checkpoint),
                '--eval-output', str(eval_path),
                '--seed', str(args.seed),
                '--discomfort-target', str(args.discomfort_target),
                '--cost-target', str(args.cost_target),
                '--evaluation-dataset', str(dataset),
                '--expected-evaluation-dataset-sha256', str(expected_hash),
                '--evaluation-start-time-step', str(start_time_step),
            ]
            if end_time_step is not None:
                evaluation_args.extend([
                    '--evaluation-end-time-step', str(end_time_step)
                ])
            evaluation_args.extend(['--control-profile', args.control_profile])
            if args.fixed_cooling_action_schedule:
                evaluation_args.extend([
                    '--fixed-cooling-action-schedule',
                    str(args.fixed_cooling_action_schedule.resolve()),
                ])
            if args.predicted_price_charge_rule_training:
                evaluation_args.extend([
                    '--predicted-price-charge-rule-override', 'on',
                    '--predicted-price-charge-max-current-price-override',
                    str(args.predicted_price_charge_training_max_current_price),
                    '--predicted-price-charge-min-spread-override',
                    str(args.predicted_price_charge_training_min_spread),
                    '--predicted-price-charge-max-soc-override',
                    str(args.predicted_price_charge_training_max_soc),
                ])
                if args.predicted_price_charge_training_building_index is not None:
                    evaluation_args.extend([
                        '--predicted-price-charge-building-index',
                        str(args.predicted_price_charge_training_building_index),
                    ])
                if args.predicted_price_charge_training_action is not None:
                    evaluation_args.extend([
                        '--predicted-price-charge-action-override',
                        str(args.predicted_price_charge_training_action),
                    ])
            if args.battery_post_soc_floor is not None:
                evaluation_args.extend([
                    '--battery-post-soc-floor-override',
                    str(args.battery_post_soc_floor),
                    '--battery-post-soc-floor-building-index',
                    str(args.battery_post_soc_floor_building_index),
                ])
            subprocess.run(evaluation_args, check=True)
            return json.loads(eval_path.read_text(encoding='utf-8'))

        local_path = out/f'eval_local_{episode:02d}.json'
        local_evaluation = run_evaluation(
            local_path, Path(legacy.DATA).resolve(), legacy.EXPECTED,
            args.simulation_start_time_step, args.simulation_end_time_step,
        )
        if not args.evaluation_dataset:
            return local_evaluation, local_evaluation
        online_path = out/f'eval_online1_{episode:02d}.json'
        online_evaluation = run_evaluation(
            online_path, args.evaluation_dataset,
            args.evaluation_dataset_sha256,
            args.evaluation_start_time_step, args.evaluation_end_time_step,
        )
        return local_evaluation, online_evaluation

    def record_evaluation(episode, training_evaluation, evaluation):
        evaluations.append(evaluation)
        summary=dict(episode=episode,updates=learner.updates,
                     elapsed_s=time.time()-started,
                     per_building=evaluation['per_building'],
                     training_local_per_building=training_evaluation['per_building'],
                     passed=evaluation['all_buildings_meet_targets'],
                     mechanism=evaluation['mechanism'])
        with (out/'experience.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(summary)+'\n')
        print(json.dumps(dict(state='episode_evaluated',**summary)),flush=True)

    initial_training_evaluation,initial_evaluation=evaluate_episode(0)
    record_evaluation(0,initial_training_evaluation,initial_evaluation)
    if args.comfort_priority:
        learner.actor_cost_objective_scale, comfort_release_streak = update_comfort_priority_scale(
            learner.actor_cost_objective_scale,
            initial_training_evaluation['per_building'],
            [b.name for b in env.buildings],
            args.discomfort_target,
            args.comfort_cost_release_target,
            comfort_release_streak,
            args.comfort_release_patience,
            args.comfort_cost_advantage_max_scale,
        )
        learner.actor_cost_objective_scale = apply_actor_cost_advantage_freeze(
            learner.actor_cost_objective_scale, args.freeze_actor_cost_advantage)
        with (out/'comfort_priority.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(
                episode=0,
                all_buildings_meet_comfort_target=initial_training_evaluation[
                    'all_buildings_meet_comfort_target'],
                comfort_cost_release_target=args.comfort_cost_release_target,
                comfort_cost_advantage_max_scale=args.comfort_cost_advantage_max_scale,
                actor_cost_objective_scale=learner.actor_cost_objective_scale,
                release_pass_streak=comfort_release_streak,
            ))+'\n')
    # episode是一轮完整数据窗口，不是一次梯度更新；同一轮可能更新很多次或一次也不更新。
    for episode in range(1,args.episodes+1):
        if episode:
            seed_all(args.seed+episode-1);env.reset(seed=args.seed);history.reset()
            accumulator.reset()
            before=readings(env);potential_before=thermal_potential(before)
            previous_storage_actions=np.zeros((len(env.buildings),2),dtype=np.float32)
            previous_storage_prices=np.asarray(
                [float(o['electricity_pricing']) for o in before],dtype=np.float32)
            state=history.encode(before);done=trunc=False;steps=0
            unoccupied_streak=np.zeros(len(env.buildings),dtype=int)
            training_trajectory=[]; episode_reward=np.zeros(len(env.buildings),dtype=float)
            while not(done or trunc):
                # 先积累足够经验再更新。learning_starts是回放条数门槛，不是训练轮数。
                # 训练包含探索，评估固定argmax；二者动作分布不同属于明确的设计。
                warmup=len(learner.replay.rows) < args.learning_starts
                if warmup:
                    if args.warmup_policy == 'uniform':
                        behavior='uniform'; epsilon=1.0
                    else:
                        progress=min(1.0, global_step/max(1, args.epsilon_decay_steps))
                        epsilon=args.epsilon_start + progress*(args.epsilon_end-args.epsilon_start)
                        behavior='epsilon_greedy'
                elif args.behavior_policy == 'epsilon_greedy':
                    progress=min(1.0, global_step/max(1, args.epsilon_decay_steps))
                    epsilon=args.epsilon_start + progress*(args.epsilon_end-args.epsilon_start)
                    behavior='epsilon_greedy'
                else:
                    epsilon=0.0; behavior='categorical'
                ids,actions=learner.actions(
                    state, explore=True, behavior_policy=behavior, epsilon=epsilon
                )
                # 保存网络提案，然后按配置顺序应用门控/保护层；后者可能改写动作。
                proposed_ids = ids.copy()
                actions[:, 2] = np.clip(
                    actions[:, 2] + args.cooling_offset,
                    learner.grids[2].min(), learner.grids[2].max())
                unoccupied_streak=np.where(
                    np.asarray([o['occupant_count'] <= 0 for o in before]),
                    unoccupied_streak+1,0)
                proposed_actions=actions.copy()
                actions,cooling_gate=apply_unoccupied_cooling_gate(
                    before,proposed_actions,learner.grids[2],steps+1,
                    enabled=args.unoccupied_cooling_gate,
                    reduction_bins=args.unoccupied_cooling_gate_bins,
                    building_index=args.unoccupied_cooling_gate_training_building_index,
                    min_unoccupied_steps=args.unoccupied_cooling_gate_training_min_unoccupied_steps,
                    unoccupied_streak=unoccupied_streak,
                    comfort_margin=args.unoccupied_cooling_gate_training_comfort_margin,
                    second_bin_comfort_margin=(
                        args.unoccupied_cooling_gate_training_second_bin_comfort_margin),
                    max_cooling_demand=(
                        args.unoccupied_cooling_gate_training_max_demand))
                actions,charge_gate=apply_high_price_charge_gate(
                    before,actions,steps+1,
                    enabled=args.high_price_charge_gate,
                    price_threshold=args.high_price_charge_threshold,
                    reserve_soc=args.high_price_charge_reserve_soc)
                (actions, predicted_price_charge_gate
                 ) = apply_predicted_price_charge_rule(
                    before, actions, learner.grids[1],
                    enabled=args.predicted_price_charge_rule_training,
                    max_current_price=(
                        args.predicted_price_charge_training_max_current_price),
                    min_price_spread=(
                        args.predicted_price_charge_training_min_spread),
                    max_soc=args.predicted_price_charge_training_max_soc,
                    action=args.predicted_price_charge_training_action,
                    building_index=(
                        args.predicted_price_charge_training_building_index))
                for i in np.flatnonzero(cooling_gate):
                    ids[i, 2] = int(np.abs(
                        learner.grids[2] - actions[i, 2]).argmin())
                for i in np.flatnonzero(charge_gate):
                    ids[i, 1] = int(np.abs(
                        learner.grids[1] - actions[i, 1]).argmin())
                for i in np.flatnonzero(predicted_price_charge_gate):
                    ids[i, 1] = int(np.abs(
                        learner.grids[1] - actions[i, 1]).argmin())
                if args.control_profile == HISTORICAL_PROFILE:
                    actions, _, _, _ = apply_high_price_discharge_rule(
                        before, actions, learner.grids[1], enabled=True,
                        price_threshold=args.high_price_discharge_threshold_override,
                        reserve_soc=args.high_price_discharge_reserve_soc_override,
                        action=args.high_price_discharge_action_override,
                        building_index=args.high_price_discharge_building_index,
                        storage_devices=[b.electrical_storage for b in env.buildings],
                        post_soc_floor=args.high_price_discharge_post_soc_floor_override)
                    ids[:, 1] = np.abs(learner.grids[1][None, :] - actions[:, 1, None]).argmin(axis=1)
                battery_post_soc_floor_blocked = np.zeros(
                    len(before), dtype=bool)
                predicted_post_soc_for_battery_floor = np.full(
                    len(before), np.nan, dtype=float)
                if args.battery_post_soc_floor is not None:
                    (actions, battery_post_soc_floor_blocked,
                     predicted_post_soc_for_battery_floor
                     ) = apply_battery_post_soc_floor(
                        before, actions, learner.grids[1],
                        [building.electrical_storage
                         for building in env.buildings],
                        args.battery_post_soc_floor,
                        args.battery_post_soc_floor_building_index)
                    for i in np.flatnonzero(battery_post_soc_floor_blocked):
                        ids[i, 1] = int(np.abs(
                            learner.grids[1] - actions[i, 1]).argmin())
                actions,ids=apply_fixed_cooling_action_schedule(
                    actions,ids,fixed_cooling_schedule,steps,learner.grids[2])
                global_step += 1
                # 唯一推进物理仿真的位置：输入实际命令，拿到奖励、终止标志和新读数。
                # 下一温度/SOC由CityLearn设备与建筑模型计算，不由Actor直接“算出来”。
                _,step_rewards,done,trunc,info=env.step(actions.tolist());after=readings(env)
                step_rewards=np.asarray(step_rewards,dtype=float).reshape(-1)
                episode_reward += step_rewards
                potential_after=thermal_potential(after)
                shaping=args.thermal_shaping_weight * (
                    learner.discount * potential_after - potential_before
                )
                storage_penalty=args.storage_penalty_weight * (
                    np.abs(actions[:, 0]) + np.abs(actions[:, 1])
                )
                prices=np.asarray(
                    [float(o['electricity_pricing']) for o in before],dtype=np.float32)
                storage_reversal=storage_reversal_penalty(
                    actions[:,:2],prices,previous_storage_actions,
                    previous_storage_prices,args.storage_reversal_penalty_weight)
                boundary_penalty=boundary_risk_penalty(
                    after, args.boundary_risk_weight)
                components=np.stack([env.reward_function.last_cost_components,
                                      env.reward_function.last_discomfort_components,
                                      shaping + storage_penalty + boundary_penalty
                                      + storage_reversal],axis=-1).astype(np.float32)
                # 环境reward保留在轨迹中；学习器还保存可重加权的分量和可选整形项。
                # 这些训练信号不等于模型优选的最终分段评分，必须分开解释。
                for i,b in enumerate(env.buildings):
                    training_trajectory.append(dict(
                        episode=episode, step=steps+1, building=b.name,
                        source_timestep_before=args.simulation_start_time_step+steps,
                        source_timestep_after=args.simulation_start_time_step+steps+1,
                        observation_json=json.dumps(_json_value(before[i]),sort_keys=True),
                        next_observation_json=json.dumps(_json_value(after[i]),sort_keys=True),
                        action_json=json.dumps({
                            'dhw_storage':float(actions[i,0]),
                            'electrical_storage':float(actions[i,1]),
                            'cooling_device':float(actions[i,2])},sort_keys=True),
                        reward=float(step_rewards[i]),
                        cost_component=float(components[i,0]),
                        discomfort_component=float(components[i,1]),
                        shaping_component=float(components[i,2]),
                        storage_reversal_penalty=float(storage_reversal[i]),
                        terminated=bool(done),truncated=bool(trunc),
                        environment_info_json=json.dumps(_json_value(info),sort_keys=True),
                        proposed_action_ids_json=json.dumps(proposed_ids[i].tolist()),
                        executed_action_ids_json=json.dumps(ids[i].tolist()),
                        proposed_action_json=json.dumps(proposed_actions[i].tolist()),
                        proposed_cooling_action=float(proposed_actions[i,2]),
                        execution_cooling_gate=bool(cooling_gate[i]),
                        execution_high_price_charge_gate=bool(charge_gate[i]),
                        execution_predicted_price_charge_rule=bool(
                            predicted_price_charge_gate[i]),
                        execution_battery_post_soc_floor_blocked=bool(
                            battery_post_soc_floor_blocked[i]),
                        predicted_post_soc_for_battery_floor=(
                            float(predicted_post_soc_for_battery_floor[i])
                            if np.isfinite(
                                predicted_post_soc_for_battery_floor[i])
                            else None),
                        execution_fixed_cooling_action_schedule=(
                            fixed_cooling_schedule is not None),
                        dhw_action=float(actions[i,0]),
                        battery_action=float(actions[i,1]),
                        cooling_action=float(actions[i,2]),
                        **flat_observation_fields(before[i], after[i])))
                history.advance(before,actions,after);nxt=history.encode(after);steps+=1
                # 到这里真实转移才完整：state -> executed action -> components -> nxt。
                # 先把已完成转移加入历史，再编码下一输入；不读取未来实际值。
                previous_storage_actions=actions[:,:2].copy()
                previous_storage_prices=prices.copy()
                ready=accumulator.append(
                    state,ids,components,nxt,done,episode,steps,
                    episode_end=bool(done or trunc))
                for row in ready:
                    learner.replay.push(*row)
                if len(learner.replay.rows) >= args.learning_starts:
                    # 每个合格环境步可做多次优化，预算由optimizer_updates_per_step控制。
                    # updates才是实际学习次数；只有model.pt不能证明已发生学习。
                    eligible_update_steps += args.optimizer_updates_per_step
                    for _ in range(args.optimizer_updates_per_step):
                        learner.update()
                state=nxt;before=after;potential_before=potential_after
                if steps%60==0:
                    progress=dict(state='training',episode=episode,step=steps,updates=learner.updates,
                                  global_step=global_step,behavior_policy=behavior,
                                  epsilon=epsilon,elapsed_s=time.time()-started,
                                  history_enabled=args.history,**learner.last_losses)
                    with (out/'training_metrics.jsonl').open('a',encoding='utf-8') as f:
                        f.write(json.dumps(progress)+'\n')
                    write_json(out/'progress.json',progress);print(json.dumps(progress),flush=True)
            expected=eligible_update_steps
            if learner.updates!=expected:raise ValueError('Optimizer schedule mismatch')
            episode_trace=out/f'training_trajectory_episode_{episode:02d}.csv'
            with episode_trace.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(training_trajectory[0]))
                writer.writeheader();writer.writerows(training_trajectory)
            if len(training_trajectory) != steps*len(env.buildings):
                raise ValueError('Training audit row count mismatch')
            print(json.dumps(dict(state='training_episode_trace_written',
                episode=episode,steps=steps,rows=len(training_trajectory),
                per_step_reward=episode_reward.tolist(),
                file=str(episode_trace.resolve()))),flush=True)
            training_evaluation,evaluation=evaluate_episode(episode)
            record_evaluation(episode,training_evaluation,evaluation)
            if evaluation['all_buildings_meet_targets'] and not args.no_early_stop:break
            if args.comfort_priority:
                learner.actor_cost_objective_scale, comfort_release_streak = update_comfort_priority_scale(
                    learner.actor_cost_objective_scale,
                    training_evaluation['per_building'],
                    [b.name for b in env.buildings],
                    args.discomfort_target,
                    args.comfort_cost_release_target,
                    comfort_release_streak,
                    args.comfort_release_patience,
                    args.comfort_cost_advantage_max_scale,
                )
                learner.actor_cost_objective_scale = apply_actor_cost_advantage_freeze(
                    learner.actor_cost_objective_scale, args.freeze_actor_cost_advantage)
                with (out/'comfort_priority.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(dict(
                        episode=episode,
                        all_buildings_meet_comfort_target=training_evaluation['all_buildings_meet_comfort_target'],
                        comfort_cost_release_target=args.comfort_cost_release_target,
                        comfort_cost_advantage_max_scale=args.comfort_cost_advantage_max_scale,
                        actor_cost_objective_scale=learner.actor_cost_objective_scale,
                        release_pass_streak=comfort_release_streak,
                    ))+'\n')
            if max(args.dual_lr, discomfort_dual_lr) > 0 and episode >= args.dual_start_episode:
                learner.cost_weights, learner.discomfort_weights = update_constraint_weights(
                    learner.cost_weights, learner.discomfort_weights,
                    training_evaluation['per_building'],
                    [b.name for b in env.buildings], args.dual_lr, args.dual_max,
                    args.dual_cost_target, args.dual_discomfort_target,
                    discomfort_dual_lr)
                update = dict(episode=episode, cost=learner.cost_weights.tolist(),
                              discomfort=learner.discomfort_weights.tolist())
                with (out/'dual_updates.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(update)+'\n')
                print(json.dumps(dict(state='dual_updated',**update)),flush=True)
    write_json(out/'result.json',dict(state='completed',elapsed_s=time.time()-started,protocol=protocol,
                                    updates=learner.updates,evaluations=evaluations))
    write_json(out/'progress.json',dict(state='completed',episode=episode,updates=learner.updates))
    env.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path)
    p.add_argument('--episodes',type=int,default=30);p.add_argument('--seed',type=int,default=41)
    p.add_argument('--history',action='store_true');p.add_argument('--self-test',action='store_true')
    p.add_argument('--history-dilation',type=int,default=1)
    p.add_argument('--behavior-policy', choices=('categorical','epsilon_greedy'),
                   default='epsilon_greedy')
    p.add_argument('--warmup-policy', choices=('uniform','anchor_epsilon_greedy'),
                   default='uniform',
                   help='Behavior policy while replay has fewer than 719 rows; default preserves uniform warm-up')
    p.add_argument('--epsilon-start', type=float, default=0.20)
    p.add_argument('--epsilon-end', type=float, default=0.05)
    p.add_argument('--epsilon-decay-steps', type=int, default=7190)
    p.add_argument('--thermal-shaping-weight', type=float, default=0.0)
    p.add_argument('--storage-penalty-weight', type=float, default=0.0)
    p.add_argument('--storage-reversal-penalty-weight', type=float, default=0.0,
                   help='Penalize equal/worse-price reversals in DHW/battery storage actions')
    p.add_argument('--boundary-risk-weight', type=float, default=0.0,
                   help='Subtract this weight times occupied thermal-boundary risk from reward')
    p.add_argument('--discomfort-weight', type=float, default=1.0)
    p.add_argument('--dual-lr', type=float, default=0.0)
    p.add_argument('--discomfort-dual-lr', type=float, default=None,
                   help='Optional discomfort multiplier learning rate; defaults to --dual-lr')
    p.add_argument('--dual-max', type=float, default=4.0)
    p.add_argument('--dual-start-episode', type=int, default=2)
    p.add_argument('--dual-cost-target', type=float, default=0.9)
    p.add_argument('--dual-discomfort-target', type=float, default=0.1)
    p.add_argument('--optimizer-updates-per-step', type=int, choices=(1, 2), default=2)
    p.add_argument('--batch-size', type=int, choices=(128, 256), default=256,
                   help='Joint replay minibatch size for each optimizer update')
    p.add_argument('--learning-starts', type=int, default=719,
                   help='Replay rows required before gradient updates; default preserves the historical 719-step warm-up')
    p.add_argument('--comfort-priority', action='store_true',
                   help='Keep actor cost advantage at zero until all buildings pass discomfort target')
    p.add_argument('--freeze-actor-cost-advantage', action='store_true',
                   help='Keep the actor cost-objective scale at zero for the entire run')
    p.add_argument('--freeze-actor-updates', action='store_true',
                   help='Diagnostic only: keep actor and target actor fixed while critic updates')
    p.add_argument('--freeze-cooling-policy', action='store_true',
                   help='Use an immutable full anchor network for deterministic cooling; train storage only')
    p.add_argument('--unoccupied-cooling-gate', action='store_true',
                   help='Fixed observable-only one-bin cooling execution reduction; proposal replay, executed history')
    p.add_argument('--unoccupied-cooling-gate-override',
                   choices=('on', 'off'), default=None,
                   help='Evaluation-only override for the unoccupied cooling gate')
    p.add_argument('--unoccupied-cooling-gate-building-index', type=int,
                   choices=(0, 1, 2),
                   help='Optional zero-based building scope for the unoccupied cooling gate')
    p.add_argument('--unoccupied-cooling-gate-min-unoccupied-steps',
                   type=int, default=None,
                   help='Evaluation-only observed empty-step streak required before reduction')
    p.add_argument('--unoccupied-cooling-gate-comfort-margin',
                   type=float, default=None,
                   help='Evaluation-only degrees of margin below the official hot-discomfort boundary')
    p.add_argument('--unoccupied-cooling-gate-price-threshold',
                   type=float, default=None,
                   help='Evaluation-only minimum current price for the cooling gate')
    p.add_argument('--unoccupied-cooling-gate-max-demand-override',
                   type=float, default=None,
                   help='Evaluation-only maximum current cooling demand eligible for the gate')
    p.add_argument('--unoccupied-cooling-gate-extra-building-index',
                   type=int, choices=(0, 1, 2), default=None,
                   help='Evaluation-only second gate scope with a distinct cooling-demand interval')
    p.add_argument('--unoccupied-cooling-gate-extra-min-demand-exclusive',
                   type=float, default=None,
                   help='Evaluation-only lower bound for the second gate demand interval')
    p.add_argument('--unoccupied-cooling-gate-extra-max-demand',
                   type=float, default=None,
                   help='Evaluation-only upper bound for the second gate demand interval')
    p.add_argument('--unoccupied-cooling-gate-extra-bins',
                   type=int, choices=(1, 2), default=None,
                   help='Evaluation-only action reduction for the second gate')
    p.add_argument('--unoccupied-cooling-gate-extra-2-building-index',
                   type=int, choices=(0, 1, 2), default=None,
                   help='Evaluation-only third gate scope with a distinct demand interval')
    p.add_argument('--unoccupied-cooling-gate-extra-2-min-demand-exclusive',
                   type=float, default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-2-max-demand',
                   type=float, default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-2-bins',
                   type=int, choices=(1, 2), default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-3-building-index',
                   type=int, choices=(0, 1, 2), default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-3-min-demand-exclusive',
                   type=float, default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-3-max-demand',
                   type=float, default=None)
    p.add_argument('--unoccupied-cooling-gate-extra-3-bins',
                   type=int, choices=(1, 2), default=None)
    p.add_argument('--unoccupied-cooling-gate-temp-rise-block-threshold',
                   type=float, default=None,
                   help='Evaluation-only: suppress cooling reduction after a large observed prior-step temperature rise')
    p.add_argument('--cooling-action-cap-override', type=float, default=None,
                   help='Evaluation-only maximum legal cooling action')
    p.add_argument('--outage-risk-pulse', action='store_true',
                   help='Evaluation-only frozen B3 observed-shortage accumulated pulse')
    p.add_argument('--diagnostic-battery-fork', type=Path, default=None,
                   help='Research-only JSON prescribing one B3 battery action; not a deployment policy')
    p.add_argument('--b1-occupied-low-demand-cap', action='store_true',
                   help='Evaluation-only B1 cap .6 when occupied, grid-connected and current cooling demand <=2')
    p.add_argument('--unoccupied-cooling-gate-bins-override',
                   type=int, choices=(1, 2), default=None,
                   help='Evaluation-only execution reduction amplitude')
    p.add_argument('--unoccupied-cooling-gate-second-bin-comfort-margin',
                   type=float, default=None,
                   help='Require this additional temperature margin before applying the second reduction bin')
    p.add_argument('--unoccupied-cooling-gate-second-bin-risk-profile',
                   type=Path, default=None,
                   help='Evaluation-only JSON occupancy-arrival profile for second-bin suppression')
    p.add_argument('--unoccupied-cooling-gate-second-bin-risk-threshold',
                   type=float, default=None,
                   help='Allow the second bin only below this predicted next-step occupancy probability')
    p.add_argument('--unoccupied-cooling-gate-bins',type=int,choices=(1,2),default=1,
                   help='Execution reduction amplitude when gate triggers; default preserves one bin')
    p.add_argument('--unoccupied-cooling-gate-training-building-index',
                   type=int, choices=(0, 1, 2), default=None,
                   help='Training-time building scope for the cooling gate')
    p.add_argument('--unoccupied-cooling-gate-training-min-unoccupied-steps',
                   type=int, default=0,
                   help='Training-time observed empty-step streak before the cooling gate')
    p.add_argument('--unoccupied-cooling-gate-training-comfort-margin',
                   type=float, default=.5,
                   help='Training-time margin below the official hot-discomfort boundary')
    p.add_argument('--unoccupied-cooling-gate-training-second-bin-comfort-margin',
                   type=float, default=None,
                   help='Training-time additional temperature margin before applying the second reduction bin')
    p.add_argument('--unoccupied-cooling-gate-training-max-demand',
                   type=float, default=None,
                   help='Training-time maximum current cooling demand eligible for the gate')
    p.add_argument('--high-price-charge-gate', action='store_true',
                   help='Suppress positive battery charging at high price above reserve SOC')
    p.add_argument('--high-price-charge-threshold', type=float, default=.02915)
    p.add_argument('--high-price-charge-reserve-soc', type=float, default=.20)
    p.add_argument('--predicted-price-charge-rule-training', action='store_true',
                   help='Training-time one-bin charge before a forecast price rise')
    p.add_argument('--predicted-price-charge-training-max-current-price',
                   type=float, default=.03025)
    p.add_argument('--predicted-price-charge-training-min-spread',
                   type=float, default=.005)
    p.add_argument('--predicted-price-charge-training-max-soc',
                   type=float, default=.30)
    p.add_argument('--predicted-price-charge-training-building-index',
                   type=int, choices=(0, 1, 2), default=None)
    p.add_argument('--predicted-price-charge-training-action',
                   type=float, default=None)
    p.add_argument('--battery-post-soc-floor', type=float,
                   help='Training shield for non-outage battery actions')
    p.add_argument('--target-action-policy', choices=('categorical','greedy'), default='categorical',
                   help='Bootstrap action policy; default preserves categorical target sampling')
    p.add_argument('--critic-replay-sampling', choices=('uniform','battery_balanced_is'), default='uniform',
                   help='Critic-only battery-bin mixture with exact importance weights; actor keeps uniform replay')
    p.add_argument('--comfort-cost-release-target', type=float, default=.09)
    p.add_argument('--comfort-release-patience', type=int, default=2)
    p.add_argument('--comfort-cost-advantage-max-scale', type=float, default=1.0,
                   help='Maximum actor cost-advantage scale after comfort release; default preserves 1.0')
    p.add_argument('--no-early-stop', action='store_true')
    p.add_argument('--cooling-classes', type=int, choices=(11,21), default=11)
    p.add_argument('--actor-lr', type=float, default=0.001)
    p.add_argument('--critic-lr', type=float, default=0.001)
    p.add_argument('--discount', type=float, default=.99)
    p.add_argument('--tau', type=float, default=.005)
    p.add_argument('--reward-scale', type=float, default=10.)
    p.add_argument('--actor-architecture', choices=('shared','building_heads'), default='shared')
    p.add_argument('--critic-objective', choices=('scalarized','separate'), default='scalarized')
    p.add_argument('--critic-own-action-context', choices=('none','other_heads'), default='none',
                   help='Optional zero-initialized residual conditioning on own other action heads')
    p.add_argument('--cooling-offset', type=float, default=0.0)
    p.add_argument('--n-step', type=int, choices=(1,3), default=1)
    p.add_argument('--entropy-penalty', type=float, default=0.0)
    p.add_argument('--init-checkpoint', type=Path)
    p.add_argument('--behavior-kl-penalty', type=float, default=0.0)
    p.add_argument('--evaluate',type=Path);p.add_argument('--eval-output',type=Path)
    p.add_argument('--evaluation-dataset', type=Path,
                   help='Evaluate checkpoints against a separate CityLearn dataset')
    p.add_argument('--expected-evaluation-dataset-sha256')
    p.add_argument('--evaluation-start-time-step', type=int, default=0)
    p.add_argument('--evaluation-end-time-step', type=int)
    p.add_argument('--fixed-cooling-action-schedule', type=Path,
                   help='Force the same logged anchor cooling command on every step')
    p.add_argument('--fixed-dhw-action-schedule', type=Path,
                   help='Evaluation-only: replay logged DHW commands on every step')
    p.add_argument('--allow-fixed-cooling-schedule-hash-override',
                   action='store_true',
                   help='Evaluation-only: permit a dataset-specific schedule with a different checkpoint hash')
    p.add_argument('--disable-checkpoint-fixed-cooling-schedule',
                   action='store_true',
                   help='Evaluation-only: ignore the checkpoint-embedded cooling schedule')
    p.add_argument('--high-price-charge-gate-override',
                   choices=('on', 'off'), default=None,
                   help='Override the checkpoint gate setting for evaluation only')
    p.add_argument('--high-price-charge-threshold-override', type=float,
                   help='Evaluation-only override for the high-price gate threshold')
    p.add_argument('--high-price-charge-reserve-soc-override', type=float,
                   help='Evaluation-only override for the high-price gate reserve SOC')
    p.add_argument('--high-price-discharge-rule-override',
                   choices=('on', 'off'), default=None,
                   help='Evaluation-only: discharge at highest tariff when import is positive')
    p.add_argument('--high-price-discharge-reserve-soc-override', type=float,
                   help='Evaluation-only SOC floor for highest-tariff discharge rule')
    p.add_argument('--high-price-discharge-building-index', type=int,
                   choices=(0, 1, 2),
                   help='Evaluation-only zero-based building index for discharge rule')
    p.add_argument('--high-price-discharge-post-soc-floor-override',
                   type=float,
                   help='Evaluation-only minimum predicted SOC after rule action')
    p.add_argument('--high-price-discharge-post-soc-floor-building-index',
                   type=int, choices=(0, 1, 2),
                   help='Optional building-specific post-action SOC floor scope')
    p.add_argument('--high-price-discharge-post-soc-floor-building-override',
                   type=float,
                   help='Optional building-specific post-action SOC floor')
    p.add_argument('--high-price-discharge-threshold-override', type=float,
                   help='Evaluation-only minimum electricity price for discharge rule')
    p.add_argument('--high-price-discharge-action-override', type=float,
                   help='Evaluation-only legal discharge action for the rule')
    p.add_argument('--predicted-price-discharge-gate-override',
                   choices=('on', 'off'), default=None,
                   help='Evaluation-only: hold battery discharge if the next-step price forecast rises')
    p.add_argument('--predicted-price-discharge-min-spread-override',
                   type=float,
                   help='Evaluation-only minimum forecast price rise in currency/kWh')
    p.add_argument('--predicted-price-discharge-building-index', type=int,
                   choices=(0, 1, 2),
                   help='Optional building scope for the forecast-price discharge gate')
    p.add_argument('--predicted-price-charge-rule-override',
                   choices=('on', 'off'), default=None,
                   help='Evaluation-only: charge one bin before a forecast price rise at low SOC')
    p.add_argument('--predicted-price-charge-max-current-price-override',
                   type=float)
    p.add_argument('--predicted-price-charge-min-spread-override',
                   type=float)
    p.add_argument('--predicted-price-charge-max-soc-override', type=float)
    p.add_argument('--predicted-price-charge-building-index', type=int,
                   choices=(0, 1, 2))
    p.add_argument('--predicted-price-charge-additional-building-index',
                   type=int, choices=(0, 1, 2),
                   help='Evaluation-only second building scope for predicted-price precharge')
    p.add_argument('--predicted-price-charge-action-override', type=float)
    p.add_argument('--battery-post-soc-floor-override', type=float,
                   help='Evaluation-only floor for non-outage executed battery discharges')
    p.add_argument('--disable-checkpoint-battery-post-soc-floor',
                   action='store_true',
                   help='Evaluation-only: disable a battery SOC floor saved in the checkpoint')
    p.add_argument('--battery-post-soc-floor-building-index', type=int,
                   choices=(0, 1, 2),
                   help='Optional zero-based building scope for battery SOC floor')
    p.add_argument('--simulation-start-time-step', type=int, default=0)
    p.add_argument('--simulation-end-time-step', type=int, default=719)
    p.add_argument('--window-role', choices=('full_trajectory_historical_replay',
                                              'training_development_prefix_only'),
                   default='full_trajectory_historical_replay')
    p.add_argument('--discomfort-target', type=float, default=.10)
    p.add_argument('--cost-target', type=float, default=.90)
    p.add_argument('--control-profile', choices=('none', HISTORICAL_PROFILE), default='none')
    args=p.parse_args()
    if args.learning_starts < 1:
        p.error('--learning-starts must be positive')
    if (not args.evaluate and args.battery_post_soc_floor is not None
            and (args.battery_post_soc_floor_building_index is None
                 or args.fixed_cooling_action_schedule is None)):
        p.error(
            'Battery SOC floor training requires building index and fixed cooling schedule'
        )
    if (not args.evaluate and args.battery_post_soc_floor is not None
            and not 0. <= args.battery_post_soc_floor <= 1.):
        p.error('Battery SOC floor must be between zero and one')
    if args.unoccupied_cooling_gate and not args.evaluate:
        if not args.freeze_cooling_policy or args.cooling_offset!=0:
            p.error('Cooling gate training requires --freeze-cooling-policy and zero cooling offset')
    if (not args.evaluate and not args.unoccupied_cooling_gate
            and (args.unoccupied_cooling_gate_training_building_index is not None
                 or args.unoccupied_cooling_gate_training_min_unoccupied_steps != 0
                 or args.unoccupied_cooling_gate_training_comfort_margin != .5
                 or args.unoccupied_cooling_gate_training_max_demand is not None
                 or args.unoccupied_cooling_gate_training_second_bin_comfort_margin is not None)):
        p.error('Training-time cooling gate parameters require --unoccupied-cooling-gate')
    if args.unoccupied_cooling_gate_bins!=1 and not args.unoccupied_cooling_gate and not args.evaluate:
        p.error('Nondefault cooling amplitude requires --unoccupied-cooling-gate')
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    CLASSES=(21,21,args.cooling_classes)
    if args.history_dilation < 1:p.error('--history-dilation must be positive')
    if args.evaluation_dataset:
        args.evaluation_dataset = args.evaluation_dataset.resolve()
        if not (args.evaluation_dataset / 'schema.json').is_file():
            p.error('--evaluation-dataset must contain schema.json')
        evaluation_hash = dataset_digest(args.evaluation_dataset)
        if (args.expected_evaluation_dataset_sha256
                and evaluation_hash != args.expected_evaluation_dataset_sha256):
            p.error('Evaluation dataset SHA-256 does not match expected hash')
        if not args.evaluate:
            args.evaluation_dataset_sha256 = evaluation_hash
            schema = json.loads(
                (args.evaluation_dataset / 'schema.json').read_text(encoding='utf-8')
            )
            if args.evaluation_end_time_step is None:
                args.evaluation_end_time_step = int(
                    schema['simulation_end_time_step']
                )
    if args.evaluate and args.eval_output is None:
        p.error('--eval-output is required with --evaluate')
    if args.fixed_dhw_action_schedule and not args.evaluate:
        p.error('--fixed-dhw-action-schedule is evaluation-only')
    if args.disable_checkpoint_battery_post_soc_floor and not args.evaluate:
        p.error('--disable-checkpoint-battery-post-soc-floor is evaluation-only')
    if (not args.evaluate
            and (args.unoccupied_cooling_gate_override is not None
                 or args.unoccupied_cooling_gate_building_index is not None
                 or args.unoccupied_cooling_gate_min_unoccupied_steps is not None
                 or args.unoccupied_cooling_gate_comfort_margin is not None
                 or args.unoccupied_cooling_gate_price_threshold is not None
                 or args.unoccupied_cooling_gate_max_demand_override is not None
                 or args.unoccupied_cooling_gate_bins_override is not None
                 or args.unoccupied_cooling_gate_second_bin_comfort_margin is not None
                 or args.unoccupied_cooling_gate_second_bin_risk_profile is not None
                 or args.unoccupied_cooling_gate_second_bin_risk_threshold is not None)):
        p.error('Evaluation-only unoccupied cooling overrides require --evaluate')
    if not args.evaluate and args.cooling_action_cap_override is not None:
        p.error('--cooling-action-cap-override requires --evaluate')
    if args.diagnostic_battery_fork is not None and not args.evaluate:
        p.error('--diagnostic-battery-fork requires --evaluate')
    if args.outage_risk_pulse and not args.evaluate:
        p.error('--outage-risk-pulse requires --evaluate')
    if args.b1_occupied_low_demand_cap and not args.evaluate:
        p.error('--b1-occupied-low-demand-cap requires --evaluate')
    if (args.cooling_action_cap_override is not None
            and not np.isfinite(args.cooling_action_cap_override)):
        p.error('Cooling action cap must be finite')
    if (not args.evaluate
            and (args.high_price_discharge_threshold_override is not None
                 or args.high_price_discharge_action_override is not None
                 or args.high_price_discharge_post_soc_floor_building_index is not None
                 or args.high_price_discharge_post_soc_floor_building_override is not None)):
        p.error('High-price discharge overrides require --evaluate')
    if ((args.high_price_discharge_post_soc_floor_building_index is None)
            != (args.high_price_discharge_post_soc_floor_building_override is None)):
        p.error('Building-specific SOC floor requires both index and value')
    if (args.high_price_discharge_post_soc_floor_building_override is not None
            and (not np.isfinite(
                args.high_price_discharge_post_soc_floor_building_override)
                 or not 0. <= args.high_price_discharge_post_soc_floor_building_override <= 1.)):
        p.error('Building-specific SOC floor must be in [0, 1]')
    if (not args.evaluate
            and (args.predicted_price_discharge_gate_override is not None
                 or args.predicted_price_discharge_min_spread_override is not None
                 or args.predicted_price_discharge_building_index is not None)):
        p.error('Predicted-price discharge overrides require --evaluate')
    if (not args.evaluate
            and (args.predicted_price_charge_rule_override is not None
                 or args.predicted_price_charge_max_current_price_override is not None
                 or args.predicted_price_charge_min_spread_override is not None
                 or args.predicted_price_charge_max_soc_override is not None
                 or args.predicted_price_charge_building_index is not None
                 or args.predicted_price_charge_additional_building_index is not None
                 or args.predicted_price_charge_action_override is not None)):
        p.error('Predicted-price charge overrides require --evaluate')
    if (args.predicted_price_discharge_min_spread_override is not None
            and (not np.isfinite(args.predicted_price_discharge_min_spread_override)
                 or args.predicted_price_discharge_min_spread_override < 0.)):
        p.error('Predicted price spread must be finite and nonnegative')
    for value, name in (
            (args.predicted_price_charge_max_current_price_override,
             'maximum current price'),
            (args.predicted_price_charge_min_spread_override,
             'minimum price spread'),
            (args.predicted_price_charge_max_soc_override, 'maximum SOC'),
            (args.predicted_price_charge_action_override, 'charge action')):
        if value is not None and not np.isfinite(value):
            p.error(f'Predicted-price charge {name} must be finite')
    if (args.predicted_price_charge_max_current_price_override is not None
            and args.predicted_price_charge_max_current_price_override < 0.):
        p.error('Predicted-price charge maximum price must be nonnegative')
    if (args.predicted_price_charge_min_spread_override is not None
            and args.predicted_price_charge_min_spread_override < 0.):
        p.error('Predicted-price charge spread must be nonnegative')
    if (args.predicted_price_charge_max_soc_override is not None
            and not 0. <= args.predicted_price_charge_max_soc_override <= 1.):
        p.error('Predicted-price charge maximum SOC must be in [0, 1]')
    if (args.high_price_discharge_threshold_override is not None
            and args.high_price_discharge_threshold_override < 0.):
        p.error('High-price discharge threshold must be nonnegative')
    if (args.unoccupied_cooling_gate_min_unoccupied_steps is not None
            and args.unoccupied_cooling_gate_min_unoccupied_steps < 0):
        p.error('Unoccupied cooling duration must be nonnegative')
    if (args.unoccupied_cooling_gate_comfort_margin is not None
            and args.unoccupied_cooling_gate_comfort_margin < 0.):
        p.error('Unoccupied cooling comfort margin must be nonnegative')
    if (args.unoccupied_cooling_gate_price_threshold is not None
            and (not np.isfinite(args.unoccupied_cooling_gate_price_threshold)
                 or args.unoccupied_cooling_gate_price_threshold < 0.)):
        p.error('Unoccupied cooling price threshold must be finite and nonnegative')
    if (args.unoccupied_cooling_gate_max_demand_override is not None
            and (not np.isfinite(args.unoccupied_cooling_gate_max_demand_override)
                 or args.unoccupied_cooling_gate_max_demand_override < 0.)):
        p.error('Maximum cooling demand must be finite and nonnegative')
    extra_demand_gate = (
        args.unoccupied_cooling_gate_extra_building_index,
        args.unoccupied_cooling_gate_extra_min_demand_exclusive,
        args.unoccupied_cooling_gate_extra_max_demand)
    if any(value is not None for value in extra_demand_gate):
        if not args.evaluate or any(value is None for value in extra_demand_gate):
            p.error(
                'The extra cooling gate requires evaluation mode and all three overrides')
        if (not np.isfinite(
                args.unoccupied_cooling_gate_extra_min_demand_exclusive)
                or args.unoccupied_cooling_gate_extra_min_demand_exclusive < 0.
                or not np.isfinite(
                    args.unoccupied_cooling_gate_extra_max_demand)
                or args.unoccupied_cooling_gate_extra_max_demand
                <= args.unoccupied_cooling_gate_extra_min_demand_exclusive):
            p.error(
                'Extra cooling gate bounds must form a valid positive interval')
    if (args.unoccupied_cooling_gate_extra_bins is not None
            and args.unoccupied_cooling_gate_extra_building_index is None):
        p.error('Extra gate bins require an extra gate building index')
    if (args.unoccupied_cooling_gate_second_bin_comfort_margin is not None
            and (not np.isfinite(
                args.unoccupied_cooling_gate_second_bin_comfort_margin)
                 or args.unoccupied_cooling_gate_second_bin_comfort_margin < 0.)):
        p.error('Second-bin cooling margin must be finite and nonnegative')
    if ((args.unoccupied_cooling_gate_second_bin_risk_profile is None)
            != (args.unoccupied_cooling_gate_second_bin_risk_threshold is None)):
        p.error('Occupancy risk profile and threshold must be supplied together')
    if (args.unoccupied_cooling_gate_second_bin_risk_threshold is not None
            and (not np.isfinite(
                args.unoccupied_cooling_gate_second_bin_risk_threshold)
                 or not 0. <= args.unoccupied_cooling_gate_second_bin_risk_threshold <= 1.)):
        p.error('Second-bin occupancy risk threshold must be in [0, 1]')
    if args.unoccupied_cooling_gate_training_min_unoccupied_steps < 0:
        p.error('Training-time unoccupied duration must be nonnegative')
    if args.unoccupied_cooling_gate_training_comfort_margin < 0.:
        p.error('Training-time cooling comfort margin must be nonnegative')
    if (args.unoccupied_cooling_gate_training_second_bin_comfort_margin is not None
            and (not np.isfinite(
                args.unoccupied_cooling_gate_training_second_bin_comfort_margin)
                 or args.unoccupied_cooling_gate_training_second_bin_comfort_margin
                 < args.unoccupied_cooling_gate_training_comfort_margin)):
        p.error(
            'Training-time second-bin margin must be finite and at least '
            'the gate comfort margin')
    if (args.unoccupied_cooling_gate_training_second_bin_comfort_margin is not None
            and args.unoccupied_cooling_gate_bins != 2):
        p.error('Training-time second-bin margin requires two-bin cooling reduction')
    if (args.unoccupied_cooling_gate_training_max_demand is not None
            and (not np.isfinite(args.unoccupied_cooling_gate_training_max_demand)
                 or args.unoccupied_cooling_gate_training_max_demand < 0.)):
        p.error('Training-time maximum cooling demand must be finite and nonnegative')
    if (args.disable_checkpoint_battery_post_soc_floor
            and args.battery_post_soc_floor_override is not None):
        p.error(
            '--disable-checkpoint-battery-post-soc-floor cannot be combined '
            'with --battery-post-soc-floor-override'
        )
    # Validate explicit CLI overrides before expanding the fixed control profile.
    configure_profile(args)
    if args.self_test:self_test()
    elif args.evaluate:evaluate(
        args.evaluate,args.eval_output,
        (args.evaluation_start_time_step if args.evaluation_dataset
         else args.simulation_start_time_step),
        (args.evaluation_end_time_step if args.evaluation_dataset
         else args.simulation_end_time_step),args.seed,
        args.evaluation_dataset,args.expected_evaluation_dataset_sha256,
        (None if args.high_price_charge_gate_override is None
         else args.high_price_charge_gate_override == 'on'),
        args.fixed_cooling_action_schedule,
        args.allow_fixed_cooling_schedule_hash_override,
        args.high_price_charge_threshold_override,
        args.high_price_charge_reserve_soc_override,
        (None if args.high_price_discharge_rule_override is None
         else args.high_price_discharge_rule_override == 'on'),
        args.high_price_discharge_reserve_soc_override,
        args.high_price_discharge_building_index,
        args.high_price_discharge_post_soc_floor_override,
        args.disable_checkpoint_fixed_cooling_schedule,
        args.battery_post_soc_floor_override,
        args.battery_post_soc_floor_building_index,
        args.disable_checkpoint_battery_post_soc_floor,
        (None if args.unoccupied_cooling_gate_override is None
         else args.unoccupied_cooling_gate_override == 'on'),
        args.unoccupied_cooling_gate_building_index,
        args.unoccupied_cooling_gate_min_unoccupied_steps,
        args.unoccupied_cooling_gate_comfort_margin,
        args.unoccupied_cooling_gate_price_threshold,
        args.unoccupied_cooling_gate_bins_override,
        args.fixed_dhw_action_schedule,
        args.high_price_discharge_threshold_override,
        args.high_price_discharge_action_override,
        args.unoccupied_cooling_gate_second_bin_comfort_margin,
        args.unoccupied_cooling_gate_second_bin_risk_profile,
        args.unoccupied_cooling_gate_second_bin_risk_threshold,
        (None if args.predicted_price_discharge_gate_override is None
         else args.predicted_price_discharge_gate_override == 'on'),
        args.predicted_price_discharge_min_spread_override,
        args.predicted_price_discharge_building_index,
        (None if args.predicted_price_charge_rule_override is None
         else args.predicted_price_charge_rule_override == 'on'),
        args.predicted_price_charge_max_current_price_override,
        args.predicted_price_charge_min_spread_override,
        args.predicted_price_charge_max_soc_override,
        args.predicted_price_charge_building_index,
        args.predicted_price_charge_additional_building_index,
        args.predicted_price_charge_action_override,
        args.unoccupied_cooling_gate_max_demand_override,
        args.cooling_action_cap_override,
        args.unoccupied_cooling_gate_extra_building_index,
        args.unoccupied_cooling_gate_extra_min_demand_exclusive,
        args.unoccupied_cooling_gate_extra_max_demand,
        args.unoccupied_cooling_gate_extra_bins,
        args.high_price_discharge_post_soc_floor_building_index,
        args.high_price_discharge_post_soc_floor_building_override,
        args.unoccupied_cooling_gate_extra_2_building_index,
        args.unoccupied_cooling_gate_extra_2_min_demand_exclusive,
        args.unoccupied_cooling_gate_extra_2_max_demand,
        args.unoccupied_cooling_gate_extra_2_bins,
        args.unoccupied_cooling_gate_extra_3_building_index,
        args.unoccupied_cooling_gate_extra_3_min_demand_exclusive,
        args.unoccupied_cooling_gate_extra_3_max_demand,
        args.unoccupied_cooling_gate_extra_3_bins,
        args.unoccupied_cooling_gate_temp_rise_block_threshold,
        args.b1_occupied_low_demand_cap,
        args.outage_risk_pulse,
        args.diagnostic_battery_fork)
    elif args.output and args.episodes>=1:train(args)
    else:p.error('Specify output and positive episodes, or evaluation/self-test mode')
