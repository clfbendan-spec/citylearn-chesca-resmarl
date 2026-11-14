<template>
  <section class="equipment-editor">
    <h3>设备参数</h3>
    <div class="device-toggles">
      <div v-for="device in displayDefinitions" :key="device.key" class="device-toggle">
        <span>{{ device.label }}</span><el-switch :value="!!value[device.key]" :aria-label="device.label + '设备开关'" @change="toggle(device, $event)" />
      </div>
    </div>
    <el-collapse v-model="openPanels">
      <el-collapse-item v-for="device in enabledDevices" :key="device.key" :name="device.key">
        <template slot="title">{{ device.label }}<span class="schema-key">{{ device.key }}</span></template>
        <div class="device-type">{{ value[device.key].type }}</div>
        <div class="device-fields">
          <el-form-item v-for="field in device.fields" :key="field.key" :label="field.label">
            <span class="attribute-key">{{ field.key }}</span>
            <el-input-number :value="value[device.key].attributes[field.key]" :min="field.min === undefined ? 0 : field.min"
                             :max="field.max === undefined ? 100000000 : field.max" :step="field.step || 0.1"
                             :controls="false" @change="setAttribute(device.key, field.key, $event)" />
          </el-form-item>
          <el-form-item label="自动定容">
            <span class="attribute-key">autosize</span>
            <el-switch :value="!!value[device.key].autosize" :disabled="device.key === 'pv' && !value[device.key].autosize" @change="setDevice(device.key, 'autosize', $event)" />
            <span v-if="device.key === 'pv'" class="attribute-key">光伏按装机容量配置</span>
            <p class="parameter-help">{{ autosizeHelp(device.key) }}</p>
            <p v-if="device.key !== 'pv'" class="parameter-help">关闭时使用手填规格。此设置只影响仿真，不会改变实际设备，也不会随实时上报自动调整。</p>
          </el-form-item>
          <el-form-item v-if="value[device.key].autosize" label="定容安全系数">
            <span class="attribute-key">autosize_attributes.safety_factor</span>
            <el-input-number :value="(value[device.key].autosize_attributes || {}).safety_factor" :min="0.0001" :controls="false" @change="setSizing(device.key, $event)" />
            <p class="parameter-help">{{ safetyHelp(device.key) }}</p>
          </el-form-item>
        </div>
        <template v-if="device.key === 'electrical_storage'">
          <el-form-item v-for="curve in curves" :key="curve.key" :label="curve.label">
            <span class="attribute-key">{{ curve.key }}</span>
            <el-input type="textarea" :rows="2" :value="curveText[curve.key]" @input="$set(curveText, curve.key, $event)" />
            <p class="parameter-help">{{ curve.description }}</p>
            <p class="parameter-help">{{ curve.example }}</p>
            <p class="parameter-help">按 JSON 填写至少两个 [x,y] 点，x 从 0 递增到 1，点间线性插值。留空会使用 CityLearn 根据随机种子生成的默认曲线。</p>
          </el-form-item>
        </template>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<script>
const field = (key, label, max, min, step) => ({ key, label, max, min, step })
const efficiency = field('efficiency', '设备效率', 1, 0.0001, 0.01)
const storage = [field('capacity', '容量 (kWh)'), efficiency,
  field('loss_coefficient', '每步损耗系数', 1, 0, 0.0001), field('initial_soc', '初始荷电比例', 1, 0, 0.01)]
const heatPump = [field('nominal_power', '额定输入功率 (kW)'), efficiency,
  field('target_cooling_temperature', '制冷目标温度 (C)', 150, -100),
  field('target_heating_temperature', '供热目标温度 (C)', 150, -100)]
const definitions = [
  {key:'electrical_storage',label:'储能电池',fields:[...storage,field('nominal_power','额定功率 (kW)'),field('capacity_loss_coefficient','容量衰减系数',1,0,0.00001),field('depth_of_discharge','放电深度',1,0.0001,0.01)]},
  {key:'pv',label:'光伏',fields:[field('nominal_power','装机容量 (kW)')]},
  {key:'cooling_device',label:'制冷热泵',fields:heatPump},
  {key:'heating_device',label:'供热热泵',fields:heatPump},
  {key:'dhw_device',label:'生活热水设备',fields:[field('nominal_power','额定输入功率 (kW)'),efficiency]},
  ...['cooling','heating','dhw'].map((key,i)=>({key:key+'_storage',label:['蓄冷设备','蓄热设备','热水储罐'][i],fields:[...storage,field('max_input_power','最大充入功率 (kW)'),field('max_output_power','最大输出功率 (kW)')]}))
]
const clone = value => JSON.parse(JSON.stringify(value))
export default {
  name:'SchemaEquipmentForm',
  props:{value:{type:Object,required:true},templates:{type:Object,required:true}},
  data:()=>({definitions,openPanels:['electrical_storage'],deviceDrafts:{},curveText:{},curves:[
    {key:'power_efficiency_curve',label:'功率—效率曲线 [功率比例, 效率]',description:'x 是充放电功率绝对值占额定功率的比例；y 是该工作点的电池效率参数。它描述不同工作功率下的损耗，不表示剩余电量。',example:'例如额定功率 5 kW，[0.5,0.95] 表示约 2.5 kW 工作时采用 0.95 的效率参数。效率 y 须大于 0 且不超过 1。'},
    {key:'capacity_power_curve',label:'荷电—功率曲线 [荷电比例, 功率比例]',description:'x 是当前储电量占电池容量的比例（SOC）；y 是此状态下允许的充放电功率占额定功率的比例，取值 0–1。实际功率还受可用电量、剩余容量等约束。',example:'例如额定功率 5 kW，[0.8,1] 表示 SOC 为 80% 时曲线允许最高 5 kW；[1,0.25] 表示 SOC 为 100% 时曲线给出的上限为 1.25 kW。'}
  ]}),
  computed:{
    displayDefinitions(){return definitions.map(device=>device.key==='heating_device'&&this.value.heating_device&&this.value.heating_device.type==='citylearn.energy_model.ElectricHeater'?{...device,label:'供热电加热器',fields:[field('nominal_power','额定输入功率 (kW)'),efficiency]}:device)},
    enabledDevices(){return this.displayDefinitions.filter(device=>this.value[device.key])}
  },
  watch:{value:{immediate:true,handler(value){if(!value.electrical_storage)return;const attrs=value.electrical_storage.attributes||{};this.curves.forEach(curve=>{const serialized=attrs[curve.key]?JSON.stringify(attrs[curve.key]):'';if(this._lastCurveValues && this._lastCurveValues[curve.key]===serialized)return;this.$set(this.curveText,curve.key,serialized)});this._lastCurveValues=Object.fromEntries(this.curves.map(curve=>[curve.key,attrs[curve.key]?JSON.stringify(attrs[curve.key]):'']))}}},
  methods:{
    autosizeHelp(key){if(key==='pv')return '光伏自动定容需要 EPW 气象文件，当前未支持此类文件接入，因此使用手填装机容量。';if(key==='electrical_storage')return '开启后，在创建 CityLearn 仿真环境时，根据所选数据的用电需求选择电池型号和规模，可能覆盖手填的容量、功率、效率、放电深度及损耗参数。';if(key.endsWith('_storage'))return '开启后，在创建 CityLearn 仿真环境时，根据所选数据的最大冷热或热水需求估算储能容量，覆盖手填容量。';return '开启后，在创建 CityLearn 仿真环境时，根据所选数据的需求估算额定输入功率，覆盖手填额定功率。热泵还会结合室外温度与 COP 计算。'},
    safetyHelp(key){if(key==='electrical_storage')return '用于放大目标储能容量。1 表示不额外放大，1.2 表示目标增加 20%；实际结果还取决于电池型号和数量，可能不是精确倍数。留空默认 1。';if(key.endsWith('_storage'))return '容量目标 = 最大单步热需求 × 安全系数。1 表示一倍，1.2 表示放大 20%。小于 1 会缩小容量；留空时 CityLearn 会按随机种子在 1–2 之间取值。';return '额定功率 = 估算需求功率 × 安全系数。例如需要 10 kW，填写 1.2 得到约 12 kW。1 表示不额外放大；小于 1 可能无法覆盖峰值需求。留空默认 1。'},
    toggle(device,enabled){const next=clone(this.value);if(enabled){let template=this.deviceDrafts[device.key]||this.templates[device.key];if(!template&&device.key==='heating_device')template=this.templates.cooling_device;if(!template&&device.key.endsWith('_storage'))template={type:'citylearn.energy_model.StorageTank',autosize:false,attributes:{capacity:1,efficiency:0.9,loss_coefficient:0.006,initial_soc:0}};next[device.key]=clone(template);if(!this.openPanels.includes(device.key))this.openPanels.push(device.key)}else{this.$set(this.deviceDrafts,device.key,clone(next[device.key]));delete next[device.key]}this.$emit('input',next)},
    setAttribute(device,key,value){const next=clone(this.value);if(value===undefined||value===null)delete next[device].attributes[key];else next[device].attributes[key]=value;this.$emit('input',next)},
    setDevice(device,key,value){const next=clone(this.value);next[device][key]=value;this.$emit('input',next)},
    setSizing(device,value){const next=clone(this.value);next[device].autosize_attributes=value==null?{}:{safety_factor:value};this.$emit('input',next)},
    configuration(){const next=clone(this.value);if(!next.electrical_storage)return next;this.curves.forEach(curve=>{const text=(this.curveText[curve.key]||'').trim();if(text){try{next.electrical_storage.attributes[curve.key]=JSON.parse(text)}catch(_){throw Error(curve.label+'：请输入有效 JSON 数组')}}else delete next.electrical_storage.attributes[curve.key]});return next}
  }
}
</script>

<style scoped>
.equipment-editor{min-width:0}.equipment-editor h3{font-size:16px;margin:8px 0 16px}.device-toggles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px;margin-bottom:20px}.device-toggle{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;padding:8px 0;border-bottom:1px solid var(--divider-color);font-size:13px}.device-toggle span{overflow-wrap:anywhere}.device-toggle .el-switch{flex-shrink:0}.parameter-help{font-size:12px;line-height:1.7;color:var(--secondary-text-color);margin:8px 0 0;overflow-wrap:anywhere}.schema-key{margin-left:12px;color:var(--secondary-text-color);font-size:12px;overflow-wrap:anywhere}.device-type{font-size:12px;color:var(--secondary-text-color);margin:0 0 16px;overflow-wrap:anywhere}.device-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px}.attribute-key{display:block;color:var(--secondary-text-color);font-size:11px;line-height:16px;margin-bottom:6px;overflow-wrap:anywhere}.el-input-number{width:100%}.equipment-editor /deep/ .el-collapse-item__header{height:auto;min-height:48px;line-height:22px;padding:8px 0}.equipment-editor /deep/ .el-collapse-item__content{padding-top:14px}@media(max-width:680px){.device-fields{grid-template-columns:1fr}.schema-key{margin-left:8px}}
</style>
