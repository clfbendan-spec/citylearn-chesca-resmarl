<template>
  <div class="kpis-analysis">
    <div class="toolbar">
      <el-button type="primary" icon="el-icon-upload2" @click="triggerUpload">上传仿真数据</el-button>
      <el-button v-if="simulationFolders.length" type="success" @click="showSelect = true">选择仿真</el-button>
      <input ref="folderInput" type="file" webkitdirectory multiple style="display: none" @change="onFolderUpload" />
    </div>

    <select-simulation-modal
      v-model="showSelect"
      :simulation-list="simulationFolders"
      @confirm="onSimulationsSelected"
    />

    <el-tabs v-if="selectedSimulations.length" v-model="activeTab" type="border-card" class="mt-16">
      <el-tab-pane
        v-for="sim in selectedSimulationsSorted"
        :key="sim"
        :label="sim"
        :name="sim"
      />
    </el-tabs>

    <kpi-analysis-panel
      v-if="selectedSimulations.length"
      :active-sim="activeTab"
      :parsed-kpis="parsedKpis"
      :selected-simulations="selectedSimulationsSorted"
    />
  </div>
</template>

<script>
import SelectSimulationModal from '@/components/shared/SelectSimulationModal.vue'
import KpiAnalysisPanel from '@/components/dashboard/KpiAnalysisPanel.vue'
import { parseFolderUpload, parseKpisFile } from '@/utils/simulationFolder'

export default {
  name: 'KpisAnalysis',
  components: { SelectSimulationModal, KpiAnalysisPanel },
  data() {
    return {
      showSelect: false,
      simulationFolders: [],
      fileMapByFolder: {},
      selectedSimulations: [],
      parsedKpis: {},
      activeTab: ''
    }
  },
  computed: {
    selectedSimulationsSorted() {
      return [...this.selectedSimulations].sort()
    }
  },
  methods: {
    triggerUpload() {
      this.$refs.folderInput.click()
    },
    onFolderUpload(e) {
      const { simulationFolders, fileMapByFolder } = parseFolderUpload(e.target.files)
      this.simulationFolders = simulationFolders
      this.fileMapByFolder = fileMapByFolder
      this.parsedKpis = {}
      e.target.value = ''
    },
    async onSimulationsSelected(list) {
      this.selectedSimulations = list
      this.activeTab = [...list].sort()[0]
      for (const sim of list) {
        if (this.parsedKpis[sim]) continue
        const file = this.fileMapByFolder[sim]?.['exported_kpis.csv']
        if (file) {
          const data = await parseKpisFile(file)
          this.$set(this.parsedKpis, sim, data)
        }
      }
    }
  }
}
</script>

<style scoped>
.kpis-analysis { padding: 8px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.mt-16 { margin-top: 16px; }
</style>
