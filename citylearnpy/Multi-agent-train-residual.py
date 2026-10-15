# CHESCA-在环 Multi-Agent SAC 残差训练入口（路线 A，2026-10-10 新增）
#
# 【与 Multi-agent-train.py 的关系】
#   本文件是 Multi-agent-train.py 的**独立副本**，只加不改：
#   · 原文件、utils/train.py、utils/env.py、Multi-agent*.py 一个字都没动 ✓
#   · 默认行为（不带 --chesca-in-loop）与 Multi-agent-train.py 完全一致 ✓
#   · 带 --chesca-in-loop 时，训练环境的动作语义变为
#         a_final = clip(a_base + α·span·(mask⊙a_rl)·gate) → 安全投影 → clip
#     由 chesca_residual_env.ChescaResidualEnv 实现（不改任何现有文件 ✓）
#
# 【为什么不是"包装 RLlib 环境"】
#   见 chesca_residual_env.py 文件头（action_safety_projection.py:283-296 的弃用说明）。
#
# 【已知未接线项（本文件刻意不动）】
#   1) 中期评估 / best-ckpt 选择仍走 utils.env 的 _AGENT_ENV_CLS（纯策略口径）
#      ⇒ 选出的 checkpoint 与部署口径不一致（配置单 §第 0 层"目标口径错位"）。
#      本文件只在启动时打印警告，不改 utils/train.py。
#   2) 评估侧仍是"加载同一份 RLlib checkpoint"，无需改动 ✓（checkpoint 格式不变 ✓）。
import argparse
import json
import os
import sys
import time
from pathlib import Path

# 算子不大，设置单线程启动，避免多线程抢锁
_THREADS = str(max(1, int(os.environ.get('TORCH_NUM_THREADS', '1') or '1')))
os.environ.setdefault('OMP_NUM_THREADS', _THREADS)
os.environ.setdefault('MKL_NUM_THREADS', _THREADS)
os.environ.setdefault('NUMEXPR_NUM_THREADS', _THREADS)

# 执行时会把本脚本复制到 output/outkpis/{taskId}/ 再执行
sys.path[:0] = [str(Path(p).resolve()) for p in (os.environ.get('CITYLEARNPY_DIR'), r'D:\citylearn-demo\citylearnpy') if p and Path(p).is_dir()][:1]

# 日志工具，设置torch单线程
from utils.base import log_console, TORCH_THREADS

# 构建环境配置，动作解析
from utils.env import _AGENT_ENV_CLS, build_env_config

# 中期评估,checkpoint,动作注入钩子
from utils.train import save_multi_agent_checkpoint, install_action_hook, log_reward_banner

# 自定义奖励函数相关配置，用于记录决策推演日志
from utils.config import (
    CUSTOM_REWARD_KWARGS,
    DEFAULT_EVAL_SCHEMA,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TRAIN_SCHEMA,
    TRAIN_EPOCHS,
    TRAIN_BATCH_SIZE,
    ROLLOUT_FRAGMENT_LENGTH,
    MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
    DEFAULT_SEED,
    MIN_TRAIN_EPOCHS,
    CKPT_DIR,
    P4_COST_HINGE,
    REPLAY_BUFFER_CAPACITY,
)

# 奖励函数自检
from custom_comfort_reward import check_reward_equivalence as _reward_equiv_check


# 外部入参
def parse_args():
    parser = argparse.ArgumentParser(
        description='CHESCA-在环 SAC 残差训练：a_final = clip(a_base + α·span·(mask⊙a_rl)) → 安全投影 → clip。'
                    '默认（不带 --chesca-in-loop）与 Multi-agent-train.py 行为一致。'
    )
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='把 KPI 与仿真数据导出到这个目录（Java 平台会传入任务目录）')
    parser.add_argument('--train-schema', type=str, default=DEFAULT_TRAIN_SCHEMA,
                        help=f'训练数据集（默认 {DEFAULT_TRAIN_SCHEMA}）')
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA,
                        help=f'评估用数据集：CityLearn 数据目录名（默认 {DEFAULT_EVAL_SCHEMA}）')
    parser.add_argument('--train-epochs', type=int, default=None,
                        help=(f'训练轮数（硬上限；Java 注入走这个），默认 {TRAIN_EPOCHS}'
                              f'（每轮采样 ≈ {MIN_SAMPLE_TIMESTEPS_PER_ITERATION} env-step；'
                              f'训练 batch={TRAIN_BATCH_SIZE}）'))
    parser.add_argument('--min-train-epochs', type=int, default=None,
                        help=(f'最小训练轮数：在此之前一律继续训练（早停判据②不生效），'
                              f'默认 {MIN_TRAIN_EPOCHS}'))
    parser.add_argument('--no-checkpoint', action='store_true',
                        help='关闭训练中的 checkpoint 保存（默认开启，每 CKPT_EVERY 轮一次）')
    parser.add_argument('--no-best-ckpt', action='store_true',
                        help=('P2-D：关闭「训练期最优快照用于最终评估」'
                              f'（默认开启：中期评估创新低即存 best 快照，评估用 best 权重；'
                              f'关闭后退回用末次权重）'))
    parser.add_argument('--checkpoint-dir', type=str, default=None,
                        help=f'checkpoint 目录，默认 {CKPT_DIR}（相对本脚本所在目录）')
    parser.add_argument('--check-reward', action='store_true',
                        help='自检开关：对比自定义奖励与数据集原版奖励是否逐位一致，打印结果后直接退出')
    parser.add_argument('--bat-weight', type=float, default=None,
                        help=('电池"择时"项（低买高卖）权重：越大利诱电池低价充电、高价放电。'
                              '默认 = CUSTOM_REWARD_KWARGS 的 50。'))
    parser.add_argument('--cost-weight', type=float, default=None,
                        help=('电费项权重覆盖：r_cost=−w×price×max(0,net)。'
                              '默认 = CUSTOM_REWARD_KWARGS 的 0（关闭）。'))
    parser.add_argument('--p4-hinge-w', type=float, default=None,
                        help='P-13：best-ckpt 选择指标的成本 hinge 权重（默认 0）。')
    parser.add_argument('--p4-hinge-target', type=float, default=None,
                        help='P-13：hinge 目标线覆盖（默认 0.93）。')
    parser.add_argument('--bat-loss', type=float, default=None,
                        help=('电池"损耗/账单"项权重：r_loss = −w×price×(充电−有效放电)。'
                              '默认 = CUSTOM_REWARD_KWARGS 的 12。'))
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help=f'固定 RLlib/ray 随机种子，默认 {DEFAULT_SEED}；论文方差跑 3 次：--seed 0/1/2')
    # ------------------------------------------------------------------
    # 本文件新增：CHESCA 在环（残差）训练
    # ------------------------------------------------------------------
    parser.add_argument('--chesca-in-loop', action='store_true',
                        help='开启「CHESCA 在环」残差训练：动作 = a_base + α·span·(mask⊙a_rl)（→ 安全投影 → clip）')
    parser.add_argument('--residual-alpha', type=float, default=0.3,
                        help='残差强度 α（默认 0.3）。α=0 ⇒ 逐位等于纯 CHESCA（可用于对照）')
    parser.add_argument('--residual-span', type=float, default=1.0,
                        help='残差物理尺度（与 α 解耦；默认 1.0）')
    parser.add_argument('--residual-mode', type=str, default='additive',
                        choices=['additive', 'blend'],
                        help='additive（默认，有恒等点 ✓）/ blend（旧行为，仅 A/B 对照）')
    parser.add_argument('--residual-mask', type=str, default='{"dhw":false,"ele":true,"tmp":false}',
                        help='逐维掩码 JSON（默认只开 ELE，与当前部署一致）')
    parser.add_argument('--safety-projection-enabled', type=str, default='true',
                        help='true/false：残差合成后是否施加温控/停电硬投影（默认 true）')
    parser.add_argument('--safety-projection-params', type=str, default=None,
                        help='JSON：覆盖 SafetyProjectionConfig 字段（如 {"outage_cooling_floor":0.0}）')
    parser.add_argument('--residual-gate-enabled', type=str, default='true',
                        help='true/false：P0 门控总开关（默认 true）')
    parser.add_argument('--residual-gate-outage', type=str, default='true',
                        help='true/false：停电期关掉该栋残差（默认 true）')
    parser.add_argument('--residual-gate-soc-bound', type=str, default='true',
                        help='true/false：SOC 触界时关掉该栋残差（默认 true）')
    parser.add_argument('--residual-gate-soc-margin', type=float, default=0.02,
                        help='SOC 触界余量（0~1，默认 0.02）')
    parser.add_argument('--residual-log-every', type=int, default=0,
                        help='环境侧每 N 步打印一次残差诊断（0 = 不打印）')
    parser.add_argument('--actor-prior-mode', type=str, default='own_obs',
                        choices=['own_obs', '+a_ch', '+neighbors',
                                 '+a_ch_dhw', '+a_ch_ele', '+a_ch_tmp'],
                        help=('actor 观测中先验注入形式（v3 §十.1 #4/#9 ablation）。'
                              'own_obs = 仅原生 obs + 父类追加 [capacity/identity/a_ref]（默认，与旧行为逐位一致）;'
                              '+a_ch = 额外拼入本栋 a_ch (3 维);'
                              '+neighbors = 额外拼入所有楼的 a_ch (3·n_b 维);'
                              '+a_ch_dhw/+a_ch_ele/+a_ch_tmp = 只拼本栋 a_ch 的某一维（#9 维度级）'))
    parser.add_argument('--dump-residual-config', type=str, default=None,
                        help='把生效的残差配置 JSON 写到该路径（便于复现）')
    return parser.parse_args()


def _truthy(value) -> bool:
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y', 't')


if __name__ == '__main__':
    # 流程：① 装钩子 → ② 解析参数 → ③ 奖励自检(可选) → ④ 定目录/数据集/轮数 → ⑤ 覆盖权重(可选)
    #       → ⑥ 建环境（可选：换成 CHESCA 在环环境）→ ⑦ 跑训练 → ⑧ 取回产出 → ⑨ 收尾汇总 → ⑩ 存 checkpoint

    # 让环境每一步都把动作记下来
    install_action_hook()

    # 解析命令行参数
    args = parse_args()

    # 奖励自检开关
    if args.check_reward:
        _worst = _reward_equiv_check(CUSTOM_REWARD_KWARGS, verbose=True)
        sys.exit(0 if _worst == 0.0 else 1)

    # 确定输出目录
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定数据集
    train_schema = (args.train_schema or '').strip() or DEFAULT_TRAIN_SCHEMA
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    train_steps = None
    eval_steps = None
    # 训练轮数
    train_epochs = int(args.train_epochs or TRAIN_EPOCHS)
    min_train_epochs = int(
        getattr(args, 'min_train_epochs', None)
        if getattr(args, 'min_train_epochs', None) is not None else MIN_TRAIN_EPOCHS
    )
    if min_train_epochs > train_epochs:
        log_console(
            f'[轮数] 最小训练轮数 {min_train_epochs} > 最大 {train_epochs} → 自动收敛为 {min_train_epochs}'
        )
        train_epochs = min_train_epochs
    min_train_epochs = max(1, min(min_train_epochs, train_epochs))
    # 随机种子
    seed = int(getattr(args, 'seed', None) if getattr(args, 'seed', None) is not None else DEFAULT_SEED)
    # 根据入参覆盖奖励中的部分参数
    for _oname, _obox, _okey, _oshown, _owhy in (
        ('bat-weight', CUSTOM_REWARD_KWARGS, 'bat_weight', 'bat_weight', '电池择时项'),
        ('bat-loss', CUSTOM_REWARD_KWARGS, 'bat_loss_weight', 'bat_loss_weight', '电池损耗项'),
        ('cost-weight', CUSTOM_REWARD_KWARGS, 'cost_weight', 'cost_weight',
         '电费项 price×max(0,net)，含电池'),
        ('p4-hinge-w', P4_COST_HINGE, 'w', 'P4_COST_HINGE["w"]', None),
        ('p4-hinge-target', P4_COST_HINGE, 'target', '目标线',
         'B2 ≈ 1.07~1.09 × 目标线 ⇒ 0.90 对应 B2 ≈ 0.96~0.98'),
    ):
        _oval = getattr(args, _oname.replace('-', '_'), None)
        if _oval is None:
            continue
        _obox[_okey] = float(_oval)
        _otag = '[P-13]' if _oname.startswith('p4-hinge') else '[奖励]'
        _oextra = _owhy or f'目标线 {P4_COST_HINGE.get("target"):g}'
        log_console(f'{_otag} --{_oname} 覆盖：{_oshown}={float(_oval):g}（{_oextra}）')

    # 建训练环境
    train_env_config = build_env_config(
        train_schema, train_steps, output_dir, enable_render=False, record_details=False
    )

    # ---- CHESCA 在环：把动作语义换成"基准 + 残差" ----------------------------
    _env_cls = _AGENT_ENV_CLS
    if args.chesca_in_loop:
        from chesca_residual_env import ChescaResidualEnv, ChescaResidualTrainConfig

        try:
            mask = json.loads(args.residual_mask)
        except Exception as exc:
            raise SystemExit(f'--residual-mask 不是合法 JSON：{args.residual_mask!r}（{exc}）')
        try:
            sp_params = json.loads(args.safety_projection_params) if args.safety_projection_params else {}
        except Exception as exc:
            raise SystemExit(f'--safety-projection-params 不是合法 JSON：{exc}')

        r_cfg = ChescaResidualTrainConfig(
            enabled=True,
            alpha=float(args.residual_alpha),
            span=float(args.residual_span),
            residual_mode=str(args.residual_mode),
            action_mask={k: bool(v) for k, v in dict(mask).items()},
            safety_projection_enabled=_truthy(args.safety_projection_enabled),
            safety_projection_params=dict(sp_params),
            gate_enabled=_truthy(args.residual_gate_enabled),
            gate_on_outage=_truthy(args.residual_gate_outage),
            gate_on_soc_bound=_truthy(args.residual_gate_soc_bound),
            gate_soc_margin=float(args.residual_gate_soc_margin),
            schema=train_schema,
            episode_time_steps=train_steps,
            output_dir=str(output_dir),
            actor_prior_mode=str(args.actor_prior_mode),
            log_every=int(args.residual_log_every or 0),
        )
        train_env_config = dict(train_env_config)
        train_env_config['chesca_residual'] = r_cfg.to_dict()
        _env_cls = ChescaResidualEnv

        # 把 utils.train 里的环境类换成残差环境（只改本进程的模块属性，不动文件 ✓）
        import utils.train as _utrain
        _utrain._AGENT_ENV_CLS = ChescaResidualEnv

        log_console('=' * 72)
        log_console('[CHESCA 在环] 动作语义 = a_base + α·span·(mask⊙a_rl) → 安全投影 → clip')
        log_console(f'  α={r_cfg.alpha}  span={r_cfg.span}  mode={r_cfg.residual_mode}')
        log_console(f'  mask={json.dumps(r_cfg.action_mask, ensure_ascii=False)}')
        log_console(f'  safety_projection={r_cfg.safety_projection_enabled} '
                    f'params={json.dumps(r_cfg.safety_projection_params, ensure_ascii=False)}')
        log_console(f'  gate: enabled={r_cfg.gate_enabled} outage={r_cfg.gate_on_outage} '
                    f'soc_bound={r_cfg.gate_on_soc_bound} margin={r_cfg.gate_soc_margin}')
        log_console(f'  镜像 schema={r_cfg.schema} steps={r_cfg.episode_time_steps or "auto"}')
        log_console(f'  ★ actor_prior_mode={r_cfg.actor_prior_mode}'
                    f'（v3 §十.1 #4 ablation：own_obs=旧行为, +a_ch=本栋 a_ch, +neighbors=全部楼 a_ch）')
        log_console('  ⚠️ 中期评估/best-ckpt 仍是纯策略口径（utils/train.py 未改动）')
        log_console('=' * 72)
        if args.dump_residual_config:
            _dump = Path(args.dump_residual_config)
            _dump.parent.mkdir(parents=True, exist_ok=True)
            _dump.write_text(json.dumps(r_cfg.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
            log_console(f'已写出残差配置快照：{_dump.resolve()}')

    log_console(f'初始化 SAC 多智能体，导出目录: {output_dir.resolve()}')
    log_reward_banner(log_console)   # 奖励口径 + 动作重标定总览（实现在 utils/train.py ✓）
    log_console(f'训练 schema={train_schema} steps={train_steps or "auto(数据集自带)"}')
    log_console(f'训练中中期评估/探针 schema={eval_schema} steps={eval_steps or "auto(数据集自带)"}')
    log_console(
        f'训练规模: epochs={train_epochs}（最小 {min_train_epochs}：在此之前不停）'
        f' | 每轮: 采样 fragment={ROLLOUT_FRAGMENT_LENGTH}（auto≈100，单进程采样）'
        f' | 训练 batch={TRAIN_BATCH_SIZE}（agent-steps，×楼栋数才是 agent-step）'
        f' | seed={seed}'
    )
    log_console(
        f'计算线程: torch={TORCH_THREADS}（TORCH_NUM_THREADS='
        f'{os.environ.get("TORCH_NUM_THREADS") or "未设→1"}；OMP='
        f'{os.environ.get("OMP_NUM_THREADS")}）'
        f' | 该 learner 是框架开销主导，线程数不是提速手段'
    )

    # 经验池容量
    _rb_kwargs = {}
    if REPLAY_BUFFER_CAPACITY:
        _rb_kwargs['replay_buffer_config'] = {'capacity': int(REPLAY_BUFFER_CAPACITY)}

    probe = _env_cls(train_env_config)
    # 训练主循环
    from utils.train import log_training_summary, restore_best_model, run_training
    _o = run_training(
        log=log_console,
        _rb_kwargs=_rb_kwargs,
        args=args,
        eval_schema=eval_schema,
        min_train_epochs=min_train_epochs,
        output_dir=output_dir,
        seed=seed,
        train_env_config=train_env_config,
        train_epochs=train_epochs,
    )

    # 取回参数
    _last_epoch = _o._last_epoch
    _mid_best = _o._mid_best
    _mid_eval_hist = _o._mid_eval_hist
    ckpt = _o.ckpt
    ckpt_dir = _o.ckpt_dir
    model = _o.model
    _train_secs = time.perf_counter() - _o._t_train0
    # 训练结束
    ckpt.save('训练结束', _last_epoch, _mid_best, _mid_eval_hist)
    # 打印收尾
    log_training_summary(
        log=log_console, model=model, stopped_reason=_o._stopped_reason,
        last_epoch=_last_epoch, start_epoch=_o._start_epoch, train_epochs=train_epochs,
        train_secs=_train_secs, sampled=_o._sampled_prev,
        mid_best=_mid_best, mid_prev_sums=_o._mid_prev_sums, mid_vote_stale=_o._mid_vote_stale,
        mid_best_sums=_o._mid_best_sums, mid_worsen=_o._mid_worsen, mid_conv=_o._mid_conv,
    )
    # 用训练期最优快照替换 model
    _best_model = restore_best_model(ckpt, last_epoch=_last_epoch, log=log_console)
    if _best_model is not None:
        model = _best_model

    # 保存checkpoint
    _ckpt_saved = save_multi_agent_checkpoint(model, ckpt_dir, log_console=log_console)
    log_console('')
    log_console(f'CHECKPOINT={_ckpt_saved}')
    log_console(
        f'训练完成（本脚本只训练，不出 KPI）。要看 KPI 请运行：'
        f'python Multi-agent-eval.py --checkpoint "{_ckpt_saved}" '
        f'--eval-schema {eval_schema} --output-dir {output_dir}'
    )
    log_console(
        '提示：Java 平台可把配置页的「multi_agent_checkpoint」设为上面的绝对路径，'
        '之后评估任务即会跳过训练直接复用该模型。'
    )
    sys.stdout.flush()
    sys.exit(0)
