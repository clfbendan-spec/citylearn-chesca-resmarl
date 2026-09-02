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
        """ Returns the actions for the current time step """
        error = setpoint_value - cur_value

        if saturated_perc < 0.04:  # Update:
            self.updated_integral = self.integral
            self.updated_prev_error = self.prev_error
        else:  # there is saturation, reduce the integral and derivative terms proportionally
            self.integral = self.integral * (1.0 - saturated_perc)
            self.prev_error = self.prev_error * (1.0 - saturated_perc)

            self.updated_integral = self.integral
            self.updated_prev_error = self.prev_error

        if not outage_flag:  # Normal operation
            # 输出将为负（不制冷）且误差仍使积分更负时，停止继续 windup
            tentative_i = self.updated_integral + self.Ki * error * self.dt
            P = self.Kp * error
            D = self.Kd * (error - self.updated_prev_error) / self.dt
            tentative_out = P + tentative_i + D
            if tentative_out < 0.0 and (self.Ki * error * self.dt) < 0.0:
                # 保持积分，不再向更负方向累积
                self.integral = self._clamp_integral(self.updated_integral)
            else:
                self.integral = self._clamp_integral(tentative_i)
            self.prev_error = error
            pid_output = P + self.integral + D
        else:  # During outage
            P = self.Kp_outage * error
            pid_output = P + self.OutTempScaler * (outdoor_temp - cur_value)

        return pid_output
