"""
集中式 RBC（Rule-Based Control）基线仿真脚本。

使用 CityLearn 内置 BasicRBC 智能体，在 2023 phase 2 数据集上运行 720 步 episode，
开启 render 导出时序 CSV，供前端 UI 上传分析。

BasicRBC：基于规则的启发式控制器（非强化学习），作为 benchmark 对比 RL / CHESCA 等算法。
"""

from pathlib import Path

from citylearn.agents.rbc import BasicRBC as Agent
from citylearn.citylearn import CityLearnEnv

# BasicRBC 逻辑说明见：citylearnpy/agents/BasicRBC注释参考.py
# （库内源码：site-packages/citylearn/agents/rbc.py，继承 HourRBC，按 hour 查表输出动作）

# ---------------------------------------------------------------------------
# 1. 创建仿真环境
# ---------------------------------------------------------------------------
# schema：2023 挑战赛 phase 2 本地评估数据集（3 栋建筑 + 区域，720 步）
# central_agent=True：单智能体统一输出所有建筑动作
# episode_time_steps=720：与数据集默认仿真长度一致
# render_mode='during'：每步写入 exported_data_*.csv；episode 结束自动导出 exported_kpis.csv
# render_directory / render_session_name：输出到 outputs/ui_exports/<session>/
env = CityLearnEnv(
    'citylearn_challenge_2023_phase_2_local_evaluation',
    central_agent=True,
    episode_time_steps=720,
    render_mode='during',
    render_directory=Path('outputs/ui_exports'),
    render_session_name='my_first_run6',
)

# ---------------------------------------------------------------------------
# 2. 加载 RBC 智能体
# ---------------------------------------------------------------------------
# BasicRBC 根据观测（电价、SOC、负荷等）用固定规则生成动作，无需训练
model = Agent(env)

# ---------------------------------------------------------------------------
# 3. 仿真主循环
# ---------------------------------------------------------------------------
# reset：环境回到 t=0，返回初始观测与 info（CityLearn 2.5 为二元组）
observations, _ = env.reset()

# 逐步执行直至 episode 结束（env.terminated == True）
while not env.terminated:
    # RBC 根据当前观测预测动作（central_agent：[[dhw, battery, cooling, ...]]）
    actions = model.predict(observations)
    # 施加动作，环境前进 1 步；返回新观测、奖励、终止/截断标志、info
    observations, reward, terminated, truncated, info = env.step(actions)

# ---------------------------------------------------------------------------
# 4. 评估并打印 KPI
# ---------------------------------------------------------------------------
# evaluate：相对「无主动控制」基线归一化的 cost_function（<1 优于基线，>1 劣于基线）
kpis = model.env.evaluate()
# 转为宽表：行=指标名，列=Building_1 / Building_2 / Building_3 / District
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
# 去掉全 NaN 行
kpis = kpis.dropna(how='all')
print('outputkpi')
print(kpis)

# render 开启时打印导出目录（含 exported_kpis.csv 与 exported_data_*.csv）
if env.new_folder_path:
    print('输出目录:', Path(env.new_folder_path).resolve())
else:
    print('未生成导出目录（请确认 render_mode 已启用）')
