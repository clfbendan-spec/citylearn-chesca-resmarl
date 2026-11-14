package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"citylearn.file.python-file-path=${java.io.tmpdir}/citylearn-community-assessment-tests","citylearn.community.validate-runtime=false"})
@Transactional
class CommunityAssessmentServiceTest {
    @Autowired CommunityAssessmentService assessments;
    @Autowired CommunityManagementService communities;
    @Autowired CommunityPublicationService publication;
    @Autowired CommunityDatasetService legacyPublication;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @Autowired FileResourceProperties files;
    @Autowired org.springframework.core.env.Environment environment;
    @org.springframework.boot.test.mock.mockito.MockBean CommunityAssessmentTasks managedTasks;

    @Test void oneClickCreatesOnlyNoControlWithoutRequiringChescaHistory() throws Exception {
        long community=community("Baseline assessment");
        String release=release(community);
        org.mockito.Mockito.when(managedTasks.bestChesca()).thenThrow(new IllegalArgumentException("No CHESCA history"));
        org.mockito.Mockito.when(managedTasks.create(org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.any(),org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.anyMap())).thenReturn("baseline-task");
        Map<String,Object> pair=assessments.startBaseline(community,release);
        List<Map<String,Object>> runs=(List<Map<String,Object>>)pair.get("runs");
        assertEquals(1,runs.size());
        assertEquals("NOCONTROL",((Map<?,?>)runs.get(0).get("config")).get("algorithm"));
        Map<?,?> config=(Map<?,?>)runs.get(0).get("config");
        assertEquals("baseline-task",config.get("taskId"));
        assertFalse(config.containsKey("bestSource"));
        assertEquals(true,((Map<?,?>)config.get("parameters")).get("dhw_storage_fix"));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE release_id=?",Integer.class,release));
        org.mockito.Mockito.verify(managedTasks,org.mockito.Mockito.never()).bestChesca();
        org.mockito.Mockito.verify(managedTasks,org.mockito.Mockito.never()).execute(org.mockito.ArgumentMatchers.anyString());
    }

    long community(String name) {return ((Number)communities.save(null,Map.of("name",name)).get("id")).longValue();}
    String release(long community)throws Exception { return release(community,false); }
    String release(long community,boolean synthetic)throws Exception {
        String id=UUID.randomUUID().toString(),key="community_"+id.replace("-","");
        Path dir=Paths.get(files.getPythonFilePath(),"datasets",key);Files.createDirectories(dir);
        Files.writeString(dir.resolve("schema.json"),synthetic?"{\"simulation_start_time_step\":0,\"simulation_end_time_step\":71,\"buildings\":{}}":"{\"buildings\":{}}");
        Map<String,Object> manifest=new LinkedHashMap<>();
        String contentHash="hash";
        if(synthetic){
            Map<String,Object> configuration=Map.of("startStep",24,"steps",48);
            Files.writeString(dir.resolve("generation_config.json"),mapper.writeValueAsString(configuration));
            Files.writeString(dir.resolve("validation_report.json"),"{\"runtimeValidation\":\"passed\",\"chescaSmokeTest\":\"passed\"}");
            Map<String,String> packageFiles=new TreeMap<>();
            for(String name:List.of("schema.json","generation_config.json","validation_report.json"))
                packageFiles.put(name,BuildingDatasetExporter.sha256(Files.readAllBytes(dir.resolve(name))));
            contentHash=BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(packageFiles));
            manifest.put("files",packageFiles);manifest.put("configuration",configuration);
            manifest.put("sourceMode","synthetic_ol1");manifest.put("scoreStartStep",24);manifest.put("scoreEndStepExclusive",72);
            manifest.put("contentHash",contentHash);manifest.put("chescaCompatible",true);
        } else manifest.put("files",Map.of("schema.json",BuildingDatasetExporter.sha256(Files.readAllBytes(dir.resolve("schema.json")))));
        Files.writeString(dir.resolve("manifest.json"),mapper.writeValueAsString(manifest));
        jdbc.update("INSERT INTO community_dataset_release(id,schema_key,name,start_time,end_time,time_steps,building_count,sources_json,content_hash) VALUES (?,?,?,'2026-01-01T00:00:00Z','2026-01-01T02:00:00Z',2,1,'[]',?)",id,key,"Test release",contentHash);
        jdbc.update("INSERT INTO community_dataset_owner(release_id,community_id) VALUES (?,?)",id,community);
        jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled) VALUES (?,?,?,1,2,0,1)",key,"Test","datasets/"+key);
        return id;
    }
    @Test void freezesSyntheticScoreWindowFromManifestAndRejectsSimulationTruncation()throws Exception {
        long community=community("Synthetic score window");String release=release(community,true);
        Map<String,Object> run=assessments.start(community,release,Map.of("algorithm","CHESCA"));
        Map<?,?> config=(Map<?,?>)run.get("config");
        Map<?,?> parameters=(Map<?,?>)config.get("parameters");
        assertEquals(24,((Number)parameters.get("score_start_step")).intValue());
        assertEquals(72,((Number)parameters.get("score_end_step_exclusive")).intValue());
        String id=run.get("id").toString();assessments.cancel(community,release,id);
        assertThrows(IllegalArgumentException.class,()->assessments.start(community,release,Map.of("start_step",24,"end_step",71)));
    }
    @Test void freezesSnapshotChecksOwnershipAndCancelsQueuedRun()throws Exception {
        long community=community("Assessment owner"),other=community("Other owner");String release=release(community);
        assertThrows(IllegalArgumentException.class,()->assessments.start(other,release));
        Map<String,Object> run=assessments.start(community,release);String id=run.get("id").toString();
        assertEquals("queued",run.get("status"));
        assertTrue(Files.isRegularFile(assessments.runDirectory(id).resolve("dataset/schema.json")));
        assertThrows(IllegalArgumentException.class,()->assessments.start(community,release));
        assertThrows(IllegalArgumentException.class,()->assessments.get(other,release,id));
        assertThrows(IllegalArgumentException.class,()->publication.delete(community,release));
        assertThrows(IllegalArgumentException.class,()->legacyPublication.delete(release));
        assertThrows(IllegalArgumentException.class,()->communities.delete(community));
        assessments.cancel(community,release,id);
        assertEquals("cancelled",assessments.get(community,release,id).get("status"));
        assertThrows(IllegalArgumentException.class,()->assessments.report(community,release,id));
        publication.delete(community,release);
    }
    @Test void rejectsTamperedFilesAndRecoversInterruptedRuns()throws Exception {
        long community=community("Integrity");String release=release(community);
        Path source=publication.directory(community,release);
        Files.writeString(source.resolve("schema.json"),"{\"changed\":true}");
        assertThrows(IllegalArgumentException.class,()->assessments.start(community,release));
        assertTrue(assessments.list(community,release).isEmpty());
        String id=UUID.randomUUID().toString();
        jdbc.update("INSERT INTO community_assessment_run(id,community_id,release_id,status,stage,config_json) VALUES (?,?,?,'running','nocontrol','{}')",id,community,release);
        assessments.recoverInterruptedRuns();
        assertEquals("failed",assessments.get(community,release,id).get("status"));
        assertThrows(IllegalArgumentException.class,()->assessments.runDirectory("../wrong"));
    }
    @Test void runnerCompletionRequiresSuccessfulBaselineAndKeepsFailedEvidence()throws Exception {
        long community=community("Runner completion");String release=release(community);
        String id=assessments.start(community,release).get("id").toString();
        Path output=assessments.runDirectory(id);
        Files.writeString(output.resolve("result.json"),"{\"status\":\"succeeded\",\"baseline\":{\"status\":\"succeeded\"},\"cases\":[]}");
        Files.writeString(output.resolve("report.md"),"# Completed report");
        Files.writeString(output.resolve("home_trace.csv"),"episode,step,building,action_tmp_final\n1,0,0,0.5\n");
        String python=environment.getProperty("citylearn.python.executable");
        assessments.execute(id,List.of(python,"-c","pass"));
        assertEquals("succeeded",assessments.get(community,release,id).get("status"),Objects.toString(assessments.get(community,release,id).get("error"),"no error details"));
        assertEquals("episode,step,building,action_tmp_final\n1,0,0,0.5\n",jdbc.queryForObject("SELECT content FROM community_assessment_artifact WHERE run_id=? AND artifact_type='home_trace_csv'",String.class,id));
        assertEquals("# Completed report",Files.readString(assessments.report(community,release,id)));
        String failed=assessments.start(community,release).get("id").toString();
        Files.writeString(assessments.runDirectory(failed).resolve("result.json"),"{\"status\":\"succeeded\",\"baseline\":{\"status\":\"failed\"}}");
        assessments.execute(failed,List.of(python,"-c","pass"));
        Map<String,Object> record=assessments.get(community,release,failed);
        assertEquals("failed",record.get("status"));
        assertTrue(record.get("error").toString().contains("NoControl"));
    }
    @Test void exposesWrittenNoControlBaselineBeforeWholeAssessmentFinishes()throws Exception {
        long community=community("Partial baseline");String release=release(community);String id=UUID.randomUUID().toString();
        jdbc.update("INSERT INTO community_assessment_run(id,community_id,release_id,status,stage,config_json) VALUES (?,?,?,'running','basic_rbc','{}')",id,community,release);
        Path directory=assessments.runDirectory(id);Files.createDirectories(directory);
        Files.writeString(directory.resolve("result.json"),"{\"status\":\"running\",\"baseline\":{\"status\":\"succeeded\",\"metrics\":{\"score\":1.25,\"officialRows\":[{\"level\":\"building\",\"name\":\"Building_1\",\"cost_function\":\"cost_total\",\"value\":0.8}] }},\"cases\":[]}");
        Map<String,Object> run=assessments.get(community,release,id);
        assertEquals("running",run.get("status"));
        Map<?,?> partial=(Map<?,?>)run.get("result");Map<?,?> baseline=(Map<?,?>)partial.get("baseline");Map<?,?> metrics=(Map<?,?>)baseline.get("metrics");
        assertEquals(1.25,((Number)metrics.get("score")).doubleValue());
        assertEquals(1,((List<?>)metrics.get("officialRows")).size());
    }
}
