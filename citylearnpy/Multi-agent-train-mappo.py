# CHESCA-ResMARL · MAPPO 集中 critic（CTDE）训练入口（2026-10-11 新增）
#
# 【与 Multi-agent-train.py / Multi-agent-train-residual.py 的关系】
#   本文件是**独立新增**的训练入口，不替换、不改动任何现有文件：
#   · 默认（不带 --algorithm mappo）与 Multi-agent-train.py 行为一致（走 SAC）；
#   · 带 --algorithm mappo 时，把算法换成集中 critic 的 PPO（mappo_cc.py）：
#         actor 分散（每栋一个策略，obs 只看自己）✓
#         critic 集中（训练期看其它楼 obs+动作算 value）✓
#   · 动作语义、奖励、checkpoint 目录、中期评估口径全部沿用现有 utils 管线。
#
# 【零侵入铁律】
#   - 不 import mappo_cc 时，本文件与 Multi-agent-train.py 逐字等价；
#   - 只在 `--algorithm mappo` 分支里就地 import mappo_cc + ray.rllib.ppo。
#
# 【已知未接线项（本文件刻意不动）】
#   - 评估侧仍是 Multi-agent-eval.py 加载 RLlib checkpoint；PPO checkpoint 的
#     目录标记与 SAC 一致（rllib_checkpoint.json 等）⇒ 理论兼容，但 PPO 加载路径
#     `PPO.from_checkpoint` 需实测验证（见 §收尾说明）。
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

from utils.base import log_console, TORCH_THREADS
from utils.env import _AGENT_ENV_CLS, build_env_config
from utils.train import save_multi_agent_checkpoint, install_action_hook, log_reward_banner
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
from custom_comfort_reward import check_reward_equivalence as _reward_equiv_check


def _extract_vf_explained_var(result):
    """从 RLlib 旧 API 栈的 result 里取 vf_explained_var（多策略聚合键带 `_mean` 后缀）。

    取不到时返回 None（调用方显示 n/a）。**刻意不用 float('nan') 兜底**——否则会把
    "根本没有这个键" 误报成 "监控量为 nan"，掩盖真实原因。也兼容
    `info.learner.<pid>.learner_stats.vf_explained_var` 这一路径。
    """
    try:
        cm = result.get('custom_metrics') or {}
        if 'vf_explained_var_mean' in cm:
            return float(cm['vf_explained_var_mean'])
        for _pid, d in (result.get('info', {}) or {}).get('learner', {}).items():
            _ls = (d or {}).get('learner_stats') or {}
            if 'vf_explained_var' in _ls:
                return float(_ls['vf_explained_var'])
    except Exception:
        pass
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description='MARL 训练入口（默认 SAC；--algorithm mappo 时用集中 critic 的 PPO）。'
    )
    parser.add_argument('--output-dir', '-o', type=str, default=None)
    parser.add_argument('--train-schema', type=str, default=DEFAULT_TRAIN_SCHEMA)
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA)
    parser.add_argument('--train-epochs', type=int, default=None)
    parser.add_argument('--min-train-epochs', type=int, default=None)
    parser.add_argument('--no-checkpoint', action='store_true')
    parser.add_argument('--no-best-ckpt', action='store_true')
    parser.add_argument('--checkpoint-dir', type=str, default=None)
    parser.add_argument('--check-reward', action='store_true')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    # 奖励权重覆盖（与 Multi-agent-train.py 一致）
    parser.add_argument('--bat-weight', type=float, default=None)
    parser.add_argument('--cost-weight', type=float, default=None)
    parser.add_argument('--p4-hinge-w', type=float, default=None)
    parser.add_argument('--p4-hinge-target', type=float, default=None)
    parser.add_argument('--bat-loss', type=float, default=None)
    # 本文件新增：算法选择 + MAPPO 超参
    parser.add_argument('--algorithm', type=str, default='sac',
                        choices=['sac', 'mappo', 'ippo'],
                        help='sac（默认，独立 SAC）/ mappo（PPO + 集中 critic）'
                             ' / ippo（PPO + 分散 critic，MAPPO 的对照基线）')
    parser.add_argument('--mappo-gamma', type=float, default=0.99)
    parser.add_argument('--mappo-lambda', type=float, default=0.95)
    parser.add_argument('--mappo-lr', type=float, default=5e-4)
    parser.add_argument('--mappo-clip-param', type=float, default=0.2)
    parser.add_argument('--mappo-entropy-coeff', type=float, default=0.01)
    parser.add_argument('--mappo-vf-loss-coeff', type=float, default=0.5)
    parser.add_argument('--mappo-kl-coeff', type=float, default=0.2)
    # ---- CHESCA 在环（残差）训练：与 Multi-agent-train-residual.py 同名同义 ----
    parser.add_argument('--chesca-in-loop', action='store_true',
                        help='开启「CHESCA 在环」残差训练：动作 = a_base + α·span·(mask⊙a_rl)'
                             '（→ 安全投影 → clip）。默认关 ⇒ 行为与不带该开关时逐字一致。')
    parser.add_argument('--residual-alpha', type=float, default=0.3,
                        help='残差强度 α（默认 0.3）。α=0 ⇒ 逐位等于纯 CHESCA（对照）')
    parser.add_argument('--residual-span', type=float, default=1.0, help='残差物理尺度（默认 1.0）')
    parser.add_argument('--residual-mode', type=str, default='additive',
                        choices=['additive', 'blend'], help='additive（默认，有恒等点）/ blend（A/B 对照）')
    parser.add_argument('--residual-mask', type=str, default='{"dhw":false,"ele":true,"tmp":false}',
                        help='逐维掩码 JSON（默认只开 ELE，与部署一致）')
    parser.add_argument('--safety-projection-enabled', type=str, default='true')
    parser.add_argument('--safety-projection-params', type=str, default=None)
    parser.add_argument('--residual-gate-enabled', type=str, default='true')
    parser.add_argument('--residual-gate-outage', type=str, default='true')
    parser.add_argument('--residual-gate-soc-bound', type=str, default='true')
    parser.add_argument('--residual-gate-soc-margin', type=float, default=0.02)
    parser.add_argument('--residual-log-every', type=int, default=0)
    parser.add_argument('--actor-prior-mode', type=str, default='own_obs',
                        choices=['own_obs', '+a_ch', '+neighbors',
                                 '+a_ch_dhw', '+a_ch_ele', '+a_ch_tmp'],
                        help=('actor 观测中先验注入形式（v3 §十.1 #4/#9 ablation）。'
                              'own_obs = 仅原生 obs + 父类追加 [capacity/identity/a_ref]（默认，与旧行为逐位一致）;'
                              '+a_ch = 额外拼入本栋 a_ch (3 维);'
                              '+neighbors = 额外拼入所有楼的 a_ch (3·n_b 维);'
                              '+a_ch_dhw/+a_ch_ele/+a_ch_tmp = 只拼本栋 a_ch 的某一维（#9 维度级）'))
    parser.add_argument('--chesca-agent-params', type=str, default=None,
                        help='镜像 CHESCA（产生 a_base）的 agent 参数 JSON。默认 None = raw CHESCA；'
                             '传 soft(5,6) 参数组 ⇒ 残差叠在部署配置之上（底座口径见 _ablation_alpha.py）。')
    parser.add_argument('--dump-residual-config', type=str, default=None)
    return parser.parse_args()


def _truthy(value) -> bool:
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y', 't')


if __name__ == '__main__':
    install_action_hook()
    args = parse_args()

    if args.check_reward:
        _worst = _reward_equiv_check(CUSTOM_REWARD_KWARGS, verbose=True)
        sys.exit(0 if _worst == 0.0 else 1)

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    train_schema = (args.train_schema or '').strip() or DEFAULT_TRAIN_SCHEMA
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    train_steps = None
    eval_steps = None
    train_epochs = int(args.train_epochs or TRAIN_EPOCHS)
    min_train_epochs = int(args.min_train_epochs or MIN_TRAIN_EPOCHS)
    if min_train_epochs > train_epochs:
        min_train_epochs = train_epochs
    seed = int(args.seed)

    # 奖励权重覆盖
    for _oname, _obox, _okey, _oshown in (
        ('bat-weight', CUSTOM_REWARD_KWARGS, 'bat_weight', 'bat_weight'),
        ('bat-loss', CUSTOM_REWARD_KWARGS, 'bat_loss_weight', 'bat_loss_weight'),
        ('cost-weight', CUSTOM_REWARD_KWARGS, 'cost_weight', 'cost_weight'),
        ('p4-hinge-w', P4_COST_HINGE, 'w', 'P4_COST_HINGE["w"]'),
        ('p4-hinge-target', P4_COST_HINGE, 'target', '目标线'),
    ):
        _oval = getattr(args, _oname.replace('-', '_'), None)
        if _oval is not None:
            _obox[_okey] = float(_oval)
            log_console(f'[奖励] --{_oname} 覆盖：{_oshown}={float(_oval):g}')

    train_env_config = build_env_config(
        train_schema, train_steps, output_dir, enable_render=False, record_details=False
    )

    # ---- CHESCA 在环：动作语义换成「CHESCA 基准 + α·残差」（默认关 ⇒ 行为不变）----
    _env_cls = _AGENT_ENV_CLS
    if getattr(args, 'chesca_in_loop', False):
        from chesca_residual_env import ChescaResidualEnv, ChescaResidualTrainConfig

        try:
            _mask = json.loads(args.residual_mask)
        except Exception as exc:
            raise SystemExit(f'--residual-mask 不是合法 JSON：{args.residual_mask!r}（{exc}）')
        try:
            _sp = json.loads(args.safety_projection_params) if args.safety_projection_params else {}
        except Exception as exc:
            raise SystemExit(f'--safety-projection-params 不是合法 JSON：{exc}')
        try:
            _ap = json.loads(args.chesca_agent_params) if args.chesca_agent_params else {}
        except Exception as exc:
            raise SystemExit(f'--chesca-agent-params 不是合法 JSON：{exc}')

        _r_cfg = ChescaResidualTrainConfig(
            enabled=True,
            alpha=float(args.residual_alpha),
            span=float(args.residual_span),
            residual_mode=str(args.residual_mode),
            action_mask={k: bool(v) for k, v in dict(_mask).items()},
            safety_projection_enabled=_truthy(args.safety_projection_enabled),
            safety_projection_params=dict(_sp),
            gate_enabled=_truthy(args.residual_gate_enabled),
            gate_on_outage=_truthy(args.residual_gate_outage),
            gate_on_soc_bound=_truthy(args.residual_gate_soc_bound),
            gate_soc_margin=float(args.residual_gate_soc_margin),
            schema=train_schema,
            episode_time_steps=train_steps,
            output_dir=str(output_dir),
            agent_params=dict(_ap),
            actor_prior_mode=str(args.actor_prior_mode),
            log_every=int(args.residual_log_every or 0),
        )
        train_env_config = dict(train_env_config)
        train_env_config['chesca_residual'] = _r_cfg.to_dict()
        _env_cls = ChescaResidualEnv
        log_console('=' * 72)
        log_console('[CHESCA 在环] 动作 = a_base + α·span·(mask⊙a_rl) → 安全投影 → clip')
        log_console(f'  α={_r_cfg.alpha}  span={_r_cfg.span}  mode={_r_cfg.residual_mode}  '
                    f'mask={json.dumps(_r_cfg.action_mask, ensure_ascii=False)}')
        log_console(f'  ★ actor_prior_mode={_r_cfg.actor_prior_mode}'
                    f'（v3 §十.1 #4 ablation：own_obs=旧行为, +a_ch=本栋 a_ch, +neighbors=全部楼 a_ch）')
        log_console('=' * 72)
        if args.dump_residual_config:
            _dump = Path(args.dump_residual_config)
            _dump.parent.mkdir(parents=True, exist_ok=True)
            _dump.write_text(json.dumps(_r_cfg.to_dict(), ensure_ascii=False, indent=2),
                             encoding='utf-8')
            log_console(f'已写出残差配置快照：{_dump.resolve()}')

    log_console(f'初始化 MARL（algorithm={args.algorithm}），导出目录: {output_dir.resolve()}')
    log_reward_banner(log_console)
    log_console(f'训练 schema={train_schema} steps={train_steps or "auto"}')
    log_console(f'训练规模: epochs={train_epochs} | batch={TRAIN_BATCH_SIZE} | seed={seed}')

    if args.algorithm == 'sac':
        # 走现有 SAC 管线（与 Multi-agent-train.py 完全一致）
        from utils.train import log_training_summary, restore_best_model, run_training
        if _env_cls is not _AGENT_ENV_CLS:
            # CHESCA 在环：把 utils.train 的环境类换成本进程的残差环境（只改模块属性，不动文件）
            import utils.train as _utrain
            _utrain._AGENT_ENV_CLS = _env_cls
        _rb_kwargs = {}
        if REPLAY_BUFFER_CAPACITY:
            _rb_kwargs['replay_buffer_config'] = {'capacity': int(REPLAY_BUFFER_CAPACITY)}
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
        ckpt_dir = _o.ckpt_dir
        model = _o.model
        ckpt = _o.ckpt
        _last_epoch = _o._last_epoch
        _mid_best = _o._mid_best
        _mid_eval_hist = _o._mid_eval_hist
        ckpt.save('训练结束', _last_epoch, _mid_best, _mid_eval_hist)
        log_training_summary(
            log=log_console, model=model, stopped_reason=_o._stopped_reason,
            last_epoch=_last_epoch, start_epoch=_o._start_epoch, train_epochs=train_epochs,
            train_secs=time.perf_counter() - _o._t_train0, sampled=_o._sampled_prev,
            mid_best=_mid_best, mid_prev_sums=_o._mid_prev_sums,
            mid_vote_stale=_o._mid_vote_stale, mid_best_sums=_o._mid_best_sums,
            mid_worsen=_o._mid_worsen, mid_conv=_o._mid_conv,
        )
        _best_model = restore_best_model(ckpt, last_epoch=_last_epoch, log=log_console)
        if _best_model is not None:
            model = _best_model
        _ckpt_saved = save_multi_agent_checkpoint(model, ckpt_dir, log_console=log_console)
    else:
        # ---- PPO 系列：MAPPO(集中 critic) / IPPO(分散 critic) ----------------
        import mappo_cc

        mappo_cc.register_mappo_model()

        from mappo_cc import CentralizedCriticPPO, build_mappo_config, build_ippo_config

        _centralized = (args.algorithm == 'mappo')
        _tag = 'MAPPO' if _centralized else 'IPPO'
        _builder = build_mappo_config if _centralized else build_ippo_config

        probe = _env_cls(train_env_config)
        agent_ids = list(probe._agent_ids)
        del probe

        config = _builder(
            env_cls=_env_cls,
            env_config=train_env_config,
            agent_ids=agent_ids,
            train_batch_size=TRAIN_BATCH_SIZE,
            rollout_fragment_length=ROLLOUT_FRAGMENT_LENGTH,
            num_rollout_workers=0,
            min_sample_timesteps_per_iteration=MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
            seed=seed,
            gamma=args.mappo_gamma,
            lambda_=args.mappo_lambda,
            lr=args.mappo_lr,
            clip_param=args.mappo_clip_param,
            entropy_coeff=args.mappo_entropy_coeff,
            vf_loss_coeff=args.mappo_vf_loss_coeff,
            kl_coeff=args.mappo_kl_coeff,
        )

        log_console('=' * 72)
        if _centralized:
            log_console('[MAPPO 集中 critic] actor 分散 + critic 集中（训练期看其它楼 obs+动作）')
        else:
            log_console('[IPPO 基线] actor 分散 + critic 分散（只看本楼 obs；MAPPO 的对照臂）')
        log_console(f'  gamma={args.mappo_gamma} lambda={args.mappo_lambda} lr={args.mappo_lr}')
        log_console(f'  clip={args.mappo_clip_param} entropy={args.mappo_entropy_coeff} '
                    f'vf_loss={args.mappo_vf_loss_coeff} kl={args.mappo_kl_coeff}')
        log_console('=' * 72)

        from utils.config import DEFAULT_CHECKPOINT_DIR
        if getattr(args, 'checkpoint_dir', None):
            ckpt_dir = Path(args.checkpoint_dir)
            if not ckpt_dir.is_absolute():
                ckpt_dir = Path(DEFAULT_CHECKPOINT_DIR).parent / ckpt_dir
        else:
            ckpt_dir = Path(DEFAULT_CHECKPOINT_DIR)

        if _centralized:
            model = CentralizedCriticPPO(config=config)
        else:
            from ray.rllib.algorithms.ppo import PPO as _PlainPPO

            model = _PlainPPO(config=config)

        _t0 = time.perf_counter()
        for epoch in range(1, train_epochs + 1):
            result = model.train()
            _r = result.get('episode_reward_mean', float('nan'))
            _ev = _extract_vf_explained_var(result)
            _ev_s = 'n/a' if _ev is None else f'{_ev:.4g}'
            log_console(
                f'[{_tag}] epoch {epoch}/{train_epochs} '
                f'episode_reward_mean={_r:.4g} '
                f'vf_explained_var={_ev_s} '
                f'({time.perf_counter() - _t0:.1f}s)'
            )
        _ckpt_saved = save_multi_agent_checkpoint(model, ckpt_dir, log_console=log_console)

    log_console('')
    log_console(f'CHECKPOINT={_ckpt_saved}')
    log_console(
        f'训练完成（本脚本只训练，不出 KPI）。要看 KPI 请运行：'
        f'python Multi-agent-eval.py --checkpoint "{_ckpt_saved}" '
        f'--eval-schema {eval_schema} --output-dir {output_dir}'
    )
    log_console('⚠️ 提示：PPO/MAPPO/IPPO 的评估加载路径已实测可用（Algorithm.from_checkpoint）。')
    sys.stdout.flush()
    sys.exit(0)
