import { get, post } from './http'

/**
 * 算法参数配置接口（`/web/basedata/*AlgorithmParamConfig*`）。
 *
 * 两层结构：
 *   - 参数（config）：一条 = 一个可调键（name / paramName / valueType / defaultValue…）
 *   - 配置组（set）：一组参数的集合，参数可「加入 / 移出」，成员关系由后端维护
 *
 * ⚠️ 写接口的 body 是 JSON（后端 `@RequestBody`），**不是**表单体。
 *    与 `/web/user/*` 相反，改错格式会 400/415。
 */

/** 单独参数列表。isMember=0 表示「还没被任何配置组占用」的那些 */
export function listParamConfigs(isMember, options) {
  return get('/web/basedata/getAlgorithmParamConfigList',
    Object.assign({ params: { isMember } }, options))
}

export function listParamConfigSets(options) {
  return get('/web/basedata/getAlgorithmParamConfigSetList', options)
}

export function getParamConfigSetDetail(setId, options) {
  return get('/web/basedata/getAlgorithmParamConfigSetDetail',
    Object.assign({ params: { id: setId } }, options))
}

export function addParamConfig(payload, options) {
  return post('/web/basedata/addAlgorithmParamConfig', Object.assign({ data: payload }, options))
}

export function updateParamConfig(payload, options) {
  return post('/web/basedata/updateAlgorithmParamConfig', Object.assign({ data: payload }, options))
}

export function deleteParamConfig(id, options) {
  return post('/web/basedata/deleteAlgorithmParamConfig', Object.assign({ data: { id } }, options))
}

/**
 * 新增 / 更新配置组。
 * 传了 `memberIds` 就整组覆盖成员（后端同时写入名称/简介）——「加入 / 移出」也走 update。
 */
export function addParamConfigSet(payload, options) {
  return post('/web/basedata/addAlgorithmParamConfigSet', Object.assign({ data: payload }, options))
}

export function updateParamConfigSet(payload, options) {
  return post('/web/basedata/updateAlgorithmParamConfigSet', Object.assign({ data: payload }, options))
}

export function deleteParamConfigSet(id, options) {
  return post('/web/basedata/deleteAlgorithmParamConfigSet', Object.assign({ data: { id } }, options))
}
