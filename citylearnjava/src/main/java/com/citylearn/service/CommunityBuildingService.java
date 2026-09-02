package com.citylearn.service;


import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.StringUtils;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.citylearn.common.PageBean;
import com.citylearn.config.SystemConfig;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.vo.CommunityBuildingVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.util.CollectionUtils;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * <p>
 *  服务实现类
 * </p>
 *
 * @author Your Name
 * @since 2025-06-08
 */
@Service
public class CommunityBuildingService implements SystemConfig {

    @Resource
    private CommunityBuildingMapper communityBuildingMapper;


    public int addCommunityBuilding(String name, String description, String imageUrl) {
        CommunityBuilding communityBuilding = new CommunityBuilding();
        communityBuilding.setId(getUUID());
        communityBuilding.setName(name);
        communityBuilding.setDescription(description);
        communityBuilding.setImageUrl(imageUrl);
        communityBuilding.setIfDelete(false);
        Date now = new Date();
        communityBuilding.setCreateTime(now);
        communityBuilding.setUpdateTime(now);
        return communityBuildingMapper.insert(communityBuilding);
    }

    public int editCommunityBuilding(String id, String name, String description, String imageUrl) {
        CommunityBuilding communityBuilding = communityBuildingMapper.selectById(id);
        if (communityBuilding != null) {
            communityBuilding.setName(name);
            communityBuilding.setDescription(description);
            communityBuilding.setImageUrl(imageUrl);
            Date now = new Date();
            communityBuilding.setUpdateTime(now);
            return communityBuildingMapper.updateById(communityBuilding);
        }
        return -1;
    }

    public int deleteCommunityBuilding(String id) {
        CommunityBuilding communityBuilding = communityBuildingMapper.selectById(id);
        if (communityBuilding != null) {
            communityBuilding.setIfDelete(true);
            Date now = new Date();
            communityBuilding.setUpdateTime(now);
            return communityBuildingMapper.updateById(communityBuilding);
        }
        return -1;
    }

    public PageBean<CommunityBuildingVO> listPageCommunityBuilding(String name, Integer currentPage, Integer pageSize) {
        Page<CommunityBuilding> page = new Page<>(currentPage, pageSize);
        PageBean<CommunityBuildingVO> pageBean = new PageBean<>();
        pageBean.setRows(new ArrayList<>());
        pageBean.setTotal(0);

        LambdaQueryWrapper<CommunityBuilding> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.like(StringUtils.isNotBlank(name),CommunityBuilding::getName,name);
        queryWrapper.eq(CommunityBuilding::getIfDelete, false);
        queryWrapper.orderByAsc(CommunityBuilding::getCreateTime);
        List<CommunityBuilding> infos = communityBuildingMapper.selectPage(page, queryWrapper).getRecords();
        if (CollectionUtils.isEmpty(infos)) {
            return pageBean;
        }

        List<CommunityBuildingVO> returnList=infos.stream().map(info->{
            CommunityBuildingVO communityBuildingVO=new CommunityBuildingVO();
            BeanUtils.copyProperties(info,communityBuildingVO);
            return communityBuildingVO;
        }).collect(Collectors.toList());

        pageBean.setRows(returnList);
        pageBean.setTotal((int) page.getTotal());
        return pageBean;
    }
}
