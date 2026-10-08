<template>
  <div class="ha-page task-list-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">任务管理</h1>
        <p class="ha-muted">共 {{ mainTasks.length }} 条</p>
      </div>
      <div class="ha-toolbar toolbar">
        <el-button type="primary" icon="el-icon-plus" @click="openCreateTask()">
          新建任务
        </el-button>
        <el-button icon="el-icon-refresh" :loading="loading" @click="loadTasks()">
          刷新
        </el-button>
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <el-table
        ref="taskTable"
        :data="pagedTasks"
        v-loading="loading"
        stripe
        style="width: 100%"
        row-key="taskId"
        :row-class-name="rowClassName"
        @expand-change="handleExpandChange"
      >
        <!--
          详情展开位：编排任务点「详情」后在当前行下方展示训练 / 评估两个子任务。
          本页没有编排任务时整列不渲染；有编排任务时，简易任务那一行的箭头用
          row-class + CSS 藏掉（简易任务没有子任务，不该出现展开入口）。
        -->
        <el-table-column v-if="hasPipelineOnPage" type="expand" width="42">

          <template slot-scope="{ row }">
            <div class="subtask-wrap">
              <div v-if="subTaskLoading[row.taskId]" class="subtask-tip">加载子任务…</div>
              <template v-else>
                <el-table :data="subTasksOf(row)" size="mini" border style="width: 100%">
                  <el-table-column label="子任务" width="120">
                    <template slot-scope="scope">{{ subTaskRoleLabel(scope.row) }}</template>
                  </el-table-column>
                  <el-table-column label="脚本" min-width="200" show-overflow-tooltip>
                    <template slot-scope="scope">{{ scope.row.scriptName || '（脚本已删除）' }}</template>
                  </el-table-column>
                  <el-table-column label="状态" width="120" align="center">
                    <template slot-scope="scope">
                      <span class="task-status" :class="'st-' + normalizeStatus(scope.row.status)">
                        {{ scope.row.statusDesc || '未知' }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="100" align="center">
                    <template slot-scope="scope">
                      <el-button
                        type="text"
                        size="small"
                        :disabled="!canOpenSubTaskDetail(scope.row)"
                        :title="canOpenSubTaskDetail(scope.row)
                          ? '跳转到代码编辑器查看该子任务的记录'
                          : '所属脚本已不存在，无法跳转'"
                        @click="openSubTaskDetail(scope.row)"
                      >
                        详情
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="!subTasksOf(row).length" class="subtask-tip">
                  该任务还没有子任务（重新保存一次任务即可生成）
                </div>
              </template>
            </div>
          </template>
        </el-table-column>

        <el-table-column type="index" label="#" width="60" :index="rowIndex" />

        <el-table-column label="类型" width="120" align="center">
          <template slot-scope="{ row }">
            <span class="task-type-tag" :class="isPipelineTask(row) ? 'tt-pipeline' : 'tt-simple'">
              {{ isPipelineTask(row) ? '训练 + 评估' : '简易任务' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="任务名称" min-width="240" show-overflow-tooltip>
          <template slot-scope="{ row }">{{ taskNameOf(row) }}</template>
        </el-table-column>

        <el-table-column label="运行开始时间" width="210">
          <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
        </el-table-column>

        <el-table-column label="运行状态" width="170">
          <template slot-scope="{ row }">
            <span class="task-status" :class="'st-' + normalizeStatus(row.status)">
              {{ row.statusDesc || '未知' }}
            </span>
            <span
              v-if="isUnread(row)"
              class="unread-mark"
              title="执行完成但尚未查看，点击「详情」查看后即标记为已读"
            >未读</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="240" align="center">
          <template slot-scope="{ row }">
            <!-- 执行：只有「待执行」的编排任务可执行；执行后编辑/删除自动消失（它们同样要求 status=5） -->
            <el-button
              v-if="canExecutePipelineTask(row)"
              type="text"
              size="small"
              class="primary-text-btn"
              title="开始执行：先跑训练子任务，训练完成后自动接力评估子任务"
              @click="executeTask(row)"
            >
              执行
            </el-button>
            <el-button
              v-if="canEditPipelineTask(row)"
              type="text"
              size="small"
              title="编辑任务名称与两张卡片的配置"
              @click="openEditTask(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="canEditPipelineTask(row)"
              type="text"
              size="small"
              class="danger-text-btn"
              title="删除该任务"
              @click="deleteTask(row)"
            >
              删除
            </el-button>
            <el-button
              type="text"
              size="small"
              :disabled="!canOpenDetail(row)"
              :title="detailTitle(row)"
              @click="openDetail(row)"
            >
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && !mainTasks.length" class="empty-tip ha-muted">暂无任务</div>

      <el-pagination
        v-if="mainTasks.length > pageSize"
        class="pager"
        background
        layout="total, prev, pager, next"
        :total="mainTasks.length"
        :page-size="pageSize"
        :current-page.sync="currentPage"
      />
    </el-card>

    <!-- 新建 / 编辑任务：固定两张卡片（训练卡 → 评估卡）；taskId 非空即编辑模式 -->
    <pipeline-task-dialog
      :visible.sync="newTaskVisible"
      :task-id="editingTaskId"
      @saved="onTaskSaved"
    />
  </div>
</template>

<script>
import axios from 'axios'
import PipelineTaskDialog from '../components/PipelineTaskDialog.vue'

export default {
  name: 'TaskList',
  components: {
    PipelineTaskDialog
  },
  data() {
    return {
      tasks: [],
      loading: false,
      /** 「新建/编辑任务」弹窗可见性 */
      newTaskVisible: false,
      /** 弹窗编辑的任务 ID：空串 = 新建模式 */
      editingTaskId: '',
      /** 前端分页：记录会随使用不断增长，一次全渲染没必要 */
      currentPage: 1,
      pageSize: 20,
      /** 运行中任务的静默刷新定时器 */
      refreshTimer: null,
      /** 编排任务详情展开：父任务 id → 子任务列表（getSubTaskList） */
      subTasks: {},
      /** 子任务加载中标记：父任务 id → true */
      subTaskLoading: {}
    }
  },
  computed: {
    /**
     * 主列表数据：过滤掉编排任务拆出的子任务。
     * 子任务不是用户直接管理的对象，只在父任务「详情」展开的子表格里展示
     * （代码编辑器「记录」列表里仍会带「子任务」标识展示它们）。
     */
    mainTasks() {
      return this.tasks.filter((t) => !t.isSubtask)
    },
    pagedTasks() {
      const start = (this.currentPage - 1) * this.pageSize
      return this.mainTasks.slice(start, start + this.pageSize)
    },
    /** 是否有任务（或子任务）还在执行：决定要不要继续轮询 */
    hasRunning() {
      return this.tasks.some((t) => Number(t.status) === 0)
    },
    /**
     * 本页是否有「训练+评估」编排任务：只有编排任务才有子任务可展开，
     * 所以整页都是简易任务时连展开列都不渲染（避免多出一条空白列）。
     */
    hasPipelineOnPage() {
      return this.pagedTasks.some((t) => this.isPipelineTask(t))
    }
  },
  mounted() {
    this.loadTasks()
    // 有任务在跑时每 5 秒静默刷新一次，让状态实时更新；全部结束即停止请求。
    // 静默刷新不显示 loading、也不重置页码，避免打断正在翻页的用户。
    this.refreshTimer = setInterval(() => {
      if (this.hasRunning) {
        this.loadTasks({ silent: true, keepPage: true })
      }
    }, 5000)
  },
  beforeDestroy() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer)
      this.refreshTimer = null
    }
  },
  methods: {
    /**
     * 加载全部任务列表。
     * @param {object} [options] silent=true 不显示 loading / 不弹错误提示；keepPage=true 不重置页码
     */
    async loadTasks(options) {
      const opts = options || {}
      if (!opts.silent) {
        this.loading = true
      }
      try {
        const response = await axios.get('/api/web/basedata/getAllPyTaskList')
        if (response.data && response.data.code === 0) {
          const list = response.data.data || []
          // 后端已按 create_time 倒序；这里再兜一层，避免同一秒创建的多条记录顺序不稳定
          list.sort((a, b) => this.timeValue(b.createTime) - this.timeValue(a.createTime))
          this.tasks = list
          if (!opts.keepPage) {
            this.currentPage = 1
          }
          // 记录被删除后当前页可能越界，收敛到最后一页
          const maxPage = Math.max(1, Math.ceil(list.length / this.pageSize))
          if (this.currentPage > maxPage) {
            this.currentPage = maxPage
          }
        } else if (!opts.silent) {
          this.$message.error((response.data && response.data.message) || '加载任务列表失败')
        }
      } catch (error) {
        console.error('加载任务列表失败:', error)
        if (!opts.silent) {
          this.$message.error('加载任务列表失败')
        }
      } finally {
        if (!opts.silent) {
          this.loading = false
        }
      }
    },

    timeValue(time) {
      if (!time) {
        return 0
      }
      const t = new Date(time).getTime()
      return Number.isNaN(t) ? 0 : t
    },

    /** 与代码编辑器里的记录列表保持同一时间格式 */
    formatTime(time) {
      if (!time) {
        return '-'
      }
      const date = new Date(time)
      if (Number.isNaN(date.getTime())) {
        return String(time)
      }
      const pad = (n) => String(n).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
        + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    },

    /** 未知/为空的状态按「未知」处理，避免出现 st-undefined 样式（6=等待中，子任务专用） */
    normalizeStatus(status) {
      const n = Number(status)
      return [0, 1, 2, 3, 4, 5, 6].indexOf(n) >= 0 ? n : 'unknown'
    },

    /** 是否为「训练+评估」编排任务（py_task.type=0；历史数据与代码编辑器执行的都是 1） */
    isPipelineTask(row) {
      return !!row && Number(row.type) === 0
    },

    /**
     * 任务名称（列表列取值规则）：
     *   type=0 编排任务 → py_task.task_name（本表字段）
     *   type=1 简易任务 → 关联脚本名，即「代码名称」py_file.file_name
     */
    taskNameOf(row) {
      if (!row) {
        return '-'
      }
      if (this.isPipelineTask(row)) {
        return row.taskName || '（未命名）'
      }
      return row.scriptName || '（脚本已删除）'
    },

    /**
     * 能否编辑/删除：只有「待执行」（status=5）的编排任务。
     * 与后端 updatePipelineTask 的限制一致 —— 任务一旦开始执行，改配置会让
     * 库里记的配置与实际跑的东西对不上，所以只在待执行阶段允许。
     */
    canEditPipelineTask(row) {
      return this.isPipelineTask(row) && Number(row.status) === 5
    },

    /** 打开新建弹窗（taskId 置空 = 新建模式） */
    openCreateTask() {
      this.editingTaskId = ''
      this.newTaskVisible = true
    },

    /** 打开编辑弹窗：弹窗按 taskId 自行拉取详情回填 */
    openEditTask(row) {
      this.editingTaskId = row.taskId
      this.newTaskVisible = true
    },

    /** 删除任务（软删除，对应 /deletePyTask；该接口为通用实现，type=0/1 都支持） */
    async deleteTask(row) {
      try {
        await this.$confirm(
          `确定删除任务「${this.taskNameOf(row)}」吗？`,
          '删除任务',
          { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
        )
      } catch (error) {
        // 用户点了取消
        return
      }
      try {
        const response = await axios.post('/api/web/basedata/deletePyTask', { taskId: row.taskId })
        if (response.data && response.data.code === 0) {
          this.$message.success('已删除')
          this.loadTasks()
        } else {
          this.$message.error((response.data && response.data.message) || '删除失败')
        }
      } catch (error) {
        console.error('删除任务失败:', error)
        this.$message.error('删除失败：' + (error.message || '网络错误'))
      }
    },

    /**
     * 是否已结束（即已有结果可查看）：1成功 / 2失败 / 3运行终止 / 4已中断。
     * 0-执行中 与 5-待执行 都不算 —— 编排任务创建后是 5，此时还没有任何结果。
     */
    isFinishedTask(row) {
      return !!row && [1, 2, 3, 4].indexOf(Number(row.status)) >= 0
    },

    /** 是否未读：已结束 且 if_notified 为 0 */
    isUnread(row) {
      return this.isFinishedTask(row) && !row.ifNotified
    },

    /**
     * 能否点「详情」。
     *   · 编排任务（type=0）：在当前行下方展开子表格（训练 / 评估两个子任务）
     *   · 简易任务：跳代码编辑器查看该记录
     */
    canOpenDetail(row) {
      if (!row || !row.taskId) {
        return false
      }
      if (this.isPipelineTask(row)) {
        return true
      }
      return !!(row.pyId && row.scriptName)
    },

    /** 详情按钮提示 */
    detailTitle(row) {
      if (this.isPipelineTask(row)) {
        return '展开查看训练 / 评估子任务'
      }
      return this.canOpenDetail(row) ? '跳转到代码编辑器查看该记录' : '所属脚本已不存在，无法跳转'
    },

    openDetail(row) {
      if (!this.canOpenDetail(row)) {
        return
      }
      if (this.isPipelineTask(row)) {
        this.expandPipelineRow(row)
        return
      }
      // 由 App.vue 接收：记录导航意图并切到代码编辑器（见 App.handleOpenTaskRecord）
      this.$emit('open-task-record', { pyId: row.pyId, taskId: row.taskId })
    },

    /* ---------------- 「训练+评估」编排任务：执行与子任务 ---------------- */

    /** 能否执行：只有「待执行」（status=5）的编排任务 */
    canExecutePipelineTask(row) {
      return this.isPipelineTask(row) && Number(row.status) === 5
    },

    /**
     * 执行编排任务：父任务转执行中、训练子任务立刻开跑、评估子任务等待中。
     * 若评估卡选的是「复用历史成功训练任务」，则没有训练子任务 —— 只跑评估子任务。
     * 执行后「编辑 / 删除」自动消失（它们同样只在 status=5 时显示），详情仍可看子任务进度。
     */
    async executeTask(row) {
      const reuseTaskId = row.reuseTrainTaskId
      const confirmText = reuseTaskId
        ? `确定执行「${this.taskNameOf(row)}」吗？本次复用历史训练模型，`
            + '只执行评估子任务、不再训练；执行期间不能编辑或删除。'
        : `确定执行「${this.taskNameOf(row)}」吗？将先跑训练子任务，训练完成后自动接力评估子任务；`
            + '执行期间不能编辑或删除。'
      try {
        await this.$confirm(confirmText, '执行任务', {
          type: 'warning',
          confirmButtonText: '执行',
          cancelButtonText: '取消'
        })
      } catch (error) {
        // 用户点了取消
        return
      }
      try {
        const response = await axios.post('/api/web/basedata/executePipelineTask', {
          taskId: row.taskId
        })
        if (response.data && response.data.code === 0) {
          this.$message.success(reuseTaskId
            ? '已开始执行：评估子任务运行中（复用历史训练模型）'
            : '已开始执行：训练子任务运行中')
          await this.loadTasks()
          this.$nextTick(() => {
            const fresh = this.tasks.find((t) => t.taskId === row.taskId)
            if (fresh) {
              this.expandPipelineRow(fresh)
            }
          })
        } else {
          this.$message.error((response.data && response.data.message) || '执行失败')
        }
      } catch (error) {
        console.error('执行任务失败:', error)
        const msg = (error.response && error.response.data && error.response.data.message)
          || error.message || '网络错误'
        this.$message.error('执行失败：' + msg)
      }
    },

    /** 展开某一行（编排任务详情）：Element 的展开态是表格内部状态，得用实例切换 */
    async expandPipelineRow(row) {
      const table = this.$refs.taskTable
      if (table) {
        table.toggleRowExpansion(row, true)
      }
      // 展开详情 = 查看了这条任务的结果 → 顺手把「未读」标记消掉
      // （父任务没有自己的记录可点，这是它在任务管理页里唯一的已读入口）
      this.markPipelineTaskRead(row)
      await this.loadSubTasks(row.taskId)
    },

    /** 把编排任务的父任务标记为已读（已读/未执行时不发请求） */
    markPipelineTaskRead(row) {
      if (!row || !row.taskId || !this.isUnread(row)) {
        return
      }
      axios.post('/api/web/basedata/markPyTaskNotified', { taskId: row.taskId })
        .then(() => {
          const idx = this.tasks.findIndex((t) => t.taskId === row.taskId)
          if (idx >= 0) {
            this.$set(this.tasks, idx, { ...this.tasks[idx], ifNotified: true })
          }
        })
        .catch((error) => {
          console.warn('标记任务已读失败:', error)
        })
    },

    /** 用户手点行首箭头展开时也拉一次子任务 */
    handleExpandChange(row, expanded) {
      if (expanded && this.isPipelineTask(row)) {
        this.loadSubTasks(row.taskId)
      }
    },

    /** 拉取某个编排任务的两个子任务（训练 / 评估） */
    async loadSubTasks(taskId) {
      this.$set(this.subTaskLoading, taskId, true)
      try {
        const response = await axios.get('/api/web/basedata/getSubTaskList', {
          params: { taskId }
        })
        if (response.data && response.data.code === 0) {
          this.$set(this.subTasks, taskId, response.data.data || [])
        } else {
          this.$message.error((response.data && response.data.message) || '加载子任务失败')
        }
      } catch (error) {
        console.error('加载子任务失败:', error)
        this.$message.error('加载子任务失败')
      } finally {
        this.$set(this.subTaskLoading, taskId, false)
      }
    },

    subTasksOf(row) {
      return this.subTasks[row.taskId] || []
    },

    /** 子任务角色（按 id 后缀）：-train / -eval 是后端固定的命名约定 */
    subTaskRoleLabel(sub) {
      const id = (sub && sub.taskId) || ''
      if (id.endsWith('-train')) {
        return '训练子任务'
      }
      if (id.endsWith('-eval')) {
        return '评估子任务'
      }
      return '子任务'
    },

    canOpenSubTaskDetail(sub) {
      return !!(sub && sub.pyId && sub.scriptName)
    },

    /** 子任务「详情」：跳到代码编辑器对应脚本的记录里（记录列表会带「子任务」标识） */
    openSubTaskDetail(sub) {
      if (!this.canOpenSubTaskDetail(sub)) {
        return
      }
      this.$emit('open-task-record', { pyId: sub.pyId, taskId: sub.taskId })
    },

    /** 新建 / 编辑成功：清掉编辑态并刷新列表 */
    onTaskSaved() {
      this.editingTaskId = ''
      this.loadTasks()
    },

    /** 分页后序号的连续编号 */
    rowIndex(index) {
      return (this.currentPage - 1) * this.pageSize + index + 1
    },

    /**
     * 行样式类：用来给简易任务藏掉行首的展开箭头（配 CSS 用）。
     * 简易任务没有子任务，不该出现展开入口。
     */
    rowClassName({ row }) {
      return this.isPipelineTask(row) ? 'row-pipeline-task' : 'row-simple-task'
    }
  }
}
</script>

<style scoped>
.task-list-page {
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4, 16px);
  margin-bottom: var(--space-4, 16px);
}

.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--primary-text-color);
}

.table-card {
  border-radius: 10px;
}

.empty-tip {
  padding: 24px 0;
  text-align: center;
}

.pager {
  margin-top: 16px;
  text-align: right;
}

/* 状态标签：配色与代码编辑器任务列表保持一致 */
.task-status {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.task-status.st-0 {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.task-status.st-1 {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.task-status.st-2 {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.task-status.st-3 {
  background: rgba(158, 158, 158, 0.25);
  color: #9e9e9e;
}

.task-status.st-4 {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
}

/* 5-待执行：编排任务（type=0）创建后的初始状态 */
.task-status.st-5 {
  background: rgba(144, 147, 153, 0.2);
  color: #909399;
}

/* 任务类型标签：编排任务 vs 代码编辑器直接执行的简易任务 */
.task-type-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.task-type-tag.tt-pipeline {
  background: rgba(64, 158, 255, 0.15);
  color: #409eff;
}

.task-type-tag.tt-simple {
  background: rgba(144, 147, 153, 0.15);
  color: #909399;
}

/* 删除按钮：文本按钮形态，用危险色与「编辑/详情」区分 */
.danger-text-btn {
  color: #f56c6c;
}

.danger-text-btn:hover {
  color: #f78989;
}

.task-status.st-unknown {
  background: rgba(158, 158, 158, 0.2);
  color: var(--secondary-text-color);
}

/* 6-等待中：编排任务的评估子任务在等训练跑完（只有子任务会出现这个状态） */
.task-status.st-6 {
  background: rgba(230, 162, 60, 0.2);
  color: #e6a23c;
}

/* 「执行」按钮：与「编辑 / 详情」的文本按钮区分，用主色强调 */
.primary-text-btn {
  color: #409eff;
}

.primary-text-btn:hover {
  color: #66b1ff;
}

/* 详情展开区：训练 / 评估子表格 */
.subtask-wrap {
  padding: 8px 12px 12px 46px;
  background: var(--bg-color, #fafafa);
}

.subtask-tip {
  padding: 8px 0;
  font-size: 12px;
  color: var(--secondary-text-color);
}

/*
  简易任务：藏掉行首的展开箭头 —— 它们没有子任务，展开入口只属于「训练+评估」编排任务
  （编排任务由 rowClassName 加 row-pipeline-task 类，箭头照常显示）。
*/
.task-list-page >>> .el-table .row-simple-task .el-table__expand-column .cell {
  visibility: hidden;
}

/* 「未读」标记：与顶栏「待查看」、文件列表红点同一视觉语言 */
.unread-mark {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 16px;
  color: #ffffff;
  background: #f5222d;
  white-space: nowrap;
}
</style>
