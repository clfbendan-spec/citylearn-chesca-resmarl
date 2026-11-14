import { get, post } from './http'
import axios from 'axios'

const base = '/web/communities'
export const listCommunities = () => get(base)
export const getFields = () => get(base + '/fields')
export const getCommunity = id => get(`${base}/${id}`)
export const saveCommunity = (id, data) => post(base + (id ? '/' + id : ''), { data })
export const deleteCommunity = id => post(`${base}/${id}/delete`)
export const listBuildings = id => get(`${base}/${id}/buildings`)
export const createBuilding = (id, data) => post(`${base}/${id}/buildings`, { data })
export const measurements = (id, params) => get(`${base}/${id}/measurements`, { params })
export const batches = (id, params) => get(`${base}/${id}/batches`, { params })
export const ingest = (id, data) => post(`${base}/${id}/ingest`, { data })
export const rotateToken = id => post(`${base}/${id}/token`)
export const uploadModel = (id, file) => { const data = new FormData(); data.append('file', file); return post(`${base}/${id}/models`, { data }) }
export const datasets = id => get(`${base}/${id}/datasets`)
export const publicationRange = (id, data) => post(`${base}/${id}/datasets/range`, { data })
export const preview = (id, data) => post(`${base}/${id}/datasets/preview`, { data })
export const publish = (id, data) => post(`${base}/${id}/datasets`, { data })
export const publicationTasks = id => get(`${base}/${id}/datasets/publication-tasks`, { silent: true })
export const getPublicationTask = (id, task) => get(`${base}/${id}/datasets/publication-tasks/${task}`, { silent: true })
const generatorBase = id => `${base}/${id}/datasets/generator`
export const previewOl1Scenario = (id, data) => post(generatorBase(id) + '/preview', { data })
export const startOl1Scenario = (id, data) => post(generatorBase(id) + '/tasks', { data })
export const listOl1ScenarioTasks = id => get(generatorBase(id) + '/tasks', { silent: true })
export const getOl1ScenarioTask = (id, task) => get(generatorBase(id) + '/tasks/' + task, { silent: true })
export const cancelOl1ScenarioTask = (id, task) => post(generatorBase(id) + '/tasks/' + task + '/cancel', { data: {} })
export const deleteDataset = (id, version) => post(`${base}/${id}/datasets/${version}/delete`)
const assessmentsBase = (id, version) => `${base}/${id}/datasets/${version}/assessments`
export const listAssessments = (id, version) => get(assessmentsBase(id, version), { silent: true })
export const startAssessment = (id, version, options = {}) => post(assessmentsBase(id, version), { data: options })
export const getAssessment = (id, version, run) => get(`${assessmentsBase(id, version)}/${run}`, { silent: true })
export const cancelAssessment = (id, version, run) => post(`${assessmentsBase(id, version)}/${run}/cancel`, { data: {} })
export async function getAssessmentReport(id, version, run) {
  try { const response = await axios.get('/api' + assessmentsBase(id, version) + '/' + run + '/report', { responseType: 'text' }); return { ok: true, data: response.data } }
  catch (_) { return { ok: false, message: '报告读取失败，请稍后重试' } }
}
export const getHomeSource = () => get('/web/home/source')
export const saveHomeSource = communityId => post('/web/home/source', { data: { communityId } })
