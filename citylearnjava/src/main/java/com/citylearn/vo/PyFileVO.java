package com.citylearn.vo;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Date;

/**
 * <p>
 * 
 * </p>
 *
 * @author Your Name
 * @since 2025-09-02
 */
@Getter
@Setter
@ToString
public class PyFileVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 主键
     */
    private String id;

    /**
     * 文件名
     */
    private String fileName;


    /**
     * 文件注释
     */
    private String description;

    /**
     * 是否为系统默认文件
     */
    private Boolean ifSystem;

    /**
     * 创建时间
     */
    private Date createTime;

    /**
     * 创建人用户名
     */
    private String createUser;

    /**
     * 是否展示此文件对应结果
     */
    private Boolean ifShow;

    /**
     * 脚本类型，前端按此筛选文件列表：
     * train=只训练 / eval=只评估 / both=训练+评估一体
     */
    private String scriptType;

    /**
     * 该脚本的算法配置（JSON 字符串），供「配置」弹窗回填：
     * [{"id":1,"param_name":"train-schema","value":"1"}]
     * 前端自行 JSON.parse；为空表示尚未配置过。
     */
    private String algorithmConfig;
}
