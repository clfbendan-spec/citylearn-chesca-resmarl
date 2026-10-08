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
            <el-menu-item v-if="hasPermission(PERMS.MENU_HOME)" index="home">
              <i class="el-icon-s-home"></i>
              <span slot="title">首页</span>
            </el-menu-item>
            <el-menu-item v-if="hasPermission(PERMS.MENU_REC_DASHBOARD)" index="recDashboard">
              <i class="el-icon-data-line"></i>
              <span slot="title">模型优选</span>
            </el-menu-item>
            <el-menu-item v-if="hasPermission(PERMS.MENU_DATA_LIST)" index="dataList">
              <i class="el-icon-menu"></i>
              <span slot="title">原始数据</span>
            </el-menu-item>
            <el-menu-item v-if="hasPermission(PERMS.MENU_CODE_EDITOR)" index="codeEditor">
              <i class="el-icon-edit"></i>
              <span slot="title">代码编辑器</span>
            </el-menu-item>
            <el-menu-item v-if="hasPermission(PERMS.MENU_TASK_LIST)" index="taskList">
              <i class="el-icon-tickets"></i>
              <span slot="title">任务管理</span>
            </el-menu-item>
            <!-- 「CHESCA-ResMARL 配置」页：2026-10-08 起按使用者要求隐藏，
                 入口由 SHOW_RES_MARL_CONFIG_MENU 统一开关（页面组件与接口都保留） -->
            <el-menu-item
              v-if="SHOW_RES_MARL_CONFIG_MENU && hasPermission(PERMS.MENU_RES_MARL)"
              index="resMarlConfig"
            >
              <i class="el-icon-s-operation"></i>
              <span slot="title">CHESCA-ResMARL配置</span>
            </el-menu-item>
            <el-menu-item v-if="hasPermission(PERMS.MENU_ALGORITHM_PARAM)" index="algorithmParam">
              <i class="el-icon-setting"></i>
              <span slot="title">参数配置</span>
            </el-menu-item>
            <el-menu-item v-if="showAnalysisMenus" index="forecastMape">
              <i class="el-icon-data-analysis"></i>
              <span slot="title">预测误差 MAPE</span>
            </el-menu-item>
            <el-menu-item v-if="showAnalysisMenus" index="residualDeltaEle">
              <i class="el-icon-s-marketing"></i>
              <span slot="title">残差 ΔELE</span>
            </el-menu-item>
            <el-menu-item v-if="showAnalysisMenus" index="alphaSweep">
              <i class="el-icon-s-data"></i>
              <span slot="title">α–KPI 扫描</span>
            </el-menu-item>
            <el-menu-item v-if="isSuperAdmin" index="userManagement">
              <i class="el-icon-user-solid"></i>
              <span slot="title">用户管理</span>
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
            <button
              v-if="unreadCount && hasPermission(PERMS.MENU_TASK_LIST)"
              type="button"
              class="header-notice-btn header-notice-unread"
              :title="`有 ${unreadCount} 条执行完成但尚未查看的记录，点击查看`"
              @click="handleMenuSelect('taskList')"
            >
              <i class="el-icon-bell"></i>
              <span>待查看 {{ unreadCount }}</span>
            </button>
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
            @open-task-record="handleOpenTaskRecord"
            @task-notice-changed="pollTaskNotice"
          />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script>
import axios from 'axios'
import DataList from './components/DataList.vue'
import KpiList from './components/KpiList.vue'
import MonacoEditor from './components/MonacoEditor.vue'
import BuildingManagement from './components/BuildingManagement.vue'
import ResMarlConfig from './views/ResMarlConfig.vue'
import AlgorithmParamConfig from './views/AlgorithmParamConfig.vue'
import HomePage from './views/HomePage.vue'
import RecDashboard from './views/RecDashboard.vue'
import ForecastMape from './views/ForecastMape.vue'
import ResidualDeltaEle from './views/ResidualDeltaEle.vue'
import AlphaSweep from './views/AlphaSweep.vue'
import KpisAnalysis from './views/KpisAnalysis.vue'
import SchemaPage from './views/SchemaPage.vue'
import LoginPage from './views/LoginPage.vue'
import UserManagement from './views/UserManagement.vue'
import TaskList from './views/TaskList.vue'
import { PERMS, MENU_PERM_MAP, userHasPermission, firstAllowedMenu } from './utils/permissions'

const SIDEBAR_COLLAPSED_KEY = 'citylearn-sidebar-collapsed'

/**
 * 「CHESCA-ResMARL 配置」页（views/ResMarlConfig.vue）的显示开关。
 *
 * 2026-10-08 按使用者要求**隐藏**：这些参数（α / 残差动作掩码 / 模型路径 …）现在都在
 * 代码编辑器与任务管理页的「配置」弹窗里按任务设置，不需要再留一个全局配置页。
 * 页面组件、路由分支与后端接口都**原样保留**（一行没删）⇒ 把这里改成 true 即可恢复。
 */
const SHOW_RES_MARL_CONFIG_MENU = false

export default {
  name: 'App',
  components: {
    DataList,
    KpiList,
    MonacoEditor,
    BuildingManagement,
    ResMarlConfig,
    AlgorithmParamConfig,
    HomePage,
    RecDashboard,
    ForecastMape,
    ResidualDeltaEle,
    AlphaSweep,
    KpisAnalysis,
    SchemaPage,
    LoginPage,
    UserManagement,
    TaskList
  },
  provide() {
    return {
      hasPermission: (code) => this.hasPermission(code)
    }
  },
  data() {
    return {
      PERMS,
      /** 见文件顶部的 SHOW_RES_MARL_CONFIG_MENU：CHESCA-ResMARL 配置页入口开关 */
      SHOW_RES_MARL_CONFIG_MENU,
      authChecked: false,
      currentUser: null,
      activeMenu: 'home',
      currentComponent: 'HomePage',
      sidebarCollapsed: false,
      showAnalysisMenus: false,
      /** 全局「运行中任务」列表（轮询 /getPyTaskNoticeSummary），任何页面都可见 */
      runningTasks: [],
      /** 执行完但未被查看（未读）的记录数 */
      unreadCount: 0,
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
    this.fetchCurrentUser()
    window.addEventListener('citylearn-auth-required', this.onAuthRequired)
    // 全局轮询任务通知汇总：任何页面都能看到运行中/待查看数量与完成提示
    this.runningPollTimer = setInterval(this.pollTaskNotice, 5000)
  },
  beforeDestroy() {
    window.removeEventListener('citylearn-auth-required', this.onAuthRequired)
    if (this.runningPollTimer) {
      clearInterval(this.runningPollTimer)
      this.runningPollTimer = null
    }
  },
  methods: {
    hasPermission(code) {
      return userHasPermission(this.currentUser, code)
    },
    navigateToAllowed(preferred) {
      let target = preferred
      if (target === 'userManagement') {
        if (!this.isSuperAdmin) target = null
      } else if (target && MENU_PERM_MAP[target] && !this.hasPermission(MENU_PERM_MAP[target])) {
        target = null
      }
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
        const res = await axios.get('/api/web/auth/current')
        if (res.data && res.data.code === 0 && res.data.data) {
          this.currentUser = res.data.data
          this.$nextTick(() => this.navigateToAllowed(this.activeMenu || 'home'))
        } else {
          this.currentUser = null
        }
      } catch (e) {
        this.currentUser = null
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

    /**
     * 轮询全局任务通知汇总：运行中任务列表 + 执行完未读数量。
     * 未登录 / 后端不可用时静默跳过（后者在后端重启期间会连续失败，恢复后自动续上）。
     */
    async pollTaskNotice() {
      if (!this.currentUser) {
        return
      }
      try {
        const res = await axios.get('/api/web/basedata/getPyTaskNoticeSummary')
        if (!res.data || res.data.code !== 0) {
          return
        }
        const summary = res.data.data || {}
        const running = summary.runningTasks || []
        this.notifyFinishedTasks(running)
        this.runningTasks = running
        this.unreadCount = Number(summary.unreadCount) || 0
      } catch (e) {
        // 静默：后端重启期间会连续失败，恢复后自动续上
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
        const res = await axios.get('/api/web/basedata/getPyTaskResult', {
          params: { taskId: item.taskId }
        })
        const task = res.data && res.data.data
        if (task && task.statusDesc) {
          statusDesc = task.statusDesc
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
      try {
        await axios.post('/api/web/auth/logout')
      } catch (e) {
        /* ignore */
      }
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
      if (index === 'userManagement') {
        if (!this.isSuperAdmin) {
          this.$message.warning('无权限访问用户管理')
          return
        }
      } else if (index === 'resMarlConfig' && !SHOW_RES_MARL_CONFIG_MENU) {
        // 菜单里已经看不到它；这里再拦一道，避免别处误调 navigate 到已隐藏的页面
        this.$message.warning('「CHESCA-ResMARL 配置」页已隐藏')
        return
      } else if (MENU_PERM_MAP[index] && !this.hasPermission(MENU_PERM_MAP[index])) {
        this.$message.warning('无权限访问该菜单')
        return
      }
      const map = {
        home: 'HomePage',
        recDashboard: 'RecDashboard',
        forecastMape: 'ForecastMape',
        residualDeltaEle: 'ResidualDeltaEle',
        alphaSweep: 'AlphaSweep',
        kpisAnalysis: 'KpisAnalysis',
        schemaPage: 'SchemaPage',
        dataList: 'DataList',
        kpiList: 'KpiList',
        codeEditor: 'MonacoEditor',
        taskList: 'TaskList',
        buildingManagement: 'BuildingManagement',
        resMarlConfig: 'ResMarlConfig',
        algorithmParam: 'AlgorithmParamConfig',
        userManagement: 'UserManagement'
      }
      this.activeMenu = index
      this.currentComponent = map[index] || 'HomePage'
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
  letter-spacing: 0.02em;
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
  letter-spacing: 0.04em;
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
  background: #f5222d;
  color: #ffffff;
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
