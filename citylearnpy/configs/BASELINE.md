# CHESCA 基线冻结说明（阶段 0–3）

## 基线配置

文件：[`chesca_baseline_v1.json`](./chesca_baseline_v1.json)

| 项 | 值 | 说明 |
|----|-----|------|
| `resmarl_enabled` | **false** | ResMARL 关闭 |
| `residual_alpha` | **0.0** | 残差强度为 0 |
| `resmarl_policy_path` | **null** | 无策略权重 |

## 阶段 3：可解释 + 消融 + 看板

### Decision Trace

- CSV / JSON 导出 `residual_base_*` / `residual_delta_*` / `residual_final_*`
- 启用 ResMARL 时时间线增加 **阶段 6**
- 推演表展示 ELE：`base + Δ → final` 与 α

### 消融批量评估

```bash
cd citylearnpy
# 冒烟（24 步 × 三组）
python ablation_resmarl.py --smoke --policy checkpoints/resmarl_policy_smoke.pt

# 完整 720 步
python ablation_resmarl.py --policy checkpoints/resmarl_policy.pt --alpha 0.15 --steps 720
```

三组对照：

| 名称 | 含义 |
|------|------|
| `chesca_baseline` | 纯 CHESCA |
| `resmarl_alpha0` | 启用残差层但 α=0（恒等） |
| `resmarl_full` | 完整 ResMARL |

结果：`ablation_results/` 下各子目录 + `ablation_summary.csv`

配置模板：[`configs/ablation/`](./ablation/)

### 看板残差参数 ↔ KPI

- 任务目录写入 `chesca_agent_config.json` 快照
- 仪表盘详情返回 `resmarlSummary`（label / enabled / α）
- KPI 对比与分组 Tab 标注「纯 CHESCA / ResMARL α=…」

## 回归测试

```bash
cd citylearnpy
python tests/test_residual_phase0.py
python tests/test_residual_phase1.py
python tests/test_residual_phase2.py
python tests/test_residual_phase3.py
```

## 下一阶段（阶段 4，可选）

- MAPPO 分布式残差

## α 扫描看板（阶段 5）

批量扫描并入库：

```bash
cd citylearnpy
python ablation_resmarl.py --alpha-sweep 0,0.05,0.1,0.15,0.2 --policy checkpoints/resmarl_policy.pt --steps 720
```

已有三组消融结果入库：

```bash
python ablation_resmarl.py --register-existing ablation_results
```

产物：

- `ablation_results/alpha_sweep_<id>/alpha_sweep_summary.json`
- `ablation_results/registry/index.json`（看板列表）

前端菜单 **α–KPI 扫描** 读取上述 registry，绘制 α–KPI 曲线（虚线 = 纯 CHESCA 基线）。
