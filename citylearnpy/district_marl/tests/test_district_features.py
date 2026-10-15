# -*- coding: utf-8 -*-
"""district_marl 单元测试（可在无 ray 环境下运行）。

覆盖：
  · rank_norm 的并列/单元素/全等/非有限值行为
  · DistrictFeatureExtractor 的形状、值域、共享维一致性与专属维区分度
  · running_peak 的单调性与 reset 语义（跨局不污染）
  · DistrictPeakReward 的区域项数学（隔离父类后单独验证）

运行：
  python -m pytest district_marl/tests/test_district_features.py -q
  python district_marl/tests/test_district_features.py      # 直接跑也可（自带 main）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

# 允许"直接 python 运行"：把 citylearnpy 根目录放进 sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from district_marl.district_features import (  # noqa: E402
    FEATURE_NAMES,
    N_FEATURES,
    DistrictFeatureConfig,
    DistrictFeatureExtractor,
    rank_norm,
)


class _SkipTest(Exception):
    """无 pytest 环境下的跳过信号（自带 runner 用）。"""


def _skip(msg):
    """有 pytest 就用它跳过；否则抛本模块的跳过信号。"""
    try:
        import pytest
        pytest.skip(msg)
    except ImportError:
        raise _SkipTest(msg)


# =============================================================================
# rank_norm
# =============================================================================

def test_rank_norm_basic_order():
    out = rank_norm([10.0, 0.0, 5.0])
    assert out[1] == 0.0 and out[2] == 0.5 and out[0] == 1.0


def test_rank_norm_ties_share_average_rank():
    out = rank_norm([1.0, 1.0, 3.0])
    # 并列的两者取平均名次 (0+1)/2 /2 = 0.25
    assert np.isclose(out[0], 0.25) and np.isclose(out[1], 0.25)
    assert np.isclose(out[2], 1.0)


def test_rank_norm_degenerate_cases():
    assert np.allclose(rank_norm([2.0]), [0.5])
    assert np.allclose(rank_norm([2.0, 2.0, 2.0]), [0.5, 0.5, 0.5])
    # 非有限值当"最低"处理，不传播 NaN
    out = rank_norm([np.nan, 1.0, 2.0])
    assert np.all(np.isfinite(out))


def test_rank_norm_is_order_nonsensitive():
    a = np.array([3.0, 1.0, 2.0])
    b = np.array([2.0, 3.0, 1.0])
    ra, rb = rank_norm(a), rank_norm(b)
    # 同一组数值的排名（按值对齐）应一致
    assert np.isclose(ra[1], rb[2])   # 值 1.0 → 0.0
    assert np.isclose(ra[2], rb[0])   # 值 2.0 → 0.5
    assert np.isclose(ra[0], rb[1])   # 值 3.0 → 1.0


# =============================================================================
# DistrictFeatureExtractor
# =============================================================================

def test_extractor_shape_and_range():
    ex = DistrictFeatureExtractor(3)
    out = ex.update([1.0, 2.0, 3.0], [0.2, 0.5, 0.9])
    assert out.shape == (3, N_FEATURES)
    assert out.dtype == np.float32
    assert np.all(out >= -1.0) and np.all(out <= 1.0)


def test_shared_dims_identical_own_dims_differ():
    ex = DistrictFeatureExtractor(3)
    out = ex.update([1.0, 5.0, 2.0], [0.2, 0.5, 0.9])
    shared = out[:, :5]
    # 5 个共享维在每个 agent 上必须完全相同（"我们一起处在什么状态"）
    for i in range(1, 3):
        assert np.allclose(shared[0], shared[i])
    # 专属维必须能区分楼栋（否则三栋学出同一个策略）
    own = out[:, 5:]
    assert not np.allclose(own[0], own[1])
    # SOC 排名：最低 SOC 的楼排名 0
    soc_rank_idx = FEATURE_NAMES.index('own_soc_rank')
    assert np.isclose(out[0, soc_rank_idx], 0.0)
    assert np.isclose(out[2, soc_rank_idx], 1.0)


def test_running_peak_monotonic_and_headroom():
    ex = DistrictFeatureExtractor(2)
    ex.update([3.0, 3.0], [0.5, 0.5])      # 社区 6.0
    ex.update([1.0, 1.0], [0.5, 0.5])      # 社区 2.0（低于峰值）
    peak = ex.running_peak
    assert np.isclose(peak, 6.0)
    headroom_idx = FEATURE_NAMES.index('dist_headroom')
    row = ex.update([1.0, 1.0], [0.5, 0.5])
    assert row[0, headroom_idx] > 0.0      # 距峰值还有空间
    assert np.isclose(ex.running_peak, 6.0)


def test_is_peak_and_valley_flags():
    cfg = DistrictFeatureConfig(net_scale=9.0, peak_net=6.0, valley_net=4.0)
    ex = DistrictFeatureExtractor(2, cfg)
    hi = ex.update([5.0, 5.0], [0.5, 0.5])   # 社区 10 ≥ 6 ⇒ 尖峰
    assert np.isclose(hi[0, FEATURE_NAMES.index('dist_is_peak')], 1.0)
    ex.reset()
    lo = ex.update([1.0, 1.0], [0.5, 0.5])   # 社区 2 ≤ 4 ⇒ 谷底
    assert np.isclose(lo[0, FEATURE_NAMES.index('dist_is_valley')], 1.0)
    assert np.isclose(lo[0, FEATURE_NAMES.index('dist_is_peak')], 0.0)


def test_reset_clears_cross_episode_state():
    ex = DistrictFeatureExtractor(2)
    ex.update([9.0, 9.0], [0.5, 0.5])
    assert ex.running_peak > 0.0
    ex.reset()
    assert ex.running_peak == 0.0 and ex.steps == 0


def test_soc_missing_degrades_to_neutral():
    ex = DistrictFeatureExtractor(3)
    out = ex.update([1.0, 2.0, 3.0], None)
    idx = FEATURE_NAMES.index('own_soc_rank')
    assert np.allclose(out[:, idx], 0.5)     # 不知道 ⇒ 中性，不制造伪信号


def test_zero_buildings_safe():
    ex = DistrictFeatureExtractor(0)
    out = ex.update([], [])
    assert out.shape == (0, N_FEATURES)


def test_short_input_padded_not_crashing():
    ex = DistrictFeatureExtractor(3)
    out = ex.update([1.0], [0.5])
    assert out.shape == (3, N_FEATURES)
    assert np.all(np.isfinite(out))


# =============================================================================
# DistrictPeakReward：区域项数学（隔离父类）
# =============================================================================

def _bare_reward(**overrides):
    """构造一个**绕过 __init__** 的 reward 实例：只测区域项数学，不依赖 citylearn。"""
    try:
        from district_marl import district_reward as dr
    except Exception as exc:  # pragma: no cover
        _skip(f'需要 citylearn 才能 import 本类: {exc}')
    r = dr.DistrictPeakReward.__new__(dr.DistrictPeakReward)
    r.district_peak_weight = float(overrides.get('district_peak_weight', 0.0))
    r.district_peak_target = float(overrides.get('district_peak_target', 6.0))
    r.district_valley_target = float(overrides.get('district_valley_target', 4.0))
    r.district_net_scale = 9.0
    r.district_team_share = float(overrides.get('district_team_share', 0.0))
    r.district_stagger_weight = float(overrides.get('district_stagger_weight', 0.0))
    r.district_stagger_soc_target = float(overrides.get('district_stagger_soc_target', 0.85))
    r._dm_peak = None
    r._dm_peak_sum = 0.0
    r._dm_over_steps = 0
    r._dm_over_amount = 0.0
    r._dm_steps = 0
    r._dm_last_district_net = 0.0
    return r, dr


def _patch_parent(monkeypatch_base, values_by_call=None):
    """把父类 calculate 换成返回固定值，隔离出区域项。"""
    dr = monkeypatch_base
    original = dr.CustomComfortReward.calculate
    calls = {'n': 0}

    def fake(self, observations):
        calls['n'] += 1
        if values_by_call is not None:
            return list(values_by_call)
        return [0.0] * len(observations)

    dr.CustomComfortReward.calculate = fake
    return original, calls


def test_peak_penalty_only_above_target():
    r, dr = _bare_reward(district_peak_weight=2.0, district_peak_target=6.0)
    original, _ = _patch_parent(dr)
    try:
        obs = [{'net_electricity_consumption': 1.0}] * 3      # 社区 3.0 < 6.0
        assert np.allclose(r.calculate(obs), [0.0, 0.0, 0.0])
        obs2 = [{'net_electricity_consumption': 3.0}] * 3     # 社区 9.0 > 6.0
        # 罚 = 2.0 × (9 − 6) = 6.0
        assert np.allclose(r.calculate(obs2), [-6.0, -6.0, -6.0])
        assert r._dm_over_steps == 1
        assert np.isclose(r._dm_over_amount, 3.0)
    finally:
        dr.CustomComfortReward.calculate = original


def test_team_share_mixes_toward_mean():
    r, dr = _bare_reward(district_team_share=0.5)
    original, _ = _patch_parent(dr, values_by_call=[10.0, 0.0, 0.0])
    try:
        obs = [{'net_electricity_consumption': 0.0}] * 3
        out = r.calculate(obs)
        # 均值 = 10/3；s=0.5 ⇒ [5+5/3, 0+5/3, 0+5/3]
        mean = 10.0 / 3.0
        assert np.allclose(out, [0.5 * 10.0 + 0.5 * mean, 0.5 * mean, 0.5 * mean])
    finally:
        dr.CustomComfortReward.calculate = original


def test_zero_weights_are_identity():
    r, dr = _bare_reward()          # 全默认 0
    original, _ = _patch_parent(dr, values_by_call=[1.0, -2.0, 3.0])
    try:
        obs = [{'net_electricity_consumption': 5.0}] * 3   # 社区 15（会触发尖峰）
        assert np.allclose(r.calculate(obs), [1.0, -2.0, 3.0])
    finally:
        dr.CustomComfortReward.calculate = original


def test_stagger_rewards_lowest_soc_in_valley():
    r, dr = _bare_reward(district_stagger_weight=1.0, district_valley_target=4.0)
    original, _ = _patch_parent(dr)
    try:
        # 社区净用电 3.0 ≤ 4.0 ⇒ 谷底；SOC 越低加分越多
        obs = [
            {'net_electricity_consumption': 1.0, 'electrical_storage_soc': 0.1},
            {'net_electricity_consumption': 1.0, 'electrical_storage_soc': 0.5},
            {'net_electricity_consumption': 1.0, 'electrical_storage_soc': 0.9},
        ]
        out = np.asarray(r.calculate(obs))
        assert out[0] > out[1] > out[2]        # 最空的最该充
        assert np.all(out >= 0.0)
    finally:
        dr.CustomComfortReward.calculate = original


def test_central_agent_length_mismatch_is_passthrough():
    r, dr = _bare_reward(district_peak_weight=5.0)
    original, _ = _patch_parent(dr, values_by_call=[7.0])
    try:
        obs = [{'net_electricity_consumption': 99.0}] * 3   # 父类只回 1 个（central）
        assert r.calculate(obs) == [7.0]                    # 不误改
    finally:
        dr.CustomComfortReward.calculate = original


# =============================================================================
# 环境层回归：CityLearn 占位 0 的坑（本包曾静默失效的地方）
# =============================================================================

def test_current_index_skips_citylearn_placeholder():
    """`Building` 时序数组末位是未计算的占位 0 ⇒ 当前步下标必须是 time_step-1。"""
    try:
        from district_marl.district_env import DistrictContextRLlibEnv
    except Exception as exc:  # pragma: no cover
        _skip(f'需要 citylearn/ray 才能 import 环境类: {exc}')

    class _Bare:
        pass

    b = _Bare()
    for ts, expected in ((0, 0), (1, 0), (2, 1), (5, 4)):
        b.time_step = ts
        assert DistrictContextRLlibEnv._dm_current_index(b) == expected


def test_live_env_district_obs_nonzero_after_step():
    """真环境回归：步进后区域观测量不能恒为 0（占位 0 的静默失效会在这里暴露）。

    ⚠️ 需要 citylearn + ray + 本地数据集缓存，默认跳过；
       设 DISTRICT_MARL_SLOW_TESTS=1 打开。
    """
    if os.environ.get('DISTRICT_MARL_SLOW_TESTS', '0') != '1':
        _skip('慢测试：设 DISTRICT_MARL_SLOW_TESTS=1 打开')

    from district_marl.district_train import district_net_now
    from district_marl.district_env import DistrictContextRLlibEnv
    from district_marl.district_train import build_district_env_config

    cfg = build_district_env_config(
        'citylearn_challenge_2023_phase_2_local_evaluation', 24,
        enable_render=False, district_obs=True)
    env = DistrictContextRLlibEnv(cfg)
    try:
        ids = list(env._agent_ids)
        obs, _ = env.reset()
        assert np.asarray(obs[ids[0]]).size == env.observation_space[ids[0]].shape[0]
        seen = []
        for _ in range(3):
            acts = {k: env.action_space[k].sample() for k in ids}
            obs, _rew, _t, _tr, _i = env.step(acts)
            seen.append(district_net_now(env))
            o = np.asarray(obs[ids[0]], dtype=np.float32)
            assert np.all(np.isfinite(o))
        assert any(abs(v) > 1e-6 for v in seen), f'社区净用电全为 0 ⇒ 取值口径又错了: {seen}'
        assert env._dm_extractor.running_peak > 0.0
    finally:
        try:
            env.close()
        except Exception:
            pass


# =============================================================================

def _run_all():
    """无 pytest 时的极简 runner（跳过信号同时兼容 pytest.Skipped 与 _SkipTest）。"""
    passed = skipped = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_') or not callable(fn):
            continue
        try:
            fn()
            print(f'  [OK] {name}')
            passed += 1
        except BaseException as exc:      # pytest 的 Skipped 继承 BaseException
            if type(exc).__name__ in ('Skipped', '_SkipTest'):
                print(f'  [SKIP] {name}: {exc}')
                skipped += 1
            else:
                print(f'  [FAIL] {name}: {type(exc).__name__}: {exc}')
                raise
    print(f'通过 {passed}，跳过 {skipped}')
    return 0


if __name__ == '__main__':
    sys.exit(_run_all())
