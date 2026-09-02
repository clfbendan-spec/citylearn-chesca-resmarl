<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="6">
        <el-select v-model="monthValue" placeholder="月份" >
      <el-option
        v-for="item in monthOptions"
        :key="item.value"
        :label="item.label"
        :value="item.value">
      </el-option>
    </el-select>
      </el-col>
      <el-col :span="6">
        <el-select v-model="hourValue" placeholder="小时" >
      <el-option
        v-for="item in hourOptions"
        :key="item.value"
        :label="item.label"
        :value="item.value">
      </el-option>
    </el-select>
      </el-col>
      <el-col :span="6">
        <el-select v-model="dayTypeValue" placeholder="星期" >
      <el-option
        v-for="item in dayTypeOptions"
        :key="item.value"
        :label="item.label"
        :value="item.value">
      </el-option>
    </el-select>
      </el-col>
      <el-col :span="6">
        <el-button type="primary" @click="handleChange">搜索</el-button>
      </el-col>
      
     
    </el-row>
    
    
    

    <el-table
      :data="tableData"
      style="width: 100%"
      border
      stripe
      height="calc(100vh - 100px)"
      :max-height="1500"
      :scrollable="true"
      v-loading="loading">
      <el-table-column
        prop="month"
        label="月份"
        width="60"
        fixed="left"
        :formatter="formatMonth">
      </el-table-column>
      <el-table-column
        prop="hour"
        label="小时"
        width="60"
        fixed="left">
      </el-table-column>
      <el-table-column
          prop="dayType"
          label="星期"
          width="80"
          fixed="left"
          :formatter="formatDayType">
        </el-table-column>
      
      <el-table-column
        prop="daylightSavingsStatus"
        label="是否处于夏令时"
        :formatter="formatDaylightStatus">
      </el-table-column>
      <el-table-column
        prop="indoorDryBulbTemperature"
        label="室内干球温度">
      </el-table-column>
      <el-table-column
        prop="averageUnmetCoolingSetpointDifference"
        label="平均未满足冷却设定点温差">
      </el-table-column>
      <el-table-column
        prop="indoorRelativeHumidity"
        label="室内相对湿度">
      </el-table-column>
      <el-table-column
        prop="nonShiftableLoad"
        label="电器当前消耗电量">
      </el-table-column>
      <el-table-column
        prop="dhwDemand"
        label="供热需求">
      </el-table-column>
      <el-table-column
        prop="coolingDemand"
        label="制冷需求">
      </el-table-column>
      <el-table-column
        prop="heatingDemand"
        label="供暖需求">
      </el-table-column>
      <el-table-column
        prop="solarGeneration"
        label="光伏发电量">
      </el-table-column>
      <el-table-column
        prop="occupantCount"
        label="建筑内人员数量">
      </el-table-column>
      <el-table-column
        prop="indoorDryBulbTemperatureCoolingSetPoint"
        label="室内干球温度制冷设定点">
      </el-table-column>
      <el-table-column
        prop="indoorDryBulbTemperatureHeatingSetPoint"
        label="室内干球温度制热设定点">
      </el-table-column>
      <el-table-column
        prop="hvacMode"
        label="制冷模式">
      </el-table-column>
      <el-table-column
        prop="carbonIntensity"
        label="二氧化碳排放率">
      </el-table-column>
      <el-table-column
        prop="electricityPricing"
        label="单位电价">
      </el-table-column>
      <el-table-column
        prop="electricityPricingPredicted1"
        label="预测电价1">
      </el-table-column>
      <el-table-column
        prop="electricityPricingPredicted2"
        label="预测电价2">
      </el-table-column>
      <el-table-column
        prop="electricityPricingPredicted3"
        label="预测电价3">
      </el-table-column>
      <el-table-column
        prop="outdoorDryBulbTemperature"
        label="室外干球温度">
      </el-table-column>
      <el-table-column
        prop="outdoorRelativeHumidity"
        label="室外相对湿度">
      </el-table-column>
      <el-table-column
        prop="diffuseSolarIrradiance"
        label="散射太阳辐照度">
      </el-table-column>
      <el-table-column
        prop="directSolarIrradiance"
        label="直接太阳辐照度">
      </el-table-column>
      <el-table-column
        prop="outdoorDryBulbTemperaturePredicted1"
        label="室外干球温度预测1">
      </el-table-column>
      <el-table-column
        prop="outdoorDryBulbTemperaturePredicted2"
        label="室外干球温度预测2">
      </el-table-column>
      <el-table-column
        prop="outdoorDryBulbTemperaturePredicted3"
        label="室外干球温度预测3">
      </el-table-column>
      <el-table-column
        prop="outdoorRelativeHumidityPredicted1"
        label="室外相对湿度预测1">
      </el-table-column>
      <el-table-column
        prop="outdoorRelativeHumidityPredicted2"
        label="室外相对湿度预测2">
      </el-table-column>
      <el-table-column
        prop="outdoorRelativeHumidityPredicted3"
        label="室外相对湿度预测3">
      </el-table-column>
       <el-table-column
        prop="diffuseSolarIrradiancePredicted1"
        label="漫射太阳辐照度预测1">
      </el-table-column>
       <el-table-column
        prop="diffuseSolarIrradiancePredicted2"
        label="漫射太阳辐照度预测2">
      </el-table-column>
      <el-table-column
        prop="diffuseSolarIrradiancePredicted3"
        label="漫射太阳辐照度预测3">
      </el-table-column>
      <el-table-column
        prop="directSolarIrradiancePredicted1"
        label="直射太阳辐照度预测1">
      </el-table-column>
      <el-table-column
        prop="directSolarIrradiancePredicted2"
        label="直射太阳辐照度预测2">
      </el-table-column>
      <el-table-column
        prop="directSolarIrradiancePredicted3"
        label="直射太阳辐照度预测3">
      </el-table-column>
    </el-table>

  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      tableData: [],
      dayTypeValue: '',
      dayTypeOptions: [{
          value: '',
          label: '全部日期'
        },{
          value: '1',
          label: '星期一'
        }, {
          value: '2',
          label: '星期二'
        }, {
          value: '3',
          label: '星期三'
        }, {
          value: '4',
          label: '星期四'
        }, {
          value: '5',
          label: '星期五'
        },{
          value: '6',
          label: '星期六'
        },{
          value: '7',
          label: '星期天'
        }],
      hourValue: '',
      hourOptions: [{
          value: '',
          label: '全部时间'
        },{
          value: '1',
          label: '1'
        },{
          value: '2',
          label: '2'
        },{
          value: '3',
          label: '3'
        },{
          value: '4',
          label: '4'
        },{
          value: '5',
          label: '5'
        },{
          value: '6',
          label: '6'
        },{
          value: '7',
          label: '7'
        },{
          value: '8',
          label: '8'
        },{
          value: '9',
          label: '9'
        },{
          value: '10',
          label: '10'
        },{
          value: '11',
          label: '11'
        },{
          value: '12',
          label: '12'
        },{
          value: '13',
          label: '13'
        },{
          value: '14',
          label: '14'
        },{
          value: '15',
          label: '15'
        },{
          value: '16',
          label: '16'
        },{
          value: '17',
          label: '17'
        },{
          value: '18',
          label: '18'
        },{
          value: '19',
          label: '19'
        },{
          value: '20',
          label: '20'
        },{
          value: '21',
          label: '21'
        },{
          value: '22',
          label: '22'
        },{
          value: '23',
          label: '23'
        },{
          value: '24',
          label: '24'
        },],
      monthValue: '',
      monthOptions: [{
          value: '',
          label: '全部月份'
        },{
          value: '1',
          label: '1月'
        }, {
          value: '2',
          label: '2月'
        }, {
          value: '3',
          label: '3月'
        }, {
          value: '4',
          label: '4月'
        }, {
          value: '5',
          label: '5月'
        },{
          value: '6',
          label: '6月'
        },{
          value: '7',
          label: '7月'
        },{
          value: '8',
          label: '8月'
        },{
          value: '9',
          label: '9月'
        },{
          value: '10',
          label: '10月'
        },{
          value: '11',
          label: '11月'
        },{
          value: '12',
          label: '12月'
        },],
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
    formatDayType(row, column, cellValue) {
      switch (cellValue) {
        case 1:
          return '星期一';
        case 2:
          return '星期二';
        case 3:
          return '星期三';
        case 4:
          return '星期四';
        case 5:
          return '星期五';
        case 6:
          return '星期六';
        case 7:
          return '星期天';
        default:
          return '';
      }
    },
    formatMonth(row, column, cellValue) {
      switch (cellValue) {
        case 1:
          return '1月';
        case 2:
          return '2月';
        case 3:
          return '3月';
        case 4:
          return '4月';
        case 5:
          return '5月';
        case 6:
          return '6月';
        case 7:
          return '7月';
        case 8:
          return '8月';
        case 9:
          return '9月';
        case 10:
          return '10月';
        case 11:
          return '11月';
        case 12:
          return '12月';
        default:
          return '';
      }
    },
    formatDaylightStatus(row, column, cellValue) {
      return cellValue ? '是' : '否';
    },
    fetchData() {
      this.loading = true;
      axios.get('/api/web/basedata/getList', {
        params: {
          buildingId: 'building1',
          dayType: this.dayTypeValue,
          month: this.monthValue,
          hour: this.hourValue
        }
      })
      .then(response => {
        this.tableData = response.data.data;
        this.total = response.data.total || 0;
      })
      .catch(error => {
        console.error('获取数据失败:', error);
        this.$message.error('数据加载失败');
      })
      .finally(() => {
        this.loading = false;
      });
    },
    handleChange() {
      this.fetchData();
    },
    handleSizeChange(val) {
      this.pageSize = val;
      this.fetchData();
    },
    handleCurrentChange(val) {
      this.currentPage = val;
      this.fetchData();
    }
  }
}
</script>

<style scoped>
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

.el-row {
    margin-bottom: 20px;
    &:last-child {
      margin-bottom: 0;
    }
  }
  .el-col {
    border-radius: 4px;
  }
  .bg-purple-dark {
    background: #99a9bf;
  }
  .bg-purple {
    background: #d3dce6;
  }
  .bg-purple-light {
    background: #e5e9f2;
  }
  .grid-content {
    border-radius: 4px;
    min-height: 36px;
  }
  .row-bg {
    padding: 10px 0;
    background-color: #f9fafc;
  }
</style>