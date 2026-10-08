/** 首页 / more-info 可点传感器定义 */
export const HOME_SENSORS = {
  temperature: {
    key: 'temperature',
    field: 'outdoor_dry_bulb_temperature',
    name: '室外温度',
    entityId: 'sensor.outdoor_dry_bulb_temperature',
    unit: '°C',
    digits: 1,
    icon: 'thermometer',
    color: '#FF9800',
    bg: 'rgba(255,152,0,0.12)',
    chartColor: '#FF9800'
  },
  humidity: {
    key: 'humidity',
    field: 'outdoor_relative_humidity',
    name: '室外湿度',
    entityId: 'sensor.outdoor_relative_humidity',
    unit: '%',
    digits: 0,
    icon: 'waterPercent',
    color: '#00BCD4',
    bg: 'rgba(0,188,212,0.12)',
    chartColor: '#00BCD4'
  },
  pricing: {
    key: 'pricing',
    field: 'electricity_pricing',
    name: '电价',
    entityId: 'sensor.electricity_pricing',
    unit: '$/kWh',
    digits: 2,
    icon: 'currencyUsd',
    color: '#43A047',
    bg: 'rgba(67,160,71,0.12)',
    chartColor: '#43A047',
    group: 'pricing',
    /** 详情图额外曲线 */
    extraSeries: [
      {
        field: 'electricity_pricing_predicted_1',
        name: '6小时预测',
        color: '#81C784'
      },
      {
        field: 'electricity_pricing_predicted_2',
        name: '12小时预测',
        color: '#FFB74D'
      },
      {
        field: 'electricity_pricing_predicted_3',
        name: '24小时预测',
        color: '#64B5F6'
      }
    ]
  },
  carbon: {
    key: 'carbon',
    field: 'carbon_intensity',
    name: '碳排放强度',
    entityId: 'sensor.carbon_intensity',
    unit: 'kgCO₂/kWh',
    digits: 4,
    icon: 'moleculeCo2',
    color: '#8E021B',
    bg: 'rgba(142,2,27,0.10)',
    chartColor: '#8E021B'
  },
  diffuse: {
    key: 'diffuse',
    field: 'diffuse_solar_irradiance',
    name: '散射太阳辐照',
    entityId: 'sensor.diffuse_solar_irradiance',
    unit: 'W/m²',
    digits: 0,
    icon: 'weatherHazy',
    color: '#78909C',
    bg: 'rgba(120,144,156,0.14)',
    chartColor: '#78909C'
  },
  direct: {
    key: 'direct',
    field: 'direct_solar_irradiance',
    name: '直射太阳辐照',
    entityId: 'sensor.direct_solar_irradiance',
    unit: 'W/m²',
    digits: 0,
    icon: 'whiteBalanceSunny',
    color: '#FF9800',
    bg: 'rgba(255,152,0,0.12)',
    chartColor: '#FFB74D'
  },
  indoorTemp: {
    key: 'indoorTemp',
    field: 'indoor_dry_bulb_temperature',
    name: '室内温度',
    entityId: 'sensor.indoor_dry_bulb_temperature',
    unit: '°C',
    digits: 1,
    icon: 'homeThermometer',
    color: '#03A9F4',
    bg: 'rgba(3,169,244,0.12)',
    chartColor: '#03A9F4',
    group: 'building'
  },
  indoorHumidity: {
    key: 'indoorHumidity',
    field: 'indoor_relative_humidity',
    name: '室内湿度',
    entityId: 'sensor.indoor_relative_humidity',
    unit: '%',
    digits: 0,
    icon: 'waterPercent',
    color: '#26C6DA',
    bg: 'rgba(38,198,218,0.12)',
    chartColor: '#26C6DA',
    group: 'building'
  },
  coolSetpoint: {
    key: 'coolSetpoint',
    field: 'indoor_dry_bulb_temperature_cooling_set_point',
    name: '制冷设定温度',
    entityId: 'sensor.cooling_set_point',
    unit: '°C',
    digits: 1,
    icon: 'snowflake',
    color: '#42A5F5',
    bg: 'rgba(66,165,245,0.12)',
    chartColor: '#42A5F5',
    group: 'building'
  },
  heatSetpoint: {
    key: 'heatSetpoint',
    field: 'indoor_dry_bulb_temperature_heating_set_point',
    name: '供暖设定温度',
    entityId: 'sensor.heating_set_point',
    unit: '°C',
    digits: 1,
    icon: 'fire',
    color: '#EF5350',
    bg: 'rgba(239,83,80,0.12)',
    chartColor: '#EF5350',
    group: 'building'
  },
  occupants: {
    key: 'occupants',
    field: 'occupant_count',
    name: '建筑内人数',
    entityId: 'sensor.occupant_count',
    unit: '人',
    digits: 0,
    icon: 'accountGroup',
    color: '#7E57C2',
    bg: 'rgba(126,87,194,0.12)',
    chartColor: '#7E57C2',
    group: 'building'
  },
  solarGeneration: {
    key: 'solarGeneration',
    field: 'solar_generation',
    name: '光伏发电量',
    entityId: 'sensor.solar_generation',
    unit: 'W/kW',
    digits: 1,
    icon: 'solarPower',
    color: '#FF9800',
    bg: 'rgba(255,152,0,0.12)',
    chartColor: '#FF9800',
    group: 'building'
  },
  hvacMode: {
    key: 'hvacMode',
    field: 'hvac_mode',
    name: '空调模式',
    entityId: 'sensor.hvac_mode',
    unit: '',
    digits: 0,
    icon: 'airConditioner',
    color: '#5C6BC0',
    bg: 'rgba(92,107,192,0.12)',
    chartColor: '#5C6BC0',
    group: 'hvac',
    format: 'hvacMode'
  },
  coolingDemand: {
    key: 'coolingDemand',
    field: 'cooling_demand',
    name: '制冷负荷',
    entityId: 'sensor.cooling_demand',
    unit: 'kWh',
    digits: 2,
    icon: 'snowflake',
    color: '#42A5F5',
    bg: 'rgba(66,165,245,0.12)',
    chartColor: '#42A5F5',
    group: 'hvac'
  },
  heatingDemand: {
    key: 'heatingDemand',
    field: 'heating_demand',
    name: '供暖负荷',
    entityId: 'sensor.heating_demand',
    unit: 'kWh',
    digits: 2,
    icon: 'fire',
    color: '#EF5350',
    bg: 'rgba(239,83,80,0.12)',
    chartColor: '#EF5350',
    group: 'hvac'
  },
  actionDhw: {
    key: 'actionDhw',
    field: 'action_dhw_final',
    name: '热水动作 DHW',
    entityId: 'action.dhw_final',
    unit: '',
    digits: 3,
    icon: 'waterBoiler',
    color: '#5470C6',
    bg: 'rgba(84,112,198,0.12)',
    chartColor: '#5470C6',
    group: 'action'
  },
  actionEle: {
    key: 'actionEle',
    field: 'action_ele_final',
    name: '电池动作 ELE',
    entityId: 'action.ele_final',
    unit: '',
    digits: 3,
    icon: 'battery',
    color: '#4DB6AC',
    bg: 'rgba(77,182,172,0.12)',
    chartColor: '#4DB6AC',
    group: 'action'
  },
  actionTmp: {
    key: 'actionTmp',
    field: 'action_tmp_final',
    name: '冷机动作 TMP',
    entityId: 'action.tmp_final',
    unit: '',
    digits: 3,
    icon: 'airConditioner',
    color: '#42A5F5',
    bg: 'rgba(66,165,245,0.12)',
    chartColor: '#42A5F5',
    group: 'action'
  }
}

export const HOME_SENSOR_KEYS = Object.keys(HOME_SENSORS)

/** 建筑侧实体卡 */
export const BUILDING_SENSOR_KEYS = [
  'indoorTemp',
  'coolSetpoint',
  'heatSetpoint',
  'occupants',
  'solarGeneration'
]

/** HVAC 状态 / 冷热负荷 */
export const HVAC_SENSOR_KEYS = ['hvacMode', 'coolingDemand', 'heatingDemand']

/** CHESCA 最终动作卡 */
export const ACTION_SENSOR_KEYS = ['actionDhw', 'actionEle', 'actionTmp']

export const HVAC_MODE_LABELS = {
  0: '关闭',
  1: '制冷',
  2: '供暖'
}

export function formatSensorValue(sensor, value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  if (sensor.format === 'hvacMode') {
    const key = Math.round(n)
    return HVAC_MODE_LABELS[key] != null ? HVAC_MODE_LABELS[key] : String(key)
  }
  if (sensor.digits === 0) return String(Math.round(n))
  return n.toFixed(sensor.digits)
}
