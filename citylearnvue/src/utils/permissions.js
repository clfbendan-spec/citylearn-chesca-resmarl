/** 与后端 PermissionCodes 保持一致 */
export const PERMS = {
  MENU_HOME: 'menu:home',
  MENU_REC_DASHBOARD: 'menu:recDashboard',
  MENU_DATA_LIST: 'menu:dataList',
  MENU_CODE_EDITOR: 'menu:codeEditor',
  MENU_TASK_LIST: 'menu:taskList',
  MENU_RES_MARL: 'menu:resMarlConfig',
  MENU_ALGORITHM_PARAM: 'menu:algorithmParam',
  CODE_EDITOR_OPERATE: 'codeEditor:operate',
  CODE_EDITOR_DELETE: 'codeEditor:delete',
  RES_MARL_OPERATE: 'resMarlConfig:operate'
}

export const MENU_PERM_MAP = {
  home: PERMS.MENU_HOME,
  recDashboard: PERMS.MENU_REC_DASHBOARD,
  dataList: PERMS.MENU_DATA_LIST,
  codeEditor: PERMS.MENU_CODE_EDITOR,
  taskList: PERMS.MENU_TASK_LIST,
  resMarlConfig: PERMS.MENU_RES_MARL,
  algorithmParam: PERMS.MENU_ALGORITHM_PARAM
}

export function userHasPermission(user, code) {
  if (!user || !code) return false
  if (user.role === 'SUPER_ADMIN') return true
  const list = user.permissions || []
  return list.indexOf(code) >= 0
}

export function firstAllowedMenu(user) {
  // 注意：'resMarlConfig'（CHESCA-ResMARL 配置页）2026-10-08 起在 App.vue 里被隐藏
  // （见那边的 SHOW_RES_MARL_CONFIG_MENU）⇒ 这里不作为回退落点，免得落在空白页
  const order = ['home', 'recDashboard', 'dataList', 'codeEditor', 'taskList', 'algorithmParam']
  for (let i = 0; i < order.length; i++) {
    const key = order[i]
    if (userHasPermission(user, MENU_PERM_MAP[key])) {
      return key
    }
  }
  if (user && user.role === 'SUPER_ADMIN') {
    return 'userManagement'
  }
  return null
}
