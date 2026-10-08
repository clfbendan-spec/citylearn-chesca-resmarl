<template>
  <div class="pipeline-task-dialog-root">
  <el-dialog
    :title="dialogTitle"
    :visible.sync="visibleProxy"
    width="1000px"
    top="8vh"
    custom-class="pipeline-task-dialog"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <p class="dialog-hint">
      {{ isEdit
        ? '修改任务名称与两张卡片的配置。只有「待执行」的任务可以编辑。'
        : '按「训练 → 评估」两步编排一个任务。创建后只在任务列表中生成一条记录（类型为 训练+评估），暂不执行脚本。' }}
    </p>

    <div v-loading="loading" class="pipeline-task-body">
      <!-- 任务名称：type=0 的名称存在 py_task.task_name，任务管理页「任务名称」列读它 -->
      <div class="name-field">
        <label class="field-label">任务名称</label>
        <el-input
          v-model="form.taskName"
          maxlength="128"
          show-word-limit
          clearable
          placeholder="例如：2023 local 训练 → online_1 评估"
        />
      </div>

      <div class="pipeline-flow">
        <!-- ============ 第一张卡：训练 ============ -->
        <div class="flow-card">
          <div class="card-head">
            <span class="card-index">1</span>
            <div class="card-head-text">
              <span class="card-title">训练</span>
              <span class="card-sub">训练脚本 · 训练配置</span>
            </div>
          </div>

          <div class="card-body">
            <div class="field">
              <label class="field-label">训练脚本</label>
              <el-select
                v-model="form.trainPyId"
                placeholder="请选择训练脚本"
                filterable
                class="field-control"
                :disabled="isReuseTrainModel"
              >
                <el-option
                  v-for="file in trainScripts"
                  :key="'train-py-' + file.id"
                  :label="file.fileName"
                  :value="file.id"
                />
              </el-select>
              <p v-if="isReuseTrainModel" class="field-hint">
                本次复用历史训练模型（{{ reuseTrainTaskLabel }}）⇒ 不执行训练，
                创建后只跑评估子任务。想恢复训练请到评估卡「配置」里改回「重新训练」。
              </p>
            </div>

            <div v-if="form.trainPyId" class="field">
              <label class="field-label">训练脚本配置</label>
              <div class="config-row">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  icon="el-icon-setting"
                  :disabled="isReuseTrainModel"
                  @click="openStepConfig('train')"
                >配置</el-button>
                <span v-if="form.trainConfig" class="config-status is-set">
                  {{ configStatusText(form.trainConfig) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ 中间箭头：表示训练完成后流向评估 ============ -->
        <div class="flow-arrow" aria-hidden="true">
          <span class="arrow-line" />
          <i class="el-icon-caret-right arrow-head" />
        </div>

        <!-- ============ 第二张卡：评估 ============ -->
        <div class="flow-card">
          <div class="card-head">
            <span class="card-index">2</span>
            <div class="card-head-text">
              <span class="card-title">评估</span>
              <span class="card-sub">评估脚本 · 评估配置</span>
            </div>
          </div>

          <div class="card-body">
            <div class="field">
              <label class="field-label">评估脚本</label>
              <el-select
                v-model="form.evalPyId"
                placeholder="请选择评估脚本"
                filterable
                class="field-control"
              >
                <el-option
                  v-for="file in evalScripts"
                  :key="'eval-py-' + file.id"
                  :label="file.fileName"
                  :value="file.id"
                />
              </el-select>
            </div>

            <div v-if="form.evalPyId" class="field">
              <label class="field-label">评估脚本配置</label>
              <div class="config-row">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  icon="el-icon-setting"
                  @click="openStepConfig('eval')"
                >配置</el-button>
                <span v-if="form.evalConfig" class="config-status is-set">
                  {{ configStatusText(form.evalConfig) }}
                </span>
                <span v-if="isReuseTrainModel" class="config-status is-set">
                  训练模型：复用 {{ reuseTrainTaskLabel }}
                </span>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>

    <div slot="footer">
      <el-button @click="visibleProxy = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </div>
  </el-dialog>

  <!-- 任务级脚本配置弹窗：与代码编辑器共用，但 persist=false —— 保存只挂到本任务上 -->
  <algorithm-config-dialog
    :visible.sync="configDialogVisible"
    :py-file="configScript"
    :config="configDialogConfig"
    :persist="false"
    :locked-params="configDialogLockedParams"
    :train-model-picker="configStep === 'eval'"
    :train-task-options="trainTaskOptions"
    :parent-task-id="taskId || ''"
    @saved="onStepConfigSaved"
  />
  </div>
</template>

<script>
import axios from 'axios'
import AlgorithmConfigDialog from './AlgorithmConfigDialog.vue'

/**
 * 「新建 / 编辑任务」弹窗：固定两张卡片（训练卡 → 评估卡），中间用右箭头连接。
 *
 * 每张卡片只有两项：脚本下拉 + 「配置」按钮。
 *   脚本   GET /api/web/basedata/getPyFileList?scriptType=train|eval
 *   配置   复用 AlgorithmConfigDialog（persist=false）：界面与代码编辑器的「配置」弹窗一致，
 *          点开自动带出该脚本文件的配置，保存只挂到当前任务上，不改脚本文件。
 *
 * 数据集不在卡片上选：它在「配置」里以 train-schema / eval-schema 参数（数据集下拉）出现，
 * 后端保存时会从 config 里解析出 datasetId / schemaKey / datasetName 回填。
 *
 * 新建 POST /api/web/basedata/createPipelineTask
 * 编辑 POST /api/web/basedata/updatePipelineTask   （回填用 GET /getPyTaskDetail?taskId=）
 *   后端校验后写 py_task：type=0、status=5（待执行）、task_name 存名称、
 *   train_config / eval_config 分别存两张卡片的 JSON：
 *     {pyId, scriptName, datasetId, schemaKey, datasetName, trainEpochs, trainBatchSize, config}
 */
export default {
  name: 'PipelineTaskDialog',
  components: { AlgorithmConfigDialog },
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    /**
     * 编辑模式：传入要编辑的任务 ID；留空表示新建。
     * 只传 ID 而不是整行对象 —— 弹窗自己拉一次详情（含两段配置 JSON），
     * 这样列表接口不必为每行都带上那两段 JSON。
     */
    taskId: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      loading: false,
      submitting: false,
      /** 选项只加载一次：同一会话内反复打开弹窗不重复请求 */
      optionsLoaded: false,
      trainScripts: [],
      evalScripts: [],
      /** 「复用历史成功训练任务」候选（后端 getTrainModelTaskList 下发，评估卡配置弹窗用） */
      trainTaskOptions: [],
      form: {
        taskName: '',
        trainPyId: null,
        // 训练轮数 / 批大小仍随卡片落库（后端会校验），但界面上不再单独填 ——
        // 训练轮数由「配置」弹窗里的算法参数 train-epochs 表达，这里保留既有默认值。
        trainEpochs: 360,
        trainBatchSize: 1024,
        evalPyId: null,
        /** 任务级脚本配置（JSON 字符串；空 = 沿用脚本文件配置） */
        trainConfig: null,
        evalConfig: null,
        /** 上面两份配置是「基于哪个脚本」配的：换脚本后旧配置要作废 */
        trainConfigPyId: null,
        evalConfigPyId: null,
        /**
         * 编辑已有任务时从详情带回的数据集信息（数据集现在只在「配置」里选）。
         * 仅回填 + 原样回传：老任务没有 config，后端解析不到数据集时用它兜底。
         */
        trainDataset: null,
        evalDataset: null
      },
      /** 任务级配置弹窗 */
      configDialogVisible: false,
      /** 当前在配哪张卡：'train' | 'eval' | ''（未打开） */
      configStep: ''
    }
  },
  computed: {
    visibleProxy: {
      get() {
        return this.visible
      },
      set(value) {
        this.$emit('update:visible', value)
      }
    },
    isEdit() {
      return !!this.taskId
    },
    dialogTitle() {
      return this.isEdit ? '编辑任务' : '新建任务'
    },
    /** 配置弹窗当前对应的脚本对象（含 fileName / algorithmConfig） */
    configScript() {
      if (this.configStep === 'train') {
        return this.findScript(this.trainScripts, this.form.trainPyId)
      }
      if (this.configStep === 'eval') {
        return this.findScript(this.evalScripts, this.form.evalPyId)
      }
      return null
    },
    /** 配置弹窗的初始配置：任务级配置优先，为空则由弹窗回落到脚本文件配置 */
    configDialogConfig() {
      if (this.configStep === 'train') {
        return this.form.trainConfig || ''
      }
      if (this.configStep === 'eval') {
        return this.form.evalConfig || ''
      }
      return ''
    },
    /**
     * 评估卡的固定参数：「训练模型」= 本任务 id（在评估的配置页面写死、不可删除）。
     *
     * <p>新建时任务 id 还不存在（由后端创建任务时生成），这里只做展示占位；
     * 真正写进配置的值由服务端注入（BaseDataService#withTrainModelParam），
     * 执行评估子任务时它会变成 {@code --train-task-id <父任务id>} 传给评估脚本。
     */
    configDialogLockedParams() {
      if (this.configStep !== 'eval') {
        return []
      }
      return [{
        name: '训练模型',
        param_name: 'train-task-id',
        value: this.taskId || '',
        placeholder: '（任务创建后自动写入本任务 id）',
        desc: '评估脚本据此加载 Multi-Agent 模型：'
          + '「重新训练」= 本任务的 <任务id>-train；「复用历史成功训练任务」= 所选任务的目录'
      }]
    },
    /**
     * 评估卡配置里「训练模型」（train-task-id）现在的取值（没配返回空串）。
     * 取值语义与后端一致：空 / 本任务 id / &lt;本任务id&gt;-train = 重新训练；其它 = 复用历史任务。
     */
    evalTrainTaskId() {
      const raw = this.form.evalConfig
      if (!raw) {
        return ''
      }
      let sections = null
      try {
        sections = JSON.parse(raw)
      } catch (error) {
        return ''
      }
      if (!Array.isArray(sections)) {
        return ''
      }
      for (const section of sections) {
        const params = (section && section.params) || []
        for (const p of params) {
          if (p && p.param_name === 'train-task-id') {
            return (p.value === null || p.value === undefined ? '' : String(p.value)).trim()
          }
        }
      }
      return ''
    },
    /** 本次任务是否「复用历史成功训练任务」（= 执行时只跑评估子任务、不训练）。 */
    isReuseTrainModel() {
      const value = this.evalTrainTaskId
      if (!value) {
        return false
      }
      const parent = this.taskId || ''
      if (!parent) {
        // 新建：父任务 id 还没生成，非空只可能是用户选的历史记录
        return true
      }
      return value !== parent && value !== `${parent}-train`
    },
    /** 复用的历史训练任务 id（非复用时空串） */
    reuseTrainTaskId() {
      return this.isReuseTrainModel ? this.evalTrainTaskId : ''
    },
    /**
     * 复用的历史训练任务展示文案：**任务名 · 时间**（与评估卡下拉里的写法一致）。
     * 按 id 去候选列表反查；查不到（例如那条历史任务的模型已被删）就说「历史训练任务」——
     * 一律不显示 32 位任务 id（太长，界面上放不下）。
     */
    reuseTrainTaskLabel() {
      const id = this.reuseTrainTaskId
      if (!id) {
        return ''
      }
      const hit = (this.trainTaskOptions || []).find((t) => t.taskId === id)
      if (!hit) {
        return '历史训练任务'
      }
      const name = hit.displayName || hit.taskName || ''
      const time = hit.timeText || hit.updated || ''
      if (!name) {
        // 老记录没有任务名：只用时间（与评估卡下拉一致）
        return time || '历史训练任务'
      }
      return time ? `${name} · ${time}` : name
    }
  },
  watch: {
    visible(value) {
      if (value) {
        this.initDialog()
      }
    },
    /**
     * 换脚本 → 之前为该任务改的配置不再对应，作废并回到新脚本文件自己的配置。
     * 用 trainConfigPyId 记「配置属于哪个脚本」，避免回填（loadDetail）时被这里误清。
     */
    'form.trainPyId'(value) {
      if (this.form.trainConfigPyId !== value) {
        this.form.trainConfig = null
        this.form.trainConfigPyId = null
      }
    },
    'form.evalPyId'(value) {
      if (this.form.evalConfigPyId !== value) {
        this.form.evalConfig = null
        this.form.evalConfigPyId = null
      }
    }
  },
  methods: {
    async initDialog() {
      if (!this.optionsLoaded) {
        await this.loadOptions()
      }
      if (this.isEdit) {
        await this.loadDetail()
      } else {
        this.resetForm()
      }
    },

    async loadOptions() {
      this.loading = true
      try {
        // 数据集不用在这里拉：改由卡片「配置」里的 train-schema / eval-schema 参数选择；
        // 「训练模型」下拉的候选（以往成功的训练任务）一并在这里拉一次
        const [trainRes, evalRes, modelRes] = await Promise.all([
          axios.get('/api/web/basedata/getPyFileList', { params: { scriptType: 'train' } }),
          axios.get('/api/web/basedata/getPyFileList', { params: { scriptType: 'eval' } }),
          axios.get('/api/web/basedata/getTrainModelTaskList')
        ])
        this.trainScripts = (trainRes.data && trainRes.data.data) || []
        this.evalScripts = (evalRes.data && evalRes.data.data) || []
        this.trainTaskOptions = (modelRes.data && modelRes.data.data) || []
        this.optionsLoaded = true
      } catch (error) {
        console.error('加载脚本选项失败:', error)
        this.$message.error('加载脚本选项失败，请检查后端服务')
      } finally {
        this.loading = false
      }
    },

    /**
     * 编辑模式：拉取任务详情并回填表单。
     * 先确保选项已加载，否则 el-select 找不到对应选项、会直接显示成裸 ID。
     */
    async loadDetail() {
      this.loading = true
      try {
        const response = await axios.get('/api/web/basedata/getPyTaskDetail', {
          params: { taskId: this.taskId }
        })
        const detail = response.data && response.data.data
        if (!response.data || response.data.code !== 0 || !detail) {
          this.$message.error((response.data && response.data.message) || '加载任务配置失败')
          this.visibleProxy = false
          return
        }
        const train = detail.trainConfig || {}
        const evaluation = detail.evalConfig || {}
        // 引用的脚本可能在任务创建之后被停用或删除，补占位选项避免下拉空白
        this.ensureScriptOption(this.trainScripts, train.pyId, train.scriptName)
        this.ensureScriptOption(this.evalScripts, evaluation.pyId, evaluation.scriptName)

        this.form.taskName = detail.taskName || ''
        this.form.trainPyId = train.pyId || null
        this.form.trainEpochs = train.trainEpochs || this.form.trainEpochs
        this.form.trainBatchSize = train.trainBatchSize || this.form.trainBatchSize
        this.form.evalPyId = evaluation.pyId || null
        // 数据集：卡片上不再选，这里只把库里已有的值带回，提交时原样回传做兜底
        this.form.trainDataset = (train.datasetId || train.schemaKey)
          ? { datasetId: train.datasetId, schemaKey: train.schemaKey, datasetName: train.datasetName }
          : null
        this.form.evalDataset = (evaluation.datasetId || evaluation.schemaKey)
          ? {
            datasetId: evaluation.datasetId,
            schemaKey: evaluation.schemaKey,
            datasetName: evaluation.datasetName
          }
          : null
        // 任务级配置：记上它属于哪个脚本，避免下面的 script watcher 把回填的内容清掉
        this.form.trainConfig = train.config || null
        this.form.trainConfigPyId = train.config ? (train.pyId || null) : null
        this.form.evalConfig = evaluation.config || null
        this.form.evalConfigPyId = evaluation.config ? (evaluation.pyId || null) : null
      } catch (error) {
        console.error('加载任务配置失败:', error)
        this.$message.error('加载任务配置失败：' + (error.message || '网络错误'))
        this.visibleProxy = false
      } finally {
        this.loading = false
      }
    },

    /**
     * 新建模式的表单重置。
     * 任务名称预填一个带时间的默认值：既不挡着创建，又能直接改 ——
     * 列表的「任务名称」列本来就靠它显示，留空会让那一列没内容。
     */
    resetForm() {
      this.form.taskName = `训练+评估 ${this.nowStamp()}`
      this.form.trainPyId = null
      this.form.trainEpochs = 360
      this.form.trainBatchSize = 1024
      this.form.evalPyId = null
      this.form.trainConfig = null
      this.form.evalConfig = null
      this.form.trainConfigPyId = null
      this.form.evalConfigPyId = null
      this.form.trainDataset = null
      this.form.evalDataset = null
      this.configStep = ''
      this.configDialogVisible = false
      this.applySingleOptionDefaults()
    },

    nowStamp() {
      const now = new Date()
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
    },

    /** 只有一个候选时自动选中，省一次点击 */
    applySingleOptionDefaults() {
      if (this.trainScripts.length === 1) {
        this.form.trainPyId = this.form.trainPyId || this.trainScripts[0].id
      }
      if (this.evalScripts.length === 1) {
        this.form.evalPyId = this.form.evalPyId || this.evalScripts[0].id
      }
    },

    /** 详情引用的脚本可能已被停用/删除，补一个带提示的占位选项避免下拉空白 */
    ensureScriptOption(list, id, fileName) {
      if (!id || list.some((file) => file.id === id)) {
        return
      }
      list.push({ id, fileName: (fileName || '未知脚本') + '（已停用或已删除）' })
    },

    findScript(list, id) {
      return list.find((file) => file.id === id) || null
    },

    /* ---------------- 任务级脚本配置 ---------------- */

    /** 点「配置」：选中脚本后可用；弹窗自己会把脚本文件里的配置带出来回填 */
    openStepConfig(step) {
      const pyId = step === 'train' ? this.form.trainPyId : this.form.evalPyId
      if (!pyId) {
        this.$message.warning(step === 'train' ? '请先选择训练脚本' : '请先选择评估脚本')
        return
      }
      this.configStep = step
      this.configDialogVisible = true
    },

    /** 配置弹窗「确定」：只更新本任务的表单，不落脚本文件 */
    onStepConfigSaved(configJson) {
      if (this.configStep === 'train') {
        this.form.trainConfig = configJson
        this.form.trainConfigPyId = this.form.trainPyId
      } else if (this.configStep === 'eval') {
        this.form.evalConfig = configJson
        this.form.evalConfigPyId = this.form.evalPyId
      }
    },

    /** 「配置」按钮右侧的状态文案（只有已保存过配置时才会渲染） */
    configStatusText(configJson) {
      const count = this.countConfigItems(configJson)
      return count > 0 ? `已配置 ${count} 项参数` : '已保存配置'
    },

    /**
     * 统计配置里的参数项数，兼容两种格式：
     *   新格式（分组）[{type,params:[...]}, ...] → 各 params 长度之和
     *   旧格式（扁平）[{id,...}, ...]          → 数组长度
     */
    countConfigItems(configJson) {
      if (!configJson) {
        return 0
      }
      let parsed = null
      try {
        parsed = typeof configJson === 'string' ? JSON.parse(configJson) : configJson
      } catch (error) {
        return 0
      }
      if (!Array.isArray(parsed)) {
        return 0
      }
      if (parsed.length && parsed[0] && Array.isArray(parsed[0].params)) {
        return parsed.reduce((acc, sec) => acc + ((sec && Array.isArray(sec.params)) ? sec.params.length : 0), 0)
      }
      return parsed.filter((item) => item && item.id).length
    },

    /** 提交前校验：返回错误文案；全部通过返回空串 */
    validate() {
      if (!this.form.taskName || !this.form.taskName.trim()) {
        return '请填写任务名称'
      }
      // 复用历史训练模型时不产生训练子任务 ⇒ 训练卡不必填（后端也跳过训练卡校验）
      if (!this.isReuseTrainModel) {
        if (!this.form.trainPyId) {
          return '请选择训练脚本'
        }
        if (!this.form.trainEpochs || this.form.trainEpochs <= 0) {
          return '训练轮数必须大于 0'
        }
        if (!this.form.trainBatchSize || this.form.trainBatchSize <= 0) {
          return '训练批大小必须大于 0'
        }
      }
      if (!this.form.evalPyId) {
        return '请选择评估脚本'
      }
      if (this.isReuseTrainModel && !this.reuseTrainTaskId) {
        return '请选择要复用的历史训练任务（在评估卡的「配置」里）'
      }
      return ''
    },

    /**
     * 卡片配置。
     * 数据集不在卡片上选：后端优先从 config 里的 train-schema / eval-schema 参数
     * 解析出 datasetId / schemaKey / datasetName；解析不到时用下面带回的旧值兜底。
     */
    buildTrainConfig() {
      const script = this.findScript(this.trainScripts, this.form.trainPyId)
      const dataset = this.form.trainDataset || {}
      return {
        pyId: this.form.trainPyId,
        scriptName: script ? script.fileName : null,
        datasetId: dataset.datasetId != null ? dataset.datasetId : null,
        schemaKey: dataset.schemaKey || null,
        datasetName: dataset.datasetName || null,
        trainEpochs: this.form.trainEpochs,
        trainBatchSize: this.form.trainBatchSize,
        // 任务级脚本配置覆盖；空表示运行时沿用脚本文件自身的配置
        config: this.form.trainConfig || null
      }
    },

    buildEvalConfig() {
      const script = this.findScript(this.evalScripts, this.form.evalPyId)
      const dataset = this.form.evalDataset || {}
      return {
        pyId: this.form.evalPyId,
        scriptName: script ? script.fileName : null,
        datasetId: dataset.datasetId != null ? dataset.datasetId : null,
        schemaKey: dataset.schemaKey || null,
        datasetName: dataset.datasetName || null,
        config: this.form.evalConfig || null
      }
    },

    async submit() {
      const errorText = this.validate()
      if (errorText) {
        this.$message.warning(errorText)
        return
      }
      this.submitting = true
      try {
        const payload = {
          taskName: this.form.taskName.trim(),
          trainConfig: this.buildTrainConfig(),
          evalConfig: this.buildEvalConfig()
        }
        let response
        if (this.isEdit) {
          response = await axios.post('/api/web/basedata/updatePipelineTask', {
            ...payload,
            taskId: this.taskId
          })
        } else {
          response = await axios.post('/api/web/basedata/createPipelineTask', payload)
        }
        if (response.data && response.data.code === 0) {
          this.$message.success(this.isEdit ? '任务已保存' : '任务创建成功')
          this.$emit('saved', response.data.data)
          this.visibleProxy = false
        } else {
          this.$message.error((response.data && response.data.message) || (this.isEdit ? '保存失败' : '创建失败'))
        }
      } catch (error) {
        console.error('保存任务失败:', error)
        this.$message.error('保存失败：' + (error.message || '网络错误'))
      } finally {
        this.submitting = false
      }
    },

    onClosed() {
      // 关闭后清掉表单，避免下次打开时残留上一个任务的内容
      this.form.taskName = ''
      this.form.trainPyId = null
      this.form.evalPyId = null
      this.form.trainConfig = null
      this.form.evalConfig = null
      this.form.trainConfigPyId = null
      this.form.evalConfigPyId = null
      this.form.trainDataset = null
      this.form.evalDataset = null
      this.configStep = ''
      this.configDialogVisible = false
    }
  }
}
</script>

<style scoped>
/* 「配置」按钮 + 状态文案同一行 */
.config-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-status {
  font-size: 12px;
  color: var(--secondary-text-color);
}

.config-status.is-set {
  color: var(--primary-color, #409eff);
}

.dialog-hint {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--secondary-text-color);
}

.pipeline-task-body {
  min-height: 280px;
}

.name-field {
  margin-bottom: 16px;
}

.pipeline-flow {
  display: flex;
  align-items: stretch;
  min-height: 260px;
}

/* ---------- 卡片 ---------- */
.flow-card {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--divider-color, #e4e7ed);
  border-radius: 10px;
  overflow: hidden;
  background: #ffffff;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(90deg, rgba(64, 158, 255, 0.12), rgba(64, 158, 255, 0.02));
  border-bottom: 1px solid var(--divider-color, #e4e7ed);
}

.card-index {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary-color, #409eff);
  color: #ffffff;
  font-size: 12px;
  line-height: 22px;
  text-align: center;
}

.card-head-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.card-title {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--primary-text-color);
}

.card-sub {
  font-size: 12px;
  line-height: 1.4;
  color: var(--secondary-text-color);
}

.card-body {
  flex: 1 1 auto;
  padding: 16px;
}

/* ---------- 字段 ---------- */
.field {
  margin-bottom: 14px;
}

.field:last-child {
  margin-bottom: 0;
}

.field-row {
  display: flex;
  gap: 12px;
}

.field-row .field {
  flex: 1 1 0;
  min-width: 0;
}

.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--primary-text-color);
}

.field-control {
  width: 100%;
}

.field-hint {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--secondary-text-color);
}


/* ---------- 中间箭头 ---------- */
.flow-arrow {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  width: 76px;
  padding: 0 8px;
  color: var(--primary-color, #409eff);
}

.arrow-line {
  flex: 1 1 auto;
  height: 2px;
  background: linear-gradient(90deg, rgba(64, 158, 255, 0.2), var(--primary-color, #409eff));
}

.arrow-head {
  flex: 0 0 auto;
  margin-left: -5px;
  font-size: 20px;
  line-height: 1;
}
</style>
