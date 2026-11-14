"""Trusted rewards bundled with published external-measurement datasets."""
from citylearn.reward_function import RewardFunction


class PurchaseCostReward(RewardFunction):
    def calculate(self, observations):
        values = [-max(row['net_electricity_consumption'], 0.0) * row['electricity_pricing'] for row in observations]
        return [sum(values)] if self.central_agent else values


class PurchaseCarbonReward(RewardFunction):
    def calculate(self, observations):
        values = [-max(row['net_electricity_consumption'], 0.0) * row['carbon_intensity'] for row in observations]
        return [sum(values)] if self.central_agent else values
