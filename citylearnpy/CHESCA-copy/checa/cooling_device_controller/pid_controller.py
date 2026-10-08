import numpy as np


class PIDController:
    def __init__(self):
        self.Kp = None
        self.Kd = None
        self.Ki = None
        self.dt = None

        self.Kp_outage = None
        self.OutTempScaler = None

        self.integral = 0.0  # integral of error for Ki
        self.prev_error = 0.0  # error last time step for Kd

        self.updated_integral = 0.0
        self.updated_prev_error = 0.0

        # 积分限幅（防 windup）；None 表示不限制
        self.integrator_min = None
        self.integrator_max = None

    def _clamp_integral(self, value):
        if self.integrator_min is not None:
            value = max(self.integrator_min, value)
        if self.integrator_max is not None:
            value = min(self.integrator_max, value)
        return value

    def reset_integral(self):
        self.integral = 0.0
        self.updated_integral = 0.0

    def get_actions(self, b, cur_value, setpoint_value, saturated_perc, outage_flag, outdoor_temp):
        """
        计算本步冷机「电功率需求」粗略值（pid_output），供上层换算 TMP。

        参数
        ----
        b : int
            建筑索引（本函数未使用，保留调用签名兼容）。
        cur_value : float
            当前室内干球温度 (°C)。
        setpoint_value : float
            目标设定温度 (°C)，通常为观测中的 indoor set point。
        saturated_perc : float
            上一步「期望制冷 vs 实际制冷」相对偏差比例 [0,1]。
            接近 0 表示未饱和；较大表示实际出力远低于期望（常见于停电电力不足）。
        outage_flag : bool
            True → 走停电简化控制；False → 走正常 PID。
        outdoor_temp : float
            室外温度 (°C)，停电分支用于额外加热扰动项。

        返回
        ----
        pid_output : float
            近似「希望的冷机电功率需求」(kW 量级，可正可负)。
            · 正值 → 需要制冷（上层再 / nominal_power 得到 TMP∈[0,1]）
            · 负值 → 不需要制冷（上层通常 clip 掉或置 0）

        符号约定（与 CHESCA 标定增益一致）
        --------------------------------
        error = setpoint - indoor
          · 室内偏热（indoor > setpoint）→ error < 0
          · 本工程 Kp、Ki 为负：error < 0 时 P/I 项为正 → 增大制冷需求
          · 室内偏冷（indoor < setpoint）→ error > 0 → 输出倾向为负（少制冷/不制冷）
        """
        # ---------- 1) 跟踪误差 ----------
        # 设定 − 室内：偏热为负，偏冷为正（见上方符号约定）
        error = setpoint_value - cur_value

        # ---------- 2) 饱和时衰减 I / 上一拍误差（防积分在「要得太多、实际给不出」时继续膨胀）----------
        # saturated_perc < 0.04：视为未饱和，直接用当前 I、prev_error 作为本拍更新基线
        # 否则：按饱和程度同比缩小 I 与 prev_error，减轻 windup，再作为本拍基线
        if saturated_perc < 0.04:
            self.updated_integral = self.integral
            self.updated_prev_error = self.prev_error
        else:
            self.integral = self.integral * (1.0 - saturated_perc)
            self.prev_error = self.prev_error * (1.0 - saturated_perc)
            self.updated_integral = self.integral
            self.updated_prev_error = self.prev_error

        anti_windup_frozen = False
        outdoor_term = 0.0
        if not outage_flag:
            # ---------- 3a) 正常工况：完整 PID ----------
            # I 候选：I ← I + Ki * error * dt
            tentative_i = self.updated_integral + self.Ki * error * self.dt
            # P：比例项
            P = self.Kp * error
            # D：误差变化率（相对上一有效误差）
            D = self.Kd * (error - self.updated_prev_error) / self.dt
            # 用「候选 I」试算整拍输出，判断是否会继续向「负需求」方向积分
            tentative_out = P + tentative_i + D

            # 抗 windup（负向）：
            # 若试算输出已 < 0（本就不制冷），且本拍 I 增量仍在把积分往更负推，
            # 则冻结积分（不采纳 tentative_i），避免长期负饱和导致之后很难恢复正制冷。
            # 否则采纳 tentative_i，并做积分上下限钳位（integrator_min/max）。
            if tentative_out < 0.0 and (self.Ki * error * self.dt) < 0.0:
                self.integral = self._clamp_integral(self.updated_integral)
                anti_windup_frozen = True
            else:
                self.integral = self._clamp_integral(tentative_i)

            self.prev_error = error
            pid_output = P + self.integral + D
        else:
            # ---------- 3b) 停电工况：简化控制（不用完整 I/D）----------
            # 比例项改用停电增益 Kp_outage；再加室外−室内温差项，
            # 室外明显高于室内时增大制冷倾向（有限电力下尽量压热）。
            P = self.Kp_outage * error
            D = 0.0
            outdoor_term = self.OutTempScaler * (outdoor_temp - cur_value)
            pid_output = P + outdoor_term
            tentative_out = pid_output

        # 供推演剧本 / CSV：本拍入参与中间量（不改变控制逻辑）
        self._trace_last = {
            'pid_indoor_temp': float(cur_value),
            'pid_setpoint_temp': float(setpoint_value),
            'pid_outdoor_temp': float(outdoor_temp),
            'pid_error': float(error),
            'pid_saturated_perc': float(saturated_perc),
            'pid_outage_flag': bool(outage_flag),
            'pid_P': float(P),
            'pid_I': float(0.0 if outage_flag else self.integral),
            'pid_D': float(D),
            'pid_outdoor_term': float(outdoor_term),
            'pid_tentative_out': float(tentative_out),
            'pid_anti_windup_frozen': bool(anti_windup_frozen),
            'pid_raw_output': float(pid_output),
            'pid_Kp': float(self.Kp_outage if outage_flag else self.Kp),
            'pid_Ki': float(0.0 if outage_flag else self.Ki),
            'pid_Kd': float(0.0 if outage_flag else self.Kd),
        }

        return pid_output
