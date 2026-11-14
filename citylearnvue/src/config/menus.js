import { PERMS, userHasPermission } from '../utils/permissions'

/**
 * 菜单的**唯一真源**。
 *
 * 为什么要有这个文件：加一个菜单入口原本要同步六处 —— 后端 `PermissionCodes.java`、
 * DB `permission` 表、前端 `PERMS` 常量、`MENU_PERM_MAP`、`firstAllowedMenu` 的 order、
 * 以及 App.vue 的菜单项 + 组件映射。漏掉收尾就会留下「map 有条目、菜单没有项」的
 * 死页面（本仓库曾因此积了 6 个不可达组件，见 commit 里的 P1）。
 *
 * 现在只改这里，其余三处都是派生的：
 *   · `MENU_PERM_MAP`  ← 本表的 perm
 *   · `MENU_COMPONENTS` ← 本表的 component
 *   · `firstAllowedMenu` 的落点顺序 ← 本表顺序（跳过 enabled=false 与 superAdminOnly）
 *
 * 一致性由 `_verify_menu_perm_align.py` 做四方断言（本表 ↔ App.vue 实际渲染 ↔
 * PermissionCodes.java ↔ DB permission 表）。加菜单后跑一次它，别靠肉眼。
 *
 * 字段：
 *   key            菜单标识，同时是 `handleMenuSelect(index)` 的入参
 *   title          侧边栏文字
 *   icon           Element UI 图标类名
 *   perm           访问所需权限码；`null` 表示不挂权限码（必须配 superAdminOnly 之类的守卫）
 *   component      `handleMenuSelect` 要渲染的组件名（必须在 App.vue 的 components 里注册）
 *   enabled        false = 入口隐藏（页面组件与后端接口都保留，翻回 true 即恢复）
 *   superAdminOnly true = 只对超管可见（不挂权限码，靠角色判断）
 */
export const MENUS = [
  {
    key: 'home',
    title: '首页',
    icon: 'el-icon-s-home',
    perm: PERMS.MENU_HOME,
    component: 'HomePage',
    enabled: true
  },
  {
    key: 'recDashboard',
    title: '模型优选',
    icon: 'el-icon-data-line',
    perm: PERMS.MENU_REC_DASHBOARD,
    component: 'RecDashboard',
    enabled: true
  },
  {
    key: 'communityManagement',
    title: '社区管理',
    icon: 'el-icon-office-building',
    perm: PERMS.MENU_BUILDING_MANAGEMENT,
    component: 'CommunityManagement',
    enabled: true
  },
  {
    key: 'buildingManagement',
    title: '建筑管理',
    icon: 'el-icon-office-building',
    perm: PERMS.MENU_BUILDING_MANAGEMENT,
    component: 'BuildingManagement',
    enabled: false
  },
  {
    key: 'dataList',
    title: '数据集查看',
    icon: 'el-icon-menu',
    perm: PERMS.MENU_DATA_LIST,
    component: 'DataList',
    enabled: true
  },
  {
    key: 'codeEditor',
    title: '代码编辑器',
    icon: 'el-icon-edit',
    perm: PERMS.MENU_CODE_EDITOR,
    component: 'MonacoEditor',
    enabled: true
  },
  {
    key: 'taskList',
    title: '任务管理',
    icon: 'el-icon-tickets',
    perm: PERMS.MENU_TASK_LIST,
    component: 'TaskList',
    enabled: true
  },
  {
    // 2026-10-08 按使用者要求隐藏：这些参数（α / 残差动作掩码 / 模型路径 …）现在都在
    // 代码编辑器与任务管理页的「配置」弹窗里按任务设置，不需要再留一个全局配置页。
    // 页面组件、路由分支与后端接口都原样保留 ⇒ 把 enabled 改成 true 即可恢复；
    // 恢复前先看 citylearnvue/README-deploy.md 里那 7 个专用接口的说明。
    key: 'resMarlConfig',
    title: 'CHESCA-ResMARL配置',
    icon: 'el-icon-s-operation',
    perm: PERMS.MENU_RES_MARL,
    component: 'ResMarlConfig',
    enabled: false
  },
  {
    key: 'algorithmParam',
    title: '参数配置',
    icon: 'el-icon-setting',
    perm: PERMS.MENU_ALGORITHM_PARAM,
    component: 'AlgorithmParamConfig',
    enabled: true
  },
  {
    key: 'userManagement',
    title: '用户管理',
    icon: 'el-icon-user-solid',
    perm: null,
    component: 'UserManagement',
    enabled: true,
    superAdminOnly: true
  }
]

/** key → 权限码。只收挂了权限码的菜单。 */
export const MENU_PERM_MAP = MENUS.reduce((acc, m) => {
  if (m.perm) acc[m.key] = m.perm
  return acc
}, {})

/** key → 组件名。`handleMenuSelect` 用它决定渲染哪个页面。 */
export const MENU_COMPONENTS = MENUS.reduce((acc, m) => {
  acc[m.key] = m.component
  return acc
}, {})

export function findMenu(key) {
  return MENUS.filter(m => m.key === key)[0] || null
}

/**
 * 当前用户能否使用某个菜单：开关 → 角色 → 权限码。
 * 三处判断集中在函数里，避免模板、handleMenuSelect、navigateToAllowed 各写一遍走样。
 */
export function canUseMenu(user, menu) {
  if (!menu || !menu.enabled) return false
  if (menu.superAdminOnly && !(user && user.role === 'SUPER_ADMIN')) return false
  if (menu.perm) return userHasPermission(user, menu.perm)
  return true
}

/**
 * 登录后/权限不足时的落点：按 MENUS 的顺序找第一个可用菜单。
 * 顺序即 MENUS 的顺序，不再单独维护 order 数组（原先两处顺序不同步就会落到空白页）。
 */
export function firstAllowedMenu(user) {
  const hit = MENUS.filter(m => !m.superAdminOnly && canUseMenu(user, m))[0]
  if (hit) return hit.key
  if (user && user.role === 'SUPER_ADMIN') return 'userManagement'
  return null
}
