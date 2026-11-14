import { get, post } from './http'

/**
 * 任务（py_task）相关接口。
 *
 * 说明：任务的「训练 / 训练+评估」是两种编排，落库都进同一张 py_task 表；
 * `executePipelineTask` 只是把待执行记录交给后端拆子任务，不直接跑脚本。
 */

/** 任务列表（后端已按 create_time 倒序） */
export function listTasks(options) {
  return get('/web/basedata/getAllPyTaskList', options)
}

/** 子任务列表（训练+评估编排拆出来的那些） */
export function listSubTasks(taskId, options) {
  return get('/web/basedata/getSubTaskList', Object.assign({ params: { taskId } }, options))
}

export function deleteTask(taskId, options) {
  return post('/web/basedata/deletePyTask', Object.assign({ data: { taskId } }, options))
}

/** 执行（训练+评估会由后端按顺序拆成两条子任务） */
export function executePipelineTask(taskId, options) {
  return post('/web/basedata/executePipelineTask', Object.assign({ data: { taskId } }, options))
}

export function markTaskNotified(taskId, options) {
  return post('/web/basedata/markPyTaskNotified', Object.assign({ data: { taskId } }, options))
}

export function markAllTasksNotified(options) {
  return post('/web/basedata/markAllPyTaskNotified', options)
}

/** 顶栏通知摘要：运行中数量 + 未读数 */
export function fetchTaskNoticeSummary(options) {
  return get('/web/basedata/getPyTaskNoticeSummary', options)
}

export function fetchTaskResult(taskId, options) {
  return get('/web/basedata/getPyTaskResult', Object.assign({ params: { taskId } }, options))
}

/* ---------------- 编排任务（训练 / 训练+评估）---------------- */

/** Python 脚本下拉。scriptType: 'train' | 'eval' */
export function listPyFiles(scriptType, options) {
  return get('/web/basedata/getPyFileList',
    Object.assign({ params: { scriptType } }, options))
}

/**
 * 「复用历史成功训练任务」候选。
 * ⚠️ 必须按 `pyFileId` 过滤：不过滤会把 CHESCA / Multi-agent 的训练记录全列进来，
 *    选错会因观测维度/奖励语义不匹配而跑不出结果。
 */
export function listTrainModelTasks(pyFileId, options) {
  return get('/web/basedata/getTrainModelTaskList',
    Object.assign({ params: pyFileId ? { pyFileId } : {} }, options))
}

/** 任务详情（编辑模式回填表单用） */
export function fetchTaskDetail(taskId, options) {
  return get('/web/basedata/getPyTaskDetail', Object.assign({ params: { taskId } }, options))
}

export function createPipelineTask(payload, options) {
  return post('/web/basedata/createPipelineTask', Object.assign({ data: payload }, options))
}

export function updatePipelineTask(payload, options) {
  return post('/web/basedata/updatePipelineTask', Object.assign({ data: payload }, options))
}
