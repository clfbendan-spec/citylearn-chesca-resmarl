package com.citylearn.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.citylearn.entity.AlgorithmParamConfig;

/**
 * 算法参数定义表（algorithm_param_config）Mapper。
 *
 * <p>注意不要与 {@link AlgorithmConfigMapper} 混淆：那个对应 CHESCA / ResMARL 的
 * 参数取值键值表 algorithm_config。
 */
public interface AlgorithmParamConfigMapper extends BaseMapper<AlgorithmParamConfig> {
}
