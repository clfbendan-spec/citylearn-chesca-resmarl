import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "building_experiment.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("building_experiment", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildingExperimentTest(unittest.TestCase):
    def test_time_split_has_no_train_evaluation_overlap(self):
        runner = load_runner()
        self.assertEqual(runner.split_ranges(100, 0.8), ((0, 79), (80, 99)))
        with self.assertRaises(ValueError):
            runner.split_ranges(3, 0.8)


    def test_rejects_tampered_dataset_before_training(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "schema.json").write_text('{"changed": true}')
            (directory / "manifest.json").write_text(json.dumps({"files": {"schema.json": "bad-hash"}}))
            with self.assertRaisesRegex(ValueError, "hash"):
                runner.verify_dataset(directory)


if __name__ == "__main__":
    unittest.main()
