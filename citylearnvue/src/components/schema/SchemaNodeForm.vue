<template>
  <div class="schema-node-form">
    <template v-if="node.type === 'building'">
      <el-input v-model="node.formData.energy_simulation" size="mini" placeholder="energy_simulation" />
      <el-input v-model="node.formData.weather" size="mini" placeholder="weather" class="mt-4" />
      <el-input v-model="node.formData.pricing" size="mini" placeholder="pricing" class="mt-4" />
    </template>
    <template v-else-if="node.type === 'ev'">
      <el-input-number v-model="node.formData.capacity" size="mini" :min="1" />
      <el-input-number v-model="node.formData.nominal_power" size="mini" :min="1" class="mt-4" />
    </template>
    <template v-else>
      <el-input v-model="node.formData.selectedType" size="mini" placeholder="type class" />
      <el-input-number v-model="node.formData.nominal_power" size="mini" :min="0" class="mt-4" />
    </template>
  </div>
</template>

<script>
export default {
  name: 'SchemaNodeForm',
  props: {
    node: { type: Object, required: true }
  }
}
</script>

<style scoped>
.mt-4 { margin-top: 6px; }
.schema-node-form .el-input,
.schema-node-form .el-input-number { width: 100%; }
</style>
