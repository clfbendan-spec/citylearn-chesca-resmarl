
import { themeColor } from './theme'
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
    color: themeColor('energy-solar-color'),
    bg: 'rgba(255,152,0,0.12)',
    chartColor: themeColor('energy-solar-color')
  },
  humidity: {
    key: 'humidity',
    field: 'outdoor_relative_humidity',
    name: '室外湿度',
    entityId: 'sensor.outdoor_relative_humidity',
    unit: '%',
    digits: 0,
    icon: 'waterPercent',
    color: themeColor('energy-water-color'),
    bg: 'rgba(0,188,212,0.12)',
    chartColor: themeColor('energy-water-color')
  },
  pricing: {
    key: 'pricing',
    field: 'electricity_pricing',
    name: '电价',
    entityId: 'sensor.electricity_pricing',
    unit: '$/kWh',
    digits: 2,
    icon: 'currencyUsd',
    color: themeColor('success-color'),
    bg: 'rgba(67,160,71,0.12)',
    chartColor: themeColor('success-color'),
    group: 'pricing',
    /** 详情图额外曲线 */
    extraSeries: [
      {
        field: 'electricity_pricing_predicted_1',
        name: '6小时预测',
        color: themeColor('energy-battery-in-color')
      },
      {
        field: 'electricity_pricing_predicted_2',
        name: '12小时预测',
        color: themeColor('accent-color')
      },
      {
        field: 'electricity_pricing_predicted_3',
        name: '24小时预测',
        color: themeColor('light-primary-color')
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
    color: themeColor('energy-gas-color'),
    bg: 'rgba(142,2,27,0.10)',
    chartColor: themeColor('energy-gas-color')
  },
  diffuse: {
    key: 'diffuse',
    field: 'diffuse_solar_irradiance',
    name: '散射太阳辐照',
    entityId: 'sensor.diffuse_solar_irradiance',
    unit: 'W/m²',
    digits: 0,
    icon: 'weatherHazy',
    color: themeColor('secondary-text-color'),
    bg: 'rgba(120,144,156,0.14)',
    chartColor: themeColor('secondary-text-color')
  },
  direct: {
    key: 'direct',
    field: 'direct_solar_irradiance',
    name: '直射太阳辐照',
    entityId: 'sensor.direct_solar_irradiance',
    unit: 'W/m²',
    digits: 0,
    icon: 'whiteBalanceSunny',
    color: themeColor('energy-solar-color'),
    bg: 'rgba(255,152,0,0.12)',
    chartColor: themeColor('accent-color')
  },
  indoorTemp: {
    key: 'indoorTemp',
    field: 'indoor_dry_bulb_temperature',
    name: '室内温度',
    entityId: 'sensor.indoor_dry_bulb_temperature',
    unit: '°C',
    digits: 1,
    icon: 'homeThermometer',
    color: themeColor('primary-color'),
    bg: 'rgba(3,169,244,0.12)',
    chartColor: themeColor('primary-color'),
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
    color: themeColor('energy-water-color'),
    bg: 'rgba(38,198,218,0.12)',
    chartColor: themeColor('energy-water-color'),
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
    color: themeColor('primary-color'),
    bg: 'rgba(66,165,245,0.12)',
    chartColor: themeColor('primary-color'),
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
    color: themeColor('error-color'),
    bg: 'rgba(239,83,80,0.12)',
    chartColor: themeColor('error-color'),
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
    color: themeColor('energy-grid-return-color'),
    bg: 'rgba(126,87,194,0.12)',
    chartColor: themeColor('energy-grid-return-color'),
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
    color: themeColor('energy-solar-color'),
    bg: 'rgba(255,152,0,0.12)',
    chartColor: themeColor('energy-solar-color'),
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
    color: themeColor('secondary-text-color'),
    bg: 'rgba(92,107,192,0.12)',
    chartColor: themeColor('secondary-text-color'),
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
    color: themeColor('primary-color'),
    bg: 'rgba(66,165,245,0.12)',
    chartColor: themeColor('primary-color'),
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
    color: themeColor('error-color'),
    bg: 'rgba(239,83,80,0.12)',
    chartColor: themeColor('error-color'),
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
    color: themeColor('energy-water-color'),
    bg: 'rgba(0,188,212,0.12)',
    chartColor: themeColor('energy-water-color'),
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
    color: themeColor('energy-battery-out-color'),
    bg: 'rgba(77,182,172,0.12)',
    chartColor: themeColor('energy-battery-out-color'),
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
    color: themeColor('primary-color'),
    bg: 'rgba(66,165,245,0.12)',
    chartColor: themeColor('primary-color'),
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
