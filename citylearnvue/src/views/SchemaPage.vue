<template>
  <div class="schema-page">
    <div class="toolbar">
      <el-button v-if="!editing" type="primary" @click="editing = true">新建 Schema</el-button>
      <template v-else>
        <el-button type="danger" plain @click="cancelEdit">取消</el-button>
        <el-button type="success" :disabled="!canSave" @click="saveSchema">Save schema.json</el-button>
      </template>
    </div>

    <template v-if="editing">
      <el-card shadow="never" class="section">
        <h3>Dataset info</h3>
        <el-form :model="meta" label-width="140px" size="small">
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="Dataset Name" required>
                <el-input v-model="datasetName" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="Schema Name" required>
                <el-input v-model="siteName" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-card>

      <el-card shadow="never" class="section">
        <h3>基础配置</h3>
        <el-form :model="formData" label-width="200px" size="small">
          <el-row :gutter="12">
            <el-col :span="8"><el-form-item label="random_seed"><el-input-number v-model="formData.random_seed" :min="0" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="root_directory"><el-input v-model="formData.root_directory" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="seconds_per_time_step"><el-input-number v-model="formData.seconds_per_time_step" :min="1" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="simulation_start"><el-input-number v-model="formData.simulation_start_time_step" :min="0" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="simulation_end"><el-input-number v-model="formData.simulation_end_time_step" :min="0" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="episode_time_steps"><el-input-number v-model="formData.episode_time_steps" :min="1" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="period"><el-input-number v-model="formData.period" :min="1" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="date_from"><el-input v-model="formData.date_from" type="datetime-local" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="date_until"><el-input v-model="formData.date_until" type="datetime-local" /></el-form-item></el-col>
          </el-row>
          <el-checkbox v-model="formData.central_agent">central_agent</el-checkbox>
          <el-checkbox v-model="formData.rolling_episode_split">rolling_episode_split</el-checkbox>
          <el-checkbox v-model="formData.random_episode_split">random_episode_split</el-checkbox>
        </el-form>
      </el-card>

      <el-row :gutter="16" class="section">
        <el-col :span="12">
          <el-card shadow="never">
            <h3>Observations</h3>
            <obs-action-selector :options="observations" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <h3>Actions</h3>
            <obs-action-selector :options="actions" :shared="false" />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="section">
        <h3>Agent / Reward (JSON)</h3>
        <el-row :gutter="16">
          <el-col :span="12">
            <p>Agent</p>
            <el-input v-model="agentJson" type="textarea" :rows="6" :placeholder="agentPlaceholder" />
          </el-col>
          <el-col :span="12">
            <p>Reward Function</p>
            <el-input v-model="rewardJson" type="textarea" :rows="6" :placeholder="rewardPlaceholder" />
          </el-col>
        </el-row>
      </el-card>

      <el-card shadow="never" class="section">
        <div class="palette">
          <span>Drag nodes to canvas:</span>
          <el-button
            v-for="t in paletteTypes"
            :key="t.type"
            size="mini"
            draggable
            @dragstart.native="onDragStart($event, t.type)"
          >
            {{ t.label }}
          </el-button>
        </div>
        <div
          class="canvas"
          @dragover.prevent
          @drop="onDrop"
        >
          <div
            v-for="node in nodes"
            :key="node.id"
            class="node"
            :style="{ left: node.x + 'px', top: node.y + 'px' }"
            @mousedown="startDrag(node, $event)"
          >
            <div class="node-title">{{ node.label }} ({{ node.type }})</div>
            <schema-node-form :node="node" />
            <el-select
              v-if="node.type !== 'building' && node.type !== 'ev'"
              v-model="node.buildingId"
              size="mini"
              placeholder="关联建筑"
              clearable
              class="mt-4"
            >
              <el-option
                v-for="b in buildingNodes"
                :key="b.id"
                :label="b.label"
                :value="b.id"
              />
            </el-select>
          </div>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script>
import ObsActionSelector from '@/components/schema/ObsActionSelector.vue'
import SchemaNodeForm from '@/components/schema/SchemaNodeForm.vue'
import { buildSchemaExport } from '@/utils/schemaExport'

const PALETTE = [
  { type: 'building', label: 'Building' },
  { type: 'ev', label: 'EV' },
  { type: 'pv', label: 'PV' },
  { type: 'charger', label: 'Charger' },
  { type: 'cooling_device', label: 'Cooling' },
  { type: 'heating_device', label: 'Heating' },
  { type: 'electrical_storage', label: 'Battery' }
]

export default {
  name: 'SchemaPage',
  components: { ObsActionSelector, SchemaNodeForm },
  data() {
    return {
      editing: false,
      datasetName: '',
      siteName: '',
      formData: {
        random_seed: 2022,
        root_directory: '/',
        central_agent: false,
        simulation_start_time_step: 0,
        simulation_end_time_step: 8759,
        episode_time_steps: 24,
        rolling_episode_split: false,
        random_episode_split: false,
        seconds_per_time_step: 3600,
        period: 60,
        date_from: '2025-07-15T00:00',
        date_until: '2025-07-22T23:59'
      },
      observations: {
        month: { active: false, shared_in_central_agent: false },
        hour: { active: false, shared_in_central_agent: false },
        outdoor_dry_bulb_temperature: { active: false, shared_in_central_agent: false },
        net_electricity_consumption: { active: false, shared_in_central_agent: false },
        electricity_pricing: { active: false, shared_in_central_agent: false },
        electrical_storage_soc: { active: false, shared_in_central_agent: false }
      },
      actions: {
        electrical_storage: { active: false },
        electric_vehicle_storage: { active: false }
      },
      agentJson: '{"type":"citylearn.agents.base.BaselineAgent","attributes":{}}',
      rewardJson: '{"type":"citylearn.reward_function.MARL","attributes":{}}',
      agentPlaceholder: '{"type":"citylearn.agents.base.BaselineAgent","attributes":{}}',
      rewardPlaceholder: '{"type":"citylearn.reward_function.MARL","attributes":{}}',
      nodes: [],
      nodeCounts: { building: 0, ev: 0, pv: 0, charger: 0, cooling_device: 0, heating_device: 0, electrical_storage: 0 },
      dragNode: null,
      dragOffset: { x: 0, y: 0 },
      paletteTypes: PALETTE
    }
  },
  computed: {
    buildingNodes() {
      return this.nodes.filter((n) => n.type === 'building')
    },
    canSave() {
      return Boolean(this.datasetName && this.siteName && this.nodes.some((n) => n.type === 'building'))
    }
  },
  methods: {
    cancelEdit() {
      this.editing = false
    },
    onDragStart(e, type) {
      e.dataTransfer.setData('schema-node-type', type)
    },
    onDrop(e) {
      const type = e.dataTransfer.getData('schema-node-type')
      if (!type) return
      const rect = e.currentTarget.getBoundingClientRect()
      this.addNode(type, e.clientX - rect.left - 80, e.clientY - rect.top - 20)
    },
    addNode(type, x, y) {
      const id = `n${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
      let label = type
      let formData = {}
      if (type === 'building') {
        this.nodeCounts.building += 1
        label = `Building_${this.nodeCounts.building}`
        formData = {
          energy_simulation: `${label}.csv`,
          weather: 'weather.csv',
          carbon_intensity: 'carbon_intensity.csv',
          pricing: 'pricing.csv',
          inactive_observations: [],
          inactive_actions: []
        }
      } else if (type === 'ev') {
        this.nodeCounts.ev += 1
        label = `Electric_Vehicle_${this.nodeCounts.ev}`
        formData = { capacity: 40, nominal_power: 50, initial_soc: 0.25, depth_of_discharge: 0.85 }
      } else {
        this.nodeCounts[type] = (this.nodeCounts[type] || 0) + 1
        label = `${type}_${this.nodeCounts[type]}`
        formData = { selectedType: 'citylearn.energy_model.PV', nominal_power: 5 }
        if (type === 'charger') {
          formData = {
            selectedType: 'citylearn.electric_vehicle_charger.Charger',
            nominal_power: 11,
            efficiency: 0.95,
            charger_type: 0
          }
        }
        if (type === 'electrical_storage') {
          formData = {
            selectedType: 'citylearn.energy_model.Battery',
            capacity: 6.4,
            nominal_power: 5
          }
        }
      }
      this.nodes.push({ id, type, label, x, y, formData, buildingId: null })
    },
    startDrag(node, e) {
      if (e.target.closest('input,textarea,select,button')) return
      this.dragNode = node
      this.dragOffset = { x: e.clientX - node.x, y: e.clientY - node.y }
      const onMove = (ev) => {
        if (!this.dragNode) return
        this.dragNode.x = ev.clientX - this.dragOffset.x
        this.dragNode.y = ev.clientY - this.dragOffset.y
      }
      const onUp = () => {
        this.dragNode = null
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    saveSchema() {
      let agentData
      let rewardFunctionData
      try {
        agentData = JSON.parse(this.agentJson)
        rewardFunctionData = JSON.parse(this.rewardJson)
      } catch (e) {
        this.$message.error('Agent or Reward JSON is invalid')
        return
      }
      const schema = buildSchemaExport({
        datasetName: this.datasetName,
        siteName: this.siteName,
        formData: this.formData,
        observations: this.observations,
        actions: this.actions,
        agentData,
        rewardFunctionData,
        nodes: this.nodes
      })
      const blob = new Blob([JSON.stringify(schema, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'schema.json'
      a.click()
      URL.revokeObjectURL(url)
      this.$message.success('Schema exported')
    }
  }
}
</script>

<style scoped>
.schema-page { padding: 8px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 8px; }
.section { margin-bottom: 16px; }
.palette { margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.canvas {
  position: relative;
  height: 480px;
  border: 1px dashed #dcdfe6;
  background: #fafafa;
  overflow: auto;
}
.node {
  position: absolute;
  width: 220px;
  background: #fff;
  border: 1px solid #409eff;
  border-radius: 6px;
  padding: 8px;
  cursor: move;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
}
.node-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.mt-4 { margin-top: 8px; }
</style>
