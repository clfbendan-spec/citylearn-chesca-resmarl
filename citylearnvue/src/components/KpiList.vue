<template>
  <div class="kpi-container">
    <div class="search-container">
      <el-row type="flex" justify="center">
        <el-col :span="20">
          <el-select v-model="optionValue" style="width:100%">
            <el-option
              v-for="item in options"
              :key="item.value"
              :label="item.label"
              :value="item.value">
            </el-option>
          </el-select>
        </el-col>
        <el-col :span="4" :offset="1">
          <el-button type="primary" @click="handleChange">搜索</el-button>
        </el-col>
      </el-row>
    </div>
    <div class="table-container">
      <div class="table-wrapper">
        <el-table
          ref="table1"
          :data="tableData1"
          style="width: 100%"
          border
          stripe
          height="calc(100vh - 250px)"
          :max-height="600"
          :scrollable="true"
          v-loading="loading"
          @scroll="handleTable1Scroll">
        <el-table-column
          prop="line1"
          label="行列"
          >
        </el-table-column>
        <el-table-column
          prop="line2"
          label="Building_1"
          >
        </el-table-column>
        <el-table-column
          prop="line3"
          label="Building_2"
          >
        </el-table-column>
        <el-table-column
          prop="line4"
          label="Building_3"
         >
        </el-table-column>
        <el-table-column
          prop="line5"
          label="District"
          >
        </el-table-column>
      </el-table>
    </div>
    <div class="table-wrapper">
      <el-table
        ref="table2"
        :data="tableData2"
        style="width: 100%"
        border
        stripe
        height="calc(100vh - 250px)"
        :max-height="600"
        :scrollable="true"
        v-loading="loading"
        @scroll="handleTable2Scroll">
        <el-table-column
          prop="line1"
          label="行列"
          >
        </el-table-column>
        <el-table-column
          prop="line2"
          label="Building_1"
          >
        </el-table-column>
        <el-table-column
          prop="line3"
          label="Building_2"
          >
        </el-table-column>
        <el-table-column
          prop="line4"
          label="Building_3"
          >
        </el-table-column>
        <el-table-column
          prop="line5"
          label="District"
          >
        </el-table-column>
     
      </el-table>
    </div>
  </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
       options: [{
          value: 'diSac',
          label: '分散式独立 SAC'
        }, {
          value: 'multi',
          label: '多智能体 SAC'
        }, {
          value: 'single',
          label: '单智能体 SAC'
        }],
      optionValue:'diSac',
      tableData1: [],
      tableData2: [],
      loading: false,
      pageSize: 20,
      currentPage: 1,
      total: 0
    }
  },
  created() {
    this.fetchData();
  },
  methods: {
    fetchData() {
      this.loading = true;
      if(this.tableData1.length==0){
        axios.get('/api/web/basedata/getKpis', {
        params: {
          agentType: 'baseLine',
        }
      })
      .then(response => {
        this.tableData1 = response.data.data;
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      })
      }
      axios.get('/api/web/basedata/getKpis', {
        params: {
          agentType: this.optionValue,
        }
      })
      .then(response => {
        this.tableData2 = response.data.data;
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      })
      

      this.loading = false;
    },
    handleChange() {
      this.fetchData();
    },
    handleTable1Scroll(e) {
      if (this.$refs.table2) {
        const wrapper = this.$refs.table2.$el.querySelector('.el-table__body-wrapper');
        if (wrapper && wrapper.scrollTop !== e.target.scrollTop) {
          wrapper.scrollTop = e.target.scrollTop;
        }
      }
    },
    handleTable2Scroll(e) {
      if (this.$refs.table1) {
        const wrapper = this.$refs.table1.$el.querySelector('.el-table__body-wrapper');
        if (wrapper && wrapper.scrollTop !== e.target.scrollTop) {
          wrapper.scrollTop = e.target.scrollTop;
        }
      }
    },
  }
}
</script>

<style scoped>
.kpi-container {
  display: flex;
  flex-direction: column;
}

.search-container {
  margin-bottom: 20px;
  width: 100%;
  display: flex;
  justify-content: center;
}

.table-container {
  display: flex;
  width: 100%;
  gap: 20px;
}
.table-wrapper {
  flex: 0 0 calc(50% - 10px);
  min-width: 0;
}
.el-table {
  margin: 20px 0;
  overflow: auto;
}
.el-table::before {
  height: 0;
}
.el-table__body-wrapper {
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: #409EFF #f5f5f5;
}
.el-table__body-wrapper::-webkit-scrollbar {
  height: 8px;
  width: 8px;
}
.el-table__body-wrapper::-webkit-scrollbar-track {
  background: #f5f5f5;
}
.el-table__body-wrapper::-webkit-scrollbar-thumb {
  background-color: #409EFF;
  border-radius: 4px;
}
.el-pagination {
  justify-content: center;
}
.tooltip-content {
  display: inline-block;
  margin: 5px;
}
.tooltip-content span {
  cursor: pointer;
  color: #409EFF;
}
.image-list-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.pagination {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.image-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.image {
  width: 100%;
  height: 100%;
  border-radius: 4px;
}

.image-title {
  margin-top: 8px;
  text-align: center;
  font-weight: bold;
}



.detail-container {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.detail-image {
  width: auto;
  max-width: 100%;
  max-height: 70vh;
  margin-bottom: 20px;
}

.detail-title {
  margin-bottom: 15px;
  text-align: center;
}

.detail-description {
  width: 100%;
  text-align: center;
}

.detail-description p {
  margin-bottom: 10px;
}
</style>