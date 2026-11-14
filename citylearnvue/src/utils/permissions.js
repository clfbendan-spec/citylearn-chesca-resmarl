/**
 * 权限码常量 + 「这个用户有没有某个码」。
 *
 * ⚠️ 菜单相关的两份派生数据（`MENU_PERM_MAP`、`firstAllowedMenu`）已迁到
 * `src/config/menus.js` —— 那里的 `MENUS` 是唯一真源，这两份是从它派生的。
 * 之前它们放在本文件，与 App.vue 的组件映射形成两个平行副本，已经漂移过
 * （`MENU_PERM_MAP` 7 个 key、App.vue map 14 个 key）。别再往这里加菜单表。
 */
export const PERMS = {
  MENU_HOME: 'menu:home',
  MENU_REC_DASHBOARD: 'menu:recDashboard',
  // 模型优选：重算 KPI（GET 但会启动 Python 并写库，单独发放）
  REC_UPDATE_LEARN: 'recDashboard:updateLearn',
  MENU_DATA_LIST: 'menu:dataList',
  MENU_BUILDING_MANAGEMENT: 'menu:buildingManagement',
  BUILDING_WRITE: 'building:write',
  MENU_CODE_EDITOR: 'menu:codeEditor',
  MENU_TASK_LIST: 'menu:taskList',
  MENU_RES_MARL: 'menu:resMarlConfig',
  MENU_ALGORITHM_PARAM: 'menu:algorithmParam',
  // 代码编辑器：脚本级（保存 / 执行 / 删除脚本）
  CODE_SAVE: 'codeEditor:save',
  CODE_RUN: 'codeEditor:run',
  CODE_DELETE_FILE: 'codeEditor:deleteFile',
  // 代码编辑器：执行记录级（删除 / 改名 / 展示）
  CODE_DELETE_RECORD: 'codeEditor:deleteRecord',
  CODE_RENAME_RECORD: 'codeEditor:renameRecord',
  CODE_SHOW_RECORD: 'codeEditor:showRecord',
  RES_MARL_OPERATE: 'resMarlConfig:operate',
  // 任务管理：新建 / 编辑 / 删除 / 执行
  TASK_CREATE: 'taskList:create',
  TASK_EDIT: 'taskList:edit',
  TASK_DELETE: 'taskList:delete',
  TASK_RUN: 'taskList:run',
  // 参数配置：单独配置（分组节点 + 新建/编辑/删除）
  PARAM_ITEM: 'algorithmParam:item',
  PARAM_ITEM_CREATE: 'algorithmParam:itemCreate',
  PARAM_ITEM_EDIT: 'algorithmParam:itemEdit',
  PARAM_ITEM_DELETE: 'algorithmParam:itemDelete',
  // 参数配置：配置组（分组节点 + 新建/编辑/删除/移入/移出）
  PARAM_SET: 'algorithmParam:set',
  PARAM_SET_CREATE: 'algorithmParam:setCreate',
  PARAM_SET_EDIT: 'algorithmParam:setEdit',
  PARAM_SET_DELETE: 'algorithmParam:setDelete',
  PARAM_SET_MOVE_IN: 'algorithmParam:setMoveIn',
  PARAM_SET_MOVE_OUT: 'algorithmParam:setMoveOut'
}

export function userHasPermission(user, code) {
  if (!user || !code) return false
  if (user.role === 'SUPER_ADMIN') return true
  const list = user.permissions || []
  return list.indexOf(code) >= 0
}
