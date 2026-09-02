<template>

  <div class="building-management">

    <div class="toolbar">

      

      <div class="search-bar">

        <el-input

          v-model="searchName"

          class="search-input"

          placeholder="建筑名称"

          prefix-icon="el-icon-search"

          clearable

          @keyup.enter.native="handleSearch"

          @clear="handleSearch" />

        <el-button type="primary" @click="handleSearch">搜索</el-button>

      </div>

    </div>



    <div v-loading="loading" class="building-list">

      <div v-if="!loading && buildingList.length === 0" class="empty-tip">

        暂无建筑数据

      </div>



      <div

        v-for="item in buildingList"

        :key="item.id"

        class="building-item">

        <div class="item-thumb">

          <img

            :src="item.imageUrl"

            :alt="item.name"

            @error="onImageError($event)" />

        </div>



        <div class="item-content">

          <div class="title-row">

            <span class="item-title">{{ item.name }}</span>

            <!--<span class="status-tag">在册</span>-->

          </div>

          <div class="item-time">{{ formatTime(item.createTime) }}</div>

          <div class="detail-tags">

            <span v-if="item.description" class="detail-tag">

              <i class="el-icon-document"></i>

              {{ truncateText(item.description, 40) }}

            </span>

            <span class="detail-tag">

              <i class="el-icon-time"></i>

              更新于 {{ formatTime(item.updateTime) }}

            </span>

          </div>

        </div>



        <div class="item-actions">

          <button type="button" class="action-btn" @click="openEditDialog(item)">

            <i class="el-icon-edit"></i>

            编辑

          </button>

          <button type="button" class="action-btn danger" @click="handleDelete(item)">

            <i class="el-icon-delete"></i>

            删除

          </button>

        </div>

      </div>

    </div>



    <div v-if="total > pageSize" class="pagination-wrap">

      <el-pagination

        background

        layout="prev, pager, next"

        :current-page.sync="currentPage"

        :page-size="pageSize"

        :total="total"

        @current-change="fetchBuildingList" />

    </div>



    <el-dialog

      title="编辑建筑"

      :visible.sync="editDialogVisible"

      width="480px"

      @closed="resetEditForm">

      <el-form ref="editForm" :model="editForm" label-width="80px">

        <el-form-item label="名称" required>

          <el-input v-model="editForm.name" placeholder="建筑名称" />

        </el-form-item>

        <el-form-item label="信息">

          <el-input

            v-model="editForm.description"

            type="textarea"

            :rows="3"

            placeholder="建筑描述" />

        </el-form-item>

        <el-form-item label="图片">

          <el-input v-model="editForm.imageUrl" placeholder="图片 URL" />

        </el-form-item>

      </el-form>

      <span slot="footer">

        <el-button @click="editDialogVisible = false">取消</el-button>

        <el-button type="primary" :loading="saving" @click="handleSaveEdit">保存</el-button>

      </span>

    </el-dialog>

  </div>

</template>



<script>

import axios from 'axios'



const DEFAULT_IMAGE =

  'data:image/svg+xml,' +

  encodeURIComponent(

    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="90" viewBox="0 0 120 90">' +

      '<rect fill="#f0f2f5" width="120" height="90"/>' +

      '<text x="60" y="48" text-anchor="middle" fill="#bbb" font-size="12" font-family="sans-serif">暂无图片</text>' +

      '</svg>'

  )



export default {

  name: 'BuildingManagement',

  data() {

    return {

      activeTab: 'all',

      searchName: '',

      buildingList: [],

      loading: false,

      saving: false,

      currentPage: 1,

      pageSize: 10,

      total: 0,

      defaultImage: DEFAULT_IMAGE,

      editDialogVisible: false,

      editForm: {

        id: '',

        name: '',

        description: '',

        imageUrl: ''

      }

    }

  },

  mounted() {

    this.fetchBuildingList()

  },

  methods: {

    async fetchBuildingList() {

      this.loading = true

      try {

        const response = await axios.get('/api/web/communityBuilding/listPageCommunityBuilding', {

          params: {

            name: this.searchName || undefined,

            currentPage: this.currentPage,

            pageSize: this.pageSize

          }

        })

        if (response.data.code === 0) {

          const page = response.data.data || {}

          this.buildingList = page.rows || []

          this.buildingList.forEach(item => {

            item.imageUrl = "/api" + item.imageUrl

          })

          this.total = page.total || 0

        } else {

          this.$message.error(response.data.message || '加载失败')

        }

      } catch (error) {

        console.error('加载建筑列表失败:', error)

        this.$message.error('加载建筑列表失败')

      } finally {

        this.loading = false

      }

    },

    handleSearch() {

      this.currentPage = 1

      this.fetchBuildingList()

    },

    formatTime(value) {

      if (!value) return '-'

      const date = new Date(value)

      if (Number.isNaN(date.getTime())) return value

      const pad = (n) => String(n).padStart(2, '0')

      return (

        `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +

        `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`

      )

    },

    truncateText(text, maxLen) {

      if (!text) return ''

      return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text

    },

    onImageError(event) {

      event.target.src = this.defaultImage

    },

    openEditDialog(item) {

      this.editForm = {

        id: item.id,

        name: item.name,

        description: item.description || '',

        imageUrl: item.imageUrl || ''

      }

      this.editDialogVisible = true

    },

    resetEditForm() {

      this.editForm = { id: '', name: '', description: '', imageUrl: '' }

    },

    async handleSaveEdit() {

      if (!this.editForm.name.trim()) {

        this.$message.warning('请输入建筑名称');

        return

      }

      this.saving = true

      try {

        const params = new URLSearchParams()

        params.append('id', this.editForm.id)

        params.append('name', this.editForm.name.trim())

        params.append('description', this.editForm.description || '')

        params.append('imageUrl', this.editForm.imageUrl || '')

        const response = await axios.post(

          '/api/web/communityBuilding/editCommunityBuilding',

          params

        )

        if (response.data.code === 0) {

          this.$message.success('保存成功')

          this.editDialogVisible = false

          this.fetchBuildingList()

        } else {

          this.$message.error(response.data.message || '保存失败')

        }

      } catch (error) {

        console.error('保存失败:', error)

        this.$message.error('保存失败')

      } finally {

        this.saving = false

      }

    },

    handleDelete(item) {

      this.$confirm(`确定删除建筑「${item.name}」吗？`, '提示', {

        type: 'warning'

      })

        .then(() => this.doDelete(item.id))

        .catch(() => {})

    },

    async doDelete(id) {

      try {

        const params = new URLSearchParams()

        params.append('id', id)

        const response = await axios.post(

          '/api/web/communityBuilding/deleteCommunityBuilding',

          params

        )

        if (response.data.code === 0) {

          this.$message.success('删除成功')

          if (this.buildingList.length === 1 && this.currentPage > 1) {

            this.currentPage -= 1

          }

          this.fetchBuildingList()

        } else {

          this.$message.error(response.data.message || '删除失败')

        }

      } catch (error) {

        console.error('删除失败:', error)

        this.$message.error('删除失败')

      }

    }

  }

}

</script>



<style scoped>

.building-management {

  padding: 24px 32px;

  background: #fff;

  min-height: 100%;

  box-sizing: border-box;

}



.toolbar {

  display: flex;

  align-items: center;

  justify-content: flex-start;

  gap: 16px;

  margin-bottom: 16px;

}



.search-bar {

  display: flex;

  align-items: center;

  gap: 8px;

}



.filter-tabs {

  display: inline-flex;

  background: #f5f5f5;

  border-radius: 8px;

  padding: 3px;

}



.tab-item {

  border: none;

  background: transparent;

  padding: 8px 20px;

  font-size: 14px;

  color: #666;

  border-radius: 6px;

  cursor: pointer;

  outline: none;

  transition: all 0.2s;

}



.tab-item.active {

  background: #fff;

  color: #1a1a1a;

  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);

}



.search-input {

  width: 220px;

}



.search-input >>> .el-input__inner {

  border-radius: 20px;

  background: #f7f7f7;

  border-color: transparent;

}



.search-input >>> .el-input__inner:focus {

  border-color: #dcdfe6;

  background: #fff;

}



.building-list {

  min-height: 200px;

}



.empty-tip {

  text-align: center;

  color: #999;

  padding: 60px 0;

  font-size: 14px;

}



.building-item {

  display: flex;

  align-items: center;

  padding: 20px 0;

  border-bottom: 1px solid #eee;

  gap: 16px;

}



.item-thumb {

  flex-shrink: 0;

  width: 120px;

  height: 90px;

  border-radius: 6px;

  overflow: hidden;

  background: #f5f5f5;

}



.item-thumb img {

  width: 100%;

  height: 100%;

  object-fit: cover;

  display: block;

}



.item-content {

  flex: 1;

  min-width: 0;

}



.title-row {

  display: flex;

  align-items: center;

  gap: 8px;

  margin-bottom: 6px;

}



.item-title {

  font-size: 15px;

  font-weight: 600;

  color: #1a1a1a;

  overflow: hidden;

  text-overflow: ellipsis;

  white-space: nowrap;

}



.status-tag {

  flex-shrink: 0;

  font-size: 12px;

  color: #fff;

  background: #e6a23c;

  padding: 2px 8px;

  border-radius: 3px;

  line-height: 1.4;

}



.item-time {

  font-size: 13px;

  color: #999;

  margin-bottom: 10px;

}



.detail-tags {

  display: flex;

  flex-wrap: wrap;

  gap: 8px;

}



.detail-tag {

  display: inline-flex;

  align-items: center;

  gap: 4px;

  font-size: 12px;

  color: #888;

  background: #f5f5f5;

  padding: 4px 10px;

  border-radius: 4px;

}



.detail-tag i {

  font-size: 12px;

}



.item-actions {

  flex-shrink: 0;

  display: flex;

  flex-direction: column;

  gap: 10px;

  margin-left: 16px;

}



.action-btn {

  display: inline-flex;

  align-items: center;

  justify-content: center;

  gap: 4px;

  min-width: 110px;

  padding: 8px 16px;

  font-size: 13px;

  color: #666;

  background: #fff;

  border: 1px solid #ddd;

  border-radius: 6px;

  cursor: pointer;

  outline: none;

  transition: border-color 0.2s, color 0.2s;

}



.action-btn:hover {

  border-color: #bbb;

  color: #333;

}



.action-btn.danger:hover {

  border-color: #f56c6c;

  color: #f56c6c;

}



.pagination-wrap {

  margin-top: 24px;

  text-align: center;

}

</style>

