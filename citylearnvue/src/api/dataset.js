import { get } from './http'

/**
 * 原始数据（数据集 / 逐时负荷）相关接口。
 */

/** 可选数据集列表（schemaKey + 名称，来自 citylearn_dataset.sql） */
export function getDatasetList(options) {
  return get('/web/basedata/getDatasetList', options)
}

/**
 * 按筛选条件查逐时负荷。
 * @param {{buildingId:number, datasetSchema:string, date?:string, dayType?:string, hour?:number}} params
 */
export function getList(params, options) {
  return get('/web/basedata/getList', Object.assign({ params }, options))
}
