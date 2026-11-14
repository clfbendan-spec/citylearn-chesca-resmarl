package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

@RestController
@RequestMapping("/web/buildings/community-datasets")
@RequirePerm("menu:buildingManagement")
public class CommunityDatasetController {
    @Resource private CommunityDatasetService service;
    @GetMapping("/sources") public Result<?> sources() { return Result.success(service.sources()); }
    @GetMapping public Result<?> list() { return Result.success(service.list()); }
    @PostMapping @RequirePerm("building:write")
    public Result<?> publish(@RequestBody Map<String,Object> request) throws Exception { return Result.fail("旧社区发布入口已停用，请在社区管理的数据集发布中统一选择建筑和时间范围"); }
    @PostMapping("/preview")
    public Result<?> preview(@RequestBody Map<String,Object> request) throws Exception {return Result.fail("旧社区发布入口已停用，请在社区管理的数据集发布中统一选择建筑和时间范围");}
    @PostMapping("/{id}/delete") @RequirePerm("building:write")
    public Result<?> delete(@PathVariable String id) { service.delete(id); return Result.success(); }
    @GetMapping("/{id}/bundle")
    public void bundle(@PathVariable String id,HttpServletResponse response) throws Exception {
        Path directory=service.directory(id);
        response.setContentType("application/zip"); response.setHeader("Content-Disposition","attachment; filename=\"citylearn-community-"+id+".zip\"");
        try (ZipOutputStream zip=new ZipOutputStream(response.getOutputStream()); java.util.stream.Stream<Path> paths=Files.list(directory)) {
            for (Path file:(Iterable<Path>)paths.filter(Files::isRegularFile)::iterator) {
                zip.putNextEntry(new ZipEntry(file.getFileName().toString())); Files.copy(file,zip); zip.closeEntry();
            }
        }
    }
}
