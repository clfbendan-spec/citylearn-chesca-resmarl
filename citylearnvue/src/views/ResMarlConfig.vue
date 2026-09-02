<template>
  <div class="resmarl-config-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">CHESCA-ResMARL 配置</h2>
        <p class="page-desc">
          CHESCA 规则基准动作 + Multi-Agent SAC 残差修正：
          <code>a_final = clip(a_base + α · mask · Δa)</code>。
          保存后写入 MySQL <code>algorithm_config</code>，由
          <code>local_evaluation_copy.py</code> 加载执行。
        </p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadConfig">刷新</el-button>
        <el-button @click="handleReset">恢复默认</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card v-loading="loading" shadow="never" class="config-card">
          <div class="panel-title">全局开关</div>

          <div class="form-item">
            <div class="form-label-row">
              <label class="form-label">启用 CHESCA-ResMARL（resmarl_enabled）</label>
              <el-tag :type="resmarlEnabled ? 'success' : 'info'" size="mini">
                {{ resmarlEnabled ? '已启用' : '已关闭' }}
              </el-tag>
            </div>
            <el-switch v-model="resmarlEnabled" active-text="启用" inactive-text="关闭" />
            <p class="param-help">
              关闭时走纯 CHESCA；开启后评估前按训练轮数训练 Multi-Agent SAC，再对 CHESCA 动作做残差修正。
            </p>
          </div>

          <template v-if="resmarlEnabled">
            <el-divider content-position="left">残差层（α / mask）</el-divider>

            <div class="form-item">
              <div class="form-label-row">
                <label class="form-label">残差强度 α（residual_alpha）</label>
                <span class="alpha-value">{{ residualAlpha.toFixed(2) }}</span>
              </div>
              <el-slider
                v-model="residualAlpha"
                :min="0"
                :max="1"
                :step="0.01"
                show-input
                :show-input-controls="true"
                input-size="small"
              />
              <p class="param-help">α=0 时残差恒等，数值上与纯 CHESCA 一致（消融对照）。</p>
            </div>

            <div class="form-item">
              <div class="form-label-row">
                <label class="form-label">动作维 mask（residual_action_mask）</label>
              </div>
              <el-checkbox-group v-model="maskKeys" class="mask-group">
                <el-checkbox label="ele">电池 ELE</el-checkbox>
                <el-checkbox label="tmp">冷机 TMP</el-checkbox>
                <el-checkbox label="dhw">热水 DHW</el-checkbox>
              </el-checkbox-group>
              <p class="param-help">首版建议<strong>仅开启 ELE</strong>。</p>
            </div>

            <div class="form-item">
              <div class="form-label-row">
                <label class="form-label">残差时机（resmarl_after_safety）</label>
              </div>
              <el-radio-group v-model="resmarlAfterSafety">
                <el-radio :label="true">模式 A：安全审查之后</el-radio>
                <el-radio :label="false">模式 B：安全审查之前</el-radio>
              </el-radio-group>
            </div>

            <el-divider content-position="left">Multi-Agent SAC</el-divider>

            <div class="form-item">
              <div class="form-label-row">
                <label class="form-label">训练轮数（multi_agent_train_epochs）</label>
              </div>
              <el-input-number
                v-model="multiAgentTrainEpochs"
                :min="1"
                :max="500"
                :step="1"
                controls-position="right"
              />
              <p class="param-help">
                评估前现场训练各 agent SAC 策略的 epoch 数（与 <code>Multi-agent.py</code> 一致，默认 20）。
              </p>
            </div>

            <!--<div class="form-item">
              <div class="form-label-row">
                <label class="form-label">评估 explore（multi_agent_explore）</label>
              </div>
              <el-switch
                v-model="multiAgentExplore"
                active-text="开启"
                inactive-text="关闭（deterministic）"
              />
            </div>-->

            <el-divider content-position="left">训测数据集（方案 A）</el-divider>

            <div class="form-item">
              <div class="form-label-row">
                <label class="form-label">训测 schema 分离（schema_split_enabled）</label>
              </div>
              <el-switch
                v-model="schemaSplitEnabled"
                active-text="开启"
                inactive-text="关闭（同 schema）"
              />
              <p class="param-help">
                开启后：SAC 在 <code>train_schema</code> 上训练，CHESCA 在 <code>eval_schema</code> 上仿真/KPI。
              </p>
            </div>

            <template v-if="schemaSplitEnabled">
              <div class="form-item">
                <label class="form-label">训练 schema（train_schema）</label>
                <el-input v-model="trainSchema" placeholder="phase_2_local_evaluation" />
                <p class="param-help">默认 720h 本地开发集，训练较快。</p>
              </div>
              <div class="form-item">
                <label class="form-label">评估 schema（eval_schema）</label>
                <el-input v-model="evalSchema" placeholder="phase_2_online_evaluation_1" />
                <p class="param-help">默认 2208h 线上评估集（不同天气），用于泛化测试。</p>
              </div>
            </template>
          </template>

          <el-alert
            v-if="!resmarlEnabled"
            title="当前：纯 CHESCA 基线。"
            type="success"
            :closable="false"
            show-icon
            class="mode-alert"
          />
          <el-alert
            v-else-if="residualAlpha > 0"
            :title="`CHESCA-ResMARL：α=${residualAlpha.toFixed(2)}，评估前训练 SAC ${multiAgentTrainEpochs} 轮。`"
            type="warning"
            :closable="false"
            show-icon
            class="mode-alert"
          />
          <el-alert
            v-else
            title="CHESCA-ResMARL 已启用但 α=0：与纯 CHESCA 数值一致。"
            type="info"
            :closable="false"
            show-icon
            class="mode-alert"
          />
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never" class="explain-card">
          <div class="panel-title">架构说明</div>
          <div class="explain-block">
            <h4>控制链路</h4>
            <ul>
              <li>阶段 1–4：CHESCA 预测 → 初稿 → 电池 refine</li>
              <li>评估前：按训练轮数训练 Multi-Agent SAC</li>
              <li>阶段 5：各 agent 输出 Δa，叠加到 a_base</li>
            </ul>
          </div>
          <div class="explain-block">
            <h4>存储键（algorithm_config）</h4>
            <ul>
              <li><code>resmarl_enabled</code> / <code>marl_mode</code></li>
              <li><code>residual_alpha</code> / <code>residual_action_mask</code></li>
              <li><code>resmarl_after_safety</code></li>
              <li><code>multi_agent_train_epochs</code> / <code>multi_agent_explore</code></li>
              <li><code>schema_split_enabled</code> / <code>train_schema</code> / <code>eval_schema</code></li>
            </ul>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'ResMarlConfig',
  data() {
    return {
      loading: false,
      saving: false,
      resmarlEnabled: false,
      multiAgentTrainEpochs: 20,
      multiAgentExplore: false,
      residualAlpha: 0,
      maskKeys: ['ele'],
      resmarlAfterSafety: true,
      schemaSplitEnabled: true,
      trainSchema: 'citylearn_challenge_2023_phase_2_local_evaluation',
      evalSchema: 'citylearn_challenge_2023_phase_2_online_evaluation_1'
    }
  },
  created() {
    this.loadConfig()
  },
  methods: {
    buildMaskPayload() {
      return {
        dhw: this.maskKeys.includes('dhw'),
        ele: this.maskKeys.includes('ele'),
        tmp: this.maskKeys.includes('tmp')
      }
    },
    applyConfig(data) {
      if (!data) return
      this.resmarlEnabled = !!data.resmarlEnabled
      const epochs = Number(data.multiAgentTrainEpochs)
      this.multiAgentTrainEpochs = Number.isFinite(epochs) && epochs >= 1 ? epochs : 20
      this.multiAgentExplore = !!data.multiAgentExplore
      const alpha = Number(data.residualAlpha)
      this.residualAlpha = Number.isFinite(alpha) ? alpha : 0
      const mask = data.residualActionMask || { dhw: false, ele: true, tmp: false }
      this.maskKeys = ['dhw', 'ele', 'tmp'].filter((k) => !!mask[k])
      if (!this.maskKeys.length) this.maskKeys = ['ele']
      this.resmarlAfterSafety = data.resmarlAfterSafety !== false
      this.schemaSplitEnabled = data.schemaSplitEnabled !== false
      this.trainSchema = data.trainSchema || 'citylearn_challenge_2023_phase_2_local_evaluation'
      this.evalSchema = data.evalSchema || 'citylearn_challenge_2023_phase_2_online_evaluation_1'
    },
    async loadConfig() {
      this.loading = true
      try {
        const response = await axios.get('/api/web/basedata/getResMarlConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
        } else {
          this.$message.error((response.data && response.data.message) || '加载配置失败')
        }
      } catch (e) {
        this.$message.error('加载配置失败，请确认已执行 algorithm_config.sql 并重启 Java 服务')
      } finally {
        this.loading = false
      }
    },
    async handleSave() {
      if (this.resmarlEnabled && !this.maskKeys.length) {
        this.$message.warning('请至少勾选一个动作维（建议保留 ELE）')
        return
      }
      this.saving = true
      try {
        const response = await axios.post('/api/web/basedata/saveResMarlConfig', {
          resmarlEnabled: this.resmarlEnabled,
          marlMode: this.resmarlEnabled ? 'multi_agent' : 'none',
          multiAgentTrainEpochs: this.multiAgentTrainEpochs,
          multiAgentExplore: this.multiAgentExplore,
          residualAlpha: this.residualAlpha,
          residualActionMask: this.buildMaskPayload(),
          resmarlAfterSafety: this.resmarlAfterSafety,
          schemaSplitEnabled: this.schemaSplitEnabled,
          trainSchema: this.trainSchema,
          evalSchema: this.evalSchema
        })
        if (response.data && response.data.code === 0) {
          this.$message.success('CHESCA-ResMARL 配置已保存')
          await this.loadConfig()
        } else {
          this.$message.error((response.data && response.data.message) || '保存失败')
        }
      } catch (e) {
        this.$message.error((e.response && e.response.data && e.response.data.message) || '保存失败')
      } finally {
        this.saving = false
      }
    },
    async handleReset() {
      try {
        await this.$confirm('将恢复为默认：关闭 ResMARL，α=0。是否继续？', '恢复默认', { type: 'warning' })
      } catch (e) {
        return
      }
      this.loading = true
      try {
        const response = await axios.post('/api/web/basedata/resetResMarlConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
          this.$message.success('已恢复默认配置')
        } else {
          this.$message.error((response.data && response.data.message) || '恢复失败')
        }
      } catch (e) {
        this.$message.error('恢复失败')
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style scoped>
.resmarl-config-page {
  padding: 16px 20px 24px;
  max-width: 1100px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 6px;
  font-size: 20px;
  color: #303133;
}
.page-desc {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.55;
  max-width: 640px;
}
.page-desc code {
  background: #f4f4f5;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.config-card,
.explain-card {
  border: 1px solid #ebeef5;
  min-height: 420px;
}
.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 18px;
}
.form-item {
  margin-bottom: 24px;
}
.form-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.alpha-value {
  font-family: Consolas, Monaco, monospace;
  font-size: 14px;
  color: #409eff;
  font-weight: 600;
}
.param-help {
  margin: 10px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.param-help code {
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
  color: #606266;
}
.param-help strong {
  color: #606266;
}
.mode-alert {
  margin-top: 8px;
}
.mask-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.explain-block {
  margin-bottom: 18px;
}
.explain-block h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #303133;
}
.explain-block ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}
</style>
