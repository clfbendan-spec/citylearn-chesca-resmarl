<template>
  <div class="rec-dashboard ha-page" :class="{ 'has-energy-bar': showEnergyBar }">
    <div class="page-header">
      <div>
        <h1 class="page-title">模型优选</h1>
        <p class="ha-muted">能源流向 · KPI · 决策轨迹</p>
      </div>
      <div class="ha-toolbar toolbar">
        <el-button
          type="primary"
          icon="el-icon-refresh"
          :loading="loadingList"
          @click="loadShowSimulations"
        >
          加载展示模型
        </el-button>
        <el-button
          v-if="selectedSimulations.length"
          :type="configSidebarCollapsed ? 'default' : 'warning'"
          icon="el-icon-notebook-2"
          @click="configSidebarCollapsed = !configSidebarCollapsed"
        >
          {{ configSidebarCollapsed ? '展开任务配置' : '收起任务配置' }}
        </el-button>
      </div>
    </div>

    <select-compare-model-modal
      v-model="showSelect"
      :simulation-list="simulationFolders"
      @confirm="onSimulationsSelected"
      @cancel="goHome"
    />

    <div class="dashboard-body" :class="{ 'with-sidebar': selectedSimulations.length }">
      <div class="dashboard-main">
        <el-tabs v-if="selectedSimulations.length" v-model="activeTab" type="border-card" class="mt-16">
          <el-tab-pane
            v-for="sim in selectedSimulationsSorted"
            :key="sim"
            :label="tabLabel(sim)"
            :name="sim"
          >
            <el-row :gutter="16">
              <el-col :span="6" v-if="false">
                <simulation-data-tree
                  v-if="filteredData(sim)"
                  :folder-data="filteredData(sim)"
                  :selected-episode="episodeBySim[sim] || episodesBySim[sim][0]"
                  @graph="(p) => setGraph(sim, p)"
                  @equipment="(p) => setEquipment(sim, p)"
                />
              </el-col>
              <el-col :span="24">
                <energy-distribution-panel
                  v-if="filteredData(sim)"
                  :folder-data="filteredData(sim)"
                  :sim-name="sim"
                  :external-days="energyDays"
                  :external-buildings="energyBuildings"
                  :external-scope="energyScope"
                  :external-selected-day="energyExternalSelectedDay"
                  :external-aggregate-mode="energyAggregateMode"
                  :external-period-key="energyPeriodKey"
                  hide-scope-select
                  hide-day-controls
                  prefer-latest-day
                  class="energy-dist-above"
                  @node-click="(p) => openEnergyNodeMoreInfo(sim, p)"
                />
                <el-card v-if="graphBySim[sim]" shadow="never" class="mt-12">
                  <simulation-chart-card
                    :title="graphBySim[sim].title"
                    :data="graphBySim[sim].data"
                    :chart-type="graphBySim[sim].chartType"
                  />
                </el-card>
                <el-card v-if="equipmentBySim[sim]" shadow="never" class="mt-12">
                  <simulation-chart-card
                    :title="equipmentBySim[sim].title"
                    :data="equipmentBySim[sim].data"
                    :chart-type="equipmentBySim[sim].chartType"
                  />
                </el-card>
                <!--<el-empty
                  v-if="!graphBySim[sim] && !equipmentBySim[sim]"
                  description="Select an item from the tree"
                />-->
              </el-col>
            </el-row>
          </el-tab-pane>
        </el-tabs>

        <kpi-analysis-panel
          v-if="selectedSimulations.length"
          :active-sim="activeTab"
          :parsed-kpis="parsedKpis"
          :selected-simulations="selectedSimulationsSorted"
          :resmarl-by-sim="resmarlBySim"
        />

        <chesca-trace-panel
          v-if="selectedSimulations.length"
          :active-sim="activeTab"
          :parsed-trace="parsedTrace"
          :decision-trace-by-sim="decisionTraceBySim"
          :resmarl-by-sim="resmarlBySim"
        />
      </div>

      <task-config-sidebar
        v-if="selectedSimulations.length"
        :config="agentConfigBySim[activeTab] || null"
        :sim-name="activeTab"
        :collapsed.sync="configSidebarCollapsed"
      />
    </div>

    <energy-home-more-info-dialog
      :visible.sync="energyDialogVisible"
      :focus="energyDialogFocus"
      :day="energyDialogDay"
      :scope="energyDialogScope"
      :period-label="energyDialogPeriodLabel"
      :grain="energyDialogGrain"
      :local-points="energyDialogPoints"
      :pricing-points="energyDialogPricingPoints"
    />

    <ha-energy-period-selector
      v-if="showEnergyBar"
      v-model="energySelectedDay"
      :days="energyDays"
      :scope-options="energyScopeOptions"
      :scope.sync="energyScope"
      show-aggregate-mode
      :aggregate-mode.sync="energyAggregateMode"
      :periods="energyPeriods"
      :period-key.sync="energyPeriodKey"
      @change="onEnergyDayChange"
      @aggregate-change="onEnergyAggregateChange"
    />
  </div>
</template>

<script>
import axios from 'axios'
import Papa from 'papaparse'
import SelectCompareModelModal from '@/components/shared/SelectCompareModelModal.vue'
import SimulationDataTree from '@/components/dashboard/SimulationDataTree.vue'
import SimulationChartCard from '@/components/charts/SimulationChartCard.vue'
import EnergyDistributionPanel from '@/components/dashboard/EnergyDistributionPanel.vue'
import EnergyHomeMoreInfoDialog from '@/components/home/EnergyHomeMoreInfoDialog.vue'
import HaEnergyPeriodSelector from '@/components/home/HaEnergyPeriodSelector.vue'
import KpiAnalysisPanel from '@/components/dashboard/KpiAnalysisPanel.vue'
import ChescaTracePanel from '@/components/dashboard/ChescaTracePanel.vue'
import TaskConfigSidebar from '@/components/dashboard/TaskConfigSidebar.vue'
import {
  buildEnergyFlowSeriesPoints,
  listEnergyFlowMeta,
  listEnergyFlowPeriods
} from '@/utils/energyFlowAggregate'
import { buildPricingSeriesPoints } from '@/utils/homePricing'
import { normalizeKpiRows, parseKpiCsvText } from '@/utils/kpiCsvParse'
import { parseChescaTraceCsv } from '@/utils/chescaTraceParse'
import { resolveDecisionTrace } from '@/utils/decisionTrace'
import { buildResmarlSummaryFromConfig, formatResmarlLabel, parseAgentConfigJson } from '@/utils/resmarlLabels'

export default {
  name: 'RecDashboard',
  components: {
    SelectCompareModelModal,
    SimulationDataTree,
    SimulationChartCard,
    EnergyDistributionPanel,
    EnergyHomeMoreInfoDialog,
    HaEnergyPeriodSelector,
    KpiAnalysisPanel,
    ChescaTracePanel,
    TaskConfigSidebar
  },
  data() {
    return {
      loadingList: false,
      loadingDetail: false,
      showSelect: false,
      simulationFolders: [],
      /** groupName -> { taskId, pyId } */
      simulationMeta: {},
      selectedSimulations: [],
      parsedSimulations: {},
      parsedKpis: {},
      parsedTrace: {},
      decisionTraceBySim: {},
      resmarlBySim: {},
      agentConfigBySim: {},
      configSidebarCollapsed: true,
      episodesBySim: {},
      episodeBySim: {},
      activeTab: '',
      graphBySim: {},
      equipmentBySim: {},
      energyDialogVisible: false,
      energyDialogFocus: 'home',
      energyDialogDay: '',
      energyDialogScope: 'community',
      energyDialogPeriodLabel: '',
      energyDialogGrain: 'hour',
      energyDialogPoints: [],
      energyDialogPricingPoints: [],
      energyScope: 'community',
      energyAggregateMode: 'day',
      energySelectedDay: '',
      energyPeriodKey: ''
    }
  },
  computed: {
    selectedSimulationsSorted() {
      // 保持选择顺序：评估模型 → 对照组
      return [...this.selectedSimulations]
    },
    simsWithEnergy() {
      return this.selectedSimulations.filter((sim) => !!this.filteredData(sim))
    },
    showEnergyBar() {
      return this.simsWithEnergy.length > 0
    },
    energyDays() {
      const set = new Set()
      this.simsWithEnergy.forEach((sim) => {
        listEnergyFlowMeta(this.filteredData(sim)).days.forEach((d) => set.add(d))
      })
      return [...set].sort()
    },
    energyBuildings() {
      const set = new Set()
      this.simsWithEnergy.forEach((sim) => {
        listEnergyFlowMeta(this.filteredData(sim)).buildings.forEach((b) => set.add(b))
      })
      return [...set].sort((a, b) => {
        const na = parseInt((a.match(/\d+/) || ['0'])[0], 10)
        const nb = parseInt((b.match(/\d+/) || ['0'])[0], 10)
        return na - nb
      })
    },
    energyScopeOptions() {
      return [
        { value: 'community', label: '社区合计' },
        ...this.energyBuildings.map((b) => {
          const n = (b.match(/\d+/) || [])[0]
          return { value: b, label: n ? `建筑${n}` : b }
        })
      ]
    },
    energyPeriods() {
      return listEnergyFlowPeriods(this.energyDays, this.energyAggregateMode)
    },
    energyExternalSelectedDay() {
      return this.energyAggregateMode === 'day' ? this.energySelectedDay : null
    },
    tabLabel() {
      return (sim) => {
        const role =
          this.selectedSimulations[0] === sim
            ? '评估模型'
            : this.selectedSimulations[1] === sim
              ? '对照组'
              : ''
        const tag = formatResmarlLabel(this.resmarlBySim[sim])
        const name = tag ? `${sim} · ${tag}` : sim
        return role ? `${role} · ${name}` : name
      }
    }
  },
  watch: {
    energyDays: {
      immediate: true,
      handler(days) {
        this.syncEnergySelection(days)
      }
    },
    energyAggregateMode() {
      this.syncEnergyPeriod()
    },
    energyBuildings(list) {
      if (this.energyScope !== 'community' && !(list || []).includes(this.energyScope)) {
        this.energyScope = 'community'
      }
    }
  },
  mounted() {
    this.loadShowSimulations()
  },
  methods: {
    goHome() {
      this.$emit('navigate-home')
    },

    syncEnergySelection(days) {
      const list = days || this.energyDays || []
      if (!list.length) {
        this.energySelectedDay = ''
        this.energyPeriodKey = ''
        return
      }
      if (!list.includes(this.energySelectedDay)) {
        this.energySelectedDay = list[list.length - 1]
      }
      this.syncEnergyPeriod()
    },

    syncEnergyPeriod() {
      const periods = this.energyPeriods || []
      if (!periods.length) {
        this.energyPeriodKey = ''
        return
      }
      if (this.energyAggregateMode === 'day') {
        const day = periods.some((p) => p.key === this.energySelectedDay)
          ? this.energySelectedDay
          : periods[periods.length - 1].key
        this.energySelectedDay = day
        this.energyPeriodKey = day
        return
      }
      if (periods.some((p) => p.key === this.energyPeriodKey)) return
      const containing = this.energySelectedDay
        ? periods.find((p) => (p.days || []).includes(this.energySelectedDay))
        : null
      this.energyPeriodKey = containing
        ? containing.key
        : periods[periods.length - 1].key
    },

    onEnergyDayChange(day) {
      this.energySelectedDay = day
      if (this.energyAggregateMode === 'day') {
        this.energyPeriodKey = day
      }
    },

    onEnergyAggregateChange() {
      this.$nextTick(() => this.syncEnergyPeriod())
    },

    isApiSuccess(response) {
      return response && response.data && Number(response.data.code) === 0
    },

    storeAgentConfig(sim, detail) {
      const cfg = parseAgentConfigJson(detail && detail.agentConfigJson)
      this.$set(this.agentConfigBySim, sim, cfg)
      const resmarl =
        (detail && detail.resmarlSummary) || buildResmarlSummaryFromConfig(cfg)
      this.$set(this.resmarlBySim, sim, resmarl)
    },

    async loadShowSimulations() {
      this.loadingList = true
      try {
        const response = await axios.get('/api/web/basedata/getDashboardSimulations')
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '加载展示模型失败')
          return
        }
        const list = response.data.data || []
        this.simulationMeta = {}
        this.simulationFolders = list.map((item) => {
          this.simulationMeta[item.groupName] = {
            taskId: item.taskId,
            pyId: item.pyId
          }
          return item.groupName
        })
        this.parsedSimulations = {}
        this.parsedKpis = {}
        this.parsedTrace = {}
        this.decisionTraceBySim = {}
        this.resmarlBySim = {}
        this.agentConfigBySim = {}
        this.episodesBySim = {}
        this.episodeBySim = {}
        this.selectedSimulations = []
        this.graphBySim = {}
        this.equipmentBySim = {}
        this.activeTab = ''

        if (!this.simulationFolders.length) {
          this.$message.warning('暂无展示数据：请先在代码编辑器「记录」页将执行完成的记录设为【展示】')
        } else {
          this.$message.success(`已加载 ${this.simulationFolders.length} 个展示模型`)
          this.showSelect = true
        }
      } catch (error) {
        console.error('加载展示模型失败:', error)
        this.$message.error('加载展示模型失败')
      } finally {
        this.loadingList = false
      }
    },

    parseCsvText(text) {
      if (!text || !text.trim()) {
        return []
      }
      const result = Papa.parse(text.trim(), { header: true, skipEmptyLines: true })
      return result.data || []
    },

    parseSimulationDataFromFiles(dataFiles) {
      const parsed = {}
      const episodes = new Set()
      Object.entries(dataFiles || {}).forEach(([fileName, csvText]) => {
        const cleaned = fileName.replace('exported_data_', '').replace(/\.[^/.]+$/, '')
        const ep = cleaned.match(/_?(ep\d+)/i)
        if (ep) {
          episodes.add(ep[1])
        }
        parsed[cleaned] = this.parseCsvText(csvText)
      })
      return {
        parsed,
        episodes: [...episodes].sort()
      }
    },

    async loadKpiRowsFromDb(pyId) {
      try {
        const response = await axios.get('/api/web/basedata/getPyFileKpiRows', {
          params: { pyId }
        })
        if (!this.isApiSuccess(response)) {
          return []
        }
        return normalizeKpiRows(response.data.data)
      } catch (error) {
        console.error('从数据库加载 KPI 失败:', error)
        return []
      }
    },

    async loadSimulationDetail(groupName) {
      const meta = this.simulationMeta[groupName]
      if (!meta || !meta.taskId) {
        return
      }
      const response = await axios.get('/api/web/basedata/getDashboardSimulationDetail', {
        params: { taskId: meta.taskId }
      })
      if (!this.isApiSuccess(response) || !response.data.data) {
        throw new Error(response.data.message || '加载仿真详情失败')
      }
      return response.data.data
    },

    async onSimulationsSelected(list) {
      this.selectedSimulations = list
      this.activeTab = [...list].sort()[0]
      this.loadingDetail = true
      const loading = this.$loading({
        lock: true,
        text: '正在加载仿真数据…',
        spinner: 'el-icon-loading'
      })
      try {
        for (const sim of list) {
          const meta = this.simulationMeta[sim]
          if (!this.parsedSimulations[sim]) {
            const detail = await this.loadSimulationDetail(sim)
            const { parsed, episodes } = this.parseSimulationDataFromFiles(detail.dataFiles)
            this.$set(this.parsedSimulations, sim, parsed)
            this.$set(this.episodesBySim, sim, episodes.length ? episodes : ['ep0'])
            this.$set(this.episodeBySim, sim, episodes[0] || 'ep0')

            let kpiRows = normalizeKpiRows(detail.kpiRows)
            if (kpiRows.length < 2 && detail.kpisCsv) {
              const fromCsv = parseKpiCsvText(detail.kpisCsv)
              if (fromCsv.length > kpiRows.length) {
                kpiRows = fromCsv
              }
            }
            if (kpiRows.length < 2 && meta && meta.pyId) {
              const dbRows = await this.loadKpiRowsFromDb(meta.pyId)
              if (dbRows.length > kpiRows.length) {
                kpiRows = dbRows
              }
            }
            if (kpiRows.length) {
              this.$set(this.parsedKpis, sim, kpiRows.slice())
            } else {
              this.$message.warning(`${sim}：未解析到 KPI 数据`)
            }

            const traceRows = parseChescaTraceCsv(detail.chescaTraceCsv)
            if (traceRows.length) {
              this.$set(this.parsedTrace, sim, traceRows)
            }
            const decisionTrace = resolveDecisionTrace({
              decisionTraceJson: detail.decisionTraceJson,
              chescaTraceCsv: detail.chescaTraceCsv
            })
            if (decisionTrace) {
              this.$set(this.decisionTraceBySim, sim, decisionTrace)
            }
            this.storeAgentConfig(sim, detail)
          } else if (!this.parsedKpis[sim] || this.parsedKpis[sim].length < 2) {
            const detail = await this.loadSimulationDetail(sim)
            let kpiRows = normalizeKpiRows(detail.kpiRows)
            if (kpiRows.length < 2 && detail.kpisCsv) {
              kpiRows = parseKpiCsvText(detail.kpisCsv)
            }
            if (kpiRows.length < 2 && meta && meta.pyId) {
              kpiRows = await this.loadKpiRowsFromDb(meta.pyId)
            }
            if (kpiRows.length) {
              this.$set(this.parsedKpis, sim, kpiRows.slice())
            }
            if (!this.agentConfigBySim[sim]) {
              this.storeAgentConfig(sim, detail)
            }
          }
          if (
            !this.parsedTrace[sim] ||
            !this.decisionTraceBySim[sim] ||
            !this.resmarlBySim[sim] ||
            !this.agentConfigBySim[sim]
          ) {
            const detail = await this.loadSimulationDetail(sim)
            if (!this.parsedTrace[sim]) {
              const traceRows = parseChescaTraceCsv(detail.chescaTraceCsv)
              if (traceRows.length) {
                this.$set(this.parsedTrace, sim, traceRows)
              }
            }
            if (!this.decisionTraceBySim[sim]) {
              const decisionTrace = resolveDecisionTrace({
                decisionTraceJson: detail.decisionTraceJson,
                chescaTraceCsv: detail.chescaTraceCsv
              })
              if (decisionTrace) {
                this.$set(this.decisionTraceBySim, sim, decisionTrace)
              }
            }
            if (!this.agentConfigBySim[sim] || !this.resmarlBySim[sim]) {
              this.storeAgentConfig(sim, detail)
            }
          }
        }
      } catch (error) {
        console.error('加载仿真详情失败:', error)
        this.$message.error(error.message || '加载仿真详情失败')
      } finally {
        loading.close()
        this.loadingDetail = false
      }
    },

    filteredData(sim) {
      const all = this.parsedSimulations[sim]
      if (!all) {
        return null
      }
      const ep = this.episodeBySim[sim] || this.episodesBySim[sim]?.[0] || 'ep0'
      const out = {}
      Object.entries(all).forEach(([k, v]) => {
        if (k.includes(ep)) {
          out[k] = v
        }
      })
      return out
    },

    setGraph(sim, payload) {
      this.$set(this.graphBySim, sim, payload)
      this.$set(this.equipmentBySim, sim, null)
    },

    setEquipment(sim, payload) {
      this.$set(this.equipmentBySim, sim, payload)
      this.$set(this.graphBySim, sim, null)
    },

    async openEnergyNodeMoreInfo(sim, payload) {
      const folderData = this.filteredData(sim)
      if (!folderData || !payload) return
      const focus = ['home', 'solar', 'grid', 'battery', 'load'].includes(payload.focus)
        ? payload.focus
        : 'home'
      const periodDays = payload.periodDays || (payload.day ? [payload.day] : [])
      if (!periodDays.length) return
      const mode = payload.aggregateMode || 'day'
      const scope = payload.scope || 'community'
      const { points, grain } = buildEnergyFlowSeriesPoints(
        folderData,
        periodDays,
        mode,
        scope
      )
      this.energyDialogFocus = focus
      this.energyDialogDay = payload.day || periodDays[0]
      this.energyDialogScope = scope
      this.energyDialogPeriodLabel = payload.periodLabel || ''
      this.energyDialogGrain = grain
      this.energyDialogPoints = points
      this.energyDialogPricingPoints = []
      if (focus === 'grid') {
        try {
          const pricing = await buildPricingSeriesPoints(folderData, periodDays, mode)
          this.energyDialogPricingPoints = pricing.points || []
        } catch (e) {
          console.warn('加载电价曲线失败', e)
          this.energyDialogPricingPoints = []
        }
      }
      // 先准备好电价数据再打开，避免第二次打开时先空数组触发 dispose
      this.energyDialogVisible = true
    }
  }
}
</script>

<style scoped>
.rec-dashboard {
  min-height: 100%;
  box-sizing: border-box;
  padding-bottom: 0;
}
.rec-dashboard.has-energy-bar {
  padding-bottom: 72px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 400;
  line-height: 1.25;
  color: var(--primary-text-color);
}
.toolbar {
  margin-bottom: 0;
}
.rec-dashboard :deep(.el-tabs__content) {
  overflow: visible;
}
.rec-dashboard :deep(.el-tab-pane) {
  overflow: visible;
}
.dashboard-body {
  display: block;
}
.dashboard-body.with-sidebar {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}
.dashboard-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.mt-16 { margin-top: 0; }
.mt-12 { margin-top: var(--space-3); }
.energy-dist-above + .el-card,
.energy-dist-above + .el-empty {
  margin-top: var(--space-3);
}
</style>
