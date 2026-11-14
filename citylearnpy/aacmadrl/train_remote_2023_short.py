import hashlib
import csv
import json
import random
import subprocess
import sys
import time
import os
from pathlib import Path

import numpy as np
import torch
from citylearn.citylearn import CityLearnEnv
from citylearn.reward_function import RewardFunction

DATA = Path(r'E:\citylearn-work\datasets\citylearn_challenge_2023_phase_2_local_evaluation')
EXPECTED = 'ebaf5a18299d759bd9a369680199d40c4451aa9c9af523cf4e97e31a374ab567'
CLASSES = dict(dhw_storage=21, electrical_storage=21, cooling_device=11,
               heating_device=11, cooling_or_heating_device=21)
SEED = 41
BETA = 0.0
EPISODES = 2
COMFORT_WEIGHT = 4.0
CONSUMPTION_WEIGHT = 1.0
REWARD_MODE = 'weighted_proxy'
DUAL_LR = 0.5
RELABEL_DUAL_REPLAY = False
BASELINE_COSTS = {
    'Building_1': 33.894485857206746,
    'Building_2': 19.82718759198906,
    'Building_3': 29.60129014123231,
}

# Platform subprocesses inherit the immutable task dataset and normalization.
if os.environ.get('AACMADRL_DATA'):
    DATA = Path(os.environ['AACMADRL_DATA'])
    EXPECTED = os.environ['AACMADRL_DATA_SHA256']
    BASELINE_COSTS = json.loads(os.environ['AACMADRL_BASELINE_COSTS'])


def relabel_dual_replay(agent, components, reward_function):
    """Recompute every stored scalar reward at current multipliers, preserving transitions."""
    counts = []
    for i, replay in enumerate(agent.replay_buffer):
        if len(components[i]) != len(replay.buffer):
            raise RuntimeError('Replay component/transition alignment failed')
        replacement = []
        for row, (cost, discomfort) in zip(replay.buffer, components[i]):
            raw = -10.0 * (reward_function.cost_multipliers[i] * cost +
                           reward_function.discomfort_multipliers[i] * discomfort)
            value = agent.get_normalized_reward(i, raw) if agent.normalized[i] else raw
            if not np.isfinite(value):
                raise ValueError('Non-finite relabeled reward')
            replacement.append((row[0], row[1], float(value), row[3], row[4]))
        replay.buffer = replacement
        counts.append(len(replacement))
    return counts


class KPIAlignedComfortCostReward(RewardFunction):
    version = 'official_kpi_aligned_v1'
    dual_version = 'official_kpi_dual_v1'

    def __init__(self, env_metadata, baseline_costs, occupied_counts,
                 cost_multipliers=None, discomfort_multipliers=None):
        super().__init__(env_metadata)
        self.baseline_costs = list(map(float, baseline_costs))
        self.occupied_counts = list(map(float, occupied_counts))
        if any(x <= 0 or not np.isfinite(x) for x in self.baseline_costs + self.occupied_counts):
            raise ValueError('KPI normalization denominators must be finite and positive')
        self.last_cost_components = np.zeros(len(self.baseline_costs), dtype=float)
        self.last_discomfort_components = np.zeros(len(self.baseline_costs), dtype=float)
        self.cost_multipliers = np.ones(len(self.baseline_costs), dtype=float) if cost_multipliers is None else np.asarray(cost_multipliers, dtype=float)
        self.discomfort_multipliers = np.ones(len(self.baseline_costs), dtype=float) if discomfort_multipliers is None else np.asarray(discomfort_multipliers, dtype=float)

    def set_multipliers(self, cost, discomfort):
        cost = np.asarray(cost, dtype=float)
        discomfort = np.asarray(discomfort, dtype=float)
        if cost.shape != self.cost_multipliers.shape or discomfort.shape != self.discomfort_multipliers.shape:
            raise ValueError('Dual multiplier dimensions changed')
        if not np.isfinite(cost).all() or not np.isfinite(discomfort).all() or (cost < 0).any() or (discomfort < 0).any():
            raise ValueError('Dual multipliers must be finite and non-negative')
        self.cost_multipliers = cost.copy()
        self.discomfort_multipliers = discomfort.copy()

    def reset(self):
        self.last_cost_components.fill(0.0)
        self.last_discomfort_components.fill(0.0)

    def calculate(self, observations):
        costs, discomforts = [], []
        for i, o in enumerate(observations):
            net = float(o['net_electricity_consumption'])
            price = float(o['electricity_pricing'])
            cost = max(net * price, 0.0) / self.baseline_costs[i] / 0.90
            occupied = float(o['occupant_count']) > 0.0
            temp = float(o['indoor_dry_bulb_temperature'])
            cold = temp < (float(o['indoor_dry_bulb_temperature_heating_set_point']) -
                           float(o['comfort_band']))
            hot = temp > (float(o['indoor_dry_bulb_temperature_cooling_set_point']) +
                          float(o['comfort_band']))
            discomfort = float(occupied and (cold or hot)) / self.occupied_counts[i] / 0.10
            costs.append(cost)
            discomforts.append(discomfort)
        self.last_cost_components = np.asarray(costs, dtype=float)
        self.last_discomfort_components = np.asarray(discomforts, dtype=float)
        rewards = (-10.0 * (self.cost_multipliers * self.last_cost_components +
                             self.discomfort_multipliers * self.last_discomfort_components)).tolist()
        return [sum(rewards)] if self.central_agent else rewards


def digest_data():
    h = hashlib.sha256()
    for p in sorted(x for x in DATA.rglob('*') if x.is_file()):
        h.update(p.relative_to(DATA).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def seed_training(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_env(start_time_step=0, end_time_step=719, seed=SEED):
    kpi_reward = REWARD_MODE in (
        KPIAlignedComfortCostReward.version, KPIAlignedComfortCostReward.dual_version)
    # The KPI reward needs building metadata, available after construction.
    # Its temporary bootstrap reward must not depend on an unused custom package.
    reward_kwargs = (
        {'reward_function': RewardFunction} if kpi_reward else
        {'reward_function': 'citylearn.custom_reward.ComfortConsumptionDistrictRewardFixed',
         'reward_function_kwargs': {'beta': BETA, 'gamma': 1.0}})
    env = CityLearnEnv(str(DATA / 'schema.json'), central_agent=False,
                       random_seed=seed,
                       simulation_start_time_step=start_time_step,
                       simulation_end_time_step=end_time_step,
                       **reward_kwargs)
    if not kpi_reward and COMFORT_WEIGHT != 1.0:
        from citylearn.custom_reward import ComfortConsumptionDistrictRewardFixed

        class WeightedComfortReward(ComfortConsumptionDistrictRewardFixed):
            def calculate(self, observations):
                nets = [float(o['net_electricity_consumption']) for o in observations]
                district = -(sum(nets) ** 2) / (len(nets) ** self.gamma)
                return [10 * ((1 - self.beta) *
                              (COMFORT_WEIGHT * self._comfort_term(o) +
                               CONSUMPTION_WEIGHT * min((-net) ** 3, 0.0))
                              + self.beta * district) for o, net in zip(observations, nets)]

        env.reward_function = WeightedComfortReward(env.metadata, beta=BETA, gamma=1.0)
    if kpi_reward:
        occupied_counts = [float((np.asarray(b.energy_simulation.occupant_count[
            start_time_step:end_time_step + 1], dtype=float) > 0).sum())
                           for b in env.buildings]
        env.reward_function = KPIAlignedComfortCostReward(
            env.get_metadata(),
            baseline_costs=[BASELINE_COSTS[b.name] for b in env.buildings],
            occupied_counts=occupied_counts)
    return env


def metric_rows(env):
    return env.evaluate().to_dict(orient='records')


def eval_checkpoint(checkpoint, stats_path, episode, eval_path, trajectory_path=None):
    from aac_madrl_safe_io import SafeIOAAC
    actual_hash = digest_data()
    if actual_hash != EXPECTED:
        raise ValueError('Dataset SHA-256 mismatch during evaluation: ' + actual_hash)
    env = make_env()
    agent = SafeIOAAC(env, classes=CLASSES, lr=1e-3, random_seed=SEED)
    agent.load_models(str(checkpoint))
    stats = json.loads(stats_path.read_text(encoding='utf-8'))
    agent.norm_mean = [np.asarray(x, dtype=float) for x in stats['norm_mean']]
    agent.norm_std = [np.asarray(x, dtype=float) for x in stats['norm_std']]
    agent.r_norm_mean = stats['r_norm_mean']
    agent.r_norm_std = stats['r_norm_std']
    agent.normalized = stats['normalized']
    obs, _ = env.reset()
    ended = truncated = False
    transitions = 0
    trajectory = []
    while not (ended or truncated):
        prior = []
        for building in env.buildings:
            t = building.time_step
            prior.append(dict(temperature=float(building.indoor_dry_bulb_temperature[t]),
                              cooling_setpoint=float(building.indoor_dry_bulb_temperature_cooling_set_point[t]),
                              heating_setpoint=float(building.indoor_dry_bulb_temperature_heating_set_point[t]),
                              comfort_band=float(building.comfort_band[t]),
                              occupant_count=float(building.energy_simulation.occupant_count[t]),
                              electricity_pricing=float(
                                  building.pricing.electricity_pricing[t]
                              ),
                              outage=float(building.power_outage),
                              hvac_mode=int(dict(zip(agent.observation_names[len(prior)],
                                                     obs[len(prior)])).get('hvac_mode', 0)),
                              net=float(building.net_electricity_consumption[t])))
        observation_rows = [
            dict(zip(agent.observation_names[i], map(float, obs[i])))
            for i in range(len(env.buildings))
        ]
        actions = agent.predict(obs, deterministic=True)
        obs, rewards, ended, truncated, info = env.step(actions)
        transitions += 1
        for i, building in enumerate(env.buildings):
            t = building.time_step
            current_observation = dict(zip(agent.observation_names[i], obs[i]))
            next_state = dict(
                temperature=float(building.indoor_dry_bulb_temperature[t]),
                cooling_setpoint=float(
                    building.indoor_dry_bulb_temperature_cooling_set_point[t]
                ),
                heating_setpoint=float(
                    building.indoor_dry_bulb_temperature_heating_set_point[t]
                ),
                comfort_band=float(building.comfort_band[t]),
                occupant_count=float(
                    building.energy_simulation.occupant_count[t]
                ),
                electricity_pricing=float(
                    building.pricing.electricity_pricing[t]
                ),
                outage=float(building.power_outage),
                net=float(building.net_electricity_consumption[t]),
                hvac_mode=int(current_observation.get('hvac_mode', 0)),
            )
            trajectory.append(dict(step=transitions, building=building.name,
                                   time_step=int(t),
                                   observation=json.dumps(
                                       observation_rows[i], sort_keys=True
                                   ),
                                   next_observation=json.dumps(
                                       dict(zip(agent.observation_names[i],
                                                map(float, obs[i]))),
                                       sort_keys=True),
                                   state_before=json.dumps(prior[i], sort_keys=True),
                                   state_after=json.dumps(next_state, sort_keys=True),
                                   actions=json.dumps({k: float(v) for k, v in
                                                       zip(agent.action_names[i], actions[i])}),
                                   reward=float(rewards[i]),
                                   terminated=bool(ended),
                                   truncated=bool(truncated),
                                   environment_info=json.dumps(
                                       info, sort_keys=True, default=str
                                   )))
    rows = metric_rows(env)
    by_building = {name: {r['cost_function']: r['value'] for r in rows
                          if r['name'] == name and r['level'] == 'building'}
                   for name in sorted({r['name'] for r in rows if r['level'] == 'building'})}
    result = dict(episode=episode, transitions=transitions, dataset_sha256=actual_hash,
                  optimizer_updates=stats['optimizer_updates'],
                  official_kpi=rows, per_building=by_building,
                  terminal_soc={b.name: float(b.electrical_storage.soc[b.time_step]) for b in env.buildings},
                  all_buildings_meet_targets=all(
                      k.get('discomfort_proportion', 1.0) < .10 and k.get('cost_total', 1.0) < .90
                      for k in by_building.values()))
    eval_path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    if trajectory_path is not None:
        trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        with trajectory_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(trajectory[0]))
            writer.writeheader(); writer.writerows(trajectory)
    env.close()
    return result


def isolated_evaluate(out, checkpoint, agent, episode):
    stats_path = out / f'eval_stats_{episode:02d}.json'
    eval_path = out / f'eval_episode_{episode:02d}.json'
    trajectory_path = out / f'eval_trajectory_episode_{episode:02d}.csv'
    stats_path.write_text(json.dumps(dict(
        norm_mean=[np.asarray(x).tolist() for x in agent.norm_mean],
        norm_std=[np.asarray(x).tolist() for x in agent.norm_std],
        r_norm_mean=agent.r_norm_mean, r_norm_std=agent.r_norm_std,
        normalized=agent.normalized, optimizer_updates=agent.niter),
        allow_nan=False), encoding='utf-8')
    subprocess.run([sys.executable, str(Path(__file__).resolve()), '--evaluate',
                    '--checkpoint', str(checkpoint), '--stats', str(stats_path),
                    '--episode', str(episode), '--eval-output', str(eval_path),
                    '--trajectory-output', str(trajectory_path),
                    '--comfort-weight', str(COMFORT_WEIGHT),
                    '--consumption-weight', str(CONSUMPTION_WEIGHT),
                    '--reward-mode', str(REWARD_MODE), '--dual-lr', str(DUAL_LR)],
                   check=True, env={**__import__('os').environ, 'OMP_NUM_THREADS': '1'})
    return json.loads(eval_path.read_text(encoding='utf-8'))


def main():
    import argparse
    global COMFORT_WEIGHT, CONSUMPTION_WEIGHT, EPISODES, REWARD_MODE, DUAL_LR, RELABEL_DUAL_REPLAY
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--stats', type=Path)
    parser.add_argument('--episode', type=int, default=0)
    parser.add_argument('--eval-output', type=Path)
    parser.add_argument('--comfort-weight', type=float, default=4.0)
    parser.add_argument('--consumption-weight', type=float, default=1.0)
    parser.add_argument('--reward-mode', choices=['weighted_proxy', KPIAlignedComfortCostReward.version,
                                                   KPIAlignedComfortCostReward.dual_version],
                        default='weighted_proxy')
    parser.add_argument('--dual-lr', type=float, default=0.5)
    parser.add_argument('--relabel-dual-replay', action='store_true')
    parser.add_argument('--trajectory-output', type=Path)
    parser.add_argument('--episodes', type=int, default=EPISODES)
    args = parser.parse_args()
    COMFORT_WEIGHT = args.comfort_weight
    CONSUMPTION_WEIGHT = args.consumption_weight
    EPISODES = args.episodes
    REWARD_MODE = args.reward_mode
    DUAL_LR = args.dual_lr
    RELABEL_DUAL_REPLAY = args.relabel_dual_replay
    if RELABEL_DUAL_REPLAY and REWARD_MODE != KPIAlignedComfortCostReward.dual_version:
        parser.error('--relabel-dual-replay requires dual reward mode')
    if EPISODES < 1:
        parser.error('--episodes must be positive')
    if args.evaluate:
        if not all((args.checkpoint, args.stats, args.eval_output)):
            parser.error('--evaluate requires --checkpoint, --stats, and --eval-output')
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        eval_checkpoint(args.checkpoint, args.stats, args.episode, args.eval_output,
                        args.trajectory_output)
        return
    if args.output is None:
        parser.error('--output is required for training')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    actual_hash = digest_data()
    if actual_hash != EXPECTED:
        raise ValueError('Dataset SHA-256 mismatch: ' + actual_hash)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    train_env = make_env()
    from aac_madrl_safe_io import SafeIOAAC

    agent = SafeIOAAC(train_env, classes=CLASSES, lr=1e-3, random_seed=SEED)
    agent.norm_mean = [np.zeros(agent.observation_dimension[i]) for i in range(agent.nagents)]
    agent.norm_std = [np.ones(agent.observation_dimension[i]) for i in range(agent.nagents)]
    protocol = dict(dataset_sha256=actual_hash, seed=SEED, episode_seed_policy='SEED + episode - 1; reset(seed=SEED)',
                    action_space_seed_policy='each Box seeded with episode_seed + agent_index before exploration',
                    deterministic_torch=True, episodes=EPISODES,
                    state_window=[0, 719], transitions_per_episode=719,
                    beta=BETA, gamma=1.0, learning_rate=1e-3,
                    comfort_reward_weight=COMFORT_WEIGHT,
                    consumption_reward_weight=CONSUMPTION_WEIGHT,
                    reward_mode=REWARD_MODE,
                    reward_normalization=(dict(
                        target_cost_ratio=0.90, target_discomfort_proportion=0.10,
                        baseline_cost_by_building=BASELINE_COSTS,
                        occupied_timestep_count_by_building={
                            b.name: int((np.asarray(b.energy_simulation.occupant_count[:720], dtype=float) > 0).sum())
                            for b in train_env.buildings})
                        if REWARD_MODE in (KPIAlignedComfortCostReward.version,
                                           KPIAlignedComfortCostReward.dual_version) else None),
                    dual_update=(dict(rule='lambda=max(0.05,min(20,lambda+dual_lr*(official_kpi-target)))',
                                      learning_rate=DUAL_LR, initial_cost=[1.0]*agent.nagents,
                                      initial_discomfort=[1.0]*agent.nagents)
                                 if REWARD_MODE == KPIAlignedComfortCostReward.dual_version else None),
                    dual_replay_relabel=RELABEL_DUAL_REPLAY,
                    dual_reward_normalization='fixed initial statistics; all replay rewards recomputed after lambda change' if RELABEL_DUAL_REPLAY else 'stored scalar rewards',
                    reward_formula=('reward_i=-10*(lambda_cost_i*max(net_i*price_i,0)/(baseline_cost_i*0.90) + '
                                    'lambda_discomfort_i*official_occupied_discomfort_i/(occupied_count_i*0.10))'
                                    if REWARD_MODE == KPIAlignedComfortCostReward.dual_version else
                                    'reward_i=-10*(max(net_i*price_i,0)/(baseline_cost_i*0.90) + '
                                    'official_occupied_discomfort_i/(occupied_count_i*0.10)'
                                    if REWARD_MODE == KPIAlignedComfortCostReward.version else
                                    '10*((1-beta)*(comfort_weight*comfort_i + consumption_weight*min((-net_i)^3,0)) + beta*(-sum(net)^2/N^gamma))'),
                    batch_size=agent.batch_size, updates_per_step=agent.update_per_time_step,
                    learning_starts=agent.standardize_start_time_step,
                    expected_optimizer_updates_cumulative=[2 + 1438 * i for i in range(EPISODES)],
                    evaluation='separate process; model and normalization statistics loaded from checkpoint',
                    target={'per_building_discomfort_proportion_lt': .10,
                            'per_building_cost_total_lt': .90},
                    note='Fixed local development trajectory; no online data or test-set selection.')
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    initial_checkpoint = out / 'initial.zip'
    agent.save_models(str(initial_checkpoint))
    evaluations = [isolated_evaluate(out, initial_checkpoint, agent, 0)]
    replay_components = [[] for _ in range(agent.nagents)]
    started = time.time()
    for episode in range(1, EPISODES + 1):
        episode_seed = SEED + episode - 1
        obs, _ = train_env.reset(seed=SEED)
        seed_training(episode_seed)
        for i, action_space in enumerate(agent.action_space):
            action_space.seed(episode_seed + i)
        done = truncated = False
        steps = 0
        reward_sum = np.zeros(agent.nagents, dtype=float)
        cost_component_sum = np.zeros(agent.nagents, dtype=float)
        discomfort_component_sum = np.zeros(agent.nagents, dtype=float)
        cost_lambda_before = train_env.reward_function.cost_multipliers.tolist() if REWARD_MODE in (
            KPIAlignedComfortCostReward.version, KPIAlignedComfortCostReward.dual_version) else None
        discomfort_lambda_before = train_env.reward_function.discomfort_multipliers.tolist() if REWARD_MODE in (
            KPIAlignedComfortCostReward.version, KPIAlignedComfortCostReward.dual_version) else None
        rollout_digest = hashlib.sha256()
        while not (done or truncated):
            actions = agent.predict(obs, deterministic=False)
            nxt, rewards, done, truncated, _ = train_env.step(actions)
            if not np.isfinite(rewards).all():
                raise ValueError('Non-finite training reward')
            rollout_digest.update(np.asarray(actions, dtype='<f4').tobytes())
            rollout_digest.update(np.asarray(rewards, dtype='<f8').tobytes())
            if RELABEL_DUAL_REPLAY:
                for i, replay in enumerate(agent.replay_buffer):
                    pair = (float(train_env.reward_function.last_cost_components[i]),
                            float(train_env.reward_function.last_discomfort_components[i]))
                    if len(replay_components[i]) < replay.capacity:
                        replay_components[i].append(pair)
                    else:
                        replay_components[i][replay.position] = pair
            agent.update(obs, actions, rewards, nxt, done, truncated)
            if REWARD_MODE in (KPIAlignedComfortCostReward.version, KPIAlignedComfortCostReward.dual_version):
                cost_component_sum += train_env.reward_function.last_cost_components
                discomfort_component_sum += train_env.reward_function.last_discomfort_components
            obs = nxt; reward_sum += rewards; steps += 1
            if steps % 60 == 0:
                print(json.dumps(dict(state='training', episode=episode, step=steps,
                                      updates=agent.niter, elapsed_s=time.time()-started)), flush=True)
        checkpoint = out / f'episode_{episode:02d}.zip'
        agent.save_models(str(checkpoint))
        training_state_before_eval = (agent.time_step, agent.niter)
        evaluation = isolated_evaluate(out, checkpoint, agent, episode)
        if (agent.time_step, agent.niter) != training_state_before_eval:
            raise RuntimeError('Isolated evaluation mutated training-agent state')
        expected_updates = protocol['expected_optimizer_updates_cumulative'][episode - 1]
        if agent.niter != expected_updates:
            raise RuntimeError(f'Unexpected cumulative optimizer updates: {agent.niter}; expected {expected_updates}')
        relabeled_counts = None
        if REWARD_MODE == KPIAlignedComfortCostReward.dual_version:
            next_cost_lambda, next_discomfort_lambda = [], []
            for building in train_env.buildings:
                kpi = evaluation['per_building'][building.name]
                next_cost_lambda.append(float(np.clip(
                    train_env.reward_function.cost_multipliers[len(next_cost_lambda)] +
                    DUAL_LR * (kpi['cost_total'] - 0.90), 0.05, 20.0)))
                next_discomfort_lambda.append(float(np.clip(
                    train_env.reward_function.discomfort_multipliers[len(next_discomfort_lambda)] +
                    DUAL_LR * (kpi['discomfort_proportion'] - 0.10), 0.05, 20.0)))
            train_env.reward_function.set_multipliers(next_cost_lambda, next_discomfort_lambda)
            if RELABEL_DUAL_REPLAY:
                relabeled_counts = relabel_dual_replay(agent, replay_components, train_env.reward_function)
        evaluations.append(evaluation)
        summary = dict(episode=episode, transitions=steps, optimizer_updates=agent.niter,
                       episode_seed=episode_seed,
                       training_rollout_sha256=rollout_digest.hexdigest(),
                       reward_sum_per_building=reward_sum.tolist(),
                       reward_cost_component_sum=cost_component_sum.tolist(),
                       reward_discomfort_component_sum=discomfort_component_sum.tolist(),
                       replay_rewards_relabeled=relabeled_counts,
                       cost_lambda_before=cost_lambda_before,
                       discomfort_lambda_before=discomfort_lambda_before,
                       cost_lambda_for_next_episode=(train_env.reward_function.cost_multipliers.tolist()
                           if REWARD_MODE == KPIAlignedComfortCostReward.dual_version else None),
                       discomfort_lambda_for_next_episode=(train_env.reward_function.discomfort_multipliers.tolist()
                           if REWARD_MODE == KPIAlignedComfortCostReward.dual_version else None),
                       checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                       per_building=evaluation['per_building'],
                       target_met=evaluation['all_buildings_meet_targets'])
        with (out / 'experience.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(summary, allow_nan=False) + '\n')
        print(json.dumps(dict(state='episode_evaluated', **summary)), flush=True)
        if evaluation['all_buildings_meet_targets']:
            break
    train_env.close()
    result = dict(state='completed', elapsed_s=time.time()-started,
                  dataset_sha256=actual_hash, protocol=protocol,
                  final_updates=agent.niter, evaluations=evaluations,
                  experience= 'See experience.jsonl; each episode evaluated on the full 720-state 2023 local trajectory.')
    (out / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(state='completed', result=str(out/'result.json'),
                          final_updates=agent.niter,
                          target_met=evaluations[-1]['all_buildings_meet_targets']), indent=2), flush=True)


if __name__ == '__main__':
    main()
