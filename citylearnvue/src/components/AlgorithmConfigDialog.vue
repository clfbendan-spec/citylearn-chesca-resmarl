<template>
  <!-- 两个弹窗（主配置 + 键值对子弹窗）需要一个共同根节点，否则 Vue 2 报多根 -->
  <div class="algorithm-config-dialog-root">
  <el-dialog
    title="算法配置"
    :visible.sync="visibleProxy"
    width="920px"
    top="8vh"
    custom-class="algorithm-config-dialog"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <!-- 添加参数 / 添加配置组：两个独立下拉，分别加到默认参数 section 与新 section -->
    <div class="add-bar">
      <!--
        「添加参数」下拉只列 isMember=0 的目录参数（即不在任何配置组里的参数）。
        下游若改了配置组成员（把某参数从某组移出去），需要重新打开弹窗才会重新列出。
      -->
      <el-dropdown trigger="click" @command="addRow">
        <el-button type="primary" plain icon="el-icon-plus" :loading="optionsLoading">
          添加参数
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item
            v-for="opt in addableOptions"
            :key="opt.id"
            :command="opt.id"
          >
            {{ opt.name }}（{{ opt.paramName }}）
            <span v-if="opt.ifSystem" class="sys-flag">系统</span>
          </el-dropdown-item>
          <el-dropdown-item v-if="!addableOptions.length" disabled>
            可添加的参数已全部添加
          </el-dropdown-item>
          <!-- 页面专属项：不在算法参数目录（algorithm_param_config）里，点了直接加一行全部手填的参数 -->
          <el-dropdown-item divided :command="customCommand">
            <i class="el-icon-edit-outline" /> 自定义参数
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <!-- 「添加配置组」下拉：列出当前还没被加进当前脚本的所有配置组 -->
      <el-dropdown trigger="click" @command="addSet">
        <el-button plain icon="el-icon-folder-add" :loading="setsLoading">
          添加配置组
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item
            v-for="s in addableSets"
            :key="s.id"
            :command="s.id"
          >
            {{ s.name }}<span class="set-meta-inline">（{{ s.memberCount || 0 }} 项）</span>
          </el-dropdown-item>
          <el-dropdown-item v-if="!addableSets.length" disabled>
            可添加的配置组已全部添加
          </el-dropdown-item>
          <el-dropdown-item v-if="!sets.length && !setsLoading" disabled>
            暂无可用的配置组（去「参数配置」页新建）
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <span class="ha-muted add-hint">
        共 {{ totalRowCount }} 项配置 · {{ sections.length }} 个分组
      </span>
    </div>

    <!--
      多张 section 卡片：
        · 第一个 section.kind === 'alone'（默认参数卡），永远在最上方
        · 其后每个 kind === 'set' 的卡片来自配置组，按用户添加顺序排列
      每张卡片有独立滚动（moveRow 时只滚本卡片内部的 scrollTop）。
    -->
    <div
      v-for="section in sections"
      :key="section.key"
      class="section-card"
      :class="{
        'section-card-set': section.kind === 'set',
        'section-card-collapsed': section.collapsed,
        'section-card-drag-over': dragOverKey === section.key
      }"
      :ref="el => bindSectionEl(section.key, el)"
      @dragover="onSectionDragOver($event, section.key)"
      @dragleave="onSectionDragLeave($event, section.key)"
      @drop="onSectionDrop($event, section)"
    >
      <div class="section-head">
        <div class="section-head-left">
          <i
            :class="section.kind === 'alone' ? 'el-icon-document' : 'el-icon-folder'"
            class="section-head-icon"
          />
          <!--
            配置组的标题可点击 → 打开成员管理弹窗；
            标题后面挂一个小叹号，悬停显示配置组自身的简介（set.desc）。
            单独配置的标题不可点，也不需要叹号。
          -->
          <span
            v-if="section.kind === 'set'"
            class="section-title section-title-clickable"
            title="点击管理该配置组的成员"
            @click="openSetMemberDialog(section)"
          >{{ section.title }}</span>
          <span v-else class="section-title">{{ section.title }}</span>
          <!-- 配置组的简介叹号：放在标题后面 -->
          <el-tooltip
            v-if="section.kind === 'set'"
            placement="top"
            effect="light"
            popper-class="alg-set-desc-popper"
          >
            <div slot="content" class="desc-pop">
              <p v-if="setDescOf(section)" class="desc-pop-text">{{ setDescOf(section) }}</p>
              <p v-else class="desc-pop-text desc-pop-empty">该配置组暂无简介</p>
            </div>
            <i class="el-icon-warning-outline desc-icon set-desc-icon" />
          </el-tooltip>
        </div>
        <div class="section-head-right">
          <!-- 折叠 / 展开按钮（每张卡片各自独立） -->
          <el-button
            type="text"
            size="mini"
            class="collapse-btn"
            :title="section.collapsed ? '展开' : '收起'"
            @click="toggleCollapse(section)"
          >
            <i :class="section.collapsed ? 'el-icon-arrow-down' : 'el-icon-arrow-up'" />
            <span class="collapse-text">{{ section.collapsed ? '展开' : '收起' }}</span>
          </el-button>
          <!-- 配置组卡片：右侧一个「移除整个配置组」按钮 -->
          <el-button
            v-if="section.kind === 'set'"
            type="text"
            size="small"
            class="danger-text-btn"
            title="移除该配置组（其下参数会一并从当前脚本移除）"
            @click="removeSetSection(section.key)"
          >
            <i class="el-icon-delete" /> 移除配置组
          </el-button>
        </div>
      </div>

      <!-- 主体：折叠时 v-show 隐藏但保留 DOM，避免展开时丢失输入框焦点 / 滚动位置 -->
      <div v-show="!section.collapsed" v-if="section.rows.length" class="cfg-table">
        <div class="cfg-head">
          <!-- 排序列：表头不写字，只占位，和行里的上/下箭头对齐 -->
          <div class="col-sort" />
          <div class="col-name">名称</div>
          <div class="col-param">参数名</div>
          <div class="col-value">值</div>
          <div class="col-op" />
        </div>

        <div
          v-for="(row, index) in section.rows"
          :key="row.key"
          class="cfg-row"
          :class="{
            'cfg-row-custom': row.custom,
            'cfg-row-locked': row.locked,
            'cfg-row-draggable': isRowDraggable(row),
            'cfg-row-dragging': draggingFrom && draggingFrom.row === row
          }"
          :draggable="isRowDraggable(row) ? 'true' : 'false'"
          @dragstart="onRowDragStart($event, section, row, index)"
          @dragend="onRowDragEnd"
        >
          <!--
            上/下箭头调整顺序：行的先后就是保存进 py_file.algorithm_config 的 JSON 顺序，
            也决定下游拼命令行时参数的先后。首行禁用「上移」、末行禁用「下移」。
            排序范围 =当前 section 内部（每张卡片各自独立排序）。
            固定参数（row.locked）不参与排序：它必须待在默认参数表里且不可移动。
          -->
          <div class="col-sort">
            <el-button
              v-if="!row.locked"
              type="text"
              size="mini"
              class="sort-btn"
              title="上移"
              :disabled="index === 0 || (section.rows[index - 1] && section.rows[index - 1].locked)"
              @click="moveRow(section.key, index, -1)"
            >
              <i class="el-icon-arrow-up" />
            </el-button>
            <el-button
              v-if="!row.locked"
              type="text"
              size="mini"
              class="sort-btn"
              title="下移"
              :disabled="index === section.rows.length - 1"
              @click="moveRow(section.key, index, 1)"
            >
              <i class="el-icon-arrow-down" />
            </el-button>
          </div>

          <div class="col-name">
            <!-- 自定义参数：名称手填；目录参数：名称只读 -->
            <el-input
              v-if="row.custom"
              v-model="row.name"
              size="small"
              class="name-input"
              placeholder="请输入名称"
              :disabled="row.locked"
              clearable
            />
            <span v-else class="cfg-name" :title="row.name">{{ row.name }}</span>

            <!--
              名称右侧的小叹号：鼠标悬浮显示参数简介（desc）。
              弹层里「简介下方还有一行输入框」，写的是这条参数自己的补充说明，存 JSON 的 extra_desc。
                · 目录参数：上面显示目录里的 desc（没配则提示「暂无简介」），下面是输入框
                · 自定义参数：没有 desc，弹层里就只有这个输入框，可直接编辑
              （el-tooltip 的弹层支持鼠标移入不关闭，所以里面可以放可编辑的输入框）
            -->
            <el-tooltip placement="top" effect="light" popper-class="alg-desc-popper">
              <div slot="content" class="desc-pop">
                <p v-if="row.desc" class="desc-pop-text">{{ row.desc }}</p>
                <p v-else-if="!row.custom" class="desc-pop-text desc-pop-empty">该参数暂无简介</p>
                <el-input
                  v-if="!row.locked"
                  v-model="row.extraDesc"
                  size="mini"
                  class="desc-pop-input"
                  placeholder="补充说明（选填）"
                  clearable
                />
              </div>
              <i class="el-icon-warning-outline desc-icon" />
            </el-tooltip>

            <em v-if="row.ifSystem" class="sys-tag">系统</em>
            <!-- 固定参数（任务编排注入）标记：与「系统」并列，提示这行不可动 -->
            <em v-if="row.locked" class="sys-tag locked-tag">固定</em>
          </div>

          <div class="col-param">
            <!-- 自定义参数：参数名只给一个输入框；目录参数：原始参数名 + 别名输入框 -->
            <el-input
              v-if="row.custom"
              v-model="row.alias"
              size="small"
              class="alias-input"
              placeholder="请输入参数名"
              :disabled="row.locked"
              clearable
            />
            <template v-else>
              <span class="base-param" :title="row.baseParamName">{{ row.baseParamName }}</span>
              <el-input
                v-model="row.alias"
                size="small"
                class="alias-input"
                :placeholder="row.baseParamName"
                :disabled="row.locked"
                clearable
              />
            </template>
          </div>

          <div class="col-value">
            <!--
              值这一列用哪个控件，由配置表 algorithm_param_config.value_type 决定（后端下发 row.valueType）：
                num      → 数字输入框，只能输入数字
                bool     → 开关，存 JSON 布尔值 true / false
                special  → 数据集下拉，值是 citylearn_dataset.id
                ratio    → 单选下拉，候选项来自该参数的 default_value，存的是选项 key
                multiple → 多选下拉，候选项同上，存的是选项 key 的数组
                map      → 键值对，列宽放不下，用按钮开子弹窗编辑，存 [{key,value}] 的 JSON
                其它     → 普通文本输入框
            -->
            <!--
              固定参数「训练模型」：任务编排的评估卡里换成选择器 ——
              「重新训练」（后端注入父任务 id，本次先训练）或「复用历史成功训练任务」（本次只评估）。
            -->
            <div
              v-if="row.locked && row.lockedParamName === 'train-task-id' && trainModelPicker"
              class="train-model-picker"
            >
              <el-select
                v-model="trainModelMode"
                size="small"
                class="value-control"
                @change="onTrainModelModeChange"
              >
                <el-option label="重新训练（先训练再评估）" value="retrain" />
                <el-option label="复用历史成功训练任务" value="hist" />
              </el-select>
              <el-select
                v-if="trainModelMode === 'hist'"
                v-model="trainModelTaskId"
                placeholder="选择历史训练任务"
                filterable
                size="small"
                class="value-control"
                @change="onTrainModelTaskChange"
              >
                <el-option
                  v-for="t in trainTaskOptions"
                  :key="'train-task-' + t.taskId"
                  :label="trainTaskLabel(t)"
                  :value="t.taskId"
                  :disabled="t.modelReady === false"
                >
                  <!-- 标签只留「任务名 · 时间」；脚本 / 轮数 / 任务 id 挪到悬停提示，免得选项太长 -->
                  <span :title="trainTaskTooltip(t)">{{ trainTaskLabel(t) }}</span>
                </el-option>
              </el-select>
            </div>
            <el-select
              v-else-if="row.valueType === 'special'"
              v-model="row.value"
              placeholder="请选择数据集"
              filterable
              size="small"
              class="value-control"
            >
              <el-option
                v-for="ds in datasets"
                :key="'ds-' + ds.id"
                :label="datasetLabel(ds)"
                :value="ds.id"
              />
            </el-select>
            <el-select
              v-else-if="row.valueType === 'ratio'"
              v-model="row.value"
              placeholder="请选择"
              size="small"
              clearable
              class="value-control"
            >
              <el-option
                v-for="opt in row.valueOptions"
                :key="'ratio-' + opt.key"
                :label="opt.label"
                :value="opt.key"
              />
            </el-select>
            <el-select
              v-else-if="row.valueType === 'multiple'"
              v-model="row.value"
              multiple
              collapse-tags
              placeholder="请选择（可多选）"
              size="small"
              class="value-control"
            >
              <el-option
                v-for="opt in row.valueOptions"
                :key="'multi-' + opt.key"
                :label="opt.label"
                :value="opt.key"
              />
            </el-select>
            <!-- 键值对：值这一列放不下，用按钮开子弹窗编辑 -->
            <el-button
              v-else-if="row.valueType === 'map'"
              size="small"
              class="value-control map-value-btn"
              :class="{ 'map-value-empty': !mapItemCount(row) }"
              @click="openMapEditor(row)"
            >{{ mapButtonLabel(row) }}</el-button>
            <el-switch
              v-else-if="row.valueType === 'bool'"
              v-model="row.value"
              active-text="开启"
              inactive-text="关闭"
              class="value-control"
            />
            <el-input
              v-else-if="row.valueType === 'num'"
              :value="row.value"
              size="small"
              class="value-control"
              placeholder="请输入数字"
              @input="onNumValueInput(row, $event)"
            />
            <el-input
              v-else
              v-model="row.value"
              size="small"
              class="value-control"
              :placeholder="row.placeholder || '请输入值'"
              :disabled="row.locked"
            />
          </div>

          <div class="col-op">
            <!-- 固定参数没有删除入口：任务编排要用的值必须一直在 -->
            <el-button
              v-if="!row.locked"
              type="text"
              size="small"
              class="danger-text-btn"
              title="移除该参数"
              @click="removeRow(section.key, index)"
            >
              <i class="el-icon-delete" />
            </el-button>
            <span v-else class="locked-param-tag">不可修改</span>
          </div>
        </div>
      </div>

      <div v-else class="empty-tip ha-muted">
        暂无参数，点上方「添加参数」或「添加配置组」即可
      </div>
    </div>

    <div slot="footer">
      <el-button @click="visibleProxy = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </div>
  </el-dialog>

    <!-- ============ 成员管理弹窗（点配置组标题打开） ============ -->
    <el-dialog
      :title="setMemberDialogTitle"
      :visible.sync="setMemberDialogVisible"
      width="640px"
      top="8vh"
      append-to-body
      :close-on-click-modal="false"
      @close="cancelMemberDialog"
    >
      <p class="ha-muted map-tip">
        勾选 / 取消当前配置组里的成员。取消勾选只是从<strong>本脚本</strong>移除该参数，
        不会改动算法参数目录里该配置组的定义。临时参数（自添加）不在此弹窗内。
      </p>
      <div v-if="!setMemberEditingSection || !(setMemberEditingSection.originalMembers || []).length"
           class="empty-tip ha-muted">
        该配置组没有原始成员（可能配置组为空，或成员已被算法参数目录删除）
      </div>
      <template v-else>
        <div class="member-toolbar">
          <el-button size="mini" @click="toggleAllMembers(true)">全选</el-button>
          <el-button size="mini" @click="toggleAllMembers(false)">全不选</el-button>
          <span class="ha-muted member-stat">
            已选 {{ includedCount }} / {{ totalCount }}
          </span>
        </div>
        <div class="member-list">
          <label
            v-for="m in setMemberEditingSection.originalMembers"
            :key="'mem-' + m.id"
            class="member-item"
          >
            <el-checkbox
              :value="!!setMemberDraftIncluded[m.id]"
              @change="toggleMemberInSection(m.id)"
            />
            <span class="member-name">{{ m.name || ('参数 #' + m.id) }}</span>
            <span class="member-param">{{ m.paramName }}</span>
            <span v-if="m.desc" class="member-desc ha-muted">{{ m.desc }}</span>
          </label>
        </div>
      </template>
      <div slot="footer">
        <el-button @click="cancelMemberDialog">取消</el-button>
        <el-button type="primary" @click="applyMemberDialog">
          {{ persist ? '应用到当前脚本' : '应用到当前配置' }}
        </el-button>
      </div>
    </el-dialog>

    <!-- ============ 键值对（map）编辑子弹窗 ============ -->
    <el-dialog
      :title="mapDialogTitle"
      :visible.sync="mapDialogVisible"
      width="760px"
      top="8vh"
      append-to-body
      :close-on-click-modal="false"
      @opened="onMapDialogOpened"
      @closed="onMapDialogClosed"
    >
      <p class="ha-muted map-tip">
        这里编辑键值对本身，「确定」后只写回上面那一行；点弹窗的「保存」才真正落到脚本配置里。
      </p>

      <!-- 键 / 值的别名取自参数定义，让界面不说生硬的 key / value -->
      <div class="map-alias-row">
        <span class="map-alias-item">{{ mapAlias.key }}</span>
        <span class="map-alias-item">{{ mapAlias.value }}</span>
      </div>

      <div v-if="!mapDraft.length" class="map-empty ha-muted">
        还没有键值对，点下方「添加一项」新增，或「恢复参数默认值」
      </div>

      <div
        v-for="(item, index) in mapDraft"
        :key="item.uid"
        class="map-row"
        :class="{ 'map-row-active': index === mapSelectedIndex }"
      >
        <el-input v-model="item.key" size="small" class="map-input" :placeholder="mapAlias.key" />
        <el-input v-model="item.value" size="small" class="map-input" :placeholder="mapAlias.value" />
        <el-button
          type="text"
          size="small"
          class="danger-text map-del"
          title="删除该项"
          @click="removeMapItem(index)"
        >
          <i class="el-icon-delete" />
        </el-button>
      </div>

      <div class="map-actions">
        <el-button size="mini" icon="el-icon-plus" @click="addMapItem">添加一项</el-button>
        <el-button
          size="mini"
          icon="el-icon-refresh-left"
          :disabled="!resetMapAvailable"
          title="用参数定义里的默认键值对覆盖当前内容"
          @click="resetMapFromOption"
        >恢复参数默认值</el-button>
      </div>

      <p class="ha-muted map-chart-hint">
        点柱子选中一行；把鼠标放在<strong>选中的柱子</strong>内滚动滚轮，可按 {{ mapChartStep }} 微调该行的值
      </p>
      <div ref="mapChart" class="map-chart"></div>

      <div slot="footer">
        <el-button @click="mapDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmMapEdit">确定</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import axios from 'axios'
import * as echarts from 'echarts'

/**
 * 算法配置弹窗（代码编辑器文件列表选中 train / eval 脚本后点「配置」）。
 *
 * 数据来源
 *   可选参数目录  GET /api/web/basedata/getAlgorithmParamConfigList  (algorithm_param_config)
 *   数据集选项    GET /api/web/basedata/getDatasetList               (citylearn_dataset，仅启用)
 * 保存
 *   POST /api/web/basedata/savePyFileAlgorithmConfig
 *     body { id: pyFile.id, algorithmConfig: '[{"type":"alone","params":[...]}]' }
 *     落库为 v2 分组格式，详见下方 buildSectionsFromFile / submit 的说明
 *   persist=false 时跳过该接口，只 emit('saved', json) —— 任务管理页用它把配置
 *   挂到当前任务上（不回写脚本文件）
 *
 * 目录参数（algorithm_param_config）里有四个字段会影响界面：
 *   value_type    值这一列用什么控件：
 *                   num=只允许输入数字；text/NULL=普通文本；special=数据集下拉；
 *                   bool=开关；ratio=单选下拉；multiple=多选下拉；map=键值对（子弹窗）
 *   default_value ratio / multiple 的候选项，以及 map 的键值对，
 *                 均为 JSON 数组 [{"key":"..","value":".."}]；
 *                 key 是存进配置的真实取值，value 是界面显示文字
 *   key_alias / value_alias
 *                 map 专用：键、值的别名（如「选择时段」「电池 SOC 下限」）
 *   desc          参数简介：名称右侧的小叹号，鼠标悬浮时显示
 *
 * 保存的 JSON 里：
 *   id         = algorithm_param_config.id（自定义参数是页面生成的 uuid）
 *   param_name = 参数别名（第二列右侧输入框）；留空时回落到原始参数名，
 *                这样下游要拼命令行时永远能拿到「最终参数名」，不必再去查目录
 *   value      = 参数值；数据集类参数存 citylearn_dataset.id；
 *                bool 存 JSON 布尔值（true / false）；
 *                ratio 存选项 key；multiple 存选项 key 的 JSON 数组（如 ["a","b"]）；
 *                map 存键值对的 JSON 数组（如 [{"key":"0","value":"0.6"}]）
 *   extra_desc = 补充说明（名称右侧叹号弹层里的输入框，选填；空则不写这个字段）
 *   type       = 仅自定义参数有，固定 "extra"，用来与目录参数区分
 */
export default {
  name: 'AlgorithmConfigDialog',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    /** 当前脚本（getPyFileList 返回的对象，含 id / fileName / scriptType / algorithmConfig） */
    pyFile: {
      type: Object,
      default: null
    },
    /**
     * 初始配置 JSON 字符串。非空时优先于 pyFile.algorithmConfig ——
     * 任务管理页「新建任务」用它把「已保存在该任务上的配置」带出来回填。
     */
    config: {
      type: String,
      default: ''
    },
    /**
     * 保存方式：
     *   true （默认）= 写回脚本文件（py_file.algorithm_config），代码编辑器用；
     *   false = 不落库，只 emit('saved', json)，由调用方决定存哪里（任务级配置用）。
     */
    persist: {
      type: Boolean,
      default: true
    },
    /**
     * 固定参数（任务编排注入，如评估卡的「训练模型」= 父任务 id）：
     * 只在弹窗顶部展示，**不可删除**，也不进保存的 JSON —— 服务端保存任务时会重新写入
     * （见 BaseDataService#withTrainModelParam），保证值始终是权威的那一份。
     */
    lockedParams: {
      type: Array,
      default: () => []
    },
    /**
     * 「训练模型」选择器（任务管理页评估卡专用）：
     * true 时，固定参数 train-task-id 的「值」列渲染成
     * 「重新训练 / 复用历史成功训练任务」两级选择器，而不是只读输入框。
     *
     * 取值语义（与后端 BaseDataService 完全一致）：
     *   空，或 = 本任务 id / &lt;本任务id&gt;-train → 重新训练（后端会注入父任务 id）
     *   其它非空值                                → 复用该历史训练任务的模型（本次不再训练）
     */
    trainModelPicker: {
      type: Boolean,
      default: false
    },
    /** 「复用历史成功训练任务」的候选（后端 getTrainModelTaskList 下发） */
    trainTaskOptions: {
      type: Array,
      default: () => []
    },
    /** 本任务的父任务 id（编辑时用它区分"重新训练"与"复用历史"） */
    parentTaskId: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      optionsLoading: false,
      setsLoading: false,
      saving: false,
      /** 「训练模型」选择器：'retrain' 重新训练 / 'hist' 复用历史成功训练任务 */
      trainModelMode: 'retrain',
      /** 选中要复用的历史训练任务 id（trainModelMode === 'hist' 时有效） */
      trainModelTaskId: '',
      /** 可选参数目录（algorithm_param_config）—— 仅「不在任何配置组」的参数 */
      options: [],
      /** 配置组清单（algorithm_param_config_set）—— 用于「添加配置组」按钮 */
      sets: [],
      /** 启用中的数据集 */
      datasets: [],
      /**
       * 界面上的配置块（section）列表，按顺序渲染成「默认参数卡片 + 配置组卡片」。
       * 第一个一定是 kind:'alone'（单独配置）；其后每个 kind:'set' 的卡片代表一个
       * 「从配置组载入」的快照。
       *
       * 单个 section 的形状：
       *   {
       *     key:      'alone' | 'set-<setId>'，列表渲染时的稳定 key
       *     kind:     'alone' | 'set'
       *     title:    卡片标题
       *     setId?:   仅 kind='set' 时存在；保存到 JSON 时回填
       *     setName?: 仅 kind='set' 时存在，便于用户看清组名
       *     rows:     参数行（同原来 rows 中元素的形状）
       *     collapsed?:       是否收起（每张卡片各自控制；true 时表头可见、主体隐藏）
       *     originalMembers?: 仅 kind='set' 时存在；该配置组原始成员列表（来自
       *                       getAlgorithmParamConfigSetDetail.members），
       *                       用于「成员管理」弹窗的勾选列表，
       *                       临时参数（custom=true）不出现在这里
       *   }
       */
      sections: [],
      /**
       * 「添加配置组」弹窗状态：候选下拉里展示 sets，
       * 选中一个 set 后调用 getAlgorithmParamConfigSetDetail 拉成员，再 addSet()。
       */
      setPickerVisible: false,
      setPickerLoading: false,
      setPickerError: '',
      /** 已经添加过的 set 集合（key 是 setId）：避免重复添加同一组 */
      addedSetIds: [],
      /** el-dropdown 里「自定义参数」项的 command 值（仅页面内用，不落库、不在目录里） */
      customCommand: '_custom_',
      /** 自定义参数落库时打的 type 标记，用来和目录参数（无此字段）区分 */
      customType: 'extra',

      /* ---------- 键值对（map）子弹窗 ---------- */
      mapDialogVisible: false,
      /** 正在编辑的配置行（引用，点「确定」才写回它的 value） */
      mapEditingRow: null,
      /** 编辑中的键值对副本 [{uid, key, value}]，取消不影响原行 */
      mapDraft: [],
      /** 柱状图当前选中的行下标（只对选中柱子响应滚轮） */
      mapSelectedIndex: 0,
      /** 子弹窗柱状图的 ECharts 实例 */
      mapChart: null,
      /**
       * 每个 section 卡片根节点的 DOM 引用（用于 scrollRowIntoView 按 section 滚动）。
       * 用 Vue 函数式 ref 写入；Vue 2 的字符串 ref 在 v-for 里只能拿到数组，不便按
       * sectionKey 查找，所以这里走独立对象 + bindSectionEl 方法手动维护。
       */
      sectionRefs: {},
      /* ---------- 成员管理弹窗（点 set section 标题打开） ---------- */
      /** 弹窗可见性 */
      setMemberDialogVisible: false,
      /** 弹窗正在编辑的 set section 引用；null 表示弹窗未打开 */
      setMemberEditingSection: null,
      /** 弹窗里每行的勾选状态：{[configId]: boolean}；提交前仅在弹窗内编辑 */
      setMemberDraftIncluded: {},
      /* ---------- 拖动（行 → section） ---------- */
      /**
       * 拖动源：{sectionKey, rowIndex, row}。dragstart 时写入，drop / dragend 时清空。
       * 仅 custom=true 的行可拖（满足"在算法配置页添加的临时参数可移动"需求）；
       * 目录参数不进入 draggingFrom，drop 时会被忽略。
       */
      draggingFrom: null,
      /**
       * 拖动目标高亮 key（section.key）。dragover 进入时设置，离开 / drop 后清空。
       * 用一个 ref 对象而非单值是为了支持嵌套 section；当前只一级，简单 key 即可。
       */
      dragOverKey: ''
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
    fileName() {
      return (this.pyFile && this.pyFile.fileName) || ''
    },
    /**
     * 「添加参数」下拉里还能选的项目。
     * 只看「单独配置」section 里的 configId（配置组内的参数不能重复加，且 isMember=0
     * 的 options 本身就不包含已在配置组里的参数）。
     */
    addableOptions() {
      const alone = this.sections.find((s) => s.kind === 'alone')
      const used = alone ? alone.rows.map((row) => row.configId).filter((id) => id) : []
      return this.options.filter((opt) => used.indexOf(opt.id) < 0)
    },
    /**
     * 「添加配置组」下拉里还能选的项目（已经被添加过的组不可重复）。
     */
    addableSets() {
      return this.sets.filter((s) => this.addedSetIds.indexOf(Number(s.id)) < 0)
    },
    /** 整张弹窗里所有 section 的总行数（用于顶部「共 X 项配置」提示） */
    totalRowCount() {
      return this.sections.reduce((acc, s) => acc + s.rows.filter((r) => r.configId).length, 0)
    },
    /** 成员管理弹窗标题 */
    setMemberDialogTitle() {
      const sec = this.setMemberEditingSection
      return sec ? `成员管理 — ${sec.title}` : '成员管理'
    },
    /** 弹窗里已选成员数 */
    includedCount() {
      const draft = this.setMemberDraftIncluded || {}
      return Object.keys(draft).filter((k) => draft[k]).length
    },
    /** 弹窗里总成员数（来自 originalMembers） */
    totalCount() {
      const sec = this.setMemberEditingSection
      return sec && Array.isArray(sec.originalMembers) ? sec.originalMembers.length : 0
    },
    mapDialogTitle() {
      const name = this.mapEditingRow ? this.mapEditingRow.name : ''
      return name ? `编辑键值对 — ${name}` : '编辑键值对'
    },
    /** 键 / 值的显示名（别名来自参数定义，没配就退回「键」「值」） */
    mapAlias() {
      const row = this.mapEditingRow || {}
      return {
        key: row.keyAlias || '键',
        value: row.valueAlias || '值'
      }
    },
    /** 参数定义里带了默认键值对时，才允许「恢复参数默认值」 */
    resetMapAvailable() {
      const row = this.mapEditingRow
      return !!(row && row.valueOptions && row.valueOptions.length)
    },
    /** 柱状图每根柱子的数值（非数字按 0 处理） */
    mapChartValues() {
      return this.mapDraft.map((item) => this.toFiniteNumber(item.value))
    },
    /**
     * 柱状图 Y 轴上界。键值对没有单位概念，按数据量级给一个整的上界：
     *   ≤1 → 1（占比类，如 min_soc_per_hour 的 0~1）；≤10 → 10；≤100 → 100；
     *   再大就向上取整到 100 的倍数。全 0 给 1，避免出现一条压扁的轴。
     */
    mapChartMax() {
      const max = Math.max(0, ...this.mapChartValues)
      if (max <= 1) return 1
      if (max <= 10) return 10
      if (max <= 100) return 100
      return Math.ceil(max / 100) * 100
    },
    /** 滚轮微调步长：跟着 Y 轴量级走 */
    mapChartStep() {
      const max = this.mapChartMax
      if (max <= 1) return 0.01
      if (max <= 10) return 0.1
      return 1
    }
  },
  watch: {
    visible(value) {
      if (value) {
        this.initDialog()
      }
    },
    /**
     * 键值对改动（含滚轮微调）后重画柱状图。
     * renderMapChart 只读 mapDraft、不改它，不会反过来触发本 watcher。
     */
    mapDraft: {
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
  methods: {
    async initDialog() {
      await Promise.all([this.loadOptions(), this.loadSets()])
      this.buildSectionsFromFile()
      // 行建好后再回填「训练模型」选择器的状态（读行里已有的取值）
      this.syncTrainModelPicker()
    },

    async loadOptions() {
      this.optionsLoading = true
      try {
        // isMember=0 → 后端只下发「不在任何配置组」的参数；
        // 「添加配置组」按钮走另一条路，不污染这里的 options。
        const [optionRes, datasetRes] = await Promise.all([
          axios.get('/api/web/basedata/getAlgorithmParamConfigList', { params: { isMember: 0 } }),
          axios.get('/api/web/basedata/getDatasetList')
        ])
        this.options = (optionRes.data && optionRes.data.data) || []
        this.datasets = (datasetRes.data && datasetRes.data.data) || []
      } catch (error) {
        console.error('加载算法参数/数据集选项失败:', error)
        this.$message.error('加载算法参数失败，请确认后端服务已重启')
      } finally {
        this.optionsLoading = false
      }
    },

    /** 拉配置组清单（用于「添加配置组」下拉） */
    async loadSets() {
      this.setsLoading = true
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigSetList')
        if (res.data && res.data.code === 0) {
          this.sets = res.data.data || []
        } else {
          this.sets = []
        }
      } catch (error) {
        console.error('加载配置组清单失败:', error)
        this.sets = []
      } finally {
        this.setsLoading = false
      }
    },

    /**
     * 用脚本已保存的配置回填界面。
     *
     * 支持两种 JSON 形态：
     *   旧格式（不带 type 字段）：[{id, param_name, value, extra_desc}, ...] —— 全部视为「单独配置」
     *   新格式（带 type 字段）：
     *     [
     *       {type: 'alone', params: [{id, param_name, value, extra_desc}, ...]},
     *       {type: 'set', set_id: <id>, params: [{...}, ...]},
     *       ...
     *     ]
     *
     * 旧格式自动迁移：保存时会按新格式落库，下次加载就是新格式。
     */
    buildSectionsFromFile() {
      this.sections = []
      this.addedSetIds = []
      // 任务级配置（config）优先；为空才退回脚本文件自己的配置
      const raw = (this.config && String(this.config).trim())
        || (this.pyFile && this.pyFile.algorithmConfig)
      let parsed = null
      if (raw) {
        try {
          parsed = JSON.parse(raw)
        } catch (error) {
          console.warn('algorithm_config 解析失败，按未配置处理:', raw)
        }
      }
      if (!Array.isArray(parsed) || parsed.length === 0) {
        // 没有保存过配置：给一个空的「单独配置」section
        this.sections.push(this.buildAloneSection([]))
        return
      }
      const isNewFormat = parsed.length > 0
        && parsed[0]
        && Object.prototype.hasOwnProperty.call(parsed[0], 'type')
        && Array.isArray(parsed[0].params)
      if (!isNewFormat) {
        // 旧格式：全部当作 alone
        this.sections.push(this.buildAloneSection(parsed))
        return
      }
      // 新格式：按 type 拆
      parsed.forEach((sec) => {
        if (!sec || !Array.isArray(sec.params)) {
          return
        }
        if (sec.type === 'set') {
          const setId = Number(sec.set_id)
          const meta = this.sets.find((s) => Number(s.id) === setId)
          const setName = (meta && meta.name) || `配置组 #${setId}`
          // reload 路径也带上 originalMembers / setDesc，保证：
          //   1) section 标题右侧叹号能显示 set.desc
          //   2) 成员管理弹窗能列出原始成员
          // 注意：reload 时 sec.params 是已存的 JSON（不含 _fromSet / value_type），
          // 因此 buildRow 走 catalog option 兜底，name / desc / valueType 都从 options 取。
          this.sections.push(
            this.buildSetSection(setId, setName, sec.params, null, meta && meta.desc ? meta.desc : '')
          )
          if (setId && this.addedSetIds.indexOf(setId) < 0) {
            this.addedSetIds.push(setId)
          }
          // 异步拉一次 set detail，把 originalMembers / setDesc 补全；
          // 失败时不阻塞编辑流程，仅叹号弹层显示「暂无简介」。
          this.fetchSetDetailForSection(setId)
        } else {
          // type==='alone' 或未知：当成 alone
          this.sections.push(this.buildAloneSection(sec.params))
        }
      })
    },

    /**
     * reload 后异步补全某张 set section 的 originalMembers / setDesc。
     * 拉的是 getAlgorithmParamConfigSetDetail，里面 members 字段是完整的 VO 列表。
     * 成功时仅替换 setDesc / originalMembers，**不重写 rows**——rows 是用户已保存的快照。
     */
    fetchSetDetailForSection(setId) {
      axios.get('/api/web/basedata/getAlgorithmParamConfigSetDetail', { params: { id: setId } })
        .then((res) => {
          if (!res || !res.data || res.data.code !== 0) {
            return
          }
          const detail = res.data.data
          if (!detail) {
            return
          }
          const sec = this.sections.find((s) => s.kind === 'set' && Number(s.setId) === Number(setId))
          if (!sec) {
            return
          }
          const members = Array.isArray(detail.members) ? detail.members : []
          // 用 normalizeSetMember 保留完整字段（含 valueType / keyAlias / valueAlias / ifSystem），
          // 否则 reload 后从成员管理弹窗勾选回来的行同样会退化成临时参数样式。
          const originals = members.map((m) => this.normalizeSetMember(m))
          this.$set(sec, 'originalMembers', originals)
          if (detail.desc !== undefined) {
            this.$set(sec, 'setDesc', detail.desc)
          }
          // reload 时 sec.params 里只存了 {id, param_name, value, extra_desc}，
          // 而 options 只拉 isMember=0，配置组成员在 buildRow 里 option 查不到
          // → 会 fallback 成「临时参数」形态（名称变输入框、简介丢失、值控件变文本框）。
          // 这里拿到 detail.members 的完整字段后重建这些行，
          // 同时保留用户已保存的 value / alias / extraDesc。
          const memberMap = {}
          originals.forEach((m) => {
            memberMap[m.id] = m
          })
          const rebuilt = sec.rows.map((row, idx) => {
            const id = Number(row.configId)
            const m = id ? memberMap[id] : null
            // 不在配置组定义里的行（临时参数、或成员已被目录删除）保持原样
            if (!m) {
              return row
            }
            // 已经是 catalog 形态的行（本次新添加、尚未落库）→ 不动
            if (!row.custom) {
              return row
            }
            // row.value 是界面模型，先用 serializeRowValue 转回落库形态，
            // 交给 buildRow 走正常的 normalizeRowValue 还原（与保存/加载口径一致）
            const item = this.buildMemberRowItem(m, row.extraDesc, row.alias)
            item.value = this.serializeRowValue(row)
            const newRow = this.buildRow(item, idx)
            // 保留原 key：Vue 按 key 复用 DOM，避免重建导致输入框失焦 / 折叠状态抖动
            newRow.key = row.key
            return newRow
          })
          this.$set(sec, 'rows', rebuilt)
        })
        .catch((e) => {
          // 拉取失败：保持现有 section 不变，仅叹号弹层显示「暂无简介」
          console.warn(`[AlgorithmConfigDialog] 补全配置组 #${setId} 详情失败`, e)
        })
    },

    /** 构造「单独配置」section */
    buildAloneSection(items) {
      let list = Array.isArray(items) ? items.slice() : []
      /*
       * 固定参数（任务编排注入，如评估卡的「训练模型」）：
       * 与普通默认参数**同处一张表格**，直接补成普通行再打 locked 标记 ——
       * 界面据此禁用编辑 / 禁用排序 / 不给删除按钮，但仍参与保存
       * （值以服务端为准：保存任务时 BaseDataService 会重新写入权威值）。
       */
      const lockedParams = this.lockedParams || []
      lockedParams.forEach((p) => {
        const exists = list.some((it) => it && it.param_name === p.param_name)
        if (!exists) {
          list.push({
            id: p.id || p.param_name,
            type: this.customType,        // 走「自定义参数」形态：名称/参数名/值都是输入框
            name: p.name,
            param_name: p.param_name,
            value: p.value || '',
            extra_desc: p.desc || ''
          })
        }
      })
      // 固定参数一律排到最前面（位置固定，不可被移动）：列表顺序 = 保存进 JSON 的顺序
      const lockedNames = lockedParams.map((p) => p.param_name)
      const isLockedItem = (it) => !!it && lockedNames.indexOf(it.param_name) >= 0
      list = list.filter(isLockedItem).concat(list.filter((it) => !isLockedItem(it)))
      return {
        key: 'alone',
        kind: 'alone',
        title: '默认参数',
        rows: list.map((item, index) => {
          const row = this.buildRow(item, index)
          if (isLockedItem(item)) {
            // 在 section 被 push 之前打标记，保证它是响应式字段
            row.locked = true
            // 值列要换成专用选择器时，得知道这一行是哪个固定参数（模板按它判断）
            row.lockedParamName = item.param_name
            if (!row.value) {
              // 新建任务时后端还没生成任务 id：值这一列给个说明占位（禁用态下可见）
              row.placeholder = lockedParams.find((p) => p.param_name === item.param_name).placeholder
            }
          }
          return row
        })
      }
    },

    /* ---------------- 固定参数「训练模型」选择器（任务编排评估卡） ---------------- */

    /** 「训练模型」那一行（找不到返回 null）。 */
    trainModelRow() {
      const alone = this.sections.find((s) => s.kind === 'alone')
      if (!alone) {
        return null
      }
      return alone.rows.find((r) => r.locked && r.lockedParamName === 'train-task-id') || null
    },

    /** 取值是否指向"本任务自己的训练子任务"（= 重新训练）。空值也算。 */
    isOwnTrainTask(value) {
      const v = (value === null || value === undefined ? '' : String(value)).trim()
      if (!v) {
        return true
      }
      const parent = (this.parentTaskId || '').trim()
      if (!parent) {
        // 新建时父任务 id 还不存在：非空只可能是用户选的历史记录
        return false
      }
      return v === parent || v === `${parent}-train`
    },

    /** 用行里已有的取值回填选择器状态（打开弹窗 / 切换脚本后调用）。 */
    syncTrainModelPicker() {
      const row = this.trainModelRow()
      const value = row ? row.value : ''
      if (this.isOwnTrainTask(value)) {
        this.trainModelMode = 'retrain'
        this.trainModelTaskId = ''
      } else {
        this.trainModelMode = 'hist'
        this.trainModelTaskId = String(value)
      }
    },

    /**
     * 切换「重新训练 / 复用历史」：结果写回固定参数的值列。
     * 该行参与正常序列化 ⇒ 保存时会随 config JSON 一起提交给后端。
     */
    onTrainModelModeChange(mode) {
      const row = this.trainModelRow()
      if (!row) {
        return
      }
      if (mode === 'hist') {
        // 顺手默认选第一条，省得用户再点一次；没有候选就留空（后端会按"未选"处理）
        if (!this.trainModelTaskId) {
          const first = (this.trainTaskOptions || [])[0]
          this.trainModelTaskId = first ? first.taskId : ''
        }
        this.$set(row, 'value', this.trainModelTaskId || '')
      } else {
        this.$set(row, 'value', '')
      }
    },

    /** 选中某条历史训练任务 → 写入固定参数的值列。 */
    onTrainModelTaskChange(taskId) {
      const row = this.trainModelRow()
      if (row) {
        this.$set(row, 'value', taskId || '')
      }
    },

    /**
     * 历史训练任务下拉的展示文案：**任务名 · 时间**。
     * 刻意不拼 32 位任务 id（太长，界面上放不下）；脚本名 / 训练轮数等信息挪到悬停提示里。
     * 顺序由后端按同一个时间倒序下发（见 BaseDataService.getTrainModelTaskList）。
     */
    trainTaskLabel(t) {
      if (!t) {
        return ''
      }
      const name = t.displayName || t.taskName || ''
      const time = t.timeText || t.updated || ''
      const epochs = (t.epochsDone === null || t.epochsDone === undefined)
        ? ''
        : `${t.epochsDone}${t.trainEpochsTarget ? `/${t.trainEpochsTarget}` : ''} 轮`
      // 模型已经丢了的历史任务（后端 modelReady=false）：照样列出来，但标出来且不可选
      const lost = t.modelReady === false ? '（模型已丢失）' : ''
      if (name) {
        return (time ? `${name} · ${time}` : name) + lost
      }
      // 老记录没有任务名（代码编辑器直接跑的训练任务）⇒ 显示「时间 · 训练轮数」，
      // 时间本身就是区分这些记录的信息；绝不退回 32 位任务 id
      const parts = [time, epochs].filter(Boolean)
      return (parts.length ? parts.join(' · ') : '历史训练任务') + lost
    },

    /** 悬停提示：标签里省掉的信息（脚本、轮数、精确时间、任务 id）都放这儿。 */
    trainTaskTooltip(t) {
      if (!t) {
        return ''
      }
      const parts = []
      if (t.modelReady === false) {
        parts.push('模型已不在磁盘上（早期训练写在全局目录、被后来的训练覆盖），仅作记录，不能选')
      }
      if (t.scriptName) {
        parts.push(`脚本：${t.scriptName}`)
      }
      if (t.epochsDone !== null && t.epochsDone !== undefined) {
        const target = t.trainEpochsTarget ? ` / ${t.trainEpochsTarget}` : ''
        parts.push(`已训练：${t.epochsDone}${target} 轮`)
      }
      const time = t.sortTime || t.updated || t.timeText
      if (time) {
        parts.push(`时间：${time}`)
      }
      if (t.taskId) {
        parts.push(`任务 id：${t.taskId}`)
      }
      return parts.join('\n')
    },

    /**
     * 构造「配置组」section（kind=set，载入时填 setId + setName）。
     * @param setId            配置组 id
     * @param setName          配置组名称
     * @param items            当前 section 的 rows 输入（同 buildRow 的输入形态）
     * @param originalMembers  配置组原始成员列表 [{id, name, paramName, defaultValue, desc}]
     *                         用于「成员管理」弹窗；不传则默认从 items 推一个最小集合
     * @param setDesc          配置组自身的简介（标题右侧叹号悬停显示）
     */
    buildSetSection(setId, setName, items, originalMembers, setDesc) {
      // 把后端 members 标准化成弹窗能直接显示的字段；id 用 Number 方便和 section.rows[i].configId 对比。
      // ⚠️ 必须保留**完整字段**（valueType / defaultValue / keyAlias / valueAlias / ifSystem）：
      //   「成员管理」弹窗把成员取消勾选后再勾选回来时，要靠这些字段重建出
      //   与「添加参数」加进来时完全一致的 row；只存 4 个字段会让重建的行退化成临时参数。
      const originals = Array.isArray(originalMembers)
        ? originalMembers.map((m) => this.normalizeSetMember(m))
        : items.map((it) =>
            // reload 场景（originalMembers 为 null）的临时兜底：字段不全，
            // 稍后会由 fetchSetDetailForSection() 拉 detail 覆盖成完整形态。
            this.normalizeSetMember({
              id: it.id,
              name: it.name || '',
              paramName: it.param_name || '',
              valueType: it.value_type || '',
              defaultValue: it.default_value !== undefined ? it.default_value : it.value,
              keyAlias: it.key_alias || '',
              valueAlias: it.value_alias || '',
              desc: it.desc || '',
              ifSystem: it.if_system
            })
          )
      return {
        key: `set-${setId}`,
        kind: 'set',
        title: setName,
        setId,
        setName,
        // 每张卡片独立控制收起/展开；默认全部展开，临时折叠不影响落库
        collapsed: false,
        // 配置组自身简介（标题右侧叹号悬停显示）；空字符串不算"暂无简介"，调用方展示占位文案
        setDesc: setDesc || '',
        // 配置组原始成员列表（含 desc / defaultValue），用于成员管理弹窗
        originalMembers: originals,
        rows: items.map((item, index) => this.buildRow(item, index))
      }
    },

    buildRow(item, index) {
      const option = this.options.find((opt) => opt.id === item.id)
      /*
       * 自定义参数的判据：JSON 里显式带 type:"extra"。
       * 兜底「id 在目录里查不到」对页面临时添加适用；但「配置组载入」时
       * item._fromSet = true，强制按 catalog 形态渲染（set detail 自带
       * name / paramName / desc / defaultValue），绝不退化成自定义参数。
       */
      const isCustom = item._fromSet
        ? false
        : (item.type === this.customType || !option)
      if (isCustom) {
        return {
          key: `custom-${index}-${Date.now()}-${Math.random()}`,
          configId: item.id,
          custom: true,
          name: item.name || '',
          baseParamName: '',
          ifSystem: false,
          // 自定义参数的名称/参数名全手填，没有目录简介，值也按普通文本处理
          valueType: '',
          valueOptions: [],
          keyAlias: '',
          valueAlias: '',
          desc: '',
          alias: item.param_name || '',
          value: item.value === null || item.value === undefined ? '' : item.value,
          extraDesc: item.extra_desc || ''
        }
      }
      // 配置组 / catalog 形态：item 直接携带的字段优先于 catalog，
      // 避免「set detail 自带」与「options 缓存」之间出现不一致。
      // 解析 valueType：_fromSet 时直接读 item.value_type，
      // 否则走 option → resolveValueType 的完整解析。
      // _fromSet 且 value_type 为空时，用 isDatasetParamName 兜底（与 resolveValueType 一致），
      // 避免升级前保存的「数据集类参数」在配置组里退化成文本框。
      //
      // baseParamName（第二列左边的「原始参数名」）取值：
      //   · _fromSet → 配置组定义里的 paramName（item.param_name 就是它）
      //   · 否则     → 优先目录 option.paramName；option 查不到时退到 item.param_name
      // 别名（第二列右边输入框）的候选值：
      //   · _fromSet → item.alias（重建时显式传进来的用户别名）
      //   · 否则     → item.param_name（落库存的是"别名或原始名"）
      // 只有当候选与原始名不同才回填到输入框，否则留空（placeholder 显示原始名）。
      const baseParamName = item._fromSet
        ? (item.param_name || '')
        : ((option && option.paramName) || item.param_name || '')
      let valueType = 'text'
      let valueOptions = []
      if (item._fromSet) {
        valueType = item.value_type
          ? this.coerceValueType(item.value_type)
          : (this.isDatasetParamName(item.param_name) ? 'special' : 'text')
        valueOptions = this.parseOptionList(item.default_value)
      } else if (option) {
        valueType = this.resolveValueType(option)
        valueOptions = this.parseOptionList(option.defaultValue)
      }
      const aliasCandidate = item._fromSet ? (item.alias || '') : (item.param_name || '')
      const valueRaw = item.value === null || item.value === undefined ? '' : item.value
      return {
        key: `${item.id}-${index}-${Date.now()}-${Math.random()}`,
        configId: item.id,
        custom: false,
        name: item.name || (option && option.name) || '',
        baseParamName,
        ifSystem: item._fromSet ? !!item.if_system : (option ? !!option.ifSystem : false),
        valueType,
        valueOptions,
        keyAlias: item._fromSet
          ? (item.key_alias || '')
          : (option ? (option.keyAlias || '') : ''),
        valueAlias: item._fromSet
          ? (item.value_alias || '')
          : (option ? (option.valueAlias || '') : ''),
        desc: item.desc || (option && option.desc) || '',
        alias: aliasCandidate && aliasCandidate !== baseParamName ? aliasCandidate : '',
        value: this.normalizeRowValue(valueRaw, valueType),
        extraDesc: item.extra_desc || ''
      }
    },

    /**
     * 把后端 value_type 字符串规范化成 row.valueType 接受的形态。
     * 后端约定：num / text / bool / ratio / multiple / map / special；
     * 空 / null / 未知值 → 'text'。
     */
    coerceValueType(v) {
      const allowed = ['num', 'text', 'bool', 'ratio', 'multiple', 'map', 'special']
      if (allowed.indexOf(v) >= 0) {
        return v
      }
      return 'text'
    },

    /**
     * 把后端 set detail 的其中一个 member（AlgorithmParamConfigVO）标准化成
     * section.originalMembers 的元素形态。
     *
     * ⚠️ 必须保留完整字段，不能只留 id/name/paramName/desc：
     *   成员管理弹窗「取消勾选 → 再勾选回来」时，要用这些字段重建 row，
     *   否则重建出来的行会因缺少 valueType / _fromSet 而退化成「临时参数」样式。
     */
    normalizeSetMember(m) {
      const src = m || {}
      return {
        id: Number(src.id),
        name: src.name || '',
        paramName: src.paramName || '',
        valueType: src.valueType || '',
        defaultValue: src.defaultValue === null || src.defaultValue === undefined ? '' : src.defaultValue,
        keyAlias: src.keyAlias || '',
        valueAlias: src.valueAlias || '',
        desc: src.desc || '',
        ifSystem: !!src.ifSystem
      }
    },

    /**
     * 用 originalMembers 里的一个成员构造 buildRow 的输入。
     * 与 addSet() 里构造 payload 的逻辑保持一致：
     *   · _fromSet = true → buildRow 强制按 catalog 形态渲染（不 fallback 成临时参数）
     *   · 带上完整字段，保证 name / 参数名 / 简介 / valueType / 控件类型都不丢
     *
     * @param m               originalMembers 里的元素（normalizeSetMember 的产物）
     * @param extraDescOverride  重建时若要保留用户填过的补充说明，传进来；默认空
     * @param aliasOverride      重建时要保留的用户别名；默认空（= 未改过参数名）
     */
    buildMemberRowItem(m, extraDescOverride, aliasOverride) {
      return {
        id: m.id,
        _fromSet: true,
        name: m.name || '',
        // param_name 对 _fromSet 而言是「原始参数名」（来自配置组定义），
        // 用户改过的别名单独走 alias 字段（buildRow 里两者分开处理）
        param_name: m.paramName || '',
        alias: aliasOverride === undefined ? '' : aliasOverride,
        value_type: m.valueType || '',
        default_value: m.defaultValue,
        key_alias: m.keyAlias || '',
        value_alias: m.valueAlias || '',
        desc: m.desc || '',
        if_system: !!m.ifSystem,
        value: m.defaultValue,
        extra_desc: extraDescOverride === undefined ? '' : extraDescOverride
      }
    },

    /**
     * 取出某张 set section 标题右侧叹号要显示的简介。
     * 优先用 section.setDesc（addSet 时存的 detail.desc），
     * 列表里 sets 也带 desc，兼容兜底。
     */
    setDescOf(section) {
      if (!section || section.kind !== 'set') {
        return ''
      }
      if (section.setDesc) {
        return section.setDesc
      }
      const meta = this.sets.find((s) => Number(s.id) === Number(section.setId))
      return meta ? (meta.desc || '') : ''
    },

    /** 数据集 id 存的是数字，JSON 回来后统一成数字，el-select 才能匹配上选项 */
    normalizeValue(value) {
      if (value === null || value === undefined || value === '') {
        return null
      }
      const num = Number(value)
      return Number.isNaN(num) ? value : num
    },

    /**
     * 回填「值」这一列（把落库的字符串还原成界面控件需要的模型类型）。
     *   num      → 只留「数字 + 小数点」（历史数据里若混进过字符，这里顺手清掉，免得出现在数字框里）
     *   ratio    → 原样字符串，不能过 Number()：选项 key 若是 "1" 会被转成数字 1，el-select 就匹配不上选项
     *   multiple → 拆成 key 数组（多选下拉框的模型必须是数组）
     *   其它     → 走 normalizeValue（数据集 id 统一成 number，el-select 才匹配得上选项）
     */
    normalizeRowValue(value, valueType) {
      if (valueType === 'num') {
        return this.sanitizeNumInput(value)
      }
      if (valueType === 'bool') {
        return this.parseBoolValue(value)
      }
      if (valueType === 'ratio') {
        return value === null || value === undefined || value === '' ? null : String(value)
      }
      if (valueType === 'multiple') {
        return this.parseMultipleValue(value)
      }
      if (valueType === 'map') {
        return this.parseMapPairs(value)
      }
      return this.normalizeValue(value)
    },

    /**
     * 布尔回填。真实布尔、'true'/'false'、1/0、'开启'/'关闭'/'是'/'否' 都能认。
     *
     * 没存过值（null / 空串）时返回 false：开关只有开、关两态，不存在「未设置」，
     * 返回 null 的话既渲染不出第三种状态，又会被必填校验拦下来。
     */
    parseBoolValue(value) {
      if (typeof value === 'boolean') {
        return value
      }
      if (value === null || value === undefined || value === '') {
        return false
      }
      if (typeof value === 'number') {
        return value !== 0
      }
      const text = String(value).trim().toLowerCase()
      if (text === 'false' || text === '0' || text === '关闭' || text === '否' || text === 'no') {
        return false
      }
      return true
    },

    /**
     * 解析目录参数的 default_value（单选 / 多选的候选项）。
     * 后端下发的是 JSON 数组字符串：[{"key":"a","value":"甲"}, ...]
     * 脏数据不阻塞页面：解析失败只当作没有候选项。
     * @returns {Array<{key: string, label: string}>}
     */
    parseOptionList(raw) {
      if (!raw) {
        return []
      }
      let list = raw
      if (typeof raw === 'string') {
        try {
          list = JSON.parse(raw)
        } catch (error) {
          console.warn('default_value 不是合法 JSON，已忽略:', raw)
          return []
        }
      }
      if (!Array.isArray(list)) {
        return []
      }
      return list
        .map((item) => {
          if (!item || typeof item !== 'object') {
            return null
          }
          const key = item.key === null || item.key === undefined ? '' : String(item.key)
          if (!key) {
            return null
          }
          const label = item.value === null || item.value === undefined || String(item.value) === ''
            ? key
            : String(item.value)
          return { key, label }
        })
        .filter((item) => !!item)
    },

    /**
     * 把落库的多选值还原成 key 数组。
     * 保存时写的是 JSON 数组（["a","b"]）；这里同时兼容 [a,b] 这种不带引号的写法
     * 和逗号分隔串 —— 读得宽容一点，格式再变也不会把已存的数据读丢。
     */
    parseMultipleValue(value) {
      if (value === null || value === undefined || value === '') {
        return []
      }
      if (Array.isArray(value)) {
        return value.map((item) => String(item))
      }
      const text = String(value).trim()
      if (!text) {
        return []
      }
      try {
        const parsed = JSON.parse(text)
        if (Array.isArray(parsed)) {
          return parsed.map((item) => String(item))
        }
      } catch (error) {
        // 不是 JSON，继续按下面的宽松写法拆
      }
      const inner = text.startsWith('[') && text.endsWith(']')
        ? text.slice(1, -1)
        : text
      return inner
        .split(',')
        .map((item) => item.trim().replace(/^["']|["']$/g, ''))
        .filter((item) => item !== '')
    },

    /**
     * 「值」这一列是否为空（保存前的必填校验）。
     * 多选 / 键值对的模型是数组，空数组也算没填 —— 老的 `value === ''` 判断会漏掉这种情况。
     */
    isRowValueEmpty(row) {
      /*
       * 固定参数（任务编排注入，如评估卡的「训练模型」）不算「没填」：
       * 新建任务时任务 id 还不存在（由服务端落库时生成并写入），这一格本来就是空的，
       * 不能因此拦住创建。值由 BaseDataService 保存时补上，这里直接放行。
       */
      if (row.locked) {
        return false
      }
      // 开关只有开/关两态，不存在"没填"（false 也是有效值，不能被当成空）
      if (row.valueType === 'bool') {
        return false
      }
      if (row.valueType === 'multiple' || row.valueType === 'map') {
        return !Array.isArray(row.value) || row.value.length === 0
      }
      return row.value === null || row.value === '' || row.value === undefined
    },

    /**
     * 落库前的值序列化。
     *   multiple → 选项 key 的 JSON 数组（["a","b"]）；一个都没选则返回 ''
     *   其它     → 原样（ratio 已经是 key 字符串，special 是数据集 id）
     */
    serializeRowValue(row) {
      if (row.valueType === 'bool') {
        // 落库就是 JSON 布尔值，不是字符串 "true"
        return !!row.value
      }
      if (row.valueType === 'multiple') {
        const keys = Array.isArray(row.value) ? row.value : []
        return keys.length ? JSON.stringify(keys) : ''
      }
      if (row.valueType === 'map') {
        // 与参数定义 default_value 同构：[{"key":"0","value":"0.6"}, ...]
        const pairs = Array.isArray(row.value) ? row.value : []
        return pairs.length ? JSON.stringify(pairs) : ''
      }
      return row.value
    },

    /**
     * 把落库的键值对还原成 [{key, value}] 数组。
     * 保存时写的是 JSON 数组；这里顺带兼容 {"k":"v"} 这种对象写法，
     * 万一以后改了存储形态也不会把已存数据读丢。
     */
    parseMapPairs(value) {
      if (value === null || value === undefined || value === '') {
        return []
      }
      let data = value
      if (typeof data === 'string') {
        const text = data.trim()
        if (!text) {
          return []
        }
        try {
          data = JSON.parse(text)
        } catch (error) {
          console.warn('键值对不是合法 JSON，已按空处理:', value)
          return []
        }
      }
      if (Array.isArray(data)) {
        return data
          .filter((item) => item && item.key !== undefined && item.key !== null && String(item.key) !== '')
          .map((item) => ({
            key: String(item.key),
            value: item.value === null || item.value === undefined ? '' : String(item.value)
          }))
      }
      if (data && typeof data === 'object') {
        return Object.keys(data).map((key) => ({
          key,
          value: data[key] === null || data[key] === undefined ? '' : String(data[key])
        }))
      }
      return []
    },

    /**
     * 找到「单独配置」section（永远存在，可能为空）。
     * 这是「添加参数」按钮默认落到的位置。
     */
    getAloneSection() {
      let alone = this.sections.find((s) => s.kind === 'alone')
      if (!alone) {
        alone = this.buildAloneSection([])
        this.sections.unshift(alone)
      }
      return alone
    },

    /**
     * 按 sectionKey + 行下标定位 row，并返回可写的对象。
     * @return {{section: object, row: object} | null}
     */
    findRow(sectionKey, rowIndex) {
      const section = this.sections.find((s) => s.key === sectionKey)
      if (!section) {
        return null
      }
      const row = section.rows[rowIndex]
      if (!row) {
        return null
      }
      return { section, row }
    },

    /**
     * 添加一行（目录参数）。
     * 「添加参数」按钮只能选 isMember=0 的目录参数，因此加到的永远是「单独配置」section。
     * @param command el-dropdown 的 command：目录参数的 id，或 customCommand（自定义参数）
     */
    addRow(command) {
      if (command === this.customCommand) {
        this.addCustomRow()
        return
      }
      const option = this.options.find((opt) => opt.id === command)
      if (!option) {
        return
      }
      const valueType = this.resolveValueType(option)
      const row = {
        key: `${option.id}-${Date.now()}-${Math.random()}`,
        configId: option.id,
        custom: false,
        name: option.name,
        baseParamName: option.paramName,
        ifSystem: !!option.ifSystem,
        valueType,
        valueOptions: this.parseOptionList(option.defaultValue),
        keyAlias: option.keyAlias || '',
        valueAlias: option.valueAlias || '',
        desc: option.desc || '',
        alias: '',
        // 多选的下拉框模型、键值对的模型都必须是数组（el-select / 子弹窗都要数组）；
        // 开关只有开/关两态，直接给 false，避免出现第三种「未设置」态
        value: valueType === 'multiple' || valueType === 'map'
          ? []
          : (valueType === 'bool' ? false : null),
        extraDesc: ''
      }
      this.getAloneSection().rows.push(row)
    },

    /**
     * 加一行「自定义参数」：不在算法参数目录里，名称/参数名/值三项全部手填。
     * 同样落到「单独配置」section。
     *
     * id 由页面生成 uuid；保存后 JSON 为
     *   {id:"<uuid>", name:"<名称>", param_name:"<参数名>", value:"<值>",
     *    extra_desc:"<补充说明>", type:"extra"}
     * 比目录参数多 name / type / extra_desc：
     *   · name  —— 界面回填时显示的名称
     *   · type:"extra" —— 显式标记「这是自定义参数」，回填时以此判定
     *   · extra_desc —— 名称右侧叹号弹层里写的补充说明（选填，没写就不落库）
     */
    addCustomRow() {
      const row = {
        key: `custom-${Date.now()}-${Math.random()}`,
        configId: this.generateUuid(),
        custom: true,
        name: '',
        baseParamName: '',
        ifSystem: false,
        valueType: '',
        desc: '',
        alias: '',
        value: '',
        extraDesc: ''
      }
      this.getAloneSection().rows.push(row)
    },

    /**
     * 添加一个「配置组」section：拉成员、构造新 section，插到列表末尾。
     * 如果该 setId 之前已经添加过，就直接弹提示、不重复。
     */
    async addSet(setId) {
      const sid = Number(setId)
      if (!sid) {
        return
      }
      if (this.addedSetIds.indexOf(sid) >= 0) {
        const meta = this.sets.find((s) => Number(s.id) === sid)
        this.$message.warning(`配置组「${(meta && meta.name) || sid}」已存在，不能重复添加`)
        return
      }
      let detail = null
      try {
        const res = await axios.get('/api/web/basedata/getAlgorithmParamConfigSetDetail', {
          params: { id: sid }
        })
        if (res.data && res.data.code === 0) {
          detail = res.data.data || null
        }
      } catch (error) {
        console.error('加载配置组详情失败:', error)
        this.$message.error('加载配置组详情失败')
        return
      }
      if (!detail) {
        this.$message.error('配置组详情为空')
        return
      }
      const meta = this.sets.find((s) => Number(s.id) === sid)
      const setName = detail.name || (meta && meta.name) || `配置组 #${sid}`
      const setDesc = detail.desc || (meta && meta.desc) || ''
      const members = Array.isArray(detail.members) ? detail.members : []
      // 后端的 members 字段是完整的 AlgorithmParamConfigVO（id / name / paramName /
      // valueType / defaultValue / keyAlias / valueAlias / desc / ...）。
      // 配置组加进来的参数 *不是* 页面临时参数——它们也是 algorithm_param_config 里的
      // 真实条目，但 options 只拉了 isMember=0（不在任何配置组），查不到 option。
      // 因此用 buildMemberRowItem 把完整字段塞进 payload，靠 _fromSet 让 buildRow
      // 强制按 catalog 形态渲染（保留 ratio/multiple/bool/special/map 控件）。
      // ⚠️ 与 applyMemberDialog（成员管理弹窗勾选回来）共用同一个构造函数，
      //    保证两条路径产出的 row 形状完全一致。
      const payload = members.map((m) => this.buildMemberRowItem(this.normalizeSetMember(m)))
      // 原始 members 留给成员管理弹窗：传全字段（含 defaultValue / desc），
      // 弹窗里用 defaultValue 重建取消勾选后再勾选的 row。
      this.sections.push(this.buildSetSection(sid, setName, payload, members, setDesc))
      this.addedSetIds.push(sid)
      this.setPickerVisible = false
      this.$nextTick(() => {
        // 新 section 在末尾，自动滚到能看到
        this.scrollSectionIntoView(`set-${sid}`)
      })
    },

    /** 删除整张「配置组」section（弹确认） */
    removeSetSection(sectionKey) {
      const section = this.sections.find((s) => s.key === sectionKey)
      if (!section || section.kind !== 'set') {
        return
      }
      this.$confirm(
        `确定移除配置组「${section.title}」吗？该卡片内全部参数会一并从当前脚本移除。`,
        '移除配置组',
        { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' }
      )
        .then(() => {
          const idx = this.sections.findIndex((s) => s.key === sectionKey)
          if (idx >= 0) {
            this.sections.splice(idx, 1)
          }
          const sid = Number(section.setId)
          const listIdx = this.addedSetIds.indexOf(sid)
          if (listIdx >= 0) {
            this.addedSetIds.splice(listIdx, 1)
          }
        })
        .catch(() => {})
    },

    /** 打开「添加配置组」弹窗 */
    openSetPicker() {
      this.setPickerVisible = true
      this.setPickerError = ''
      if (!this.sets.length && !this.setsLoading) {
        this.loadSets()
      }
    },

    /* ---------------- 折叠 / 展开 ---------------- */

    /**
     * 切换某张 section 卡片的折叠状态。
     * 折叠态只影响可视性，不影响 rows 的内容/顺序，也不影响落库。
     */
    toggleCollapse(section) {
      if (!section) {
        return
      }
      this.$set(section, 'collapsed', !section.collapsed)
    },

    /* ---------------- 成员管理弹窗 ---------------- */

    /**
     * 点 set section 的标题打开成员管理弹窗。
     * 弹窗内容 = section.originalMembers（配置组原始成员，不含临时参数）；
     * 弹窗勾选状态 = 当前 section.rows 中 configId 的存在性。
     */
    openSetMemberDialog(section) {
      if (!section || section.kind !== 'set') {
        return
      }
      this.setMemberEditingSection = section
      // 初始勾选状态：以"当前 section.rows 里有哪些 configId"为准
      const included = {}
      const originals = Array.isArray(section.originalMembers) ? section.originalMembers : []
      section.rows.forEach((row) => {
        const id = Number(row.configId)
        if (id) {
          included[id] = true
        }
      })
      // 把每个 originalMember 的勾选状态显式初始化（未在 rows 里的 = false）
      const draft = {}
      originals.forEach((m) => {
        draft[m.id] = !!included[m.id]
      })
      this.setMemberDraftIncluded = draft
      this.setMemberDialogVisible = true
    },

    /**
     * 弹窗里勾选 / 取消某个成员（仅改草稿，不直接写回 section.rows）。
     */
    toggleMemberInSection(memberId) {
      const draft = Object.assign({}, this.setMemberDraftIncluded)
      const id = Number(memberId)
      draft[id] = !draft[id]
      this.setMemberDraftIncluded = draft
    },

    /**
     * 全选 / 全不选弹窗里的所有成员。
     */
    toggleAllMembers(checked) {
      const draft = {}
      const section = this.setMemberEditingSection
      if (!section) {
        return
      }
      const originals = section.originalMembers || []
      originals.forEach((m) => {
        draft[m.id] = !!checked
      })
      this.setMemberDraftIncluded = draft
    },

    /**
     * 把弹窗里的勾选状态真正落到 section.rows：
     *   取消勾选的成员 → 从 section.rows 中删除该 configId 的 row
     *   勾选回来的成员 → 从 originalMembers 取默认值，按 rows 末尾追加新 row
     */
    applyMemberDialog() {
      const section = this.setMemberEditingSection
      if (!section) {
        this.setMemberDialogVisible = false
        return
      }
      const draft = this.setMemberDraftIncluded
      const originals = section.originalMembers || []
      // 1) 取消勾选 → 从 rows 中删除
      const includedIds = new Set()
      Object.keys(draft).forEach((id) => {
        if (draft[id]) {
          includedIds.add(Number(id))
        }
      })
      section.rows = section.rows.filter((row) => {
        const id = Number(row.configId)
        if (!id) {
          return true
        } // 临时参数（configId 是 uuid）始终保留
        return includedIds.has(id)
      })
      // 2) 勾选回来的成员 → 加到末尾
      // ⚠️ 必须用 buildMemberRowItem（带 _fromSet + 完整字段）而不是手拼 4 个字段：
      //   手拼的 item 会让 buildRow 里 option 查不到 → fallback 成 custom，
      //   行就退化成「临时参数」样式（名称变输入框、简介丢失、值控件变文本框）。
      originals.forEach((m) => {
        if (!includedIds.has(Number(m.id))) {
          return
        }
        // 已经在 rows 里的不重复加
        const exists = section.rows.some((row) => Number(row.configId) === Number(m.id))
        if (exists) {
          return
        }
        section.rows.push(this.buildRow(this.buildMemberRowItem(m), section.rows.length))
      })
      this.setMemberDialogVisible = false
      this.setMemberEditingSection = null
    },

    /**
     * 弹窗关闭（点取消 / 右上角 X）时清掉草稿，避免下次打开看到脏数据。
     */
    cancelMemberDialog() {
      this.setMemberDialogVisible = false
      this.setMemberEditingSection = null
      this.setMemberDraftIncluded = {}
    },

    /* ---------------- 拖动（行 → section） ---------------- */

    /**
     * 仅 custom=true 的行可拖（"在算法配置页添加的临时参数"）。
     * 目录参数行不响应 dragstart —— 它们靠 set 标题 → 成员管理弹窗来管理。
     */
    isRowDraggable(row) {
      // 固定参数（任务编排注入）也不可拖：它必须待在默认参数表里
      return !!(row && row.custom && !row.locked)
    },

    /**
     * 拖动开始：把拖动源信息记录到 draggingFrom，并通过 setData 写一个标记字符串，
     * 让 dragover / drop 都能识别（部分浏览器要求必须 setData 才能 fire drop）。
     */
    onRowDragStart(event, section, row, rowIndex) {
      if (!this.isRowDraggable(row)) {
        event.preventDefault()
        return
      }
      this.draggingFrom = {
        sectionKey: section.key,
        rowIndex,
        row
      }
      try {
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', `alg-row:${section.key}:${row.configId || ''}`)
      } catch (e) {
        // 极少数环境下 dataTransfer 不可用，忽略
      }
    },

    /**
     * 拖动结束（含 drop 成功 / drop 在无效区域 / ESC 取消）时清掉状态。
     */
    onRowDragEnd() {
      this.draggingFrom = null
      this.dragOverKey = ''
    },

    /**
     * dragover 必须 preventDefault 才能触发 drop；并设置 effectAllowed。
     * drop target = section 卡片根 DOM。
     */
    onSectionDragOver(event, sectionKey) {
      if (!this.draggingFrom) {
        return
      }
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
      if (this.dragOverKey !== sectionKey) {
        this.dragOverKey = sectionKey
      }
    },

    /**
     * 拖动离开 section 卡片时清掉高亮。仅当真正离开（而非进入子元素）才清——
     * 用 relatedTarget 是否仍在卡片内判断。
     */
    onSectionDragLeave(event, sectionKey) {
      const card = event.currentTarget
      if (!card) {
        return
      }
      const related = event.relatedTarget
      // 进入子元素 → 不清；离开整张卡片 → 清
      if (related && card.contains(related)) {
        return
      }
      if (this.dragOverKey === sectionKey) {
        this.dragOverKey = ''
      }
    },

    /**
     * drop：把 draggingFrom 里的 row 从源 section.rows 中 splice 出来，
     * push 到目标 section.rows 末尾。同 section 拖动 = 移到末尾（不重复加）。
     */
    onSectionDrop(event, targetSection) {
      event.preventDefault()
      const src = this.draggingFrom
      this.draggingFrom = null
      this.dragOverKey = ''
      if (!src || !src.row || !src.row.custom) {
        return
      }
      // 找到源 section（src.sectionKey 可能因 DOM diff 失效，重新查一遍）
      const sourceSection = this.sections.find((s) => s.key === src.sectionKey)
      if (!sourceSection) {
        return
      }
      // 二次校验 index 有效性（拖动中可能 rows 已被 mutation 改过）
      let sourceIndex = sourceSection.rows.indexOf(src.row)
      if (sourceIndex < 0) {
        sourceIndex = src.rowIndex
      }
      // 同一 section：等于"移到末尾"，直接调 moveRow
      if (sourceSection.key === targetSection.key) {
        this.moveRow(targetSection.key, sourceIndex, targetSection.rows.length - 1 - sourceIndex)
        return
      }
      // 跨 section：splice + push
      const [moved] = sourceSection.rows.splice(sourceIndex, 1)
      if (!moved) {
        return
      }
      targetSection.rows.push(moved)
      // 拖走后 alone section 留空 → 保留一个空 placeholder，跟 removeRow 一致
      if (sourceSection.kind === 'alone' && sourceSection.rows.length === 0) {
        sourceSection.rows.push({
          key: `placeholder-${Date.now()}`,
          configId: null,
          custom: true,
          name: '',
          baseParamName: '',
          ifSystem: false,
          valueType: '',
          desc: '',
          alias: '',
          value: '',
          extraDesc: ''
        })
      }
    },

    /** 生成 uuid：优先用浏览器的 crypto.randomUUID，不支持时退回随机模板 */
    generateUuid() {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID()
      }
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
        const random = (Math.random() * 16) | 0
        const value = char === 'x' ? random : ((random & 0x3) | 0x8)
        return value.toString(16)
      })
    },

    /**
     * 删除一行。sectionKey 用来定位是哪个 section 的哪一行。
     * 「单独配置」section 不能被删空——删到 0 行会自动塞回一个空 section。
     */
    removeRow(sectionKey, index) {
      const target = this.findRow(sectionKey, index)
      if (!target) {
        return
      }
      target.section.rows.splice(index, 1)
      if (target.section.kind === 'alone' && target.section.rows.length === 0) {
        // 保留 alone section 不被清空（界面与落库格式都需要它在）
        target.section.rows.push({
          key: `placeholder-${Date.now()}`,
          configId: null,
          custom: true,
          name: '',
          baseParamName: '',
          ifSystem: false,
          valueType: '',
          desc: '',
          alias: '',
          value: '',
          extraDesc: ''
        })
      }
    },

    /**
     * 调整配置行的顺序（最左侧的上/下箭头）。
     *
     * 排序范围 = 当前 section 内部：保证「单独配置」与每个「配置组」各自独立排序。
     * save() 里 payload 按 sections 顺序、每段内部按 rows 顺序生成。
     * 行的 :key 是稳定值，Vue 会复用 DOM 做移动而不是重建整行，输入框焦点不会丢。
     *
     * @param sectionKey  所属 section 的 key
     * @param index       当前行在 section 内的下标
     * @param offset      -1 上移，+1 下移
     */
    moveRow(sectionKey, index, offset) {
      const target = this.findRow(sectionKey, index)
      if (!target) {
        return
      }
      const targetIndex = index + offset
      if (targetIndex < 0 || targetIndex >= target.section.rows.length) {
        return
      }
      const [moved] = target.section.rows.splice(index, 1)
      target.section.rows.splice(targetIndex, 0, moved)
      this.scrollRowIntoView(target.section, targetIndex)
    },

    /**
     * 把第 index 行滚进表格的可视区域。
     *
     * 行数超过 max-height 后表格内部会滚动，此时点箭头把行移到视野外，
     * 界面上看不出任何变化，会被当成「点了没反应」，所以移动后主动滚一下。
     *
     * 只改本表自己的 scrollTop，不用 scrollIntoView —— 后者会连带滚动外层弹窗乃至页面，
     * 列表没溢出时尤其突兀。顶部还要让开 sticky 表头的高度，否则上移后的行正好被表头压住。
     */
    /**
     * 把第 index 行滚进表格的可视区域。
     *
     * 行数超过 max-height 后表格内部会滚动，此时点箭头把行移到视野外，
     * 界面上看不出任何变化，会被当成「点了没反应」，所以移动后主动滚一下。
     *
     * 只改本表自己的 scrollTop，不用 scrollIntoView —— 后者会连带滚动外层弹窗乃至页面，
     * 列表没溢出时尤其突兀。顶部还要让开 sticky 表头的高度，否则上移后的行正好被表头压住。
     *
     * 参数 (section, index) —— section 既承载滚动的 .cfg-table DOM，也是 row 的归属。
     */
    scrollRowIntoView(section, index) {
      this.$nextTick(() => {
        // section 自己没挂 el，靠手动维护的 sectionRefs 映射按 key 找 DOM 根节点
        const table = section && this.sectionRefs[section.key]
        if (!table) {
          return
        }
        // querySelectorAll 按文档顺序返回（= 界面顺序），不受 v-for 上 ref 注册顺序的影响
        const rows = table.querySelectorAll('.cfg-row')
        const row = rows[index]
        if (!row) {
          return
        }
        const head = table.querySelector('.cfg-head')
        const headHeight = head ? head.offsetHeight : 0
        // row.offsetTop 以 .cfg-table 为基准（该元素是 position: relative），与 scrollTop 同一坐标系
        const rowTop = row.offsetTop
        const rowBottom = rowTop + row.offsetHeight
        if (rowTop < table.scrollTop + headHeight) {
          table.scrollTop = rowTop - headHeight
        } else if (rowBottom > table.scrollTop + table.clientHeight) {
          table.scrollTop = rowBottom - table.clientHeight
        }
      })
    },

    /**
     * 滚某个 section 卡片进可视区域（新增「配置组」卡片时用）。
     */
    scrollSectionIntoView(sectionKey) {
      const el = this.sectionRefs && this.sectionRefs[sectionKey]
      if (el && typeof el.scrollIntoView === 'function') {
        this.$nextTick(() => el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }))
      }
    },

    /**
     * 给 template 里的 `:ref="el => bindSectionEl(section.key, el)"` 用。
     * Vue 2 v-for 里的字符串 ref会被收集成数组、不便按 key 找，这里手动维护映射。
     */
    bindSectionEl(key, el) {
      if (!el) {
        return
      }
      this.$set(this.sectionRefs, key, el)
    },

    /**
     * 取某个目录参数的「值类型」，决定值这一列渲染哪个控件。
     * 优先用配置表里的 value_type（num / special）；没配时退回按参数名判断，
     * 这样升级前保存的行也照旧显示成数据集下拉，不会突然退化成文本框。
     */
    resolveValueType(option) {
      const configured = (option && option.valueType) || ''
      if (configured) {
        return configured
      }
      return this.isDatasetParamName(option && option.paramName) ? 'special' : ''
    },

    /**
     * 参数名是否是数据集类参数（value_type 未配置时的兜底判据）。
     * ⚠️ 传的是参数名字符串本身，不是 row 对象。
     */
    isDatasetParamName(paramName) {
      return paramName === 'train-schema' || paramName === 'eval-schema'
    },

    /**
     * 「值」这一列的输入（value_type=num）：保留数字与小数点，其它字符直接丢掉。
     *
     * ⚠️ 必须放行小数点：max_soc_normal=0.99 / B_low=1.18 这类比值本就是小数，
     *    早先只留 \d 会把 "0.99" 洗成 "099"、传给 CHESCA.py 就成了 99，
     *    在「0~1」校验处直接 ValueError 崩掉（2026-10-08 实际踩到）。
     *
     * 过滤后把 row.value 设回去，界面上多打的字符也会被抹掉 ——
     * el-input 的 handleInput 里有 `this.$nextTick(this.setNativeInputValue)`，
     * 下一拍会把 DOM 的值回写成模型值，所以非法字符不会残留在输入框里。
     */
    onNumValueInput(row, value) {
      row.value = this.sanitizeNumInput(value)
    },

    /**
     * num 输入框的字符清洗：只保留数字、至多一个小数点，允许前导负号。
     *   "0.99"   → "0.99"
     *   "1.2.3"  → "1.23"（多余的小数点丢掉）
     *   "-0.5a"  → "-0.5"
     * 空串返回空串，交给外层做「是否必填」判断。
     */
    sanitizeNumInput(value) {
      let text = String(value === null || value === undefined ? '' : value).trim()
      const negative = text.startsWith('-')
      text = text.replace(/[^\d.]/g, '')
      const firstDot = text.indexOf('.')
      if (firstDot >= 0) {
        text = text.slice(0, firstDot + 1) + text.slice(firstDot + 1).replace(/\./g, '')
      }
      return (negative ? '-' : '') + text
    },

    datasetLabel(dataset) {
      if (!dataset) {
        return ''
      }
      const extra = []
      if (dataset.buildingCount) {
        extra.push(`${dataset.buildingCount} 栋`)
      }
      if (dataset.timeSteps) {
        extra.push(`${dataset.timeSteps} 步`)
      }
      return extra.length ? `${dataset.displayName}（${extra.join('·')}）` : dataset.displayName
    },

    save() {
      if (!this.pyFile || !this.pyFile.id) {
        this.$message.error('未选中脚本，无法保存')
        return
      }
      // 自定义参数：名称与参数名都必须填，否则这一行没有意义
      // 配置组 section 里允许出现「自定义参数 placeholder」（configId 为 null），
      // 这种行一定没填完，直接拦下。
      const allRows = this.sections.reduce((acc, s) => acc.concat(s.rows), [])
      const incompleteCustom = allRows.find(
        (row) => row.custom && row.configId
          && (!row.name || !row.name.trim() || !row.alias || !row.alias.trim())
      )
      if (incompleteCustom) {
        this.$message.warning('自定义参数需要同时填写名称与参数名')
        return
      }
      const missing = allRows.find((row) => row.configId && this.isRowValueEmpty(row))
      if (missing) {
        this.$message.warning(`请为「${missing.name || '自定义参数'}」填写值`)
        return
      }

      /**
       * 落库格式（v2）：
       *   [
       *     {type: 'alone', params: [{id, param_name, value, extra_desc?}, ...]},
       *     {type: 'set',   set_id: <id>, params: [{...}, ...]},
       *     ...
       *   ]
       * 旧格式（无 type 字段的纯数组）在 buildSectionsFromFile 里被自动迁移，
       * 下次保存时统一落到 v2 形态。
       */
      const payload = this.sections.map((section) => {
        const params = section.rows
          .filter((row) => row.configId) // 过滤掉 placeholder 空行
          .map((row) => {
            const extraDesc = (row.extraDesc || '').trim()
            const value = this.serializeRowValue(row)
            if (row.custom) {
              return {
                id: row.configId,
                name: (row.name || '').trim(),
                param_name: (row.alias || '').trim(),
                value,
                ...(extraDesc ? { extra_desc: extraDesc } : {}),
                type: this.customType
              }
            }
            return {
              id: row.configId,
              // 别名留空 → 回落到原始参数名
              param_name: (row.alias || '').trim() || row.baseParamName,
              value,
              ...(extraDesc ? { extra_desc: extraDesc } : {})
            }
          })
        if (section.kind === 'set') {
          return { type: 'set', set_id: section.setId, params }
        }
        return { type: 'alone', params }
      })
      this.submit(JSON.stringify(payload))
    },

    /* ---------------- 键值对（map）子弹窗 ---------------- */

    /** 值列按钮上的条目数 */
    mapItemCount(row) {
      return Array.isArray(row.value) ? row.value.length : 0
    },

    mapButtonLabel(row) {
      const count = this.mapItemCount(row)
      return count ? `编辑键值对（${count} 项）` : '尚未设置，点击编辑'
    },

    newMapItem(key, value) {
      return {
        uid: `map-${Date.now()}-${Math.random()}`,
        key: key === null || key === undefined ? '' : String(key),
        value: value === null || value === undefined ? '' : String(value)
      }
    },

    /**
     * 打开键值对编辑子弹窗。
     * 脚本里还没配过时，用参数定义里的默认键值对打底（如小时下限的 24 个小时），
     * 免得对着空白一行行敲。
     */
    openMapEditor(row) {
      if (!row) {
        return
      }
      this.mapEditingRow = row
      const current = Array.isArray(row.value) ? row.value : []
      const source = current.length
        ? current
        : (row.valueOptions || []).map((opt) => ({ key: opt.key, value: opt.label }))
      this.mapDraft = source.map((item) => this.newMapItem(item.key, item.value))
      this.mapSelectedIndex = 0
      this.mapDialogVisible = true
    },

    addMapItem() {
      this.mapDraft.push(this.newMapItem('', ''))
    },

    removeMapItem(index) {
      this.mapDraft.splice(index, 1)
      if (this.mapSelectedIndex >= this.mapDraft.length) {
        this.mapSelectedIndex = Math.max(0, this.mapDraft.length - 1)
      }
    },

    /** 用参数定义里的默认键值对覆盖草稿 */
    resetMapFromOption() {
      const options = (this.mapEditingRow && this.mapEditingRow.valueOptions) || []
      this.mapDraft = options.map((opt) => this.newMapItem(opt.key, opt.label))
      this.mapSelectedIndex = 0
    },

    /** 确定：只写回那一行（过滤掉键为空的项；键重复直接拦下） */
    confirmMapEdit() {
      const pairs = this.mapDraft
        .map((item) => ({ key: (item.key || '').trim(), value: (item.value || '').trim() }))
        .filter((item) => item.key)
      const duplicated = pairs.find(
        (item, index) => pairs.findIndex((other) => other.key === item.key) !== index
      )
      if (duplicated) {
        this.$message.warning(`键重复：${duplicated.key}`)
        return
      }
      if (this.mapEditingRow) {
        this.mapEditingRow.value = pairs
      }
      this.mapDialogVisible = false
    },

    /** 子弹窗打开动画结束后初始化/重画（此时容器才有尺寸） */
    onMapDialogOpened() {
      this.$nextTick(() => this.renderMapChart())
    },

    onMapDialogClosed() {
      this.destroyMapChart()
      this.mapDraft = []
      this.mapEditingRow = null
    },

    /** 文本 → 有限数字；非数字一律按 0，避免一个空值把整张图带崩 */
    toFiniteNumber(value) {
      const num = Number(value)
      return Number.isFinite(num) ? num : 0
    },

    /** 数字 → 去掉浮点噪声的字符串（滚轮 ±0.01 容易出现 0.30000000000000004） */
    formatNumber(value) {
      const num = Number(value)
      if (!Number.isFinite(num)) {
        return ''
      }
      return String(Number(num.toFixed(4)))
    },

    /**
     * 画键值对柱状图。操作方式与「24 小时 SOC 下限柱状图」一致：
     *   点柱子 → 选中对应那一行（该行输入框高亮、柱子变蓝）；
     *   滚轮   → 在选中的柱体上滚动，按 mapChartStep 微调该行的值。
     */
    renderMapChart() {
      const el = this.$refs.mapChart
      if (!el) {
        return
      }
      if (!this.mapChart) {
        this.mapChart = echarts.init(el)
        this.mapChart.on('click', this.handleMapChartClick)
        // passive:false 才能 preventDefault，否则弹窗会跟着一起滚
        el.addEventListener('wheel', this.handleMapChartWheel, { passive: false })
      }
      const keys = this.mapDraft.map((item, index) => {
        const key = (item.key || '').trim()
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
          axisLabel: { fontSize: 10, interval: 0, rotate: keys.length > 12 ? 45 : 0 }
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
          data: this.mapDraft.map((item, index) => ({
            value: this.toFiniteNumber(item.value),
            itemStyle: { color: index === selected ? '#409eff' : '#a0cfff' }
          }))
        }]
      }, true)
      this.mapChart.resize()
    },

    handleMapChartClick(params) {
      if (params == null || params.componentType !== 'series') {
        return
      }
      const index = Number(params.dataIndex)
      if (!Number.isInteger(index) || index < 0 || index >= this.mapDraft.length) {
        return
      }
      this.mapSelectedIndex = index
    },

    /**
     * 滚轮微调：只对「选中的那根柱子、且指针落在柱体实心区域内」生效，
     * 每次 ±mapChartStep（量级 ≤1 的数据为 0.01，0~100 的为 1）。
     */
    handleMapChartWheel(event) {
      if (!this.mapChart || !this.mapDraft.length) {
        return
      }
      const point = [event.offsetX, event.offsetY]
      if (!this.mapChart.containPixel('grid', point)) {
        return
      }
      const dataCoord = this.mapChart.convertFromPixel({ seriesIndex: 0 }, point)
      if (!Array.isArray(dataCoord) || dataCoord.length < 2) {
        return
      }
      const index = Math.round(dataCoord[0])
      if (index !== this.mapSelectedIndex || index < 0 || index >= this.mapDraft.length) {
        return
      }
      if (Math.abs(dataCoord[0] - index) > 0.45) {
        return
      }
      const current = this.toFiniteNumber(this.mapDraft[index].value)
      if (dataCoord[1] < 0 || dataCoord[1] > current) {
        return // 只有落在柱体里才响应
      }
      event.preventDefault()
      const step = this.mapChartStep
      const next = Math.max(0, current + (event.deltaY < 0 ? step : -step))
      this.mapDraft[index].value = this.formatNumber(next)
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

    async submit(algorithmConfig) {
      // 任务级配置：不写 py_file，只把 JSON 交回调用方（挂在任务上）
      if (!this.persist) {
        this.$message.success('配置已应用到当前任务（不会修改脚本文件）')
        this.$emit('saved', algorithmConfig)
        this.visibleProxy = false
        return
      }
      this.saving = true
      try {
        const response = await axios.post('/api/web/basedata/savePyFileAlgorithmConfig', {
          id: this.pyFile.id,
          algorithmConfig
        })
        if (response.data && response.data.code === 0) {
          this.$message.success('算法配置已保存')
          this.$emit('saved', algorithmConfig)
          this.visibleProxy = false
        } else {
          this.$message.error((response.data && response.data.message) || '保存失败')
        }
      } catch (error) {
        console.error('保存算法配置失败:', error)
        this.$message.error('保存失败：' + (error.message || '网络错误'))
      } finally {
        this.saving = false
      }
    },

    onClosed() {
      // 关闭弹窗时清空 sections，下次打开重新加载（避免跨脚本状态串味）
      this.sections = []
      this.addedSetIds = []
      this.setPickerVisible = false
      this.setPickerError = ''
    }
  }
}
</script>

<style scoped>
/* 顶部 hint 文字样式已移除（原本挂在 .dialog-hint 上） */

.add-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.add-hint {
  font-size: 12px;
}

/* ---------- 配置组卡片（每个 section 一张） ---------- */
.section-card {
  margin-bottom: 14px;
  border: 1px solid var(--divider-color, #e4e7ed);
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}

.section-card-set {
  border-color: rgba(64, 158, 255, 0.35);
  background: linear-gradient(180deg, rgba(64, 158, 255, 0.04) 0%, #fff 50%);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f5f7fa;
  border-bottom: 1px solid var(--divider-color, #e4e7ed);
}

.section-card-set .section-head {
  background: rgba(64, 158, 255, 0.08);
}

.section-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.section-head-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-head-icon {
  font-size: 15px;
  color: var(--secondary-text-color, #909399);
}

.section-card-set .section-head-icon {
  color: #409eff;
}

.section-title {
  font-weight: 500;
  font-size: 14px;
  color: var(--primary-text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.section-meta {
  font-size: 12px;
}

/* 「添加配置组」下拉里组名后跟着的成员数提示 */
.set-meta-inline {
  margin-left: 4px;
  font-size: 11px;
  color: #909399;
}

/* ---------- 配置组标题：可点击打开成员管理弹窗 ---------- */
.section-title-clickable {
  cursor: pointer;
  border-bottom: 1px dashed transparent;
  transition: border-color 120ms;
}
.section-title-clickable:hover {
  border-bottom-color: #409eff;
  color: #409eff;
}

/* ---------- 折叠按钮 ---------- */
.collapse-btn {
  padding: 0 8px;
  height: 24px;
  line-height: 24px;
  font-size: 12px;
  color: var(--secondary-text-color, #909399);
}
.collapse-btn i {
  margin-right: 2px;
  font-size: 12px;
}
.collapse-btn:hover {
  color: #409eff;
}

/* ---------- 折叠态：去掉表头与主体之间的分隔线，让卡片"收紧" ---------- */
.section-card-collapsed .section-head {
  border-bottom-color: transparent;
}

/* ---------- 拖动：目标高亮 ---------- */
.section-card-drag-over {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2) inset;
  background-color: rgba(64, 158, 255, 0.04);
}

/* ---------- 拖动：行源样式 ---------- */
.cfg-row-draggable {
  cursor: grab;
}
.cfg-row-draggable:hover {
  background-color: rgba(230, 162, 60, 0.06);
}
.cfg-row-dragging {
  opacity: 0.4;
}

/* ---------- 成员管理弹窗 ---------- */
.member-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.member-stat {
  margin-left: auto;
  font-size: 12px;
}
.member-list {
  max-height: 460px;
  overflow-y: auto;
  border: 1px solid var(--divider-color, #e4e7ed);
  border-radius: 6px;
}
.member-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--divider-color, #e4e7ed);
  cursor: pointer;
}
.member-item:last-child {
  border-bottom: none;
}
.member-item:hover {
  background-color: rgba(64, 158, 255, 0.04);
}
.member-name {
  flex: 0 0 auto;
  font-weight: 500;
  color: var(--primary-text-color);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.member-param {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: var(--primary-text-color);
  background: rgba(144, 147, 153, 0.15);
}
.member-desc {
  flex: 1 1 auto;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- 配置表（排序 / 名称 / 参数名 / 值 / 操作）---------- */
.cfg-table {
  /* position: relative 是为了让行的 offsetTop 以本表为基准 ——
     moveRow 里算滚动位置要用它，否则基准会变成 .el-dialog（最近的有定位祖先） */
  position: relative;
  border: 1px solid var(--divider-color, #e4e7ed);
  border-radius: 6px;
  /* 行多时不把弹窗顶出屏幕：只滚表格内部，表头靠 sticky 固定在顶部。
     约 7 行高度，想调大调小改这个值即可。 */
  max-height: 340px;
  overflow-y: auto;
  overflow-x: hidden;
}

.cfg-head,
.cfg-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
}

.cfg-head {
  /* 表格内部滚动时表头固定在顶部。
     背景必须不透明 —— 原来的半透明灰在行滚到下面时会透出来。 */
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f5f7fa;
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.cfg-row {
  border-top: 1px solid var(--divider-color, #e4e7ed);
}

.cfg-row:hover {
  background: rgba(64, 158, 255, 0.04);
}

.col-name {
  flex: 0 0 200px;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.col-param {
  flex: 1 1 260px;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.col-value {
  flex: 1 1 240px;
  min-width: 0;
}

.col-op {
  flex: 0 0 40px;
  text-align: center;
}

/* 最左侧的排序列：上/下箭头竖排，尽量窄，别挤压名称列 */
.col-sort {
  flex: 0 0 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

/* 箭头按钮：默认内边距会把行撑高，这里压扁（两枚共 28px，塞在 32px 高的输入框旁边） */
.sort-btn {
  padding: 0;
  height: 14px;
  line-height: 14px;
  font-size: 12px;
}

/* Element UI 的 .el-button + .el-button 会加 10px 左边距，竖排不需要 */
.sort-btn + .sort-btn {
  margin-left: 0;
}

.cfg-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 名称右侧的小叹号：悬浮显示参数简介（desc） */
.desc-icon {
  flex: 0 0 auto;
  font-size: 14px;
  line-height: 1;
  color: #c0c4cc;
  cursor: help;
}

.desc-icon:hover {
  color: #409eff;
}

/* 配置组标题旁的叹号：略小一点、和标题基线对齐 */
.set-desc-icon {
  font-size: 13px;
  margin-left: -2px;
}

/* 叹号弹层里的内容：简介文字 + 补充说明输入框 */
.desc-pop-text {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.5;
}

.desc-pop-empty {
  color: #909399;
}

/* 第二列：左边是数据库里的原始参数名，右边是别名输入框 */
.base-param {
  flex: 0 0 auto;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: var(--primary-text-color);
  background: rgba(144, 147, 153, 0.15);
}

.alias-input,
.value-control,
.name-input {
  flex: 1 1 auto;
  width: 100%;
}

/* 自定义参数行：左侧加一条色带，和目录参数区分开 */
.cfg-row-custom {
  border-left: 3px solid #e6a23c;
  background: rgba(230, 162, 60, 0.04);
}

.cfg-row-custom:hover {
  background: rgba(230, 162, 60, 0.08);
}

.sys-tag {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  font-style: normal;
  line-height: 16px;
  color: #409eff;
  background: rgba(64, 158, 255, 0.12);
}

.sys-flag {
  margin-left: 6px;
  font-size: 11px;
  color: #909399;
}

.empty-tip {
  padding: 28px 0;
  text-align: center;
  border: 1px dashed var(--divider-color, #e4e7ed);
  border-radius: 6px;
}

.danger-text-btn {
  color: #f56c6c;
}

.danger-text-btn:hover {
  color: #f78989;
}

/* ---------- 固定参数「训练模型」：值列里的两级选择器（列窄 ⇒ 竖排） ---------- */
.train-model-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.train-model-picker .value-control {
  width: 100%;
}

/* ---------- 键值对（map）：值列入口按钮 + 子弹窗 ---------- */
.map-value-btn {
  width: 100%;
  font-size: 12px;
}

.map-value-empty {
  color: #909399;
}

.map-tip {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
}

/* 键 / 值别名表头 */
.map-alias-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 6px;
  border-bottom: 1px solid var(--divider-color, #e4e7ed);
  margin-bottom: 8px;
}

.map-alias-item {
  flex: 1 1 0;
  padding-left: 2px;
  font-size: 12px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.map-empty {
  padding: 10px 0;
  font-size: 12px;
}

.map-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.map-row-active .map-input >>> .el-input__inner {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.06);
}

/* 固定参数行（任务编排注入）：与普通默认参数同处一张表格，只读、不可移动 */
.cfg-row-locked {
  background: #f4f8ff;
}

/* 禁用态的输入框保持浅蓝底，让「这一行是固定的」在视觉上连成一片 */
.cfg-row-locked >>> .el-input.is-disabled .el-input__inner {
  background: #f4f8ff;
  color: var(--primary-text-color);
}

/* 名称右侧的「固定」标记：与「系统」同位置，用主色区分 */
.locked-tag {
  background: #409eff;
  color: #ffffff;
}

.locked-param-tag {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.map-input {
  flex: 1 1 0;
}

.map-del {
  flex: 0 0 auto;
}

.map-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 12px;
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

<!--
  el-tooltip 的弹层被挂到 body 下（不在本组件的 DOM 子树里），scoped 样式选不到它的外框，
  只能用非 scoped 块按 popper-class 限定。默认宽度 276px 放输入框偏窄，这里放宽一点。
-->
<style>
.alg-desc-popper {
  max-width: 320px;
  line-height: 1.5;
}
</style>
