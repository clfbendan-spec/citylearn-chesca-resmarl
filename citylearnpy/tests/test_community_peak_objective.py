import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from community_peak_objective import CommunityPeakObjective, PeakObjectiveConfig


def score(powers):
    objective=CommunityPeakObjective()
    return sum(objective.update(p)['total'] for p in powers)


class PeakObjectiveTests(unittest.TestCase):
    def test_peak_terms_telescope(self):
        self.assertEqual(score([5,8,6]),-8.)
        self.assertEqual(score([2,8,8]),-8.)

    def test_lower_final_peak_is_better(self):
        self.assertGreater(score([6,7,6]),score([5,8,6]))

    def test_charge_that_creates_peak_is_penalized(self):
        self.assertLess(score([9,7]),score([5,8]))

    def test_early_discharge_without_final_peak_gain_is_not_rewarded(self):
        self.assertEqual(score([4,8]),score([5,8]))

    def test_comfort_and_terminal_cannot_be_free(self):
        plain=CommunityPeakObjective().update(8)['total']
        penalized=CommunityPeakObjective().update(8,occupied_violations=1,terminal_shortfall=.2)['total']
        self.assertEqual(penalized,plain-3.)

    def test_more_throughput_has_a_cost(self):
        self.assertLess(CommunityPeakObjective().update(8,throughput=2)['total'],CommunityPeakObjective().update(8)['total'])

    def test_new_episode_resets_peak(self):
        one=CommunityPeakObjective();one.update(9)
        self.assertEqual(CommunityPeakObjective().update(5)['peak'],-5.)

    def test_invalid_penalties_rejected(self):
        with self.assertRaises(ValueError):PeakObjectiveConfig(comfort_weight=-1)
        with self.assertRaises(ValueError):CommunityPeakObjective().update(5,terminal_shortfall=-1)


if __name__=='__main__':unittest.main()
