<template>
  <div class="algorithm-param-page ha-page">
    <div class="page-header ha-toolbar">
      <div>
        <h2 class="page-title">参数配置</h2>
      </div>
      <div class="header-actions">
        <!-- 配置组详情：把该组的成员操作放在最显眼的位置 -->
        <template v-if="inSetDetail">
          <el-button icon="el-icon-folder-add" @click="openPicker">从已有配置添加</el-button>
          <el-button type="primary" icon="el-icon-plus" @click="openAddDialog">添加配置</el-button>
        </template>
        <el-button
          v-else
          type="primary"
          icon="el-icon-plus"
          @click="activeTab === 'alone' ? openAddDialog() : openAddSetDialog()"
        >
          {{ activeTab === 'alone' ? '添加配置' : '新建配置组' }}
        </el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never" class="table-card">
      <!-- ============ 配置组详情：显示该组下所有参数，可添加/编辑 ============ -->
      <div v-if="inSetDetail" class="set-detail">
        <div class="detail-head">
          <el-button type="text" icon="el-icon-back" @click="closeSetDetail">返回配置组</el-button>
          <div class="detail-title">
            <span class="set-name">{{ activeSet.name }}</span>
            <el-tag size="mini" type="info" class="member-tag">{{ memberCount }} 个参数</el-tag>
          </div>
          <p class="detail-desc ha-muted">{{ activeSet.desc || '暂无简介' }}</p>
        </div>

        <el-table :data="activeSet.members" stripe style="width: 100%">
          <el-table-column label="名称" min-width="180">
            <template slot-scope="{ row }">
              <span class="param-name">{{ row.name }}</span>
              <el-tag v-if="row.ifSystem" size="mini" type="warning" class="sys-tag">系统</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="默认参数名" min-width="180">
            <template slot-scope="{ row }">
              <span class="param-key">{{ row.paramName }}</span>
            </template>
          </el-table-column>

          <el-table-column label="简介" min-width="240">
            <template slot-scope="{ row }">
              <span :class="{ 'ha-muted': !row.desc }">{{ row.desc || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="创建时间" width="170">
            <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
          </el-table-column>

          <el-table-column label="操作" width="160" fixed="right">
            <template slot-scope="{ row }">
              <el-button type="text" @click="openEditDialog(row)">编辑</el-button>
              <el-button type="text" class="danger-text" @click="removeMember(row)">移出组</el-button>
            </template>
          </el-table-column>

          <template slot="empty">
            <span class="ha-muted">该组还没有参数，点右上角「添加配置」或「从已有配置添加」</span>
          </template>
        </el-table>
      </div>

      <!-- ============ 页签：单独配置 / 配置组 ============ -->
      <el-tabs v-else v-model="activeTab">
        <!-- ---------- 单独配置：未加入任何配置组的参数 ---------- -->
        <el-tab-pane label="单独配置" name="alone">
          <el-table :data="list" stripe style="width: 100%">
            <el-table-column label="名称" min-width="180">
              <template slot-scope="{ row }">
                <span class="param-name">{{ row.name }}</span>
                <el-tag v-if="row.ifSystem" size="mini" type="warning" class="sys-tag">系统</el-tag>
              </template>
            </el-table-column>

            <el-table-column label="默认参数名" min-width="180">
              <template slot-scope="{ row }">
                <span class="param-key">{{ row.paramName }}</span>
              </template>
            </el-table-column>

            <el-table-column label="简介" min-width="260">
              <template slot-scope="{ row }">
                <span :class="{ 'ha-muted': !row.desc }">{{ row.desc || '—' }}</span>
              </template>
            </el-table-column>

            <el-table-column label="创建时间" width="170">
              <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
            </el-table-column>

            <el-table-column label="操作" width="150" fixed="right">
              <template slot-scope="{ row }">
                <el-button type="text" @click="openEditDialog(row)">编辑</el-button>
                <!-- 系统内置参数不提供删除：后端也会拒绝（deleteAlgorithmParamConfig） -->
                <el-button
                  v-if="!row.ifSystem"
                  type="text"
                  class="danger-text"
                  title="删除该参数"
                  @click="handleDelete(row)"
                >删除</el-button>
              </template>
            </el-table-column>

            <template slot="empty">
              <span class="ha-muted">暂无独立参数，点右上角「添加配置」新增</span>
            </template>
          </el-table>
        </el-tab-pane>

        <!-- ---------- 配置组：组清单，点详情进入组内参数页 ---------- -->
        <el-tab-pane label="配置组" name="set">
          <el-table :data="sets" stripe style="width: 100%">
            <el-table-column label="组名称" min-width="200">
              <template slot-scope="{ row }">
                <span class="param-name">{{ row.name }}</span>
                <el-tag size="mini" type="info" class="sys-tag">{{ row.memberCount || 0 }} 个参数</el-tag>
              </template>
            </el-table-column>

            <el-table-column label="创建时间" width="170">
              <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
            </el-table-column>

            <el-table-column label="简介" min-width="280">
              <template slot-scope="{ row }">
                <span :class="{ 'ha-muted': !row.desc }">{{ row.desc || '—' }}</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="180" fixed="right">
              <template slot-scope="{ row }">
                <el-button type="text" @click="openSetDetail(row)">详情</el-button>
                <el-button type="text" @click="openEditSetDialog(row)">编辑</el-button>
                <!-- 组内有参数时不允许删除：后端也会拒绝（deleteAlgorithmParamConfigSet） -->
                <el-button
                  type="text"
                  class="danger-text"
                  :disabled="!!row.memberCount"
                  :title="row.memberCount ? '组内还有参数，先全部移出后才能删除' : '删除该配置组'"
                  @click="handleDeleteSet(row)"
                >删除</el-button>
              </template>
            </el-table-column>

            <template slot="empty">
              <span class="ha-muted">暂无配置组，点右上角「新建配置组」创建</span>
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ============ 参数新增 / 编辑弹窗 ============ -->
    <el-dialog
      :title="dialogMode === 'add' ? '添加配置' : '编辑配置'"
      :visible.sync="dialogVisible"
      :width="isMapType ? '800px' : '620px'"
      top="8vh"
      :close-on-click-modal="false"
      @opened="onParamDialogOpened"
      @closed="resetDialog"
    >
      <p v-if="isSystemRow" class="sys-hint">
        <i class="el-icon-info" />
        系统内置参数：仅可编辑「简介」，其余字段锁定（可能已被历史脚本配置引用）。
      </p>
      <p v-else-if="dialogMode === 'add' && inSetDetail" class="sys-hint">
        <i class="el-icon-info" />
        该参数保存后会直接加入配置组「{{ activeSet.name }}」
      </p>

      <el-form ref="dialogForm" :model="dialogForm" :rules="dialogRules" label-width="96px">
        <el-form-item label="名称" prop="name">
          <el-input
            v-model="dialogForm.name"
            maxlength="128"
            clearable
            :disabled="isSystemRow"
            placeholder="界面显示的名称，如：评估数据集"
          />
        </el-form-item>

        <el-form-item label="默认参数名" prop="paramName">
          <el-input
            v-model="dialogForm.paramName"
            maxlength="128"
            clearable
            :disabled="isSystemRow"
            placeholder="参数标识，如：eval-schema"
          />
        </el-form-item>

        <el-form-item label="值类型" prop="valueType">
          <el-select
            v-model="dialogForm.valueType"
            :disabled="isSystemRow"
            placeholder="请选择值类型"
            style="width: 100%"
            @change="onValueTypeChange"
          >
            <el-option
              v-for="opt in valueTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="简介" prop="desc">
          <el-input
            v-model="dialogForm.desc"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
            placeholder="参数说明，鼠标悬浮名称旁的小叹号时显示"
          />
        </el-form-item>
      </el-form>

      <!-- 单选 / 多选 / 键值对：下方生成一个卡片维护内容（key/value 形式） -->
      <div v-if="isOptionType" class="option-card">
        <div class="option-card-head">
          <div>
            <span class="option-card-title">{{ isMapType ? '键值对' : '候选项' }}</span>
            <span class="ha-muted option-card-hint">{{ optionCardHint }}</span>
          </div>
          <el-button
            type="primary"
            plain
            size="mini"
            icon="el-icon-plus"
            :disabled="isSystemRow"
            @click="addOption"
          >{{ optionAddLabel }}</el-button>
        </div>

        <!-- 键值对：可以给 key / value 起别名，界面就不再显示生硬的 key/value -->
        <div v-if="isMapType" class="alias-row">
          <el-input
            v-model="dialogForm.keyAlias"
            size="small"
            class="alias-input"
            :disabled="isSystemRow"
            placeholder="键的别名，如：选择时段"
          />
          <el-input
            v-model="dialogForm.valueAlias"
            size="small"
            class="alias-input"
            :disabled="isSystemRow"
            placeholder="值的别名，如：电池 SOC 下限"
          />
          <span class="alias-tip ha-muted">（别名只影响界面显示）</span>
        </div>

        <div v-if="!dialogForm.options.length" class="option-empty ha-muted">
          还没有内容，点「{{ optionAddLabel }}」新增
        </div>

        <div
          v-for="(opt, index) in dialogForm.options"
          :key="opt.uid"
          class="option-row"
          :class="{ 'option-row-active': isMapType && index === mapSelectedIndex }"
        >
          <el-input
            v-model="opt.key"
            size="small"
            class="option-input"
            :disabled="isSystemRow"
            :placeholder="keyPlaceholder"
          />
          <el-input
            v-model="opt.value"
            size="small"
            class="option-input"
            :disabled="isSystemRow"
            :placeholder="valuePlaceholder"
          />
          <el-button
            type="text"
            size="small"
            class="danger-text option-del"
            :disabled="isSystemRow"
            title="删除该项"
            @click="removeOption(index)"
          >
            <i class="el-icon-delete" />
          </el-button>
        </div>

        <!-- 键值对：下方柱状图，操作方式同「24 小时 SOC 下限柱状图」 -->
        <div v-if="isMapType" class="map-chart-wrap">
          <p class="ha-muted map-chart-hint">
            点柱子选中一行；把鼠标放在<strong>选中的柱子</strong>内滚动滚轮，可按 {{ mapChartStep }} 微调该行的值
          </p>
          <div ref="mapChart" class="map-chart"></div>
        </div>
      </div>

      <div slot="footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDialog">确定</el-button>
      </div>
    </el-dialog>

    <!-- ============ 配置组新增 / 编辑弹窗 ============ -->
    <el-dialog
      :title="setDialogMode === 'add' ? '新建配置组' : '编辑配置组'"
      :visible.sync="setDialogVisible"
      width="520px"
      :close-on-click-modal="false"
      @closed="resetSetDialog"
    >
      <el-form ref="setForm" :model="setForm" :rules="setRules" label-width="88px">
        <el-form-item label="组名称" prop="name">
          <el-input v-model="setForm.name" maxlength="128" clearable placeholder="如：电价感知电池参数" />
        </el-form-item>
        <el-form-item label="简介" prop="desc">
          <el-input
            v-model="setForm.desc"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
            placeholder="这组参数是做什么的（选填）"
          />
        </el-form-item>
      </el-form>
      <p class="ha-muted dialog-tip">
        成员在组详情页里维护：可以新建参数，也可以从「单独配置」里挑已有的加进来。
      </p>
      <div slot="footer">
        <el-button @click="setDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="setSaving" @click="submitSetDialog">确定</el-button>
      </div>
    </el-dialog>

    <!-- ============ 从已有配置里挑成员 ============ -->
    <el-dialog
      title="从已有配置添加"
      :visible.sync="pickerVisible"
      width="820px"
      top="8vh"
      :close-on-click-modal="false"
      @closed="resetPicker"
    >
      <p class="ha-muted dialog-tip">
        下面列出的是「单独配置」页签里、未加入任何配置组的参数。勾选后确定即加入本组。<br>
        系统内置参数（由平台预置、全局共享）不能加入配置组，已从列表中排除。
      </p>
      <el-table
        ref="pickerTable"
        v-loading="pickerLoading"
        :data="pickerCandidates"
        height="360"
        stripe
        @selection-change="onPickerSelectionChange"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column label="名称" min-width="160">
          <template slot-scope="{ row }">
            <span class="param-name">{{ row.name }}</span>
            <el-tag v-if="row.ifSystem" size="mini" type="warning" class="sys-tag">系统</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="paramName" label="默认参数名" min-width="170" />
        <el-table-column label="简介" min-width="220">
          <template slot-scope="{ row }">
            <span :class="{ 'ha-muted': !row.desc }">{{ row.desc || '—' }}</span>
          </template>
        </el-table-column>
        <template slot="empty">
          <span class="ha-muted">
            没有可加入的参数：独立参数都已在配置组里，或只剩系统内置参数（不可入组）
          </span>
        </template>
      </el-table>
      <div slot="footer">
        <el-button @click="pickerVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!pickerSelected.length" :loading="saving" @click="submitPicker">
          确定加入（已选 {{ pickerSelected.length }} 个）
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import axios from 'axios'
import * as echarts from 'echarts'

/**
 * 值类型下拉的固定选项。
 * label 只写中文，不带括号里的库内取值 —— 那是给开发看的，不该出现在界面上。
 * 「单选 / 多选 / 键值对」都要配内容（存在 default_value），其余类型该列为 NULL。
 * 存量数据里的 special 是历史值（数据集下拉），仅在编辑到它时追加显示。
 */
const VALUE_TYPES = [
  { value: 'num', label: '数字' },
  { value: 'text', label: '文字' },
  { value: 'bool', label: '布尔' },
  { value: 'ratio', label: '单选' },
  { value: 'multiple', label: '多选' },
  { value: 'map', label: '键值对' }
]

const SPECIAL_OPTION = { value: 'special', label: '数据集' }

/** 需要维护「候选项 / 键值对」卡片的值类型（内容都存在 default_value 里） */
const OPTION_TYPES = ['ratio', 'multiple', 'map']

/** 键值对类型：额外支持给 key / value 起别名，并在下方画柱状图 */
const MAP_TYPE = 'map'

let optionUid = 0

export default {
  name: 'AlgorithmParamConfig',
  data() {
    return {
      /** 页签：alone=单独配置，set=配置组 */
      activeTab: 'alone',
      loading: false,
      saving: false,

      /** 单独配置：未加入任何配置组的参数（is_member=0） */
      list: [],

      /** 配置组清单 */
      sets: [],

      /** 配置组详情；非 null 表示当前正在看某个组（此时隐藏页签） */
      activeSet: null,

      /** 参数新增/编辑弹窗 */
      dialogVisible: false,
      dialogMode: 'add',
      dialogForm: {
        id: null,
        name: '',
        paramName: '',
        valueType: 'text',
        desc: '',
        ifSystem: false,
        options: [],
        // 仅 map 用：键 / 值的别名
        keyAlias: '',
        valueAlias: ''
      },
      /** map 编辑弹窗下方柱状图的 ECharts 实例 */
      mapChart: null,
      /** 柱状图当前选中的行下标（点柱子切换，滚轮只对选中柱子生效） */
      mapSelectedIndex: 0,
      dialogRules: {
        name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
        paramName: [{ required: true, message: '请输入默认参数名', trigger: 'blur' }],
        valueType: [{ required: true, message: '请选择值类型', trigger: 'change' }]
      },

      /** 配置组新增/编辑弹窗 */
      setDialogVisible: false,
      setDialogMode: 'add',
      setSaving: false,
      setForm: { id: null, name: '', desc: '' },
      setRules: {
        name: [{ required: true, message: '请输入组名称', trigger: 'blur' }]
      },

      /** 「从已有配置添加」弹窗 */
      pickerVisible: false,
      pickerLoading: false,
      pickerCandidates: [],
      pickerSelected: []
    }
  },
  computed: {
    /** 是否正处于配置组详情视图 */
    inSetDetail() {
      return !!this.activeSet
    },
    memberCount() {
      return (this.activeSet && this.activeSet.members && this.activeSet.members.length) || 0
    },
    /** 编辑中的是否为系统内置参数：系统参数只允许改简介 */
    isSystemRow() {
      return this.dialogMode === 'edit' && !!this.dialogForm.ifSystem
    },
    /** 当前值类型是否需要维护内容卡片（单选 / 多选 / 键值对） */
    isOptionType() {
      return OPTION_TYPES.indexOf(this.dialogForm.valueType) >= 0
    },
    /** 当前是否为「键值对」类型 */
    isMapType() {
      return this.dialogForm.valueType === MAP_TYPE
    },
    /** 卡片副标题：键值对讲 key/value 的语义，单选/多选讲候选值 */
    optionCardHint() {
      return this.isMapType
        ? '左侧为键、右侧为值；键值对会一起存进脚本配置'
        : 'key = 实际存进脚本配置的取值，value = 界面显示文字'
    },
    /** 新增按钮文案 */
    optionAddLabel() {
      return this.isMapType ? '添加一项' : '添加选项'
    },
    /** 行内两列输入框的占位文案（map 用别名，其余用 key/value） */
    keyPlaceholder() {
      const alias = (this.dialogForm.keyAlias || '').trim()
      return this.isMapType ? (alias || '键') + '（如 high）' : 'key（如 high）'
    },
    valuePlaceholder() {
      const alias = (this.dialogForm.valueAlias || '').trim()
      return this.isMapType ? (alias || '值') + '（如 0.6）' : '显示文字（如 高峰）'
    },
    /** 柱状图上每根柱子的数值（非数字按 0 处理） */
    mapChartValues() {
      return this.dialogForm.options.map((opt) => this.toFiniteNumber(opt.value))
    },
    /**
     * 柱状图 Y 轴上界。map 没有单位概念，按数据量级给一个整的上界：
     *   ≤1  → 1（占比类，如 min_soc_per_hour 的 0~1）
     *   ≤10 → 10；≤100 → 100；再大就向上取整到 100 的倍数
     * 全 0 时给 1，避免出现一条压扁的轴。
     */
    mapChartMax() {
      const max = Math.max(0, ...this.mapChartValues)
      if (max <= 1) return 1
      if (max <= 10) return 10
      if (max <= 100) return 100
      return Math.ceil(max / 100) * 100
    },
    /** 滚轮微调步长：跟着 Y 轴量级走，避免大数值只能一次挪 0.01 */
    mapChartStep() {
      const max = this.mapChartMax
      if (max <= 1) return 0.01
      if (max <= 10) return 0.1
      return 1
    },
    /** 值类型下拉：存量数据是 special 时补上该项，避免打开编辑就把它悄悄改掉 */
    valueTypeOptions() {
      const options = VALUE_TYPES.slice()
      if (this.dialogForm.valueType === 'special') {
        options.push(SPECIAL_OPTION)
      }
      return options
    }
  },
  watch: {
    activeTab(value) {
      if (value === 'alone') {
        this.fetchList()
      } else {
        this.fetchSets()
      }
    },
    /** 切换值类型后，map 的柱状图要么出现要么消失；离开 map 要销毁实例（DOM 已被 v-if 移走） */
    'dialogForm.valueType'() {
      if (!this.isMapType) {
        this.destroyMapChart()
        return
      }
      this.mapSelectedIndex = 0
      this.$nextTick(() => this.renderMapChart())
    },
    /**
     * 键值对改动（含滚轮微调）后重画柱状图。
     * renderMapChart 只读 options、不改它，所以不会反过来触发本 watcher。
     */
    'dialogForm.options': {
      deep: true,
      handler() {
        this.$nextTick(() => this.renderMapChart())
      }
    },
    /**
     * 点柱子改变选中行后必须重画。
     * 柱子的高亮色是在 renderMapChart 里按 mapSelectedIndex 算的，
     * 少了这个 watcher 就会出现「选中态确实变了、但颜色还停在第 0 根柱子」。
     */
    mapSelectedIndex() {
      this.$nextTick(() => this.renderMapChart())
    }
  },
  created() {
    this.fetchList()
  },
  beforeDestroy() {
    this.destroyMapChart()
  },
  methods: {
    formatTime(val) {
      if (!val) return '—'
      const d = new Date(val)
      if (Number.isNaN(d.getTime())) return String(val)
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    },

    /* ---------------- 数据加载 ---------------- */

    /** 单独配置：只取 is_member=0 的参数 */
    async fetchList() {
      this.loading = true
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigList', {
          params: { isMember: 0 }
        })
        if (res.data && res.data.code === 0) {
          this.list = res.data.data || []
        } else {
          this.$message.error((res.data && res.data.message) || '加载参数列表失败')
        }
      } catch (e) {
        this.$message.error('加载参数列表失败')
      } finally {
        this.loading = false
      }
    },

    async fetchSets() {
      this.loading = true
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigSetList')
        if (res.data && res.data.code === 0) {
          this.sets = res.data.data || []
        } else {
          this.$message.error((res.data && res.data.message) || '加载配置组失败')
        }
      } catch (e) {
        this.$message.error('加载配置组失败')
      } finally {
        this.loading = false
      }
    },

    /** 打开配置组详情（用 id 重新拉，保证成员/标记都是最新的） */
    async openSetDetail(row) {
      if (!row || !row.id) return
      this.loading = true
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigSetDetail', {
          params: { id: row.id }
        })
        if (res.data && res.data.code === 0) {
          const detail = res.data.data || {}
          this.activeSet = {
            id: detail.id,
            name: detail.name,
            desc: detail.desc,
            members: detail.members || []
          }
        } else {
          this.$message.error((res.data && res.data.message) || '加载配置组详情失败')
        }
      } catch (e) {
        this.$message.error('加载配置组详情失败')
      } finally {
        this.loading = false
      }
    },

    closeSetDetail() {
      this.activeSet = null
      this.fetchSets()
    },

    /**
     * 参数发生增删改后刷新当前视图：
     * 组详情里只刷该组，单独配置页签刷列表。
     */
    refreshCurrentView() {
      if (this.inSetDetail) {
        return this.openSetDetail({ id: this.activeSet.id })
      }
      return this.fetchList()
    },

    /* ---------------- 参数：新增 / 编辑 / 删除 ---------------- */

    /** 解析后端下发的 default_value（JSON 数组字符串）→ 编辑用的候选项行 */
    parseOptions(raw) {
      if (!raw) return []
      let arr = raw
      if (typeof raw === 'string') {
        try {
          arr = JSON.parse(raw)
        } catch (e) {
          // 脏数据不阻塞页面：当作没有候选项
          console.warn('[参数配置] default_value 不是合法 JSON，已忽略:', raw)
          return []
        }
      }
      if (!Array.isArray(arr)) return []
      return arr.map((item) => ({
        uid: 'opt-' + optionUid++,
        key: item && item.key != null ? String(item.key) : '',
        value: item && item.value != null ? String(item.value) : ''
      }))
    },

    openAddDialog() {
      this.dialogMode = 'add'
      this.resetDialog()
      this.dialogVisible = true
    },

    openEditDialog(row) {
      this.dialogMode = 'edit'
      this.dialogForm = {
        id: row.id,
        name: row.name || '',
        paramName: row.paramName || '',
        // 历史数据的 value_type 可能是空（等价普通文本），界面统一按「文字」呈现
        valueType: row.valueType || 'text',
        desc: row.desc || '',
        ifSystem: !!row.ifSystem,
        options: this.parseOptions(row.defaultValue),
        keyAlias: row.keyAlias || '',
        valueAlias: row.valueAlias || ''
      }
      this.mapSelectedIndex = 0
      this.dialogVisible = true
      this.$nextTick(() => {
        if (this.$refs.dialogForm) this.$refs.dialogForm.clearValidate()
      })
    },

    resetDialog() {
      this.destroyMapChart()
      this.dialogForm = {
        id: null,
        name: '',
        paramName: '',
        valueType: 'text',
        desc: '',
        ifSystem: false,
        options: [],
        keyAlias: '',
        valueAlias: ''
      }
      this.mapSelectedIndex = 0
      this.dialogMode = 'add'
      if (this.$refs.dialogForm) {
        this.$refs.dialogForm.clearValidate()
      }
    },

    /** 值类型切换：离开「单选/多选/键值对」时清空内容，避免把过期数据带给后端 */
    onValueTypeChange(value) {
      if (OPTION_TYPES.indexOf(value) < 0) {
        this.dialogForm.options = []
        return
      }
      if (!this.dialogForm.options.length) {
        this.addOption()
      }
    },

    addOption() {
      this.dialogForm.options.push({ uid: 'opt-' + optionUid++, key: '', value: '' })
    },

    removeOption(index) {
      this.dialogForm.options.splice(index, 1)
      if (this.mapSelectedIndex >= this.dialogForm.options.length) {
        this.mapSelectedIndex = Math.max(0, this.dialogForm.options.length - 1)
      }
    },

    /* ---------------- 键值对（map）柱状图 ---------------- */

    /** 文本 → 有限数字；非数字一律按 0，避免一个空值把整张图带崩 */
    toFiniteNumber(value) {
      const num = Number(value)
      return Number.isFinite(num) ? num : 0
    },

    /** 数字 → 去掉浮点噪声的字符串（滚轮 ±0.01 容易出现 0.30000000000000004） */
    formatNumber(value) {
      const num = Number(value)
      if (!Number.isFinite(num)) return ''
      return String(Number(num.toFixed(4)))
    },

    /** 弹窗打开动画结束后初始化/重画（此时容器才有尺寸，echarts 才能正确取宽高） */
    onParamDialogOpened() {
      this.$nextTick(() => this.renderMapChart())
    },

    /**
     * 画键值对柱状图（仅 map 类型会走到这里）。
     * 操作方式与「24 小时 SOC 下限柱状图」一致：
     *   点柱子 → 选中对应那一行（选中行高亮、柱子上色）；
     *   滚轮   → 在选中的柱体上滚动，按 mapChartStep 微调该行的值。
     */
    renderMapChart() {
      const el = this.$refs.mapChart
      if (!el || !this.isMapType) return
      if (!this.mapChart) {
        this.mapChart = echarts.init(el)
        this.mapChart.on('click', this.handleMapChartClick)
        // passive:false 才能 preventDefault，否则页面/弹窗会跟着一起滚
        el.addEventListener('wheel', this.handleMapChartWheel, { passive: false })
      }
      const rows = this.dialogForm.options
      const keys = rows.map((row, index) => {
        const key = (row.key || '').trim()
        return key || `#${index + 1}`
      })
      const selected = this.mapSelectedIndex
      this.mapChart.setOption({
        animation: true,
        animationDuration: 200,
        grid: { left: 52, right: 16, top: 18, bottom: keys.length > 12 ? 52 : 30 },
        tooltip: { trigger: 'axis' },
        xAxis: {
          type: 'category',
          data: keys,
          axisLabel: {
            fontSize: 10,
            interval: 0,
            rotate: keys.length > 12 ? 45 : 0
          }
        },
        yAxis: {
          type: 'value',
          min: 0,
          max: this.mapChartMax,
          splitLine: { lineStyle: { type: 'dashed' } }
        },
        series: [{
          type: 'bar',
          barMaxWidth: 28,
          data: rows.map((row, index) => ({
            value: this.toFiniteNumber(row.value),
            itemStyle: { color: index === selected ? '#409eff' : '#a0cfff' }
          }))
        }]
      }, true)
      this.mapChart.resize()
    },

    /** 点柱子 → 选中那一行（与 SOC 下限图一致：先选中，滚轮才对该行生效） */
    handleMapChartClick(params) {
      if (params == null || params.componentType !== 'series') return
      const index = Number(params.dataIndex)
      if (!Number.isInteger(index) || index < 0 || index >= this.dialogForm.options.length) return
      this.mapSelectedIndex = index
    },

    /**
     * 滚轮微调：只对「选中的那根柱子、且指针落在柱体实心区域内」生效，
     * 每次 ±mapChartStep（量级 ≤1 的数据为 0.01，0~100 的为 1）。
     */
    handleMapChartWheel(event) {
      if (!this.mapChart || !this.dialogForm.options.length) return
      const point = [event.offsetX, event.offsetY]
      if (!this.mapChart.containPixel('grid', point)) return
      const dataCoord = this.mapChart.convertFromPixel({ seriesIndex: 0 }, point)
      if (!Array.isArray(dataCoord) || dataCoord.length < 2) return

      const index = Math.round(dataCoord[0])
      if (index !== this.mapSelectedIndex || index < 0 || index >= this.dialogForm.options.length) return
      if (Math.abs(dataCoord[0] - index) > 0.45) return

      const current = this.toFiniteNumber(this.dialogForm.options[index].value)
      if (dataCoord[1] < 0 || dataCoord[1] > current) return // 只有落在柱体里才响应

      event.preventDefault()
      const step = this.mapChartStep
      const next = Math.max(0, current + (event.deltaY < 0 ? step : -step))
      this.dialogForm.options[index].value = this.formatNumber(next)
    },

    destroyMapChart() {
      const el = this.$refs.mapChart
      if (this.mapChart) {
        this.mapChart.off('click', this.handleMapChartClick)
        this.mapChart.dispose()
        this.mapChart = null
      }
      if (el) {
        el.removeEventListener('wheel', this.handleMapChartWheel)
      }
    },

    /** 候选项 / 键值对 → 提交给后端的 JSON 数组字符串 */
    buildOptionsPayload() {
      if (!this.isOptionType) return null
      const rows = this.dialogForm.options
        .map((opt) => ({ key: (opt.key || '').trim(), value: (opt.value || '').trim() }))
        .filter((opt) => opt.key)
      return JSON.stringify(rows)
    },

    /** 提交前的本地校验（后端的校验仍是最终防线） */
    validateOptions() {
      // 系统参数只能改简介，内容不参与提交，无需校验
      if (this.isSystemRow || !this.isOptionType) return true
      const keys = []
      for (let i = 0; i < this.dialogForm.options.length; i++) {
        const opt = this.dialogForm.options[i]
        const key = (opt.key || '').trim()
        if (!key) {
          this.$message.warning(`第 ${i + 1} 项的 key 不能为空`)
          return false
        }
        if (keys.indexOf(key) >= 0) {
          this.$message.warning(`key 重复：${key}`)
          return false
        }
        keys.push(key)
      }
      if (!keys.length) {
        this.$message.warning('值类型为单选 / 多选 / 键值对时，至少配置一项')
        return false
      }
      return true
    },

    submitDialog() {
      this.$refs.dialogForm.validate(async (valid) => {
        if (!valid) return
        if (!this.validateOptions()) return
        this.saving = true
        try {
          const payload = {
            id: this.dialogForm.id,
            name: (this.dialogForm.name || '').trim(),
            paramName: (this.dialogForm.paramName || '').trim(),
            valueType: this.dialogForm.valueType,
            defaultValue: this.buildOptionsPayload(),
            // 键值对类型才带别名；其它类型留空，后端也会归一成 NULL
            keyAlias: this.isMapType ? (this.dialogForm.keyAlias || '').trim() : '',
            valueAlias: this.isMapType ? (this.dialogForm.valueAlias || '').trim() : '',
            desc: (this.dialogForm.desc || '').trim()
          }
          // 在配置组详情里新建的参数，保存后自动入组
          if (this.dialogMode === 'add' && this.inSetDetail) {
            payload.setId = this.activeSet.id
          }
          const url = this.dialogMode === 'add'
            ? '/api/web/basedata/addAlgorithmParamConfig'
            : '/api/web/basedata/updateAlgorithmParamConfig'
          const res = await axios.post(url, payload)
          if (res.data && res.data.code === 0) {
            this.$message.success(this.dialogMode === 'add' ? '添加成功' : '保存成功')
            this.dialogVisible = false
            this.refreshCurrentView()
          } else {
            this.$message.error((res.data && res.data.message) || '操作失败')
          }
        } catch (e) {
          this.$message.error('操作失败')
        } finally {
          this.saving = false
        }
      })
    },

    handleDelete(row) {
      if (row.ifSystem) {
        this.$message.warning('系统内置参数不可删除')
        return
      }
      this.$confirm(
        `确定删除参数「${row.name}」吗？已使用该参数的脚本配置不会自动清理。`,
        '删除确认',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
      )
        .then(async () => {
          const res = await axios.post('/api/web/basedata/deleteAlgorithmParamConfig', { id: row.id })
          if (res.data && res.data.code === 0) {
            this.$message.success('已删除')
            this.refreshCurrentView()
          } else {
            this.$message.error((res.data && res.data.message) || '删除失败')
          }
        })
        .catch(() => {})
    },

    /* ---------------- 配置组：新增 / 编辑 / 删除 ---------------- */

    openAddSetDialog() {
      this.setDialogMode = 'add'
      this.resetSetDialog()
      this.setDialogVisible = true
    },

    openEditSetDialog(row) {
      this.setDialogMode = 'edit'
      this.setForm = { id: row.id, name: row.name || '', desc: row.desc || '' }
      this.setDialogVisible = true
      this.$nextTick(() => {
        if (this.$refs.setForm) this.$refs.setForm.clearValidate()
      })
    },

    resetSetDialog() {
      this.setForm = { id: null, name: '', desc: '' }
      this.setDialogMode = 'add'
      if (this.$refs.setForm) {
        this.$refs.setForm.clearValidate()
      }
    },

    submitSetDialog() {
      this.$refs.setForm.validate(async (valid) => {
        if (!valid) return
        this.setSaving = true
        try {
          const isAdd = this.setDialogMode === 'add'
          const res = await axios.post(
            isAdd
              ? '/api/web/basedata/addAlgorithmParamConfigSet'
              : '/api/web/basedata/updateAlgorithmParamConfigSet',
            {
              id: this.setForm.id,
              name: (this.setForm.name || '').trim(),
              desc: (this.setForm.desc || '').trim()
            }
          )
          if (res.data && res.data.code === 0) {
            this.$message.success(isAdd ? '创建成功' : '保存成功')
            this.setDialogVisible = false
            this.fetchSets()
            if (isAdd && res.data.data && res.data.data.id) {
              // 新建后直接进详情，省得再找一次
              this.openSetDetail({ id: res.data.data.id })
            }
          } else {
            this.$message.error((res.data && res.data.message) || '操作失败')
          }
        } catch (e) {
          this.$message.error('操作失败')
        } finally {
          this.setSaving = false
        }
      })
    },

    handleDeleteSet(row) {
      if (row.memberCount) {
        this.$message.warning(`配置组内还有 ${row.memberCount} 个参数，请先全部移出后再删除`)
        return
      }
      this.$confirm(
        `确定删除配置组「${row.name}」吗？`,
        '删除确认',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
      )
        .then(async () => {
          const res = await axios.post('/api/web/basedata/deleteAlgorithmParamConfigSet', { id: row.id })
          if (res.data && res.data.code === 0) {
            this.$message.success('已删除')
            this.fetchSets()
            if (this.inSetDetail && this.activeSet.id === row.id) {
              this.activeSet = null
            }
          } else {
            this.$message.error((res.data && res.data.message) || '删除失败')
          }
        })
        .catch(() => {})
    },

    /* ---------------- 组成员：加入 / 移出 ---------------- */

    /** 用新的成员列表覆盖当前组（名称/简介原样带回，后端会一并写入） */
    async saveMemberIds(memberIds, successText) {
      this.saving = true
      try {
        const res = await axios.post('/api/web/basedata/updateAlgorithmParamConfigSet', {
          id: this.activeSet.id,
          name: this.activeSet.name,
          desc: this.activeSet.desc,
          memberIds
        })
        if (res.data && res.data.code === 0) {
          this.$message.success(successText)
          await this.openSetDetail({ id: this.activeSet.id })
          return true
        }
        this.$message.error((res.data && res.data.message) || '操作失败')
        return false
      } catch (e) {
        this.$message.error('操作失败')
        return false
      } finally {
        this.saving = false
      }
    },

    async openPicker() {
      this.pickerSelected = []
      this.pickerVisible = true
      this.pickerLoading = true
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigList', {
          params: { isMember: 0 }
        })
        // 系统内置参数不允许入组，直接不列出来（后端也会拒绝）
        this.pickerCandidates = ((res.data && res.data.data) || []).filter((item) => !item.ifSystem)
      } catch (e) {
        this.$message.error('加载可选参数失败')
      } finally {
        this.pickerLoading = false
      }
    },

    onPickerSelectionChange(rows) {
      this.pickerSelected = rows || []
    },

    resetPicker() {
      this.pickerCandidates = []
      this.pickerSelected = []
    },

    async submitPicker() {
      if (!this.pickerSelected.length) {
        this.$message.warning('请至少勾选一个参数')
        return
      }
      const current = (this.activeSet.members || []).map((m) => m.id)
      const added = this.pickerSelected.map((r) => r.id)
      const memberIds = current.concat(added.filter((id) => current.indexOf(id) < 0))
      const ok = await this.saveMemberIds(memberIds, `已加入 ${this.pickerSelected.length} 个参数`)
      if (ok) {
        this.pickerVisible = false
      }
    },

    removeMember(row) {
      this.$confirm(
        `确定把「${row.name}」移出配置组「${this.activeSet.name}」吗？参数本身不会被删除，会回到「单独配置」。`,
        '移出配置组',
        { type: 'warning', confirmButtonText: '移出', cancelButtonText: '取消' }
      )
        .then(async () => {
          const memberIds = (this.activeSet.members || [])
            .filter((m) => m.id !== row.id)
            .map((m) => m.id)
          await this.saveMemberIds(memberIds, '已移出配置组')
        })
        .catch(() => {})
    }
  }
}
</script>

<style scoped>
.algorithm-param-page {
  padding: 20px 24px 32px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: var(--primary-text-color);
}


.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.table-card {
  border-radius: 12px;
}

.param-name {
  color: var(--primary-text-color);
}

.param-key {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: var(--primary-text-color);
}

.sys-tag {
  margin-left: 8px;
}

.member-tag {
  margin-left: 8px;
}

.danger-text {
  color: var(--error-color, #db4437) !important;
}

.sys-hint {
  margin: 0 0 16px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--secondary-background-color, #f5f7fa);
  color: var(--secondary-text-color);
  font-size: 13px;
  line-height: 1.6;
}

.dialog-tip {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.6;
}

/* ---------- 配置组详情 ---------- */
.detail-head {
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--divider-color, #ebeef5);
}

.detail-title {
  display: flex;
  align-items: center;
  margin-top: 6px;
}

.set-name {
  font-size: 16px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.detail-desc {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

/* 单选 / 多选的候选项卡片 */
.option-card {
  margin: 0 0 8px;
  padding: 12px 14px;
  border: 1px solid var(--divider-color, #ebeef5);
  border-radius: 8px;
  background: var(--secondary-background-color, #fafafa);
}

.option-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.option-card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.option-card-hint {
  margin-left: 8px;
  font-size: 12px;
}

.option-empty {
  font-size: 12px;
  padding: 6px 0;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.option-input {
  flex: 1 1 0;
}

.option-del {
  flex: 0 0 auto;
}

/* 键值对：key / value 别名输入行 */
.alias-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.alias-input {
  flex: 1 1 0;
}

.alias-tip {
  flex: 0 0 auto;
  font-size: 12px;
}

/* 当前选中的键值对行（与柱状图选中态联动） */
.option-row-active .option-input >>> .el-input__inner {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.06);
}

/* 键值对下方的柱状图 */
.map-chart-wrap {
  margin-top: 6px;
}

.map-chart-hint {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.6;
}

.map-chart {
  width: 100%;
  height: 220px;
}
</style>
