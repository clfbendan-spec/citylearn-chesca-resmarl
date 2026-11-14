package com.citylearn.building;

import java.util.*;

/** Executable choices supported by external, measured thermal-demand datasets. */
public final class BuildingExportOptions {
    public static final List<String> STORAGE=List.of("electrical_storage","cooling_storage","heating_storage","dhw_storage");
    public final String profile, reward;
    public final List<String> actions;
    private BuildingExportOptions(String profile,String reward,List<String> actions) {this.profile=profile;this.reward=reward;this.actions=actions;}
    public static BuildingExportOptions parse(Object value,Map<String,Object> definition) {
        if(value!=null && !(value instanceof Map)) throw new IllegalArgumentException("仿真配置必须为对象");
        Map<?,?> input=value==null?Map.of():(Map<?,?>)value;
        if(!Set.of("profile","reward","actions").containsAll(input.keySet())) throw new IllegalArgumentException("不支持的仿真配置项");
        String profile=Objects.toString(input.get("profile"),"battery"),reward=Objects.toString(input.get("reward"),"energy");
        if(!List.of("battery","storage").contains(profile)) throw new IllegalArgumentException("请选择电池调度或多储能调度；外部测量不支持动态 HVAC 控制");
        if(!List.of("energy","cost","carbon").contains(reward)) throw new IllegalArgumentException("不支持的奖励目标");
        List<String> actions=new ArrayList<>();
        if(input.containsKey("actions")) {
            if(!(input.get("actions") instanceof List)) throw new IllegalArgumentException("控制设备选择无效");
            for(Object item:(List<?>)input.get("actions")) {
                String key=Objects.toString(item,"");
                if(!STORAGE.contains(key) || !definition.containsKey(key) || actions.contains(key) || profile.equals("battery") && !key.equals("electrical_storage"))
                    throw new IllegalArgumentException("控制设备不存在或不适用于所选场景: "+key);
                actions.add(key);
            }
        } else for(String key:STORAGE) if(definition.containsKey(key) && (profile.equals("storage") || key.equals("electrical_storage"))) actions.add(key);
        for(String key:actions) if(!key.equals("electrical_storage") && !definition.containsKey(key.replace("_storage","_device")))
            throw new IllegalArgumentException("启用热储能控制需要对应冷热/热水设备: "+key);
        return new BuildingExportOptions(profile,reward,List.copyOf(actions));
    }
    public Map<String,Object> asMap() {return Map.of("profile",profile,"reward",reward,"actions",actions,"thermalModel","exogenous","powerOutage",false);}
    public Map<String,Object> rewardDefinition() {
        return Map.of("type",reward.equals("energy")?"citylearn.reward_function.RewardFunction":"citylearn_external_rewards."+(reward.equals("cost")?"PurchaseCostReward":"PurchaseCarbonReward"),"attributes",Map.of());
    }
}
