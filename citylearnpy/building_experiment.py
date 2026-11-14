"""Single-building battery experiments on frozen ingestion datasets."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys


def split_ranges(length, fraction):
    split = int(length * fraction)
    if not 0.5 <= fraction <= 0.9 or split < 2 or length - split < 2:
        raise ValueError("Need at least two training and two evaluation hours")
    return (0, split - 1), (split, length - 1)


def verify_dataset(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("files"):
        raise ValueError("Dataset manifest has no file hashes")
    for name, expected in manifest["files"].items():
        file = (directory / name).resolve()
        if file.parent != directory:
            raise ValueError("Invalid dataset hash path")
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("Dataset hash mismatch: " + name)
    return manifest


def write_json(file, content):
    temporary = file.with_suffix(".tmp")
    temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(file)


def slice_dataset(source, target, start, end):
    """Physically isolate folds so observation-space bounds cannot see future samples."""
    target.mkdir(parents=True, exist_ok=False)
    schema = json.loads((source / "schema.json").read_text(encoding="utf-8"))
    for file in source.glob("*.csv"):
        with file.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        with (target / file.name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows[start:end + 1])
    schema["simulation_start_time_step"] = 0
    schema["simulation_end_time_step"] = end - start
    schema["root_directory"] = str(target)
    for name in ("citylearn_ingested_devices.py", "citylearn_external_rewards.py"):
        module = source / name
        if module.is_file():
            shutil.copy2(module, target / module.name)
    write_json(target / "schema.json", schema)
    return target / "schema.json"


def make_env(schema_file, seed):
    module_root = str(Path(schema_file).resolve().parent)
    if module_root not in sys.path:
        sys.path.insert(0, module_root)
    import gymnasium as gym
    import numpy as np
    from citylearn.citylearn import CityLearnEnv

    class BatteryEnv(gym.Env):
        def __init__(self):
            self.base = CityLearnEnv(str(schema_file), central_agent=True, random_seed=seed)
            names = self.base.observation_names[0]
            # Fixed physical scaling, independent of either fold's empirical statistics.
            scales = {"month": 12, "hour": 24, "day_type": 7, "carbon_intensity": 2,
                      "electricity_pricing": 10, "electrical_storage_soc": 1}
            self.scales = np.array([scales.get(n, 50 if "temperature" in n else
                                               1000 if "solar" in n else 100) for n in names], dtype=np.float32)
            self.observation_space = gym.spaces.Box(-1, 1, (len(names),), np.float32)
            self.action_space = self.base.action_space[0]
            self.trace = []

        def observation(self, values):
            values = np.asarray(values[0], dtype=np.float32)
            if not np.isfinite(values).all():
                raise ValueError("Nonfinite CityLearn observations")
            return np.tanh(values / self.scales)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.trace = []
            values, info = self.base.reset(seed=seed)
            return self.observation(values), info

        def step(self, action):
            index = self.base.time_step
            values, reward, terminated, truncated, info = self.base.step([action.tolist()])
            b = self.base.buildings[0]
            net = float(b.net_electricity_consumption[index])
            price = float(b.pricing.electricity_pricing[index])
            carbon = float(b.carbon_intensity.carbon_intensity[index])
            soc = float(b.electrical_storage.soc[min(index, len(b.electrical_storage.soc) - 1)])
            self.trace.append({"step": index, "netKwh": net, "cost": max(net, 0) * price,
                               "carbonKg": max(net, 0) * carbon, "batterySoc": soc,
                               "action": float(action[0])})
            return self.observation(values), float(reward[0]), terminated, truncated, info

        def close(self):
            self.base.close()

    return BatteryEnv()


def evaluate(schema_file, seed, model=None):
    import numpy as np
    env = make_env(schema_file, seed)
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        action = np.zeros(env.action_space.shape, dtype=np.float32) if model is None else model.predict(obs, deterministic=True)[0]
        obs, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
    trace = env.trace
    net = [r["netKwh"] for r in trace]
    result = {"steps": len(trace), "importKwh": sum(max(v, 0) for v in net),
              "cost": sum(r["cost"] for r in trace), "carbonKg": sum(r["carbonKg"] for r in trace),
              "peakKw": max(net), "rampingKwh": sum(abs(b - a) for a, b in zip(net, net[1:])),
              "finalSoc": trace[-1]["batterySoc"],
              "terminalStoredKwh": trace[-1]["batterySoc"] * env.base.buildings[0].electrical_storage.capacity}
    env.close()
    return result, trace


def run(args):
    import platform
    import citylearn
    import stable_baselines3
    from stable_baselines3 import SAC
    from stable_baselines3.common.callbacks import BaseCallback
    source, output = Path(args.schema).resolve().parent, Path(args.output_dir).resolve()
    manifest = verify_dataset(source)
    if manifest.get("profile") != "battery-only-exogenous-thermal-demand":
        raise ValueError("Unsupported building profile")
    output.mkdir(parents=True, exist_ok=True)
    count = manifest["timeSteps"]
    model = None
    train_range = None
    if args.mode == "train":
        train_range, evaluation_range = split_ranges(count, args.fraction)
        training = slice_dataset(source, output / "train-data", *train_range)
        evaluation = slice_dataset(source, output / "evaluation-data", *evaluation_range)
        env = make_env(training, args.seed)

        class Progress(BaseCallback):
            def _on_step(self):
                if self.num_timesteps % 32 == 0 or self.num_timesteps == args.steps:
                    write_json(output / "progress.json", {"steps": self.num_timesteps, "total": args.steps})
                return True

        model = SAC("MlpPolicy", env, seed=args.seed, device="cpu", verbose=0,
                    learning_starts=min(100, max(1, args.steps // 4)), buffer_size=50000,
                    batch_size=64, policy_kwargs={"net_arch": [64, 64]})
        model.learn(total_timesteps=args.steps, callback=Progress())
        model.save(str(output / "model"))
        env.close()
    else:
        evaluation_range = (0, count - 1)
        evaluation = slice_dataset(source, output / "evaluation-data", *evaluation_range)
        if args.model:
            model = SAC.load(args.model, device="cpu")
    baseline, _ = evaluate(evaluation, args.seed)
    candidate, trace = evaluate(evaluation, args.seed, model)
    with (output / "trace.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(trace[0]))
        writer.writeheader()
        writer.writerows(trace)
    result = {"mode": args.mode, "seed": args.seed, "sourceVersion": manifest["version"],
              "contentHash": manifest["contentHash"], "trainRange": train_range,
              "evaluationRange": evaluation_range, "baseline": baseline, "candidate": candidate,
              "stepsRequested": args.steps if args.mode == "train" else 0,
              "versions": {"python": platform.python_version(), "citylearn": citylearn.__version__,
                           "stableBaselines3": stable_baselines3.__version__},
              "limitations": ["battery-only", manifest.get("deviceModel", "legacy equipment model"),
                              "exogenous thermal demand; no learned building thermal dynamics",
                              "no sale revenue", "no terminal SOC constraint",
                              "last CSV row is CityLearn's terminal observation"]}
    write_json(output / "result.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["train", "evaluation"], default="evaluation")
    parser.add_argument("--steps", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2023)
    parser.add_argument("--fraction", type=float, default=0.8)
    parser.add_argument("--model")
    parsed = parser.parse_args()
    if not 32 <= parsed.steps <= 1000000:
        parser.error("steps must be between 32 and 1000000")
    run(parsed)
