package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import java.nio.file.Files;

@RestController
@RequestMapping("/web/communities/{community}/datasets/{release}/assessments")
@RequirePerm("menu:buildingManagement")
public class CommunityAssessmentController {
    @Resource private CommunityAssessmentService service;
    @GetMapping public Result<?> list(@PathVariable long community,@PathVariable String release){return Result.success(service.list(community,release));}
    @PostMapping @RequirePerm("building:write") public Result<?> start(@PathVariable long community,@PathVariable String release)throws Exception{return Result.success(service.startBaseline(community,release));}
    @GetMapping("/{id}") public Result<?> detail(@PathVariable long community,@PathVariable String release,@PathVariable String id){return Result.success(service.get(community,release,id));}
    @PostMapping("/{id}/cancel") @RequirePerm("building:write") public Result<?> cancel(@PathVariable long community,@PathVariable String release,@PathVariable String id){service.cancel(community,release,id);return Result.success();}
    @GetMapping("/{id}/report") public void report(@PathVariable long community,@PathVariable String release,@PathVariable String id,HttpServletResponse response)throws Exception{
        java.nio.file.Path path=service.report(community,release,id);
        response.setContentType("text/markdown;charset=UTF-8");response.setHeader("Content-Disposition","attachment; filename=community-preliminary-"+id+".md");Files.copy(path,response.getOutputStream());
    }
}
