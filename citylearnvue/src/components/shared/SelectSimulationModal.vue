<template>
  <el-dialog title="选择比较模型KPI 指标" :visible.sync="visible" width="640px" @close="handleClose">
    <el-checkbox-group v-model="localSelected">
      <el-row :gutter="12">
        <el-col v-for="sim in simulationList" :key="sim" :span="24">
          <el-checkbox :label="sim">{{ sim }}</el-checkbox>
        </el-col>
      </el-row>
    </el-checkbox-group>
    <span slot="footer">
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :disabled="!localSelected.length" @click="confirm">确认</el-button>
    </span>
  </el-dialog>
</template>

<script>
export default {
  name: 'SelectSimulationModal',
  props: {
    value: { type: Boolean, default: false },
    simulationList: { type: Array, default: () => [] }
  },
  data() {
    return { localSelected: [] }
  },
  computed: {
    visible: {
      get() { return this.value },
      set(v) { this.$emit('input', v) }
    }
  },
  watch: {
    value(open) {
      if (open) this.localSelected = []
    }
  },
  methods: {
    handleClose() {
      this.visible = false
    },
    confirm() {
      this.$emit('confirm', [...this.localSelected])
      this.visible = false
    }
  }
}
</script>
