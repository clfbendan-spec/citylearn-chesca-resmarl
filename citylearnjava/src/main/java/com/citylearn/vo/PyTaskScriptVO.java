package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * 任务输出目录中的 Python 脚本内容
 */
@Getter
@Setter
@ToString
public class PyTaskScriptVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private String taskId;

    private String fileName;

    private String code;
}
