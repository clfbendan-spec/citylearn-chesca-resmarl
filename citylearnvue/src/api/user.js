import { get, post } from './http'

/**
 * 用户管理接口（`/web/user/*`）。
 *
 * ⚠️ 除两个查询接口外，其余全部用 `@RequestParam` 接收，body 必须是
 *    `application/x-www-form-urlencoded`（`URLSearchParams`）。改成 JSON 会直接 400。
 *
 * ⚠️ 「新增 / 编辑 / 重置密码」三个动作的边界（后端强制的，前端不要越界）：
 *    - 新增：username + password（必填）+ nickname（可选）
 *    - 编辑：只改 username + nickname，**不收 password**（改密码只走 resetPassword）
 *    - 编辑 / 删除 都不允许作用于 SUPER_ADMIN（后端会拒）
 */

/** 权限树（全部可选权限码，含分组层级） */
export function fetchPermissionTree(options) {
  return get('/web/user/permissionTree', options)
}

/** 某个用户已勾选的权限码数组 */
export function fetchUserPermissions(userId, options) {
  return get('/web/user/getPermissions', Object.assign({ params: { id: userId } }, options))
}

export function saveUserPermissions(userId, permissions, options) {
  const body = new URLSearchParams()
  body.append('id', userId)
  body.append('permissions', JSON.stringify(permissions))
  return post('/web/user/savePermissions', Object.assign({ data: body }, options))
}

/** 分页列表。params: `{ username?, currentPage, pageSize }` */
export function listUsers(params, options) {
  return get('/web/user/listPage', Object.assign({ params }, options))
}

export function resetUserPassword(id, password, options) {
  const body = new URLSearchParams()
  body.append('id', id)
  body.append('password', password)
  return post('/web/user/resetPassword', Object.assign({ data: body }, options))
}

export function addUser(user, options) {
  const body = new URLSearchParams()
  body.append('username', (user.username || '').trim())
  body.append('password', user.password)
  if (user.nickname) body.append('nickname', (user.nickname || '').trim())
  return post('/web/user/add', Object.assign({ data: body }, options))
}

export function editUser(user, options) {
  const body = new URLSearchParams()
  body.append('id', user.id)
  body.append('username', (user.username || '').trim())
  body.append('nickname', user.nickname || '')
  return post('/web/user/edit', Object.assign({ data: body }, options))
}

export function deleteUser(id, options) {
  const body = new URLSearchParams()
  body.append('id', id)
  return post('/web/user/delete', Object.assign({ data: body }, options))
}
