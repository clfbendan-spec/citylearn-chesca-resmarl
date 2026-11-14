<template>
  <div id="app">
    <div v-if="!authChecked" class="auth-loading">加载中…</div>
    <login-page v-else-if="!currentUser" @login-success="onLoginSuccess" />

    <el-container v-else style="height: 100vh;">
      <el-aside :width="asideWidth" class="app-aside">
        <div class="aside-brand" v-show="!sidebarCollapsed">
          <div class="aside-brand-title">建筑群节能控制</div>
        </div>
        <el-menu
          :key="activeMenu"
          :default-active="activeMenu"
          :collapse="sidebarCollapsed"
          :collapse-transition="false"
          class="app-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item-group title="">
            <el-menu-item
              v-for="menu in visibleMenus"
              :key="menu.key"
              :index="menu.key"
            >
              <i :class="menu.icon"></i>
              <span slot="title">{{ menu.title }}</span>
            </el-menu-item>
          </el-menu-item-group>
        </el-menu>
        <button
          type="button"
          class="sidebar-toggle"
          :title="sidebarCollapsed ? '展开菜单' : '收起菜单'"
          @click="toggleSidebar"
        >
          <i :class="sidebarCollapsed ? 'el-icon-s-unfold' : 'el-icon-s-fold'"></i>
          <span v-show="!sidebarCollapsed">收起菜单</span>
        </button>
      </el-aside>

      <el-container class="app-body" direction="vertical">
        <el-header class="app-header" height="56px">
          <div class="header-left">
            <!-- 全局任务指示器：轮询 /getPyTaskNoticeSummary，任何页面都能看到
                 运行中数量与"执行完但未查看"数量；任务结束时也会弹出结果提示。 -->
            <button
              v-if="runningCount && hasPermission(PERMS.MENU_TASK_LIST)"
              type="button"
              class="header-notice-btn header-notice-running"
              title="有任务正在执行，点击查看任务管理"
              @click="handleMenuSelect('taskList')"
            >
              <i class="el-icon-loading header-notice-spin"></i>
              <span>执行中 {{ runningCount }}</span>
            </button>
            <!-- 待查看：悬浮显示气泡，气泡里可一键「设为已读」；点按钮本身仍然跳到任务管理 -->
            <el-popover
              v-if="unreadCount && hasPermission(PERMS.MENU_TASK_LIST)"
              placement="bottom-start"
              width="248"
              trigger="hover"
              popper-class="header-notice-popover"
            >
              <div class="notice-popover">
                <div class="notice-popover-title">有 {{ unreadCount }} 条执行完成但尚未查看的记录</div>
                <div class="notice-popover-actions">
                  <el-button
                    type="primary"
                    size="mini"
                    :loading="markingAllRead"
                    @click.stop="markAllRead"
                  >设为已读</el-button>
                </div>
              </div>
              <button
                slot="reference"
                type="button"
                class="header-notice-btn header-notice-unread"
                :title="`有 ${unreadCount} 条执行完成但尚未查看的记录，点击查看`"
                @click="handleMenuSelect('taskList')"
              >
                <i class="el-icon-bell"></i>
                <span>待查看 {{ unreadCount }}</span>
              </button>
            </el-popover>
          </div>
          <el-dropdown trigger="click" @command="handleUserCommand">
            <button type="button" class="header-user-btn">
              <i class="el-icon-user-solid header-user-icon"></i>
              <span class="header-user-name">{{ displayName }}</span>
              <i class="el-icon-arrow-down header-user-caret"></i>
            </button>
            <el-dropdown-menu slot="dropdown" class="header-user-menu">
              <el-dropdown-item disabled class="header-account-item">
                <div class="header-account-label">账号</div>
                <div class="header-account-value">{{ currentUser.username }}</div>
              </el-dropdown-item>
              <el-dropdown-item divided command="logout">注销</el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </el-header>
        <el-main class="app-main">
          <component
            ref="page"
            :is="currentComponent"
            @navigate-home="handleMenuSelect('home')"
            @navigate-back="handleNavigateBack"
            @open-task-record="handleOpenTaskRecord"
            @task-notice-changed="pollTaskNotice"
          />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script>
import DataList from './components/DataList.vue'
import MonacoEditor from './components/MonacoEditor.vue'
import ResMarlConfig from './views/ResMarlConfig.vue'
import AlgorithmParamConfig from './views/AlgorithmParamConfig.vue'
import HomePage from './views/HomePage.vue'
import RecDashboard from './views/RecDashboard.vue'
import LoginPage from './views/LoginPage.vue'
import UserManagement from './views/UserManagement.vue'
import TaskList from './views/TaskList.vue'
import BuildingManagement from './views/BuildingManagement.vue'
import CommunityManagement from './views/CommunityManagement.vue'
import { PERMS, userHasPermission } from './utils/permissions'
import { MENUS, findMenu, canUseMenu, firstAllowedMenu } from './config/menus'
import { fetchCurrentUser as apiFetchCurrentUser, logout as apiLogout } from './api/auth'
import {
  fetchTaskNoticeSummary,
  fetchTaskResult,
  markAllTasksNotified
} from './api/task'

const SIDEBAR_COLLAPSED_KEY = 'citylearn-sidebar-collapsed'

export default {
  name: 'App',
  components: {
    DataList,
    MonacoEditor,
    ResMarlConfig,
    AlgorithmParamConfig,
    HomePage,
    RecDashboard,
    LoginPage,
    UserManagement,
    TaskList,
    BuildingManagement,
    CommunityManagement
  },
  provide() {
    return {
      hasPermission: (code) => this.hasPermission(code)
    }
  },
  data() {
    return {
      PERMS,
      authChecked: false,
      currentUser: null,
      activeMenu: 'home',
      previousMenu: 'home',
      currentComponent: 'HomePage',
      sidebarCollapsed: false,
      /** 全局「运行中任务」列表（轮询 /getPyTaskNoticeSummary），任何页面都可见 */
      runningTasks: [],
      /** 执行完但未被查看（未读）的记录数 */
      unreadCount: 0,
      /** 「设为已读」请求进行中（气泡按钮 loading） */
      markingAllRead: false,
      /** 上一轮运行中的任务，用于检测"刚刚结束"并提示结果 */
      knownRunning: [],
      /** 首次轮询只建立基线不提示，避免把启动前遗留的已结束任务报成"刚完成" */
      runningPollReady: false,
      runningPollTimer: null
    }
  },
  computed: {
    asideWidth() {
      return this.sidebarCollapsed ? '64px' : '240px'
    },
    /**
     * 侧边栏实际渲染的菜单。三重过滤都集中在 config/menus.js 的 canUseMenu 里：
     * 开关（enabled）→ 角色（superAdminOnly）→ 权限码（perm）。
     * 模板只负责画，不再重复判断，避免和 handleMenuSelect 的守卫走样。
     */
    visibleMenus() {
      return MENUS.filter(m => canUseMenu(this.currentUser, m))
    },
    isSuperAdmin() {
      return this.currentUser && this.currentUser.role === 'SUPER_ADMIN'
    },
    displayName() {
      if (!this.currentUser) return ''
      return this.currentUser.nickname || this.currentUser.username || ''
    },
    /** 顶栏「运行中 N」 */
    runningCount() {
      return this.runningTasks.length
    }
  },
  created() {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    if (saved === '1') {
      this.sidebarCollapsed = true
    }
    if (window.innerWidth <= 680) this.sidebarCollapsed = true
    window.addEventListener('resize', this.collapseSidebarOnSmallViewport)
    this.fetchCurrentUser()
    window.addEventListener('citylearn-auth-required', this.onAuthRequired)
    window.addEventListener('citylearn-permission-denied', this.onPermissionDenied)
    // 全局轮询任务通知汇总：任何页面都能看到运行中/待查看数量与完成提示
    this.runningPollTimer = setInterval(this.pollTaskNotice, 5000)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.collapseSidebarOnSmallViewport)
    window.removeEventListener('citylearn-auth-required', this.onAuthRequired)
    window.removeEventListener('citylearn-permission-denied', this.onPermissionDenied)
    if (this.runningPollTimer) {
      clearInterval(this.runningPollTimer)
      this.runningPollTimer = null
    }
  },
  methods: {
    collapseSidebarOnSmallViewport() {
      if (window.innerWidth <= 680 && !this.sidebarCollapsed) this.sidebarCollapsed = true
    },
    hasPermission(code) {
      return userHasPermission(this.currentUser, code)
    },
    navigateToAllowed(preferred) {
      // 落点校验与 visibleMenus 共用 canUseMenu，避免「菜单看不到但能跳进去」
      let target = canUseMenu(this.currentUser, findMenu(preferred)) ? preferred : null
      if (!target) {
        target = firstAllowedMenu(this.currentUser)
      }
      if (!target) {
        this.activeMenu = ''
        this.currentComponent = 'HomePage'
        this.$message.warning('当前账号未分配任何菜单权限，请联系超级管理员')
        return
      }
      this.handleMenuSelect(target)
    },
    async fetchCurrentUser() {
      try {
        const { ok, data } = await apiFetchCurrentUser()
        if (ok && data) {
          this.currentUser = data
          this.$nextTick(() => this.navigateToAllowed(this.activeMenu || 'home'))
        } else {
          this.currentUser = null
        }
      } finally {
        this.authChecked = true
      }
    },
    onLoginSuccess(user) {
      this.currentUser = user
      this.authChecked = true
      this.$nextTick(() => this.navigateToAllowed('home'))
    },
    onAuthRequired() {
      if (this.currentUser) {
        this.$message.warning('登录已过期，请重新登录')
      }
      this.currentUser = null
      this.resetRunningPoll()
    },

    /** 接口级鉴权失败（code=403）：提示一次，说明是权限问题而不是数据加载失败 */
    onPermissionDenied(event) {
      const detail = (event && event.detail) || {}
      const msg = detail.message || '无权限访问该接口'
      this.$message.warning(`权限不足：${msg}`)
    },

    /**
     * 气泡里的「设为已读」：二次确认后，把所有未读的执行记录（含编排任务的子任务）标为已读。
     * 成功后顶栏计数清零，并广播 citylearn-tasks-read 让任务管理页 / 代码编辑器
     * 同步清掉本地的未读红点（否则要等它们各自下一次轮询）。
     */
    async markAllRead() {
      if (this.markingAllRead) {
        return
      }
      try {
        await this.$confirm(
          `确认将全部 ${this.unreadCount} 条未读记录标记为已读？标记后「待查看」红点会消失，且不可撤销。`,
          '设为已读',
          { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
        )
      } catch (e) {
        return
      }
      this.markingAllRead = true
      try {
        // silent: 由本方法自己弹一次错误，避免 http 层再弹一次（双 toast）
        const { ok, data, message } = await markAllTasksNotified({ silent: true })
        if (!ok) {
          this.$message.error(message || '设为已读失败')
          return
        }
        const count = Number(data) || 0
        this.unreadCount = 0
        this.$message.success(count > 0 ? `已将 ${count} 条记录标记为已读` : '没有需要标记的记录')
        window.dispatchEvent(new CustomEvent('citylearn-tasks-read'))
      } finally {
        this.markingAllRead = false
      }
    },

    /**
     * 轮询全局任务通知汇总：运行中任务列表 + 执行完未读数量。
     * 未登录 / 后端不可用时静默跳过（后者在后端重启期间会连续失败，恢复后自动续上）。
     * 无「任务管理」菜单权限时不发起请求：后端已按菜单权限校验该接口，否则会持续收到 403。
     */
    async pollTaskNotice() {
      if (!this.currentUser || !this.hasPermission(PERMS.MENU_TASK_LIST)) {
        return
      }
      try {
        // silent: 轮询失败要保持安静（后端重启期间会连续失败，恢复后自动续上）
        const { ok, data } = await fetchTaskNoticeSummary({ silent: true })
        if (!ok) {
          return
        }
        const summary = data || {}
        const running = summary.runningTasks || []
        this.notifyFinishedTasks(running)
        this.runningTasks = running
        this.unreadCount = Number(summary.unreadCount) || 0
      } finally {
        // 静默：无需处理，下一轮继续
      }
    },

    /**
     * 对比上一轮，对「刚刚结束」的任务弹出结果提示。
     * 首次轮询只建立基线、不提示 —— 否则会把启动前遗留的已结束任务报成"刚完成"。
     */
    async notifyFinishedTasks(newList) {
      const previous = this.knownRunning
      this.knownRunning = newList.map((t) => ({ taskId: t.taskId, scriptName: t.scriptName }))
      if (!this.runningPollReady) {
        this.runningPollReady = true
        return
      }
      const newIds = newList.map((t) => t.taskId)
      const finished = previous.filter((t) => newIds.indexOf(t.taskId) < 0)
      for (let i = 0; i < finished.length; i++) {
        await this.notifyOneFinished(finished[i])
      }
    },

    /** 查询刚结束任务的最终状态并提示（脚本名沿用上一轮已知的，避免多一次查询） */
    async notifyOneFinished(item) {
      const name = item.scriptName || '脚本任务'
      let statusDesc = ''
      try {
        // silent：这是「补一条更准确的提示」，拿不到状态就只提示"已结束"，不该再弹一个错误
        const { ok, data } = await fetchTaskResult(item.taskId, { silent: true })
        if (ok && data && data.statusDesc) {
          statusDesc = data.statusDesc
        }
      } catch (e) {
        // 拿不到状态就只提示"已结束"
      }
      const message = statusDesc ? `${name} 已结束（${statusDesc}）` : `${name} 已结束`
      if (statusDesc === '执行完成') {
        this.$message.success(message)
      } else {
        // 失败 / 运行终止 / 已中断 都按警告提示，避免被当成成功
        this.$message.warning(message)
      }
    },

    /** 清空任务通知相关状态（注销或会话失效时调用） */
    resetRunningPoll() {
      this.runningTasks = []
      this.unreadCount = 0
      this.knownRunning = []
      this.runningPollReady = false
    },
    handleUserCommand(command) {
      if (command === 'logout') {
        this.handleLogout()
      }
    },
    async handleLogout() {
      // 退出接口失败也要放行本地状态（否则后端不可用时会卡在登录态）
      await apiLogout()
      this.currentUser = null
      this.activeMenu = 'home'
      this.currentComponent = 'HomePage'
      this.resetRunningPoll()
      this.$message.success('已退出登录')
    },
    /**
     * 「任务管理」页点【详情】：切到代码编辑器，并把「要打开哪条记录」推给它。
     *
     * 这里用 ref 主动调用子组件方法，而不是 provide/inject 传值 —— 动态组件
     * `<component :is>` 既可能是本次新建的实例、也可能已存在，主动调用对两种
     * 情况都成立，不依赖任何渲染时序假设。
     */
    handleOpenTaskRecord(payload) {
      if (!payload || !payload.taskId) {
        return
      }
      if (!this.hasPermission(PERMS.MENU_CODE_EDITOR)) {
        this.$message.warning('无代码编辑器访问权限，无法查看该记录')
        return
      }
      this.handleMenuSelect('codeEditor')
      this.$nextTick(() => {
        const page = this.$refs.page
        if (page && typeof page.openTaskRecord === 'function') {
          page.openTaskRecord(payload.pyId, payload.taskId)
        } else {
          console.warn('[任务管理] 代码编辑器组件尚未就绪，无法打开详情', page)
          this.$message.warning('代码编辑器尚未就绪，请稍后重试')
        }
      })
    },
    handleMenuSelect(index) {
      const menu = findMenu(index)
      if (menu) {
        // 隐藏页：菜单里已经看不到它，这里再拦一道，避免别处误调跳到已隐藏的页面
        if (!menu.enabled) {
          this.$message.warning('「' + menu.title + '」页已隐藏')
          return
        }
        if (menu.superAdminOnly && !this.isSuperAdmin) {
          this.$message.warning('无权限访问用户管理')
          return
        }
        if (!canUseMenu(this.currentUser, menu)) {
          this.$message.warning('无权限访问该菜单')
          return
        }
      }
      if (index !== this.activeMenu) {
        this.previousMenu = this.activeMenu
      }
      this.activeMenu = index
      this.currentComponent = menu ? menu.component : 'HomePage'
    },
    handleNavigateBack() {
      const previous = findMenu(this.previousMenu)
      const target = previous && previous.key !== this.activeMenu && canUseMenu(this.currentUser, previous)
        ? previous.key
        : firstAllowedMenu(this.currentUser)
      if (target) this.handleMenuSelect(target)
    },
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, this.sidebarCollapsed ? '1' : '0')
      this.$nextTick(() => {
        window.dispatchEvent(new Event('resize'))
      })
    }
  }
}
</script>

<style>
#app {
  font-family: var(--ha-font-family);
  color: var(--primary-text-color);
}

.auth-loading {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--secondary-text-color);
  font-size: 14px;
  background: var(--primary-background-color);
}

.app-aside {
  background-color: var(--sidebar-background-color);
  border-right: 1px solid var(--sidebar-border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.28s ease;
}

.aside-brand {
  flex-shrink: 0;
  padding: 20px 20px 12px;
}

.aside-brand-title {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--primary-text-color);
}

.aside-brand-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
  letter-spacing: 0;
}

.app-menu {
  flex: 1;
  border-right: none !important;
  overflow-x: hidden;
  overflow-y: auto;
  background: transparent !important;
  padding: 4px 8px 12px;
}

.app-menu:not(.el-menu--collapse) {
  width: 240px;
}

.app-menu.el-menu--collapse {
  width: 64px;
  padding: 4px 0 12px;
}

.app-menu .el-menu-item {
  height: 44px;
  line-height: 44px;
  margin: 2px 0;
  border-radius: 8px;
  color: var(--sidebar-text-color) !important;
  background: transparent !important;
  display: flex;
  align-items: center;
}

.app-menu .el-menu-item i {
  color: var(--sidebar-icon-color);
  margin-right: 8px;
  width: 20px;
  flex-shrink: 0;
  text-align: center;
  font-size: 18px;
  line-height: 1;
}

.app-menu .el-menu-item:hover {
  background: rgba(var(--rgb-primary-color), 0.06) !important;
  color: var(--primary-color) !important;
}

.app-menu .el-menu-item:hover i {
  color: var(--sidebar-selected-icon-color);
}

.app-menu .el-menu-item.is-active {
  background: var(--sidebar-selected-background) !important;
  color: var(--sidebar-selected-text-color) !important;
  font-weight: 500;
}

.app-menu .el-menu-item.is-active i {
  color: var(--sidebar-selected-icon-color);
}

.app-menu.el-menu--collapse .el-menu-item {
  margin: 2px 8px;
  padding: 0 !important;
  justify-content: center;
  width: auto;
}

.app-menu.el-menu--collapse .el-menu-item i,
.app-menu.el-menu--collapse .el-menu-item .el-tooltip,
.app-menu.el-menu--collapse .el-tooltip {
  margin: 0 !important;
  margin-right: 0 !important;
}

.app-menu.el-menu--collapse .el-tooltip {
  display: flex !important;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 0 !important;
}

.app-menu.el-menu--collapse .el-menu-item i {
  width: 24px;
  font-size: 20px;
}

.el-menu--collapse .el-menu-item-group__title {
  display: none !important;
  padding: 0 !important;
  height: 0 !important;
}

.el-menu-item-group__title {
  color: var(--secondary-text-color) !important;
  padding: 12px 12px 8px !important;
  font-size: 12px !important;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.app-body {
  min-width: 0;
  background: var(--primary-background-color);
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--card-background-color, #fff);
  border-bottom: 1px solid var(--divider-color);
  box-sizing: border-box;
}

.header-left {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

/* 顶栏任务指示器：运行中 / 待查看 */
.header-notice-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  margin-right: 8px;
  padding: 0 12px;
  border: none;
  border-radius: 15px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  font-weight: 500;
  white-space: nowrap;
  transition: filter 0.15s ease;
}

.header-notice-btn:hover {
  filter: brightness(0.94);
}

/* 运行中：主色系柔和底 */
.header-notice-running {
  background: rgba(var(--rgb-primary-color), 0.12);
  color: var(--primary-color);
}

/* 待查看：红底白字，与文件列表 / 任务列表上的未读标记同一视觉语言 */
.header-notice-unread {
  background: var(--error-color);
  color: var(--text-primary-color);
}

/* 「待查看」悬浮气泡：内容由 popper-class 渲染到 body 下，必须是全局样式（不能 scoped） */
.header-notice-popover.el-popover {
  padding: 12px 14px;
}

.notice-popover-title {
  margin-bottom: 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--primary-text-color);
}

.notice-popover-actions {
  display: flex;
  justify-content: flex-end;
}

.header-notice-spin {
  font-size: 14px;
  animation: header-notice-rotate 1.4s linear infinite;
}

@keyframes header-notice-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.header-user-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 220px;
  height: 36px;
  padding: 0 10px 0 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--primary-text-color);
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  transition: background 0.15s ease;
}

.header-user-btn:hover {
  background: rgba(var(--rgb-primary-color), 0.08);
}

.header-user-icon {
  font-size: 16px;
  color: var(--primary-color);
}

.header-user-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.header-user-caret {
  font-size: 12px;
  color: var(--secondary-text-color);
}

.header-account-item {
  cursor: default !important;
  line-height: 1.4 !important;
  opacity: 1 !important;
  color: var(--primary-text-color) !important;
}

.header-account-label {
  font-size: 12px;
  color: var(--secondary-text-color);
}

.header-account-value {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.sidebar-toggle {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 48px;
  padding: 0 12px;
  border: none;
  border-top: 1px solid var(--divider-color);
  background: var(--card-background-color);
  color: var(--secondary-text-color);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: background 0.15s ease, color 0.15s ease;
}

.sidebar-toggle:hover {
  background: rgba(var(--rgb-primary-color), 0.06);
  color: var(--primary-color);
}

.app-aside .sidebar-toggle i {
  margin: 0;
  width: 20px;
  text-align: center;
  font-size: 18px;
  line-height: 1;
}

.app-main {
  flex: 1;
  height: auto;
  padding: 0 !important;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--primary-background-color);
}
</style>
