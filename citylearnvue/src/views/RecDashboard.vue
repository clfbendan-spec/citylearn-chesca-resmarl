<template>
  <div class="rec-dashboard">
    <div class="toolbar">
      <el-button
        type="primary"
        icon="el-icon-refresh"
        :loading="loadingList"
        @click="loadShowSimulations"
      >
        加载展示数据
      </el-button>
      <el-button
        v-if="simulationFolders.length"
        type="success"
        :disabled="loadingList"
        @click="showSelect = true"
      >
        选择分组
      </el-button>
      <el-button
        v-if="selectedSimulations.length"
        :type="configSidebarCollapsed ? 'default' : 'warning'"
        icon="el-icon-notebook-2"
        @click="configSidebarCollapsed = !configSidebarCollapsed"
      >
        {{ configSidebarCollapsed ? '展开任务配置' : '收起任务配置' }}
      </el-button>
      <span v-if="simulationFolders.length" class="hint" />
    </div>

    <select-simulation-modal
      v-model="showSelect"
      :simulation-list="simulationFolders"
      @confirm="onSimulationsSelected"
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
              <el-col :span="6">
                <simulation-data-tree
                  v-if="filteredData(sim)"
                  :folder-data="filteredData(sim)"
                  :selected-episode="episodeBySim[sim] || episodesBySim[sim][0]"
                  @graph="(p) => setGraph(sim, p)"
                  @equipment="(p) => setEquipment(sim, p)"
                />
              </el-col>
              <el-col :span="18">
                <el-card v-if="graphBySim[sim]" shadow="never">
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
                <el-empty
                  v-if="!graphBySim[sim] && !equipmentBySim[sim]"
                  description="Select an item from the tree"
                />
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
  </div>
</template>

<script>
import axios from 'axios'
import Papa from 'papaparse'
import SelectSimulationModal from '@/components/shared/SelectSimulationModal.vue'
import SimulationDataTree from '@/components/dashboard/SimulationDataTree.vue'
import SimulationChartCard from '@/components/charts/SimulationChartCard.vue'
import KpiAnalysisPanel from '@/components/dashboard/KpiAnalysisPanel.vue'
import ChescaTracePanel from '@/components/dashboard/ChescaTracePanel.vue'
import TaskConfigSidebar from '@/components/dashboard/TaskConfigSidebar.vue'
import { normalizeKpiRows, parseKpiCsvText } from '@/utils/kpiCsvParse'
import { parseChescaTraceCsv } from '@/utils/chescaTraceParse'
import { resolveDecisionTrace } from '@/utils/decisionTrace'
import { buildResmarlSummaryFromConfig, formatResmarlLabel, parseAgentConfigJson } from '@/utils/resmarlLabels'

export default {
  name: 'RecDashboard',
  components: {
    SelectSimulationModal,
    SimulationDataTree,
    SimulationChartCard,
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
      configSidebarCollapsed: false,
      episodesBySim: {},
      episodeBySim: {},
      activeTab: '',
      graphBySim: {},
      equipmentBySim: {}
    }
  },
  computed: {
    selectedSimulationsSorted() {
      return [...this.selectedSimulations].sort()
    },
    tabLabel() {
      return (sim) => {
        const tag = formatResmarlLabel(this.resmarlBySim[sim])
        return tag && tag !== '未标注' ? `${sim} · ${tag}` : sim
      }
    }
  },
  mounted() {
    this.loadShowSimulations()
  },
  methods: {
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
          this.$message.error(response.data.message || '加载展示数据失败')
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
          this.$message.success(`已加载 ${this.simulationFolders.length} 个展示分组`)
          this.showSelect = true
        }
      } catch (error) {
        console.error('加载展示数据失败:', error)
        this.$message.error('加载展示数据失败')
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
    }
  }
}
</script>

<style scoped>
.rec-dashboard {
  padding: 8px 8px 32px;
  min-height: 100%;
  box-sizing: border-box;
}
.rec-dashboard :deep(.el-tabs__content) {
  overflow: visible;
}
.rec-dashboard :deep(.el-tab-pane) {
  overflow: visible;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.hint {
  color: #909399;
  font-size: 13px;
}
.dashboard-body {
  display: block;
}
.dashboard-body.with-sidebar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.dashboard-main {
  flex: 1;
  min-width: 0;
}
.mt-16 { margin-top: 16px; }
.mt-12 { margin-top: 12px; }
</style>
