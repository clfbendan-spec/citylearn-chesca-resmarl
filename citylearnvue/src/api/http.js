import axios from 'axios'

/**
 * 统一请求层。
 *
 * 为什么需要它：后端所有接口的响应都是 `{ code, message, data }`（`code === 0` 表示成功），
 * 但此前每个调用点都自己写一遍「判断 code、判断 data 是否存在、失败了提示什么」——
 * 全仓库 36 处手写 `code === 0`、113 处 `$message.*`，后端改一次包装要改几十处。
 *
 * 本模块只做四件事：
 *   1. 统一判定成功（`code === 0`）
 *   2. 统一把失败转成 `{ ok: false, message }`，**不抛异常**
 *   3. 统一 `$message.error` 兜底文案（页面要自定义文案就传 failMessage）
 *   4. 统一 401/403 的语义出口（仍复用 main.js 里的全局事件，保持既有行为）
 *
 * ⚠️ 设计选择：`request()` 不抛异常，返回 `{ ok, data, message, code }`。
 *    原因是既有页面全是 `try { ... } catch` + `if (code === 0)` 的写法，
 *    改成抛异常需要重排所有控制流，风险远大于收益。返回对象则是一行替换。
 *
 * ⚠️ 迁移期间允许并存：没迁移的调用点继续用 `axios.get(...)`，行为完全不变。
 *    这是刻意的「零侵入」——每批迁移只改一批文件，改完跑一遍验收脚本。
 */
import { Message } from 'element-ui'

/**
 * 把后端各种失败形态归一成一句人话。
 * 后端 `Result.fail` 的 message 通常是中文，直接用；没有就给兜底。
 */
function pickMessage(body, fallback) {
  if (body && typeof body.message === 'string' && body.message) return body.message
  return fallback || '请求失败'
}

/**
 * 发一个请求。
 *
 * ⚠️ 401/403 的提示**不在这里**做：`main.js` 的响应拦截器统一负责（节流在
 *    `api/permNotice.js`）。本模块用的是同一个 axios 实例，所以新老调用点都覆盖得到；
 *    如果这里再派发一次，一次 403 就会弹两个提示。
 *
 * @param {'get'|'post'} method
 * @param {string} url 以 `/web/...` 开头（本模块统一补 `/api` 前缀）
 * @param {object} [options]
 * @param {object} [options.params]   query 参数
 * @param {object} [options.data]     body
 * @param {string} [options.failMessage] 失败时的提示文案；传 `false` 表示不提示
 * @param {boolean} [options.silent]  同 failMessage=false，语义更直白
 * @returns {Promise<{ok: boolean, data: any, message: string, code: number|null}>}
 */
export async function request(method, url, options) {
  const opts = options || {}
  // 调用方偶尔会传完整路径（含 /api），这里统一成 /api/web/...
  const full = url.indexOf('/api/') === 0 ? url : '/api' + url
  const config = {}
  if (opts.params) config.params = opts.params
  if (opts.data !== undefined) config.data = opts.data

  let res
  try {
    res = method === 'post' ? await axios.post(full, config.data, config) : await axios.get(full, config)
  } catch (e) {
    // 网络层失败（后端没起、超时、断网）。401/403 由 main.js 的拦截器转成事件，不进这里。
    const raw = (e && e.response && e.response.status === 401)
      ? '登录状态已失效，请重新登录'
      : '网络异常，请稍后重试'
    // 调用方指定了文案就用它的（保持既有页面上的措辞不变）
    const msg = (opts.failMessage && opts.failMessage !== false) ? opts.failMessage : raw
    if (!opts.silent && opts.failMessage !== false) {
      Message.error(msg)
    }
    return { ok: false, data: null, message: msg, code: null }
  }

  const body = res && res.data

  if (body && body.code === 0) {
    return { ok: true, data: body.data, message: body.message || '', code: 0 }
  }

  const message = pickMessage(body, opts.failMessage)
  if (!opts.silent && opts.failMessage !== false) {
    Message.error(message)
  }
  return { ok: false, data: null, message, code: body ? body.code : null }
}

export function get(url, options) {
  return request('get', url, options)
}

export function post(url, options) {
  return request('post', url, options)
}

/**
 * 迁移过渡期用：把旧的 axios 响应对象（`res.data.code === 0` 那套）转成统一结构。
 * 已经拿到 axios 原始响应的调用点（比如需要读 headers 的）可以用它，
 * 不必为了用新层而重写请求。
 */
export function unwrap(res, failMessage) {
  const body = res && res.data
  if (body && body.code === 0) {
    return { ok: true, data: body.data, message: body.message || '', code: 0 }
  }
  const message = pickMessage(body, failMessage)
  return { ok: false, data: null, message, code: body ? body.code : null }
}
