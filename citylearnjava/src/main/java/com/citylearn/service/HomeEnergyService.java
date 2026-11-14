package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.citylearn.common.HomeEnergyHaMath;
import com.citylearn.common.Result;
import com.citylearn.common.SimulationDataPaths;
import com.citylearn.common.TaskNaming;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.param.PipelineStepConfig;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.param.PyFileParam;
import com.citylearn.vo.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * 首页能源分配（按日/按小时预聚合）—— 原 BaseDataService 的一部分，按领域拆出。
 *
 * <p>只读：按 taskId 找到仿真导出 CSV，在服务端聚合后下发，避免前端拉全年原始数据。
 * 结果按 (taskId, mode, untilTs, datasetYear) 缓存在内存里，最多 32 条。</p>
 */
@Slf4j
@Service
public class HomeEnergyService {

    @Resource
    private PyFileMapper pyFileMapper;
    @Resource
    private PyTaskMapper pyTaskMapper;
    @Resource
    private FileResourceProperties fileResourceProperties;

    /** 首页能源流缓存：key = taskId|mode|untilTs|year */
    private final ConcurrentHashMap<String, HomeEnergyFlowVO> homeEnergyFlowCache = new ConcurrentHashMap<>();

    /** 导出目录定位规则与仪表盘共用，抽到 {@link SimulationDataPaths}。 */
    private Path resolveSimulationDataRoot(Path taskDir) throws IOException {
        return SimulationDataPaths.resolve(taskDir);
    }

    /** 任务目录规则与任务执行链共用，抽到 {@link SimulationDataPaths}。 */
    private Path getTaskDir(String taskId) {
        return SimulationDataPaths.taskDir(fileResourceProperties.getOutFilePath(), taskId);
    }

    /** 展示名规则与仪表盘共用，抽到 {@link TaskNaming}。 */
    private String buildDashboardGroupName(PyFile pyFile, PyTask task) {
        return TaskNaming.groupName(pyFile, task);
    }

    /**
     * 首页能源分配轻量接口：服务端按日预聚合，避免下发全年 CSV。
     *
     * @param mode today=仅当日；history=截止 untilTs 的全部日期
     */
    public HomeEnergyFlowVO getHomeEnergyFlow(String taskId, String untilTs, Integer datasetYear, String mode)
            throws IOException {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        String normalizedMode = "history".equalsIgnoreCase(mode) ? "history" : "today";
        int year = datasetYear == null || datasetYear < 2000 ? 2026 : datasetYear;
        String until = untilTs == null ? "" : untilTs.trim().replace('T', ' ');
        if (until.length() >= 19) {
            until = until.substring(0, 19);
        } else if (until.length() >= 16) {
            until = until.substring(0, 16) + ":00";
        }
        if (until.isEmpty()) {
            throw new RuntimeException("untilTs 不能为空");
        }

        String cacheKey = taskId + "|" + until + "|" + year + "|" + normalizedMode;
        HomeEnergyFlowVO cached = homeEnergyFlowCache.get(cacheKey);
        if (cached != null) {
            return cached;
        }

        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || task.getStatus() == null || task.getStatus() != 1) {
            throw new RuntimeException("任务不存在或未执行成功");
        }
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            throw new RuntimeException("关联 Python 文件不存在");
        }

        Path taskDir = getTaskDir(taskId);
        Path dataRoot = resolveSimulationDataRoot(taskDir);
        String todayKey = until.length() >= 10 ? until.substring(0, 10) : null;
        String onlyMonthDay = "today".equals(normalizedMode) && todayKey != null && todayKey.length() >= 10
                ? todayKey.substring(5, 10)
                : null;

        List<BuildingExportPair> pairs = listBuildingExportPairs(dataRoot);
        if (pairs.isEmpty() && !dataRoot.equals(taskDir)) {
            pairs = listBuildingExportPairs(taskDir);
        }

        // day -> buildingId -> accumulator
        Map<String, Map<String, Map<String, Double>>> byDayBuilding = new LinkedHashMap<>();
        List<String> buildings = new ArrayList<>();

        for (BuildingExportPair pair : pairs) {
            buildings.add(pair.buildingId);
            Map<String, double[]> batByTs = loadBatteryByTimestamp(pair.batteryFile, onlyMonthDay, until, year);
            accumulateBuildingDays(pair.buildingFile, pair.buildingId, batByTs, onlyMonthDay, until, year, byDayBuilding);
        }

        buildings.sort((a, b) -> {
            int na = Integer.parseInt(a.replaceAll("\\D+", "0"));
            int nb = Integer.parseInt(b.replaceAll("\\D+", "0"));
            return Integer.compare(na, nb);
        });

        Map<String, Map<String, Map<String, Double>>> flows = new LinkedHashMap<>();
        List<String> days = new ArrayList<>(byDayBuilding.keySet());
        Collections.sort(days);
        for (String day : days) {
            Map<String, Map<String, Double>> scopeMap = new LinkedHashMap<>();
            Map<String, Double> community = HomeEnergyHaMath.emptyFlow();
            Map<String, Map<String, Double>> buildingAcc = byDayBuilding.get(day);
            for (String bId : buildings) {
                Map<String, Double> acc = buildingAcc.get(bId);
                if (acc == null) {
                    acc = HomeEnergyHaMath.emptyFlow();
                }
                Map<String, Double> finalized = HomeEnergyHaMath.finalizeFlow(acc);
                scopeMap.put(bId, finalized);
                for (Map.Entry<String, Double> e : finalized.entrySet()) {
                    community.put(e.getKey(), community.getOrDefault(e.getKey(), 0d) + e.getValue());
                }
            }
            // community 的 otherLoad/nonShiftable 用各建筑已 finalize 后的和再 round
            for (String k : new ArrayList<>(community.keySet())) {
                community.put(k, HomeEnergyHaMath.round3(community.get(k)));
            }
            scopeMap.put("community", community);
            flows.put(day, scopeMap);
        }

        HomeEnergyFlowVO vo = new HomeEnergyFlowVO();
        vo.setTaskId(taskId);
        vo.setGroupName(buildDashboardGroupName(pyFile, task));
        vo.setMode(normalizedMode);
        vo.setUntilTs(until);
        vo.setDatasetYear(year);
        vo.setDays(days);
        vo.setBuildings(buildings);
        vo.setFlows(flows);

        homeEnergyFlowCache.put(cacheKey, vo);
        // 限制缓存体积：同一 task 只保留少量条目
        if (homeEnergyFlowCache.size() > 32) {
            Iterator<String> it = homeEnergyFlowCache.keySet().iterator();
            if (it.hasNext()) {
                homeEnergyFlowCache.remove(it.next());
            }
        }
        return vo;
    }

    /**
     * 指定日 + scope 的逐小时家庭用电（对齐 HA energy more-info）。
     */
    public HomeEnergyHourlyVO getHomeEnergyHourly(String taskId, String day, String scope,
                                                  String untilTs, Integer datasetYear) throws IOException {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        if (day == null || day.trim().length() < 10) {
            throw new RuntimeException("day 不能为空");
        }
        int year = datasetYear == null || datasetYear < 2000 ? 2026 : datasetYear;
        String dayKey = day.trim().substring(0, 10);
        // 映射到数据集年份（前端选中日可能已是 2026）
        if (dayKey.length() >= 10) {
            dayKey = year + dayKey.substring(4);
        }
        String until = untilTs == null ? "" : untilTs.trim().replace('T', ' ');
        if (until.length() >= 19) {
            until = until.substring(0, 19);
        } else if (until.length() >= 16) {
            until = until.substring(0, 16) + ":00";
        }
        if (until.isEmpty()) {
            throw new RuntimeException("untilTs 不能为空");
        }
        String normalizedScope = scope == null || scope.trim().isEmpty()
                ? "community"
                : scope.trim().toLowerCase(Locale.ROOT);

        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || task.getStatus() == null || task.getStatus() != 1) {
            throw new RuntimeException("任务不存在或未执行成功");
        }
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            throw new RuntimeException("关联 Python 文件不存在");
        }

        Path taskDir = getTaskDir(taskId);
        Path dataRoot = resolveSimulationDataRoot(taskDir);
        String onlyMonthDay = dayKey.length() >= 10 ? dayKey.substring(5, 10) : null;

        List<BuildingExportPair> pairs = listBuildingExportPairs(dataRoot);
        if (pairs.isEmpty() && !dataRoot.equals(taskDir)) {
            pairs = listBuildingExportPairs(taskDir);
        }

        // ts -> 累加指标
        Map<String, Map<String, Double>> byTs = new LinkedHashMap<>();
        for (BuildingExportPair pair : pairs) {
            if (!"community".equals(normalizedScope) && !normalizedScope.equals(pair.buildingId)) {
                continue;
            }
            Map<String, double[]> batByTs = loadBatteryByTimestamp(pair.batteryFile, onlyMonthDay, until, year);
            accumulateBuildingHours(pair.buildingFile, batByTs, onlyMonthDay, dayKey, until, year, byTs);
        }

        List<String> tsList = new ArrayList<>(byTs.keySet());
        Collections.sort(tsList);
        List<Map<String, Object>> points = new ArrayList<>();
        double totalHome = 0;
        String[] metricKeys = {
                "home", "pv", "gridIn", "gridOut", "batIn", "batOut", "nonShiftable",
                "solarToHome", "solarToGrid", "solarToBattery",
                "gridToHome", "gridToBattery",
                "batteryToHome", "batteryToGrid"
        };
        for (String ts : tsList) {
            Map<String, Double> acc = byTs.get(ts);
            double home = HomeEnergyHaMath.round3(acc.getOrDefault("home", 0d));
            totalHome += home;
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("ts", ts);
            for (String key : metricKeys) {
                point.put(key, HomeEnergyHaMath.round3(acc.getOrDefault(key, 0d)));
            }
            // 净用电量 = 购入 − 外送（可负），与 CSV Net Electricity Consumption 一致
            double net = acc.getOrDefault("gridIn", 0d) - acc.getOrDefault("gridOut", 0d);
            point.put("net", HomeEnergyHaMath.round3(net));
            points.add(point);
        }

        HomeEnergyHourlyVO vo = new HomeEnergyHourlyVO();
        vo.setTaskId(taskId);
        vo.setGroupName(buildDashboardGroupName(pyFile, task));
        vo.setDay(dayKey);
        vo.setScope(normalizedScope);
        vo.setUntilTs(until);
        vo.setDatasetYear(year);
        vo.setTotalHome(HomeEnergyHaMath.round3(totalHome));
        vo.setPoints(points);
        return vo;
    }

    private static final class BuildingExportPair {
        private final String buildingId;
        private final Path buildingFile;
        private final Path batteryFile;

        private BuildingExportPair(String buildingId, Path buildingFile, Path batteryFile) {
            this.buildingId = buildingId;
            this.buildingFile = buildingFile;
            this.batteryFile = batteryFile;
        }
    }

    private List<BuildingExportPair> listBuildingExportPairs(Path dir) throws IOException {
        List<BuildingExportPair> out = new ArrayList<>();
        if (!Files.isDirectory(dir)) {
            return out;
        }
        Map<String, Path> buildingFiles = new LinkedHashMap<>();
        Map<String, Path> batteryFiles = new LinkedHashMap<>();
        try (Stream<Path> stream = Files.list(dir)) {
            stream.filter(Files::isRegularFile).forEach(p -> {
                String name = p.getFileName().toString();
                if (!name.startsWith("exported_data_") || !name.endsWith(".csv")) {
                    return;
                }
                String cleaned = name.substring("exported_data_".length(), name.length() - 4);
                String base = cleaned.replaceAll("(?i)_ep\\d+$", "").toLowerCase(Locale.ROOT);
                if (base.matches("building_\\d+")) {
                    buildingFiles.put(base, p);
                } else if (base.matches("building_\\d+_battery.*")) {
                    String bId = base.replaceFirst("_battery.*", "");
                    batteryFiles.put(bId, p);
                }
            });
        }
        for (Map.Entry<String, Path> e : buildingFiles.entrySet()) {
            out.add(new BuildingExportPair(e.getKey(), e.getValue(), batteryFiles.get(e.getKey())));
        }
        out.sort(Comparator.comparing(p -> p.buildingId));
        return out;
    }

    private Map<String, double[]> loadBatteryByTimestamp(Path batteryFile, String onlyMonthDay,
                                                         String untilTs, int year) throws IOException {
        Map<String, double[]> map = new HashMap<>();
        if (batteryFile == null || !Files.isRegularFile(batteryFile)) {
            return map;
        }
        try (BufferedReader reader = Files.newBufferedReader(batteryFile, StandardCharsets.UTF_8)) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                return map;
            }
            if (headerLine.startsWith("\uFEFF")) {
                headerLine = headerLine.substring(1);
            }
            String[] headers = splitCsvLine(headerLine);
            int tsIdx = indexOfHeader(headers, "timestamp");
            int batIdx = indexOfHeader(headers,
                    "Battery (Dis)Charge-kWh", "Battery (Dis)Charge");
            if (tsIdx < 0 || batIdx < 0) {
                return map;
            }
            String line;
            while ((line = reader.readLine()) != null) {
                if (onlyMonthDay != null
                        && !line.contains("-" + onlyMonthDay + "T")
                        && !line.contains("-" + onlyMonthDay + " ")) {
                    continue;
                }
                String[] cols = splitCsvLine(line);
                if (cols.length <= Math.max(tsIdx, batIdx)) {
                    continue;
                }
                String norm = HomeEnergyHaMath.normalizeTs(cols[tsIdx], year);
                if (norm.isEmpty() || norm.compareTo(untilTs) > 0) {
                    continue;
                }
                double bat = HomeEnergyHaMath.parseDouble(cols[batIdx]);
                map.put(norm, new double[]{bat});
            }
        }
        return map;
    }

    private void accumulateBuildingDays(Path buildingFile, String buildingId,
                                        Map<String, double[]> batByTs,
                                        String onlyMonthDay, String untilTs, int year,
                                        Map<String, Map<String, Map<String, Double>>> byDayBuilding)
            throws IOException {
        if (buildingFile == null || !Files.isRegularFile(buildingFile)) {
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(buildingFile, StandardCharsets.UTF_8)) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                return;
            }
            if (headerLine.startsWith("\uFEFF")) {
                headerLine = headerLine.substring(1);
            }
            String[] headers = splitCsvLine(headerLine);
            int tsIdx = indexOfHeader(headers, "timestamp");
            int pvIdx = indexOfHeader(headers,
                    "Energy Production from PV-kWh", "Energy Production from PV", "Total Solar Generation-kWh");
            int netIdx = indexOfHeader(headers,
                    "Net Electricity Consumption-kWh", "Net Electricity Consumption");
            int loadIdx = indexOfHeader(headers,
                    "Non-shiftable Load Electricity Consumption-kWh",
                    "Non-shiftable Load-kWh",
                    "Non-shiftable Load");
            if (tsIdx < 0) {
                return;
            }
            String line;
            while ((line = reader.readLine()) != null) {
                if (onlyMonthDay != null
                        && !line.contains("-" + onlyMonthDay + "T")
                        && !line.contains("-" + onlyMonthDay + " ")) {
                    continue;
                }
                String[] cols = splitCsvLine(line);
                if (cols.length <= tsIdx) {
                    continue;
                }
                String norm = HomeEnergyHaMath.normalizeTs(cols[tsIdx], year);
                if (norm.isEmpty() || norm.compareTo(untilTs) > 0) {
                    continue;
                }
                String day = HomeEnergyHaMath.dayKey(norm);
                if (day == null) {
                    continue;
                }
                double pvH = Math.abs(pvIdx >= 0 && cols.length > pvIdx
                        ? HomeEnergyHaMath.parseDouble(cols[pvIdx]) : 0);
                double net = netIdx >= 0 && cols.length > netIdx
                        ? HomeEnergyHaMath.parseDouble(cols[netIdx]) : 0;
                double gridInH = Math.max(net, 0);
                double gridOutH = Math.max(-net, 0);
                double loadH = Math.max(loadIdx >= 0 && cols.length > loadIdx
                        ? HomeEnergyHaMath.parseDouble(cols[loadIdx]) : 0, 0);
                double batVal = 0;
                double[] bat = batByTs.get(norm);
                if (bat == null) {
                    // 电池文件可能仍是原始年份时间戳，再试未映射 key
                    bat = batByTs.get(HomeEnergyHaMath.normalizeTs(cols[tsIdx], year));
                }
                if (bat != null) {
                    batVal = bat[0];
                }
                double batInH = Math.max(batVal, 0);
                double batOutH = Math.max(-batVal, 0);

                Map<String, Map<String, Double>> buildingMap =
                        byDayBuilding.computeIfAbsent(day, d -> new LinkedHashMap<>());
                Map<String, Double> acc =
                        buildingMap.computeIfAbsent(buildingId, b -> HomeEnergyHaMath.emptyFlow());
                HomeEnergyHaMath.addHour(acc, pvH, gridInH, gridOutH, batInH, batOutH, loadH);
            }
        }
    }

    /**
     * 将单栋楼指定日的逐小时 HA 分摊累加进 byTs（community 时多栋同 ts 相加）。
     */
    private void accumulateBuildingHours(Path buildingFile, Map<String, double[]> batByTs,
                                         String onlyMonthDay, String dayKey, String untilTs, int year,
                                         Map<String, Map<String, Double>> byTs) throws IOException {
        if (buildingFile == null || !Files.isRegularFile(buildingFile)) {
            return;
        }
        try (BufferedReader reader = Files.newBufferedReader(buildingFile, StandardCharsets.UTF_8)) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                return;
            }
            if (headerLine.startsWith("\uFEFF")) {
                headerLine = headerLine.substring(1);
            }
            String[] headers = splitCsvLine(headerLine);
            int tsIdx = indexOfHeader(headers, "timestamp");
            int pvIdx = indexOfHeader(headers,
                    "Energy Production from PV-kWh", "Energy Production from PV", "Total Solar Generation-kWh");
            int netIdx = indexOfHeader(headers,
                    "Net Electricity Consumption-kWh", "Net Electricity Consumption");
            int loadIdx = indexOfHeader(headers,
                    "Non-shiftable Load Electricity Consumption-kWh",
                    "Non-shiftable Load-kWh",
                    "Non-shiftable Load");
            if (tsIdx < 0) {
                return;
            }
            String line;
            while ((line = reader.readLine()) != null) {
                if (onlyMonthDay != null
                        && !line.contains("-" + onlyMonthDay + "T")
                        && !line.contains("-" + onlyMonthDay + " ")) {
                    continue;
                }
                String[] cols = splitCsvLine(line);
                if (cols.length <= tsIdx) {
                    continue;
                }
                String norm = HomeEnergyHaMath.normalizeTs(cols[tsIdx], year);
                if (norm.isEmpty() || norm.compareTo(untilTs) > 0) {
                    continue;
                }
                String day = HomeEnergyHaMath.dayKey(norm);
                if (day == null || !day.equals(dayKey)) {
                    continue;
                }
                double pvH = Math.abs(pvIdx >= 0 && cols.length > pvIdx
                        ? HomeEnergyHaMath.parseDouble(cols[pvIdx]) : 0);
                double net = netIdx >= 0 && cols.length > netIdx
                        ? HomeEnergyHaMath.parseDouble(cols[netIdx]) : 0;
                double gridInH = Math.max(net, 0);
                double gridOutH = Math.max(-net, 0);
                double loadH = Math.max(loadIdx >= 0 && cols.length > loadIdx
                        ? HomeEnergyHaMath.parseDouble(cols[loadIdx]) : 0, 0);
                double batVal = 0;
                double[] bat = batByTs.get(norm);
                if (bat != null) {
                    batVal = bat[0];
                }
                double batInH = Math.max(batVal, 0);
                double batOutH = Math.max(-batVal, 0);

                Map<String, Double> step = HomeEnergyHaMath.computeHaConsumption(
                        pvH, gridInH, gridOutH, batInH, batOutH);
                Map<String, Double> acc = byTs.computeIfAbsent(norm, t -> new HashMap<>());
                acc.merge("pv", pvH, Double::sum);
                acc.merge("gridIn", gridInH, Double::sum);
                acc.merge("gridOut", gridOutH, Double::sum);
                acc.merge("batIn", batInH, Double::sum);
                acc.merge("batOut", batOutH, Double::sum);
                acc.merge("nonShiftable", loadH, Double::sum);
                for (Map.Entry<String, Double> e : step.entrySet()) {
                    acc.merge(e.getKey(), e.getValue(), Double::sum);
                }
            }
        }
    }

    private static String[] splitCsvLine(String line) {
        return line.split(",", -1);
    }

    private static int indexOfHeader(String[] headers, String... keys) {
        for (int i = 0; i < headers.length; i++) {
            String h = headers[i] == null ? "" : headers[i].trim();
            for (String k : keys) {
                if (h.equalsIgnoreCase(k)) {
                    return i;
                }
            }
        }
        return -1;
    }
}
