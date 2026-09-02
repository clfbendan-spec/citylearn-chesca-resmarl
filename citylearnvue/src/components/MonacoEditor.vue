<template>
  <div class="python-editor">
    <div class="editor-header">
      <h3>{{ fileName }}</h3>
      <div class="controls">
        <template v-if="listMode === 'files'">
          <button
            @click="toggleIfShow"
            :disabled="!currentFile || isTogglingIfShow"
            class="btn-show"
            :class="{ 'btn-show-active': currentFileIfShow }"
            :title="currentFileIfShow ? '当前结果将在前端展示，点击设为未展示' : '当前结果未展示，点击设为展示中'"
          >
            {{ isTogglingIfShow ? '更新中...' : (currentFileIfShow ? '展示中' : '未展示') }}
          </button>
          <button
            @click="enterTaskRecordMode"
            :disabled="!currentFile"
            class="btn-record"
            title="查看执行记录"
          >
            记录
          </button>
          <button
            @click="runPyFile"
            :disabled="runButtonDisabled"
            class="btn-run"
            :title="runButtonTitle"
          >
            {{ runButtonLabel }}
          </button>
          <button @click="saveCode" :disabled="isSaving || null==this.currentFile || !this.currentFile?.ifEdit" class="btn-save">
            {{ isSaving ? '保存中...' : '保存' }}
          </button>
        </template>
        <button
          v-else
          @click="exitTaskRecordMode"
          class="btn-back"
          title="返回文件列表"
        >
          返回
        </button>
      </div>
    </div>

    <div class="editor-layout">
      <div class="file-list">
        <div class="file-list-content">
          <h4 v-if="listMode === 'files'">
            文件列表
            <button style="float: right;" @click.stop="addPyFile()" class="rename-btn"><i class="el-icon-folder-add"></i></button>
          </h4>
          <h4 v-else>执行记录</h4>

          <ul v-if="listMode === 'files' && files.length">
            <li 
              v-for="file in files" 
              :key="file.id"
              :class="{ active: file.id === currentFileId && !viewingTaskRecord }"
            >
              <div v-if="file.id !== editingFileId" class="file-item">
                <span @click="selectFile(file)">
                  <div style="color:chocolate" v-show="file.ifEdit"><i v-show="file.ifSystem" class="el-icon-star-off"></i>{{ file.fileName }}</div>
                  <div v-show="!file.ifEdit"><i v-show="file.ifSystem" class="el-icon-star-off"></i>{{ file.fileName }}</div>
                </span>
                <button @click.stop="startEditing(file)" class="rename-btn"><i class="el-icon-edit"></i></button>
                <button @click.stop="deletePyFile(file)" class="rename-btn"><i class="el-icon-folder-delete"></i></button>
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
            <li v-else-if="!taskList.length" class="loading">暂无执行记录</li>
            <li
              v-for="(task, index) in taskList"
              :key="task.taskId"
              :class="{ active: task.taskId === currentTaskId }"
              @click="selectTask(task)"
            >
              <div class="task-item">
                <span class="task-title">{{ index + 1 }}. {{ formatTaskTime(task.createTime) }}</span>
                <span v-if="task.showName" class="task-show-name" :title="task.showName">{{ task.showName }}</span>
                <span class="task-status" :class="'task-status-' + task.status">{{ task.statusDesc }}</span>
                <button
                  type="button"
                  class="btn-task-name"
                  :disabled="editingShowNameTaskId === task.taskId"
                  title="添加或更改仪表盘展示名称"
                  @click.stop="editTaskShowName(task)"
                >
                  {{ editingShowNameTaskId === task.taskId ? '...' : (task.showName ? '改名' : '名称') }}
                </button>
                <button
                  v-if="Number(task.status) === 1"
                  type="button"
                  class="btn-task-show"
                  :class="{ 'btn-task-show-active': !!task.ifShow }"
                  :disabled="togglingTaskId === task.taskId"
                  :title="task.ifShow ? '已在仪表盘展示，点击设为未展示' : '未展示，点击后可在仿真仪表盘选择'"
                  @click.stop="toggleTaskIfShow(task)"
                >
                  {{ togglingTaskId === task.taskId ? '...' : (task.ifShow ? '展示' : '未展示') }}
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
            @blur="updateFileDescription()"
          ></textarea>
        </div>
      </div>

      <div class="editor-area">
        <div ref="editorContainer" class="editor-container"></div>
        
        <div v-if="showOutputPanel" class="output-panel">
          <div class="output-header">
            <span>输出</span>
            <button @click="output = ''" class="btn-clear">清空</button>
          </div>
          <pre ref="outputContent" class="output-content">{{ formatConsoleOutput(output) || (isPollingTask || isCurrentFileRunning ? '运行中，等待输出…' : '') }}</pre>
        </div>
        
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import * as monaco from 'monaco-editor';
import axios from 'axios';

export default {
  name: 'PythonEditor',
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
      /** pyId -> { taskId, status }，status: 0执行中 1成功 2失败 */
      runningTasks: {},
      pollTimer: null,
      consolePollTimer: null,
      activePollTaskId: null,
      isPollingTask: false,
      output: '',
      error: '',
      fileName: '',
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
      taskList: [],
      isLoadingTasks: false,
      currentTaskId: null,
      viewingTaskRecord: false,
      togglingTaskId: null,
      editingShowNameTaskId: null
    };
  },
  computed: {
    fileId() {
      return btoa(this.filePath); // 简单的路径编码
    },
    isCurrentFileRunning() {
      if (!this.currentFileId) {
        return false;
      }
      const task = this.runningTasks[this.currentFileId];
      return task && Number(task.status) === 0;
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
        this.currentFile.ifEdit ||
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
    runButtonTitle() {
      if (!this.currentFile) {
        return '请先选择文件';
      }
      if (this.currentFile.ifEdit) {
        return '请先保存后再执行';
      }
      if (this.isCurrentFileRunning) {
        return '当前文件正在执行';
      }
      return '执行 Python 脚本';
    }
  },
  watch: {
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
        this.$nextTick(() => this.handleResize());
      }
    }
  },
  mounted() {
    this.initEditor();
    this.fetchFiles();
    window.addEventListener('resize', this.handleResize);
  },
  beforeDestroy() {
    this.stopPollTask();
    if (this.editor) {
      this.editor.dispose();
    }
    window.removeEventListener('resize', this.handleResize);
  },
  methods: {
    async fetchFiles() {
      this.isLoadingFiles = true;
      axios.get('/api/web/basedata/getPyFileList', {
      })
      .then(response => {
        this.files = response.data.data || [];
        if (!this.currentFileId && this.files.length) {
          this.selectFile(this.files[0]);
        }
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      }).finally(() => {
        this.isLoadingFiles = false;
      });
    },
    
    async selectFile(file) {
      this.stopPollTask();
      this.listMode = 'files';
      this.viewingTaskRecord = false;
      this.currentTaskId = null;
      this.setEditorReadOnly(false);
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
      this.loadCode();
    },

    setEditorReadOnly(readOnly) {
      if (this.editor) {
        this.editor.updateOptions({ readOnly });
      }
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
      if (!this.currentFile) {
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
        this.$message.success(ifShow ? '已设为【展示】，可在仿真仪表盘选择' : '已设为【未展示】');
      } catch (error) {
        console.error('更新记录展示状态失败:', error);
        this.$message.error('更新记录展示状态失败');
      } finally {
        this.togglingTaskId = null;
      }
    },

    async editTaskShowName(task) {
      if (!task || !task.taskId) {
        return;
      }
      let value;
      try {
        const result = await this.$prompt(
          '有名称时，仿真仪表盘分组将按此名称显示；留空则显示「代码名 + 记录时间」。',
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

    async enterTaskRecordMode(taskIdToSelect = null) {
      if (!this.currentFile) {
        this.$message.warning('请先选择文件');
        return;
      }
      this.listMode = 'tasks';
      this.viewingTaskRecord = false;
      if (taskIdToSelect) {
        this.currentTaskId = taskIdToSelect;
      } else {
        this.currentTaskId = null;
        this.output = '';
        this.error = '';
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
      this.setEditorReadOnly(false);
      if (this.currentFile) {
        this.fileName = this.currentFile.fileName;
        this.loadCode();
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
          this.$message.error(response.data.message || '加载执行记录失败');
        }
      } catch (error) {
        console.error('加载执行记录失败:', error);
        this.$message.error('加载执行记录失败');
      } finally {
        this.isLoadingTasks = false;
      }
    },

    async selectTask(task) {
      await this.selectTaskRecord(task, true);
    },

    async selectTaskRecord(task, restartPoll) {
      this.currentTaskId = task.taskId;
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
          if (result.output != null) {
            this.output = result.output;
            this.scrollOutputToBottom();
          }
          if (result.errorMessage) {
            this.error = result.errorMessage;
          }
          if (restartPoll && Number(result.status) === 0 && this.currentFileId) {
            this.startPollTask(task.taskId, this.currentFileId);
          } else if (Number(result.status) === 0 && this.activePollTaskId === task.taskId) {
            this.isPollingTask = true;
          }
        }
      } catch (error) {
        console.error('加载任务脚本失败:', error);
        this.$message.error('加载任务脚本失败');
      }
    },
    async deletePyFile(file){
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
      
      // 监听内容变化
      this.editor.onDidChangeModelContent(() => {
        if(this.currentFile.code!=this.editor.getValue()){
          this.currentFile.code=this.editor.getValue();
          if(this.currentFile.oriCode!=this.currentFile.code){
            this.currentFile.ifEdit=true;
            this.$forceUpdate();
          }else{
            this.currentFile.ifEdit=false;
            this.$forceUpdate();
          }
        }
        
        //alert(this.currentFile.ifEdit)
        
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
         this.currentFile.ifEdit=false;
          this.editor.setValue(this.currentFile.code);
          this.code = code;
          this.error = '';
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      })
      }else{
        this.editor.setValue(this.currentFile.code);
        this.code = this.currentFile.code;
          this.error = '';
      }
      
    },
    
    async saveCode() {
      this.isSaving = true;
      this.error = '';
      
      try {
        const response = await axios.post('/api/web/basedata/savePyFile', {
          id: this.currentFile.id,
          code:this.currentFile.code
        });
        console.log(response.data)
        if (response.data.code==0) {
          this.currentFile.oriCode=this.currentFile.code;
          this.currentFile.ifEdit=false;
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

    scrollOutputToBottom() {
      this.$nextTick(() => {
        const el = this.$refs.outputContent;
        if (el) {
          el.scrollTop = el.scrollHeight;
        }
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
      this.isPollingTask = true;

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
          this.runningTasks = {
            ...this.runningTasks,
            [pyId]: { taskId: task.taskId, status: Number(task.status) }
          };
          if (task.output != null && task.output !== '') {
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
          this.runningTasks = {
            ...this.runningTasks,
            [pyId]: { taskId: task.taskId, status: Number(task.status) }
          };
          if (task.output != null && task.output !== '') {
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
      this.stopPollTask();
      const next = { ...this.runningTasks };
      delete next[pyId];
      this.runningTasks = next;
      if (task.status === 1) {
        this.$message.success('执行完成');
        this.error = '';
      } else if (task.status === 2) {
        const msg = task.errorMessage || '执行失败';
        this.error = msg;
        this.$message.error(msg);
      }
      if (task.output != null) {
        this.output = task.output;
        this.scrollOutputToBottom();
      }
      if (this.listMode === 'tasks' && this.currentFileId) {
        this.fetchTaskList();
      }
    },

    async runPyFile() {
      if (!this.currentFile) {
        this.$message.warning('请先选择文件');
        return;
      }
      if (this.currentFile.ifEdit) {
        this.$message.warning('请先保存后再执行');
        return;
      }
      if (this.isCurrentFileRunning) {
        return;
      }

      this.isRunning = true;
      this.output = '';
      this.error = '';

      try {
        const response = await axios.post('/api/web/basedata/runPyFile', {
          id: this.currentFile.id
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
        this.$message.success('已开始执行');
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
    },
    
    startEditing(file) {
      this.editingFileId = file.id;
      this.editingFileName = file.fileName;
      this.editingFileOriginalName = file.fileName;
      this.$nextTick(() => {
        this.$refs.renameInput?.focus();
      });
    },
    
    async confirmRename() {
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

.btn-back {
  background: #5a5a5a;
  color: white;
}

.btn-back:hover {
  background: #6e6e6e;
}

.btn-run {
  background: #55aa55;
  color: white;
}

.btn-run:hover:not(:disabled) {
  background: #66bb66;
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

.editor-container {
  flex: 1 1 auto;
  min-height: 0;
}

.output-panel {
  flex: 0 0 200px;
  border-top: 1px solid #3e3e42;
  background: #1e1e1e;
  min-height: 160px;
  max-height: 200px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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

.output-content {
  flex: 1;
  padding: 12px 16px;
  margin: 0;
  overflow: auto;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
}

.error-message {
  padding: 12px 16px;
  background: #c75050;
  color: white;
  font-size: 14px;
}
</style>