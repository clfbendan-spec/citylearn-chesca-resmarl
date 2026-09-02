<template>
  <div class="sim-tree">
    <el-collapse v-model="openBuildings">
      <el-collapse-item
        v-for="building in sortedBuildings"
        :key="building"
        :name="building"
        :title="formatLabel(building)"
      >
        <el-menu class="tree-menu" @select="onMenuSelect">
          <el-menu-item :index="`${building}_production`" @click="selectProduction(building)">
            发电(Production)
          </el-menu-item>
          <el-menu-item :index="`${building}_consumption`" @click="selectConsumption(building)">
            用电(Consumption)
          </el-menu-item>
          <template v-if="groups[building].chargers.length">
            <div class="sub-title">充电桩(Charger)</div>
            <el-menu-item
              v-for="(c, i) in groups[building].chargers"
              :key="c"
              :index="`${c}_charger`"
              @click="selectCharger(c, i + 1)"
            >
              充电桩 {{ i + 1 }}
            </el-menu-item>
          </template>
          <template v-if="groups[building].batteries.length">
            <div class="sub-title">电池(Battery)</div>
            <el-menu-item
              v-for="(b, i) in groups[building].batteries"
              :key="b"
              :index="`${b}_battery`"
              @click="selectBattery(b, i + 1)"
            >
              电池 {{ i + 1 }}
            </el-menu-item>
          </template>
        </el-menu>
      </el-collapse-item>
    </el-collapse>

    <el-collapse v-if="evKeys.length" v-model="openEvs" class="mt-8">
      <el-collapse-item name="evs" title="电动汽车(EVs)">
        <el-menu>
          <el-menu-item v-for="(ev,i) in evKeys" :key="ev" @click="selectEv(ev,i+1)">
            电动汽车 {{ i + 1 }}
          </el-menu-item>
        </el-menu>
      </el-collapse-item>
    </el-collapse>

    <el-collapse class="mt-8">
      <el-collapse-item  title="电价(Pricing)">
        <el-menu class="mt-8">
          <el-menu-item @click="selectPricing">电价</el-menu-item>
        </el-menu>
      </el-collapse-item>
    </el-collapse>
    
  </div>
</template>

<script>
export default {
  name: 'SimulationDataTree',
  props: {
    folderData: { type: Object, default: () => ({}) },
    selectedEpisode: { type: String, default: 'ep0' }
  },
  data() {
    return {
      openBuildings: [],
      openEvs: ['evs'],
      groups: {},
      evKeys: [],
      pricingKey: null
    }
  },
  computed: {
    sortedBuildings() {
      return Object.keys(this.groups).sort((a, b) => {
        const na = parseInt(a.match(/\d+/)?.[0] || '0', 10)
        const nb = parseInt(b.match(/\d+/)?.[0] || '0', 10)
        return na - nb
      })
    }
  },
  watch: {
    folderData: { immediate: true, handler: 'buildGroups' }
  },
  methods: {
    stripEpisode(key) {
      return key.replace(/_ep\d+$/i, '')
    },
    formatLabel(label) {
      return label.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    },
    buildGroups() {
      const groups = {}
      const evKeys = []
      let pricingKey = null

      Object.keys(this.folderData || {}).forEach((fullKey) => {
        const key = fullKey.toLowerCase()
        const base = this.stripEpisode(key)
        const charger = base.match(/^building_(\d+)_charger_\d+_(\d+)$/)
        const battery = base.match(/^building_(\d+)_battery/)
        const isBuilding = base.startsWith('building_') && !charger && !battery
        const isEv = base.includes('electric_vehicle')

        if (charger || battery) {
          const bKey = `building_${(charger || battery)[1]}`
          if (!groups[bKey]) groups[bKey] = { chargers: [], batteries: [] }
          if (charger) groups[bKey].chargers.push(fullKey)
          else groups[bKey].batteries.push(fullKey)
        } else if (isBuilding) {
          if (!groups[base]) groups[base] = { chargers: [], batteries: [] }
        }

        if (isEv) evKeys.push(fullKey)
        if (key.startsWith('pricing') && !pricingKey) pricingKey = fullKey
      })

      this.groups = groups
      this.evKeys = evKeys.sort()
      this.pricingKey = pricingKey
      this.openBuildings = this.sortedBuildings.slice(0, 1)
    },
    onMenuSelect() {},
    selectProduction(building) {
      const key = `${building}_${this.selectedEpisode}`
      this.$emit('graph', {
        title: `${this.formatLabel(building)} 发电(Production)`,
        data: this.folderData[key],
        chartType: 'production'
      })
    },
    selectConsumption(building) {
      const key = `${building}_${this.selectedEpisode}`
      this.$emit('graph', {
        title: `${this.formatLabel(building)} 用电(Consumption)`,
        data: this.folderData[key],
        chartType: 'consumption'
      })
    },
    selectCharger(chargerKey, index) {
      const m = this.stripEpisode(chargerKey).match(/^building_(\d+)_charger_\d+_(\d+)$/)
      this.$emit('equipment', {
        title: `建筑 ${m[1]} - 充电桩(Charger) ${index}`,
        data: this.folderData[chargerKey],
        chartType: 'charger'
      })
    },
    selectBattery(batteryKey, index) {
      const m = this.stripEpisode(batteryKey).match(/^building_(\d+)_battery/)
      this.$emit('equipment', {
        title: `建筑 ${m[1]} - 电池(Battery) ${index}`,
        data: this.folderData[batteryKey],
        chartType: 'battery'
      })
    },
    selectEv(evKey,index) {
      this.$emit('equipment', {
        title: `电动汽车(Electric Vehicle) ${index}`,
        data: this.folderData[evKey],
        chartType: 'ev'
      })
    },
    selectPricing() {
      this.$emit('equipment', {
        title: '电价(Pricing)',
        data: this.folderData[this.pricingKey],
        chartType: 'pricing'
      })
    }
  }
}
</script>

<style scoped>
.sim-tree {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  max-height: 875px;
  overflow-y: auto;
  padding: 8px;
}
.sub-title {
  font-size: 12px;
  color: #909399;
  padding: 8px 16px 4px;
}
.tree-menu { border-right: none; }
.mt-8 { margin-top: 8px; }
</style>
