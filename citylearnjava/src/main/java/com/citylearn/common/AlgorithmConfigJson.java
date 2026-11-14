package com.citylearn.common;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;

/**
 * 脚本「算法配置」JSON 的结构校验与归一化。
 *
 * <p>原来私有在 {@code BaseDataService} 里，但代码编辑器保存配置与任务编排
 * （pipeline step 的 config）两处都要用，属于跨域纯函数，抽到这里避免两个
 * Service 互相依赖。</p>
 *
 * <p>支持两种落库格式：</p>
 * <pre>
 * v1: [{"id":13,"value":"0.5"}, ...]                       // 顶层直接带 id
 * v2: [{"type":"alone","params":[{...}]},
 *      {"type":"set","set_id":3,"params":[{...}]}]         // 按单独配置/配置组分组
 * </pre>
 */
public final class AlgorithmConfigJson {

    private AlgorithmConfigJson() {
    }

    /**
     * 归一化算法配置 JSON。
     *
     * <p>空值统一落成 <code>"[]"</code> 而不是 null —— MyBatis-Plus 默认
     * updateStrategy 是 NOT_NULL，null 字段不会进 UPDATE 语句，
     * 那样「清空配置」这个操作会静默失效。</p>
     *
     * <p>非法 JSON 直接抛错，避免把脏数据写进库。</p>
     */
    public static String normalize(String algorithmConfig) {
        if (Texts.isBlank(algorithmConfig)) {
            return "[]";
        }
        JSONArray array;
        try {
            array = JSON.parseArray(algorithmConfig.trim());
        } catch (Exception e) {
            throw new RuntimeException("算法配置不是合法的 JSON 数组: " + e.getMessage());
        }
        if (array == null) {
            return "[]";
        }
        for (int i = 0; i < array.size(); i++) {
            JSONObject item = array.getJSONObject(i);
            if (item == null) {
                throw new RuntimeException("算法配置第 " + (i + 1) + " 项不是合法的 JSON 对象");
            }
            if (item.containsKey("params")) {
                // 新格式：按「单独配置 / 配置组」分组，顶层没有 id，id 在每个参数项上
                validateSection(item, i + 1);
            } else if (item.get("id") == null) {
                throw new RuntimeException("算法配置第 " + (i + 1) + " 项缺少 id");
            }
        }
        return array.toJSONString();
    }

    /**
     * 校验新格式里的一个分组（{@code {"type":"alone","params":[...]}} 或
     * {@code {"type":"set","set_id":3,"params":[...]}}）。
     *
     * @param section      分组对象
     * @param sectionIndex 分组序号（从 1 开始，仅用于报错提示）
     */
    private static void validateSection(JSONObject section, int sectionIndex) {
        String type = section.getString("type");
        if (Texts.isBlank(type)) {
            throw new RuntimeException("算法配置第 " + sectionIndex + " 组缺少 type");
        }
        if (!"alone".equals(type) && !"set".equals(type)) {
            throw new RuntimeException("算法配置第 " + sectionIndex + " 组的 type 非法: " + type);
        }
        if ("set".equals(type) && section.get("set_id") == null) {
            throw new RuntimeException("算法配置第 " + sectionIndex + " 组缺少 set_id");
        }
        JSONArray params = section.getJSONArray("params");
        if (params == null) {
            throw new RuntimeException("算法配置第 " + sectionIndex + " 组缺少 params");
        }
        for (int i = 0; i < params.size(); i++) {
            JSONObject param = params.getJSONObject(i);
            if (param == null || param.get("id") == null) {
                throw new RuntimeException("算法配置第 " + sectionIndex + " 组第 " + (i + 1) + " 项缺少 id");
            }
        }
    }
}
