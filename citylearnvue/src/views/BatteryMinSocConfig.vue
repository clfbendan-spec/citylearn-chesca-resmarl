<template>
  <div :class="['battery-min-soc-page', { 'is-embedded': embedded, 'is-readonly': readonly }]">
    <el-card
      v-loading="loading"
      shadow="never"
      :class="['config-card', 'chesca-unified-card', { 'is-collapsed': collapsed }]"
    >
      <div class="panel-title-row">
        <div class="ha-card-title">CHESCA 配置</div>
        <button
          type="button"
          class="card-toggle-btn"
          :title="collapsed ? '展开' : '收起'"
          :aria-label="collapsed ? '展开' : '收起'"
          @click="toggleCollapsed"
        >
          <i :class="collapsed ? 'el-icon-arrow-down' : 'el-icon-arrow-up'" />
        </button>
      </div>

      <div class="card-schema-bar">
        <div class="form-item eval-schema-item">
          <label class="form-label">评估数据集（eval_schema）</label>
          <el-select
            v-model="evalSchema"
            filterable
            allow-create
            default-first-option
            :disabled="readonly"
            placeholder="选择或输入 CityLearn schema"
            class="eval-schema-select"
          >
            <el-option
              v-for="opt in schemaOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
      </div>

      <div v-show="!collapsed" class="card-body">
        <p class="chesca-desc">
          配置 CHESCA 算法如何控制三栋楼的空调（TMP）、电池（ELE）与生活热水（DHW）。
         
          TMP / ELE / DHW 是 CityLearn 的三个动作维：数值越大通常表示空调更制冷、电池更充电、热水更加热。
        </p>

        <div class="chesca-block">



        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">冷机</h3>
            <p class="balance-desc">
              PID 会按室温误差调节空调，但偶尔会「反应偏慢」。开环保底在 PID 之外再加一道「最低制冷」：
              室内已经偏热、或室外很热时，保证空调至少开到一定水平，避免闷热。
              把室外保底系数或冷负荷前馈比例设为 0，即可关掉对应保底项。
            </p>
            <div class="balance-form cool-floor-form">
              <div class="slider-header">
              <label class="form-label">冷机最大削减比例 (TMP_max_reduction_percent)</label>
              <span class="slider-value">{{ tmpMaxReductionPercent }}%</span>
            </div>
            <el-slider
              v-model="tmpMaxReductionPercent"
              :min="0"
              :max="100"
              :step="1"
              :show-tooltip="true"
              :format-tooltip="formatPercentTooltip"
            />
            <p class="field-hint">
              减负荷时空调最多能被砍掉的比例。0% = 保护舒适、不砍空调；100% = 允许把空调几乎关停来保电网。
              默认 0% 偏保守；若更在意削峰，可试 30%～60%。
            </p>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">过热保底系数 (min_cool_per_c_overheat)</label>
              <el-input-number
                v-model="minCoolPerCOverheat"
                :min="0"
                :max="2"
                :step="0.01"
                :precision="3"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                室内比设定温度每高出 1°C，至少按「系数 × 额定制冷功率」要电。
                例：系数 0.12、过热 2°C → 最低约 24% 额定功率的制冷电需求，防止 PID 还没跟上时房间继续升温。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">室外保底系数 (min_cool_per_c_outdoor_gap，0=关)</label>
              <el-input-number
                v-model="minCoolPerCOutdoorGap"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="3"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                按「室外温度 − 室内设定」额外抬一点制冷。室外越热、保底越高；设为 0 则完全关闭室外保底。
                适合炎热午后：即使室内暂时还没过热，也提前开一点空调。
              </p>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">室外死区 °C(outdoor_gap_deadband_c)</label>
              <el-input-number
                v-model="outdoorGapDeadbandC"
                :min="0"
                :max="30"
                :step="0.5"
                :precision="1"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                只有「室外 − 设定」超过死区才启用室外保底。例：设定 24°C、死区 5°C，则室外 ≥29°C 才开始加室外保底，避免误开空调。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">室外保底最大过热阈值 °C(outdoor_floor_max_overheat_c)</label>
              <el-input-number
                v-model="outdoorFloorMaxOverheatC"
                :min="0"
                :max="10"
                :step="0.1"
                :precision="2"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                仅当室内过热还「不太严重」（0 ≤ 过热 &lt; 该值）时叠加室外保底。
                例：阈值 0.5°C —— 过热已到 1°C 时，过热保底/PID 已够用，不再叠加室外项，避免双重加码浪费电。
              </p>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">冷负荷前馈比例 (cooling_demand_feedforward_frac，0=关)</label>
              <el-input-number
                v-model="coolingDemandFeedforwardFrac"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                例：比例 0.1 表示至少按冷负荷的 10% 要电。
                设为 0 关闭。可理解为：不等 PID 慢慢纠偏，先按负荷预报预开一点空调。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">前馈仅过热时启用 (demand_feedforward_only_when_overheat)</label>
              <el-switch v-model="demandFeedforwardOnlyWhenOverheat" />
              <p class="field-hint">
                开启：只有室内已经过热才用冷负荷前馈。关闭：室温刚贴设定时也能预开空调，舒适更稳，略费电。
              </p>
            </div>
          </div>
          <div class="form-row-3">
            <div class="form-item">
              <label class="form-label">室外保底允许低于设定 (outdoor_floor_allow_when_under_setpoint)</label>
              <el-switch v-model="outdoorFloorAllowWhenUnderSetpoint" />
              <p class="field-hint">
                开启：即使室内比设定还凉一点（过热&lt;0），只要室外很热，仍可按室外温差保底预冷。
                关闭：室内已低于设定时不再加室外保底。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">低于设定清掉开环保底 (clear_open_loop_floor_when_under_setpoint)</label>
              <el-switch v-model="clearOpenLoopFloorWhenUnderSetpoint" />
              <p class="field-hint">
                开启后：室内低于设定时，清空室外保底与冷负荷前馈，只留 PID。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">PID 使用滞后动力学室温 (use_lagged_dynamics_indoor)</label>
              <el-switch v-model="useLaggedDynamicsIndoor" />
              <p class="field-hint">
                开启：PID 用「上一拍已落地」的室内温（indoor[-2]），与建筑动力学/LSTM 状态对齐，减少「看错温度」导致的震荡。
                关闭：用更新的观测温，反应更快但可能和仿真内部状态略错位。
              </p>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">仅当滞后室温更热时启用 (lagged_indoor_only_when_hotter)</label>
              <el-switch v-model="laggedIndoorOnlyWhenHotter" />
              <p class="field-hint">
                开启：只有滞后室温比最新观测更热、且温差超过下面裕度时，才改用滞后温（偏保守防闷热）。
                关闭：只要总开关打开就始终用滞后温。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">滞后更热裕度 (lagged_indoor_hotter_margin_c，°C)</label>
              <el-input-number
                v-model="laggedIndoorHotterMarginC"
                :min="0"
                :max="10"
                :step="0.1"
                :precision="2"
                :disabled="!laggedIndoorOnlyWhenHotter"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                例：裕度 0.3°C —— 滞后温要比最新观测至少高 0.3°C 才切换，过滤噪声。
              </p>
            </div>
          </div>
            </div>
          </div>
        </div>
        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">电力恢复时 TMP 功率帽</h3>

            <div class="balance-form cool-floor-form">
          <div class="form-item">
            <label class="form-label">TMP 功率帽 (post_outage_tmp_cap_enabled)</label>
            <el-switch v-model="postOutageTmpCapEnabled" />
            <p class="field-hint">
              停电刚恢复时室内往往很热，PID 容易把三栋楼空调一步拉满（TMP≈1.0），造成用电高峰。开启时电力恢复后一段时间内限制空调功率。关闭：电力恢复第一步就可满功率制冷，舒适快但耗电大。
            </p>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">TMP 功率帽窗口步数 (post_outage_tmp_cap_steps)</label>
              <el-input-number
                v-model="postOutageTmpCapSteps"
                :min="0"
                :max="48"
                :step="1"
                :disabled="!postOutageTmpCapEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                限制持续多少个仿真步（约等于小时步）。例：4 步表示复电后约 4 小时内逐步放开。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">首步 TMP 上限 (post_outage_tmp_max_start)</label>
              <el-input-number
                v-model="postOutageTmpMaxStart"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!postOutageTmpCapEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                电力恢复那一步允许的最大 TMP。0.40 ≈ 最多开到满功率的 40%。越小尖峰越低，但室内降温更慢。
              </p>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">线性爬升到满功率 (post_outage_tmp_ramp)</label>
              <el-switch
                v-model="postOutageTmpRamp"
                :disabled="!postOutageTmpCapEnabled"
              />
              <p class="field-hint">
                开启：最大MP从「首步上限」线性升到 1.0（如 0.4→0.6→0.8→1.0）。关闭：维持首步上限，结束限制步数才解除限制。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">分栋错峰 (post_outage_tmp_stagger)</label>
              <el-switch
                v-model="postOutageTmpStagger"
                :disabled="!postOutageTmpCapEnabled"
              />
              <p class="field-hint">
                开启：Building0 先爬坡，Building1 / Building2 各再晚 1 步，避免三栋同时拉满。类似错峰用电。
              </p>
            </div>
          </div>
            </div>
          </div>
        </div>
        </div>

        <div class="chesca-block">

        <div class="config-section">
<div class="config-layout">
        <aside class="config-panel">
          <h3 class="section-heading">SOC 参数配置</h3>
          <p class="field-hint soc-panel-intro">
            SOC = 电池剩余电量百分比。
          </p>

          <div class="form-section">
            <div class="section-title">全局上限</div>
            <div class="form-row-3">
              <div class="form-item">
                <label class="form-label">正常时段 SOC 上限%(max_soc_normal)</label>
                <div class="soc-input-row">
                  <el-input-number
                    v-model="maxSocNormalPercent"
                    :min="0"
                    :max="100"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    class="percent-input"
                  />
                </div>
                <p class="field-hint">电网正常时电池最多充到多少。例：99% 几乎可充满，减少过充风险。</p>
              </div>
              <div class="form-item">
                <label class="form-label">停电时段 SOC 上限% (max_soc_outage)</label>
                <div class="soc-input-row">
                  <el-input-number
                    v-model="maxSocOutagePercent"
                    :min="0"
                    :max="100"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    class="percent-input"
                  />

                </div>
                <p class="field-hint">
                  停电期间允许的 SOC 上限，通常低于正常上限。
                </p>
              </div>
              <div class="form-item">
                <label class="form-label">停电 SOC 最大降幅% (max_soc_reduction_in_outage)</label>
                <div class="soc-input-row">
                  <el-input-number
                    v-model="maxSocReductionInOutagePercent"
                    :min="0"
                    :max="100"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    class="percent-input"
                  />
                  
                </div>
                <p class="field-hint">
                  停电期间相对停电前，允许下降多少电。限制「一口气把电放光」。
                </p>
              </div>
            </div>
          </div>

          <div class="form-section">
            <div class="section-title">小时下限</div>
            <div class="form-row-2">
              <div class="form-item">
                <label class="form-label">选择时段</label>
                <el-select
                  v-model="selectedHour"
                  placeholder="请选择小时"
                  class="hour-select"
                  filterable
                >
                  <el-option
                    v-for="row in hourRows"
                    :key="row.hour"
                    :label="row.hourLabel"
                    :value="row.hour"
                  />
                </el-select>
                <p class="field-hint">可选时段后改 SOC 下限，也可直接点下方柱状图切换时段。</p>
              </div>
              <div class="form-item">
                <label class="form-label">电池 SOC 下限</label>
                <div class="soc-input-row">
                  <el-input-number
                    v-model="currentMinSocPercent"
                    :min="0"
                    :max="100"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    class="percent-input"
                  />

                </div>
                <p class="field-hint">
                  该小时电池「尽量不要低于」的电量。例：傍晚高峰设 70%，算法会倾向提前充电，高峰时还能放电支援。
                </p>
              </div>
            </div>
          </div>

        </aside>

        <section class="chart-panel">
          <div class="chart-header">
            <span class="chart-title">24 小时 SOC 下限柱状图</span>
           
          </div>
          <div ref="chart" class="soc-chart"></div>
        </section>
      </div>
        </div>
        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">电力恢复后缓充</h3>
            <div class="balance-form cool-floor-form">
          <div class="form-item">
            <label class="form-label">电力恢复后缓充 (post_outage_soft_charge_enabled)</label>
            <el-switch v-model="postOutageSoftChargeEnabled" />
            <p class="field-hint">停电刚恢复时 SOC 往往很低；若不加限制，负荷会过大。电力恢复后几步内，可以限制每步充电量、过热时优先把电留给空调。关闭后下列规则不生效。</p>
          </div>
          <div class="form-item">
            <label class="form-label">缓充窗口步数 (post_outage_relax_steps)</label>
            <el-input-number
              v-model="postOutageRelaxSteps"
              :min="0"
              :max="48"
              :step="1"
              :disabled="!postOutageSoftChargeEnabled"
              controls-position="right"
              class="number-input"
            />
            <p class="field-hint">
              复电后连续多少步生效（含刚复电的第 0 步）。例：4 ≈ 复电后约 4 小时内都按缓充规则。
            </p>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">避免SOC强制充电 (post_outage_waive_min_soc)</label>
              <el-switch
                v-model="postOutageWaiveMinSoc"
                :disabled="!postOutageSoftChargeEnabled"
              />
              <p class="field-hint">
                开启：强制把 SOC 充电到该小时下限，避免用电高峰。
                关闭：仍会按小时下限充电，用电峰值更大。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">ELE 充电上限 (post_outage_max_ele_charge)</label>
              <el-input-number
                v-model="postOutageMaxEleCharge"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!postOutageSoftChargeEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                每一步最多充多少（相对 SOC）。0.15 ≈ 每步最多充约 15% 电量。
              </p>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">过热时禁止充电 (post_outage_forbid_charge_when_overheat)</label>
              <el-switch
                v-model="postOutageForbidChargeWhenOverheat"
                :disabled="!postOutageSoftChargeEnabled"
              />
              <p class="field-hint">
                室内过热超过阈值时强制 ELE≤0（只许放电或不动作），把电力优先留给制冷。。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">过热阈值 (post_outage_overheat_c)</label>
              <el-input-number
                v-model="postOutageOverheatC"
                :min="0"
                :max="20"
                :step="0.1"
                :precision="2"
                :disabled="!postOutageSoftChargeEnabled || !postOutageForbidChargeWhenOverheat"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                室内比设定高出多少过热禁止充电。
              </p>
            </div>
          </div>
            </div>
          </div>
        </div>
        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">电价感知电池</h3>
            <div class="balance-form cool-floor-form">
          <div class="form-item">
            <label class="form-label">电价感知 (price_aware_battery_enabled)</label>
            <el-switch v-model="priceAwareBatteryEnabled" />
            <p class="field-hint">用最近一段时间的电价分布判断「现在贵不贵」：贵则少充、便宜则多充电。关闭后下面高/低价规则不生效（韧性地板若单独开启仍可能约束放电）。</p>
          </div>
          <div class="form-row-3">
            <div class="form-item">
              <label class="form-label">高价分位数 (price_high_quantile)</label>
              <el-input-number
                v-model="priceHighQuantile"
                :min="0.5"
                :max="0.99"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                当前电价 ≥ 历史该分位数 → 判为高价。0.75 = 贵过历史上约 75% 的时刻才算贵。越大越难触发高价策略。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">低价分位数 (price_low_quantile)</label>
              <el-input-number
                v-model="priceLowQuantile"
                :min="0.01"
                :max="0.5"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                当前电价 ≤ 历史该分位数 → 判为低价。0.25 = 便宜到历史上约 25% 分位才算便宜。越小越难触发低价补电。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">电价历史最少步数 (price_history_min_steps)</label>
              <el-input-number
                v-model="priceHistoryMinSteps"
                :min="8"
                :max="720"
                :step="8"
                :disabled="!priceAwareBatteryEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                至少攒够多少步电价样本才开始判高/低价。例：48 ≈ 两天（按小时步）。太小易误判，太大则前期长时间策略不生效。
              </p>
            </div>
          </div>
          <div class="form-item">
            <label class="form-label">高价禁止充电 (price_high_forbid_charge)</label>
            <el-switch
              v-model="priceHighForbidCharge"
              :disabled="!priceAwareBatteryEnabled"
            />
            <p class="field-hint">开启后高价时段禁止充电（ELE≤0）。避免电价高时还充电。</p>
          </div>
          <div class="form-item">
            <label class="form-label">高价强制放电 (price_high_force_discharge)</label>
            <el-switch
              v-model="priceHighForceDischarge"
              :disabled="!priceAwareBatteryEnabled"
            />
            <p class="field-hint">开启后，在高价且 SOC 够高时主动放电，用电池电顶替买电，降低电费与净负荷。</p>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">高价强放 SOC 阈值 (price_high_soc_threshold)</label>
              <el-input-number
                v-model="priceHighSocThreshold"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled || !priceHighForceDischarge"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                高价且 SOC ≥ 该值时才强制放电。例：0.70 = 电量至少七成才卖电，避免电价贵却把电池放空。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">强制放电幅度 (price_high_discharge_ele)</label>
              <el-input-number
                v-model="priceHighDischargeEle"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled || !priceHighForceDischarge"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                高价强制放电时每步放多少。例：0.15 ≈ 每步大约放出 15% SOC。
              </p>
            </div>
          </div>
          
          <div class="form-item">
            <label class="form-label">全局韧性地板 (price_global_reserve_enabled)</label>
            <el-switch v-model="priceGlobalReserveEnabled" />
            <p class="field-hint">
              开启：中/高/低价放电都受韧性地板约束，树搜索的 SOC 下限也会抬到地板以上。
              关闭：中价放电不起效，树搜索的 SOC 下限不会抬到地板以上。
            </p>
          </div>
          <div class="form-item">
            <label class="form-label">韧性地板 SOC (price_min_reserve_soc)</label>
            <el-input-number
              v-model="priceMinReserveSoc"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              :disabled="!priceAwareBatteryEnabled && !priceGlobalReserveEnabled"
              controls-position="right"
              class="number-input"
            />
            <p class="field-hint">
              非停电时放电不得低于此 SOC，为下次停电留「应急电」。例：0.55 = 平时至少留一半电。停电时仍可放到硬件允许深度。
            </p>
          </div>
          <div class="form-row-2">
            <div class="form-item">
              <label class="form-label">低价补电目标 SOC (price_low_target_soc)</label>
              <el-input-number
                v-model="priceLowTargetSoc"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                低价时希望把 SOC 补到的目标。例：0.80 = 便宜电时尽量充到八成，为高峰放电做准备。
              </p>
            </div>
            <div class="form-item">
              <label class="form-label">低价补电幅度 (price_low_charge_ele)</label>
              <el-input-number
                v-model="priceLowChargeEle"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
                :disabled="!priceAwareBatteryEnabled"
                controls-position="right"
                class="number-input"
              />
              <p class="field-hint">
                低价时每步建议充电幅度。默认 0.25；若当前已低于韧性地板，会优先先补回到地板。
              </p>
            </div>
          </div>
          <div class="form-item">
            <label class="form-label">低价树搜索促补电 (price_low_search_boost)</label>
            <el-switch
              v-model="priceLowSearchBoost"
              :disabled="!priceAwareBatteryEnabled"
            />
            <p class="field-hint">
              开启：低价时抬高树搜索的 SOC 下限，促使一步充到「当前 SOC + 补电幅度」，让搜索更积极地抓住便宜电。
            </p>
          </div>
            </div>
          </div>
        </div>
        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">电池树搜索适应度类型 (balance_type)</h3>
            <p class="balance-desc">
              在多种充放电候选里，选「代价」最小的那一个。
              balance_type 决定「什么叫好」。
            </p>
            <div class="form-item narrow-select-item">
              <el-select v-model="balanceType" placeholder="请选择 balance_type" class="hour-select">
                <el-option
                  v-for="option in balanceTypeOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>
        <div class="balance-type-notes">
          <div
            v-for="option in balanceTypeOptions"
            v-show="balanceType === option.value"
            :key="option.value"
            class="type-note active"
          >
            <div class="type-note-title">{{ option.label }}</div>
            <p class="type-note-desc">{{ option.desc }}</p>
            <p class="type-note-effect"><strong>效果：</strong>{{ option.effect }}</p>
          </div>
        </div>
          </div>
        </div>
        </div>

        <div class="chesca-block">
        <div class="config-section">
          <div class="balance-panel">
            <h3 class="section-heading">负荷阈值（B_low / B_high）</h3>
            <p class="balance-desc">
              算法持续估计社区净负荷的均值与波动（标准差 σ）。
              当净负荷低于「均值 − B_low × σ」时，认为用电偏低，增加 DHW。
              当净负荷高于「均值 + B_high × σ」时，认为用电偏高，削减 DHW，再按「冷机最大削减比例」下调 TMP。
            </p>
            <div class="balance-form">
              <div class="form-item">
                <label class="form-label">B_low</label>
                <el-input-number
                  v-model="bLow"
                  :min="0.01"
                  :max="20"
                  :step="0.01"
                  :precision="2"
                  controls-position="right"
                  class="number-input"
                />
                <p class="field-hint">
                  B_low越大 越懒：要掉得更低才加热水箱。
                </p>
              </div>
              <div class="form-item">
                <label class="form-label">B_high</label>
                <el-input-number
                  v-model="bHigh"
                  :min="0.01"
                  :max="20"
                  :step="0.01"
                  :precision="2"
                  controls-position="right"
                  class="number-input"
                />
                <p class="field-hint">
                  B_high越大 敏感度越低：要冲得更高才减少负荷。
                </p>
              </div>
            </div>
          </div>
        </div>
        </div>

        <div class="chesca-block">
        <div class="config-section">
          <div class="balance-panel tau-panel">
            <h3 class="section-heading">预测步长 (tau)</h3>
            <div class="form-item tau-form-item">
              <el-select v-model="tau" placeholder="请选择 tau" class="hour-select">
                <el-option
                  v-for="option in tauOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <p class="field-hint tau-desc">
                tau = 时序预测与电池树搜索「向前看」的步数，tau越高，计划更远但计算更重、对预测误差也更敏感。
              </p>
            </div>
          </div>
        </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import axios from 'axios'
import * as echarts from 'echarts'

const DEFAULT_MAX_SOC_NORMAL_PERCENT = 99
const DEFAULT_MAX_SOC_OUTAGE_PERCENT = 87
const DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE_PERCENT = 70
const DEFAULT_B_LOW = 1.18
const DEFAULT_B_HIGH = 1.0
const DEFAULT_TMP_MAX_REDUCTION_PERCENT = 0
const DEFAULT_MIN_COOL_PER_C_OVERHEAT = 0.12
const DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP = 0.03
const DEFAULT_OUTDOOR_GAP_DEADBAND_C = 5.0
const DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C = 0.5
const DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC = 0.1
const DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT = false
const DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT = true
const DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT = false
const DEFAULT_USE_LAGGED_DYNAMICS_INDOOR = true
const DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER = false
const DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C = 0.3
const DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED = true
const DEFAULT_POST_OUTAGE_RELAX_STEPS = 4
const DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC = true
const DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE = 0.15
const DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT = true
const DEFAULT_POST_OUTAGE_OVERHEAT_C = 0.5
const DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED = true
const DEFAULT_POST_OUTAGE_TMP_CAP_STEPS = 4
const DEFAULT_POST_OUTAGE_TMP_MAX_START = 0.4
const DEFAULT_POST_OUTAGE_TMP_RAMP = true
const DEFAULT_POST_OUTAGE_TMP_STAGGER = true
const DEFAULT_PRICE_AWARE_BATTERY_ENABLED = true
const DEFAULT_PRICE_HIGH_QUANTILE = 0.75
const DEFAULT_PRICE_LOW_QUANTILE = 0.25
const DEFAULT_PRICE_HISTORY_MIN_STEPS = 48
const DEFAULT_PRICE_HIGH_SOC_THRESHOLD = 0.7
const DEFAULT_PRICE_HIGH_FORBID_CHARGE = true
const DEFAULT_PRICE_HIGH_FORCE_DISCHARGE = true
const DEFAULT_PRICE_HIGH_DISCHARGE_ELE = 0.15
const DEFAULT_PRICE_MIN_RESERVE_SOC = 0.55
const DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED = true
const DEFAULT_PRICE_LOW_TARGET_SOC = 0.8
const DEFAULT_PRICE_LOW_CHARGE_ELE = 0.25
const DEFAULT_PRICE_LOW_SEARCH_BOOST = true
const DEFAULT_TAU = 1

const TAU_OPTIONS = [
  { value: 1, label: '1 步' },
  { value: 2, label: '2 步' },
  { value: 3, label: '3 步' }
]

const DEFAULT_BALANCE_TYPE = 'C'

const BALANCE_TYPE_OPTIONS = [
  {
    value: 'A',
    label: 'A — 跟踪历史均值',
    desc: '代价 = |历史净负荷均值 − 当前步净负荷|。把「社区长期平均用电」当锚点，尽量让当前净负荷回到平均水平。',
    effect: '更像「回归平均」：适合希望整体负荷围着长期均值转的场景；对相邻小时跳变的惩罚不如 B 直接。'
  },
  {
    value: 'B',
    label: 'B — 抑制步间波动',
    desc: '代价 = |上一步净负荷 − 当前步净负荷|。只看相邻两步差了多少，不直接参照历史均值。',
    effect: '更强调平滑：单步大起大落惩罚更重，有利于爬坡（ramping）指标；但不保证贴近长期平均用电。'
  },
  {
    value: 'C',
    label: 'C — 跟踪均值与预测中点',
    desc: '代价 = |(历史均值 + 预测净负荷) / 2 − 当前步净负荷|。目标取「历史均值」与「下一步预测」的中点。',
    effect: '既顾历史水平，又顾短期预测，更均衡。'
  }
]

/** 0~1 小数 → 百分比整数 */
function ratioToPercent(ratio) {
  return Math.round(Number(ratio) * 100)
}

/** 百分比 → 0~1 小数（保留 4 位，与后端 DECIMAL(6,4) 一致） */
function percentToRatio(percent) {
  return Math.round(Number(percent) * 100) / 10000
}

export default {
  name: 'BatteryMinSocConfig',
  props: {
    /** 嵌入 ResMARL 配置页时隐藏独立页标题与外边距 */
    embedded: {
      type: Boolean,
      default: false
    },
    /** 无操作权限时只读 */
    readonly: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      collapsed: true,
      loading: false,
      saving: false,
      selectedHour: 0,
      maxSocNormalPercent: DEFAULT_MAX_SOC_NORMAL_PERCENT,
      maxSocOutagePercent: DEFAULT_MAX_SOC_OUTAGE_PERCENT,
      maxSocReductionInOutagePercent: DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE_PERCENT,
      bLow: DEFAULT_B_LOW,
      bHigh: DEFAULT_B_HIGH,
      tmpMaxReductionPercent: DEFAULT_TMP_MAX_REDUCTION_PERCENT,
      minCoolPerCOverheat: DEFAULT_MIN_COOL_PER_C_OVERHEAT,
      minCoolPerCOutdoorGap: DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP,
      outdoorGapDeadbandC: DEFAULT_OUTDOOR_GAP_DEADBAND_C,
      outdoorFloorMaxOverheatC: DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C,
      coolingDemandFeedforwardFrac: DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC,
      demandFeedforwardOnlyWhenOverheat: DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT,
      outdoorFloorAllowWhenUnderSetpoint: DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT,
      clearOpenLoopFloorWhenUnderSetpoint: DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT,
      useLaggedDynamicsIndoor: DEFAULT_USE_LAGGED_DYNAMICS_INDOOR,
      laggedIndoorOnlyWhenHotter: DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER,
      laggedIndoorHotterMarginC: DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C,
      postOutageSoftChargeEnabled: DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED,
      postOutageRelaxSteps: DEFAULT_POST_OUTAGE_RELAX_STEPS,
      postOutageWaiveMinSoc: DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC,
      postOutageMaxEleCharge: DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE,
      postOutageForbidChargeWhenOverheat: DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT,
      postOutageOverheatC: DEFAULT_POST_OUTAGE_OVERHEAT_C,
      postOutageTmpCapEnabled: DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED,
      postOutageTmpCapSteps: DEFAULT_POST_OUTAGE_TMP_CAP_STEPS,
      postOutageTmpMaxStart: DEFAULT_POST_OUTAGE_TMP_MAX_START,
      postOutageTmpRamp: DEFAULT_POST_OUTAGE_TMP_RAMP,
      postOutageTmpStagger: DEFAULT_POST_OUTAGE_TMP_STAGGER,
      priceAwareBatteryEnabled: DEFAULT_PRICE_AWARE_BATTERY_ENABLED,
      priceHighQuantile: DEFAULT_PRICE_HIGH_QUANTILE,
      priceLowQuantile: DEFAULT_PRICE_LOW_QUANTILE,
      priceHistoryMinSteps: DEFAULT_PRICE_HISTORY_MIN_STEPS,
      priceHighSocThreshold: DEFAULT_PRICE_HIGH_SOC_THRESHOLD,
      priceHighForbidCharge: DEFAULT_PRICE_HIGH_FORBID_CHARGE,
      priceHighForceDischarge: DEFAULT_PRICE_HIGH_FORCE_DISCHARGE,
      priceHighDischargeEle: DEFAULT_PRICE_HIGH_DISCHARGE_ELE,
      priceMinReserveSoc: DEFAULT_PRICE_MIN_RESERVE_SOC,
      priceGlobalReserveEnabled: DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED,
      priceLowTargetSoc: DEFAULT_PRICE_LOW_TARGET_SOC,
      priceLowChargeEle: DEFAULT_PRICE_LOW_CHARGE_ELE,
      priceLowSearchBoost: DEFAULT_PRICE_LOW_SEARCH_BOOST,
      tau: DEFAULT_TAU,
      tauOptions: TAU_OPTIONS,
      balanceType: DEFAULT_BALANCE_TYPE,
      balanceTypeOptions: BALANCE_TYPE_OPTIONS,
      evalSchema: 'citylearn_challenge_2023_phase_2_online_evaluation_1',
      schemaOptions: [],
      hourRows: [],
      chart: null,
      resizeObserver: null
    }
  },
  computed: {
    currentRow() {
      return this.hourRows.find((row) => row.hour === this.selectedHour) || this.hourRows[0]
    },
    currentMinSocPercent: {
      get() {
        return this.currentRow ? this.currentRow.minSocPercent : 60
      },
      set(value) {
        if (this.currentRow) {
          this.currentRow.minSocPercent = value
        }
      }
    },
    currentHourLabel() {
      return this.currentRow ? this.currentRow.hourLabel : ''
    }
  },
  watch: {
    hourRows: {
      deep: true,
      handler() {
        this.renderChart()
      }
    },
    selectedHour(val) {
      if (typeof val === 'string') {
        this.selectedHour = Number(val)
        return
      }
      this.renderChart()
    },
    maxSocNormalPercent() {
      this.renderChart()
    },
    maxSocOutagePercent() {
      this.renderChart()
    }
  },
  created() {
    this.initRows()
    this.loadDatasetOptions().finally(() => this.loadConfig())
  },
  mounted() {
    this.chart = echarts.init(this.$refs.chart)
    this.chart.on('click', this.handleChartClick)
    if (this.$refs.chart) {
      this.$refs.chart.addEventListener('wheel', this.handleChartWheel, { passive: false })
    }
    window.addEventListener('resize', this.handleResize)
    if (typeof ResizeObserver !== 'undefined' && this.$refs.chart) {
      this.resizeObserver = new ResizeObserver(() => this.handleResize())
      this.resizeObserver.observe(this.$refs.chart)
    }
    this.renderChart()
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize)
    if (this.resizeObserver) this.resizeObserver.disconnect()
    if (this.$refs.chart) {
      this.$refs.chart.removeEventListener('wheel', this.handleChartWheel)
    }
    if (this.chart) {
      this.chart.off('click', this.handleChartClick)
      this.chart.dispose()
      this.chart = null
    }
  },
  methods: {
    toggleCollapsed() {
      this.collapsed = !this.collapsed
      if (!this.collapsed) {
        this.$nextTick(() => {
          this.handleResize()
          this.renderChart()
        })
      }
    },
    async loadDatasetOptions() {
      try {
        const response = await axios.get('/api/web/basedata/getDatasetList')
        if (response.data && response.data.code === 0 && Array.isArray(response.data.data)) {
          this.schemaOptions = response.data.data.map((d) => ({
            value: d.schemaKey,
            label: d.displayName,
            chescaCompatible: d.chescaCompatible
          }))
        }
      } catch (e) {
        console.error('加载数据集列表失败', e)
      }
    },
    initRows() {
      this.hourRows = Array.from({ length: 24 }, (_, hour) => ({
        hour,
        hourLabel: `${String(hour).padStart(2, '0')}:00 - ${String(hour).padStart(2, '0')}:59`,
        minSocPercent: 60
      }))
    },
    applyConfig(data) {
      if (!data) return
      if (data.minSocPerHour) {
        this.applyMinSocMap(data.minSocPerHour)
      }
      if (data.maxSocNormal != null) {
        this.maxSocNormalPercent = ratioToPercent(data.maxSocNormal)
      }
      if (data.maxSocOutage != null) {
        this.maxSocOutagePercent = ratioToPercent(data.maxSocOutage)
      }
      if (data.maxSocReductionInOutage != null) {
        this.maxSocReductionInOutagePercent = ratioToPercent(data.maxSocReductionInOutage)
      }
      if (data.bLow != null) {
        this.bLow = Number(data.bLow)
      }
      if (data.bHigh != null) {
        this.bHigh = Number(data.bHigh)
      }
      if (data.tmpMaxReductionPercent != null) {
        this.tmpMaxReductionPercent = ratioToPercent(data.tmpMaxReductionPercent)
      }
      if (data.minCoolPerCOverheat != null) {
        this.minCoolPerCOverheat = Number(data.minCoolPerCOverheat)
      }
      if (data.minCoolPerCOutdoorGap != null) {
        this.minCoolPerCOutdoorGap = Number(data.minCoolPerCOutdoorGap)
      }
      if (data.outdoorGapDeadbandC != null) {
        this.outdoorGapDeadbandC = Number(data.outdoorGapDeadbandC)
      }
      if (data.outdoorFloorMaxOverheatC != null) {
        this.outdoorFloorMaxOverheatC = Number(data.outdoorFloorMaxOverheatC)
      }
      if (data.coolingDemandFeedforwardFrac != null) {
        this.coolingDemandFeedforwardFrac = Number(data.coolingDemandFeedforwardFrac)
      }
      if (data.demandFeedforwardOnlyWhenOverheat != null) {
        this.demandFeedforwardOnlyWhenOverheat = !!data.demandFeedforwardOnlyWhenOverheat
      }
      if (data.outdoorFloorAllowWhenUnderSetpoint != null) {
        this.outdoorFloorAllowWhenUnderSetpoint = !!data.outdoorFloorAllowWhenUnderSetpoint
      }
      if (data.clearOpenLoopFloorWhenUnderSetpoint != null) {
        this.clearOpenLoopFloorWhenUnderSetpoint = !!data.clearOpenLoopFloorWhenUnderSetpoint
      }
      if (data.useLaggedDynamicsIndoor != null) {
        this.useLaggedDynamicsIndoor = !!data.useLaggedDynamicsIndoor
      }
      if (data.laggedIndoorOnlyWhenHotter != null) {
        this.laggedIndoorOnlyWhenHotter = !!data.laggedIndoorOnlyWhenHotter
      }
      if (data.laggedIndoorHotterMarginC != null) {
        this.laggedIndoorHotterMarginC = Number(data.laggedIndoorHotterMarginC)
      }
      if (data.postOutageSoftChargeEnabled != null) {
        this.postOutageSoftChargeEnabled = !!data.postOutageSoftChargeEnabled
      }
      if (data.postOutageRelaxSteps != null) {
        this.postOutageRelaxSteps = Number(data.postOutageRelaxSteps)
      }
      if (data.postOutageWaiveMinSoc != null) {
        this.postOutageWaiveMinSoc = !!data.postOutageWaiveMinSoc
      }
      if (data.postOutageMaxEleCharge != null) {
        this.postOutageMaxEleCharge = Number(data.postOutageMaxEleCharge)
      }
      if (data.postOutageForbidChargeWhenOverheat != null) {
        this.postOutageForbidChargeWhenOverheat = !!data.postOutageForbidChargeWhenOverheat
      }
      if (data.postOutageOverheatC != null) {
        this.postOutageOverheatC = Number(data.postOutageOverheatC)
      }
      if (data.postOutageTmpCapEnabled != null) {
        this.postOutageTmpCapEnabled = !!data.postOutageTmpCapEnabled
      }
      if (data.postOutageTmpCapSteps != null) {
        this.postOutageTmpCapSteps = Number(data.postOutageTmpCapSteps)
      }
      if (data.postOutageTmpMaxStart != null) {
        this.postOutageTmpMaxStart = Number(data.postOutageTmpMaxStart)
      }
      if (data.postOutageTmpRamp != null) {
        this.postOutageTmpRamp = !!data.postOutageTmpRamp
      }
      if (data.postOutageTmpStagger != null) {
        this.postOutageTmpStagger = !!data.postOutageTmpStagger
      }
      if (data.priceAwareBatteryEnabled != null) {
        this.priceAwareBatteryEnabled = !!data.priceAwareBatteryEnabled
      }
      if (data.priceHighQuantile != null) {
        this.priceHighQuantile = Number(data.priceHighQuantile)
      }
      if (data.priceLowQuantile != null) {
        this.priceLowQuantile = Number(data.priceLowQuantile)
      }
      if (data.priceHistoryMinSteps != null) {
        this.priceHistoryMinSteps = Number(data.priceHistoryMinSteps)
      }
      if (data.priceHighSocThreshold != null) {
        this.priceHighSocThreshold = Number(data.priceHighSocThreshold)
      }
      if (data.priceHighForbidCharge != null) {
        this.priceHighForbidCharge = !!data.priceHighForbidCharge
      }
      if (data.priceHighForceDischarge != null) {
        this.priceHighForceDischarge = !!data.priceHighForceDischarge
      }
      if (data.priceHighDischargeEle != null) {
        this.priceHighDischargeEle = Number(data.priceHighDischargeEle)
      }
      if (data.priceMinReserveSoc != null) {
        this.priceMinReserveSoc = Number(data.priceMinReserveSoc)
      }
      if (data.priceGlobalReserveEnabled != null) {
        this.priceGlobalReserveEnabled = !!data.priceGlobalReserveEnabled
      }
      if (data.priceLowTargetSoc != null) {
        this.priceLowTargetSoc = Number(data.priceLowTargetSoc)
      }
      if (data.priceLowChargeEle != null) {
        this.priceLowChargeEle = Number(data.priceLowChargeEle)
      }
      if (data.priceLowSearchBoost != null) {
        this.priceLowSearchBoost = !!data.priceLowSearchBoost
      }
      if (data.tau != null) {
        this.tau = Number(data.tau)
      }
      if (data.balanceType != null) {
        this.balanceType = String(data.balanceType).toUpperCase()
      }
      if (data.evalSchema != null && String(data.evalSchema).trim()) {
        this.evalSchema = String(data.evalSchema).trim()
      }
    },
    applyMinSocMap(configMap) {
      if (!configMap) return
      this.hourRows.forEach((row) => {
        const key = String(row.hour)
        if (Object.prototype.hasOwnProperty.call(configMap, key)) {
          row.minSocPercent = ratioToPercent(configMap[key])
        }
      })
    },
    buildPayload() {
      const minSocPerHour = {}
      this.hourRows.forEach((row) => {
        minSocPerHour[String(row.hour)] = percentToRatio(row.minSocPercent)
      })
      return {
        minSocPerHour,
        maxSocNormal: percentToRatio(this.maxSocNormalPercent),
        maxSocOutage: percentToRatio(this.maxSocOutagePercent),
        maxSocReductionInOutage: percentToRatio(this.maxSocReductionInOutagePercent),
        bLow: this.bLow,
        bHigh: this.bHigh,
        tmpMaxReductionPercent: percentToRatio(this.tmpMaxReductionPercent),
        minCoolPerCOverheat: this.minCoolPerCOverheat,
        minCoolPerCOutdoorGap: this.minCoolPerCOutdoorGap,
        outdoorGapDeadbandC: this.outdoorGapDeadbandC,
        outdoorFloorMaxOverheatC: this.outdoorFloorMaxOverheatC,
        coolingDemandFeedforwardFrac: this.coolingDemandFeedforwardFrac,
        demandFeedforwardOnlyWhenOverheat: this.demandFeedforwardOnlyWhenOverheat,
        outdoorFloorAllowWhenUnderSetpoint: this.outdoorFloorAllowWhenUnderSetpoint,
        clearOpenLoopFloorWhenUnderSetpoint: this.clearOpenLoopFloorWhenUnderSetpoint,
        useLaggedDynamicsIndoor: this.useLaggedDynamicsIndoor,
        laggedIndoorOnlyWhenHotter: this.laggedIndoorOnlyWhenHotter,
        laggedIndoorHotterMarginC: this.laggedIndoorHotterMarginC,
        postOutageSoftChargeEnabled: this.postOutageSoftChargeEnabled,
        postOutageRelaxSteps: this.postOutageRelaxSteps,
        postOutageWaiveMinSoc: this.postOutageWaiveMinSoc,
        postOutageMaxEleCharge: this.postOutageMaxEleCharge,
        postOutageForbidChargeWhenOverheat: this.postOutageForbidChargeWhenOverheat,
        postOutageOverheatC: this.postOutageOverheatC,
        postOutageTmpCapEnabled: this.postOutageTmpCapEnabled,
        postOutageTmpCapSteps: this.postOutageTmpCapSteps,
        postOutageTmpMaxStart: this.postOutageTmpMaxStart,
        postOutageTmpRamp: this.postOutageTmpRamp,
        postOutageTmpStagger: this.postOutageTmpStagger,
        priceAwareBatteryEnabled: this.priceAwareBatteryEnabled,
        priceHighQuantile: this.priceHighQuantile,
        priceLowQuantile: this.priceLowQuantile,
        priceHistoryMinSteps: this.priceHistoryMinSteps,
        priceHighSocThreshold: this.priceHighSocThreshold,
        priceHighForbidCharge: this.priceHighForbidCharge,
        priceHighForceDischarge: this.priceHighForceDischarge,
        priceHighDischargeEle: this.priceHighDischargeEle,
        priceMinReserveSoc: this.priceMinReserveSoc,
        priceGlobalReserveEnabled: this.priceGlobalReserveEnabled,
        priceLowTargetSoc: this.priceLowTargetSoc,
        priceLowChargeEle: this.priceLowChargeEle,
        priceLowSearchBoost: this.priceLowSearchBoost,
        tau: this.tau,
        balanceType: this.balanceType,
        evalSchema: (this.evalSchema || '').trim()
      }
    },
    formatPercentTooltip(value) {
      return `${value}%`
    },
    handleResize() {
      if (this.chart) this.chart.resize()
    },
    handleChartClick(params) {
      if (params == null || params.componentType !== 'series') return
      const hour = Number(params.dataIndex)
      if (!Number.isInteger(hour) || hour < 0 || hour > 23) return
      this.selectedHour = hour
    },
    handleChartWheel(event) {
      if (!this.chart || !this.hourRows.length) return
      const point = [event.offsetX, event.offsetY]
      if (!this.chart.containPixel('grid', point)) return

      const dataCoord = this.chart.convertFromPixel({ seriesIndex: 0 }, point)
      if (!Array.isArray(dataCoord) || dataCoord.length < 2) return

      const hour = Math.round(dataCoord[0])
      if (hour !== Number(this.selectedHour) || hour < 0 || hour > 23) return
      if (Math.abs(dataCoord[0] - hour) > 0.45) return

      const barValue = Number(this.hourRows[hour].minSocPercent)
      const yValue = Number(dataCoord[1])
      if (!(yValue >= 0 && yValue <= barValue)) return

      event.preventDefault()
      const step = event.deltaY < 0 ? 1 : -1
      const next = Math.min(100, Math.max(0, barValue + step))
      if (next !== barValue) {
        this.currentMinSocPercent = next
      }
    },
    renderChart() {
      if (!this.chart || !this.hourRows.length) return

      const hours = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, '0'))
      const values = this.hourRows.map((row) => row.minSocPercent)
      const selectedIndex = Number(this.selectedHour)

      this.chart.setOption({
        animation: true,
        animationDuration: 200,
        grid: {
          left: 48,
          right: 24,
          top: 36,
          bottom: 40
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter(params) {
            const point = Array.isArray(params) ? params[0] : params
            if (!point) return ''
            return `${point.axisValue} 时<br/>SOC 下限：${point.value}%`
          }
        },
        xAxis: {
          type: 'category',
          name: '小时',
          nameLocation: 'middle',
          nameGap: 28,
          data: hours,
          axisLabel: {
            interval: 0
          }
        },
        yAxis: {
          type: 'value',
          name: 'SOC (%)',
          min: 0,
          max: 100,
          splitLine: {
            lineStyle: { type: 'dashed', color: '#e4e7ed' }
          }
        },
        series: [
          {
            name: 'SOC 下限',
            type: 'bar',
            barMaxWidth: 28,
            data: values,
            itemStyle: {
              color: (params) => (params.dataIndex === selectedIndex ? '#FF9800' : '#03A9F4'),
              cursor: 'pointer'
            },
            emphasis: {
              focus: 'self',
              itemStyle: {
                shadowBlur: 6,
                shadowColor: 'rgba(0, 0, 0, 0.18)'
              }
            },
            label: {
              show: true,
              position: 'top',
              formatter: (params) => `${params.value}%`,
              fontSize: 11,
              color: '#727272'
            },
            markLine: {
              symbol: 'none',
              label: {
                formatter: '{b}',
                fontSize: 11
              },
              data: [
                {
                  name: `正常上限 ${this.maxSocNormalPercent}%`,
                  yAxis: this.maxSocNormalPercent,
                  lineStyle: { color: '#43A047', type: 'dashed' }
                },
                {
                  name: `停电上限 ${this.maxSocOutagePercent}%`,
                  yAxis: this.maxSocOutagePercent,
                  lineStyle: { color: '#DB4437', type: 'dashed' }
                }
              ]
            }
          }
        ]
      }, true)
    },
    async loadConfig() {
      this.loading = true
      try {
        const response = await axios.get('/api/web/basedata/getBatteryMinSocConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
        } else {
          this.$message.error((response.data && response.data.message) || '加载配置失败')
        }
      } catch (e) {
        this.$message.error('加载配置失败，请确认已执行 algorithm_config.sql 建表并重启 Java 服务')
      } finally {
        this.loading = false
        this.$nextTick(() => this.renderChart())
      }
    },
    /** 供父页统一保存；silent 时不弹 toast，返回是否成功 */
    async saveConfig({ silent = false } = {}) {
      const evalSchema = (this.evalSchema || '').trim()
      if (!evalSchema) {
        if (!silent) this.$message.warning('请选择或填写评估数据集（eval_schema）')
        return false
      }
      if (/citylearn_challenge_2022/.test(evalSchema)) {
        try {
          await this.$confirm(
            '2022 数据集仅含电池动作，与 CHESCA 不兼容。\n' +
              '继续保存后若跑 CHESCA.py 会启动失败；请改用 2023/2026 schema。\n是否仍要保存？',
            '数据集不兼容提示',
            { type: 'warning', confirmButtonText: '仍保存', cancelButtonText: '取消' }
          )
        } catch (e) {
          return false
        }
      }
      this.saving = true
      try {
        const response = await axios.post('/api/web/basedata/saveBatteryMinSocConfig', this.buildPayload())
        if (response.data && response.data.code === 0) {
          if (!silent) this.$message.success('保存成功')
          return true
        }
        if (!silent) this.$message.error((response.data && response.data.message) || '保存失败')
        return false
      } catch (e) {
        if (!silent) this.$message.error('保存失败')
        return false
      } finally {
        this.saving = false
      }
    },
    async handleSave() {
      await this.saveConfig()
    },
    /** 供父页统一恢复；skipConfirm/silent 由父页控制提示 */
    async resetConfig({ silent = false, skipConfirm = false } = {}) {
      if (!skipConfirm) {
        try {
          await this.$confirm('确定恢复为 CHESCA 算法内置默认值吗？', '提示', { type: 'warning' })
        } catch {
          return false
        }
      }
      this.loading = true
      try {
        const response = await axios.post('/api/web/basedata/resetBatteryMinSocConfig')
        if (response.data && response.data.code === 0) {
          this.applyConfig(response.data.data)
          if (!silent) this.$message.success('已恢复默认值')
          return true
        }
        if (!silent) this.$message.error((response.data && response.data.message) || '恢复失败')
        return false
      } catch (e) {
        if (!silent) this.$message.error('恢复失败')
        return false
      } finally {
        this.loading = false
        this.$nextTick(() => this.renderChart())
      }
    },
    async handleReset() {
      await this.resetConfig()
    }
  }
}
</script>

<style scoped>
.battery-min-soc-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--space-4) var(--space-5) var(--space-6);
  box-sizing: border-box;
  background: var(--primary-background-color);
}

.battery-min-soc-page.is-embedded {
  min-height: 0;
  padding: 0;
  background: transparent;
}

.battery-min-soc-page.is-readonly .card-schema-bar,
.battery-min-soc-page.is-readonly .card-body {
  pointer-events: none;
  opacity: 0.72;
}

.chesca-unified-card {
  border: 1px solid var(--divider-color);
  border-radius: var(--ha-card-border-radius);
  background: var(--card-background-color);
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: 0;
}

.card-toggle-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: var(--card-background-color);
  color: var(--primary-color);
  cursor: pointer;
  box-shadow: none;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.card-toggle-btn i {
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

.card-toggle-btn:hover {
  background: var(--sidebar-selected-background);
  border-color: var(--outline-hover-color);
  color: var(--dark-primary-color);
}

.card-toggle-btn:active {
  background: var(--light-primary-color);
}

.card-body {
  margin-top: var(--space-3);
}

.chesca-block {
  margin-top: var(--space-5);
  padding: var(--space-4) 0 0;
  border: none;
  border-top: 1px solid var(--divider-color);
  border-radius: 0;
  background: transparent;
}

.chesca-desc + .chesca-block {
  margin-top: var(--space-2);
  padding-top: 0;
  border-top: none;
}

.section-heading {
  margin: 0 0 var(--space-2);
  font-size: 18px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--primary-text-color);
}

.chesca-block .config-section + .config-section {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--divider-color);
}

.chesca-desc {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  line-height: 1.6;
  color: var(--secondary-text-color);
  max-width: 960px;
}

.chesca-desc code {
  background: var(--input-fill-color);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
  font-family: "Roboto Mono", "SF Mono", Consolas, monospace;
}

.config-section + .config-section {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--divider-color);
}

.chesca-unified-card .section-heading {
  margin-bottom: var(--space-2);
}

.balance-card {
  margin-top: 0;
}

.page-header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.page-title {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 400;
  color: var(--primary-text-color);
}

.page-desc {
  margin: 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--secondary-text-color);
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.config-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: var(--ha-card-border-radius);
  min-height: 0;
}

.config-card.is-collapsed {
  flex: none;
  min-height: 0;
}

.config-card.is-collapsed >>> .el-card__body {
  flex: none;
  padding-top: var(--space-3);
  padding-bottom: var(--space-3);
}

.config-card >>> .el-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: var(--space-4);
  min-height: 0;
}

.config-layout {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-height: 0;
}

.config-panel {
  flex: none;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.panel-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.panel-subtitle {
  margin-top: var(--space-2);
  font-size: 13px;
  font-weight: 500;
  color: var(--secondary-text-color);
}

.nested-desc {
  margin-top: -4px;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--divider-color);
}

.section-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--secondary-text-color);
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.hour-select {
  width: 100%;
}

.soc-input-row {
  display: flex;
  align-items: center;
  width: 100%;
}

.percent-input {
  flex: 1;
  width: 100%;
}

.percent-input >>> .el-input-number {
  width: 100%;
}

.percent-suffix {
  margin-left: 8px;
  color: var(--secondary-text-color);
  font-size: 13px;
}

.panel-tip {
  margin-top: 0;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--secondary-text-color);
  background: var(--input-fill-color);
  border-radius: 6px;
}

.chart-panel {
  flex: none;
  width: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: var(--space-3);
  border: none;
  border-radius: 0;
  background: transparent;
}

.chart-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.chart-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--primary-text-color);
}

.chart-subtitle {
  font-size: 12px;
  color: var(--secondary-text-color);
}

.soc-chart {
  width: 100%;
  height: 360px;
  min-height: 360px;
}

.balance-card {
  margin-top: var(--space-3);
  border-radius: var(--ha-card-border-radius);
}

.balance-card >>> .el-card__body {
  padding: var(--space-4);
}

.balance-panel {
  max-width: 920px;
}

.balance-desc {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  line-height: 1.65;
  color: var(--secondary-text-color);
}

.balance-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.cool-floor-form {
  grid-template-columns: 1fr;
}

.cool-floor-form .form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-row-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.form-row-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.field-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--secondary-text-color);
}

.eval-schema-item {
  margin-bottom: 0;
}

.card-schema-bar {
  margin-top: 12px;
  margin-bottom: 0;
}

.eval-schema-select {
  width: 100%;
}

.soc-panel-intro {
  margin: 0 0 12px;
}

.number-input {
  width: 100%;
}

.number-input >>> .el-input-number {
  width: 100%;
}

.slider-form {
  max-width: 640px;
}

.slider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.slider-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--primary-color);
  font-variant-numeric: tabular-nums;
}

.tmp-card {
  margin-top: 12px;
}

.tau-card {
  margin-top: 12px;
}

.tau-panel {
  max-width: 920px;
}

.narrow-select-item .hour-select,
.tau-form-item .hour-select {
  max-width: 320px;
}

.tau-desc {
  margin-top: 4px;
  white-space: normal;
}

.balance-type-panel {
  max-width: 720px;
}

.balance-type-notes {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.type-note {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: var(--input-fill-color);
}

.type-note.active {
  border-color: var(--primary-color);
  background: var(--sidebar-selected-background);
}

.type-note-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-text-color);
  margin-bottom: 6px;
}

.type-note-desc,
.type-note-effect {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--secondary-text-color);
}

.type-note-effect {
  margin-bottom: 0;
  color: var(--secondary-text-color);
}

.balance-type-card {
  margin-top: 12px;
}

@media (max-width: 960px) {
  .soc-chart {
    height: 300px;
    min-height: 300px;
  }

  .balance-form {
    grid-template-columns: 1fr;
  }

  .form-row-3,
  .form-row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
