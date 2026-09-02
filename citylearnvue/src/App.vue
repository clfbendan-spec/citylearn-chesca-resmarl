<template>
  <div id="app">
    <el-container style="height: 100vh;">
      <el-aside :width="asideWidth" class="app-aside">
        <el-menu
          :default-active="activeMenu"
          :collapse="sidebarCollapsed"
          :collapse-transition="false"
          background-color="#545c64"
          text-color="#fff"
          active-text-color="#ffd04b"
          class="app-menu"
          @select="handleMenuSelect"
        >
          <el-menu-item-group title="建筑群节能控制策略系统">
            <el-menu-item index="recDashboard">
              <i class="el-icon-data-line"></i>
              <span slot="title">仿真仪表盘</span>
            </el-menu-item>
            <el-menu-item index="dataList">
              <i class="el-icon-menu"></i>
              <span slot="title">原始数据</span>
            </el-menu-item>
            <el-menu-item index="codeEditor">
              <i class="el-icon-edit"></i>
              <span slot="title">代码编辑器</span>
            </el-menu-item>
            <el-menu-item index="buildingManagement">
              <i class="el-icon-s-home"></i>
              <span slot="title">建筑管理</span>
            </el-menu-item>
            <el-menu-item index="batteryMinSocConfig">
              <i class="el-icon-setting"></i>
              <span slot="title">小时电池下限配置</span>
            </el-menu-item>
            <el-menu-item index="resMarlConfig">
              <i class="el-icon-s-operation"></i>
              <span slot="title">CHESCA-ResMARL</span>
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
            <!--<el-menu-item index="kpisAnalysis">
              <i class="el-icon-s-data"></i>
              <span slot="title">KPI 分析</span>
            </el-menu-item>
            <el-menu-item index="schemaPage">
              <i class="el-icon-share"></i>
              <span slot="title">Schema 构建</span>
            </el-menu-item>-->
            
          </el-menu-item-group>
          <!--<el-menu-item-group title="后端数据">
            
           <el-menu-item index="kpiList">
              <i class="el-icon-document"></i>
              <span slot="title">指标数据</span>
            </el-menu-item>
            
          </el-menu-item-group>-->
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

      <el-main class="app-main">
        <component :is="currentComponent" />
      </el-main>
    </el-container>
  </div>
</template>

<script>
import DataList from './components/DataList.vue'
import KpiList from './components/KpiList.vue'
import MonacoEditor from './components/MonacoEditor.vue'
import BuildingManagement from './components/BuildingManagement.vue'
import BatteryMinSocConfig from './views/BatteryMinSocConfig.vue'
import ResMarlConfig from './views/ResMarlConfig.vue'
import RecDashboard from './views/RecDashboard.vue'
import ForecastMape from './views/ForecastMape.vue'
import ResidualDeltaEle from './views/ResidualDeltaEle.vue'
import AlphaSweep from './views/AlphaSweep.vue'
import KpisAnalysis from './views/KpisAnalysis.vue'
import SchemaPage from './views/SchemaPage.vue'

const SIDEBAR_COLLAPSED_KEY = 'citylearn-sidebar-collapsed'

export default {
  name: 'App',
  components: {
    DataList,
    KpiList,
    MonacoEditor,
    BuildingManagement,
    BatteryMinSocConfig,
    ResMarlConfig,
    RecDashboard,
    ForecastMape,
    ResidualDeltaEle,
    AlphaSweep,
    KpisAnalysis,
    SchemaPage
  },
  data() {
    return {
      activeMenu: 'recDashboard',
      currentComponent: 'RecDashboard',
      sidebarCollapsed: false,
      // 临时隐藏：预测误差 MAPE / 残差 ΔELE / α–KPI 扫描
      showAnalysisMenus: false
    }
  },
  computed: {
    asideWidth() {
      return this.sidebarCollapsed ? '64px' : '220px'
    }
  },
  created() {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    if (saved === '1') {
      this.sidebarCollapsed = true
    }
  },
  methods: {
    handleMenuSelect(index) {
      const map = {
        recDashboard: 'RecDashboard',
        forecastMape: 'ForecastMape',
        residualDeltaEle: 'ResidualDeltaEle',
        alphaSweep: 'AlphaSweep',
        kpisAnalysis: 'KpisAnalysis',
        schemaPage: 'SchemaPage',
        dataList: 'DataList',
        kpiList: 'KpiList',
        codeEditor: 'MonacoEditor',
        buildingManagement: 'BuildingManagement',
        batteryMinSocConfig: 'BatteryMinSocConfig',
        resMarlConfig: 'ResMarlConfig'
      }
      this.activeMenu = index
      this.currentComponent = map[index] || 'RecDashboard'
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
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
}

.app-aside {
  background-color: #545c64;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.28s ease;
}

.app-menu {
  flex: 1;
  border-right: none;
  overflow-x: hidden;
  overflow-y: auto;
}

.app-menu:not(.el-menu--collapse) {
  width: 220px;
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
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: #434a50;
  color: #ddd;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s, color 0.2s;
}

.sidebar-toggle:hover {
  background: #3a4046;
  color: #ffd04b;
}

.sidebar-toggle i {
  font-size: 18px;
}

.el-menu {
  border-right: none;
}

.el-menu-item-group__title {
  color: #bbb !important;
  padding-top: 12px !important;
}

.app-main {
  height: 100%;
  padding: 0 !important;
  overflow-x: hidden;
  overflow-y: auto;
}
</style>
