package com.citylearn.building;

import com.citylearn.service.BaseDataService;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.annotation.Resource;
import java.io.IOException;
import java.util.*;

@Service
@DependsOn("homeSourceMigration")
public class HomeEvaluationService {
    @Resource private JdbcTemplate jdbc;
    @Resource private BaseDataService base;
    @Resource private AssessmentDashboardService assessments;
    public String selected(){return jdbc.queryForObject("SELECT task_id FROM home_evaluation_setting WHERE id=1",String.class);}
    public List<DashboardSimulationVO> options(){
        List<DashboardSimulationVO> result=new ArrayList<>(base.getDashboardSimulations(false));
        result.addAll(assessments.list(false));return result;
    }
    public boolean available(String id){
        return id!=null&&options().stream().anyMatch(item->id.equals(item.getTaskId()));
    }
    public DashboardSimulationDetailVO detail(String id)throws IOException{
        return id.startsWith("community:")?assessments.detail(id):base.getDashboardSimulationDetail(id);
    }
    @Transactional public void select(String id)throws IOException{
        if(id!=null){
            if(!available(id))throw new IllegalArgumentException("请选择成功且未删除的评估记录");
            detail(id);
        }
        jdbc.update("UPDATE home_evaluation_setting SET task_id=? WHERE id=1",id);
        jdbc.update("UPDATE home_source_setting SET community_id=NULL WHERE id=1");
    }
    public DashboardSimulationDetailVO current()throws IOException{
        String id=selected();
        if(id==null)return null;
        if(!available(id))throw new IllegalArgumentException("已选评估记录已删除或不可用，请重新选择首页数据源");
        return detail(id);
    }
}
