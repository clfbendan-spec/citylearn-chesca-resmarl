package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.Map;

@RestController
@RequestMapping("/web/communities/{community}/datasets/generator")
@RequirePerm("menu:buildingManagement")
public class Ol1ScenarioController {
    @Resource private Ol1ScenarioService service;

    @PostMapping("/preview")
    public Result<?> preview(@PathVariable long community, @RequestBody Map<String,Object> config) throws Exception {
        return Result.success(service.preview(community, config));
    }

    @GetMapping("/tasks")
    public Result<?> list(@PathVariable long community) {
        return Result.success(service.list(community));
    }

    @PostMapping("/tasks")
    @RequirePerm("building:write")
    public Result<?> start(@PathVariable long community, @RequestBody Map<String,Object> request) throws Exception {
        return Result.success(service.start(community, request));
    }

    @GetMapping("/tasks/{id}")
    public Result<?> get(@PathVariable long community, @PathVariable String id) {
        return Result.success(service.get(community, id));
    }

    @PostMapping("/tasks/{id}/cancel")
    @RequirePerm("building:write")
    public Result<?> cancel(@PathVariable long community, @PathVariable String id) {
        service.cancel(community, id);
        return Result.success();
    }
}
