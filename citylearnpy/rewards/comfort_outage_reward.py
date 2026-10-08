"""
comfort_outage_reward.py —— Multi-agent SAC 的自定义逐步奖励
============================================================

【这个文件在做什么？（一句话）】
  CityLearn 每走 1 个仿真小时，就会对本社区每一栋楼算出一个「标量奖励」。
  本类 ComfortOutagePenaltyReward 定义：怎么从当步观测算出这个奖励。
  Multi-agent.py 在构建环境时把 reward_function=本类 传进去，SAC 就会
  按这里的信号去学「电池怎么充放、要不要制冷」等策略。

【奖励在强化学习里扮演什么角色？】
  - 观测 observations：当前室内外温度、电价、净用电、电池 SOC、是否停电……
  - 动作 actions：由策略网络给出（本文件不直接读动作，只看动作造成的后果）
  - 奖励 reward：越大越好。正数 = 鼓励刚才的行为；负数 = 惩罚。
  - SAC 的目标：最大化长期累计奖励（不是某一小时「看起来省电」就行）

【本奖励的设计目标（多目标折中）】
  1) 舒适地板：有人在家时，明显过热/过冷要重罚；仅在舒适带(band)外才鼓励制冷
  2) 电网经济：贵电多买电要罚；低价乱放电要罚；高价放电、谷时适度充电可奖
  3) 尖峰削峰：楼栋或社区净用电过高时，禁充、鼓励放电（有 SOC 下限）
  4) 停电韧性：停电时未满足负荷比例越高罚越重；有电不放还加重罚
  5) 压无效循环：频繁充↔放（churn）、长期空转、充放损耗代理项，避免「为刷分瞎动电池」

【相对 v6 的舒适折中（方案 1+2）→ P0 再平衡（相对 online_1 vs NOCONTROL）】
  - 抬高：过热地板 / 温差惩罚 / 过热不制冷罚 / 过热有制冷奖
  - 抬高：停电未供电、停电过热、停电捂电不放
  - 过热时进一步削弱省电项（hot_energy_scale 更小），避免「关冷刷成本」
  - 非过热时仍保留成本/尖峰/谷充信号；略降谷充、加压损耗逻辑不变

【CityLearn 如何调用？】
  每步：env 收集各楼观测列表 → reward.calculate(observations) → 返回每楼一个 float
  若 central_agent=True（集中式），则把各楼奖励求和，只返回一个总分。
  episode 开始/重置时会调用 reset()，清空本类维护的跨步状态（空闲条数、累计充放等）。

【阅读建议】
  先看文件顶部辅助函数（温度差、是否不适、停电未供电比例），
  再看 ComfortOutagePenaltyReward.calculate() 里「各项 r_* 相加」的主循环。
"""

from __future__ import annotations

from typing import Any, List, Mapping, Union

# CityLearn 奖励基类：子类通常只需实现 calculate()，可选覆盖 reset()
from citylearn.reward_function import RewardFunction


# =============================================================================
# 辅助函数：从「单栋楼观测字典」里安全取值 / 判断舒适与停电
# =============================================================================
# 说明：观测里字段有时缺失、有时是 None；训练中不能因此抛异常，
# 所以统一用 _f 转成 float，并用「有则用现成 delta，无则自行相减」做兼容。


def _f(o: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    """
    从观测字典安全读取浮点数。

    - key 不存在 → 用 default
    - 值为 None → 用 default
    - 否则 float(v)
    """
    v = o.get(key, default)
    if v is None:
        return float(default)
    return float(v)


def _cooling_delta(o: Mapping[str, Any]) -> float:
    """
    制冷温差（室内相对制冷设定点偏热多少）。

    定义：indoor - cooling_set_point
      > 0  → 室内比制冷设定点热（需要制冷才能往下压）
      ≤ 0  → 已经够凉或更冷

    优先读 CityLearn 预计算字段 indoor_dry_bulb_temperature_cooling_delta；
    若无该字段，则用室内干球温度减去制冷设定点手动算。
    """
    if 'indoor_dry_bulb_temperature_cooling_delta' in o:
        return _f(o, 'indoor_dry_bulb_temperature_cooling_delta')
    indoor = o.get('indoor_dry_bulb_temperature')
    sp = o.get('indoor_dry_bulb_temperature_cooling_set_point')
    if indoor is None or sp is None:
        return 0.0
    return float(indoor) - float(sp)


def _heating_delta(o: Mapping[str, Any]) -> float:
    """
    制热温差（室内相对制热设定点偏冷多少）。

    定义：indoor - heating_set_point
      < 0  → 室内比制热设定点冷（偏冷不适）
      ≥ 0  → 不冷或更热

    优先读 indoor_dry_bulb_temperature_heating_delta，否则手动相减。
    """
    if 'indoor_dry_bulb_temperature_heating_delta' in o:
        return _f(o, 'indoor_dry_bulb_temperature_heating_delta')
    indoor = o.get('indoor_dry_bulb_temperature')
    sp = o.get('indoor_dry_bulb_temperature_heating_set_point')
    if indoor is None or sp is None:
        return 0.0
    return float(indoor) - float(sp)


def _is_hot_discomfort(o: Mapping[str, Any]) -> bool:
    """
    是否判定为「过热不适」。

    条件（同时满足）：
      1) 有人在家（occupant_count > 0）；无人则不罚舒适，避免空房刷分
      2) 制冷温差 > comfort_band（默认 2°C）
         即：室内比制冷设定点高出一个舒适带以上，才算明显过热
    """
    if _f(o, 'occupant_count') <= 0.0:
        return False
    band = _f(o, 'comfort_band', 2.0)
    return _cooling_delta(o) > band


def _is_cold_discomfort(o: Mapping[str, Any]) -> bool:
    """
    是否判定为「过冷不适」。

    条件：
      1) 有人在家
      2) 制热温差 < -comfort_band
         即：室内比制热设定点低出一个舒适带以上
    """
    if _f(o, 'occupant_count') <= 0.0:
        return False
    band = _f(o, 'comfort_band', 2.0)
    return _heating_delta(o) < -band


def _outage_unserved_fraction(o: Mapping[str, Any]) -> float:
    """
    停电时「未满足负荷」占「期望负荷」的比例，范围 [0, 1]。

    直觉：
      - 不停电 → 直接返回 0（本项不参与惩罚）
      - 停电时：期望负荷 = 冷/热/生活热水需求 + 不可转移用电
        实际供电 ≈ 各设备用电×效率 + 储冷/储热/储热水放电 +
                   （光伏 + 电池放电 − HVAC 用电）能分给不可转移负荷的部分
      - unserved / expected 越大 → 停电时「该供的没供上」越多 → 惩罚越重

    返回值会截断到 [0, 1]，方便乘权重后作为奖励项。
    """
    # power_outage 通常为 0/1；用 0.5 阈值兼容浮点
    if _f(o, 'power_outage') < 0.5:
        return 0.0

    cooling = max(0.0, _f(o, 'cooling_demand'))
    heating = max(0.0, _f(o, 'heating_demand'))
    dhw = max(0.0, _f(o, 'dhw_demand'))
    nsl = max(0.0, _f(o, 'non_shiftable_load'))
    expected = cooling + heating + dhw + nsl
    if expected <= 1e-6:
        return 0.0  # 没有期望负荷，谈不上「未供电」

    # 设备效率：电 → 热/冷 的转换系数；下限夹到 1e-6 防除零
    cool_eff = max(_f(o, 'cooling_device_efficiency', 1.0), 1e-6)
    heat_eff = max(_f(o, 'heating_device_efficiency', 1.0), 1e-6)
    dhw_eff = max(_f(o, 'dhw_device_efficiency', 1.0), 1e-6)

    cool_elec = max(0.0, _f(o, 'cooling_electricity_consumption'))
    heat_elec = max(0.0, _f(o, 'heating_electricity_consumption'))
    dhw_elec = max(0.0, _f(o, 'dhw_electricity_consumption'))
    hvac_elec = cool_elec + heat_elec + dhw_elec

    # storage_*_electricity_consumption：充为正、放为负（CityLearn 约定）
    # 放电量取 -consumption 的正部，再乘效率，近似「实际送到负荷侧的能量」
    cool_stor_dis = max(0.0, -_f(o, 'cooling_storage_electricity_consumption')) * cool_eff
    heat_stor_dis = max(0.0, -_f(o, 'heating_storage_electricity_consumption')) * heat_eff
    dhw_stor_dis = max(0.0, -_f(o, 'dhw_storage_electricity_consumption')) * dhw_eff

    # HVAC 用电×效率 + 储热/储冷放电 ≈ 已服务的冷热/热水需求
    served = (
        cool_elec * cool_eff
        + heat_elec * heat_eff
        + dhw_elec * dhw_eff
        + cool_stor_dis
        + heat_stor_dis
        + dhw_stor_dis
    )

    # 不可转移负荷：靠「光伏 + 电池放电 − HVAC 已用电」的剩余功率去顶
    solar = max(0.0, _f(o, 'solar_generation'))
    bat_elec = _f(o, 'electrical_storage_electricity_consumption')
    discharge = max(0.0, -bat_elec)
    nsl_served = min(nsl, max(0.0, solar + discharge - hvac_elec))
    served += nsl_served

    unserved = max(0.0, expected - min(served, expected))
    return float(min(1.0, unserved / expected))


def _expected_load(o: Mapping[str, Any]) -> float:
    """
    当前步「期望总负荷」的粗略估计（冷+热+热水+不可转移）。

    用于停电逻辑：若期望负荷极小，就不必强求电池放电。
    """
    return (
        max(0.0, _f(o, 'cooling_demand'))
        + max(0.0, _f(o, 'heating_demand'))
        + max(0.0, _f(o, 'dhw_demand'))
        + max(0.0, _f(o, 'non_shiftable_load'))
    )


# =============================================================================
# 主类：逐步奖励 = 多项 r_* 的加权和
# =============================================================================


class ComfortOutagePenaltyReward(RewardFunction):
    """
    舒适地板 + 尖峰/贵电电池 shaping + 分楼吞吐软约束。

    每个仿真步，对每栋楼计算：
      reward = r_energy + r_price + r_timing + r_peak + r_valley
             + r_soc + r_prepeak + r_idle_full + r_throughput + r_streak
             + r_churn + r_loss
             + r_hot + r_hot_delta + r_cool_floor
             + r_cold + r_cold_delta
             + r_outage + r_outage_hot + r_outage_bat

    多数项为负（惩罚），少数为明确正奖励（如尖峰放电、谷充、过热时有制冷）。
    调权重 = 调「智能体更在意舒适还是电费」；默认值已按课题折中调过。
    """

    def __init__(
        self,
        env_metadata: Mapping[str, Any],
        exponent: float = None,
        # --- 舒适折中（方案 1）+ P0 再平衡默认值 ---
        # energy_weight: 对「从电网净买入电量」的基础惩罚系数（越大越省电导向）
        energy_weight: float = 1.0,
        # hot_discomfort_weight: 一旦判定过热，固定扣这么多分（地板惩罚）
        # P0: 3.0 → 5.5（≈1.8×），压 B1 类「关冷省电」
        hot_discomfort_weight: float = 5.5,
        # temperature_delta_weight / exponent: 过热温差越大，惩罚按幂次加剧
        # P0: 0.35 → 0.55，温差越大罚得越狠
        temperature_delta_weight: float = 0.55,
        temperature_delta_exponent: float = 2.0,
        # cold_* : 过冷对称项（本次不过度抬高，避免矫枉过正回潮过冷）
        cold_discomfort_weight: float = 2.2,
        cold_delta_weight: float = 0.40,
        # hot_energy_scale: 过热时 r_energy 再乘该系数（越小 = 越不在乎省电）
        # P0: 0.35 → 0.15；且 calculate() 里过热时本来就不加 r_price
        hot_energy_scale: float = 0.15,
        # no_cool_when_hot_weight / cool_when_hot_reward:
        #   仅当过热超出 band 时：不制冷重罚；有制冷给小奖
        # P0: 不制冷 2.2→4.0；有制冷奖 0.45→0.90
        no_cool_when_hot_weight: float = 4.0,
        cool_when_hot_reward: float = 0.90,
        # 停电相关权重（P0 约 1.6–1.8×）
        outage_unserved_weight: float = 10.0,
        outage_hot_weight: float = 4.0,
        outage_no_discharge_weight: float = 5.5,
        # --- 电价 / 尖峰 ---
        # price_import_weight: 贵电时段买电的额外惩罚强度
        price_import_weight: float = 1.5,
        # high_price_threshold: 低于此价视为「便宜电」；≥ 视为贵电（单位随数据集电价）
        high_price_threshold: float = 0.05,
        # 低价还放电 → 罚；贵电充电 → 罚；贵电放电 → 奖
        cheap_discharge_weight: float = 4.0,
        # 低价放电时，若净用电已很高（社区/楼也很忙），可部分豁免「不该低价放」
        cheap_discharge_net_exempt: float = 5.5,
        high_price_charge_weight: float = 3.5,
        expensive_discharge_reward: float = 2.2,
        # 尖峰：充电重罚、该放不放罚、放电有奖
        peak_charge_weight: float = 6.0,
        peak_no_discharge_weight: float = 3.5,
        peak_discharge_reward: float = 1.4,
        # 判定「楼栋尖峰 / 社区尖峰」的净用电阈值
        building_peak_net: float = 3.0,
        district_peak_net: float = 6.0,
        # 尖峰鼓励放电的 SOC 下限：太低就不逼它放，留应急
        soc_discharge_min: float = 0.35,
        # --- SOC / 谷充 / 峰前 ---
        valley_net: float = 1.0,
        valley_district_net: float = 4.0,
        valley_charge_reward: float = 0.35,
        low_soc_no_charge_weight: float = 3.0,
        # 希望 SOC 落在 [soc_band_low, soc_band_high]；出带惩罚
        soc_band_low: float = 0.42,
        soc_band_high: float = 0.80,
        soc_band_weight: float = 2.2,
        # 峰前时段（小时）：提前把 SOC 充到 prepeak_soc_target 以上
        prepeak_hours: tuple = (14, 15, 16, 17),
        prepeak_soc_target: float = 0.55,
        prepeak_low_soc_weight: float = 3.0,
        high_soc_threshold: float = 0.95,
        # 电池几乎满电却不放电、且还在买电 → 小罚（浪费调峰潜力）
        idle_full_soc_weight: float = 0.25,
        # --- 分楼吞吐（过热时关闭 underuse）---
        # activity_rate = 累计|电池电量| / 步数；过低且低 SOC → underuse；过高 → overuse
        underuse_rate: float = 0.03,
        underuse_weight: float = 1.2,
        underuse_min_steps: int = 48,  # 前 N 步先不判 underuse，避免开局误罚
        overuse_rate: float = 0.20,
        overuse_weight: float = 1.2,
        # --- 降无效循环（方案 2：略加压损耗）---
        idle_streak_steps: int = 48,   # 连续多少步「几乎不动电池」才开始罚
        idle_streak_weight: float = 0.06,
        churn_window: int = 4,         # 看最近几步充放电符号是否翻转
        churn_penalty_weight: float = 2.5,
        loss_penalty_weight: float = 0.03,  # 累计充电 − 累计放电 的损耗代理
        # |电池电量| 小于此值视为「空闲」，避免浮点噪声当成充放电
        min_bat_activity: float = 0.05,
        **kwargs,
    ):
        # 调用 CityLearn 基类：保存 env_metadata、exponent（净用电惩罚的幂次）等
        super().__init__(env_metadata, exponent=exponent, **kwargs)

        # ---- 把构造参数存成实例属性，供 calculate() 使用 ----
        self.energy_weight = float(energy_weight)
        self.hot_discomfort_weight = float(hot_discomfort_weight)
        self.temperature_delta_weight = float(temperature_delta_weight)
        self.temperature_delta_exponent = float(temperature_delta_exponent)
        self.cold_discomfort_weight = float(cold_discomfort_weight)
        self.cold_delta_weight = float(cold_delta_weight)
        self.hot_energy_scale = float(hot_energy_scale)
        self.no_cool_when_hot_weight = float(no_cool_when_hot_weight)
        self.cool_when_hot_reward = float(cool_when_hot_reward)
        self.outage_unserved_weight = float(outage_unserved_weight)
        self.outage_hot_weight = float(outage_hot_weight)
        self.outage_no_discharge_weight = float(outage_no_discharge_weight)
        self.price_import_weight = float(price_import_weight)
        self.high_price_threshold = float(high_price_threshold)
        self.cheap_discharge_weight = float(cheap_discharge_weight)
        self.cheap_discharge_net_exempt = float(cheap_discharge_net_exempt)
        self.high_price_charge_weight = float(high_price_charge_weight)
        self.expensive_discharge_reward = float(expensive_discharge_reward)
        self.peak_charge_weight = float(peak_charge_weight)
        self.peak_no_discharge_weight = float(peak_no_discharge_weight)
        self.peak_discharge_reward = float(peak_discharge_reward)
        self.building_peak_net = float(building_peak_net)
        self.district_peak_net = float(district_peak_net)
        self.soc_discharge_min = float(soc_discharge_min)
        self.valley_net = float(valley_net)
        self.valley_district_net = float(valley_district_net)
        self.valley_charge_reward = float(valley_charge_reward)
        self.low_soc_no_charge_weight = float(low_soc_no_charge_weight)
        self.soc_band_low = float(soc_band_low)
        self.soc_band_high = float(soc_band_high)
        self.soc_band_weight = float(soc_band_weight)
        self.prepeak_hours = tuple(int(h) for h in prepeak_hours)
        self.prepeak_soc_target = float(prepeak_soc_target)
        self.prepeak_low_soc_weight = float(prepeak_low_soc_weight)
        self.high_soc_threshold = float(high_soc_threshold)
        self.idle_full_soc_weight = float(idle_full_soc_weight)
        self.underuse_rate = float(underuse_rate)
        self.underuse_weight = float(underuse_weight)
        self.underuse_min_steps = int(underuse_min_steps)
        self.overuse_rate = float(overuse_rate)
        self.overuse_weight = float(overuse_weight)
        self.idle_streak_steps = int(idle_streak_steps)
        self.idle_streak_weight = float(idle_streak_weight)
        self.churn_window = int(churn_window)
        self.churn_penalty_weight = float(churn_penalty_weight)
        self.loss_penalty_weight = float(loss_penalty_weight)
        self.min_bat_activity = float(min_bat_activity)

        # ---- 跨步状态（按「楼栋下标」各维护一份列表）----
        # _bat_idle_streak[i] : 第 i 栋楼电池连续「空闲」了多少步
        # _bat_sign_hist[i]   : 最近若干步的充放电符号（1 充 / -1 放 / 0 闲），用于检测 churn
        # _cum_charge[i]      : 累计充电电量
        # _cum_discharge[i]   : 累计放电电量
        # _cum_abs[i]         : 累计 |电池电量|，用来算平均活动率
        # _step_count         : 本 episode 已走步数（所有楼共享同一个时钟）
        self._bat_idle_streak: List[int] = []
        self._bat_sign_hist: List[List[int]] = []
        self._cum_charge: List[float] = []
        self._cum_discharge: List[float] = []
        self._cum_abs: List[float] = []
        self._step_count: int = 0

    def reset(self) -> None:
        """
        episode 重置时清空跨步统计。

        若不重置，上一局的累计充放、空闲条数会污染下一局的 underuse/churn/loss，
        导致奖励尺度漂移、训练不稳定。
        """
        super().reset()
        self._bat_idle_streak = []
        self._bat_sign_hist = []
        self._cum_charge = []
        self._cum_discharge = []
        self._cum_abs = []
        self._step_count = 0

    def _ensure_state(self, n: int) -> None:
        """
        保证内部列表长度 = 当前楼栋数 n。

        第一次 calculate 或楼栋数变化时，重新初始化为全 0 / 空历史。
        """
        if len(self._bat_idle_streak) != n:
            self._bat_idle_streak = [0] * n
            self._bat_sign_hist = [[] for _ in range(n)]
            self._cum_charge = [0.0] * n
            self._cum_discharge = [0.0] * n
            self._cum_abs = [0.0] * n

    def calculate(self, observations: List[Mapping[str, Union[int, float]]]) -> List[float]:
        """
        核心入口：根据本步各楼观测，返回各楼奖励列表。

        参数:
          observations: 长度 = 楼栋数；每个元素是该楼当前小时的观测字典。

        返回:
          - 默认（独立多智能体）：[r0, r1, ..., r_{n-1}]，与楼一一对应
          - central_agent=True：[sum(ri)]，只返回一个社区总分

        计算顺序概览:
          ① 社区层：汇总 district_net，判断社区是否尖峰/谷底，算 peak_scale
          ② 逐楼：读净用电、电价、SOC、电池功率、是否停电/过热/过冷……
          ③ 更新该楼跨步统计（累计吞吐、空闲条、充放符号历史）
          ④ 累加各项 r_*（电网、电价时机、尖峰、谷充、SOC、舒适、停电……）
          ⑤ 打包返回
        """
        reward_list: List[float] = []
        # exponent：基类字段；None 时按 1.0（对净用电线性惩罚）
        exp = 1.0 if self.exponent is None else float(self.exponent)
        n_buildings = len(observations)
        self._ensure_state(n_buildings)
        self._step_count += 1

        # ---------- 社区层信号（所有楼共享） ----------
        # district_net：本社区所有楼净用电之和；>0 表示整体从电网买电
        district_net = sum(_f(o, 'net_electricity_consumption') for o in observations)
        district_peak = district_net >= self.district_peak_net
        district_valley = district_net <= self.valley_district_net
        # 社区负荷越高，尖峰放电奖励越大（相对 district_peak_net 归一到约 [0.5, 2.5]）
        peak_scale = min(max(district_net / max(self.district_peak_net, 1e-6), 0.5), 2.5)

        # ---------- 逐栋计算 ----------
        for i, o in enumerate(observations):
            # ===== A. 本步原始量与布尔标志 =====
            net = _f(o, 'net_electricity_consumption')          # 该楼净用电（买电>0，卖电/余电<0）
            price = _f(o, 'electricity_pricing')                # 当前电价
            soc = _f(o, 'electrical_storage_soc')               # 电池荷电状态 ∈[0,1] 左右
            # 电池电功率：>0 充电，<0 放电（CityLearn electrical_storage 约定）
            bat_elec = _f(o, 'electrical_storage_electricity_consumption')
            hour = int(_f(o, 'hour', -1))                       # 一天中的小时 0–23
            charging = bat_elec > self.min_bat_activity
            discharging = (-bat_elec) > self.min_bat_activity
            outage = _f(o, 'power_outage') >= 0.5
            occupied = _f(o, 'occupant_count') > 0.0
            cool_delta = _cooling_delta(o)
            heat_delta = _heating_delta(o)
            hot = occupied and _is_hot_discomfort(o)
            cold = occupied and _is_cold_discomfort(o)
            building_peak = net >= self.building_peak_net
            # 尖峰：不停电，且（本楼尖峰 或 社区尖峰）
            is_peak = (not outage) and (building_peak or district_peak)
            cheap = price < self.high_price_threshold
            expensive = (not cheap) and price >= self.high_price_threshold
            # 谷：不停电，且（电价便宜 或 本楼&社区净用电都偏低）
            is_valley = (not outage) and (
                cheap or (net <= self.valley_net and district_valley)
            )
            # 峰前窗口：例如 14–17 点，提前抬高 SOC，为晚高峰放电做准备
            prepeak = (not outage) and hour in self.prepeak_hours

            # ===== B. 更新跨步统计（供吞吐 / churn / 损耗使用） =====
            # --- 累计吞吐 ---
            if charging:
                self._cum_charge[i] += bat_elec
            if discharging:
                self._cum_discharge[i] += -bat_elec
            self._cum_abs[i] += abs(bat_elec)
            # 平均「电池活动强度」：越大说明这栋楼电池动得越勤
            activity_rate = self._cum_abs[i] / max(self._step_count, 1)

            if abs(bat_elec) < self.min_bat_activity:
                self._bat_idle_streak[i] += 1
                sign = 0  # 空闲
            else:
                self._bat_idle_streak[i] = 0
                sign = 1 if charging else -1
            # 滑动窗口：只保留最近 churn_window 步的符号
            hist = self._bat_sign_hist[i]
            hist.append(sign)
            if len(hist) > self.churn_window:
                del hist[0 : len(hist) - self.churn_window]

            cool_elec = max(0.0, _f(o, 'cooling_electricity_consumption'))

            # ===== C. 电网基础成本项 =====
            # --- 电网基础；过热时削弱「省电」信号，避免弃冷刷分 ---
            # max(net,0)：只惩罚「从电网买电」；向电网送电不在这里给正奖
            r_energy = -self.energy_weight * (max(net, 0.0) ** exp)
            if hot:
                # P0：hot_energy_scale 默认已降至 0.15，过热时几乎不再为省电让路
                r_energy *= self.hot_energy_scale

            # 贵电 + 还在买电 + 非过热：额外按「电价/阈值」放大惩罚
            # （过热时故意不加 r_price，与 hot_energy_scale 同一意图）
            r_price = 0.0
            if (not outage) and expensive and net > 0.0 and (not hot):
                r_price = -self.price_import_weight * net * (
                    price / max(self.high_price_threshold, 1e-6)
                )

            # ===== D. 电价时机 shaping（电池该不该在这个价位动） =====
            # 方案3：低价放电更严；贵电放电奖励；高价充电重罚
            r_timing = 0.0
            # 便宜电还放电，且净用电并不高 → 浪费「本可低价充电」的机会
            if (not outage) and cheap and discharging and net < self.cheap_discharge_net_exempt:
                r_timing -= self.cheap_discharge_weight * min(-bat_elec, 2.0)
            if (not outage) and expensive and charging:
                r_timing -= self.high_price_charge_weight * min(bat_elec, 2.0)
            if (not outage) and expensive and discharging:
                r_timing += self.expensive_discharge_reward * min(-bat_elec, 2.0)

            # ===== E. 尖峰削峰 =====
            # 方案2：尖峰硬禁充（与 SOC 无关）；放电奖励随社区负荷放大
            r_peak = 0.0
            if is_peak and charging:
                # +0.2：即使充得很小也罚一点，堵住「微量充电」钻空子
                r_peak -= self.peak_charge_weight * (abs(bat_elec) + 0.2)
            if is_peak and discharging and soc >= self.soc_discharge_min:
                r_peak += self.peak_discharge_reward * peak_scale * min(-bat_elec, 2.0)
            # SOC 够却尖峰不放 → 按「高出放电下限多少」惩罚
            if is_peak and soc >= self.soc_discharge_min and (not discharging):
                r_peak -= self.peak_no_discharge_weight * (soc - self.soc_discharge_min)

            # ===== F. 谷时充电 =====
            # 谷充（已压低权重，避免为刷谷奖而过度循环）
            # P0：过热时关闭谷充压力，避免「低价强充」和制冷抢功率/抢优化目标
            r_valley = 0.0
            if (not hot) and is_valley and charging and soc < self.high_soc_threshold:
                r_valley += self.valley_charge_reward * min(bat_elec, 1.0)
            if (not hot) and is_valley and soc < self.soc_band_low and (not charging):
                r_valley -= self.low_soc_no_charge_weight * (self.soc_band_low - soc)

            # ===== G. SOC 舒适带 =====
            # 方案1：SOC 带 — 下方二次罚（低 SOC 更危险），上方线性罚（满电浪费调峰空间）
            r_soc = 0.0
            if soc < self.soc_band_low:
                gap = self.soc_band_low - soc
                r_soc -= self.soc_band_weight * (gap + 2.0 * gap * gap)
            elif soc > self.soc_band_high:
                r_soc -= 0.5 * self.soc_band_weight * (soc - self.soc_band_high)

            # ===== H. 峰前备电 =====
            # 峰前目标 SOC≥0.55
            r_prepeak = 0.0
            if prepeak and soc < self.prepeak_soc_target:
                gap = self.prepeak_soc_target - soc
                r_prepeak -= self.prepeak_low_soc_weight * gap
                # 电价便宜却还不充，再加一刀，强化「峰前低价备电」
                if (not charging) and cheap:
                    r_prepeak -= 0.6 * self.low_soc_no_charge_weight * gap

            # 满电空闲却还在买电：轻微提示「可以放电顶峰/自用」
            r_idle_full = 0.0
            if (
                (not outage)
                and soc >= self.high_soc_threshold
                and (not discharging)
                and net > 0.5
            ):
                r_idle_full = -self.idle_full_soc_weight * (
                    soc - self.high_soc_threshold + 0.05
                )

            # ===== I. 吞吐软约束（用得太少 / 用得太疯） =====
            # 低吞吐+低 SOC / 高吞吐软帽；过热时不做 underuse（优先制冷）
            r_throughput = 0.0
            if (not outage) and self._step_count >= self.underuse_min_steps:
                if (
                    (not hot)
                    and activity_rate < self.underuse_rate
                    and soc < self.soc_band_low
                ):
                    # 电池几乎不动 + SOC 又低：既没备电也没参与调峰
                    r_throughput -= self.underuse_weight * (
                        (self.soc_band_low - soc)
                        + (self.underuse_rate - activity_rate) / max(self.underuse_rate, 1e-6)
                    )
                if activity_rate > self.overuse_rate:
                    # 动得太勤：暗示无效循环、损耗上升
                    r_throughput -= self.overuse_weight * (
                        (activity_rate - self.overuse_rate) / max(self.overuse_rate, 1e-6)
                    )

            # 长期低 SOC 不动
            r_streak = 0.0
            streak = self._bat_idle_streak[i]
            if (not outage) and streak >= self.idle_streak_steps and soc < self.soc_band_low:
                # 连续空闲越久，惩罚缓慢加重，但上限夹到 3 倍，避免爆炸
                r_streak = -self.idle_streak_weight * min(
                    streak / self.idle_streak_steps, 3.0
                )

            # ===== J. 充放翻转（churn）与损耗代理 =====
            # 方案4：churn + 累计损耗（充-放）
            r_churn = 0.0
            # 本步在动，且窗口里刚出现过「相反符号」→ 短时内充完又放 / 放完又充
            if sign != 0 and len(hist) >= 2:
                if any(s == -sign for s in hist[:-1] if s != 0):
                    r_churn = -self.churn_penalty_weight * min(abs(bat_elec), 1.5)

            r_loss = 0.0
            # 粗代理：累计充 > 累计放 的差额，可理解为往返损耗/未回吐能量
            loss_proxy = max(0.0, self._cum_charge[i] - self._cum_discharge[i])
            if loss_proxy > 5.0 and activity_rate > self.underuse_rate:
                # 每步摊薄一点，避免早期暴击
                r_loss = -self.loss_penalty_weight * min(loss_proxy / max(self._step_count, 1) * 100.0, 3.0)

            # ===== K. 舒适折中（过热 / 过冷 / 制冷行为） =====
            # --- 舒适折中：仅 band 外鼓励制冷；过冷对称加重 ---
            band = _f(o, 'comfort_band', 2.0)
            # 过热地板：一旦 hot 为真，先扣一笔固定分
            r_hot = -self.hot_discomfort_weight if hot else 0.0
            # 过热温差连续惩罚：hot_excess = max(0, cool_delta)，越大越热
            hot_excess = max(0.0, cool_delta)
            r_hot_delta = (
                -self.temperature_delta_weight * (hot_excess ** self.temperature_delta_exponent)
                if occupied and hot_excess > 0.0
                else 0.0
            )
            r_cool_floor = 0.0
            if occupied and hot_excess > band:
                # 仅明显过热时：不制冷重罚；有制冷小奖（进入 band 内则不再奖）
                if cool_elec < 0.05:
                    r_cool_floor = -self.no_cool_when_hot_weight * (1.0 + (hot_excess - band))
                else:
                    r_cool_floor = self.cool_when_hot_reward * min(cool_elec, 1.5)
            elif cold:
                # 已过冷还在猛制冷 → 额外罚（用制冷电作代理）
                if cool_elec > 0.1:
                    r_cool_floor = -0.8 * self.cold_discomfort_weight * min(cool_elec, 1.5)

            r_cold = -self.cold_discomfort_weight if cold else 0.0
            # cold_excess：室内低于制热设定点的幅度（heat_delta 为负时取正）
            cold_excess = max(0.0, -heat_delta)
            r_cold_delta = (
                -self.cold_delta_weight * (cold_excess ** self.temperature_delta_exponent)
                if occupied and cold_excess > 0.0
                else 0.0
            )

            # ===== L. 停电韧性 =====
            # --- 停电 ---
            unserved = _outage_unserved_fraction(o)
            r_outage = -self.outage_unserved_weight * unserved
            # 停电还过热：额外罚（电池/负荷优先级更苛刻）
            r_outage_hot = -self.outage_hot_weight if (outage and hot) else 0.0
            r_outage_bat = 0.0
            # 停电 + SOC 够 + 确有负荷 + 却不放电 + 仍有未供电 → 重罚「捂电」
            if (
                outage
                and soc >= self.soc_discharge_min
                and _expected_load(o) > 0.1
                and (not discharging)
                and unserved > 0.05
            ):
                r_outage_bat = -self.outage_no_discharge_weight * soc

            # ===== M. 汇总本楼本步奖励 =====
            reward_list.append(
                float(
                    r_energy
                    + r_price
                    + r_timing
                    + r_peak
                    + r_valley
                    + r_soc
                    + r_prepeak
                    + r_idle_full
                    + r_throughput
                    + r_streak
                    + r_churn
                    + r_loss
                    + r_hot
                    + r_hot_delta
                    + r_cool_floor
                    + r_cold
                    + r_cold_delta
                    + r_outage
                    + r_outage_hot
                    + r_outage_bat
                )
            )

        # 集中式智能体：环境只期望一个标量奖励 → 对各楼求和
        if self.central_agent:
            return [sum(reward_list)]
        # 多智能体（本项目 Multi-agent SAC 默认路径）：每楼各自一个奖励
        return reward_list
