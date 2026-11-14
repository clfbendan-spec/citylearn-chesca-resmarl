package com.citylearn.building;

import com.citylearn.common.SimulationDataPaths;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.param.PipelineStepConfig;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.service.EvaluationAnalysisService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import javax.annotation.Resource;
import java.nio.file.*;
import java.util.*;

/** Uses the normal task lifecycle while keeping preliminary reports with their community. */
@Service
public class CommunityAssessmentTasks {
    @Resource private BaseDataService tasks;
    @Resource private FileResourceProperties files;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;

    public Map<String,Object> bestChesca() throws Exception {
        Path template = Paths.get(files.getPythonFilePath()).toAbsolutePath().getParent().getParent()
                .resolve("datasets/citylearn_challenge_2023_phase_2_online_evaluation_1");
        Map<String,String> originalAssets=new HashMap<>();
        try(var paths=Files.list(template)) {
            for(Path path:paths.filter(Files::isRegularFile).toList()) {
                String name=path.getFileName().toString();
                if(name.endsWith(".csv")||name.endsWith(".pth"))
                    originalAssets.put(name,BuildingDatasetExporter.sha256(Files.readAllBytes(path)));
            }
        }
        EvaluationAnalysisService reader = new EvaluationAnalysisService();
        Map<String,Object> best = null;
        String protocol = null;
        for (Map<String,Object> task : jdbc.queryForList(
                "SELECT t.id FROM py_task t JOIN py_file f ON f.id=t.py_id WHERE t.status=1 AND t.if_delete=0 AND LOWER(f.file_name)='chesca.py' ORDER BY t.create_time DESC,t.id DESC")) {
            String id = task.get("id").toString();
            Map<String,Object> evidence = reader.read(SimulationDataPaths.taskDir(files.getOutFilePath(), id), id);
            if (!"available".equals(evidence.get("status"))) continue;
            Map<?,?> manifest = (Map<?,?>)evidence.get("manifest");
            Map<?,?> physical = (Map<?,?>)manifest.get("protocol");
            Map<?,?> hashes = (Map<?,?>)physical.get("dataset_files_sha256");
            if (!originalAssets.entrySet().stream().allMatch(entry->Objects.equals(hashes.get(entry.getKey()),entry.getValue()))
                    || !Objects.equals(physical.get("simulation_window"), List.of(0,2207))) continue;
            String candidateProtocol = Objects.toString(manifest.get("physical_protocol_id"), "");
            if (candidateProtocol.isEmpty()) continue;
            if (protocol == null) protocol = candidateProtocol;
            if (!protocol.equals(candidateProtocol)) continue;
            Map<?,?> result = (Map<?,?>)evidence.get("result");
            Map<?,?> buildings = (Map<?,?>)result.get("per_building");
            if (buildings == null || buildings.size() != 3) continue;
            double cost = 0, discomfort = 0;
            boolean valid = true;
            for (Object value : buildings.values()) {
                Map<?,?> row = (Map<?,?>)value;
                Object c = row.get("cost_total"), d = row.get("discomfort_proportion");
                if (!(c instanceof Number) || !(d instanceof Number)) { valid = false; break; }
                double cv = ((Number)c).doubleValue(), dv = ((Number)d).doubleValue();
                if (!Double.isFinite(cv) || cv < 0 || !Double.isFinite(dv) || dv < 0 || dv >= .10) { valid = false; break; }
                cost += cv / 3; discomfort += dv / 3;
            }
            if (!valid || !(manifest.get("resolved_parameters") instanceof Map)) continue;
            // Current historical records have no matching frozen Anchor. Keep the
            // existing preliminary J explicit instead of inventing a formal score.
            double score = .5 * cost / .796605975703795 + .5 * discomfort / .04916529553031551;
            if (best == null || score < ((Number)best.get("score")).doubleValue()) {
                best = new LinkedHashMap<>();
                best.put("taskId", id); best.put("score", score);
                best.put("criterion", "同协议 Online1 完整评估，逐栋不适比例<10%，按既有初步评估 J 最小；正式分段评分缺少匹配 Anchor，未用于本次选参");
                best.put("physicalProtocolId", protocol);
                best.put("parameters", manifest.get("resolved_parameters"));
            }
        }
        if (best == null) throw new IllegalArgumentException("没有可复用的完整 CHESCA Online1 合格评估参数，请先完成一次 CHESCA 评估");
        return best;
    }

    public String create(String algorithm, String schemaKey, String name, Path snapshot, Path reportDirectory,
                         Map<String,Object> parameters) throws Exception {
        List<Map<String,Object>> scripts = jdbc.queryForList(
                "SELECT id,file_name FROM py_file WHERE LOWER(file_name)=? AND script_type='eval'", algorithm.toLowerCase(Locale.ROOT)+".py");
        if (scripts.size() != 1) throw new IllegalArgumentException("缺少唯一可用的 " + algorithm + " 评估脚本");
        List<Map<String,Object>> params = new ArrayList<>();
        params.add(parameter("community-assessment-schema", snapshot.resolve("schema.json").toString()));
        params.add(parameter("community-assessment-output", reportDirectory.toString()));
        params.add(parameter("community-assessment-parameters", Base64.getEncoder().encodeToString(mapper.writeValueAsBytes(parameters))));
        PipelineStepConfig step = new PipelineStepConfig();
        step.setPyId(scripts.get(0).get("id").toString());
        step.setScriptName(scripts.get(0).get("file_name").toString());
        step.setSchemaKey(schemaKey); step.setDatasetName(name);
        step.setConfig(mapper.writeValueAsString(List.of(Map.of("type","alone","params",params))));
        PipelineTaskParam request = new PipelineTaskParam();
        request.setTaskName("社区初步评估 · " + algorithm + " · " + (name.length()>75?name.substring(0,75):name));
        request.setEvalConfig(step);
        String id=tasks.createPipelineTask(request).getTaskId();
        DatasetSnapshotFiles.cleanupOnRollback(SimulationDataPaths.taskDir(files.getOutFilePath(),id));
        DatasetSnapshotFiles.cleanupOnRollback(SimulationDataPaths.taskDir(files.getOutFilePath(),id+"-eval"));
        return id;
    }
    private Map<String,Object> parameter(String name, String value) {
        return Map.of("id",UUID.randomUUID().toString(),"type","extra","param_name",name,"name",name,"value",value);
    }
    public void execute(String id) { tasks.executePipelineTask(id); }
    public void cancel(String id) { tasks.stopPyTask(id); }
    public void failStart(String id,String message) {
        jdbc.update("UPDATE py_task SET status=2,update_time=CURRENT_TIMESTAMP WHERE (id=? OR id=?) AND status IN (0,5,6)",id,id+"-eval");
    }
    public Map<String,Object> state(String id) {
        return jdbc.queryForMap("SELECT status FROM py_task WHERE id=?",id);
    }
}
