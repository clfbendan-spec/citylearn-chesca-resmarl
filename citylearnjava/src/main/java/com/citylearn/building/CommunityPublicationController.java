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
@RequestMapping("/web/communities/{community}/datasets")
@RequirePerm("menu:buildingManagement")
public class CommunityPublicationController {
    @Resource private CommunityPublicationService service;
    @Resource private CommunityPublicationJobService jobs;
    @GetMapping public Result<?> list(@PathVariable long community){return Result.success(service.list(community));}
    @PostMapping("/range") public Result<?> range(@PathVariable long community,@RequestBody Map<String,Object> request)throws Exception{return Result.success(service.availableRange(community,request));}
    @PostMapping("/preview") public Result<?> preview(@PathVariable long community,@RequestBody Map<String,Object> request)throws Exception{return Result.success(service.preview(community,request));}
    @PostMapping @RequirePerm("building:write") public Result<?> publish(@PathVariable long community,@RequestBody Map<String,Object> request)throws Exception{return Result.success(jobs.start(community,request));}
    @GetMapping("/publication-tasks") public Result<?> tasks(@PathVariable long community){return Result.success(jobs.list(community));}
    @GetMapping("/publication-tasks/{task}") public Result<?> task(@PathVariable long community,@PathVariable String task){return Result.success(jobs.get(community,task));}
    @PostMapping("/{id}/delete") @RequirePerm("building:write") public Result<?> delete(@PathVariable long community,@PathVariable String id){service.delete(community,id);return Result.success();}
    @GetMapping("/{id}/bundle") public void bundle(@PathVariable long community,@PathVariable String id,HttpServletResponse response)throws Exception {
        Path directory=service.directory(community,id);response.setContentType("application/zip");response.setHeader("Content-Disposition","attachment; filename=citylearn-community-"+id+".zip");
        try(ZipOutputStream zip=new ZipOutputStream(response.getOutputStream());java.util.stream.Stream<Path> paths=Files.walk(directory)) {
            for(Path file:(Iterable<Path>)paths.filter(Files::isRegularFile)::iterator){zip.putNextEntry(new ZipEntry(directory.relativize(file).toString().replace(java.io.File.separatorChar,'/')));Files.copy(file,zip);zip.closeEntry();}
        }
    }
}
