package com.citylearn.service;


import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.citylearn.common.Result;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.config.SystemConfig;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.PyFileParam;
import com.citylearn.vo.BuildingDataVO;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import com.citylearn.vo.KpisTransVO;
import com.citylearn.vo.KpisVO;
import com.citylearn.vo.PyFileVO;
import com.citylearn.vo.PyTaskScriptVO;
import com.citylearn.vo.PyTaskVO;
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
import java.util.stream.Stream;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * <p>
 *  服务实现类
 * </p>
 *
 * @author Your Name
 * @since 2025-06-08
 */
@Slf4j
@Service
public class BaseDataService implements SystemConfig {

    @Resource
    private Building1Mapper building1Mapper;
    @Resource
    private Building2Mapper building2Mapper;
    @Resource
    private Building3Mapper building3Mapper;
    @Resource
    private CarbonIntensityMapper carbonIntensityMapper;
    @Resource
    private PricingMapper pricingMapper;
    @Resource
    private WeatherMapper weatherMapper;
    @Resource
    private KpisMapper kpisMapper;
    @Resource
    private PyFileMapper pyFileMapper;
    @Resource
    private PyTaskMapper pyTaskMapper;
    @Resource
    private FileResourceProperties fileResourceProperties;
    @Resource(name = "pythonTaskExecutor")
    private Executor pythonTaskExecutor;
    @Resource
    private BatteryMinSocConfigService batteryMinSocConfigService;


    // 使用普通 Map，并通过 @PostConstruct 初始化
    private static Map<String, BaseMapper> BUILDING_MAPPER = new HashMap<>();

    private static Map<String, List<String>> CONSOLE_MAP = new HashMap<>();

    private static Map<String, Integer> CONSOLE_INDEX_MAP = new HashMap<>();

    /** 任务实时 stdout 缓冲（按行追加，供轮询读取） */
    private static final ConcurrentHashMap<String, StringBuilder> TASK_OUTPUT_BUFFER = new ConcurrentHashMap<>();

    @PostConstruct
    public void init() {
        BUILDING_MAPPER.put("building1", building1Mapper);
        BUILDING_MAPPER.put("building2", building2Mapper);
        BUILDING_MAPPER.put("building3", building3Mapper);
    }
    public List<BuildingDataVO> getList(String buildingId,Integer month,Integer hour,Integer dayType){
        List<?  extends Building> buildingList=null;
        if("building1".equals(buildingId)){
            buildingList=building1Mapper.selectList(new QueryWrapper<Building1>()
                    .lambda()
                    .eq(null!=month,Building1::getMonth,month)
                    .eq(null!=hour,Building1::getHour,hour)
                    .eq(null!=dayType,Building1::getDayType,dayType)
                    .orderByAsc(Building1::getId)
                    .last(null==month && null==hour && null==dayType,"limit 36"));
        }else if("building2".equals(buildingId)){
            buildingList=building2Mapper.selectList(new QueryWrapper<Building2>()
                    .lambda()
                    .eq(null!=month,Building2::getMonth,month)
                    .eq(null!=hour,Building2::getHour,hour)
                    .eq(null!=dayType,Building2::getDayType,dayType)
                    .orderByAsc(Building2::getId)
                    .last(null==month && null==hour && null==dayType,"limit 36"));
        }else if("building3".equals(buildingId)){
            buildingList=building3Mapper.selectList(new QueryWrapper<Building3>()
                    .lambda()
                    .eq(null!=month,Building3::getMonth,month)
                    .eq(null!=hour,Building3::getHour,hour)
                    .eq(null!=dayType,Building3::getDayType,dayType)
                    .orderByAsc(Building3::getId)
                    .last(null==month && null==hour && null==dayType,"limit 36"));
        }
        if(null==buildingList || buildingList.size()==0){
            return new ArrayList<>();
        }

        List<Integer> idList=buildingList.stream().map(Building::getId).collect(Collectors.toList());

        List<CarbonIntensity> carbonIntensityList=carbonIntensityMapper.selectList(new QueryWrapper<CarbonIntensity>()
                .lambda()
                .in(CarbonIntensity::getId,idList)
                .orderByAsc(CarbonIntensity::getId));

        List<Pricing> pricingList=pricingMapper.selectList(new QueryWrapper<Pricing>()
                .lambda()
                .in(Pricing::getId,idList)
                .orderByAsc(Pricing::getId));

        List<Weather> weatherList=weatherMapper.selectList(new QueryWrapper<Weather>()
                .lambda()
                .in(Weather::getId,idList)
                .orderByAsc(Weather::getId));


        List<BuildingDataVO> returnList=new ArrayList<>();
        for(int i=0;i<buildingList.size();i++){
            BuildingDataVO buildingDataVO=new BuildingDataVO();
            buildingDataVO.setBuildingId(buildingId);
            BeanUtils.copyProperties(buildingList.get(i),buildingDataVO);
            BeanUtils.copyProperties(carbonIntensityList.get(i),buildingDataVO);
            BeanUtils.copyProperties(pricingList.get(i),buildingDataVO);
            BeanUtils.copyProperties(weatherList.get(i),buildingDataVO);
            returnList.add(buildingDataVO);
        }


        return returnList;
    }


    private static final String PYTHON_PATH = "D:/Users/clfbe/anaconda3/envs/cl2/python.exe";



    private static  final  List<String> LINE_TITLE=new ArrayList<String>(){{
        add("allTimePeakAverage");
        add("annualNormalizedUnservedEnergyTotal");
        add("carbonEmissionsTotal");
        add("costTotal");
        add("dailyOneMinusLoadFactorAverage");
        add("dailyPeakAverage");
        add("discomfortColdDeltaAverage");
        add("discomfortColdDeltaMaximum");
        add("discomfortColdDeltaMinimum");
        add("discomfortColdProportion");
        add("discomfortHotDeltaAverage");
        add("discomfortHotDeltaMaximum");
        add("discomfortHotDeltaMinimum");
        add("discomfortHotProportion");
        add("discomfortProportion");
        add("electricityConsumptionTotal");
        add("monthlyOneMinusLoadFactorAverage");
        add("oneMinusThermalResilienceProportion");
        add("powerOutageNormalizedUnservedEnergyTotal");
        add("rampingAverage");
        add("zeroNetEnergy");
    }} ;

    private static  final  List<String> LINE_TXT_TITLE=new ArrayList<String>(){{
        add("全时段峰值平均值");
        add("年度标准化未满足能源总量");
        add("碳排放总量");
        add("总成本");
        add("日平均(1-负荷率)");
        add("日峰值平均值");
        add("低温不适温差平均值");
        add("低温不适温差最大值");
        add("低温不适温差最小值");
        add("低温不适温差比例");
        add("高温不适温差平均值");
        add("高温不适温差最大值");
        add("高温不适温差最小值");
        add("高温不适温差比例");
        add("不适比例");
        add("电量消耗总量");
        add("月平均(1-负荷率)");
        add("热弹性不足比例");
        add("停电未满足能源总量");
        add("负荷爬坡率");
        add("零净能耗达标率");


    }} ;
    public List<KpisTransVO> getKpis(String agentType) {
        List<Kpis> kpisList=kpisMapper.selectList(new QueryWrapper<Kpis>()
                .lambda()
                .eq(Kpis::getAgentType,agentType));

        if(null==kpisList || kpisList.size()==0){
            return new ArrayList<>();
        }

        JSONArray jsonArray=JSON.parseArray(JSON.toJSONString(kpisList));

        List<KpisTransVO> returnList=new ArrayList<>();
        for(int i=0;i<LINE_TITLE.size();i++){
            String title=LINE_TITLE.get(i);
            KpisTransVO kpisTransVO=new KpisTransVO();
            kpisTransVO.setLine1(LINE_TXT_TITLE.get(i));
            kpisTransVO.setLine2(jsonArray.getJSONObject(0).getBigDecimal(title));
            kpisTransVO.setLine3(jsonArray.getJSONObject(1).getBigDecimal(title));
            kpisTransVO.setLine4(jsonArray.getJSONObject(2).getBigDecimal(title));
            kpisTransVO.setLine5(jsonArray.getJSONObject(3).getBigDecimal(title));
            returnList.add(kpisTransVO);
        }

        return returnList;
    }

    public List<PyFileVO> getPyFileList(String createUser) {
        List<PyFile> list=pyFileMapper.getPyFileList(createUser);
        List<PyFileVO> returnList=JSON.parseArray(JSON.toJSONString(list),PyFileVO.class);
        return returnList;
    }

    private static final String basePath="D:\\citylearn-demo\\citylearnpy\\";

    public String getPyFile(String id) {
        PyFile pyFile = pyFileMapper.selectById(id);

        try {
            return new String(Files.readAllBytes(Paths.get(basePath+pyFile.getFileName())));
        } catch (IOException e) {
            e.printStackTrace();
        }
        return "";
    }

    public void savePyFile(PyFileParam pyFileParam) throws Exception {
        PyFile pyFile = pyFileMapper.selectById(pyFileParam.getId());

        if(null!=pyFileParam.getFileName()){
            List<PyFile> list=pyFileMapper.selectList(new QueryWrapper<PyFile>().lambda()
                    .eq(PyFile::getFileName,pyFileParam.getFileName())
                    .ne(PyFile::getId,pyFile.getId()));
            if(null!=list && list.size()>0){
                throw new Exception("文件名已存在");
            }

            Path source = Paths.get(basePath+pyFile.getFileName());
            Path target = Paths.get(basePath+pyFileParam.getFileName());
            try {
                Files.move(source, target);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
            pyFile.setFileName(pyFileParam.getFileName());
            pyFileMapper.updateById(pyFile);

        }else if(null!=pyFileParam.getDescription()){
            pyFile.setDescription(pyFileParam.getDescription());
            pyFileMapper.updateById(pyFile);
        }else{
            Files.write(Paths.get(basePath+pyFile.getFileName()),pyFileParam.getCode().getBytes());
        }



    }

    public PyFileVO addPyFile() throws IOException {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyyMMddHHmmss");
        Date newDate = new Date();
        PyFile pyFile=new PyFile();
        pyFile.setId(sdf.format(newDate));
        pyFile.setFileName(pyFile.getId()+".py");
        pyFile.setDescription("无");
        pyFile.setCreateUser("admin");
        pyFile.setIfSystem(false);
        pyFile.setIfShow(false);
        pyFile.setCreateTime(newDate);
        pyFileMapper.insert(pyFile);
        Files.createFile(Paths.get(basePath+pyFile.getFileName()));
        return JSON.parseObject(JSON.toJSONString(pyFile),PyFileVO.class);
    }

    public void deletePyFile(PyFileParam pyFileParam) {
        pyFileMapper.deleteById(pyFileParam.getId());
    }

    public PyFileVO updatePyFileIfShow(String id, Boolean ifShow) {
        PyFile pyFile = pyFileMapper.selectById(id);
        if (pyFile == null) {
            throw new RuntimeException("文件不存在");
        }
        pyFile.setIfShow(ifShow);
        pyFileMapper.updateById(pyFile);
        return JSON.parseObject(JSON.toJSONString(pyFile), PyFileVO.class);
    }

    /**
     * 执行记录「展示/未展示」：仅执行完成的任务可切换；默认未展示。
     */
    public PyTaskVO updatePyTaskIfShow(String taskId, Boolean ifShow) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("执行记录不存在");
        }
        if (task.getStatus() == null || task.getStatus() != 1) {
            throw new RuntimeException("仅执行完成的记录可设置展示状态");
        }
        PyTask patch = new PyTask();
        patch.setId(taskId);
        patch.setIfShow(Boolean.TRUE.equals(ifShow));
        patch.setUpdateTime(new Date());
        pyTaskMapper.updateById(patch);
        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 执行记录展示名称：有值时仪表盘分组优先显示该名称；留空则回退「代码名+时间」。
     */
    public PyTaskVO updatePyTaskShowName(String taskId, String showName) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("执行记录不存在");
        }
        String normalized = showName == null ? "" : showName.trim();
        if (normalized.length() > 128) {
            throw new RuntimeException("展示名称最多 128 个字符");
        }
        // 允许清空为 null（updateById 默认忽略 null，需用 UpdateWrapper）
        com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<PyTask> uw =
                new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
        uw.eq("id", taskId)
                .set("show_name", normalized.isEmpty() ? null : normalized)
                .set("update_time", new Date());
        pyTaskMapper.update(null, uw);
        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 仿真仪表盘：列出状态为「展示」且执行成功的代码记录；
     * 分组名优先用自定义展示名称，否则为「代码名+记录时间」。
     */
    public List<DashboardSimulationVO> getDashboardSimulations() {
        List<PyTask> showTasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfShow, true)
                .eq(PyTask::getStatus, 1)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime));
        List<DashboardSimulationVO> result = new ArrayList<>();
        if (showTasks == null || showTasks.isEmpty()) {
            return result;
        }
        Map<String, Integer> nameCount = new HashMap<>();
        for (PyTask task : showTasks) {
            PyFile pyFile = pyFileMapper.selectById(task.getPyId());
            if (pyFile == null) {
                continue;
            }
            String groupName = buildDashboardGroupName(pyFile, task);
            Integer n = nameCount.getOrDefault(groupName, 0);
            nameCount.put(groupName, n + 1);
            if (n > 0) {
                // 同名冲突时附加时间，保证仪表盘分组 key 唯一
                String timeSuffix = task.getCreateTime() == null
                        ? task.getId()
                        : new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(task.getCreateTime());
                groupName = groupName + " · " + timeSuffix;
            }
            DashboardSimulationVO vo = new DashboardSimulationVO();
            vo.setGroupName(groupName);
            vo.setPyId(pyFile.getId());
            vo.setTaskId(task.getId());
            vo.setFileName(pyFile.getFileName());
            vo.setTaskCreateTime(task.getCreateTime());
            result.add(vo);
        }
        result.sort(Comparator.comparing(DashboardSimulationVO::getGroupName,
                Comparator.nullsLast(String::compareToIgnoreCase)));
        return result;
    }

    /**
     * 仿真仪表盘：加载指定成功任务目录下的 KPI 与 exported_data CSV。
     */
    public DashboardSimulationDetailVO getDashboardSimulationDetail(String taskId) throws IOException {
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

        DashboardSimulationDetailVO vo = new DashboardSimulationDetailVO();
        vo.setGroupName(buildDashboardGroupName(pyFile, task));
        vo.setPyId(pyFile.getId());
        vo.setTaskId(taskId);

        String kpisCsv = readExportedKpisCsv(taskDir, dataRoot);
        if (kpisCsv == null || kpisCsv.trim().isEmpty()) {
            kpisCsv = buildKpisCsvFromDb(pyFile.getId());
        }
        String normalizedKpisCsv = stripUtf8Bom(kpisCsv == null ? "" : kpisCsv);
        vo.setKpisCsv(normalizedKpisCsv);
        List<Map<String, String>> kpiRows = parseKpisCsvToRows(normalizedKpisCsv);
        if (kpiRows.isEmpty()) {
            kpiRows = buildKpiRowsFromDb(pyFile.getId());
        }
        vo.setKpiRows(kpiRows);

        Map<String, String> dataFiles = new LinkedHashMap<>();
        collectExportedDataCsv(dataRoot, dataFiles);
        if (dataFiles.isEmpty() && !dataRoot.equals(taskDir)) {
            collectExportedDataCsv(taskDir, dataFiles);
        }
        vo.setDataFiles(dataFiles);

        String chescaTraceCsv = readChescaTraceCsv(taskDir, dataRoot);
        vo.setChescaTraceCsv(stripUtf8Bom(chescaTraceCsv == null ? "" : chescaTraceCsv));
        String decisionTraceJson = readDecisionTraceJson(taskDir, dataRoot);
        vo.setDecisionTraceJson(stripUtf8Bom(decisionTraceJson == null ? "" : decisionTraceJson));

        String agentConfigJson = readAgentConfigJson(taskDir, dataRoot);
        vo.setAgentConfigJson(stripUtf8Bom(agentConfigJson == null ? "" : agentConfigJson));
        vo.setResmarlSummary(buildResmarlSummary(agentConfigJson));
        return vo;
    }

    private PyTask findLatestSuccessTaskByPyId(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getStatus, 1)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime)
                .last("LIMIT 1"));
        if (tasks == null || tasks.isEmpty()) {
            return null;
        }
        return tasks.get(0);
    }

    private String stripPyExtension(String fileName) {
        if (fileName == null || fileName.isEmpty()) {
            return "";
        }
        if (fileName.toLowerCase().endsWith(".py")) {
            return fileName.substring(0, fileName.length() - 3);
        }
        int dot = fileName.lastIndexOf('.');
        return dot > 0 ? fileName.substring(0, dot) : fileName;
    }

    /** 仪表盘分组名：有展示名称用展示名称，否则代码名 + 记录创建时间 */
    private String buildDashboardGroupName(PyFile pyFile, PyTask task) {
        if (task != null && task.getShowName() != null && !task.getShowName().trim().isEmpty()) {
            return task.getShowName().trim();
        }
        String fileName = pyFile == null ? null : pyFile.getFileName();
        Date createTime = task == null ? null : task.getCreateTime();
        return buildDashboardGroupName(fileName, createTime);
    }

    /** 仪表盘分组名回退：代码名 + 记录创建时间 */
    private String buildDashboardGroupName(String fileName, Date taskCreateTime) {
        String base = stripPyExtension(fileName);
        if (base == null || base.isEmpty()) {
            base = "未命名";
        }
        if (taskCreateTime == null) {
            return base;
        }
        return base + " " + new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(taskCreateTime);
    }

    private Path resolveSimulationDataRoot(Path taskDir) throws IOException {
        if (!Files.exists(taskDir)) {
            return taskDir;
        }
        if (hasExportedDataCsv(taskDir)) {
            return taskDir;
        }
        try (Stream<Path> children = Files.list(taskDir)) {
            List<Path> subdirs = children.filter(Files::isDirectory)
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .collect(Collectors.toList());
            for (Path sub : subdirs) {
                if (hasExportedDataCsv(sub)) {
                    return sub;
                }
            }
        }
        return taskDir;
    }

    private boolean hasExportedDataCsv(Path dir) throws IOException {
        if (!Files.isDirectory(dir)) {
            return false;
        }
        try (Stream<Path> stream = Files.list(dir)) {
            return stream.anyMatch(p -> Files.isRegularFile(p)
                    && p.getFileName().toString().startsWith("exported_data_")
                    && p.getFileName().toString().endsWith(".csv"));
        }
    }

    private Path findExportedKpisCsv(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("exported_kpis.csv");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("exported_kpis.csv");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "exported_kpis.csv".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readExportedKpisCsv(Path taskDir, Path dataRoot) throws IOException {
        Path kpiPath = findExportedKpisCsv(taskDir, dataRoot);
        if (kpiPath == null || !Files.exists(kpiPath)) {
            return "";
        }
        return new String(Files.readAllBytes(kpiPath), StandardCharsets.UTF_8);
    }

    private Path findChescaTraceCsv(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("chesca_trace.csv");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("chesca_trace.csv");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "chesca_trace.csv".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readChescaTraceCsv(Path taskDir, Path dataRoot) throws IOException {
        Path tracePath = findChescaTraceCsv(taskDir, dataRoot);
        if (tracePath == null || !Files.exists(tracePath)) {
            return "";
        }
        return new String(Files.readAllBytes(tracePath), StandardCharsets.UTF_8);
    }

    private Path findDecisionTraceJson(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("decision_trace.json");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("decision_trace.json");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "decision_trace.json".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readDecisionTraceJson(Path taskDir, Path dataRoot) throws IOException {
        Path jsonPath = findDecisionTraceJson(taskDir, dataRoot);
        if (jsonPath == null || !Files.exists(jsonPath)) {
            return "";
        }
        return new String(Files.readAllBytes(jsonPath), StandardCharsets.UTF_8);
    }

    private Path findAgentConfigJson(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("chesca_agent_config.json");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("chesca_agent_config.json");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "chesca_agent_config.json".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readAgentConfigJson(Path taskDir, Path dataRoot) throws IOException {
        Path path = findAgentConfigJson(taskDir, dataRoot);
        if (path == null || !Files.exists(path)) {
            return "";
        }
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> buildResmarlSummary(String agentConfigJson) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("enabled", false);
        summary.put("marlMode", "none");
        summary.put("alpha", 0.0);
        summary.put("label", "纯 CHESCA");
        if (agentConfigJson == null || agentConfigJson.trim().isEmpty()) {
            return summary;
        }
        try {
            Map<String, Object> cfg = JSON.parseObject(agentConfigJson, Map.class);
            if (cfg == null) {
                return summary;
            }
            Object enabledObj = cfg.get("resmarl_enabled");
            boolean enabled = enabledObj != null && (
                    Boolean.TRUE.equals(enabledObj)
                            || "true".equalsIgnoreCase(String.valueOf(enabledObj))
                            || "1".equals(String.valueOf(enabledObj))
            );
            String marlMode = "none";
            Object modeObj = cfg.get("marl_mode");
            if (modeObj != null && !String.valueOf(modeObj).trim().isEmpty()) {
                marlMode = String.valueOf(modeObj).trim().toLowerCase();
                if ("central_residual".equals(marlMode)) {
                    marlMode = "multi_agent";
                }
            } else if (enabled) {
                marlMode = "multi_agent";
            }
            double alpha = 0.0;
            Object alphaObj = cfg.get("residual_alpha");
            if (alphaObj instanceof Number) {
                alpha = ((Number) alphaObj).doubleValue();
            } else if (alphaObj != null) {
                try {
                    alpha = Double.parseDouble(String.valueOf(alphaObj));
                } catch (NumberFormatException ignored) {
                    alpha = 0.0;
                }
            }
            summary.put("enabled", enabled);
            summary.put("marlMode", marlMode);
            summary.put("alpha", alpha);
            if (!enabled || "none".equals(marlMode)) {
                summary.put("label", "纯 CHESCA");
            } else if (alpha <= 0) {
                summary.put("label", "CHESCA-ResMARL α=0");
            } else {
                Object epochs = cfg.get("multi_agent_train_epochs");
                String ep = epochs != null ? String.valueOf(epochs) : "20";
                summary.put("label", String.format("CHESCA-ResMARL α=%.2f(SAC %s轮)", alpha, ep));
            }
        } catch (Exception e) {
            // keep defaults
        }
        return summary;
    }

    private static String stripUtf8Bom(String text) {
        if (text == null || text.isEmpty()) {
            return "";
        }
        if (text.charAt(0) == '\ufeff') {
            return text.substring(1);
        }
        return text;
    }

    /**
     * 将 exported_kpis.csv 解析为表格行（保留空单元格为 ""）。
     */
    private List<Map<String, String>> parseKpisCsvToRows(String csv) {
        List<Map<String, String>> rows = new ArrayList<>();
        if (csv == null || csv.trim().isEmpty()) {
            return rows;
        }
        String[] lines = csv.trim().split("\\r?\\n");
        if (lines.length < 2) {
            return rows;
        }
        String[] headers = lines[0].split(",", -1);
        for (int i = 0; i < headers.length; i++) {
            headers[i] = headers[i].trim().replace("\ufeff", "");
        }
        if (headers.length == 0) {
            return rows;
        }
        String kpiKey = headers[0];
        for (int lineIdx = 1; lineIdx < lines.length; lineIdx++) {
            String line = lines[lineIdx].trim();
            if (line.isEmpty()) {
                continue;
            }
            String[] fields = line.split(",", -1);
            if (fields.length == 0) {
                continue;
            }
            String kpiName = fields[0].trim();
            if (kpiName.isEmpty()) {
                continue;
            }
            Map<String, String> row = new LinkedHashMap<>();
            row.put(kpiKey, kpiName);
            for (int col = 1; col < headers.length; col++) {
                String value = col < fields.length ? fields[col].trim() : "";
                row.put(headers[col], value);
            }
            rows.add(row);
        }
        return rows;
    }

    public List<Map<String, String>> getPyFileKpiRows(String pyId) {
        return buildKpiRowsFromDb(pyId);
    }

    /**
     * 从 kpis 表（agentType=pyId）构建 KPI 表格行，固定 21 项指标。
     */
    private List<Map<String, String>> buildKpiRowsFromDb(String pyId) {
        List<Kpis> kpisList = kpisMapper.selectList(new QueryWrapper<Kpis>().lambda()
                .eq(Kpis::getAgentType, pyId));
        if (kpisList == null || kpisList.isEmpty()) {
            return new ArrayList<>();
        }
        JSONArray arr = JSON.parseArray(JSON.toJSONString(kpisList));
        String[] buildingNames = {"Building_1", "Building_2", "Building_3", "District"};
        JSONObject[] byBuilding = new JSONObject[4];
        for (int i = 0; i < arr.size(); i++) {
            JSONObject row = arr.getJSONObject(i);
            String name = row.getString("name");
            for (int j = 0; j < buildingNames.length; j++) {
                if (buildingNames[j].equals(name)) {
                    byBuilding[j] = row;
                }
            }
        }
        List<Map<String, String>> rows = new ArrayList<>();
        for (int i = 0; i < LINE_TITLE.size(); i++) {
            String field = LINE_TITLE.get(i);
            String snake = camelToSnake(field);
            Map<String, String> row = new LinkedHashMap<>();
            row.put("KPI", snake);
            for (int j = 0; j < buildingNames.length; j++) {
                String value = "";
                if (byBuilding[j] != null) {
                    BigDecimal v = byBuilding[j].getBigDecimal(field);
                    if (v != null) {
                        value = v.stripTrailingZeros().toPlainString();
                    }
                }
                row.put(buildingNames[j], value);
            }
            rows.add(row);
        }
        return rows;
    }

    /**
     * 任务目录无 exported_kpis.csv 时，从 kpis 表按 agentType=pyId 还原 CSV。
     */
    private String buildKpisCsvFromDb(String pyId) {
        List<Kpis> kpisList = kpisMapper.selectList(new QueryWrapper<Kpis>().lambda()
                .eq(Kpis::getAgentType, pyId));
        if (kpisList == null || kpisList.isEmpty()) {
            return "";
        }
        JSONArray arr = JSON.parseArray(JSON.toJSONString(kpisList));
        String[] buildingNames = {"Building_1", "Building_2", "Building_3", "District"};
        JSONObject[] byBuilding = new JSONObject[4];
        for (int i = 0; i < arr.size(); i++) {
            JSONObject row = arr.getJSONObject(i);
            String name = row.getString("name");
            for (int j = 0; j < buildingNames.length; j++) {
                if (buildingNames[j].equals(name)) {
                    byBuilding[j] = row;
                }
            }
        }
        StringBuilder sb = new StringBuilder("KPI,Building_1,Building_2,Building_3,District\n");
        for (int i = 0; i < LINE_TITLE.size(); i++) {
            String field = LINE_TITLE.get(i);
            String snake = camelToSnake(field);
            sb.append(snake);
            for (JSONObject building : byBuilding) {
                sb.append(",");
                if (building == null) {
                    continue;
                }
                BigDecimal value = building.getBigDecimal(field);
                if (value != null) {
                    sb.append(value.stripTrailingZeros().toPlainString());
                }
            }
            sb.append("\n");
        }
        return sb.toString();
    }

    private static String camelToSnake(String camel) {
        if (camel == null || camel.isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < camel.length(); i++) {
            char c = camel.charAt(i);
            if (Character.isUpperCase(c) && i > 0) {
                sb.append('_');
            }
            sb.append(Character.toLowerCase(c));
        }
        return sb.toString();
    }

    private void collectExportedDataCsv(Path dir, Map<String, String> dataFiles) throws IOException {
        if (!Files.isDirectory(dir)) {
            return;
        }
        try (Stream<Path> stream = Files.list(dir)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return name.startsWith("exported_data_") && name.endsWith(".csv");
                    })
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .forEach(p -> {
                        try {
                            dataFiles.put(p.getFileName().toString(),
                                    new String(Files.readAllBytes(p), StandardCharsets.UTF_8));
                        } catch (IOException e) {
                            log.warn("读取仿真数据文件失败: {}", p, e);
                        }
                    });
        }
    }

    /**
     * 异步启动 Python 脚本：创建 pyTask 后立即返回，结果通过 getPyTaskResult 查询。
     */
    public PyTaskVO runPyFile(PyFileParam pyFileParam) {
        PyFile pyFile = pyFileMapper.selectById(pyFileParam.getId());
        if (pyFile == null) {
            throw new RuntimeException("Python 文件不存在");
        }
        if (getRunningPyTask(pyFile.getId()) != null) {
            throw new RuntimeException("该 Python 文件已有任务正在执行中");
        }

        Path scriptPath = Paths.get(fileResourceProperties.getPythonFilePath(), pyFile.getFileName()).normalize();

        String taskId = getUUID();

        insertPyTask(taskId, pyFile.getId());
        CONSOLE_MAP.put(taskId, Collections.synchronizedList(new ArrayList<>()));
        CONSOLE_INDEX_MAP.put(taskId, 0);
        TASK_OUTPUT_BUFFER.put(taskId, new StringBuilder());

        final String scriptToRun;
        final String taskOutputDir;
        try {
            scriptToRun = copyPythonScriptForTask(scriptPath.toString(), taskId);
            taskOutputDir = getTaskDir(taskId).toAbsolutePath().toString();
        } catch (IOException e) {
            markPyTaskFailed(taskId, "复制 Python 脚本失败: " + e.getMessage());
            throw new RuntimeException("复制 Python 脚本到任务目录失败", e);
        }

        final String pyFileId = pyFile.getId();
        final String pyFileName = pyFile.getFileName();
        pythonTaskExecutor.execute(() -> runPythonTaskAsync(scriptToRun, taskId, pyFileId, taskOutputDir, pyFileName));

        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 查询异步任务状态与结果（执行中可轮询；完成后含 KPI 与完整输出）。
     */
    public PyTaskVO getPyTaskResult(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        String output = getLiveTaskOutput(taskId);
        if (output == null) {
            output = "";
        }
        String errorMessage = readTaskErrorLog(taskId);
        List<KpisTransVO> kpis = null;
        if (Integer.valueOf(1).equals(task.getStatus())) {
            kpis = getKpis(task.getPyId());
        }
        return buildPyTaskVO(task, output, errorMessage, kpis);
    }

    /**
     * 查询指定 Python 文件的全部任务记录，按创建时间倒序。
     */
    public List<PyTaskVO> getPyTaskList(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime));
        if (tasks == null || tasks.isEmpty()) {
            return new ArrayList<>();
        }
        List<PyTaskVO> result = new ArrayList<>();
        for (PyTask task : tasks) {
            result.add(buildPyTaskVO(task, null, null));
        }
        return result;
    }

    /**
     * 读取任务输出目录中复制的 Python 脚本内容。
     */
    public PyTaskScriptVO getPyTaskScript(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            throw new RuntimeException("关联 Python 文件不存在");
        }
        Path taskDir = getTaskDir(taskId);
        if (!Files.exists(taskDir)) {
            throw new RuntimeException("任务输出目录不存在: " + taskDir);
        }
        Path scriptPath = taskDir.resolve(pyFile.getFileName());
        if (!Files.exists(scriptPath)) {
            try (Stream<Path> paths = Files.list(taskDir)) {
                scriptPath = paths
                        .filter(p -> Files.isRegularFile(p) && p.getFileName().toString().endsWith(".py"))
                        .findFirst()
                        .orElse(null);
            } catch (IOException e) {
                throw new RuntimeException("读取任务目录失败", e);
            }
        }
        if (scriptPath == null || !Files.exists(scriptPath)) {
            throw new RuntimeException("任务目录中未找到 Python 脚本");
        }
        try {
            PyTaskScriptVO vo = new PyTaskScriptVO();
            vo.setTaskId(taskId);
            vo.setFileName(scriptPath.getFileName().toString());
            vo.setCode(new String(Files.readAllBytes(scriptPath), StandardCharsets.UTF_8));
            return vo;
        } catch (IOException e) {
            throw new RuntimeException("读取任务 Python 脚本失败", e);
        }
    }

    /**
     * 查询指定 Python 文件当前是否有执行中的任务（status=0）。
     */
    public PyTaskVO getRunningPyTask(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getStatus, 0)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime)
                .last("LIMIT 1"));
        if (tasks == null || tasks.isEmpty()) {
            return null;
        }
        return buildPyTaskVO(tasks.get(0), null, null);
    }

    private void insertPyTask(String taskId, String pyId) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setPyId(pyId);
        task.setStatus(0);
        task.setIfDelete(false);
        task.setIfShow(false);
        task.setCreateTime(new Date());
        pyTaskMapper.insert(task);
    }

    private void markPyTaskSuccess(String taskId) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setStatus(1);
        task.setUpdateTime(new Date());
        pyTaskMapper.updateById(task);
    }

    private void markPyTaskFailed(String taskId, String errorMessage) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setStatus(2);
        task.setUpdateTime(new Date());
        pyTaskMapper.updateById(task);
        saveTaskErrorLog(taskId, errorMessage);
        List<String> consoleList = CONSOLE_MAP.get(taskId);
        if (consoleList != null) {
            consoleList.add("$error");
        }
    }

    private void runPythonTaskAsync(String scriptToRun, String taskId, String pyFileId,
                                    String taskOutputDir, String pyFileName) {
        try {
            List<String> extraArgs = new ArrayList<>();
            extraArgs.add("--output-dir");
            extraArgs.add(taskOutputDir);
            if ("local_evaluation_copy.py".equalsIgnoreCase(pyFileName)) {
                String minSocConfigPath = batteryMinSocConfigService.writeConfigJsonToTaskDir(taskOutputDir);
                extraArgs.add("--min-soc-config");
                extraArgs.add(minSocConfigPath);
                log.info("已写入 CHESCA 电池 SOC 配置: {}", minSocConfigPath);
            }
            String result = runPythonProcess(scriptToRun, taskId, extraArgs.toArray(new String[0]));
            saveTaskOutputLog(taskId, result);
            parseAndSaveKpis(result, pyFileId);
            markPyTaskSuccess(taskId);
            List<String> consoleList = CONSOLE_MAP.get(taskId);
            if (consoleList != null) {
                consoleList.add("$end-1");
            }
        } catch (Exception e) {
            log.error("Python 异步任务失败, taskId={}", taskId, e);
            markPyTaskFailed(taskId, e.getMessage());
        }
    }

    private void parseAndSaveKpis(String result, String agentType) {
        List<Kpis> kpisList = new ArrayList<>();
        kpisList.add(new Kpis() {{ setName("Building_1"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("Building_2"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("Building_3"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("District"); setAgentType(agentType); }});

        try (BufferedReader reader = new BufferedReader(new StringReader(result))) {
            String line;
            int flag = 0;
            while ((line = reader.readLine()) != null) {
                if ("outputkpi".equals(line)) {
                    flag = 1;
                    continue;
                }
                if (flag == 1) {
                    line = line.trim();
                    if (!shouldParseKpiLine(line)) {
                        continue;
                    }
                    line = line.replaceAll("\\s+", " ");
                    String kpiName = line.split(" ", 2)[0];
                    List<String> values = extractKpiMetricValues(line, kpiName);
                    if (values.size() >= 4) {
                        kpiConsumer.accept(kpiName, kpisList, values.subList(0, 4));
                    }
                }
            }
            kpisMapper.delete(new QueryWrapper<Kpis>().lambda().eq(Kpis::getAgentType, agentType));
            kpisMapper.insert(kpisList);
        } catch (IOException e) {
            throw new RuntimeException("解析 KPI 结果时发生异常", e);
        }
    }

    private Path getTaskDir(String taskId) {
        return Paths.get(fileResourceProperties.getOutFilePath(), "outkpis", taskId);
    }

    private void saveTaskOutputLog(String taskId, String output) throws IOException {
        Path dir = getTaskDir(taskId);
        Files.createDirectories(dir);
        Files.write(dir.resolve("output.log"), output.getBytes(StandardCharsets.UTF_8));
    }

    private void saveTaskErrorLog(String taskId, String errorMessage) {
        try {
            Path dir = getTaskDir(taskId);
            Files.createDirectories(dir);
            Files.write(dir.resolve("error.log"),
                    (errorMessage == null ? "" : errorMessage).getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            log.warn("写入任务错误日志失败, taskId={}", taskId, e);
        }
    }

    /**
     * 仅查询任务控制台输出与状态（供前端高频轮询）。
     */
    public PyTaskVO getPyTaskOutput(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        String output = getLiveTaskOutput(taskId);
        PyTaskVO vo = new PyTaskVO();
        vo.setTaskId(task.getId());
        vo.setPyId(task.getPyId());
        vo.setStatus(task.getStatus());
        vo.setStatusDesc(PyTaskVO.statusDescOf(task.getStatus()));
        vo.setOutput(output == null ? "" : output);
        vo.setErrorMessage(readTaskErrorLog(taskId));
        return vo;
    }

    /**
     * 读取任务实时/最终控制台输出（内存缓冲 + output.log，取内容更完整的一份）。
     */
    private String getLiveTaskOutput(String taskId) {
        StringBuilder buffer = TASK_OUTPUT_BUFFER.get(taskId);
        if (buffer != null) {
            synchronized (buffer) {
                if (buffer.length() > 0) {
                    return buffer.toString();
                }
            }
        }
        String file = readTaskOutputLog(taskId);
        if (file != null && !file.isEmpty()) {
            return file;
        }
        return readTaskConsoleFull(taskId);
    }

    private String readTaskOutputLog(String taskId) {
        Path path = getTaskDir(taskId).resolve("output.log");
        if (!Files.exists(path)) {
            return null;
        }
        try {
            return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.warn("读取任务输出日志失败, taskId={}", taskId, e);
            return null;
        }
    }

    /**
     * 读取任务已累计的全部控制台输出（不消耗增量游标）。
     */
    private String readTaskConsoleFull(String taskId) {
        List<String> list = CONSOLE_MAP.get(taskId);
        if (list == null || list.isEmpty()) {
            return null;
        }
        StringBuilder sb = new StringBuilder();
        synchronized (list) {
            for (String line : list) {
                if ("$end-1".equals(line) || "$error".equals(line) || "$exitcode".equals(line)) {
                    continue;
                }
                sb.append(line);
            }
        }
        return sb.length() > 0 ? sb.toString() : null;
    }

    private String readTaskErrorLog(String taskId) {
        Path path = getTaskDir(taskId).resolve("error.log");
        if (!Files.exists(path)) {
            return null;
        }
        try {
            return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.warn("读取任务错误日志失败, taskId={}", taskId, e);
            return null;
        }
    }

    private PyTaskVO buildPyTaskVO(PyTask task, String output, String errorMessage) {
        return buildPyTaskVO(task, output, errorMessage, null);
    }

    private PyTaskVO buildPyTaskVO(PyTask task, String output, String errorMessage, List<KpisTransVO> kpis) {
        PyTaskVO vo = new PyTaskVO();
        vo.setTaskId(task.getId());
        vo.setPyId(task.getPyId());
        vo.setStatus(task.getStatus());
        vo.setStatusDesc(PyTaskVO.statusDescOf(task.getStatus()));
        vo.setIfShow(Boolean.TRUE.equals(task.getIfShow()));
        vo.setShowName(task.getShowName());
        vo.setOutput(output);
        vo.setErrorMessage(errorMessage);
        vo.setKpis(kpis);
        vo.setCreateTime(task.getCreateTime());
        vo.setUpdateTime(task.getUpdateTime());
        return vo;
    }

    private void appendTaskOutputLine(String taskId, String line, StringBuilder output, List<String> consoleList, Path liveLogPath) {
        String lineWithNewline = line + "\n";
        output.append(lineWithNewline);
        if (taskId != null) {
            StringBuilder buffer = TASK_OUTPUT_BUFFER.get(taskId);
            if (buffer != null) {
                synchronized (buffer) {
                    buffer.append(lineWithNewline);
                }
            }
        }
        if (consoleList != null) {
            consoleList.add(lineWithNewline);
        }
        if (liveLogPath != null) {
            try {
                Files.write(liveLogPath, lineWithNewline.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                log.debug("写入 output.log 失败（可能正在被读取）, taskId={}", taskId);
            }
        }
    }

    private String runPythonProcess(String scriptPath, String taskId, String... extraArgs)
            throws IOException, InterruptedException {
        StringBuilder output = new StringBuilder();
        List<String> command = new ArrayList<>();
        command.add(PYTHON_PATH);
        command.add("-u");
        command.add(scriptPath);
        if (extraArgs != null) {
            Collections.addAll(command, extraArgs);
        }
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Map<String, String> env = pb.environment();
        env.put("PYTHONUNBUFFERED", "1");
        env.put("PYTHONIOENCODING", "utf-8");
        env.put("PYTHONUTF8", "1");
        env.put("NO_COLOR", "1");
        Process process = pb.start();

        List<String> consoleList = taskId != null ? CONSOLE_MAP.get(taskId) : null;
        Path liveLogPath = taskId != null ? getTaskDir(taskId).resolve("output.log") : null;
        if (liveLogPath != null && Files.exists(liveLogPath)) {
            Files.delete(liveLogPath);
        }

        Thread stdoutThread = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    synchronized (output) {
                        appendTaskOutputLine(taskId, line, output, consoleList, liveLogPath);
                    }
                }
            } catch (IOException e) {
                log.error("读取 Python 标准输出失败, taskId={}", taskId, e);
            }
        }, "python-stdout-" + (taskId != null ? taskId : "sync"));
        stdoutThread.setDaemon(true);
        stdoutThread.start();

        int exitCode = process.waitFor();
        stdoutThread.join(600_000);

        if (exitCode != 0) {
            if (consoleList != null) {
                consoleList.add("$exitcode");
            }
            throw new RuntimeException("Python脚本执行失败，退出码：" + exitCode);
        }
        synchronized (output) {
            return output.toString().trim();
        }
    }

    @FunctionalInterface
    interface BiConsumer<T1,T2>{
        void accept(T1 a, T2 b);
    }

    @FunctionalInterface
    interface TriConsumer<T1,T2,T3>{
        void accept(T1 a, T2 b,T3 c);
    }



    private static final Pattern KPI_NUMBER_TOKEN = Pattern.compile(
            "^(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?|NaN|nan)$");

    private static boolean shouldParseKpiLine(String line) {
        if (line == null || line.isEmpty()) {
            return false;
        }
        if (line.startsWith("[") || line.startsWith("|") || line.startsWith("---")) {
            return false;
        }
        if (line.contains("rows x") || line.contains("columns]")) {
            return false;
        }
        if (line.startsWith("name ") || "cost_function".equals(line)) {
            return false;
        }
        if (line.contains("输出目录") || line.contains("KPI 文件") || line.contains("Writing buffered")) {
            return false;
        }
        String normalized = line.replaceAll("\\s+", " ");
        String kpiName = normalized.split(" ", 2)[0];
        return kpiConsumerMap.containsKey(kpiName);
    }

    private static List<String> extractKpiMetricValues(String line, String kpiName) {
        String rest = line.substring(line.indexOf(kpiName) + kpiName.length()).trim();
        List<String> values = new ArrayList<>();
        for (String token : rest.split("\\s+")) {
            if (token.isEmpty()) {
                continue;
            }
            if ("...".equals(token)) {
                values.add("NaN");
                continue;
            }
            if (KPI_NUMBER_TOKEN.matcher(token).matches()) {
                values.add(token);
            }
        }
        while (values.size() < 4) {
            values.add("NaN");
        }
        return values;
    }

    private static BigDecimal stringToBigDecimal(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String cleaned = value.trim();
        if ("NaN".equalsIgnoreCase(cleaned) || "nan".equalsIgnoreCase(cleaned)
                || "...".equals(cleaned) || "-".equals(cleaned)) {
            return null;
        }
        if ("inf".equalsIgnoreCase(cleaned) || "-inf".equalsIgnoreCase(cleaned)
                || "+inf".equalsIgnoreCase(cleaned)) {
            return null;
        }
        try {
            return new BigDecimal(cleaned);
        } catch (NumberFormatException e) {
            log.warn("无法解析 KPI 数值: {}", value);
            return null;
        }
    }

    private static Map<String, BiConsumer<Kpis,String>> kpiConsumerMap = new HashMap<String, BiConsumer<Kpis,String>>(){{
        put("all_time_peak_average", (kpis,value) -> kpis.setAllTimePeakAverage(stringToBigDecimal(value)));
        put("annual_normalized_unserved_energy_total", (kpis,value) -> kpis.setAnnualNormalizedUnservedEnergyTotal(stringToBigDecimal(value)));
        put("carbon_emissions_total", (kpis,value) -> kpis.setCarbonEmissionsTotal(stringToBigDecimal(value)));
        put("cost_total", (kpis,value) -> kpis.setCostTotal(stringToBigDecimal(value)));
        put("daily_one_minus_load_factor_average", (kpis,value) -> kpis.setDailyOneMinusLoadFactorAverage(stringToBigDecimal(value)));
        put("daily_peak_average", (kpis,value) -> kpis.setDailyPeakAverage(stringToBigDecimal(value)));
        put("discomfort_cold_delta_average", (kpis,value) -> kpis.setDiscomfortColdDeltaAverage(stringToBigDecimal(value)));
        put("discomfort_cold_delta_maximum", (kpis,value) -> kpis.setDiscomfortColdDeltaMaximum(stringToBigDecimal(value)));
        put("discomfort_cold_delta_minimum", (kpis,value) -> kpis.setDiscomfortColdDeltaMinimum(stringToBigDecimal(value)));
        put("discomfort_cold_proportion", (kpis,value) -> kpis.setDiscomfortColdProportion(stringToBigDecimal(value)));
        put("discomfort_hot_delta_average", (kpis,value) -> kpis.setDiscomfortHotDeltaAverage(stringToBigDecimal(value)));
        put("discomfort_hot_delta_maximum", (kpis,value) -> kpis.setDiscomfortHotDeltaMaximum(stringToBigDecimal(value)));
        put("discomfort_hot_delta_minimum", (kpis,value) -> kpis.setDiscomfortHotDeltaMinimum(stringToBigDecimal(value)));
        put("discomfort_hot_proportion", (kpis,value) -> kpis.setDiscomfortHotProportion(stringToBigDecimal(value)));
        put("discomfort_proportion", (kpis,value) -> kpis.setDiscomfortProportion(stringToBigDecimal(value)));
        put("electricity_consumption_total", (kpis,value) -> kpis.setElectricityConsumptionTotal(stringToBigDecimal(value)));
        put("monthly_one_minus_load_factor_average", (kpis,value) -> kpis.setMonthlyOneMinusLoadFactorAverage(stringToBigDecimal(value)));
        put("one_minus_thermal_resilience_proportion", (kpis,value) -> kpis.setOneMinusThermalResilienceProportion(stringToBigDecimal(value)));
        put("power_outage_normalized_unserved_energy_total", (kpis,value) -> kpis.setPowerOutageNormalizedUnservedEnergyTotal(stringToBigDecimal(value)));
        put("ramping_average", (kpis,value) -> kpis.setRampingAverage(stringToBigDecimal(value)));
        put("zero_net_energy", (kpis,value) -> kpis.setZeroNetEnergy(stringToBigDecimal(value)));

    }};

    private static final TriConsumer<String,List<Kpis>,List<String>> kpiConsumer = (kpiName ,kpiList, valueList) -> {
        if(null!=kpiConsumerMap.get(kpiName)) {
            for(int i=0;i<4;i++) {
                kpiConsumerMap.get(kpiName).accept(kpiList.get(i), valueList.get(i));
            }
        }

    };

    private static final Map<String,String> scriptMap=new HashMap<String,String>(){{
        put("baseLine","NOCONTROL.py");
        put("diSac","DISAC.py");
        put("multi","Multi-agent.py");
        put("single","Single-agent.py");
    }};
    public void updateLearn(String agentType) {
        String baseScriptPath="D:/Users/clfbe/anaconda3/envs/cl2/Lib/site-packages/citylearn/apply/";

        String fileName=scriptMap.get(agentType);
        if(null==fileName){
            return;
        }
        String scriptPath=baseScriptPath+fileName;

        //D:\Users\clfbe\anaconda3\envs\cl2\Lib\site-packages\citylearn\apply\NOCONTROL.py
        String result = executePythonScript(scriptPath, null, null);
        parseAndSaveKpis(result, agentType);
    }

    /**
     * 将 Python 脚本复制到任务目录：{outFilePath}/outkpis/{taskId}/
     *
     * @return 复制后的脚本绝对路径
     */
    private String copyPythonScriptForTask(String scriptPath, String taskId) throws IOException {
        Path source = Paths.get(scriptPath);
        if (!Files.exists(source)) {
            throw new RuntimeException("Python脚本不存在: " + scriptPath);
        }
        Path targetDir = Paths.get(fileResourceProperties.getOutFilePath(), "outkpis", taskId);
        Files.createDirectories(targetDir);
        Path target = targetDir.resolve(source.getFileName());
        Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
        log.info("已复制 Python 脚本: {} -> {}", source, target);
        return target.toAbsolutePath().toString();
    }

    /**
     * 同步执行 Python（用于 updateLearn 等内部调用，不创建 pyTask）。
     */
    public String executePythonScript(String scriptPath, String taskId, PyFile pyFile) {
        if (taskId != null) {
            throw new IllegalArgumentException("带 taskId 的执行请使用 runPyFile 异步接口");
        }
        try {
            String result = runPythonProcess(scriptPath, null);
            System.out.println(result);
            Files.write(Paths.get("D:/output.txt"), result.getBytes(StandardCharsets.UTF_8));
            return result;
        } catch (IOException | InterruptedException e) {
            throw new RuntimeException("执行Python脚本时发生异常", e);
        }
    }

    public void executePythonScriptNow(String scriptPath,String taskId) {
        List<String> list=CONSOLE_MAP.get(taskId);
        StringBuilder output = new StringBuilder();
        try {
            ProcessBuilder pb = new ProcessBuilder(PYTHON_PATH, scriptPath);
            pb.redirectErrorStream(true); // 合并标准输出和错误输出
            Process process = pb.start();

            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;

            while ((line = reader.readLine()) != null) {

               list.add(line+"\n");
            }

            int exitCode = process.waitFor(); // 等待脚本执行完成
            if (exitCode != 0) {
                list.add("$exitcode");
                throw new RuntimeException("Python脚本执行失败，退出码：" + exitCode);
            }
            list.add("$end-1");
        } catch (IOException | InterruptedException e) {
            list.add("$error");
            throw new RuntimeException("执行Python脚本时发生异常", e);
        }
    }

    public String getConsoleInfo(String taskId){
        Integer index=CONSOLE_INDEX_MAP.get(taskId);
        List<String> list=CONSOLE_MAP.get(taskId);
        if(null==index || index.equals(-1)){
            return "null";
        }
        StringBuilder sb=new StringBuilder();
        while(index<list.size()){
            String str=list.get(index);
            if("$end-1".equals(str) || "$error".equals(str) || "$exitcode".equals(str)){
                CONSOLE_INDEX_MAP.put(taskId,-1);
            }else{
                sb.append(list.get(index++));
            }
        }
        if(!CONSOLE_INDEX_MAP.get(taskId).equals(-1)){
            CONSOLE_INDEX_MAP.put(taskId,index);
        }
        return sb.toString();
    }

    /**
     * α 扫描 registry：citylearnpy/ablation_results/registry/index.json
     */
    public List<Map<String, Object>> listAlphaSweepRuns() {
        Path indexPath = getAlphaSweepRegistryIndexPath();
        if (!Files.isRegularFile(indexPath)) {
            return Collections.emptyList();
        }
        try {
            String text = new String(Files.readAllBytes(indexPath), StandardCharsets.UTF_8);
            if (text.startsWith("\uFEFF")) {
                text = text.substring(1);
            }
            Object parsed = JSON.parse(text);
            if (parsed instanceof JSONArray) {
                return toMapList((JSONArray) parsed);
            }
            if (parsed instanceof JSONObject) {
                JSONArray runs = ((JSONObject) parsed).getJSONArray("runs");
                return runs == null ? Collections.emptyList() : toMapList(runs);
            }
        } catch (Exception e) {
            log.warn("读取 α 扫描 registry 失败: {}", e.getMessage());
        }
        return Collections.emptyList();
    }

    public Map<String, Object> getAlphaSweepDetail(String runId) throws IOException {
        if (runId == null || runId.trim().isEmpty()) {
            throw new IllegalArgumentException("runId 不能为空");
        }
        List<Map<String, Object>> runs = listAlphaSweepRuns();
        Map<String, Object> entry = null;
        for (Map<String, Object> r : runs) {
            if (runId.equals(String.valueOf(r.get("run_id")))) {
                entry = r;
                break;
            }
        }
        Path summaryPath = null;
        Path pyRoot = Paths.get(fileResourceProperties.getPythonFilePath()).normalize();
        if (entry != null && entry.get("rel_dir") != null) {
            summaryPath = pyRoot.resolve(String.valueOf(entry.get("rel_dir")))
                    .resolve(entry.get("summary_file") != null
                            ? String.valueOf(entry.get("summary_file"))
                            : "alpha_sweep_summary.json")
                    .normalize();
        }
        if (summaryPath == null || !Files.isRegularFile(summaryPath)) {
            // 兜底：按 run_id 目录扫描
            Path candidate = pyRoot.resolve("ablation_results").resolve(runId).resolve("alpha_sweep_summary.json");
            if (Files.isRegularFile(candidate)) {
                summaryPath = candidate;
            }
        }
        if (summaryPath == null || !Files.isRegularFile(summaryPath)) {
            throw new FileNotFoundException("未找到 α 扫描结果: " + runId);
        }
        String text = new String(Files.readAllBytes(summaryPath), StandardCharsets.UTF_8);
        if (text.startsWith("\uFEFF")) {
            text = text.substring(1);
        }
        JSONObject obj = JSON.parseObject(text);
        Map<String, Object> result = new LinkedHashMap<>(obj);
        result.put("_summary_path", summaryPath.toAbsolutePath().toString());
        return result;
    }

    private Path getAlphaSweepRegistryIndexPath() {
        return Paths.get(fileResourceProperties.getPythonFilePath(), "ablation_results", "registry", "index.json")
                .normalize();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> toMapList(JSONArray arr) {
        List<Map<String, Object>> list = new ArrayList<>();
        if (arr == null) {
            return list;
        }
        for (int i = 0; i < arr.size(); i++) {
            Object item = arr.get(i);
            if (item instanceof Map) {
                list.add(new LinkedHashMap<>((Map<String, Object>) item));
            } else if (item instanceof JSONObject) {
                list.add(new LinkedHashMap<String, Object>(((JSONObject) item)));
            }
        }
        return list;
    }
}
