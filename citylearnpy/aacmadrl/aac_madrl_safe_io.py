"""Versioned input/action adapter. Upstream networks and losses are unchanged."""
import json
import zipfile

import numpy as np
import torch
from citylearn.agents.aac_madrl import AAC_MADRL
from citylearn.preprocessing import PeriodicNormalization, OnehotEncoding


class SafeIOAAC(AAC_MADRL):
    adapter_version = 'safe_io_v1'
    continuous_std_floor = 0.05  # encoded continuous feature units, fixed before pilot

    def __init__(self, env, **kwargs):
        super().__init__(env, **kwargs)
        self.action_grids = []
        self.fixed_encoding_masks = []
        for i, names in enumerate(self.action_names):
            assert [k for k in self.classes if k in names] == names, 'Action head order mismatch'
            grids = []
            for j, name in enumerate(names):
                low, high = float(self.action_space[i].low[j]), float(self.action_space[i].high[j])
                count = self.classes[name]
                assert low < high and count >= 3
                if low < 0 < high:
                    left = (count-1)//2
                    grid = np.r_[np.linspace(low, 0, left+1), np.linspace(0, high, count-left)[1:]]
                else:
                    grid = np.linspace(low, high, count)
                assert len(grid) == count and np.all(np.diff(grid) > 0)
                grids.append(grid)
            self.action_grids.append(grids)
            mask=[]
            for j, (name, encoder) in enumerate(zip(self.observation_names[i], self.encoders[i])):
                # Calendar periods are semantic constants, not the maximum seen in June.
                if name == 'month':
                    encoder.x_max = 12.0
                elif name == 'hour':
                    encoder.x_max = 24.0
                sample = np.asarray(encoder * float(self.observation_space[i].low[j]))
                mask.extend([isinstance(encoder, (PeriodicNormalization, OnehotEncoding))]*sample.size)
            self.fixed_encoding_masks.append(np.asarray(mask, dtype=bool))

    def discretize_actions(self, acs, agent=None):
        if agent is None:
            return [self.discretize_actions([a], agent=i)[0] for i, a in enumerate(acs)]
        rows = np.atleast_2d(acs)
        assert rows.shape[1] == len(self.action_grids[agent])
        return [[np.eye(len(grid))[int(np.abs(grid-value).argmin())]
                 for grid, value in zip(self.action_grids[agent], row)] for row in rows]

    def make_continuous(self, acs, defined_actions=None):
        return [[float(grid[int(np.argmax(a.detach().cpu().numpy() if torch.is_tensor(a) else a))])
                 for grid, a in zip(self.action_grids[i], agent_actions)]
                for i, agent_actions in enumerate(acs)]

    def update_buffer(self, observations, actions, reward, next_observations, done):
        for i, (o, a, r, n) in enumerate(zip(observations, actions, reward, next_observations)):
            o = self.get_encoded_observations(i, o)
            n = self.get_encoded_observations(i, n)
            if self.normalized[i]:
                o = self.get_normalized_observations(i, o)
                n = self.get_normalized_observations(i, n)
                r = self.get_normalized_reward(i, r)
            self.replay_buffer[i].push(o, a, r, n, done)
            if self.time_step >= self.standardize_start_time_step and self.batch_size <= len(self.replay_buffer[i]) and not self.normalized[i]:
                x = np.asarray([row[0] for row in self.replay_buffer[i].buffer], dtype=float)
                rewards = np.asarray([row[2] for row in self.replay_buffer[i].buffer], dtype=float)
                self.norm_mean[i] = np.mean(x, axis=0)
                self.norm_std[i] = np.maximum(np.std(x, axis=0), self.continuous_std_floor)
                self.norm_mean[i][self.fixed_encoding_masks[i]] = 0.0
                self.norm_std[i][self.fixed_encoding_masks[i]] = 1.0
                self.r_norm_mean[i] = float(np.mean(rewards))
                self.r_norm_std[i] = float(np.std(rewards)/self.reward_scaling+1e-5)
                self.replay_buffer[i].buffer = [(
                    self.get_normalized_observations(i, prev), act,
                    self.get_normalized_reward(i, rew),
                    self.get_normalized_observations(i, nxt), terminal)
                    for prev, act, rew, nxt, terminal in self.replay_buffer[i].buffer]
                self.normalized[i] = True

    def adapter_config(self):
        return dict(version=self.adapter_version, continuous_std_floor=self.continuous_std_floor,
                    calendar_periods={'month': 12, 'hour': 24},
                    action_names=self.action_names,
                    action_grids=[[g.tolist() for g in grids] for grids in self.action_grids])

    def save_models(self, zip_path='safe_io.zip', dtype=None):
        result = super().save_models(zip_path=zip_path, dtype=dtype)
        with zipfile.ZipFile(zip_path, 'a') as archive:
            archive.writestr('safe_io_adapter.json', json.dumps(self.adapter_config(), indent=2))
        return result

    def load_models(self, zip_path, **kwargs):
        with zipfile.ZipFile(zip_path) as archive:
            if 'safe_io_adapter.json' not in archive.namelist():
                raise ValueError('Legacy checkpoint rejected: retrain with the safe IO adapter')
            if json.loads(archive.read('safe_io_adapter.json')) != self.adapter_config():
                raise ValueError('Adapter or action grid mismatch')
        return super().load_models(zip_path, **kwargs)
