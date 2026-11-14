package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import lombok.Data;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

@RestController
@RequestMapping("/web/buildings")
@RequirePerm("menu:buildingManagement")
public class BuildingController {
    @Resource private BuildingIngestionService service;
    @Resource private BuildingExperimentService experiments;

    @GetMapping public Result<?> list() { return Result.success(service.list()); }
    @GetMapping("/fields") public Result<?> fields() { return Result.success(MeasurementContract.FIELDS.values()); }
    @GetMapping("/equipment-template") public Result<?> equipmentTemplate() throws Exception {
        try (java.io.InputStream input = getClass().getResourceAsStream("/citylearn/equipment-template.json")) {
            return Result.success(new com.fasterxml.jackson.databind.ObjectMapper().readValue(input, Map.class));
        }
    }
    @PostMapping @RequirePerm("building:write")
    public Result<?> create(@RequestBody Map<String, Object> body) { return Result.success(service.save(null, body)); }
    @PostMapping("/{id}") @RequirePerm("building:write")
    public Result<?> update(@PathVariable long id, @RequestBody Map<String, Object> body) { return Result.success(service.save(id, body)); }
    @PostMapping("/{id}/delete") @RequirePerm("building:write")
    public Result<?> delete(@PathVariable long id) { service.deleteBuilding(id); return Result.success(); }
    @PostMapping("/{id}/versions/{version}/delete") @RequirePerm("building:write")
    public Result<?> deleteVersion(@PathVariable long id, @PathVariable String version) {
        service.deleteVersion(id, version); return Result.success();
    }
    @GetMapping("/{id}")
    public Result<?> detail(@PathVariable long id, @RequestParam(required = false) String from,
                            @RequestParam(required = false) String to,@RequestParam(defaultValue="1") int page,
                            @RequestParam(defaultValue="100") int size) { return Result.success(service.detail(id, from, to,page,size)); }
    @GetMapping("/{id}/measurements")
    public Result<?> measurements(@PathVariable long id,@RequestParam(required=false) String from,
                                  @RequestParam(required=false) String to,@RequestParam(defaultValue="1") int page,
                                  @RequestParam(defaultValue="100") int size){return Result.success(service.measurementPage(id,from,to,page,size));}
    @PostMapping("/{id}/token") @RequirePerm("building:write")
    public Result<?> token(@PathVariable long id) { return Result.success(Map.of("token", service.rotateToken(id))); }
    @PostMapping("/{id}/ingest") @RequirePerm("building:write")
    public Result<?> ingest(@PathVariable long id, @RequestBody IngestionRequest request) {
        return Result.success(service.ingest(id, request.getRows(), request.getMapping(), request.getUnits(), "history", request.getSourceFiles(),request.getTimestampKind()));
    }
    @PostMapping("/{id}/versions") @RequirePerm("building:write")
    public Result<?> publish(@PathVariable long id, @RequestBody Map<String, Object> request) throws Exception {
        return Result.fail("建筑级数据集发布已取消，请在社区管理的数据集发布中统一选择建筑和时间范围");
    }
    @PostMapping("/{id}/versions/preview")
    public Result<?> preview(@PathVariable long id,@RequestBody Map<String,Object> request) {return Result.fail("建筑级数据集发布已取消，请在社区管理的数据集发布中统一选择建筑和时间范围");}
    @GetMapping("/{id}/versions/{version}/bundle")
    public void bundle(@PathVariable long id, @PathVariable String version, HttpServletResponse response) throws Exception {
        Path dir = service.versionDirectory(id, version);
        response.setContentType("application/zip");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"citylearn-" + version + ".zip\"");
        try (ZipOutputStream zip = new ZipOutputStream(response.getOutputStream());
             java.util.stream.Stream<Path> paths = Files.list(dir)) {
            for (Path file : (Iterable<Path>) paths.filter(Files::isRegularFile)::iterator) {
                zip.putNextEntry(new ZipEntry(file.getFileName().toString()));
                Files.copy(file, zip); zip.closeEntry();
            }
        }
    }
    @GetMapping("/{id}/experiments")
    public Result<?> experiments(@PathVariable long id) { return Result.success(experiments.list(id)); }
    @PostMapping("/{id}/experiments") @RequirePerm("building:write")
    public Result<?> start(@PathVariable long id, @RequestBody Map<String, Object> request) throws Exception {
        return Result.success(Map.of("id", experiments.start(id, request)));
    }
    @PostMapping("/{id}/experiments/{run}/cancel") @RequirePerm("building:write")
    public Result<?> cancel(@PathVariable long id, @PathVariable String run) {
        experiments.cancel(id, run); return Result.success();
    }
    @Data public static class IngestionRequest {
        private List<Map<String, Object>> rows;
        private Map<String, String> mapping = new LinkedHashMap<>();
        private Map<String, String> units = new LinkedHashMap<>();
        private List<Map<String,String>> sourceFiles = new ArrayList<>();
        private String timestampKind;
    }
}
