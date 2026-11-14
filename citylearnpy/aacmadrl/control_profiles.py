"""Explicit historical controller settings shared by collection and evaluation."""
HISTORICAL_PROFILE = 'bcf3e3cbcd9023b7'


def configure_profile(args):
    if args.control_profile == 'none':
        return
    if args.control_profile != HISTORICAL_PROFILE:
        raise ValueError('Unknown AAC control profile')
    # Preserve the inherited cooling head while training the storage policy.
    values = dict(
        freeze_cooling_policy=True,
        unoccupied_cooling_gate=True,
        unoccupied_cooling_gate_bins=2,
        unoccupied_cooling_gate_training_building_index=None,
        unoccupied_cooling_gate_training_min_unoccupied_steps=5,
        unoccupied_cooling_gate_training_comfort_margin=1.5,
        unoccupied_cooling_gate_training_second_bin_comfort_margin=1.5,
        unoccupied_cooling_gate_training_max_demand=2.,
        unoccupied_cooling_gate_override='on',
        unoccupied_cooling_gate_building_index=None,
        unoccupied_cooling_gate_min_unoccupied_steps=5,
        unoccupied_cooling_gate_comfort_margin=1.5,
        unoccupied_cooling_gate_second_bin_comfort_margin=1.5,
        unoccupied_cooling_gate_price_threshold=.02915,
        unoccupied_cooling_gate_bins_override=2,
        unoccupied_cooling_gate_max_demand_override=2.,
        high_price_charge_gate=False,
        high_price_charge_gate_override='off',
        high_price_discharge_rule_override='on',
        high_price_discharge_threshold_override=.05867,
        high_price_discharge_reserve_soc_override=.3,
        high_price_discharge_action_override=-.048787880688905716,
        high_price_discharge_building_index=1,
        high_price_discharge_post_soc_floor_override=.3,
        predicted_price_discharge_gate_override='off',
        predicted_price_charge_rule_training=True,
        predicted_price_charge_training_max_current_price=.03025,
        predicted_price_charge_training_min_spread=.005,
        predicted_price_charge_training_max_soc=.3,
        predicted_price_charge_training_building_index=None,
        predicted_price_charge_training_action=None,
        predicted_price_charge_rule_override='on',
        predicted_price_charge_max_current_price_override=.03025,
        predicted_price_charge_min_spread_override=.005,
        predicted_price_charge_max_soc_override=.3,
        predicted_price_charge_building_index=None,
        predicted_price_charge_action_override=None,
    )
    for key, value in values.items():
        setattr(args, key, value)
