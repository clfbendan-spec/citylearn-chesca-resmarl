# -*- coding: utf-8 -*-
"""DistrictContextRLlibEnv —— 给每个 agent 追加区域级观测的环境层。

【怎么做到"零改动"】
  不去改 utils/env.py 的 ContextRLlibEnv，而是**继承**它：
    · 原类负责：观测空间扩展的基础设施、制冷动作映射（COOL_FLOOR/SPAN/a_ref）、
      楼栋 one-hot 身份、制冷能力比值、a_ref 等既有额外观测；
    · 本类只做两件事：
        ① 在 __init__ 末尾把观测空间再追加 N_FEATURES 维（值域 [-1,1]）；
        ② 覆写 _ctx_augment()，在**原类拼接结果之后**再接上区域特征。
  于是"关掉本扩展"⟺ 用原 ContextRLlibEnv，行为逐位一致（DISTRICT_OBS_ENABLE=False）。

【为什么在 _ctx_augment 里做】
  · 它是 ContextRLlibEnv 里 reset()/step() 唯一的观测出口 ⇒ 挂在这里，
    两个路径都自动生效，不必重复实现；
  · 每步调用一次（三个 agent 一次遍历），社区聚合量在这里**只算一次**，
    再按 agent 取行 ⇒ 无重复计算，也保证三个 agent 看到的是同一份社区状态
    （顺序无关，避免"先算的楼拿到旧峰值"这类隐性不一致）。

【数值口径】
  · 社区净用电 = Σ 各楼 `net_electricity_consumption` 的**当前步**值
    （该属性返回 `[:time_step+1]`，而末位是未计算的占位 0 ⇒ 真实值取下标
     `time_step-1`；见 `_dm_current_index` 的实测说明）；
  · SOC = `building.electrical_storage.soc` 的当前步值（同一套下标规则）；
  · 任一读取失败 ⇒ 该维退化为中性值，**不抛异常**（训练中不能因读数崩）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import numpy as np
from gymnasium import spaces

from utils.base import log_once
from utils.env import ContextRLlibEnv

from district_marl.district_features import (
    FEATURE_NAMES,
    N_FEATURES,
    DistrictFeatureConfig,
    DistrictFeatureExtractor,
)

# env_config 里挂区域配置的键（RLlibMultiAgentEnv 只用 env_kwargs / wrappers，
# 其余顶层键它不管 ⇒ 多挂一个键是安全的）
DISTRICT_ENV_CONFIG_KEY = 'district_marl'


def read_district_env_config(env_config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """从 env_config 里取出区域配置（缺省 / 非法 ⇒ 用 district_config 的默认值）。"""
    raw: Dict[str, Any] = {}
    if isinstance(env_config, Mapping):
        got = env_config.get(DISTRICT_ENV_CONFIG_KEY)
        if isinstance(got, Mapping):
            raw = dict(got)
    try:
        from district_marl import district_config as dc
        default = dict(dc.district_env_config())
    except Exception:
        default = {}
    default.update({k: v for k, v in raw.items() if v is not None})
    return default


class DistrictContextRLlibEnv(ContextRLlibEnv):
    """在 ContextRLlibEnv 之上追加 9 维区域观测的 RLlib 多智能体环境。

    参数
    ----
    env_config : Mapping
        与 ContextRLlibEnv 完全相同，另可含顶层键 `'district_marl'`：
          {'enabled': bool, 'net_scale': float, 'peak_net': float,
           'valley_net': float, 'clip': float}
    """

    def __init__(self, env_config: Mapping[str, Any]):
        super().__init__(env_config)

        cfg = read_district_env_config(env_config)
        self._dm_enabled = bool(cfg.get('enabled', True))
        self._dm_cfg = DistrictFeatureConfig(
            net_scale=cfg.get('net_scale', 9.0),
            peak_net=cfg.get('peak_net', 6.0),
            valley_net=cfg.get('valley_net', 4.0),
            clip=cfg.get('clip', 1.0),
        ).normalized()

        # 楼栋下标 ↔ agent_id 的映射沿用原类的 _ctx_ids（顺序契约，勿改）
        self._dm_ids = list(getattr(self, '_ctx_ids', None) or [])
        n_b = len(self._dm_ids)
        self._dm_extractor = DistrictFeatureExtractor(n_b, self._dm_cfg)
        self._dm_n_extra = int(N_FEATURES) if (self._dm_enabled and n_b > 0) else 0

        if self._dm_n_extra > 0:
            self._dm_extend_observation_space()
            try:
                log_once(
                    'district_obs_on',
                    f'[district-marl] 区域观测已启用：每 agent +{self._dm_n_extra} 维'
                    f'（{", ".join(FEATURE_NAMES)}；net_scale={self._dm_cfg.net_scale:g}）',
                )
            except Exception:
                pass

        # ---- 【方案 3】结构化动作空间（默认关 ⇒ 动作空间仍 3 维，零侵入）----
        self._dm_peak_dim = int(cfg.get('peak_action_dim', 0) or 0)
        self._dm_peak_cool_frac = float(cfg.get('peak_resp_cool_frac', 0.55))
        self._dm_peak_batt_disch = float(cfg.get('peak_resp_batt_discharge', -1.0))
        self._dm_peak_gated = int(cfg.get('peak_action_gated', 0) or 0)
        # 该 agent 的"制冷维"下标 & "电池维"下标（由原类的 _cool_dim 得知制冷位）
        _cd = list(getattr(self, '_cool_dim', None) or [])
        self._dm_cool_idx = [int(v) if v is not None else 2 for v in _cd] or [2, 2, 2]
        # 电池维：active_actions 顺序为 [dhw_storage, electrical_storage, cooling_device]
        #   ⇒ 电池下标恒为 1（实测确认；见 probe_ma_action_apply.py）
        self._dm_batt_idx = 1
        if self._dm_peak_dim > 0:
            self._dm_extend_action_space()
            try:
                log_once(
                    'district_peak_action_on',
                    f'[district-marl] 结构化动作已启用：每 agent 动作 '
                    f'3 → {3 + self._dm_peak_dim} 维'
                    f'（+a_peak_resp∈[0,1]；制冷降额×{self._dm_peak_cool_frac:g} '
                    f'电池放电→{self._dm_peak_batt_disch:g}'
                    f'；门控={"峰值步" if self._dm_peak_gated else "无"})',
                )
            except Exception:
                pass

    # ---- 【方案 3】动作空间扩展 -------------------------------------------
    def _dm_extend_action_space(self) -> None:
        """把 a_peak_resp（Box[0,1]）追加到每个 agent 的动作 Box 尾部。

        ⚠️ 只在 peak_action_dim>0 时调用 ⇒ 关闭时动作空间逐位不变（零侵入）。
        """
        if self._dm_peak_dim <= 0:
            return
        try:
            base_space = dict(self.action_space)
        except Exception:
            return
        if not base_space:
            return
        pad_low = np.zeros(self._dm_peak_dim, dtype=np.float32)
        pad_high = np.ones(self._dm_peak_dim, dtype=np.float32)
        try:
            self.action_space = spaces.Dict({
                k: spaces.Box(
                    low=np.concatenate([np.asarray(v.low, dtype=np.float32), pad_low]),
                    high=np.concatenate([np.asarray(v.high, dtype=np.float32), pad_high]),
                    dtype=np.float32,
                )
                for k, v in base_space.items()
            })
        except Exception as exc:  # pragma: no cover
            self._dm_peak_dim = 0
            try:
                log_once('district_peak_action_space_fail',
                         f'[district-marl] 动作空间扩展失败，已降级为不扩展: {exc}')
            except Exception:
                pass

    @property
    def peak_action_active(self) -> bool:
        """结构化动作是否真正启用（供日志 / 自检）。"""
        return bool(self._dm_peak_dim > 0)

    def _dm_is_peak_step(self) -> bool:
        """【仅门控模式用】当前步是否判定为"社区峰值步"。

        ⚠️ 3a（纯学习）下 peak_action_gated=0 ⇒ 本函数不被调用，
           因为门控会引入"峰值判据"这一规则先验（那是 3b 的形态）。
        """
        try:
            nets = [float(v) for v in self._dm_net_by_building()]
            dn = float(sum(nets))
            pk = float(getattr(self._dm_extractor, 'peak', 0.0) or 0.0)
            thr = float(self._dm_cfg.peak_net)
            return bool(dn >= max(thr, pk * 0.95))
        except Exception:
            return False

    def _dm_peak_action_apply(self, action):
        """把第 4 维 a_peak_resp 落实为"制冷降额 + 电池放电"。

        规则（a = a_peak_resp，裁剪到 [0,1]）：
            cool' = cool × (1 - a·(1 - PEAK_RESP_COOL_FRAC))   # a=1 ⇒ ×COOL_FRAC
            batt' = batt + a·(BATT_DISCHARGE - batt)           # a=1 ⇒ 满放
          a=0 ⇒ cool'/batt' **逐位等于** 原值 ⇒ 退回原 3 维行为（零侵入）。

        ⚠️ 必须在原类 `_cool_action_apply` **之前**调用：我们只改前 3 维的数值，
           制冷维的 a_ref 倍率换算仍由原流程负责，两者叠加不冲突。
        """
        if self._dm_peak_dim <= 0 or not isinstance(action, dict):
            return action
        gated = bool(self._dm_peak_gated)
        is_peak = self._dm_is_peak_step() if gated else True
        out = {}
        for aid, vec in action.items():
            try:
                arr = np.array(vec, dtype=np.float32, copy=True).reshape(-1)
                # 第 4 维（下标 3）—— 只在确有该维时处理
                if arr.size > 3:
                    a = float(min(max(arr[3], 0.0), 1.0))
                    if gated and not is_peak:
                        a = 0.0                      # 门控：非峰值步不允许削峰
                    # 把第 4 维清零，避免被下游 inner env 当作非法/多余动作
                    arr = arr[:3].copy() if arr.size == 4 else arr
                    if a > 0.0:
                        try:
                            i = self._dm_ids.index(aid)
                        except ValueError:
                            i = -1
                        ci = self._dm_cool_idx[i] if 0 <= i < len(self._dm_cool_idx) else 2
                        bi = self._dm_batt_idx
                        if 0 <= ci < arr.size:
                            c = float(min(max(arr[ci], 0.0), 1.0))
                            lo = float(self._dm_peak_cool_frac)
                            arr[ci] = float(min(max(c * (1.0 - a * (1.0 - lo)), 0.0), 1.0))
                        if 0 <= bi < arr.size:
                            b = float(min(max(arr[bi], -1.0), 1.0))
                            tgt = float(min(max(self._dm_peak_batt_disch, -1.0), 1.0))
                            arr[bi] = float(min(max(b + a * (tgt - b), -1.0), 1.0))
                out[aid] = arr
            except Exception:
                out[aid] = vec
        return out

    def step(self, action):
        """先落实结构化削峰维（方案 3），再走原流程（含 a_ref 制冷映射）。"""
        if self._dm_peak_dim > 0:
            action = self._dm_peak_action_apply(action)
        return super().step(action)

    # ---- 观测空间扩展 -------------------------------------------------------
    def _dm_extend_observation_space(self) -> None:
        """把区域维追加到每个 agent 的 Box 上（low=-1 / high=+1）。"""
        n = self._dm_n_extra
        if n <= 0:
            return
        try:
            base_space = dict(self.observation_space)
        except Exception:
            return
        if not base_space:
            return
        pad_low = -np.ones(n, dtype=np.float32)
        pad_high = np.ones(n, dtype=np.float32)
        try:
            self.observation_space = spaces.Dict({
                k: spaces.Box(
                    low=np.concatenate([np.asarray(v.low, dtype=np.float32), pad_low]),
                    high=np.concatenate([np.asarray(v.high, dtype=np.float32), pad_high]),
                    dtype=np.float32,
                )
                for k, v in base_space.items()
            })
        except Exception as exc:  # pragma: no cover - 空间异常时降级为"不扩展"
            self._dm_n_extra = 0
            try:
                log_once('district_obs_space_fail',
                         f'[district-marl] 观测空间扩展失败，已降级为不扩展: {exc}')
            except Exception:
                pass

    # ---- 当前步读楼栋量 -----------------------------------------------------
    def _dm_net_by_building(self) -> List[float]:
        """每栋当前步的净用电（买电>0 / 卖电<0）。"""
        return self._dm_read_scalar_attr(
            ('net_electricity_consumption',), default=0.0)

    def _dm_soc_by_building(self) -> Optional[List[float]]:
        """每栋当前步的电池 SOC；只要有一栋读不到就返回 None（整列退化为中性）。"""
        vals = self._dm_read_scalar_attr(('electrical_storage', 'soc'), default=None)
        if any(v is None for v in vals):
            return None
        return [float(v) for v in vals]

    @staticmethod
    def _dm_current_index(building) -> int:
        """当前步在楼栋时序数组里的下标。

        ⚠️ 实测结论（ray 2.10 / citylearn 2.5）：`Building.net_electricity_consumption`
           返回 `[:time_step+1]`，而**末位是尚未计算的占位 0**；真实当前步值在
           `time_step - 1`（time_step≥1）。SOC 数组同理（长度固定，末位为 0）。
           若误用末位，所有"用电/储能"类特征会在步进后恒为 0（本包曾踩到，
           表现为 is_valley 恒为 1、区域内奖励恒为 0 —— 静默失效）。
        """
        try:
            ts = int(getattr(building, 'time_step', 0) or 0)
        except (TypeError, ValueError):
            ts = 0
        return ts - 1 if ts >= 1 else 0

    def _dm_read_scalar_attr(self, path, default):
        """按属性路径逐栋读取"当前步标量"。

        path 形如 ('electrical_storage', 'soc') —— 逐级 getattr 后按下标取值。
        任何一步失败 ⇒ 该栋记 default（None 表示"读不到"）。
        """
        buildings = list(getattr(self, '_ctx_buildings', None) or [])
        out: List[Any] = []
        for b in buildings:
            try:
                obj: Any = b
                for name in path:
                    obj = getattr(obj, name)
                if obj is None:
                    out.append(default)
                    continue
                arr = np.atleast_1d(np.asarray(obj, dtype=float))
                if not arr.size:
                    out.append(default)
                    continue
                idx = min(max(self._dm_current_index(b), 0), int(arr.size) - 1)
                out.append(float(arr[idx]))
            except Exception:
                out.append(default)
        return out

    # ---- 生命周期 -----------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        # 必须在 super().reset() 之前清状态：后者内部会调用 _ctx_augment（用新峰值）
        try:
            self._dm_extractor.reset()
        except Exception:
            pass
        return super().reset(seed=seed, options=options)

    # ---- 观测拼接 -----------------------------------------------------------
    def _ctx_augment(self, observations):
        """原类的拼接结果 + 区域特征（逐 agent 追加）。"""
        observations = super()._ctx_augment(observations)
        if self._dm_n_extra <= 0 or not isinstance(observations, dict):
            return observations
        try:
            feats = self._dm_extractor.update(
                self._dm_net_by_building(), self._dm_soc_by_building())
        except Exception as exc:
            try:
                log_once('district_feat_fail',
                         f'[district-marl] 区域特征计算失败，本步退化为不追加: {exc}')
            except Exception:
                pass
            return observations

        out: Dict[str, Any] = {}
        for pos, (agent_id, o) in enumerate(observations.items()):
            row = self._dm_row_for(agent_id, pos, feats)
            try:
                base = np.asarray(o, dtype=np.float32).reshape(-1)
                out[agent_id] = np.concatenate([base, row]).astype(np.float32)
            except Exception:
                out[agent_id] = o
        return out

    def _dm_row_for(self, agent_id: str, pos: int, feats: np.ndarray) -> np.ndarray:
        """取该 agent 对应的区域特征行（按 _ctx_ids 定位，取不到则按遍历位置）。"""
        idx = -1
        try:
            idx = self._dm_ids.index(agent_id)
        except ValueError:
            idx = pos
        if 0 <= idx < feats.shape[0]:
            return feats[idx].astype(np.float32)
        return np.zeros(self._dm_n_extra, dtype=np.float32)

    # ---- 诊断 --------------------------------------------------------------
    def district_debug(self) -> Dict[str, Any]:
        """当前区域状态快照（供训练日志/排查用）。"""
        d = dict(self._dm_extractor.describe())
        d['enabled'] = bool(self._dm_n_extra > 0)
        return d
