<template>
  <aside class="task-config-sidebar" :class="{ collapsed: collapsed }">
    <div class="sidebar-toggle-bar">
      <el-button
        type="text"
        class="collapse-btn"
        :title="collapsed ? '展开任务配置' : '收起侧栏'"
        @click="$emit('update:collapsed', !collapsed)"
      >
        <i :class="collapsed ? 'el-icon-d-arrow-left' : 'el-icon-d-arrow-right'" />
      </el-button>
      <template v-if="!collapsed">
        <div class="sidebar-title-wrap">
          <h4 class="sidebar-title">任务配置</h4>
          <p class="sidebar-sub">{{ simName || '未选择分组' }}</p>
        </div>
      </template>
    </div>

    <div v-if="!collapsed" class="sidebar-body">
      <el-empty
        v-if="!view.hasConfig"
        description="无 chesca_agent_config.json"
        :image-size="64"
      >
        <p class="empty-hint">请使用带配置快照的 local_evaluation_copy.py 重跑任务</p>
      </el-empty>

      <template v-else>
        <div class="resmarl-banner" :class="view.resmarl.enabled ? 'is-on' : 'is-off'">
          <el-tag :type="view.resmarl.enabled ? 'warning' : 'info'" size="mini">
            {{ view.resmarl.label }}
          </el-tag>
          <span class="banner-hint">本次仿真参数快照</span>
        </div>

        <div
          v-for="group in view.groups"
          :key="group.id"
          class="config-group"
        >
          <div class="group-title">{{ group.title }}</div>
          <div
            v-for="item in group.items"
            :key="item.key"
            class="config-row"
            :title="item.hint || item.key"
          >
            <span class="config-label">{{ item.label }}</span>
            <span
              class="config-value"
              :title="String(item.display)"
            >
              {{ item.display }}
            </span>
          </div>
        </div>

        <div v-if="view.minSoc.length" class="config-group">
          <div class="group-title">小时电池 SOC 下限</div>
          <div ref="socChart" class="soc-chart" />
          <el-collapse class="soc-collapse">
            <el-collapse-item title="24 小时数值表" name="soc">
              <el-table :data="view.minSoc" size="mini" max-height="220" border>
                <el-table-column prop="hour" label="小时" width="56" align="center" />
                <el-table-column label="min_soc" align="center">
                  <template slot-scope="{ row }">
                    {{ row.value == null ? '—' : row.value.toFixed(2) }}
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </div>

        <div class="config-group">
          <el-collapse>
            <el-collapse-item title="原始 JSON" name="raw">
              <pre class="raw-json">{{ view.rawJson }}</pre>
              <el-button size="mini" type="primary" plain icon="el-icon-document-copy" @click="copyJson">
                复制 JSON
              </el-button>
            </el-collapse-item>
          </el-collapse>
        </div>
      </template>
    </div>
  </aside>
</template>

<script>
import * as echarts from 'echarts'
import { buildAgentConfigView } from '@/utils/agentConfigDisplay'

export default {
  name: 'TaskConfigSidebar',
  props: {
    config: { type: [Object, String], default: null },
    simName: { type: String, default: '' },
    collapsed: { type: Boolean, default: false }
  },
  data() {
    return {
      chart: null
    }
  },
  computed: {
    view() {
      return buildAgentConfigView(this.config)
    }
  },
  watch: {
    view: {
      handler() {
        this.$nextTick(() => this.renderSocChart())
      },
      deep: true
    },
    collapsed(val) {
      if (!val) {
        this.$nextTick(() => {
          this.renderSocChart()
          if (this.chart) this.chart.resize()
        })
      }
    }
  },
  mounted() {
    this.$nextTick(() => this.renderSocChart())
    window.addEventListener('resize', this.onResize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.onResize)
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    renderSocChart() {
      if (this.collapsed || !this.$refs.socChart || !this.view.minSoc.length) {
        return
      }
      if (!this.chart) {
        this.chart = echarts.init(this.$refs.socChart)
      }
      const hours = this.view.minSoc.map((d) => d.hour)
      const values = this.view.minSoc.map((d) => d.value)
      this.chart.setOption({
        grid: { left: 36, right: 8, top: 12, bottom: 24 },
        tooltip: {
          trigger: 'axis',
          formatter: (params) => {
            const p = params[0]
            const v = p.value == null ? '—' : Number(p.value).toFixed(2)
            return `小时 ${p.axisValue}<br/>min_soc: ${v}`
          }
        },
        xAxis: {
          type: 'category',
          data: hours,
          name: 'h',
          axisLabel: { fontSize: 9, interval: 1 }
        },
        yAxis: {
          type: 'value',
          min: 0,
          max: 1,
          axisLabel: { fontSize: 9 }
        },
        series: [
          {
            type: 'bar',
            data: values,
            barMaxWidth: 10,
            itemStyle: { color: '#5470c6' }
          }
        ]
      })
    },
    onResize() {
      if (this.chart) this.chart.resize()
    },
    async copyJson() {
      const text = this.view.rawJson
      if (!text) return
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text)
        } else {
          const ta = document.createElement('textarea')
          ta.value = text
          document.body.appendChild(ta)
          ta.select()
          document.execCommand('copy')
          document.body.removeChild(ta)
        }
        this.$message.success('已复制配置 JSON')
      } catch (e) {
        this.$message.error('复制失败')
      }
    }
  }
}
</script>

<style scoped>
.task-config-sidebar {
  flex-shrink: 0;
  width: 320px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 24px);
  position: sticky;
  top: 8px;
  overflow: hidden;
  transition: width 0.2s ease;
}

.task-config-sidebar.collapsed {
  width: 44px;
}

.sidebar-toggle-bar {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 10px 8px 8px;
  border-bottom: 1px solid #ebeef5;
  background: #fafbfc;
}

.collapse-btn {
  padding: 4px 6px;
  color: #606266;
  font-size: 16px;
}

.sidebar-title-wrap {
  flex: 1;
  min-width: 0;
  padding-right: 4px;
}

.sidebar-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.sidebar-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.empty-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.resmarl-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 12px;
  background: #f4f4f5;
}

.resmarl-banner.is-on {
  background: #fdf6ec;
}

.banner-hint {
  font-size: 11px;
  color: #909399;
}

.config-group {
  margin-bottom: 14px;
}

.group-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #ebeef5;
}

.config-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}

.config-label {
  color: #909399;
  flex-shrink: 0;
}

.config-value {
  color: #303133;
  text-align: right;
  word-break: break-all;
  font-variant-numeric: tabular-nums;
}

.soc-chart {
  height: 140px;
  width: 100%;
  margin-bottom: 4px;
}

.soc-collapse {
  border: none;
}

.raw-json {
  margin: 0 0 8px;
  padding: 8px;
  max-height: 220px;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
