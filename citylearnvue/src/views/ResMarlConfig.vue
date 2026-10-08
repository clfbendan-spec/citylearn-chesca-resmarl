<template>
  <div :class="['resmarl-config-page', 'ha-page', { 'is-readonly': !canOperate }]">
    <div class="page-header ha-toolbar">
      <div>
        <h2 class="page-title">CHESCA-ResMARL 配置</h2>
        <p v-if="!canOperate" class="page-readonly-tip">当前为只读模式（无操作权限）</p>
      </div>
      <div class="header-actions">
        <el-button :disabled="!canOperate || saving || loading" @click="handleReset">恢复默认</el-button>
        <el-button type="primary" :disabled="!canOperate" :loading="saving" @click="handleSave">保存配置</el-button>
      </div>
    </div>

    <el-card
      v-loading="loading"
      shadow="never"
      :class="['config-card', 'multi-agent-card', { 'is-collapsed': multiAgentCollapsed }]"
    >
      <div class="panel-title-row">
        <div class="ha-card-title">Multi-agent 配置</div>
        <button
          type="button"
          class="card-toggle-btn"
          :title="multiAgentCollapsed ? '展开' : '收起'"
          :aria-label="multiAgentCollapsed ? '展开' : '收起'"
          @click="multiAgentCollapsed = !multiAgentCollapsed"
        >
          <i :class="multiAgentCollapsed ? 'el-icon-arrow-down' : 'el-icon-arrow-up'" />
        </button>
      </div>

      <div class="card-schema-bar form-row-2">
        <div class="form-item">
          <label class="form-label">训练数据集（train_schema）</label>
          <el-select
            v-model="trainSchema"
            filterable
            allow-create
            default-first-option
            :disabled="!canOperate"
            placeholder="选择或输入训练 schema"
            style="width: 100%"
          >
            <el-option
              v-for="opt in schemaOptions"
              :key="`train-${opt.value}`"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="form-item">
          <label class="form-label">评估数据集（multi_agent_eval_schema）</label>
          <el-select
            v-model="multiAgentEvalSchema"
            filterable
            allow-create
            default-first-option
            :disabled="!canOperate"
            placeholder="选择或输入评估 schema"
            style="width: 100%"
          >
            <el-option
              v-for="opt in schemaOptions"
              :key="`ma-eval-${opt.value}`"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
      </div>

      <div v-show="!multiAgentCollapsed" class="card-body card-body--empty"></div>
    </el-card>

    <battery-min-soc-config ref="chescaConfig" embedded :readonly="!canOperate" class="chesca-section" />

    <el-card
      v-loading="loading"
      shadow="never"
      :class="['config-card', 'residual-card', { 'is-collapsed': residualCollapsed }]"
    >
          <div class="panel-title-row">
            <div class="ha-card-title">残差配置</div>
            <button
              type="button"
              class="card-toggle-btn"
              :title="residualCollapsed ? '展开' : '收起'"
              :aria-label="residualCollapsed ? '展开' : '收起'"
              @click="residualCollapsed = !residualCollapsed"
            >
              <i :class="residualCollapsed ? 'el-icon-arrow-down' : 'el-icon-arrow-up'" />
            </button>
          </div>

          <div class="card-schema-bar">
            <div class="form-item form-item--schema">
              <label class="form-label">评估数据集（resmarl_eval_schema）</label>
              <el-select
                v-model="evalSchema"
                filterable
                allow-create
                default-first-option
                :disabled="!canOperate"
                placeholder="选择或输入 CityLearn schema"
                style="width: 100%"
              >
                <el-option
                  v-for="opt in schemaOptions"
                  :key="`resmarl-eval-${opt.value}`"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              
            </div>
          </div>

          <div v-show="!residualCollapsed" class="card-body">
          <p class="param-help residual-intro">
            以下参数仅在通过 <code>CHESCA_ResMARL.py</code> 启动时生效；
            <code>CHESCA.py</code> 固定走纯 CHESCA，不读残差参数。
            残差用预存 Multi-Agent SAC 动作 <code>a_rl</code> 与 CHESCA 基准 <code>a_base</code> 加权混合。
          </p>
          <div class="formula-banner" aria-label="残差混合公式">
            <div class="formula-banner__eq">
              <span class="formula-term formula-term--result">action</span>
              <span class="formula-op">=</span>
              <span class="formula-term">(1−α)·a<sub>base</sub></span>
              <span class="formula-op">+</span>
              <span class="formula-term">α·a<sub>rl</sub></span>
            </div>
          </div>

          <div class="form-item">
            <div class="form-label-row">
              <label class="form-label">残差强度 α（residual_alpha）</label>
            </div>
            <el-input-number
              v-model="residualAlpha"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="2"
              :disabled="!canOperate"
              controls-position="right"
            />
          </div>

          <div class="form-item">
            <div class="form-label-row">
              <label class="form-label">允许修正的动作维度（residual_action_mask）</label>
            </div>
            <el-checkbox-group v-model="maskKeys" class="mask-group" :disabled="!canOperate">
              <el-checkbox label="ele">电池充放电（ELE）</el-checkbox>
              <el-checkbox label="tmp">冷机 / 空调（TMP）</el-checkbox>
              <el-checkbox label="dhw">生活热水（DHW）</el-checkbox>
            </el-checkbox-group>
            <p class="param-help">允许哪些动作受 ResMARL 影响。</p>
          </div>

          <div class="form-item">
            <div class="form-label-row">
              <label class="form-label">混合残差时机（resmarl_after_safety）</label>
            </div>
            <el-radio-group v-model="resmarlAfterSafety" :disabled="!canOperate">
              <el-radio :label="true">先安全审查</el-radio>
              <el-radio :label="false">先混合残差</el-radio>
            </el-radio-group>
            <p class="param-help">
              安全审查会把动作裁剪到设备/舒适等约束内。先安全审查，残差更容易真正生效，但最终动作可能偏离审查。先混合残差，更加安全，但 ResMARL 的改动可能被再次裁掉。
            </p>
          </div>

          <div class="form-item">
            <div class="form-label-row">
              <label class="form-label">Multi-agent预存模型路径（multi_agent_checkpoint）</label>
            </div>
            <el-input
              v-model="multiAgentCheckpoint"
              clearable
              :disabled="!canOperate"
              placeholder="必填：Multi-agent.py 保存的模型路径"
            />
            <p class="param-help">Multi-agent.py 保存的模型路径（跑 CHESCA_ResMARL.py 时必填）</p>
          </div>
          </div>
    </el-card>
  </div>
</template>

<script>
import axios from 'axios'
import BatteryMinSocConfig from './BatteryMinSocConfig.vue'
import { PERMS } from '../utils/permissions'

export default {
  name: 'ResMarlConfig',
  inject: {
    hasPermission: {
      default: () => () => true
    }
  },
  components: {
    BatteryMinSocConfig
  },
  data() {
    return {
      loading: false,
      saving: false,
      residualCollapsed: true,
      multiAgentCollapsed: true,
      multiAgentExplore: false,
      multiAgentCheckpoint: '',
      residualAlpha: 0,
      maskKeys: ['ele'],
      resmarlAfterSafety: true,
      trainSchema: 'citylearn_challenge_2023_phase_2_local_evaluation',
      multiAgentEvalSchema: 'citylearn_challenge_2023_phase_2_online_evaluation_1',
      evalSchema: 'citylearn_challenge_2023_phase_2_online_evaluation_1',
      schemaOptions: []
    }
  },
  computed: {
    canOperate() {
      return this.hasPermission(PERMS.RES_MARL_OPERATE)
    }
  },
  created() {
    this.loadDatasetOptions().finally(() => this.loadConfig())
  },
  methods: {
    ensureOperate() {
      if (!this.canOperate) {
        this.$message.warning('无配置操作权限，仅可查看')
        return false
      }
      return true
    },
    async loadDatasetOptions() {
      try {
        const response = await axios.get('/api/web/basedata/getDatasetList')
        if (response.data && response.data.code === 0 && Array.isArray(response.data.data)) {
          this.schemaOptions = response.data.data.map((d) => ({
            value: d.schemaKey,
            label: d.displayName,
            chescaCompatible: d.chescaCompatible
          }))
        }
      } catch (e) {
        // 保留空列表；保存时仍可用 allow-create 手填
        console.error('加载数据集列表失败', e)
      }
    },
    buildMaskPayload() {
      return {
        dhw: this.maskKeys.includes('dhw'),
        ele: this.maskKeys.includes('ele'),
        tmp: this.maskKeys.includes('tmp')
      }
    },
    applyConfig(data) {
      if (!data) return
      this.multiAgentExplore = !!data.multiAgentExplore
      this.multiAgentCheckpoint = data.multiAgentCheckpoint || ''
      const alpha = Number(data.residualAlpha)
      this.residualAlpha = Number.isFinite(alpha) ? alpha : 0
      const mask = data.residualActionMask || { dhw: false, ele: true, tmp: false }
      this.maskKeys = ['dhw', 'ele', 'tmp'].filter((k) => !!mask[k])
      if (!this.maskKeys.length) this.maskKeys = ['ele']
      this.resmarlAfterSafety = data.resmarlAfterSafety !== false
      this.trainSchema = data.trainSchema || 'citylearn_challenge_2023_phase_2_local_evaluation'
      this.multiAgentEvalSchema = data.multiAgentEvalSchema
        || 'citylearn_challenge_2023_phase_2_online_evaluation_1'
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
      if (!this.ensureOperate()) return
      if (!this.maskKeys.length) {
        this.$message.warning('请至少勾选一个动作维（建议保留 ELE）')
        return
      }
      if (!(this.multiAgentCheckpoint || '').trim()) {
        this.$message.warning('请填写预存模型路径（multi_agent_checkpoint），跑 CHESCA_ResMARL.py 时必填')
        return
      }
      const trainSchema = (this.trainSchema || '').trim()
      if (!trainSchema) {
        this.$message.warning('请选择或填写 Multi-agent 训练数据集（train_schema）')
        return
      }
      const multiAgentEvalSchema = (this.multiAgentEvalSchema || '').trim()
      if (!multiAgentEvalSchema) {
        this.$message.warning('请选择或填写 Multi-agent 评估数据集（multi_agent_eval_schema）')
        return
      }
      const evalSchema = (this.evalSchema || '').trim()
      if (!evalSchema) {
        this.$message.warning('请选择或填写残差评估数据集（resmarl_eval_schema）')
        return
      }
      if (/citylearn_challenge_2022/.test(evalSchema)) {
        try {
          await this.$confirm(
            '2022 数据集仅含电池动作，与 CHESCA-ResMARL 不兼容。\n' +
              '继续保存后若跑 CHESCA_ResMARL.py 可能启动失败；请改用 2023/2026 schema。\n是否仍要保存？',
            '数据集不兼容提示',
            { type: 'warning', confirmButtonText: '仍保存', cancelButtonText: '取消' }
          )
        } catch (e) {
          return
        }
      }
      this.saving = true
      try {
        const chesca = this.$refs.chescaConfig
        const chescaOk = chesca
          ? await chesca.saveConfig({ silent: true })
          : true
        if (!chescaOk) {
          this.$message.error('CHESCA 配置保存失败')
          return
        }

        const response = await axios.post('/api/web/basedata/saveResMarlConfig', {
          // 是否跑残差由入口脚本决定；此处固定写入 ResMARL 参数侧标记
          resmarlEnabled: true,
          marlMode: 'multi_agent',
          multiAgentTrainEpochs: 0,
          multiAgentExplore: this.multiAgentExplore,
          multiAgentCheckpoint: (this.multiAgentCheckpoint || '').trim(),
          residualAlpha: this.residualAlpha,
          residualActionMask: this.buildMaskPayload(),
          resmarlAfterSafety: this.resmarlAfterSafety,
          trainSchema,
          multiAgentEvalSchema,
          evalSchema
        })
        if (response.data && response.data.code === 0) {
          this.$message.success('配置已保存')
          await this.loadConfig()
        } else {
          this.$message.error((response.data && response.data.message) || '残差配置保存失败')
        }
      } catch (e) {
        this.$message.error((e.response && e.response.data && e.response.data.message) || '保存失败')
      } finally {
        this.saving = false
      }
    },
    async handleReset() {
      if (!this.ensureOperate()) return
      try {
        await this.$confirm(
          '将同时恢复 CHESCA、残差与 Multi-agent 数据集为默认值。是否继续？',
          '恢复默认',
          { type: 'warning' }
        )
      } catch (e) {
        return
      }
      this.loading = true
      try {
        const chesca = this.$refs.chescaConfig
        const chescaOk = chesca
          ? await chesca.resetConfig({ silent: true, skipConfirm: true })
          : true
        if (!chescaOk) {
          this.$message.error('CHESCA 配置恢复失败')
          return
        }

        const response = await axios.post('/api/web/basedata/resetResMarlConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
          this.$message.success('已恢复全页默认配置')
        } else {
          this.$message.error((response.data && response.data.message) || '残差配置恢复失败')
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
  width: 100%;
  max-width: none;
}

.resmarl-config-page.ha-page {
  padding: var(--space-4) var(--space-5) var(--space-6);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 400;
  line-height: 1.25;
  color: var(--primary-text-color);
}

.page-readonly-tip {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--secondary-text-color);
}

.resmarl-config-page.is-readonly .config-card {
  opacity: 0.92;
}

.header-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.config-card {
  width: 100%;
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
  background: var(--card-background-color);
  margin-bottom: var(--space-3);
}

.config-card >>> .el-card__body {
  padding: var(--space-4);
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: 0;
}

.card-toggle-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: var(--card-background-color);
  color: var(--primary-color);
  cursor: pointer;
  box-shadow: none;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.card-toggle-btn i {
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

.card-toggle-btn:hover {
  background: var(--sidebar-selected-background);
  border-color: var(--outline-hover-color);
  color: var(--dark-primary-color);
}

.card-toggle-btn:active {
  background: var(--light-primary-color);
}

.card-body {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--divider-color);
}

.card-schema-bar {
  margin-top: var(--space-3);
}

.card-schema-bar .form-item {
  margin-bottom: 0;
}

.card-schema-bar .form-item--schema {
  margin-bottom: 0;
}

.form-item {
  margin-bottom: var(--space-5);
}

.form-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.param-help {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--secondary-text-color);
  line-height: 1.6;
}

.residual-intro {
  margin: 0 0 var(--space-3);
}

.param-help code {
  background: var(--input-fill-color);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--secondary-text-color);
  font-family: "Roboto Mono", "SF Mono", Consolas, monospace;
}

.formula-banner {
  margin: 0 0 var(--space-4);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  background: var(--input-fill-color);
  border: 1px solid var(--divider-color);
  border-left: 3px solid var(--primary-color);
  border-radius: 8px;
}

.formula-banner__eq {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 10px;
  font-family: Roboto, "Noto Sans SC", "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 20px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--primary-text-color);
  letter-spacing: 0.01em;
}

.formula-term {
  white-space: nowrap;
}

.formula-term--result {
  color: var(--primary-color);
}

.formula-op {
  color: var(--secondary-text-color);
  font-weight: 400;
}

.formula-banner__eq sub {
  font-size: 0.65em;
  font-weight: 500;
}

.mask-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
}

.chesca-section {
  margin-top: 0;
  margin-bottom: var(--space-3);
}

.form-row-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

@media (max-width: 960px) {
  .form-row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
