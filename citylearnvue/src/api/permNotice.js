/**
 * 403 提示的节流与派发。
 *
 * 为什么要单独一个模块：原先这段逻辑写在 `main.js` 的响应拦截器里，节流时间戳挂在
 * `window.__permWarnAt` 上 —— 这是隐式全局，测试里拿不到、两个页面并发请求时行为
 * 取决于谁先跑，而且新增一个请求层（`api/http.js`）时很容易再写一份，导致一次 403
 * 弹两次提示。收进模块作用域后只有一份状态。
 *
 * 派发的是 DOM 事件而不是直接弹 Element 的 Message，原因是「提示文案」由 App.vue 决定
 * （它能拿到当前登录态与菜单信息），这里只负责「多久允许提示一次」。
 */
const PERM_WARN_INTERVAL = 3000
let lastWarnAt = 0

/**
 * @param {string} message 后端给的文案
 * @returns {boolean} 本次是否真的派发了（被节流时返回 false，便于测试断言）
 */
export function notifyPermissionDenied(message) {
  const now = Date.now()
  if (now - lastWarnAt <= PERM_WARN_INTERVAL) {
    return false
  }
  lastWarnAt = now
  window.dispatchEvent(new CustomEvent('citylearn-permission-denied', {
    detail: { message: message || '无权限访问该接口' }
  }))
  return true
}

/** 仅测试用：重置节流窗口 */
export function resetPermissionNoticeThrottle() {
  lastWarnAt = 0
}
