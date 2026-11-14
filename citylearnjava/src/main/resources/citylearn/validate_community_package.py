import contextlib
import io
import importlib
import json
from pathlib import Path
import sys


def main():
    directory = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(directory))
    with contextlib.redirect_stdout(io.StringIO()):
        import numpy as np
        from citylearn.citylearn import CityLearnEnv
        env = CityLearnEnv(str(directory / "schema.json"))
        try:
            env.reset()
            steps = 0
            for _ in range(min(24, env.time_steps - 1)):
                observation, reward, terminated, truncated, _ = env.step(
                    [np.zeros(space.shape).tolist() for space in env.action_space]
                )
                if not all(np.isfinite(np.asarray(row)).all() for row in observation):
                    raise ValueError("CityLearn returned nonfinite observations")
                if not np.isfinite(reward).all():
                    raise ValueError("CityLearn returned nonfinite rewards")
                steps += 1
                if terminated or truncated:
                    break
            result = {
                "observationDimensions": [len(space.low) for space in env.observation_space],
                "actionDimensions": [len(space.low) for space in env.action_space],
                "verifiedSteps": steps,
                "buildingClasses": [type(building).__name__ for building in env.buildings],
            }
            declaration = env.schema.get("agent")
            if declaration:
                module, name = declaration["type"].rsplit(".", 1)
                try:
                    available = hasattr(importlib.import_module(module), name)
                except ImportError:
                    available = False
                result["defaultAgentAvailable"] = available
                if not available:
                    result["warnings"] = ["当前CityLearn未提供默认算法类 " + declaration["type"] + "，训练任务需显式选择可用算法；数据与场景配置已保留。"]
        finally:
            env.close()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
