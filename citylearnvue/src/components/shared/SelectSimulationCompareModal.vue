<template>
  <el-dialog title="选择对比仿真" :visible.sync="visible" width="480px" @close="handleClose">
    <el-radio-group v-model="selected">
      <el-row :gutter="12">
        <el-col v-for="sim in simulationList" :key="sim" :span="12">
          <el-radio :label="sim">{{ sim }}</el-radio>
        </el-col>
      </el-row>
    </el-radio-group>
    <span slot="footer">
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :disabled="!selected" @click="confirm">确认</el-button>
    </span>
  </el-dialog>
</template>

<script>
export default {
  name: 'SelectSimulationCompareModal',
  props: {
    value: { type: Boolean, default: false },
    simulationList: { type: Array, default: () => [] }
  },
  data() {
    return { selected: null }
  },
  computed: {
    visible: {
      get() { return this.value },
      set(v) { this.$emit('input', v) }
    }
  },
  watch: {
    value(open) {
      if (open) this.selected = null
    }
  },
  methods: {
    handleClose() { this.visible = false },
    confirm() {
      this.$emit('confirm', this.selected)
      this.visible = false
    }
  }
}
</script>
