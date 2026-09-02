import dayjs from 'dayjs'

const DEVICE_ATTRS = {
  'citylearn.electric_vehicle_charger.Charger': [
    'nominal_power', 'efficiency', 'charger_type', 'max_charging_power', 'min_charging_power'
  ],
  'citylearn.energy_model.PV': ['nominal_power'],
  'citylearn.energy_model.Battery': ['capacity', 'nominal_power', 'depth_of_discharge']
}

function numify(obj) {
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [k, typeof v === 'string' && v !== '' && !Number.isNaN(Number(v)) ? Number(v) : v])
  )
}

export function buildSchemaExport({
  datasetName,
  siteName,
  formData,
  observations,
  actions,
  agentData,
  rewardFunctionData,
  nodes
}) {
  const configs = {
    ...numify(formData),
    observations: {},
    actions: {},
    agent: agentData,
    reward_function: rewardFunctionData
  }

  Object.keys(observations).forEach((k) => {
    configs.observations[k] = { ...observations[k] }
  })
  Object.keys(actions).forEach((k) => {
    configs.actions[k] = { active: actions[k].active }
  })

  const schema = {
    name: datasetName,
    site_id: siteName,
    citylearn_configs: configs,
    from_ts: dayjs(formData.date_from).format('YYYY-MM-DD HH:mm:ss'),
    until_ts: dayjs(formData.date_until).format('YYYY-MM-DD HH:mm:ss'),
    electric_vehicles_def: {},
    buildings: {}
  }

  const buildingById = {}
  nodes.filter((n) => n.type === 'building').forEach((b) => {
    buildingById[b.id] = b
    schema.buildings[b.label] = {
      include: true,
      energy_simulation: b.formData.energy_simulation,
      weather: b.formData.weather,
      carbon_intensity: b.formData.carbon_intensity || 'carbon_intensity.csv',
      pricing: b.formData.pricing,
      inactive_observations: b.formData.inactive_observations || [],
      inactive_actions: b.formData.inactive_actions || []
    }
  })

  nodes.filter((n) => n.type === 'ev').forEach((ev) => {
    schema.electric_vehicles_def[ev.label] = {
      include: true,
      battery: {
        type: 'citylearn.energy_model.Battery',
        autosize: false,
        attributes: numify(ev.formData)
      }
    }
  })

  nodes
    .filter((n) => n.type !== 'building' && n.type !== 'ev' && n.buildingId)
    .forEach((device) => {
      const building = buildingById[device.buildingId]
      if (!building) return
      const bName = building.label
      const key = device.label.toLowerCase()
      const selectedType = device.formData.selectedType || 'citylearn.energy_model.PV'
      const allowed = DEVICE_ATTRS[selectedType] || ['nominal_power']
      const attributes = numify(
        Object.fromEntries(
          Object.entries(device.formData).filter(([k]) => allowed.includes(k))
        )
      )
      if (!schema.buildings[bName]) return
      schema.buildings[bName][key] = {
        type: selectedType,
        autosize: false,
        attributes
      }
    })

  return schema
}
