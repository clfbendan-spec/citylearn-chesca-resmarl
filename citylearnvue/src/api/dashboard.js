import { get, post } from './http'

export const listHomeEvaluations = () => get('/web/home/evaluations')
export const getHomeEvaluation = (options) => get('/web/home/evaluation', options)
export const getHomeEvaluationSource = () => get('/web/home/source')
export const setHomeEvaluation = (taskId) => post('/web/home/evaluation', { data: { taskId } })

/**
 * 首页仪表盘 / 推荐看板接口。
 *
 * 图表读取仿真产物，首页来源设置保存评估记录 ID。
 */

/** 看板：仿真任务列表（已完成的那些才有产物） */
export function listDashboardSimulations(options) {
  return get('/web/basedata/getDashboardSimulations', options)
}

/** 单次仿真的详情（含 chesca_trace.csv 文本、KPI、决策叙事等） */
export function getDashboardSimulationDetail(taskId, options) {
  return get('/web/basedata/getDashboardSimulationDetail',
    Object.assign({}, options, { params: { ...(options && options.params), taskId } }))
}

export function getDashboardTracePage(params, options) {
  return get('/web/basedata/getDashboardTracePage', Object.assign({ params }, options))
}

/** Latest successful community CHESCA trajectory for the homepage only. */
export function getLatestCommunityChescaHomeData(options) {
  return get('/web/basedata/getLatestCommunityChescaHomeData', options)
}

/** 看板上的 KPI 行（按 pyFileId 聚合） */
export function listPyFileKpiRows(params, options) {
  return get('/web/basedata/getPyFileKpiRows', Object.assign({ params }, options))
}

/**
 * 首页能源流向（按天汇总）。
 * @param {{taskId:string, untilTs:string, datasetYear:number|string, mode:string}} params
 */
export function getHomeEnergyFlow(params, options) {
  return get('/web/basedata/getHomeEnergyFlow', Object.assign({ params }, options))
}

/** 首页逐时曲线 */
export function getHomeEnergyHourly(params, options) {
  return get('/web/basedata/getHomeEnergyHourly', Object.assign({ params }, options))
}
