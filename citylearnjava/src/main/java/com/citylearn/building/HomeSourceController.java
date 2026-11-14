package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.Map;

@RestController
@RequestMapping("/web/home")
public class HomeSourceController {
    @Resource private HomeSourceService service;
    @Resource private HomeEvaluationService evaluations;
    @GetMapping("/source") @RequirePerm({"menu:home","menu:recDashboard","menu:buildingManagement"}) public Result<?> source(){return Result.success(service.source());}
    @GetMapping("/evaluations") @RequirePerm("menu:recDashboard") public Result<?> evaluations(){return Result.success(evaluations.options());}
    @GetMapping("/evaluation") @RequirePerm("menu:home") public Result<?> evaluation()throws java.io.IOException{return Result.success(evaluations.current());}
    @PostMapping("/evaluation") @RequirePerm({"codeEditor:showRecord", "building:write"}) public Result<?> selectEvaluation(@RequestBody Map<String,Object> body)throws java.io.IOException{
        if(!body.containsKey("taskId"))throw new IllegalArgumentException("请提供评估记录 taskId");
        evaluations.select(body.get("taskId")==null?null:body.get("taskId").toString());return Result.success(service.source());
    }
    @PostMapping("/source") @RequirePerm("building:write") public Result<?> select(@RequestBody Map<String,Object> body){
        if(!body.containsKey("communityId"))throw new IllegalArgumentException("请提供communityId，null表示默认数据源");
        Object value=body.get("communityId");Long id=null;
        if(value!=null){try{id=Long.valueOf(value.toString());}catch(RuntimeException e){throw new IllegalArgumentException("社区ID无效");}}
        return Result.success(service.select(id));
    }
    @GetMapping("/snapshot") @RequirePerm("menu:home") public Result<?> snapshot(@RequestParam(required=false) Long buildingId,@RequestParam(required=false) String from,@RequestParam(required=false) String to){return Result.success(service.snapshot(buildingId,from,to));}
}
