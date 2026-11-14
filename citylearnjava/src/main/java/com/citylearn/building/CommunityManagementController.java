package com.citylearn.building;

import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import javax.annotation.Resource;
import java.util.*;

@RestController
@RequestMapping("/web/communities")
@RequirePerm("menu:buildingManagement")
public class CommunityManagementController {
    @Resource private CommunityManagementService service;
    @Resource private CommunityAssetService assetService;
    @GetMapping public Result<?> list(){return Result.success(service.list());}
    @GetMapping("/fields") public Result<?> fields(){
        List<Map<String,Object>> fields=new ArrayList<>();
        MeasurementContract.FIELDS.forEach((key,value)->{if(CommunityManagementService.sharedField(key))fields.add(value);});
        return Result.success(fields);
    }
    @PostMapping @RequirePerm("building:write") public Result<?> create(@RequestBody Map<String,Object> body){return Result.success(service.save(null,body));}
    @GetMapping("/{id}") public Result<?> get(@PathVariable long id){return Result.success(service.get(id,false));}
    @RequestMapping(value="/{id}",method={RequestMethod.POST,RequestMethod.PUT}) @RequirePerm("building:write")
    public Result<?> update(@PathVariable long id,@RequestBody Map<String,Object> body){return Result.success(service.save(id,body));}
    @PostMapping("/{id}/delete") @RequirePerm("building:write") public Result<?> delete(@PathVariable long id){service.delete(id);return Result.success();}
    @DeleteMapping("/{id}") @RequirePerm("building:write") public Result<?> deleteRest(@PathVariable long id){return delete(id);}
    @GetMapping("/{id}/buildings") public Result<?> buildings(@PathVariable long id){return Result.success(service.buildings(id));}
    @PostMapping("/{id}/buildings") @RequirePerm("building:write") public Result<?> addBuilding(@PathVariable long id,@RequestBody Map<String,Object> body){return Result.success(service.addBuilding(id,body));}
    @GetMapping("/{id}/measurements") public Result<?> measurements(@PathVariable long id,@RequestParam(required=false) String from,@RequestParam(required=false) String to,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="100") int size){return Result.success(service.measurements(id,from,to,page,size));}
    @GetMapping("/{id}/batches") public Result<?> batches(@PathVariable long id,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="100") int size){return Result.success(service.batches(id,page,size));}
    @PostMapping("/{id}/ingest") @RequirePerm("building:write") public Result<?> ingest(@PathVariable long id,@RequestBody BuildingController.IngestionRequest request){return Result.success(service.ingest(id,request.getRows(),request.getMapping(),request.getUnits(),"history",request.getSourceFiles(),request.getTimestampKind()));}
    @PostMapping("/{id}/token") @RequirePerm("building:write") public Result<?> token(@PathVariable long id){return Result.success(Map.of("token",service.rotateToken(id)));}
    @PostMapping("/{id}/models") @RequirePerm("building:write") public Result<?> upload(@PathVariable long id,@RequestParam("file") MultipartFile file) throws java.io.IOException{return Result.success(assetService.upload(id,file));}
}
