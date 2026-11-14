import { get, post } from './http'

/**
 * 模型侧配置：CHESCA-ResMARL 与电池最小 SOC。
 *
 * 两者的形态一致：一套「单体配置」（get / save / reset），
 * 背后存的是一组参数键值，页面上按分区展示。
 */

/* ---------------- CHESCA-ResMARL ---------------- */

export function getResMarlConfig(options) {
  return get('/web/basedata/getResMarlConfig', options)
}

export function saveResMarlConfig(payload, options) {
  return post('/web/basedata/saveResMarlConfig', Object.assign({ data: payload }, options))
}

/** 恢复默认值（后端按内置默认重写一遍，不是删记录） */
export function resetResMarlConfig(options) {
  return post('/web/basedata/resetResMarlConfig', options)
}

/* ---------------- 电池最小 SOC ---------------- */

export function getBatteryMinSocConfig(options) {
  return get('/web/basedata/getBatteryMinSocConfig', options)
}

export function saveBatteryMinSocConfig(payload, options) {
  return post('/web/basedata/saveBatteryMinSocConfig', Object.assign({ data: payload }, options))
}
