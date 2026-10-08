<template>
  <el-dialog
    title="选择比较模型"
    :visible.sync="visible"
    width="720px"
    custom-class="select-compare-model-dialog"
    @close="onDialogClosed"
  >
    <div class="compare-lists">
      <div class="compare-col">
        <div class="compare-col-title">评估模型</div>
        <el-radio-group v-model="evalModel" class="compare-radio-group" @change="onEvalChange">
          <el-radio
            v-for="sim in simulationList"
            :key="'eval-' + sim"
            :label="sim"
            class="compare-radio"
          >
            {{ sim }}
          </el-radio>
        </el-radio-group>
        <div v-if="!simulationList.length" class="compare-empty">暂无可选模型</div>
      </div>
      <div class="compare-col" :class="{ disabled: !evalModel }">
        <div class="compare-col-title">对照组</div>
        <el-radio-group
          v-model="controlModel"
          class="compare-radio-group"
          :disabled="!evalModel"
        >
          <el-radio
            v-for="sim in controlCandidates"
            :key="'ctrl-' + sim"
            :label="sim"
            class="compare-radio"
          >
            {{ sim }}
          </el-radio>
        </el-radio-group>
        <div v-if="!evalModel" class="compare-hint">请先在左侧选择评估模型</div>
        <div v-else-if="!controlCandidates.length" class="compare-empty">暂无其他可选模型</div>
      </div>
    </div>
    <span slot="footer">
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!canConfirm" @click="confirm">确认</el-button>
    </span>
  </el-dialog>
</template>

<script>
export default {
  name: 'SelectCompareModelModal',
  props: {
    value: { type: Boolean, default: false },
    simulationList: { type: Array, default: () => [] }
  },
  data() {
    return {
      evalModel: '',
      controlModel: '',
      confirmed: false
    }
  },
  computed: {
    visible: {
      get() { return this.value },
      set(v) { this.$emit('input', v) }
    },
    controlCandidates() {
      return (this.simulationList || []).filter((sim) => sim !== this.evalModel)
    },
    canConfirm() {
      return !!(this.evalModel && this.controlModel && this.evalModel !== this.controlModel)
    }
  },
  watch: {
    value(open) {
      if (open) {
        this.evalModel = ''
        this.controlModel = ''
        this.confirmed = false
      }
    }
  },
  methods: {
    onEvalChange() {
      if (this.controlModel === this.evalModel) {
        this.controlModel = ''
      }
      if (this.controlModel && !this.controlCandidates.includes(this.controlModel)) {
        this.controlModel = ''
      }
    },
    onDialogClosed() {
      if (this.confirmed) {
        this.confirmed = false
        return
      }
      this.$emit('cancel')
    },
    confirm() {
      if (!this.canConfirm) {
        return
      }
      // 顺序：评估模型 → 对照组
      this.confirmed = true
      this.$emit('confirm', [this.evalModel, this.controlModel])
      this.visible = false
    }
  }
}
</script>

<style scoped>
.compare-lists {
  display: flex;
  gap: 16px;
  min-height: 280px;
}

.compare-col {
  flex: 1;
  min-width: 0;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.compare-col.disabled {
  opacity: 0.65;
}

.compare-col-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.compare-radio-group {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.compare-radio {
  margin: 0 !important;
  padding: 8px 10px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #ebeef5;
  white-space: normal;
  line-height: 1.4;
  height: auto;
}

.compare-radio:hover {
  border-color: #c0c4cc;
}

.compare-hint,
.compare-empty {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}
</style>
