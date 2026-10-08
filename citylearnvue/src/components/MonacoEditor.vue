<template>
  <div class="python-editor">
    <div class="editor-header">
      <h3>{{ fileName }}</h3>
      <div class="controls">
        <template v-if="listMode === 'files'">
          <!-- 算法配置：仅「只训练」/「只评估」类型的脚本可配（对应 py_file.script_type） -->
          <button
            v-if="canConfigureCurrentFile"
            @click="algorithmConfigVisible = true"
            :disabled="!canCodeOperate"
            class="btn-config"
            title="配置该脚本的算法参数（训练/评估数据集等）"
          >
            配置
          </button>
          <button
            @click="toggleIfShow"
            :disabled="!canCodeOperate || !currentFile || isTogglingIfShow"
            class="btn-show"
            :class="{ 'btn-show-active': currentFileIfShow }"
            :title="!canCodeOperate ? '无操作权限' : (currentFileIfShow ? '当前结果将在前端展示，点击设为未展示' : '当前结果未展示，点击设为展示中')"
          >
            {{ isTogglingIfShow ? '更新中...' : (currentFileIfShow ? '展示中' : '未展示') }}
          </button>
          <button
            @click="enterTaskRecordMode"
            :disabled="!currentFile"
            class="btn-record"
            title="查看任务列表"
          >
            记录
          </button>
          <!-- 断点续训（P19-1）：点击后选择「从哪个已完成任务」续训，选中的任务折点会复制到本次任务 -->
          <label
            v-if="resumeSupported"
            class="resume-switch"
            :class="{ 'is-on': resumeEnabled, 'is-disabled': isCodeEditLocked }"
            :title="resumeSwitchTitle"
            @click.prevent="onResumeSwitchClick"
          >
            <input
              type="checkbox"
              :checked="resumeEnabled"
              :disabled="isCodeEditLocked"
              @click.prevent
            />
            <span>续训{{ resumeEnabled && resumeFromTaskId ? '·已选任务' : '' }}</span>
          </label>
          <button
            @click="runPyFile"
            :disabled="!canCodeOperate || runButtonDisabled"
            class="btn-run"
            :title="!canCodeOperate ? '无操作权限' : runButtonTitle"
          >
            {{ runButtonLabel }}
          </button>
          <button
            v-if="isCurrentFileRunning || isStopping"
            @click="stopPyFile"
            :disabled="!canCodeOperate || isStopping"
            class="btn-stop"
            :title="!canCodeOperate ? '无操作权限' : '终止当前运行的任务（任务状态将标记为「运行终止」）'"
          >
            {{ isStopping ? '终止中...' : '终止' }}
          </button>
          <button
            @click="saveCode"
            :disabled="!canCodeOperate || isSaving || !currentFile || !codeDirty || isCodeEditLocked"
            class="btn-save"
            :title="!canCodeOperate ? '无操作权限' : (isCodeEditLocked ? '执行中不可保存' : (codeDirty ? '保存' : '没有需要保存的更改'))"
          >
            {{ isSaving ? '保存中...' : '保存' }}
          </button>
        </template>
        <template v-else>
          <button
            v-if="isCurrentFileRunning || isStopping"
            @click="stopPyFile"
            :disabled="!canCodeOperate || isStopping"
            class="btn-stop"
            :title="!canCodeOperate ? '无操作权限' : '终止当前运行的任务（任务状态将标记为「运行终止」）'"
          >
            {{ isStopping ? '终止中...' : '终止' }}
          </button>
          <button
            @click="exitTaskRecordMode"
            class="btn-back"
            title="返回文件列表"
          >
            返回
          </button>
        </template>
      </div>
    </div>

    <div class="editor-layout">
      <div class="file-list">
        <div class="file-list-content">
          <h4 v-if="listMode === 'files'">
            文件列表
            <button
              v-if="canCodeOperate"
              style="float: right;"
              @click.stop="addPyFile()"
              class="rename-btn"
              title="新建文件"
            ><i class="el-icon-folder-add"></i></button>
          </h4>
          <h4 v-else>任务管理</h4>

          <!-- 脚本类型筛选：对应 py_file.script_type（train/eval/both），旧脚本为 both -->
          <div v-if="listMode === 'files'" class="script-type-filter">
            <button
              v-for="opt in scriptTypeOptions"
              :key="opt.value"
              class="script-type-btn"
              :class="{ active: scriptTypeFilter === opt.value }"
              :title="opt.title"
              @click.stop="scriptTypeFilter = opt.value"
            >{{ opt.label }}</button>
          </div>

          <div
            v-if="listMode === 'files' && files.length && !filteredFiles.length"
            class="loading"
          >该类型下暂无文件</div>

          <ul v-if="listMode === 'files' && filteredFiles.length">
            <li
              v-for="file in filteredFiles"
              :key="file.id"
              :class="{ active: file.id === currentFileId && !viewingTaskRecord }"
            >
              <div v-if="file.id !== editingFileId" class="file-item">
                <span @click="selectFile(file)">
                  <div style="color:chocolate" v-show="file.ifEdit || (file.id === currentFileId && codeDirty)"><i v-show="file.ifSystem" class="el-icon-star-off"></i>{{ file.fileName }}</div>
                  <div v-show="!(file.ifEdit || (file.id === currentFileId && codeDirty))"><i v-show="file.ifSystem" class="el-icon-star-off"></i>{{ file.fileName }}</div>
                </span>
                <!-- 该脚本下「执行完成但未查看」的记录数（红底白字圆角矩形） -->
                <span
                  v-if="unreadCountOf(file)"
                  class="unread-badge"
                  :title="`该脚本有 ${unreadCountOf(file)} 条执行完成但尚未查看的记录`"
                >{{ unreadCountOf(file) }}</span>
                <em
                  class="script-type-tag"
                  :class="'tag-' + normalizeScriptType(file.scriptType)"
                >{{ scriptTypeLabel(file) }}</em>
                <button
                  v-if="canCodeOperate"
                  @click.stop="startEditing(file)"
                  class="rename-btn"
                  title="改名"
                ><i class="el-icon-edit"></i></button>
                <button
                  v-if="canCodeDelete && !file.ifSystem"
                  @click.stop="deletePyFile(file)"
                  class="rename-btn"
                  title="删除"
                ><i class="el-icon-folder-delete"></i></button>
              </div>
              <div v-else class="edit-mode">
                <input 
                  v-model="editingFileName" 
                  @keyup.enter="confirmRename"
                  ref="renameInput"
                >
                <button @click="confirmRename" class="confirm-btn">√</button>
                <button @click="cancelEditing" class="cancel-btn">×</button>
              </div>
            </li>
          </ul>

          <ul v-else-if="listMode === 'tasks'">
            <li v-if="isLoadingTasks" class="loading">加载中...</li>
            <li v-else-if="!taskList.length" class="loading">暂无任务</li>
            <li
              v-for="(task, index) in taskList"
              :key="task.taskId"
              :class="{ active: task.taskId === currentTaskId }"
              @click="selectTask(task)"
            >
              <div class="task-item">
                <!-- 「未读」标记嵌在标题里，才能紧跟在时间后面。
                     放在外层不行：.task-title 是 flex: 1 1 100%（独占一行），
                     加上 .task-item 的 flex-wrap: wrap，标记会被挤到下一行。 -->
                <span class="task-title">{{ index + 1 }}. {{ formatTaskTime(task.createTime) }}<span
                  v-if="isUnreadTask(task)"
                  class="unread-mark"
                  title="执行完成但尚未查看，点击该记录后即标记为已读"
                >未读</span></span>
                <!-- 编排任务拆出的子任务：在记录列表里也要能一眼认出（任务管理页看父任务） -->
                <span
                  v-if="task.isSubtask"
                  class="subtask-mark"
                  :title="'该记录是「训练+评估」编排任务拆出的子任务：' + (task.taskName || '')"
                >子任务</span>
                <span v-if="task.showName" class="task-show-name" :title="task.showName">{{ task.showName }}</span>
                <span class="task-status" :class="'task-status-' + task.status">{{ task.statusDesc }}</span>
                <button
                  v-if="canCodeOperate"
                  type="button"
                  class="btn-task-name"
                  :disabled="editingShowNameTaskId === task.taskId"
                  title="添加或更改模型优选展示名称"
                  @click.stop="editTaskShowName(task)"
                >
                  {{ editingShowNameTaskId === task.taskId ? '...' : (task.showName ? '改名' : '名称') }}
                </button>
                <button
                  v-if="canCodeOperate && Number(task.status) === 1"
                  type="button"
                  class="btn-task-show"
                  :class="{ 'btn-task-show-active': !!task.ifShow }"
                  :disabled="togglingTaskId === task.taskId"
                  :title="task.ifShow ? '已在模型优选展示，点击设为未展示' : '未展示，点击后可在模型优选选择'"
                  @click.stop="toggleTaskIfShow(task)"
                >
                  {{ togglingTaskId === task.taskId ? '...' : (task.ifShow ? '展示' : '未展示') }}
                </button>
                <button
                  v-if="canCodeDelete"
                  type="button"
                  class="btn-task-delete"
                  :disabled="deletingTaskId === task.taskId || isWaitingTask(task)"
                  :title="isWaitingTask(task)
                    ? '等待中的子任务不可删除（前置任务完成后会自动开始执行）'
                    : '删除此任务'"
                  @click.stop="deletePyTask(task)"
                >
                  {{ deletingTaskId === task.taskId ? '...' : '删除' }}
                </button>
                <button
                  v-if="canCodeOperate && Number(task.status) === 0"
                  type="button"
                  class="btn-task-stop"
                  :disabled="stoppingTaskId === task.taskId"
                  title="终止此运行中的任务（状态将标记为运行终止）"
                  @click.stop="stopTaskRecord(task)"
                >
                  {{ stoppingTaskId === task.taskId ? '...' : '终止' }}
                </button>
              </div>
            </li>
          </ul>
        </div>

        <div v-if="listMode === 'files'" class="file-description">
          <h4>文件简介</h4>
          <textarea 
            v-model="currentFileDescription" 
            placeholder="添加文件简介..."
            :disabled="!canCodeOperate"
            :readonly="!canCodeOperate"
            @blur="updateFileDescription()"
          ></textarea>
        </div>
      </div>

      <div class="editor-area">
        <div ref="editorContainer" class="editor-container"></div>
        
        <div v-if="showOutputPanel" class="output-panel" :style="{ height: outputPanelHeight + 'px' }">
          <div
            class="output-resizer"
            :class="{ active: isResizingOutput }"
            title="按住拖拽调整输出栏高度，双击恢复默认"
            @mousedown.prevent="startResizeOutput"
            @dblclick="resetOutputPanelHeight"
          ></div>
          <div class="output-header">
            <div class="output-header-left">
              <span>输出</span>
              <!-- 不适比例趋势图：解析日志里的「[中期评估] 第 XX/XX 轮」行（Multi-agent.py） -->
              <button
                class="btn-chart"
                :class="{ 'btn-chart-active': chartVisible }"
                title="按日志中的「[中期评估] 第 XX/XX 轮」绘制各栋建筑不适比例（高温+低温）曲线"
                @click="openMidEvalChart"
              >不适曲线</button>
            </div>
            <button @click="output = ''" class="btn-clear">清空</button>
          </div>
          <pre
            ref="outputContent"
            class="output-content"
            @scroll="handleOutputScroll"
          >{{ formatConsoleOutput(output) || outputPlaceholder }}</pre>
          <button
            v-if="!isOutputAtBottom"
            class="btn-scroll-bottom"
            title="回到最新输出并恢复自动跟随"
            @click="backToOutputBottom"
          >↓ 回到底部</button>
        </div>
        
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
      </div>
    </div>

    <!-- 算法配置弹窗：为当前 train / eval 脚本挂载参数（存到 py_file.algorithm_config） -->
    <algorithm-config-dialog
      :visible.sync="algorithmConfigVisible"
      :py-file="currentFile"
      @saved="onAlgorithmConfigSaved"
    />

    <!-- 不适比例趋势图：横轴=中期评估轮数，纵轴=高温不适+低温不适（每栋一条曲线） -->
    <el-dialog
      title="各栋建筑不适比例趋势"
      :visible.sync="chartVisible"
      width="900px"
      top="6vh"
      append-to-body
      @opened="handleMidEvalChartOpened"
      @closed="handleMidEvalChartClosed"
    >
      <p class="chart-hint">
        数据来源：控制台日志中的「[中期评估] 第 XX/XX 轮 | 高温/低温 …」记录（Multi-agent.py 训练过程中输出）。
        纵轴 = 高温不适比例 + 低温不适比例（合计），横轴为训练轮数；执行中图表会随日志自动刷新。
      </p>
      <div class="mid-eval-chart-wrap">
        <div ref="midEvalChart" class="mid-eval-chart"></div>
        <div v-if="!hasMidEvalData" class="mid-eval-empty">
          暂未在日志中找到「[中期评估]」记录
          <span>请确认当前执行的是 Multi-agent.py，且推进到中期评估轮次（或查看该类脚本的历史记录）</span>
        </div>
      </div>
    </el-dialog>

    <!-- 续训来源任务选择（P19-1）：列出所有含训练断点的已完成任务，选中后预览其不适曲线 -->
    <el-dialog
      title="选择续训来源任务"
      :visible.sync="resumeDialogVisible"
      width="1080px"
      top="6vh"
      append-to-body
      @opened="handleResumeDialogOpened"
      @closed="handleResumeDialogClosed"
    >
      <p class="resume-dialog-tip">
        从下表选一个<strong>执行完成</strong>的任务：系统会把该任务的训练断点（模型权重 + 已训练轮数 +
        不适曲线）复制到本次任务目录后继续训练。源任务记录保持不变，续训后的不适曲线会在所选任务的曲线上延续。
      </p>
      <div v-loading="resumeTaskLoading" class="resume-dialog-body">
        <div class="resume-task-list">
          <el-table
            ref="resumeTable"
            :data="resumeTaskList"
            height="420"
            size="mini"
            highlight-current-row
            row-key="taskId"
            @current-change="handleResumeTaskSelect"
          >
            <el-table-column prop="taskId" label="任务 ID" min-width="220">
              <template slot-scope="scope">
                <span :title="scope.row.taskId">{{ shortTaskId(scope.row.taskId) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="scriptName" label="脚本" min-width="120" show-overflow-tooltip />
            <el-table-column label="训练轮数" width="100" align="center">
              <template slot-scope="scope">
                {{ scope.row.epochsDone }}/{{ scope.row.trainEpochsTarget }}
              </template>
            </el-table-column>
            <el-table-column label="最差和" width="80" align="center">
              <template slot-scope="scope">
                {{ formatScore(scope.row.bestScore) }}
              </template>
            </el-table-column>
            <el-table-column prop="curvePoints" label="曲线点" width="72" align="center" />
            <el-table-column prop="updated" label="断点更新时间" min-width="150" />
          </el-table>
          <div v-if="!resumeTaskLoading && !resumeTaskList.length" class="resume-task-empty">
            没有找到可续训的任务
            <span>只有跑过训练且产生断点（train_progress.json）的任务才会出现在这里</span>
          </div>
        </div>
        <div class="resume-task-preview">
          <div class="resume-preview-title">
            不适曲线预览
            <span v-if="selectedResumeTaskId">（{{ shortTaskId(selectedResumeTaskId) }}）</span>
          </div>
          <div v-loading="resumeTaskDetailLoading" class="resume-preview-chart-wrap">
            <div ref="resumePreviewChart" class="resume-preview-chart"></div>
            <div
              v-if="!resumeTaskDetailLoading && selectedResumeTaskId && !hasResumePreviewData"
              class="resume-preview-empty"
            >该任务断点中没有不适曲线数据</div>
            <div
              v-if="!selectedResumeTaskId"
              class="resume-preview-empty"
            >请在左侧选择一个任务</div>
          </div>
          <div v-if="resumeTaskDetail" class="resume-preview-meta">
            <span>已训练 {{ resumeTaskDetail.epochsDone }} 轮</span>
            <span>目标 {{ resumeTaskDetail.trainEpochsTarget }} 轮</span>
            <span>最差和 {{ formatScore(resumeTaskDetail.bestScore) }}</span>
          </div>
        </div>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button
          v-if="resumeEnabled"
          size="small"
          type="danger"
          plain
          @click="disableResume"
        >关闭续训</el-button>
        <el-button size="small" @click="resumeDialogVisible = false">取消</el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!selectedResumeTaskId"
          @click="confirmResumeTask"
        >确定（从该任务续训）</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import * as monaco from 'monaco-editor';
import * as echarts from 'echarts';
import axios from 'axios';
import { PERMS } from '../utils/permissions';
import AlgorithmConfigDialog from './AlgorithmConfigDialog.vue';

/**
 * 支持 --resume 断点续训的脚本名单，与后端 BaseDataService 的能力过滤保持一致：
 * 目前只有 Multi-agent.py 声明了该参数（从 checkpoints/multi_agent_resume 接着训），
 * 其余脚本硬传会 "unrecognized arguments" 直接退出，所以工具栏只在命中名单时才显示开关。
 */
const RESUME_SUPPORTED_FILES = ['Multi-agent.py'];
/** 「续训」开关的本地存储键（属执行偏好，跨文件、跨刷新都保留） */
const RESUME_STORAGE_KEY = 'citylearn.monaco.resumeEnabled';

export default {
  name: 'PythonEditor',
  components: {
    AlgorithmConfigDialog
  },
  inject: {
    hasPermission: {
      default: () => () => true
    }
  },
  props: {
    /* eslint-disable */
    filePath: {
      type: String,
      default: ''
    },
    apiBaseUrl: {
      type: String,
      default: process.env.VUE_APP_API_BASE_URL || '/api'
    }
  },
  data() {
    return {
      editor: null,
      code: '',
      isSaving: false,
      isTogglingIfShow: false,
      isRunning: false,
      /** 「续训」开关：执行时是否给脚本追加 --resume（默认关；只对支持的脚本显示） */
      resumeEnabled: false,
      /** 正在请求终止任务（终止按钮 loading 态） */
      isStopping: false,
      /** 正在终止的记录 taskId（任务列表里的终止按钮 loading 态） */
      stoppingTaskId: null,
      /** pyId -> { taskId, status }，status: 0执行中 1成功 2失败 3运行终止 */
      runningTasks: {},
      pollTimer: null,
      consolePollTimer: null,
      activePollTaskId: null,
      isPollingTask: false,
      output: '',
      /** 输出栏高度（px），可通过顶部拖拽条调整 */
      outputPanelHeight: 200,
      /** 是否正在拖拽调整输出栏高度 */
      isResizingOutput: false,
      /** 是否自动跟随最新输出滚动到底部（用户上翻查看历史时置 false） */
      outputAutoScroll: true,
      /** 输出区当前是否已滚动到最底部 */
      isOutputAtBottom: true,
      error: '',
      fileName: '',
      /** 「算法配置」弹窗可见性 */
      algorithmConfigVisible: false,
      files: [],
      currentFileId: null,
      currentFile: null,
      currentFileDescription: '',
      isLoadingFiles: false,
      editingFileId: null,
      editingFileName: '',
      editingFileOriginalName: '',
      /** files | tasks */
      listMode: 'files',
      /**
       * 文件列表筛选：all | train | eval | both
       * 取值对应 py_file.script_type：
       *   train 只训练 / eval 只评估 / both 训练+评估一体
       */
      scriptTypeFilter: 'all',
      scriptTypeOptions: [
        { value: 'all', label: '全部', title: '显示全部脚本类型' },
        { value: 'train', label: '训练', title: '只显示「只训练」脚本' },
        { value: 'eval', label: '评估', title: '只显示「只评估」脚本' },
        { value: 'both', label: '训练+评估', title: '只显示「训练+评估一体」脚本' }
      ],
      taskList: [],
      isLoadingTasks: false,
      currentTaskId: null,
      /**
       * 输出面板当前展示的是哪个 taskId 的日志。
       * 用于避免「后台仍在轮询运行中任务」的输出覆盖用户正在查看的历史记录日志。
       */
      viewedTaskId: null,
      viewingTaskRecord: false,
      togglingTaskId: null,
      editingShowNameTaskId: null,
      deletingTaskId: null,
      /** 当前编辑器内容相对已保存原文是否有未保存改动 */
      codeDirty: false,
      /**
       * 待处理的跳转请求 { pyId, taskId }：由「任务管理」页点【详情】经 App 调
       * openTaskRecord() 写入，文件列表就绪后消费。
       */
      pendingNav: null,
      /** 按脚本 id 聚合的「执行完成但未查看」记录数（pyId -> count），用于文件列表红点 */
      unreadByPyId: {},
      /** 不适比例趋势图弹窗可见性 */
      chartVisible: false,
      /** 解析后的中期评估数据 { rounds, series, detail } */
      midEvalData: null,
      /** ECharts 实例（非渲染需要，仅为复用） */
      midEvalChart: null,
      /** 已绘制的数据指纹：日志轮询频繁，数据没变时不重复 setOption */
      midEvalChartSignature: '',
      /* ---------------- 断点续训来源任务（P19-1） ---------------- */
      /** 续训来源任务 ID：非空 = 执行时从该已完成任务的断点续训 */
      resumeFromTaskId: null,
      /** 续训来源任务选择弹窗可见性 */
      resumeDialogVisible: false,
      /** 可续训任务列表加载中 */
      resumeTaskLoading: false,
      /** 可续训任务列表（后端 getResumableTaskList） */
      resumeTaskList: [],
      /** 当前选中的来源任务 ID */
      selectedResumeTaskId: null,
      /** 选中任务的断点详情（后端 getTaskTrainProgress，含 midEvalHistory） */
      resumeTaskDetail: null,
      /** 断点详情加载中 */
      resumeTaskDetailLoading: false,
      /** 续训预览曲线（ECharts 实例 + 数据 + 指纹） */
      resumePreviewChart: null,
      resumePreviewData: null,
      resumePreviewSignature: ''
    };
  },
  computed: {
    canCodeOperate() {
      return this.hasPermission(PERMS.CODE_EDITOR_OPERATE);
    },
    canCodeDelete() {
      return this.hasPermission(PERMS.CODE_EDITOR_DELETE);
    },
    /** 按脚本类型筛选后的文件列表（py_file.script_type：train/eval/both） */
    filteredFiles() {
      const files = this.files || [];
      if (this.scriptTypeFilter === 'all') {
        return files;
      }
      return files.filter(
        (file) => this.normalizeScriptType(file.scriptType) === this.scriptTypeFilter
      );
    },
    fileId() {
      return btoa(this.filePath); // 简单的路径编码
    },
    /**
     * 是否显示「配置」按钮：只有「只训练」(train) / 「只评估」(eval) 类型的脚本可配。
     * both（训练+评估一体）与历史脚本不显示 —— 它们的训测数据集由 ResMARL 配置页统一管理。
     */
    canConfigureCurrentFile() {
      const type = this.currentFile && this.currentFile.scriptType
      return type === 'train' || type === 'eval'
    },
    isCurrentFileRunning() {
      if (!this.currentFileId) {
        return false;
      }
      const task = this.runningTasks[this.currentFileId];
      return task && Number(task.status) === 0;
    },
    /** 启动中或当前文件执行中：禁止改代码与保存 */
    isCodeEditLocked() {
      return this.isRunning || this.isCurrentFileRunning;
    },
    currentFileIfShow() {
      return !!(this.currentFile && this.currentFile.ifShow);
    },
    runButtonLabel() {
      if (this.isCurrentFileRunning) {
        return '执行中';
      }
      if (this.isRunning) {
        return '启动中...';
      }
      return '执行';
    },
    runButtonDisabled() {
      return (
        !this.currentFile ||
        this.codeDirty ||
        this.isCurrentFileRunning ||
        this.isRunning ||
        this.isSaving ||
        this.viewingTaskRecord ||
        this.listMode === 'tasks'
      );
    },
    showOutputPanel() {
      return !!(
        this.output ||
        this.error ||
        this.isCurrentFileRunning ||
        this.isPollingTask ||
        (this.listMode === 'tasks' && this.currentTaskId)
      );
    },
    /** 输出面板当前展示的内容是否来自「正在运行」的任务（决定空输出时的占位文案） */
    isViewingRunningTaskOutput() {
      if (this.viewedTaskId) {
        return this.isPollingTask && this.viewedTaskId === this.activePollTaskId;
      }
      return this.isCurrentFileRunning;
    },
    /** 输出为空时的占位文案 */
    outputPlaceholder() {
      if (this.isViewingRunningTaskOutput) {
        return '运行中，等待输出…';
      }
      if (this.listMode === 'tasks' && this.currentTaskId) {
        return '该记录暂无输出';
      }
      return '';
    },
    runButtonTitle() {
      if (!this.currentFile) {
        return '请先选择文件';
      }
      if (this.codeDirty) {
        return '请先保存后再执行';
      }
      if (this.isCurrentFileRunning) {
        return '当前文件正在执行';
      }
      if (this.resumeEnabled && this.resumeSupported) {
        return '执行 Python 脚本（断点续训：追加 --resume）';
      }
      return '执行 Python 脚本';
    },
    /** 当前脚本是否支持 --resume（决定工具栏是否显示「续训」开关） */
    resumeSupported() {
      return !!this.currentFile && RESUME_SUPPORTED_FILES.indexOf(this.currentFile.fileName) > -1;
    },
    /** 「续训」开关的悬浮提示：说清打开后会从哪个任务续训、断点怎么处理 */
    resumeSwitchTitle() {
      if (this.isCodeEditLocked) {
        return '执行中不可切换续训开关';
      }
      if (!this.resumeEnabled) {
        return '已关闭：每次从头训练。点击可选择一个「执行完成」的任务作为续训来源';
      }
      if (this.resumeFromTaskId) {
        return '已开启：执行时把任务 ' + this.shortTaskId(this.resumeFromTaskId) +
          ' 的训练断点（模型权重 + 已训练轮数 + 不适曲线）复制到本次任务目录后继续训练；' +
          '源任务记录保持不变，--train-epochs 按「目标总轮数」解释';
      }
      return '已开启（未指定来源任务）：执行时追加 --resume，' +
        '从 citylearnpy/checkpoints/multi_agent_resume 接着训；建议点击选择一个具体任务作为来源';
    },
    /** 日志里是否解析出了中期评估数据（决定图表区显示曲线还是空提示） */
    hasMidEvalData() {
      return !!(this.midEvalData && this.midEvalData.series && this.midEvalData.series.length);
    },
    /** 续训预览里是否解析出了曲线数据 */
    hasResumePreviewData() {
      return !!(this.resumePreviewData && this.resumePreviewData.series &&
        this.resumePreviewData.series.length);
    }
  },
  watch: {
    /**
     * 「续训」开关写入 localStorage：它属执行偏好，重开页面还要重新点一遍很容易漏
     * （漏点就从头白跑一轮训练），所以跨刷新保留。
     */
    resumeEnabled(value) {
      try {
        window.localStorage.setItem(RESUME_STORAGE_KEY, value ? '1' : '0');
      } catch (error) {
        // 隐私模式等写入失败的场景：不影响本次执行
      }
    },
    /**
     * 切换「全部 / 训练 / 评估 / 训练+评估」时重新拉取列表，
     * 由接口按 scriptType 过滤（见 fetchFiles）。
     * 刻意不强制跳转当前打开的文件，避免把未保存的改动切走。
     */
    scriptTypeFilter() {
      this.fetchFiles();
    },
    canCodeOperate: {
      immediate: true,
      handler(val) {
        if (!val) {
          this.setEditorReadOnly(true);
          this.editingFileId = null;
        } else {
          this.setEditorReadOnly(this.viewingTaskRecord || this.isCodeEditLocked);
        }
      }
    },
    isCodeEditLocked(locked) {
      this.setEditorReadOnly(this.viewingTaskRecord || locked);
    },
    filePath: {
      immediate: true,
      handler(newPath) {
        if (newPath) {
          this.fileName = newPath.split('/').pop();
          this.loadCode();
        }
      }
    },
    showOutputPanel(visible) {
      if (visible) {
        this.$nextTick(() => {
          this.handleResize();
          this.scrollOutputToBottom();
        });
      }
    },
    /**
     * 执行中日志每 300ms 刷新一次，这里同步刷新图表（仅当图表弹窗打开时才解析）。
     * 解析成本很低（只在含 [中期评估] 时逐行匹配），且数据未变化时不会重复 setOption。
     */
    output() {
      if (this.chartVisible) {
        this.renderMidEvalChart(false);
      }
    }
  },
  mounted() {
    this.restoreResumePref();
    this.initEditor();
    // 留住首次加载的 promise：「任务管理」页可能在列表还没回来时就要求跳转
    this.filesLoadedPromise = this.fetchFiles();
    window.addEventListener('resize', this.handleResize);
  },
  beforeDestroy() {
    this.stopPollTask();
    if (this.editor) {
      this.editor.dispose();
    }
    if (this.midEvalChart) {
      this.midEvalChart.dispose();
      this.midEvalChart = null;
    }
    if (this.resumePreviewChart) {
      this.resumePreviewChart.dispose();
      this.resumePreviewChart = null;
    }
    window.removeEventListener('resize', this.handleResize);
  },
  methods: {
    /**
     * 归一化脚本类型：空 / 未知一律按 both 处理
     * （与 py_file.script_type 的默认值一致，兼容未迁移的历史数据）
     */
    normalizeScriptType(value) {
      const t = (value || '').toString().trim().toLowerCase();
      return t === 'train' || t === 'eval' ? t : 'both';
    },

    /** 文件类型短标签（显示在文件名右侧） */
    scriptTypeLabel(file) {
      const map = { train: '训练', eval: '评估', both: '训练+评估' };
      return map[this.normalizeScriptType(file && file.scriptType)];
    },

    /**
     * 拉取文件列表。
     *
     * scriptTypeFilter !== 'all' 时把类型一并带给后端，由服务端按 py_file.script_type 过滤
     * （接口：GET /web/basedata/getPyFileList?scriptType=train|eval|both）。
     *
     * 客户端仍保留 filteredFiles 兜底：后端若尚未重启/升级，会忽略该参数并返回全部类型，
     * 此时客户端筛选照常生效 —— 保证前端先部署也不会出现列表空白或串类型。
     */
    async fetchFiles() {
      this.isLoadingFiles = true;
      const params = {};
      if (this.scriptTypeFilter && this.scriptTypeFilter !== 'all') {
        params.scriptType = this.scriptTypeFilter;
      }
      try {
        const response = await axios.get('/api/web/basedata/getPyFileList', { params });
        this.files = (response.data && response.data.data) || [];
        // 顺带拉一次未读数（不阻塞主流程）：文件列表要在对应脚本旁显示未读红点
        this.refreshTaskNotice();
        // 有「任务管理」页的跳转请求：优先打开它指定的记录，本次不做默认选中
        if (await this.consumePendingNav()) {
          return;
        }
        // 仅首次加载时默认选中第一个；切换筛选时不动用户当前打开的文件
        if (!this.currentFileId && this.files.length) {
          this.selectFile(this.files[0]);
        }
      } catch (error) {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      } finally {
        this.isLoadingFiles = false;
      }
    },

    /**
     * 【供 App 通过 ref 调用】打开指定脚本的某条任务。
     *
     * 「任务管理」页点【详情】后 App 会切到本页面并调用这个方法。这里刻意不走
     * provide/inject 传值，而是由父组件主动调用：动态组件 `<component :is>` 既可能
     * 被重建、也可能已存在，主动调用对两种情况都成立，不依赖任何时序假设。
     *
     * @param {string} pyId   记录所属脚本的 py_file.id
     * @param {string} taskId 要定位的任务 id
     */
    async openTaskRecord(pyId, taskId) {
      if (!pyId || !taskId) {
        return;
      }
      this.pendingNav = { pyId: pyId, taskId: taskId };
      try {
        await this.ensureFilesLoaded();
      } catch (error) {
        // fetchFiles 内部已做提示，这里不重复报错
        console.error('等待文件列表就绪失败:', error);
      }
      await this.consumePendingNav();
    },

    /** 等文件列表就绪：首次进入时 fetchFiles 可能仍在进行中 */
    async ensureFilesLoaded() {
      if (!this.filesLoadedPromise) {
        // 极端情况（mounted 尚未执行）：等一次渲染后再确认
        await this.$nextTick();
      }
      if (this.filesLoadedPromise) {
        await this.filesLoadedPromise;
      }
    },

    /**
     * 消费待处理的跳转请求：选中脚本 → 切到它的任务列表并定位到指定那条。
     *
     * @returns {boolean} true 表示本次文件列表加载已被它接管，调用方不要再做默认选中
     */
    async consumePendingNav() {
      const pending = this.pendingNav;
      if (!pending || !pending.taskId) {
        return false;
      }
      const pyId = pending.pyId;
      const taskId = pending.taskId;
      const file = (this.files || []).find((item) => item.id === pyId);
      if (!file) {
        // 可能被「脚本类型」筛选挡住了：放开筛选重取一次（请求保留，下次加载即命中）
        if (this.scriptTypeFilter !== 'all') {
          this.scriptTypeFilter = 'all';
          return true;
        }
        this.pendingNav = null;
        this.$message.warning('该记录所属的脚本已不存在或不在当前列表中，无法打开');
        return false;
      }
      this.pendingNav = null;
      await this.selectFile(file);
      await this.enterTaskRecordMode(taskId);
      return true;
    },

    /**
     * 拉取「按脚本聚合的未读数」，用于文件列表在对应脚本旁显示未读红点。
     * 失败静默：后端重启期间会连续失败，下次刷新即恢复。
     */
    async refreshTaskNotice() {
      try {
        const res = await axios.get('/api/web/basedata/getPyTaskNoticeSummary')
        if (res.data && res.data.code === 0 && res.data.data) {
          this.unreadByPyId = res.data.data.unreadByPyId || {}
        }
      } catch (e) {
        // 不弹提示（后端重启期间会连续失败），但留一条 warn 便于排查"红点不显示"
        console.warn('[未读红点] 拉取 getPyTaskNoticeSummary 失败:', e && e.message)
      }
    },

    /** 某个脚本下「执行完成但未查看」的记录数；为 0 时模板不渲染红点 */
    unreadCountOf(file) {
      if (!file || !this.unreadByPyId) {
        return 0
      }
      return Number(this.unreadByPyId[file.id]) || 0
    },

    /**
     * 任务是否已结束（即已有结果可查看）：1成功 / 2失败 / 3运行终止 / 4已中断。
     * 0-执行中 与 5-待执行 都不算。
     */
    isFinishedTask(task) {
      return !!task && [1, 2, 3, 4].indexOf(Number(task.status)) >= 0
    },

    /** 任务是否未读：已结束 且 if_notified 为 0 */
    isUnreadTask(task) {
      return this.isFinishedTask(task) && !task.ifNotified
    },

    /**
     * 把一条任务标记为已读：未读标记消失，并刷新文件列表红点 + 通知 App 刷新顶栏计数。
     * 只对「已结束且未读」的记录调用（见 selectTaskRecord）。
     */
    async markTaskNotified(task) {
      if (!task || !task.taskId) {
        return
      }
      try {
        await axios.post('/api/web/basedata/markPyTaskNotified', { taskId: task.taskId })
        this.$set(task, 'ifNotified', true)
        await this.refreshTaskNotice()
        // 通知 App 立即刷新顶栏「待查看」数量（否则要等下一次 5 秒轮询）
        this.$emit('task-notice-changed')
      } catch (error) {
        console.error('标记任务已读失败:', error)
      }
    },
    
    async selectFile(file) {
      this.stopPollTask();
      this.listMode = 'files';
      this.viewingTaskRecord = false;
      this.currentTaskId = null;
      this.viewedTaskId = null;
      this.codeDirty = false;
      this.currentFileId = file.id;
      this.currentFile = file;
      this.currentFileDescription = file.description;
      this.filePath = file.path;
      this.fileName = file.fileName || file.name;
      await this.checkRunningTask(file.id);
      const running = this.runningTasks[file.id];
      if (running && Number(running.status) === 0) {
        this.startPollTask(running.taskId, file.id);
      }
      this.setEditorReadOnly(this.isCodeEditLocked);
      this.loadCode();
    },

    /**
     * 根据编辑器内容与已保存原文同步“未保存”状态（驱动执行/保存按钮）
     */
    syncCodeDirtyState(editorValue) {
      if (!this.currentFile) {
        this.codeDirty = false;
        return;
      }
      const value = editorValue != null ? editorValue : (this.editor ? this.editor.getValue() : this.currentFile.code);
      const original = this.currentFile.oriCode != null ? this.currentFile.oriCode : '';
      this.currentFile.code = value;
      const dirty = value !== original;
      this.codeDirty = dirty;
      this.$set(this.currentFile, 'ifEdit', dirty);
      const idx = this.files.findIndex((f) => f.id === this.currentFile.id);
      if (idx >= 0) {
        this.$set(this.files[idx], 'ifEdit', dirty);
        if (this.files[idx] !== this.currentFile) {
          this.$set(this.files[idx], 'code', value);
        }
      }
    },

    setEditorReadOnly(readOnly) {
      if (this.editor) {
        this.editor.updateOptions({
          readOnly: !!(readOnly || !this.canCodeOperate || this.isCodeEditLocked)
        });
      }
    },

    ensureCodeOperate() {
      if (!this.canCodeOperate) {
        this.$message.warning('无代码编辑操作权限');
        return false;
      }
      return true;
    },

    ensureCodeDelete() {
      if (!this.canCodeDelete) {
        this.$message.warning('无代码删除权限');
        return false;
      }
      return true;
    },

    formatTaskTime(time) {
      if (!time) {
        return '-';
      }
      const date = new Date(time);
      if (Number.isNaN(date.getTime())) {
        return String(time);
      }
      const pad = (n) => String(n).padStart(2, '0');
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    },

    async toggleIfShow() {
      if (!this.ensureCodeOperate() || !this.currentFile) {
        return;
      }
      this.isTogglingIfShow = true;
      const nextIfShow = !this.currentFileIfShow;
      try {
        const response = await axios.post('/api/web/basedata/updatePyFileIfShow', {
          id: this.currentFile.id,
          ifShow: nextIfShow
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '更新展示状态失败');
          return;
        }
        const updated = response.data.data || {};
        const ifShow = updated.ifShow != null ? updated.ifShow : nextIfShow;
        this.currentFile = { ...this.currentFile, ifShow };
        const fileIndex = this.files.findIndex((file) => file.id === this.currentFile.id);
        if (fileIndex >= 0) {
          this.$set(this.files, fileIndex, { ...this.files[fileIndex], ifShow });
        }
        this.$message.success(ifShow ? '已设为展示中' : '已设为未展示');
      } catch (error) {
        console.error('更新展示状态失败:', error);
        this.$message.error('更新展示状态失败');
      } finally {
        this.isTogglingIfShow = false;
      }
    },

    async toggleTaskIfShow(task) {
      if (!this.ensureCodeOperate()) return;
      if (!task || !task.taskId || Number(task.status) !== 1) {
        return;
      }
      const nextIfShow = !task.ifShow;
      this.togglingTaskId = task.taskId;
      try {
        const response = await axios.post('/api/web/basedata/updatePyTaskIfShow', {
          taskId: task.taskId,
          ifShow: nextIfShow
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '更新记录展示状态失败');
          return;
        }
        const updated = response.data.data || {};
        const ifShow = updated.ifShow != null ? updated.ifShow : nextIfShow;
        const idx = this.taskList.findIndex((t) => t.taskId === task.taskId);
        if (idx >= 0) {
          this.$set(this.taskList, idx, { ...this.taskList[idx], ifShow });
        }
        this.$message.success(ifShow ? '已设为【展示】，可在模型优选选择' : '已设为【未展示】');
      } catch (error) {
        console.error('更新记录展示状态失败:', error);
        this.$message.error('更新记录展示状态失败');
      } finally {
        this.togglingTaskId = null;
      }
    },

    async editTaskShowName(task) {
      if (!this.ensureCodeOperate()) return;
      if (!task || !task.taskId) {
        return;
      }
      let value;
      try {
        const result = await this.$prompt(
          '有名称时，模型优选分组将按此名称显示；留空则显示「代码名 + 记录时间」。',
          '展示名称',
          {
            confirmButtonText: '保存',
            cancelButtonText: '取消',
            inputValue: task.showName || '',
            inputPlaceholder: '例如：CHESCA-ResMARL α=0.15',
            inputValidator: (val) => {
              if (val != null && String(val).trim().length > 128) {
                return '最多 128 个字符';
              }
              return true;
            }
          }
        );
        value = result && result.value != null ? String(result.value).trim() : '';
      } catch (e) {
        return;
      }
      const nextName = value || '';
      const prevName = (task.showName || '').trim();
      if (nextName === prevName) {
        return;
      }
      this.editingShowNameTaskId = task.taskId;
      try {
        const response = await axios.post('/api/web/basedata/updatePyTaskShowName', {
          taskId: task.taskId,
          showName: nextName
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '更新展示名称失败');
          return;
        }
        const updated = response.data.data || {};
        const showName = updated.showName != null ? updated.showName : (nextName || null);
        const idx = this.taskList.findIndex((t) => t.taskId === task.taskId);
        if (idx >= 0) {
          this.$set(this.taskList, idx, {
            ...this.taskList[idx],
            showName: showName || null
          });
        }
        this.$message.success(showName ? '展示名称已保存' : '已清除展示名称');
      } catch (error) {
        console.error('更新展示名称失败:', error);
        this.$message.error('更新展示名称失败');
      } finally {
        this.editingShowNameTaskId = null;
      }
    },

    /**
     * 是否「等待中」的子任务（status=6）：编排任务里排队等训练完成的评估子任务。
     * 这种记录不可删除 —— 训练一结束它就会被自动拉起，删掉会让父任务卡住
     * （后端 deletePyTask 也会拦，这里先给出即时提示）。
     */
    isWaitingTask(task) {
      return !!task && Number(task.status) === 6;
    },

    async deletePyTask(task) {
      if (!this.ensureCodeDelete()) return;
      if (!task || !task.taskId) {
        return;
      }
      if (this.isWaitingTask(task)) {
        this.$message.warning('该子任务正在等待中（前置任务完成后会自动开始），不可删除');
        return;
      }
      const label = this.formatTaskTime(task.createTime);
      try {
        await this.$confirm(
          Number(task.status) === 0
            ? `记录「${label}」仍在执行中，删除后列表将不再显示。确定删除？`
            : `确定删除任务「${label}」吗？`,
          '删除任务',
          { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
        );
      } catch (e) {
        return;
      }
      this.deletingTaskId = task.taskId;
      try {
        const response = await axios.post('/api/web/basedata/deletePyTask', {
          taskId: task.taskId
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '删除失败');
          return;
        }
        const idx = this.taskList.findIndex((t) => t.taskId === task.taskId);
        if (idx >= 0) {
          this.taskList.splice(idx, 1);
        }
        if (this.currentFileId && this.runningTasks[this.currentFileId]
            && this.runningTasks[this.currentFileId].taskId === task.taskId) {
          const next = { ...this.runningTasks };
          delete next[this.currentFileId];
          this.runningTasks = next;
        }
        if (this.activePollTaskId === task.taskId) {
          this.stopPollTask();
        }
        if (this.currentTaskId === task.taskId) {
          this.currentTaskId = null;
          this.viewingTaskRecord = false;
          this.output = '';
          this.error = '';
          this.setEditorReadOnly(false);
          if (this.currentFile) {
            this.fileName = this.currentFile.fileName;
            this.loadCode();
          }
        }
        this.$message.success('已删除');
      } catch (error) {
        console.error('删除任务失败:', error);
        this.$message.error('删除失败');
      } finally {
        this.deletingTaskId = null;
      }
    },

    async enterTaskRecordMode(taskIdToSelect = null) {
      if (!this.currentFile) {
        this.$message.warning('请先选择文件');
        return;
      }
      this.listMode = 'tasks';
      this.viewingTaskRecord = false;
      if (taskIdToSelect) {
        this.currentTaskId = taskIdToSelect;
        this.viewedTaskId = taskIdToSelect;
      } else {
        this.currentTaskId = null;
        this.output = '';
        this.error = '';
        // 未指定记录时：若后台有任务在跑，默认继续显示它的实时日志
        this.viewedTaskId = this.isPollingTask ? this.activePollTaskId : null;
      }
      await this.fetchTaskList();
      if (taskIdToSelect) {
        const task = this.taskList.find((t) => t.taskId === taskIdToSelect);
        if (task) {
          await this.selectTaskRecord(task, false);
        }
      }
    },

    exitTaskRecordMode() {
      this.stopPollTask();
      this.output = '';
      this.error = '';
      this.listMode = 'files';
      this.viewingTaskRecord = false;
      this.currentTaskId = null;
      this.viewedTaskId = null;
      if (this.currentFile) {
        this.fileName = this.currentFile.fileName;
        this.loadCode();
        const running = this.runningTasks[this.currentFile.id];
        if (running && Number(running.status) === 0) {
          this.startPollTask(running.taskId, this.currentFile.id);
        }
      }
      this.setEditorReadOnly(this.isCodeEditLocked);
    },

    /**
     * 算法配置保存成功：把新配置同步到本地文件对象。
     * 只改这一个字段，不必为了刷新它再拉一次整个文件列表。
     */
    onAlgorithmConfigSaved(algorithmConfig) {
      if (!this.currentFile) {
        return
      }
      const fileId = this.currentFile.id
      this.currentFile = { ...this.currentFile, algorithmConfig }
      const index = this.files.findIndex((file) => file.id === fileId)
      if (index >= 0) {
        this.$set(this.files, index, { ...this.files[index], algorithmConfig })
      }
    },

    async fetchTaskList() {
      if (!this.currentFileId) {
        return;
      }
      this.isLoadingTasks = true;
      try {
        const response = await axios.get('/api/web/basedata/getPyTaskList', {
          params: { pyId: this.currentFileId }
        });
        if (response.data.code === 0) {
          this.taskList = response.data.data || [];
        } else {
          this.$message.error(response.data.message || '加载任务列表失败');
        }
      } catch (error) {
        console.error('加载任务列表失败:', error);
        this.$message.error('加载任务列表失败');
      } finally {
        this.isLoadingTasks = false;
      }
    },

    async selectTask(task) {
      await this.selectTaskRecord(task, true);
    },

    async selectTaskRecord(task, restartPoll) {
      this.currentTaskId = task.taskId;
      // 锁定输出面板归属到这条记录，避免后台轮询把运行中任务的日志写进来
      this.viewedTaskId = task.taskId;
      this.viewingTaskRecord = true;
      this.setEditorReadOnly(true);
      try {
        const response = await axios.get('/api/web/basedata/getPyTaskScript', {
          params: { taskId: task.taskId }
        });
        if (response.data.code !== 0) {
          this.$message.error(response.data.message || '加载脚本失败');
          return;
        }
        const script = response.data.data;
        this.fileName = `[记录] ${script.fileName}`;
        if (this.editor) {
          this.editor.setValue(script.code || '');
        }
        const resultRes = await axios.get('/api/web/basedata/getPyTaskOutput', {
          params: { taskId: task.taskId }
        });
        if (this.isApiSuccess(resultRes) && resultRes.data.data) {
          const result = resultRes.data.data;
          // 无论有无输出都整体替换，避免残留上一条记录的日志
          this.output = result.output == null ? '' : result.output;
          this.scrollOutputToBottom();
          // 切换记录时，错误信息也一并切换（避免残留上一条任务的错误）
          this.error = result.errorMessage || '';
          if (restartPoll && Number(result.status) === 0 && this.currentFileId) {
            this.startPollTask(task.taskId, this.currentFileId);
          } else if (Number(result.status) === 0 && this.activePollTaskId === task.taskId) {
            this.isPollingTask = true;
          }
          // 打开的是「已结束但未读」的记录 → 标记已读：未读标记消失，
          // 并同步刷新文件列表红点与顶栏「待查看」数量
          if (this.isFinishedTask(task) && !task.ifNotified) {
            this.markTaskNotified(task);
          }
        }
      } catch (error) {
        console.error('加载任务脚本失败:', error);
        this.$message.error('加载任务脚本失败');
      }
    },
    async deletePyFile(file){
      if (!this.ensureCodeDelete()) return;
      if (!file) return
      if (file.ifSystem) {
        this.$message.warning('系统内置文件不可删除')
        return
      }
      try {
        const response = await axios.post('/api/web/basedata/deletePyFile', {
          id: file.id,
        });
         console.log(response.data)
        if (response.data.code==0) {
          this.files.splice(this.files.findIndex(item => item.id === file.id), 1); 
        } else {
          this.$message.error(response.data.message || '删除失败');
        }
      } catch (error) {
        console.error('删除失败:', error);
        this.$message.error('删除失败');
      } 
    },
    async addPyFile(){
      if (!this.ensureCodeOperate()) return;
      if(this.isSaving==true){
        return
      }
      this.isSaving = true;
      try {
        const response = await axios.post('/api/web/basedata/addPyFile', {});
         console.log(response.data)
        if (response.data.code==0) {
          this.files.push(response.data.data)
        } else {
          this.$message.error(response.data.message || '添加失败');
        }
      } catch (error) {
        console.error('添加失败:', error);
        this.$message.error('添加失败');
      } finally {
        setTimeout(() => {
          this.isSaving = false;
        }, 1000);
        
      }
    },

    async updateFileDescription(){
      if (!this.ensureCodeOperate()) return;
      if(null==this.currentFile){
        return;
      }
      this.currentFile.description=this.currentFileDescription
      console.log(this.currentFile.description)
       console.log(this.currentFileDescription)
      try {
        const response = await axios.post('/api/web/basedata/savePyFile', {
          id: this.currentFile.id,
          description:this.currentFile.description
        });
        console.log(response.data)
        if (response.data.code==0) {
        } else {
          this.$message.error(response.data.message || '保存失败');
        }
      } catch (error) {
        console.error('保存失败:', error);
        this.$message.error('保存失败');
      }
    },
    
    initEditor() {
      this.editor = monaco.editor.create(this.$refs.editorContainer, {
        value: '# 加载中...\n',
        language: 'python',
        theme: 'vs-dark',
        automaticLayout: false, // 我们手动处理布局
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        folding: true,
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        lineNumbersMinChars: 3,
        renderLineHighlight: 'all',
        scrollbar: {
          vertical: 'auto',
          horizontal: 'auto'
        }
      });
      
      // 监听内容变化：与已保存原文不一致时禁止执行，保存后才能执行
      this.editor.onDidChangeModelContent(() => {
        if (!this.currentFile || this.viewingTaskRecord || this.listMode === 'tasks') {
          return;
        }
        this.syncCodeDirtyState(this.editor.getValue());
      });
    
    },
    
    async loadCode() {
      if(null==this.currentFile || null==this.currentFile.code || this.currentFile.code==''){
        axios.get('/api/web/basedata/getPyFile', {
        params: {
          id: this.currentFileId,
        }
      })
      .then(response => {
         const code = response.data.data;
         this.currentFile.code=code;
         this.currentFile.oriCode=code;
         this.$set(this.currentFile, 'ifEdit', false);
         this.codeDirty = false;
          this.editor.setValue(this.currentFile.code);
          this.code = code;
          this.error = '';
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      })
      }else{
        if (this.currentFile.oriCode == null) {
          this.currentFile.oriCode = this.currentFile.code;
        }
        this.codeDirty = this.currentFile.code !== this.currentFile.oriCode;
        this.$set(this.currentFile, 'ifEdit', this.codeDirty);
        this.editor.setValue(this.currentFile.code);
        this.code = this.currentFile.code;
          this.error = '';
      }
      
    },
    
    async saveCode() {
      if (!this.ensureCodeOperate()) return;
      if (!this.currentFile) {
        return;
      }
      if (this.isCodeEditLocked) {
        this.$message.warning('代码执行中，不可保存');
        return;
      }
      if (!this.codeDirty) {
        this.$message.info('没有需要保存的更改');
        return;
      }
      this.isSaving = true;
      this.error = '';
      
      try {
        const codeToSave = this.editor ? this.editor.getValue() : this.currentFile.code;
        const response = await axios.post('/api/web/basedata/savePyFile', {
          id: this.currentFile.id,
          code: codeToSave
        });
        console.log(response.data)
        if (response.data.code==0) {
          this.currentFile.code = codeToSave;
          this.currentFile.oriCode = codeToSave;
          this.codeDirty = false;
          this.$set(this.currentFile, 'ifEdit', false);
          const idx = this.files.findIndex((f) => f.id === this.currentFile.id);
          if (idx >= 0) {
            this.$set(this.files[idx], 'ifEdit', false);
            this.$set(this.files[idx], 'code', codeToSave);
            this.$set(this.files[idx], 'oriCode', codeToSave);
          }
          this.$message.success('保存成功');
        } else {
          this.$message.error(response.data.message || '保存失败');
        }
      } catch (error) {
        console.error('保存失败:', error);
        this.$message.error('保存失败');
      } finally {
        this.isSaving = false;
      }
    },
    
    async checkRunningTask(pyId) {
      if (!pyId) {
        return;
      }
      try {
        const response = await axios.get('/api/web/basedata/getRunningPyTask', {
          params: { pyId }
        });
        if (response.data.code === 0 && response.data.data) {
          const task = response.data.data;
          this.runningTasks = {
            ...this.runningTasks,
            [pyId]: { taskId: task.taskId, status: task.status }
          };
        } else {
          const next = { ...this.runningTasks };
          delete next[pyId];
          this.runningTasks = next;
        }
      } catch (error) {
        console.error('查询执行中任务失败:', error);
      }
    },

    isApiSuccess(response) {
      return response && response.data && Number(response.data.code) === 0;
    },

    formatConsoleOutput(text) {
      if (!text) {
        return '';
      }
      return text.replace(/\u001b\[[0-9;]*m/g, '');
    },

    /** 输出区是否已滚动到底部（留 16px 容差，避免亚像素误差误判） */
    isOutputScrolledToBottom(el) {
      if (!el) {
        return true;
      }
      return el.scrollHeight - el.scrollTop - el.clientHeight <= 16;
    },

    /**
     * 输出区滚动事件：用户手动上翻时暂停自动跟随，滚回底部后自动恢复。
     * 程序设置 scrollTop 也会触发本事件，此时判定为「已贴底」并恢复跟随。
     */
    handleOutputScroll() {
      const atBottom = this.isOutputScrolledToBottom(this.$refs.outputContent);
      this.isOutputAtBottom = atBottom;
      this.outputAutoScroll = atBottom;
    },

    /**
     * 滚动输出区到底部。
     * 仅在仍处于自动跟随状态时生效，避免打断用户上翻查看历史日志。
     * @param {boolean} force 忽略自动跟随状态强制滚到底部
     */
    scrollOutputToBottom(force = false) {
      this.$nextTick(() => {
        const el = this.$refs.outputContent;
        if (!el || (!force && !this.outputAutoScroll)) {
          return;
        }
        el.scrollTop = el.scrollHeight;
        this.isOutputAtBottom = true;
      });
    },

    /** 回到最新输出并恢复自动跟随 */
    backToOutputBottom() {
      this.outputAutoScroll = true;
      this.scrollOutputToBottom(true);
    },

    /**
     * 拖拽顶部横条调整输出栏高度。
     * 向上拖变高、向下拖变矮；限制在 [80, editor 区域高度 - 120] 区间内。
     */
    startResizeOutput(e) {
      if (e && e.detail > 1) {
        return; // 双击交给 dblclick 处理（恢复默认高度），不进入拖拽
      }
      const startY = e && typeof e.clientY === 'number' ? e.clientY : 0;
      const startHeight = this.outputPanelHeight;
      const areaEl = this.$el.querySelector('.editor-area');
      const areaHeight = areaEl ? areaEl.clientHeight : 0;
      const maxHeight = areaHeight > 0 ? Math.max(160, areaHeight - 120) : 900;
      this.isResizingOutput = true;
      let rafId = null;

      const relayout = () => {
        if (rafId !== null) {
          return;
        }
        rafId = window.requestAnimationFrame(() => {
          rafId = null;
          this.handleResize();
        });
      };

      const onMove = (ev) => {
        const delta = startY - ev.clientY; // 向上拖 → 输出栏变高
        const next = Math.min(Math.max(startHeight + delta, 80), maxHeight);
        this.outputPanelHeight = Math.round(next);
        relayout();
      };

      const onUp = () => {
        this.isResizingOutput = false;
        if (rafId !== null) {
          window.cancelAnimationFrame(rafId);
          rafId = null;
        }
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        this.handleResize();
        this.scrollOutputToBottom();
      };

      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'ns-resize';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    /** 双击拖拽条：恢复默认高度 */
    resetOutputPanelHeight() {
      this.outputPanelHeight = 200;
      this.$nextTick(() => {
        this.handleResize();
        this.scrollOutputToBottom();
      });
    },

    stopPollTask() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
      if (this.consolePollTimer) {
        clearInterval(this.consolePollTimer);
        this.consolePollTimer = null;
      }
      this.activePollTaskId = null;
      this.isPollingTask = false;
    },

    startPollTask(taskId, pyId) {
      this.stopPollTask();
      this.activePollTaskId = taskId;
      this.currentTaskId = taskId;
      this.viewedTaskId = taskId;
      this.isPollingTask = true;
      // 新任务开始：恢复自动跟随最新输出
      this.outputAutoScroll = true;
      this.isOutputAtBottom = true;

      const pollOutput = async () => {
        if (this.activePollTaskId !== taskId) {
          return;
        }
        try {
          const response = await axios.get('/api/web/basedata/getPyTaskOutput', {
            params: { taskId }
          });
          if (!this.isApiSuccess(response) || !response.data.data) {
            return;
          }
          const task = response.data.data;
          if (this.activePollTaskId !== taskId) {
            return; // 已被终止/结束：忽略在途响应，避免把已清除的运行标记加回来
          }
          this.runningTasks = {
            ...this.runningTasks,
            [pyId]: { taskId: task.taskId, status: Number(task.status) }
          };
          // 仅在用户正在看这个任务的日志时才刷新输出，避免覆盖正在查看的历史记录
          if (this.viewedTaskId === taskId && task.output != null && task.output !== '') {
            this.output = task.output;
            this.scrollOutputToBottom();
          }
        } catch (error) {
          console.error('轮询控制台输出失败:', error);
        }
      };

      const pollResult = async () => {
        if (this.activePollTaskId !== taskId) {
          return;
        }
        try {
          const response = await axios.get('/api/web/basedata/getPyTaskResult', {
            params: { taskId }
          });
          if (!this.isApiSuccess(response) || !response.data.data) {
            return;
          }
          const task = response.data.data;
          if (this.activePollTaskId !== taskId && Number(task.status) === 0) {
            return; // 已被终止/结束：忽略在途的「执行中」响应
          }
          this.runningTasks = {
            ...this.runningTasks,
            [pyId]: { taskId: task.taskId, status: Number(task.status) }
          };
          // 仅在用户正在看这个任务的日志时才刷新输出，避免覆盖正在查看的历史记录
          if (this.viewedTaskId === taskId && task.output != null && task.output !== '') {
            this.output = task.output;
            this.scrollOutputToBottom();
          }
          if (Number(task.status) !== 0) {
            this.finishPollTask(task, pyId);
          }
        } catch (error) {
          console.error('轮询任务结果失败:', error);
        }
      };

      pollOutput();
      pollResult();
      this.consolePollTimer = setInterval(pollOutput, 300);
      this.pollTimer = setInterval(pollResult, 1500);
    },

    finishPollTask(task, pyId) {
      if (!this.isPollingTask || this.activePollTaskId !== task.taskId) {
        return;
      }
      // 用户可能已经切到其它历史记录：此时只更新列表状态，不改动正在查看的日志
      const isViewingThisTask = this.viewedTaskId === task.taskId;
      this.stopPollTask();
      const next = { ...this.runningTasks };
      delete next[pyId];
      this.runningTasks = next;
      if (Number(task.status) === 1) {
        this.$message.success('执行完成');
        if (isViewingThisTask) {
          this.error = '';
        }
      } else if (Number(task.status) === 2) {
        const msg = task.errorMessage || '执行失败';
        if (isViewingThisTask) {
          this.error = msg;
        }
        this.$message.error(msg);
      } else if (Number(task.status) === 3) {
        if (isViewingThisTask) {
          this.error = '';
        }
        this.$message.warning('运行已终止');
      } else if (Number(task.status) === 4) {
        // 后端服务重启导致任务中断：已落盘的部分日志由下方统一回填，重启后不再增长
        const msg = task.errorMessage || '任务因后端服务重启而中断';
        if (isViewingThisTask) {
          this.error = msg;
        }
        this.$message.warning('任务因后端服务重启而中断（日志可能不完整）');
      }
      if (isViewingThisTask && task.output != null) {
        this.output = task.output;
        this.scrollOutputToBottom();
      }
      if (this.listMode === 'tasks' && this.currentFileId) {
        this.fetchTaskList();
      }
    },

    /**
     * 终止当前文件正在运行的任务（编辑器头部「终止」按钮）。
     */
    async stopPyFile() {
      if (!this.ensureCodeOperate()) return;
      const pyId = this.currentFileId || (this.currentFile && this.currentFile.id);
      const running = pyId ? this.runningTasks[pyId] : null;
      const taskId = (running && running.taskId) || this.activePollTaskId;
      if (!taskId) {
        this.$message.warning('当前没有正在执行的任务');
        return;
      }
      await this.requestStopTask(taskId, pyId);
    },

    /**
     * 终止任务列表里某条「执行中」的记录。
     */
    async stopTaskRecord(task) {
      if (!task || !task.taskId) return;
      const pyId = this.currentFileId || (this.currentFile && this.currentFile.id);
      await this.requestStopTask(task.taskId, pyId);
    },

    /**
     * 调用后端 /stopPyTask：kill Python 进程并把任务状态置为 3-运行终止。
     * 编辑器头部按钮与任务列表共用此方法。
     */
    async requestStopTask(taskId, pyId) {
      if (!this.ensureCodeOperate()) return;
      if (!taskId) {
        this.$message.warning('缺少任务 ID，无法终止');
        return;
      }
      try {
        await this.$confirm(
          '确定要终止当前正在运行的任务吗？终止后任务状态将标记为「运行终止」。',
          '终止运行',
          { confirmButtonText: '确定终止', cancelButtonText: '取消', type: 'warning' }
        );
      } catch (e) {
        return; // 用户取消
      }
      this.isStopping = true;
      this.stoppingTaskId = taskId;
      try {
        const response = await axios.post('/api/web/basedata/stopPyTask', { taskId });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '终止失败');
          return;
        }
        const task = (response.data && response.data.data) || {};
        const status = task.status != null ? Number(task.status) : 3;
        if (this.isPollingTask && this.activePollTaskId === taskId) {
          // 复用结束流程：停轮询、清 runningTasks、刷新任务列表
          this.finishPollTask({ ...task, taskId, status }, pyId);
        } else {
          const next = { ...this.runningTasks };
          if (pyId) delete next[pyId];
          this.runningTasks = next;
          if (this.listMode === 'tasks' && this.currentFileId) {
            this.fetchTaskList();
          }
          if (this.listMode === 'files') {
            // 文件列表态下同步刷新运行标记（拿到库里最新状态）
            this.checkRunningTask(pyId);
          }
        }
        this.$message.warning('运行已终止');
      } catch (error) {
        console.error('终止任务失败:', error);
        this.$message.error('终止失败');
      } finally {
        this.isStopping = false;
        this.stoppingTaskId = null;
      }
    },

    /** 恢复上次的「续训」开关状态（默认关 —— 不带 --resume 更接近「从头复现」的预期） */
    restoreResumePref() {
      try {
        this.resumeEnabled = window.localStorage.getItem(RESUME_STORAGE_KEY) === '1';
      } catch (error) {
        this.resumeEnabled = false;
      }
    },

    async runPyFile() {
      if (!this.ensureCodeOperate()) return;
      if (!this.currentFile) {
        this.$message.warning('请先选择文件');
        return;
      }
      if (this.codeDirty || this.currentFile.ifEdit) {
        this.$message.warning('请先保存后再执行');
        return;
      }
      if (this.isCurrentFileRunning) {
        return;
      }

      this.isRunning = true;
      this.output = '';
      this.error = '';
      this.viewedTaskId = null;

      const withResume = this.resumeEnabled && this.resumeSupported;
      try {
        const response = await axios.post('/api/web/basedata/runPyFile', {
          id: this.currentFile.id,
          // 续训开关：只对支持的脚本传 true（后端对不支持的脚本也会忽略，双保险）
          resume: withResume,
          // P19-1：续训来源任务。非空时后端把该任务的训练断点（含不适曲线）复制到
          // 本次任务目录后继续训练；为空则退回旧的固定断点目录行为。
          resumeFromTaskId: withResume ? (this.resumeFromTaskId || null) : null
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error(response.data.message || '启动执行失败');
          return;
        }
        const task = response.data.data;
        this.runningTasks = {
          ...this.runningTasks,
          [this.currentFile.id]: { taskId: task.taskId, status: 0 }
        };
        this.$message.success(withResume ? '已开始执行（断点续训）' : '已开始执行');
        this.startPollTask(task.taskId, this.currentFile.id);
        await this.enterTaskRecordMode(task.taskId);
      } catch (error) {
        console.error('执行失败:', error);
        this.$message.error('执行失败');
      } finally {
        this.isRunning = false;
      }
    },
    
    handleResize() {
      if (this.editor) {
        this.editor.layout();
      }
      if (this.midEvalChart) {
        this.midEvalChart.resize();
      }
    },

    /* ---------------- 不适比例趋势图（[中期评估] 日志） ---------------- */

    /** 打开图表弹窗：先解析一次，避免弹窗动画期间显示空提示 */
    openMidEvalChart() {
      this.midEvalData = this.parseMidEvalLog(this.output);
      this.chartVisible = true;
    },

    /** 弹窗打开动画结束后再初始化 ECharts（此时容器已有尺寸） */
    handleMidEvalChartOpened() {
      this.$nextTick(() => {
        this.renderMidEvalChart(true);
      });
    },

    /** 弹窗关闭：销毁实例，释放 resize 监听与画布 */
    handleMidEvalChartClosed() {
      if (this.midEvalChart) {
        this.midEvalChart.dispose();
        this.midEvalChart = null;
      }
      this.midEvalChartSignature = '';
    },

    /**
     * 渲染图表。数据未变化时直接返回（日志轮询很频繁，避免无谓的重绘）。
     * @param {boolean} force 忽略数据指纹强制重绘（弹窗刚打开时用）
     */
    renderMidEvalChart(force) {
      const el = this.$refs.midEvalChart;
      if (!el) {
        return;
      }
      const data = this.parseMidEvalLog(this.output);
      this.midEvalData = data;
      const signature = this.midEvalSignature(data);
      if (!force && signature === this.midEvalChartSignature) {
        return;
      }
      this.midEvalChartSignature = signature;
      if (!this.midEvalChart) {
        this.midEvalChart = echarts.init(el);
      }
      if (!data.series.length) {
        this.midEvalChart.clear();
        return;
      }
      this.midEvalChart.setOption(this.buildMidEvalOption(data), true);
      this.$nextTick(() => {
        if (this.midEvalChart) {
          this.midEvalChart.resize();
        }
      });
    },

    /**
     * 解析日志中的中期评估行，格式（由 Multi-agent.py 的 log_console 输出）：
     *   [中期评估] 第 60/260 轮 | 高温/低温 B1: 20.0%/  3.2% B2: ... (KPI 口径, 有人步 n=...)
     *
     * @param {string} text 控制台日志全文
     * @returns {{rounds: number[], series: Array, detail: Array}}
     *   rounds 横轴轮数；series 每栋一条，data 为「高温+低温」合计（%）；
     *   detail 按轮次索引保存各栋 hot/cold，供 tooltip 展示明细。
     */
    parseMidEvalLog(text) {
      const result = { rounds: [], series: [], detail: [] };
      if (!text) {
        return result;
      }
      // 日志可能带 ANSI 颜色码，先剥离再匹配
      const clean = this.formatConsoleOutput(text);
      if (clean.indexOf('[中期评估]') < 0) {
        return result;
      }
      const lineRe = /\[中期评估\]\s*第\s*(\d+)\s*\/\s*\d+\s*轮\s*\|\s*高温\/低温\s*(.*)$/;
      const buildingRe = /B(\d+)\s*:\s*([0-9.]+%|na)\s*\/\s*([0-9.]+%|na)/g;
      const indexOfRound = {};
      const perBuilding = {};
      clean.split(/\r?\n/).forEach((line) => {
        if (line.indexOf('[中期评估]') < 0) {
          return;
        }
        const matched = line.match(lineRe);
        if (!matched) {
          return;
        }
        const round = Number(matched[1]);
        const body = matched[2] || '';
        const roundValues = {};
        let buildingMatch;
        buildingRe.lastIndex = 0;
        while ((buildingMatch = buildingRe.exec(body)) !== null) {
          const hot = this.parsePercent(buildingMatch[2]);
          const cold = this.parsePercent(buildingMatch[3]);
          roundValues['B' + Number(buildingMatch[1])] = {
            hot,
            cold,
            sum: hot == null || cold == null ? null : hot + cold
          };
        }
        if (!Object.keys(roundValues).length) {
          return;
        }
        let idx = indexOfRound[round];
        if (idx == null) {
          idx = result.rounds.length;
          indexOfRound[round] = idx;
          result.rounds.push(round);
          result.detail.push({});
        }
        Object.keys(roundValues).forEach((name) => {
          const item = roundValues[name];
          result.detail[idx][name] = item;
          if (!perBuilding[name]) {
            perBuilding[name] = [];
          }
          const arr = perBuilding[name];
          while (arr.length < result.rounds.length) {
            arr.push(null);
          }
          arr[idx] = item.sum == null ? null : Number(item.sum.toFixed(2));
        });
      });
      Object.keys(perBuilding)
        .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))
        .forEach((name) => {
          const arr = perBuilding[name];
          while (arr.length < result.rounds.length) {
            arr.push(null);
          }
          result.series.push({ name, data: arr });
        });
      return result;
    },

    /** '20.0%' → 20；'na' / 空 → null */
    parsePercent(token) {
      if (token == null) {
        return null;
      }
      const text = String(token).trim();
      if (!text || text.toLowerCase() === 'na') {
        return null;
      }
      const value = parseFloat(text);
      return Number.isFinite(value) ? value : null;
    },

    /** 数据指纹：轮数与各栋曲线一致即视为无变化 */
    midEvalSignature(data) {
      if (!data || !data.series.length) {
        return '';
      }
      return (
        data.rounds.join(',') +
        '|' +
        data.series.map((s) => s.name + ':' + s.data.join(',')).join(';')
      );
    },

    /** 构造 ECharts 配置：横轴轮数、纵轴不适比例、每栋一条曲线 */
    buildMidEvalOption(data) {
      const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#9b59b6', '#00bcd4', '#ff9800', '#795548'];
      const fmt = (v) => (v == null || !Number.isFinite(v) ? 'na' : Number(v).toFixed(1) + '%');
      return {
        tooltip: {
          trigger: 'axis',
          formatter: (params) => {
            if (!params || !params.length) {
              return '';
            }
            const idx = params[0].dataIndex;
            const lines = ['第 ' + data.rounds[idx] + ' 轮'];
            params.forEach((p) => {
              const detail = (data.detail[idx] || {})[p.seriesName] || {};
              lines.push(
                p.marker +
                  p.seriesName +
                  ' 合计 <b>' +
                  fmt(p.value) +
                  '</b>（高温 ' +
                  fmt(detail.hot) +
                  ' + 低温 ' +
                  fmt(detail.cold) +
                  '）'
              );
            });
            return lines.join('<br/>');
          }
        },
        legend: { top: 0 },
        grid: { left: 64, right: 32, top: 46, bottom: 52 },
        xAxis: {
          type: 'category',
          name: '轮数',
          boundaryGap: false,
          data: data.rounds
        },
        yAxis: {
          type: 'value',
          name: '不适比例(%)',
          axisLabel: { formatter: '{value}%' }
        },
        series: data.series.map((s, i) => ({
          name: s.name,
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          connectNulls: true,
          lineStyle: { width: 2, color: colors[i % colors.length] },
          itemStyle: { color: colors[i % colors.length] },
          data: s.data
        }))
      };
    },

    /* ---------------- 断点续训：来源任务选择（P19-1） ---------------- */

    /** 续训开关点击：统一打开选择弹窗（已开启时用于更换来源；关闭请用弹窗里的「关闭续训」） */
    onResumeSwitchClick() {
      if (this.isCodeEditLocked) {
        return;
      }
      this.openResumeDialog();
    },

    /** 打开弹窗并拉取可续训任务列表 */
    async openResumeDialog() {
      this.resumeDialogVisible = true;
      await this.fetchResumableTasks();
    },

    /** 关闭续训：清空来源并关弹窗 */
    disableResume() {
      this.resumeEnabled = false;
      this.resumeFromTaskId = null;
      this.resumeDialogVisible = false;
      this.$message.info('已关闭断点续训（下次执行将从头训练）');
    },

    /** 拉取「有训练断点」的任务列表（后端扫描 outkpis 下各任务的 checkpoints 目录） */
    async fetchResumableTasks() {
      this.resumeTaskLoading = true;
      try {
        const response = await axios.get('/api/web/basedata/getResumableTaskList');
        if (!this.isApiSuccess(response)) {
          this.$message.error((response.data && response.data.message) || '获取可续训任务失败');
          this.resumeTaskList = [];
          this.selectedResumeTaskId = null;
          return;
        }
        this.resumeTaskList = response.data.data || [];
        // 优先保持已选任务，否则默认选第一条
        const keep = this.resumeTaskList.find((it) => it.taskId === this.resumeFromTaskId);
        const first = keep || this.resumeTaskList[0];
        this.selectedResumeTaskId = first ? first.taskId : null;
        this.$nextTick(() => {
          if (first && this.$refs.resumeTable) {
            this.$refs.resumeTable.setCurrentRow(first);
          }
        });
        if (first) {
          await this.loadResumeTaskDetail(first.taskId);
        } else {
          this.resumeTaskDetail = null;
          this.resumePreviewData = null;
        }
      } catch (error) {
        console.error('获取可续训任务失败:', error);
        this.$message.error('获取可续训任务失败');
        this.resumeTaskList = [];
      } finally {
        this.resumeTaskLoading = false;
      }
    },

    /** 表格当前行变化 → 载入该任务的断点详情与曲线 */
    async handleResumeTaskSelect(row) {
      if (!row || !row.taskId) {
        return;
      }
      this.selectedResumeTaskId = row.taskId;
      await this.loadResumeTaskDetail(row.taskId);
    },

    /** 读取单个任务的断点详情（含 midEvalHistory 不适曲线） */
    async loadResumeTaskDetail(taskId) {
      this.resumeTaskDetailLoading = true;
      try {
        const response = await axios.get('/api/web/basedata/getTaskTrainProgress', {
          params: { taskId }
        });
        if (!this.isApiSuccess(response)) {
          this.$message.error((response.data && response.data.message) || '读取断点失败');
          this.resumeTaskDetail = null;
          this.resumePreviewData = null;
          return;
        }
        this.resumeTaskDetail = response.data.data || null;
        this.resumePreviewData = this.buildCurveFromHistory(
          (this.resumeTaskDetail && this.resumeTaskDetail.midEvalHistory) || []
        );
        this.renderResumePreview(true);
      } catch (error) {
        console.error('读取断点失败:', error);
        this.$message.error('读取断点失败');
        this.resumeTaskDetail = null;
        this.resumePreviewData = null;
      } finally {
        this.resumeTaskDetailLoading = false;
      }
    },

    /** 弹窗打开动画结束后初始化预览图（此时容器才有尺寸） */
    handleResumeDialogOpened() {
      this.$nextTick(() => {
        this.renderResumePreview(true);
      });
    },

    /** 弹窗关闭：销毁预览图实例，释放画布 */
    handleResumeDialogClosed() {
      if (this.resumePreviewChart) {
        this.resumePreviewChart.dispose();
        this.resumePreviewChart = null;
      }
      this.resumePreviewSignature = '';
    },

    /** 渲染续训预览曲线（复用不适曲线的 ECharts 配置） */
    renderResumePreview(force) {
      const el = this.$refs.resumePreviewChart;
      const data = this.resumePreviewData;
      if (!el) {
        return;
      }
      if (!data || !data.series.length) {
        if (this.resumePreviewChart) {
          this.resumePreviewChart.clear();
        }
        this.resumePreviewSignature = '';
        return;
      }
      const signature = this.midEvalSignature(data);
      if (!force && signature === this.resumePreviewSignature) {
        return;
      }
      this.resumePreviewSignature = signature;
      if (!this.resumePreviewChart) {
        this.resumePreviewChart = echarts.init(el);
      }
      this.resumePreviewChart.setOption(this.buildMidEvalOption(data), true);
      this.$nextTick(() => {
        if (this.resumePreviewChart) {
          this.resumePreviewChart.resize();
        }
      });
    },

    /** 确认：开启续训并记录来源任务 */
    confirmResumeTask() {
      if (!this.selectedResumeTaskId) {
        this.$message.warning('请先选择一个来源任务');
        return;
      }
      this.resumeEnabled = true;
      this.resumeFromTaskId = this.selectedResumeTaskId;
      this.resumeDialogVisible = false;
      this.$message.success(
        '已开启断点续训：将从 ' + this.shortTaskId(this.resumeFromTaskId) + ' 的断点继续训练'
      );
    },

    /**
     * 把后端断点里的 midEvalHistory 转成曲线配置所需结构。
     * 后端格式（Multi-agent.py 落盘）：[{ round, hot:[0~1...], cold:[0~1...] }, ...]
     * 目标格式（与 parseMidEvalLog 一致）：{ rounds:[], series:[{name,data}], detail:[{}] }
     * 注意比例 → 百分比的 ×100 换算。
     */
    buildCurveFromHistory(history) {
      const result = { rounds: [], series: [], detail: [] };
      if (!Array.isArray(history) || !history.length) {
        return result;
      }
      const perBuilding = {};
      const toPct = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? Number((n * 100).toFixed(2)) : null;
      };
      history.forEach((rec) => {
        const round = Number(rec && rec.round);
        if (!Number.isFinite(round)) {
          return;
        }
        const hot = Array.isArray(rec.hot) ? rec.hot : [];
        const cold = Array.isArray(rec.cold) ? rec.cold : [];
        const idx = result.rounds.length;
        result.rounds.push(round);
        result.detail.push({});
        const n = Math.max(hot.length, cold.length);
        for (let k = 0; k < n; k += 1) {
          const name = 'B' + (k + 1);
          const h = toPct(hot[k]);
          const c = toPct(cold[k]);
          const sum = h == null || c == null ? null : Number((h + c).toFixed(2));
          result.detail[idx][name] = { hot: h, cold: c, sum };
          if (!perBuilding[name]) {
            perBuilding[name] = [];
          }
          const arr = perBuilding[name];
          while (arr.length < result.rounds.length) {
            arr.push(null);
          }
          arr[idx] = sum;
        }
      });
      Object.keys(perBuilding)
        .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))
        .forEach((name) => {
          result.series.push({ name, data: perBuilding[name] });
        });
      return result;
    },

    /** 任务 ID 过长，列表里只显示前后各 6 位 */
    shortTaskId(taskId) {
      const id = taskId == null ? '' : String(taskId);
      if (id.length <= 16) {
        return id;
      }
      return id.slice(0, 6) + '…' + id.slice(-6);
    },

    /** 「最差和」显示：null/NaN → na，否则保留 3 位 */
    formatScore(value) {
      const n = Number(value);
      return Number.isFinite(n) ? n.toFixed(3) : 'na';
    },
    
    startEditing(file) {
      if (!this.ensureCodeOperate()) return;
      this.editingFileId = file.id;
      this.editingFileName = file.fileName;
      this.editingFileOriginalName = file.fileName;
      this.$nextTick(() => {
        this.$refs.renameInput?.focus();
      });
    },
    
    async confirmRename() {
      if (!this.ensureCodeOperate()) return;
      if (!this.editingFileName.trim()) {
        this.$message.error('文件名不能为空');
        return;
      }
       console.log(this.editingFileName)
      if (this.editingFileName==this.editingFileOriginalName) {
        return;
      }
     
      try {
        const response = await axios.post('/api/web/basedata/savePyFile', {
          id: this.editingFileId,
          fileName: this.editingFileName
        });
        console.log(response)
        if (response.data.code==0) {
          const file = this.files.find(f => f.id === this.editingFileId);
          if (file) {
            file.fileName = this.editingFileName;
            this.$message.success('重命名成功');
          }
        } else {
          //NOCONTROL.py
          this.$message.error(response.data.message || '重命名失败');
        }
      } catch (error) {
        console.error('重命名失败:', error);
        this.$message.error('重命名失败');
      } finally {
        this.cancelEditing();
      }
    },
    
    cancelEditing() {
      this.editingFileId = null;
      this.editingFileName = '';
      this.editingFileOriginalName = '';
    }
  }
};
</script>

<style scoped>
.python-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.editor-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.file-list {
  width: 20%;
  background: #252526;
  border-right: 1px solid #1a1a1a;
  padding: 10px;
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}

.file-list-content {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 150px; /* 为简介区域预留空间 */
}

.file-description {
  position: absolute;
  bottom: 30px;  /* 增加底部间距 */
  left: 10px;
  right: 10px;
  background: #252526;
  
  border-top: 1px solid #3e3e42;
  
}

.file-description textarea {
  width: 100%;
  min-height: 100px;
  resize: none; /* 禁用缩放功能 */
}

.file-list h4 {
  color: #cccccc;
  margin: 0 0 10px 0;
  padding: 0 0 5px 0;
  border-bottom: 1px solid #3e3e42;
}

/* ---- 脚本类型筛选（全部 / 训练 / 评估 / 训练+评估）---- */
.script-type-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0 0 8px 0;
}

.script-type-btn {
  flex: 1 1 auto;
  background: transparent;
  color: #999;
  border: 1px solid #3e3e42;
  border-radius: 3px;
  padding: 3px 6px;
  font-size: 12px;
  line-height: 16px;
  cursor: pointer;
  white-space: nowrap;
}

.script-type-btn:hover {
  color: #d4d4d4;
  border-color: #5a5a5a;
}

.script-type-btn.active {
  background: #0e639c;
  border-color: #0e639c;
  color: #ffffff;
}

/* 文件名右侧的类型短标签 */
.script-type-tag {
  flex: 0 0 auto;
  margin-left: 5px;
  padding: 0 4px;
  border-radius: 3px;
  font-size: 11px;
  font-style: normal;
  line-height: 16px;
  white-space: nowrap;
  color: #cfcfcf;
  background: #3a3d41;
}

.script-type-tag.tag-train {
  background: #2f5d3a;
  color: #b7e4c7;
}

.script-type-tag.tag-eval {
  background: #3a4a63;
  color: #b6d4fe;
}

/*
 * 未读红点：文件列表里该脚本下「执行完成但未查看」的记录数（红底白字圆角矩形）。
 *
 * 选择器必须写成 `.file-item span.unread-badge`，不能只写 `.unread-badge`：
 * 上面有一条 `.file-item span { cursor: pointer; flex-grow: 1 }`，权重是 (0,1,1)，
 * 而单个类选择器只有 (0,1,0)，会被它压过去 —— 结果是红点被 flex-grow 撑成一条
 * 横贯整行的长条，而不是紧凑的圆角矩形。这里用 (0,2,1) 明确压过它。
 */
.file-item span.unread-badge {
  flex: 0 0 auto;
  margin-left: 5px;
  padding: 0 6px;
  border-radius: 9px;
  font-size: 11px;
  line-height: 16px;
  font-weight: 500;
  color: #ffffff;
  background: #f5222d;
  white-space: nowrap;
  cursor: default;
}

/* 任务列表里的「未读」标记 */
.unread-mark {
  flex: 0 0 auto;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 16px;
  color: #ffffff;
  background: #f5222d;
  white-space: nowrap;
}

.file-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.file-list li {
  padding: 8px 10px;
  color: #d4d4d4;
  border-radius: 3px;
  margin-bottom: 2px;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.file-item span {
  cursor: pointer;
  flex-grow: 1;
}

.rename-btn {
  background: transparent;
  color: #999;
  border: none;
  cursor: pointer;
  padding: 2px 5px;
  margin-left: 5px;
  font-size: 12px;
}

.rename-btn:hover {
  color: #ccc;
  background: rgba(255,255,255,0.1);
}



.edit-mode {
  display: flex;
  align-items: center;
  gap: 5px;
}

.edit-mode input {
  flex-grow: 1;
  background: #333;
  border: 1px solid #555;
  color: #fff;
  padding: 3px 5px;
  border-radius: 3px;
}

.confirm-btn, .cancel-btn {
  background: transparent;
  border: none;
  color: #ccc;
  cursor: pointer;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
}

.confirm-btn:hover {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.cancel-btn:hover {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.file-list li:hover {
  background: #2a2d2e;
}

.file-list li.active {
  background: #37373d;
}

.loading {
  color: #999;
  text-align: center;
  padding: 10px;
}

.editor-area {
  width: 80%;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #2d2d30;
  color: #cccccc;
  border-bottom: 1px solid #3e3e42;
}

.editor-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.controls {
  display: flex;
  gap: 8px;
}

.controls button {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.controls button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-save {
  background: #0e639c;
  color: white;
}

.btn-save:hover:not(:disabled) {
  background: #1177bb;
}

.btn-show {
  background: #5a5a5a;
  color: #ccc;
}

.btn-show:hover:not(:disabled) {
  background: #6e6e6e;
  color: #fff;
}

.btn-show-active {
  background: #e6a23c;
  color: #fff;
}

.btn-show-active:hover:not(:disabled) {
  background: #ebb563;
}

.btn-record {
  background: #6b5b95;
  color: white;
}

.btn-record:hover:not(:disabled) {
  background: #7d6ba8;
}

/* 算法配置按钮：与「记录」同为元数据类操作，用蓝灰区分于运行/保存 */
.btn-config {
  background: #3f6f8f;
  color: white;
}

.btn-config:hover:not(:disabled) {
  background: #4d82a6;
}

.btn-back {
  background: #5a5a5a;
  color: white;
}

.btn-back:hover {
  background: #6e6e6e;
}

/* 断点续训开关：紧挨「执行」左侧，开启时高亮，提醒本次执行会追加 --resume */
.resume-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 4px;
  background: #3a3a3d;
  color: #cccccc;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s, color 0.2s;
}

.resume-switch:hover {
  background: #4a4a4d;
}

.resume-switch.is-on {
  background: #b8860b;
  color: #fff;
}

.resume-switch.is-on:hover {
  background: #cf9612;
}

.resume-switch.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.resume-switch input {
  margin: 0;
  cursor: inherit;
}

.btn-run {
  background: #55aa55;
  color: white;
}

.btn-run:hover:not(:disabled) {
  background: #66bb66;
}

.btn-stop {
  background: #c1444a;
  color: white;
}

.btn-stop:hover:not(:disabled) {
  background: #d4545a;
}

/* 「子任务」标识：编排任务（训练+评估）拆出的记录，与「未读」并列展示 */
.subtask-mark {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 16px;
  color: #ffffff;
  background: #409eff;
  white-space: nowrap;
}

.task-item {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  cursor: pointer;
}

.task-title {
  flex: 1 1 100%;
  font-size: 13px;
  color: #d4d4d4;
}

.task-show-name {
  flex: 1 1 100%;
  font-size: 12px;
  color: #79b8ff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-status {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 3px;
}

.btn-task-name {
  border: 1px solid #888;
  background: #3a3a3a;
  color: #bbb;
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
}

.btn-task-name:hover:not(:disabled) {
  border-color: #79b8ff;
  color: #79b8ff;
}

/* 任务列表里「终止」运行中任务 */
.btn-task-stop {
  border: 1px solid #a33;
  background: #3a2222;
  color: #e88;
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
  margin-left: 4px;
}

.btn-task-stop:hover:not(:disabled) {
  border-color: #e55;
  color: #f88;
}

.btn-task-stop:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-task-name:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-task-show {
  border: 1px solid #888;
  background: #3a3a3a;
  color: #bbb;
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
}

.btn-task-show:hover:not(:disabled) {
  border-color: #409eff;
  color: #409eff;
}

.btn-task-show-active {
  background: rgba(64, 158, 255, 0.15);
  border-color: #409eff;
  color: #409eff;
}

.btn-task-show:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-task-delete {
  border: 1px solid #888;
  background: #3a3a3a;
  color: #bbb;
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
}

.btn-task-delete:hover:not(:disabled) {
  border-color: #f44336;
  color: #f44336;
}

.btn-task-delete:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.task-status-0 {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.task-status-1 {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.task-status-2 {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

/* 3-运行终止 */
.task-status-3 {
  background: rgba(158, 158, 158, 0.25);
  color: #bdbdbd;
}

/* 4-已中断（后端服务重启导致） */
.task-status-4 {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
}

/* 6-等待中：编排任务的评估子任务在等训练跑完（这个状态下不允许删除） */
.task-status-6 {
  background: rgba(230, 162, 60, 0.2);
  color: #e6a23c;
}

.editor-container {
  flex: 1 1 auto;
  min-height: 0;
}

.output-panel {
  position: relative;
  flex: 0 0 auto;
  border-top: 1px solid #3e3e42;
  background: #1e1e1e;
  /* 兜底：窗口很矮时也不允许输出栏吞掉整个编辑区 */
  max-height: 85%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 输出栏顶部拖拽条：调整高度 */
.output-resizer {
  flex: 0 0 auto;
  height: 6px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  cursor: ns-resize;
}

.output-resizer:hover,
.output-resizer.active {
  background: #0e639c;
}

.output-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #2d2d30;
  color: #cccccc;
  font-weight: 500;
}

.btn-clear {
  background: transparent;
  color: #cccccc;
  border: 1px solid #5a5a5a;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
}

.btn-clear:hover {
  background: #3c3c3c;
}

/* 「输出」标题 + 不适曲线按钮（按钮紧跟在「输出」右侧） */
.output-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.btn-chart {
  background: transparent;
  color: #75bfff;
  border: 1px solid #0e639c;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
}

.btn-chart:hover {
  background: #0e639c;
  color: #ffffff;
}

.btn-chart-active {
  background: #0e639c;
  color: #ffffff;
}

/* 不适比例趋势图弹窗 */
.chart-hint {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.7;
  color: #909399;
}

.mid-eval-chart-wrap {
  position: relative;
  height: 420px;
}

.mid-eval-chart {
  width: 100%;
  height: 100%;
}

.mid-eval-empty {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  background: #ffffff;
  color: #909399;
  font-size: 13px;
  line-height: 2;
}

.mid-eval-empty span {
  font-size: 12px;
  color: #c0c4cc;
}

/* ---- 续训来源任务选择（P19-1） ---- */
.resume-dialog-tip {
  margin: 0 0 12px;
  font-size: 12.5px;
  color: #606266;
  line-height: 1.7;
}

.resume-dialog-tip strong {
  color: #e6a23c;
}

.resume-dialog-body {
  display: flex;
  gap: 14px;
  min-height: 420px;
}

.resume-task-list {
  position: relative;
  flex: 1 1 58%;
  min-width: 0;
}

.resume-task-empty {
  position: absolute;
  top: 40%;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 13px;
  color: #909399;
  line-height: 2;
}

.resume-task-empty span {
  display: block;
  font-size: 12px;
  color: #c0c4cc;
}

.resume-task-preview {
  flex: 1 1 42%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.resume-preview-title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.resume-preview-title span {
  font-weight: 400;
  color: #909399;
}

.resume-preview-chart-wrap {
  position: relative;
  flex: 1 1 auto;
  min-height: 340px;
}

.resume-preview-chart {
  width: 100%;
  height: 100%;
  min-height: 340px;
}

.resume-preview-empty {
  position: absolute;
  top: 45%;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 12.5px;
  color: #c0c4cc;
}

.resume-preview-meta {
  margin-top: 8px;
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #909399;
}

.output-content {
  flex: 1;
  min-height: 0;
  padding: 12px 16px;
  margin: 0;
  overflow: auto;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
}

/* 用户上翻查看历史日志时显示的「回到底部」浮层按钮 */
.btn-scroll-bottom {
  position: absolute;
  right: 16px;
  bottom: 12px;
  padding: 4px 10px;
  border: none;
  border-radius: 12px;
  background: rgba(14, 99, 156, 0.92);
  color: #ffffff;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

.btn-scroll-bottom:hover {
  background: #1177bb;
}

.error-message {
  padding: 12px 16px;
  background: #c75050;
  color: white;
  font-size: 14px;
}
</style>