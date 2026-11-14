import { get, post } from './http'

/**
 * 认证相关接口。
 * 路径统一写 `/web/...`，`/api` 前缀由 `http.js` 补（dev server 会把它 rewrite 掉）。
 */

/** 当前登录用户；未登录时后端返回 code≠0，这里表现为 ok=false */
export function fetchCurrentUser() {
  return get('/web/auth/current', { silent: true })
}

/**
 * 登录。
 * ⚠️ 请求体必须是 `URLSearchParams`（form-urlencoded），不能改成 JSON 或 query 参数：
 *    后端 auth 接口按表单收参，换格式会直接 400。这一条是从既有实现照搬的，不是猜测。
 */
export function login(username, password) {
  const body = new URLSearchParams()
  body.append('username', username)
  body.append('password', password)
  // silent: 登录页自己弹提示（保持改造前的措辞与位置），这里只负责返回 message
  return post('/web/auth/login', { data: body, silent: true, failMessage: '登录请求失败' })
}

export function logout() {
  return post('/web/auth/logout', { silent: true })
}
