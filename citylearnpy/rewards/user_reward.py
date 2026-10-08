"""CHESCA / local_evaluation 使用的默认奖励（与 CHESCA-copy/rewards/user_reward 一致）。"""

from citylearn.reward_function import SolarPenaltyAndComfortReward


###################################################################
#####                Specify your reward here                 #####
###################################################################

SubmissionReward = SolarPenaltyAndComfortReward
