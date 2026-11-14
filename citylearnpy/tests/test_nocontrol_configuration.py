"""Validate the actual entrypoint parser without starting a simulation."""
import argparse
import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class NoControlConfigurationTest(unittest.TestCase):
    def parse(self, *arguments):
        source = Path(__file__).resolve().parents[1] / 'NOCONTROL.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_args')
        ns = dict(argparse=argparse, DEFAULT_OUTPUT_DIR=Path('unused'))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), ns)
        with patch.object(sys, 'argv', ['NOCONTROL.py', *arguments]):
            return ns['parse_args']()

    def test_explicit_dataset_window_and_seed_are_accepted(self):
        args = self.parse('--eval-schema', 'custom/schema.json', '--simulation-start-time-step', '10',
                          '--simulation-end-time-step', '33', '--seed', '42')
        self.assertEqual(args.schema, 'custom/schema.json')
        self.assertEqual((args.simulation_start_time_step, args.simulation_end_time_step), (10, 33))
        self.assertEqual(args.seed, 42)

    def test_default_window_uses_dataset_full_length(self):
        args = self.parse()
        self.assertEqual(args.schema, 'citylearn_challenge_2023_phase_2_online_evaluation_1')
        self.assertIsNone(args.simulation_start_time_step)
        self.assertIsNone(args.simulation_end_time_step)

    def test_reversed_negative_and_single_state_windows_are_rejected(self):
        for start, end in ((-1, 10), (10, 9), (10, 10)):
            with self.subTest(start=start, end=end), self.assertRaises(SystemExit):
                self.parse('--simulation-start-time-step', str(start), '--simulation-end-time-step', str(end))


if __name__ == '__main__':
    unittest.main()
