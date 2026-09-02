package com.citylearn.controller;

import com.citylearn.common.PageBean;
import com.citylearn.common.Result;
import com.citylearn.param.PyFileParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.service.CommunityBuildingService;
import com.citylearn.vo.BuildingDataVO;
import com.citylearn.vo.CommunityBuildingVO;
import com.citylearn.vo.KpisTransVO;
import com.citylearn.vo.PyFileVO;
import io.swagger.annotations.Api;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.io.IOException;
import java.util.List;

/**
 * @author  chenglifu
 */
@RestController
@Api(value = "CommunityBuildingController", tags = {"建筑"})
@RequestMapping("/web/communityBuilding")
public class CommunityBuildingController {

    @Resource
    private CommunityBuildingService communityBuildingService;

    @RequestMapping(value = "/listPageCommunityBuilding",method = RequestMethod.GET)
    public Result<PageBean<CommunityBuildingVO>> listPageCommunityBuilding(@RequestParam(name = "name",required = false)String name,
                                                         @RequestParam(name = "currentPage",required = false)Integer currentPage,
                                                         @RequestParam(name = "pageSize",required = false)Integer pageSize){
        PageBean<CommunityBuildingVO> page= communityBuildingService.listPageCommunityBuilding(name,currentPage,pageSize);
        return Result.success(page);
    }

    @RequestMapping(value = "/addCommunityBuilding",method = RequestMethod.POST)
    public Result<String> addCommunityBuilding(@RequestParam(name = "name")String name,
                              @RequestParam(name = "description")String description,
                              @RequestParam(name = "imageUrl")String imageUrl){
        communityBuildingService.addCommunityBuilding(name,description,imageUrl);
        return Result.success();
    }

    @RequestMapping(value = "/editCommunityBuilding",method = RequestMethod.POST)
    public Result<String> editCommunityBuilding(@RequestParam(name = "id")String id,
                              @RequestParam(name = "name")String name,
                              @RequestParam(name = "description")String description,
                              @RequestParam(name = "imageUrl")String imageUrl){
        communityBuildingService.editCommunityBuilding(id,name,description,imageUrl);
        return Result.success();
    }

    @RequestMapping(value = "/deleteCommunityBuilding",method = RequestMethod.POST)
    public Result<String> deleteCommunityBuilding(@RequestParam(name = "id")String id){
        communityBuildingService.deleteCommunityBuilding(id);
        return Result.success();
    }
}