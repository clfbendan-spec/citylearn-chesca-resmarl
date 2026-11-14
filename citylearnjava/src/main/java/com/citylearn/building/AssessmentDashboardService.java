package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import javax.annotation.Resource;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;

@Service
public class AssessmentDashboardService {
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;
    @Resource private com.citylearn.service.CitylearnDatasetService datasetService;

    static boolean isComparisonVisible(Map<?, ?> item) {
        return "succeeded".equals(item.get("status"))
                && !Boolean.TRUE.equals(item.get("dashboard_hidden"));
    }

    public List<DashboardSimulationVO> list(){
        return list(true);
    }

    public List<DashboardSimulationVO> list(boolean shownOnly){
        List<DashboardSimulationVO> options=new ArrayList<>();
        jdbc.query("SELECT r.id,r.create_time,r.result_json,c.name,d.name AS dataset_name FROM community_assessment_run r JOIN managed_community c ON c.id=r.community_id LEFT JOIN community_dataset_release d ON d.id=r.release_id WHERE r.status='succeeded' ORDER BY r.create_time DESC",rs->{
            try{
                Map<?,?> report=mapper.readValue(rs.getString("result_json"),Map.class);
                List<Map<?,?>> cases=new ArrayList<>();
                if(report.get("baseline") instanceof Map)cases.add((Map<?,?>)report.get("baseline"));
                if(report.get("cases") instanceof List)for(Object item:(List<?>)report.get("cases"))if(item instanceof Map)cases.add((Map<?,?>)item);
                for(Map<?,?> item:cases)if("succeeded".equals(item.get("status")) && (!shownOnly || isComparisonVisible(item))){
                    DashboardSimulationVO vo=new DashboardSimulationVO();vo.setTaskId("community:"+rs.getString("id")+":"+item.get("id"));vo.setPyId("community");vo.setFileName(Objects.toString(item.get("label")));vo.setGroupName(rs.getString("name")+" · "+item.get("label")+" · "+rs.getTimestamp("create_time")+" · "+rs.getString("id").substring(0,8));vo.setTaskCreateTime(rs.getTimestamp("create_time"));options.add(vo);
                    vo.setRecordName(rs.getString("name") + " · " + item.get("label"));
                    vo.setEvaluationDataset(rs.getString("dataset_name"));
                    if (item.get("metrics") instanceof Map)
                        com.citylearn.common.DashboardKpiSummary.apply(vo, (Map<?, ?>) item.get("metrics"));
                }
            }catch(IOException error){throw new IllegalStateException("评估记录无效",error);}
        });
        return options;
    }

    public DashboardSimulationDetailVO detail(String key) throws IOException {
        return detail(key, false);
    }

    public DashboardSimulationDetailVO detail(String key, boolean pagedTrace) throws IOException {
        String[] parts=key.split(":",3);
        if(parts.length<2 || !"community".equals(parts[0]))throw new IllegalArgumentException("无效评估记录");
        String id=parts[1], caseId=parts.length==3?parts[2]:"chesca";
        if(!id.matches("[a-f0-9-]{36}")||!caseId.matches("[a-z_]+"))throw new IllegalArgumentException("无效评估记录");
        Map<String,Object> row=jdbc.queryForMap("SELECT r.result_json,r.config_json,c.name,JSON_UNQUOTE(JSON_EXTRACT(c.metadata,'$.currency')) AS currency,d.schema_key FROM community_assessment_run r JOIN managed_community c ON c.id=r.community_id LEFT JOIN community_dataset_release d ON d.id=r.release_id WHERE r.id=? AND r.status='succeeded'",id);
        Map<?,?> result=mapper.readValue(row.get("result_json").toString(),Map.class);
        List<Map<?,?>> candidates=new ArrayList<>();
        if(result.get("baseline") instanceof Map)candidates.add((Map<?,?>)result.get("baseline"));
        if(result.get("cases") instanceof List)for(Object item:(List<?>)result.get("cases"))if(item instanceof Map)candidates.add((Map<?,?>)item);
        Map<?,?> selected=candidates.stream().filter(item->caseId.equals(item.get("id"))).findFirst().orElse(Map.of());
        if(selected.isEmpty()||!"succeeded".equals(selected.get("status")))throw new IllegalArgumentException("该方案不存在或未成功完成");
        DashboardSimulationDetailVO vo=new DashboardSimulationDetailVO();
        vo.setTaskId(key);vo.setPyId("community");vo.setGroupName(row.get("name")+" · "+Objects.toString(selected.get("label"),caseId));
        vo.setAgentConfigJson(row.get("config_json").toString());
        String currency = datasetService.resolveCurrency(Objects.toString(row.get("schema_key"), ""));
        vo.setCurrency(currency == null ? Objects.toString(row.get("currency"), null) : currency);
        List<Map<String,String>> kpis=new ArrayList<>();
        if(selected.get("metrics") instanceof Map){
            Map<?,?> metrics=(Map<?,?>)selected.get("metrics");
            addKpi(kpis,"District",metrics);
            if(metrics.get("buildings") instanceof List)for(Object building:(List<?>)metrics.get("buildings"))if(building instanceof Map)addKpi(kpis,Objects.toString(((Map<?,?>)building).get("name")),(Map<?,?>)building);
        }
        List<Map<String,String>> pivot=new ArrayList<>();
        for(String metric:List.of("cost_total","discomfort_proportion","score")){
            Map<String,String> line=new LinkedHashMap<>();line.put("KPI",metric);
            for(Map<String,String> value:kpis)line.put(value.get("algorithm"),value.get(metric));
            pivot.add(line);
        }
        vo.setKpiRows(pivot);
        Path root=Paths.get(files.getPythonFilePath()).toAbsolutePath().resolve("outputs/community-assessments").resolve(id);
        Path directory=root.resolve("cases").resolve(caseId);
        if(Files.isDirectory(directory)){
            try(java.util.stream.Stream<Path> stream=Files.list(directory)){
                for(Path file:(Iterable<Path>)stream::iterator){String name=file.getFileName().toString();if(name.startsWith("exported_data_")&&name.endsWith(".csv"))vo.getDataFiles().put(name,Files.readString(file));}
            }
            if (!pagedTrace) {
                vo.setDecisionTraceJson(read(directory.resolve("decision_trace.json")));
                vo.setChescaTraceCsv(read(directory.resolve("chesca_trace.csv")));
            }
        }
        if (pagedTrace) {
            Map<String, Object> page = loadTracePage(root, directory, id, caseId, 0,
                    com.citylearn.service.DecisionTracePageService.DEFAULT_LIMIT, null);
            vo.setDecisionTraceJson((String) page.get("decisionTraceJson"));
            vo.setChescaTraceCsv((String) page.get("chescaTraceCsv"));
            vo.setTracePage((Map<String, Object>) page.get("tracePage"));
        }
        if(!pagedTrace && "chesca".equals(caseId)&& (vo.getChescaTraceCsv()==null||vo.getChescaTraceCsv().isBlank())){
            vo.setChescaTraceCsv(read(root.resolve("chesca_trace.csv")));
            if(vo.getChescaTraceCsv().isBlank()){
                List<String> saved=jdbc.query("SELECT content FROM community_assessment_artifact WHERE run_id=? AND artifact_type='home_trace_csv'",(rs,n)->rs.getString(1),id);
                if(!saved.isEmpty())vo.setChescaTraceCsv(saved.get(0));
            }
        }
        if(vo.getDataFiles().isEmpty())vo.getArtifactWarnings().add("旧评估未保存环境时序，请重新评估生成能源曲线。");
        if(vo.getDecisionTraceJson()==null||vo.getDecisionTraceJson().isBlank())vo.getArtifactWarnings().add(vo.getChescaTraceCsv()!=null&&!vo.getChescaTraceCsv().isBlank()?"旧评估仅保存 CSV；日志按已保存字段恢复，缺少完整环境转移。":"旧评估未保存决策推演日志，请重新评估；无法从 KPI 还原。");
        return vo;
    }

    public Map<String, Object> tracePage(String key, int offset, int limit, Integer building) throws IOException {
        // Validate the run and case through the same successful-record lookup
        // used by detail; the caller never supplies a filesystem path.
        String[] parts = key.split(":", 3);
        if (parts.length < 2 || !"community".equals(parts[0])
                || !parts[1].matches("[a-f0-9-]{36}"))
            throw new IllegalArgumentException("无效评估记录");
        String caseId = parts.length == 3 ? parts[2] : "chesca";
        if (!caseId.matches("[a-z_]+")) throw new IllegalArgumentException("无效评估记录");
        String report = jdbc.queryForObject("SELECT result_json FROM community_assessment_run WHERE id=? AND status='succeeded'",
                String.class, parts[1]);
        Map<?, ?> result = mapper.readValue(report, Map.class);
        List<Map<?, ?>> cases = new ArrayList<>();
        if (result.get("baseline") instanceof Map) cases.add((Map<?, ?>) result.get("baseline"));
        if (result.get("cases") instanceof List) for (Object item : (List<?>) result.get("cases"))
            if (item instanceof Map) cases.add((Map<?, ?>) item);
        if (cases.stream().noneMatch(item -> caseId.equals(item.get("id")) && "succeeded".equals(item.get("status"))))
            throw new IllegalArgumentException("该方案不存在或未成功完成");
        Path root = Paths.get(files.getPythonFilePath()).toAbsolutePath()
                .resolve("outputs/community-assessments").resolve(parts[1]);
        Path directory = root.resolve("cases").resolve(caseId);
        return loadTracePage(root, directory, parts[1], caseId, offset, limit, building);
    }

    private Map<String, Object> loadTracePage(Path root, Path directory, String id, String caseId,
                                             int offset, int limit, Integer building) throws IOException {
        Path csv = directory.resolve("chesca_trace.csv");
        if (!Files.isRegularFile(csv) && "chesca".equals(caseId)) csv = root.resolve("chesca_trace.csv");
        Path json = directory.resolve("decision_trace.json");
        var reader = new com.citylearn.service.DecisionTracePageService();
        if (!Files.isRegularFile(json) && !Files.isRegularFile(csv) && "chesca".equals(caseId)) {
            List<String> saved = jdbc.query(
                    "SELECT content FROM community_assessment_artifact WHERE run_id=? AND artifact_type='home_trace_csv'",
                    (rs, n) -> rs.getString(1), id);
            if (!saved.isEmpty()) return reader.readCsv(saved.get(0), offset, limit, building);
        }
        return reader.read(root, json, csv, offset, limit, building);
    }
    private String read(Path file)throws IOException{return Files.isRegularFile(file)?Files.readString(file):"";}
    private void addKpi(List<Map<String,String>> rows,String name,Map<?,?> metrics){
        Map<String,String> row=new LinkedHashMap<>();row.put("algorithm",name);
        for(String key:List.of("cost_total","discomfort_proportion","score"))row.put(key,Objects.toString(metrics.get(key),""));rows.add(row);
    }
}
