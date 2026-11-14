<template>
  <el-dialog
    title="任务配置"
    :visible="visible"
    width="min(760px, 94vw)"
    top="6vh"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
    @update:visible="$emit('update:visible', $event)"
    @opened="onOpened"
    @close="disposeChart"
  >
    <div class="task-config-body">
      <p class="config-sim-name">{{ simName || '未选择分组' }}</p>
      <el-empty
        v-if="!view.hasConfig"
        description="无算法配置记录"
        :image-size="64"
      >
        <p class="empty-hint">当前任务未导出配置快照</p>
      </el-empty>

      <template v-else>
        <div class="resmarl-banner" :class="view.resmarl.enabled ? 'is-on' : 'is-off'">
          <el-tag
            v-if="view.resmarl.label"
            :type="view.resmarl.enabled ? 'warning' : 'info'"
            size="mini"
          >
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
    <div slot="footer">
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
    </div>
  </el-dialog>
</template>

<script>
import * as echarts from 'echarts'
import { buildAgentConfigView } from '@/utils/agentConfigDisplay'
import { themeColor } from '@/utils/theme'

export default {
  name: 'TaskConfigDialog',
  props: {
    config: { type: [Object, String], default: null },
    simName: { type: String, default: '' },
    visible: { type: Boolean, default: false }
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
    }
  },
  mounted() {
    window.addEventListener('resize', this.onResize)
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.onResize)
    this.disposeChart()
  },
  methods: {
    onOpened() {
      this.renderSocChart()
      this.onResize()
    },
    disposeChart() {
      if (this.chart) {
        this.chart.dispose()
        this.chart = null
      }
    },
    renderSocChart() {
      if (!this.visible || !this.$refs.socChart || !this.view.minSoc.length) {
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
            itemStyle: { color: themeColor('primary-color') }
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
.config-sim-name {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--secondary-text-color);
  overflow-wrap: anywhere;
}

.task-config-body {
  max-height: 65vh;
  overflow-y: auto;
}

.empty-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--secondary-text-color);
  line-height: 1.5;
}

.resmarl-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 12px;
  background: var(--input-fill-color);
}

.resmarl-banner.is-on {
  background: rgba(255, 152, 0, 0.12);
}

.banner-hint {
  font-size: 11px;
  color: var(--secondary-text-color);
}

.config-group {
  margin-bottom: 14px;
}

.group-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--secondary-text-color);
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--divider-color);
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
  color: var(--secondary-text-color);
  flex-shrink: 0;
}

.config-value {
  color: var(--primary-text-color);
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
  background: var(--input-fill-color);
  color: var(--primary-text-color);
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
