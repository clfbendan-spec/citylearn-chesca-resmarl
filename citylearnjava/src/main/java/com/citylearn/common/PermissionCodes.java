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

    /** 代码编辑器：执行 / 保存 / 新建 / 改名等 */
    public static final String CODE_EDITOR_OPERATE = "codeEditor:operate";
    /** 代码编辑器：删除文件 / 删除执行记录 */
    public static final String CODE_EDITOR_DELETE = "codeEditor:delete";

    /** ResMARL 配置：修改 / 保存 / 恢复默认 */
    public static final String RES_MARL_OPERATE = "resMarlConfig:operate";
}
