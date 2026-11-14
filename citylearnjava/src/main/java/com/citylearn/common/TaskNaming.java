package com.citylearn.common;

import com.citylearn.entity.PyFile;
import com.citylearn.entity.PyTask;

import java.text.SimpleDateFormat;
import java.util.Date;

/**
 * 任务显示名的统一规则（从 BaseDataService 抽出，仪表盘与首页能源共用）。
 *
 * <p>规则：记录上手工改过展示名就用展示名；否则用「脚本名去掉 .py + 创建时间」。</p>
 */
public final class TaskNaming {

    private TaskNaming() {
    }

    /** 有展示名称用展示名称，否则回退到代码名 + 记录创建时间。 */
    public static String groupName(PyFile pyFile, PyTask task) {
        if (task != null && task.getShowName() != null && !task.getShowName().trim().isEmpty()) {
            return task.getShowName().trim();
        }
        String fileName = pyFile == null ? null : pyFile.getFileName();
        Date createTime = task == null ? null : task.getCreateTime();
        return groupName(fileName, createTime);
    }

    /** 仪表盘分组名回退：代码名 + 记录创建时间。 */
    public static String groupName(String fileName, Date taskCreateTime) {
        String base = stripPyExtension(fileName);
        if (base == null || base.isEmpty()) {
            base = "未命名";
        }
        if (taskCreateTime == null) {
            return base;
        }
        return base + " " + new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(taskCreateTime);
    }

    /** 去掉脚本扩展名（优先 .py，其次最后一个点之后的部分）。 */
    public static String stripPyExtension(String fileName) {
        if (fileName == null || fileName.isEmpty()) {
            return "";
        }
        if (fileName.toLowerCase().endsWith(".py")) {
            return fileName.substring(0, fileName.length() - 3);
        }
        int dot = fileName.lastIndexOf('.');
        return dot > 0 ? fileName.substring(0, dot) : fileName;
    }
}