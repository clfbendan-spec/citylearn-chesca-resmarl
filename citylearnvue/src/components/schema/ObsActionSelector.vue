<template>
  <div class="obs-action-selector">
    <el-table :data="rows" size="mini" border>
      <el-table-column prop="key" label="名称" width="220" />
      <el-table-column label="active" width="80">
        <template slot-scope="{ row }">
          <el-checkbox v-model="options[row.key].active" />
        </template>
      </el-table-column>
      <el-table-column v-if="shared" label="shared_in_central_agent" width="160">
        <template slot-scope="{ row }">
          <el-checkbox v-model="options[row.key].shared_in_central_agent" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
export default {
  name: 'ObsActionSelector',
  props: {
    options: { type: Object, required: true },
    shared: { type: Boolean, default: true }
  },
  computed: {
    rows() {
      return Object.keys(this.options).map((key) => ({ key }))
    }
  }
}
</script>
