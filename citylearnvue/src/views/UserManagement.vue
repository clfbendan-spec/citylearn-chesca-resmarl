<template>
  <div class="user-mgmt-page ha-page">
    <div class="page-header ha-toolbar">
      <div>
        <h2 class="page-title">用户管理</h2>
      </div>
      <div class="header-actions">
        <el-input
          v-model="searchUsername"
          class="search-input"
          placeholder="用户名"
          prefix-icon="el-icon-search"
          clearable
          @keyup.enter.native="handleSearch"
          @clear="handleSearch"
        />
        <el-button @click="handleSearch">搜索</el-button>
        <el-button type="primary" icon="el-icon-plus" @click="openAddDialog">新增管理员</el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never" class="table-card">
      <el-table :data="userList" stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="显示名称" min-width="120" />
        <el-table-column label="角色" width="140">
          <template slot-scope="{ row }">
            <el-tag v-if="row.role === 'SUPER_ADMIN'" size="small" type="warning">超级管理员</el-tag>
            <el-tag v-else size="small">系统管理员</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="160">
          <template slot-scope="{ row }">{{ formatTime(row.createTime) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template slot-scope="{ row }">
            <el-button type="text" @click="openResetPasswordDialog(row)">重置密码</el-button>
            <template v-if="row.role !== 'SUPER_ADMIN'">
              <el-button type="text" @click="openPermDialog(row)">权限</el-button>
              <el-button type="text" @click="openEditDialog(row)">编辑</el-button>
              <el-button type="text" class="danger-text" @click="handleDelete(row)">删除</el-button>
            </template>
          
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > pageSize" class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page.sync="currentPage"
          :page-size="pageSize"
          :total="total"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <el-dialog :title="dialogMode === 'add' ? '新增系统管理员' : '编辑系统管理员'" :visible.sync="dialogVisible" width="440px" @closed="clearDialogForm">
      <el-form ref="dialogForm" :model="dialogForm" :rules="dialogRules" label-width="88px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="dialogForm.username" maxlength="64" clearable />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="dialogForm.password"
            type="password"
            show-password
            :placeholder="dialogMode === 'edit' ? '留空则不修改密码' : '请输入密码'"
            maxlength="128"
            clearable
          />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'add' || dialogForm.password" label="确认密码" prop="confirmPassword">
          <el-input
            v-model="dialogForm.confirmPassword"
            type="password"
            show-password
            :placeholder="dialogMode === 'edit' ? '再次输入新密码' : '请再次输入密码'"
            maxlength="128"
            clearable
          />
        </el-form-item>
        <el-form-item label="显示名称" prop="nickname">
          <el-input v-model="dialogForm.nickname" maxlength="64" clearable />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitDialog">确定</el-button>
      </div>
    </el-dialog>

    <el-dialog title="重置密码" :visible.sync="resetDialogVisible" width="440px" @closed="clearResetPwdForm">
      <p class="reset-tip">为账号 <strong>{{ resetPwd.username }}</strong> 设置新密码</p>
      <el-form ref="resetPwdFormRef" :model="resetPwd" :rules="resetRules" label-width="88px">
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="resetPwd.password"
            type="password"
            show-password
            placeholder="请输入新密码"
            maxlength="128"
            clearable
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="resetPwd.confirmPassword"
            type="password"
            show-password
            placeholder="再次输入新密码"
            maxlength="128"
            clearable
          />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="resetDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="submitResetPassword">确定</el-button>
      </div>
    </el-dialog>

    <el-dialog
      :title="`分配权限 — ${permUser.username || ''}`"
      :visible.sync="permDialogVisible"
      width="520px"
      @closed="clearPermDialog"
    >
      <el-tree
        ref="permTree"
        v-loading="permLoading"
        :data="permTreeData"
        show-checkbox
        node-key="code"
        default-expand-all
        :props="permTreeProps"
        :check-strictly="true"
        @check-change="onPermCheckChange"
      />
      <div slot="footer">
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="permSaving" @click="submitPermissions">保存权限</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'UserManagement',
  data() {
    const passwordValidator = (rule, value, callback) => {
      if (this.dialogMode === 'add' && !value) {
        callback(new Error('请输入密码'))
        return
      }
      callback()
    }
    const dialogConfirmPasswordValidator = (rule, value, callback) => {
      if (this.dialogMode === 'add' || this.dialogForm.password) {
        if (!value) {
          callback(new Error('请再次输入密码'))
          return
        }
        if (value !== this.dialogForm.password) {
          callback(new Error('两次输入的密码不一致'))
          return
        }
      }
      callback()
    }
    const confirmPasswordValidator = (rule, value, callback) => {
      if (!value) {
        callback(new Error('请再次输入新密码'))
        return
      }
      if (value !== this.resetPwd.password) {
        callback(new Error('两次输入的密码不一致'))
        return
      }
      callback()
    }
    return {
      loading: false,
      saving: false,
      resetting: false,
      searchUsername: '',
      userList: [],
      currentPage: 1,
      pageSize: 10,
      total: 0,
      dialogVisible: false,
      dialogMode: 'add',
      dialogForm: {
        id: '',
        username: '',
        password: '',
        confirmPassword: '',
        nickname: ''
      },
      dialogRules: {
        username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
        password: [{ validator: passwordValidator, trigger: 'blur' }],
        confirmPassword: [{ validator: dialogConfirmPasswordValidator, trigger: 'blur' }]
      },
      resetDialogVisible: false,
      resetPwd: {
        id: '',
        username: '',
        password: '',
        confirmPassword: ''
      },
      resetRules: {
        password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
        confirmPassword: [{ validator: confirmPasswordValidator, trigger: 'blur' }]
      },
      permDialogVisible: false,
      permLoading: false,
      permSaving: false,
      permUser: { id: '', username: '' },
      permTreeData: [],
      permTreeProps: { label: 'label', children: 'children' },
      permCheckSyncing: false
    }
  },
  created() {
    this.fetchList()
    this.loadPermTree()
  },
  methods: {
    formatTime(val) {
      if (!val) return '—'
      const d = new Date(val)
      if (Number.isNaN(d.getTime())) return String(val)
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    },
    mapPermTree(nodes) {
      if (!Array.isArray(nodes)) return []
      return nodes.map((n) => ({
        code: n.code,
        label: n.label,
        children: this.mapPermTree(n.children)
      }))
    },
    collectDescendantCodes(node) {
      const codes = []
      const walk = (n) => {
        if (!n || !n.children) return
        n.children.forEach((child) => {
          codes.push(child.code)
          walk(child)
        })
      }
      walk(node)
      return codes
    },
    onPermCheckChange(data, checked) {
      if (this.permCheckSyncing) return
      const tree = this.$refs.permTree
      if (!tree || !data || !data.code) return
      this.permCheckSyncing = true
      try {
        if (checked) {
          // 勾选子级时必须勾选祖先父级
          let node = tree.getNode(data.code)
          while (node && node.parent && node.parent.level > 0) {
            const parentData = node.parent.data
            if (parentData && parentData.code) {
              tree.setChecked(parentData.code, true, false)
            }
            node = node.parent
          }
        } else {
          // 取消父级时取消全部子级；取消子级不影响父级
          const descendants = this.collectDescendantCodes(data)
          descendants.forEach((code) => {
            tree.setChecked(code, false, false)
          })
        }
      } finally {
        this.permCheckSyncing = false
      }
    },
    async loadPermTree() {
      try {
        const res = await axios.get('/api/web/user/permissionTree')
        if (res.data && res.data.code === 0) {
          this.permTreeData = this.mapPermTree(res.data.data || [])
        }
      } catch (e) {
        /* ignore */
      }
    },
    async openPermDialog(row) {
      this.permUser = { id: row.id, username: row.username }
      this.permDialogVisible = true
      this.permLoading = true
      try {
        if (!this.permTreeData.length) {
          await this.loadPermTree()
        }
        const res = await axios.get('/api/web/user/getPermissions', {
          params: { id: row.id }
        })
        const keys = (res.data && res.data.code === 0 && Array.isArray(res.data.data))
          ? res.data.data
          : []
        await this.$nextTick()
        const tree = this.$refs.permTree
        if (tree) {
          tree.setCheckedKeys([])
          tree.setCheckedKeys(keys)
        }
      } catch (e) {
        this.$message.error('加载用户权限失败')
      } finally {
        this.permLoading = false
      }
    },
    clearPermDialog() {
      this.permUser = { id: '', username: '' }
      if (this.$refs.permTree) {
        this.$refs.permTree.setCheckedKeys([])
      }
    },
    async submitPermissions() {
      const tree = this.$refs.permTree
      if (!tree || !this.permUser.id) return
      const checked = tree.getCheckedKeys(false) || []
      const permissions = [...new Set(checked)]
      this.permSaving = true
      try {
        const body = new URLSearchParams()
        body.append('id', this.permUser.id)
        body.append('permissions', JSON.stringify(permissions))
        const res = await axios.post('/api/web/user/savePermissions', body)
        if (res.data && res.data.code === 0) {
          this.$message.success('权限已保存')
          this.permDialogVisible = false
          this.fetchList()
        } else {
          this.$message.error((res.data && res.data.message) || '保存权限失败')
        }
      } catch (e) {
        this.$message.error('保存权限失败')
      } finally {
        this.permSaving = false
      }
    },
    handleSearch() {
      this.currentPage = 1
      this.fetchList()
    },
    async fetchList() {
      this.loading = true
      try {
        const res = await axios.get('/api/web/user/listPage', {
          params: {
            username: this.searchUsername || undefined,
            currentPage: this.currentPage,
            pageSize: this.pageSize
          }
        })
        if (res.data && res.data.code === 0) {
          const page = res.data.data || {}
          this.userList = page.rows || []
          this.total = page.total || 0
        } else {
          this.$message.error((res.data && res.data.message) || '加载用户失败')
        }
      } catch (e) {
        this.$message.error('加载用户失败')
      } finally {
        this.loading = false
      }
    },
    openAddDialog() {
      this.dialogMode = 'add'
      this.clearDialogForm()
      this.dialogVisible = true
    },
    openEditDialog(row) {
      this.dialogMode = 'edit'
      this.dialogForm = {
        id: row.id,
        username: row.username,
        password: '',
        confirmPassword: '',
        nickname: row.nickname || ''
      }
      this.dialogVisible = true
    },
    clearDialogForm() {
      this.dialogForm = { id: '', username: '', password: '', confirmPassword: '', nickname: '' }
      if (this.$refs.dialogForm) {
        this.$refs.dialogForm.clearValidate()
      }
    },
    openResetPasswordDialog(row) {
      this.resetPwd = {
        id: row.id,
        username: row.username,
        password: '',
        confirmPassword: ''
      }
      this.resetDialogVisible = true
      this.$nextTick(() => {
        if (this.$refs.resetPwdFormRef) {
          this.$refs.resetPwdFormRef.clearValidate()
        }
      })
    },
    clearResetPwdForm() {
      this.resetPwd = { id: '', username: '', password: '', confirmPassword: '' }
      if (this.$refs.resetPwdFormRef) {
        this.$refs.resetPwdFormRef.clearValidate()
      }
    },
    submitResetPassword() {
      this.$refs.resetPwdFormRef.validate(async (valid) => {
        if (!valid) return
        this.resetting = true
        try {
          const body = new URLSearchParams()
          body.append('id', this.resetPwd.id)
          body.append('password', this.resetPwd.password)
          const res = await axios.post('/api/web/user/resetPassword', body)
          if (res.data && res.data.code === 0) {
            this.$message.success('密码已重置')
            this.resetDialogVisible = false
          } else {
            this.$message.error((res.data && res.data.message) || '重置失败')
          }
        } catch (e) {
          this.$message.error('重置失败')
        } finally {
          this.resetting = false
        }
      })
    },
    submitDialog() {
      this.$refs.dialogForm.validate(async (valid) => {
        if (!valid) return
        this.saving = true
        try {
          const body = new URLSearchParams()
          if (this.dialogMode === 'add') {
            body.append('username', this.dialogForm.username.trim())
            body.append('password', this.dialogForm.password)
            if (this.dialogForm.nickname) body.append('nickname', this.dialogForm.nickname.trim())
            const res = await axios.post('/api/web/user/add', body)
            if (res.data && res.data.code === 0) {
              this.$message.success('新增成功')
              this.dialogVisible = false
              this.fetchList()
            } else {
              this.$message.error((res.data && res.data.message) || '新增失败')
            }
          } else {
            body.append('id', this.dialogForm.id)
            body.append('username', this.dialogForm.username.trim())
            if (this.dialogForm.password) body.append('password', this.dialogForm.password)
            body.append('nickname', this.dialogForm.nickname || '')
            const res = await axios.post('/api/web/user/edit', body)
            if (res.data && res.data.code === 0) {
              this.$message.success('保存成功')
              this.dialogVisible = false
              this.fetchList()
            } else {
              this.$message.error((res.data && res.data.message) || '保存失败')
            }
          }
        } catch (e) {
          this.$message.error('操作失败')
        } finally {
          this.saving = false
        }
      })
    },
    handleDelete(row) {
      this.$confirm(`确定删除管理员「${row.username}」吗？`, '提示', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
        .then(async () => {
          const body = new URLSearchParams()
          body.append('id', row.id)
          const res = await axios.post('/api/web/user/delete', body)
          if (res.data && res.data.code === 0) {
            this.$message.success('已删除')
            this.fetchList()
          } else {
            this.$message.error((res.data && res.data.message) || '删除失败')
          }
        })
        .catch(() => {})
    }
  }
}
</script>

<style scoped>
.user-mgmt-page {
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

.search-input {
  width: 200px;
}

.table-card {
  border-radius: 12px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.danger-text {
  color: var(--error-color, #db4437) !important;
}

.reset-tip {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--secondary-text-color);
}

.reset-tip strong {
  color: var(--primary-text-color);
  font-weight: 500;
}


.muted-tip {
  font-size: 12px;
  color: var(--disabled-text-color, #bdbdbd);
}
</style>
