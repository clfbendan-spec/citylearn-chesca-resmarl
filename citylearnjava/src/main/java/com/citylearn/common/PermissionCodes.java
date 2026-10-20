package com.citylearn.common;

/**
 * 权限码常量（与 permission 表 code 一致；树结构从数据库读取）
 */
public final class PermissionCodes {

    private PermissionCodes() {
    }

    public static final String MENU_HOME = "menu:home";
    public static final String MENU_REC_DASHBOARD = "menu:recDashboard";
    public static final String MENU_DATA_LIST = "menu:dataList";
    public static final String MENU_CODE_EDITOR = "menu:codeEditor";
    /** 任务记录：集中查看所有代码执行记录（只读列表，无子权限） */
    public static final String MENU_TASK_LIST = "menu:taskList";
    public static final String MENU_RES_MARL = "menu:resMarlConfig";
    /** 参数配置：维护算法参数定义目录（algorithm_param_config） */
    public static final String MENU_ALGORITHM_PARAM = "menu:algorithmParam";

    /* ---------------- 代码编辑器：脚本级 ---------------- */
    /** 保存代码（含新建脚本、脚本改名、文件简介、算法配置） */
    public static final String CODE_SAVE = "codeEditor:save";
    /** 执行脚本（含终止运行中的任务、续训开关） */
    public static final String CODE_RUN = "codeEditor:run";
    /** 删除脚本文件 */
    public static final String CODE_DELETE_FILE = "codeEditor:deleteFile";

    /* ---------------- 代码编辑器：执行记录级 ---------------- */
    /** 删除执行记录 */
    public static final String CODE_DELETE_RECORD = "codeEditor:deleteRecord";
    /** 执行记录改名（模型优选的展示名称） */
    public static final String CODE_RENAME_RECORD = "codeEditor:renameRecord";
    /** 执行记录「展示 / 未展示」 */
    public static final String CODE_SHOW_RECORD = "codeEditor:showRecord";

    /** ResMARL 配置：修改 / 保存 / 恢复默认 */
    public static final String RES_MARL_OPERATE = "resMarlConfig:operate";

    /* ---------------- 任务管理：新建 / 编辑 / 删除 / 执行 ---------------- */
    /** 任务管理：新建任务（含「新建训练+评估编排任务」） */
    public static final String TASK_CREATE = "taskList:create";
    /** 任务管理：编辑任务名称与卡片配置 */
    public static final String TASK_EDIT = "taskList:edit";
    /** 任务管理：删除任务 */
    public static final String TASK_DELETE = "taskList:delete";
    /** 任务管理：执行任务 */
    public static final String TASK_RUN = "taskList:run";

    /* ---------------- 参数配置：单独配置 ---------------- */
    /** 参数配置：单独配置（分组节点，本身不控制按钮） */
    public static final String PARAM_ITEM = "algorithmParam:item";
    /** 单独配置：新建参数 */
    public static final String PARAM_ITEM_CREATE = "algorithmParam:itemCreate";
    /** 单独配置：编辑参数 */
    public static final String PARAM_ITEM_EDIT = "algorithmParam:itemEdit";
    /** 单独配置：删除参数 */
    public static final String PARAM_ITEM_DELETE = "algorithmParam:itemDelete";

    /* ---------------- 参数配置：配置组 ---------------- */
    /** 参数配置：配置组（分组节点，本身不控制按钮） */
    public static final String PARAM_SET = "algorithmParam:set";
    /** 配置组：新建配置组 */
    public static final String PARAM_SET_CREATE = "algorithmParam:setCreate";
    /** 配置组：编辑配置组 */
    public static final String PARAM_SET_EDIT = "algorithmParam:setEdit";
    /** 配置组：删除配置组 */
    public static final String PARAM_SET_DELETE = "algorithmParam:setDelete";
    /** 配置组：把参数移入配置组 */
    public static final String PARAM_SET_MOVE_IN = "algorithmParam:setMoveIn";
    /** 配置组：把参数移出配置组 */
    public static final String PARAM_SET_MOVE_OUT = "algorithmParam:setMoveOut";
}
