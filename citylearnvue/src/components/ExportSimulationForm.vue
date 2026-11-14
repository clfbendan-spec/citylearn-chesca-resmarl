<template>
  <div>
    <el-form-item label="调度场景"><el-select :value="value.profile" aria-label="调度场景" @change="profileChanged"><el-option label="电池调度" value="battery" /><el-option label="多储能调度" value="storage" /></el-select></el-form-item>
    <el-form-item label="控制设备"><el-checkbox-group :value="value.actions" @input="update('actions', $event)">
      <el-checkbox v-for="device in available" :key="device.key" :label="device.key">{{ device.label }}</el-checkbox>
    </el-checkbox-group><span v-if="!available.length" class="empty-controls">无可调度储能设备</span></el-form-item>
    <el-form-item label="奖励目标"><el-select :value="value.reward" aria-label="奖励目标" @change="update('reward', $event)"><el-option label="减少购电量" value="energy" /><el-option label="减少购电费用" value="cost" /><el-option label="减少购电碳排放" value="carbon" /></el-select></el-form-item>
  </div>
</template>
<script>
const devices = [{ key: 'electrical_storage', label: '储能电池' }, { key: 'cooling_storage', label: '蓄冷' }, { key: 'heating_storage', label: '蓄热' }, { key: 'dhw_storage', label: '热水储能' }]
export default {
  name: 'ExportSimulationForm', props: { value: { type: Object, required: true }, equipment: { type: Object, default: () => ({}) } },
  computed: { available() { return devices.filter(device => this.equipment[device.key] && (this.value.profile === 'storage' || device.key === 'electrical_storage')) } },
  methods: {
    update(key, value) { this.$emit('input', { ...this.value, [key]: value }) },
    profileChanged(profile) { this.$emit('input', { ...this.value, profile, actions: devices.filter(device => this.equipment[device.key] && (profile === 'storage' || device.key === 'electrical_storage')).map(device => device.key) }) }
  }
}
</script>
<style scoped>
.el-select{width:100%}.el-checkbox{margin:0 18px 8px 0}.empty-controls{font-size:13px;color:var(--secondary-text-color)}
</style>
