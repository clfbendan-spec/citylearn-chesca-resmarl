package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.citylearn.common.Texts;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.vo.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.*;

/**
 * 算法参数目录与配置组管理。
 *
 * <p>从 {@code BaseDataService} 拆出（2026-10-20）。原来这两块混在同一个 5000 行类里：
 * 「配置 -> 命令行参数」属于任务执行链，而这里的增删改属于参数目录管理，变更原因不同。
 * 拆开后本类只依赖两张表（{@code algorithm_param_config} /
 * {@code algorithm_param_config_set}），不碰任务与文件。
 *
 * <p>成员关系是冗余存储的：{@code set.members}（JSON 数组）与
 * {@code config.is_member} 必须同步，所有写路径都收敛到 {@link #updateSetMembers}。
 */
@Service
public class AlgorithmParamConfigService {

    private static final Logger log = LoggerFactory.getLogger(AlgorithmParamConfigService.class);

    @Resource
    private AlgorithmParamConfigMapper algorithmParamConfigMapper;
    @Resource
    private AlgorithmParamConfigSetMapper algorithmParamConfigSetMapper;

    /**
     * 算法参数定义目录。
     *
     * <p>系统自带（if_system=1）排前面，其余按 id 升序，保证下拉顺序稳定、
     * 不会因为插入顺序变化而跳动。
     *
     * @param isMember 配置组成员筛选：
     *                 {@code null} = 全部（代码编辑器「配置」弹窗要用全量）；
     *                 {@code false} = 只看独立参数（参数配置页的「单独配置」页签）；
     *                 {@code true} = 只看组成员。
     */
    public List<AlgorithmParamConfigVO> listAlgorithmParamConfigs(Boolean isMember) {
        QueryWrapper<AlgorithmParamConfig> wrapper = new QueryWrapper<>();
        wrapper.lambda()
                .eq(isMember != null, AlgorithmParamConfig::getIsMember, Boolean.TRUE.equals(isMember))
                .orderByDesc(AlgorithmParamConfig::getIfSystem)
                .orderByAsc(AlgorithmParamConfig::getId);
        List<AlgorithmParamConfig> rows = algorithmParamConfigMapper.selectList(wrapper);
        List<AlgorithmParamConfigVO> result = new ArrayList<>();
        if (rows == null) {
            return result;
        }
        for (AlgorithmParamConfig row : rows) {
            result.add(toAlgorithmParamConfigVO(row));
        }
        return result;
    }

    /** 全量参数定义（代码编辑器「配置」弹窗的下拉框数据源） */
    public List<AlgorithmParamConfigVO> listAlgorithmParamConfigs() {
        return listAlgorithmParamConfigs(null);
    }

    /* ==================== 参数配置页：algorithm_param_config 增删改 ==================== */

    /**
     * 参数配置页允许的值类型：
     * num 数字 / text 文字 / bool 布尔（开关）/ ratio 单选 / multiple 多选 /
     * map 键值对 / special 数据集（历史值，保留可选项）。
     * ratio / multiple / map 会用到 default_value（内容均为 [{key,value}]），其余一律落 NULL；
     * key_alias / value_alias 只服务 map。
     */
    private static final Set<String> ALGORITHM_VALUE_TYPES =
            new HashSet<>(Arrays.asList("num", "text", "bool", "ratio", "multiple", "map", "special"));

    /**
     * 参数配置页：新增一条参数定义。
     *
     * <p>页面新增的一律按「用户自定义」入库（if_system=false）；
     * 系统参数只能由 db/*.sql 预置，避免前端把自己标成系统参数绕开删除保护。
     *
     * <p>若入参带了 {@code setId}（在配置组详情页里新建参数），插入后直接把该参数
     * 追加进这个组：members 追加 + is_member 置 1。
     */
    public AlgorithmParamConfigVO addAlgorithmParamConfig(AlgorithmParamConfigParam param) {
        if (param == null) {
            throw new RuntimeException("参数不能为空");
        }
        String name = trimToNull(param.getName());
        if (name == null) {
            throw new RuntimeException("名称不能为空");
        }
        String paramName = trimToNull(param.getParamName());
        if (paramName == null) {
            throw new RuntimeException("默认参数名不能为空");
        }
        ensureParamNameAvailable(paramName, null);
        String valueType = normalizeAlgorithmValueType(param.getValueType());

        AlgorithmParamConfig row = new AlgorithmParamConfig();
        row.setName(name);
        row.setParamName(paramName);
        row.setDesc(trimToNull(param.getDesc()));
        row.setValueType(valueType);
        row.setDefaultValue(normalizeAlgorithmDefaultValue(valueType, param.getDefaultValue()));
        row.setKeyAlias(normalizeMapAlias(valueType, param.getKeyAlias()));
        row.setValueAlias(normalizeMapAlias(valueType, param.getValueAlias()));
        row.setIfSystem(false);
        row.setIsMember(false);
        row.setCreateTime(new Date());
        algorithmParamConfigMapper.insert(row);

        Integer setId = param.getSetId();
        if (setId != null) {
            AlgorithmParamConfigSet set = algorithmParamConfigSetMapper.selectById(setId);
            if (set == null) {
                throw new RuntimeException("配置组不存在: " + setId);
            }
            List<Integer> memberIds = parseSetMemberIds(set.getMembers());
            if (!memberIds.contains(row.getId())) {
                memberIds.add(row.getId());
            }
            updateSetMembers(set, memberIds);
        }
        log.info("新增算法参数定义: id={}, name={}, paramName={}, valueType={}, setId={}",
                row.getId(), name, paramName, valueType, setId);
        return toAlgorithmParamConfigVO(algorithmParamConfigMapper.selectById(row.getId()));
    }

    /**
     * 参数配置页：编辑一条参数定义。
     *
     * <p>系统自带参数（if_system=1）只允许改简介 —— 名称 / 默认参数名 / 值类型
     * 可能已被历史 py_file.algorithm_config 引用，改了会让旧配置对不上。
     */
    public void updateAlgorithmParamConfig(AlgorithmParamConfigParam param) {
        if (param == null || param.getId() == null) {
            throw new RuntimeException("参数 id 不能为空");
        }
        AlgorithmParamConfig exist = algorithmParamConfigMapper.selectById(param.getId());
        if (exist == null) {
            throw new RuntimeException("参数不存在: " + param.getId());
        }
        if (Boolean.TRUE.equals(exist.getIfSystem())) {
            com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<AlgorithmParamConfig> uw =
                    new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
            uw.eq("id", exist.getId()).set("`desc`", trimToNull(param.getDesc()));
            algorithmParamConfigMapper.update(null, uw);
            log.info("更新系统参数简介: id={}, name={}", exist.getId(), exist.getName());
            return;
        }

        String name = trimToNull(param.getName());
        if (name == null) {
            throw new RuntimeException("名称不能为空");
        }
        String paramName = trimToNull(param.getParamName());
        if (paramName == null) {
            throw new RuntimeException("默认参数名不能为空");
        }
        ensureParamNameAvailable(paramName, exist.getId());
        String valueType = normalizeAlgorithmValueType(param.getValueType());
        String defaultValue = normalizeAlgorithmDefaultValue(valueType, param.getDefaultValue());

        // 用 UpdateWrapper 显式 set：值类型从单选/多选改成文字时，default_value 要真正置回 NULL
        // （updateById 默认忽略 null 字段，会留下过期的候选项）
        com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<AlgorithmParamConfig> uw =
                new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
        uw.eq("id", exist.getId())
                .set("name", name)
                .set("param_name", paramName)
                .set("`desc`", trimToNull(param.getDesc()))
                .set("value_type", valueType)
                .set("default_value", defaultValue)
                .set("key_alias", normalizeMapAlias(valueType, param.getKeyAlias()))
                .set("value_alias", normalizeMapAlias(valueType, param.getValueAlias()));
        algorithmParamConfigMapper.update(null, uw);
        log.info("更新算法参数定义: id={}, name={}, paramName={}, valueType={}",
                exist.getId(), name, paramName, valueType);
    }

    /** 参数配置页：删除一条参数定义（系统自带参数禁止删除） */
    public void deleteAlgorithmParamConfig(Integer id) {
        if (id == null) {
            throw new RuntimeException("参数 id 不能为空");
        }
        AlgorithmParamConfig exist = algorithmParamConfigMapper.selectById(id);
        if (exist == null) {
            throw new RuntimeException("参数不存在: " + id);
        }
        if (Boolean.TRUE.equals(exist.getIfSystem())) {
            throw new RuntimeException("系统内置参数不可删除");
        }
        algorithmParamConfigMapper.deleteById(id);
        log.info("删除算法参数定义: id={}, name={}", id, exist.getName());
    }

    /* ==================== 参数配置页：algorithm_param_config_set 配置组 ==================== */

    /**
     * 配置组列表（按 id 升序）。
     * 列表页只展示 组名称 / 创建时间 / 简介 / 成员数，不返回成员明细。
     */
    public List<AlgorithmParamConfigSetVO> listAlgorithmParamConfigSets() {
        List<AlgorithmParamConfigSet> rows = algorithmParamConfigSetMapper.selectList(
                new QueryWrapper<AlgorithmParamConfigSet>().lambda()
                        .orderByAsc(AlgorithmParamConfigSet::getId));
        List<AlgorithmParamConfigSetVO> result = new ArrayList<>();
        if (rows == null) {
            return result;
        }
        for (AlgorithmParamConfigSet row : rows) {
            result.add(toAlgorithmParamConfigSetVO(row));
        }
        return result;
    }

    /**
     * 配置组详情：组信息 + 组内参数定义（按组内顺序）。
     * members 里已被删掉的 id 会被静默跳过，不报错。
     */
    public AlgorithmParamConfigSetDetailVO getAlgorithmParamConfigSetDetail(Integer id) {
        AlgorithmParamConfigSet set = requireAlgorithmParamConfigSet(id);
        AlgorithmParamConfigSetDetailVO vo = new AlgorithmParamConfigSetDetailVO();
        vo.setId(set.getId());
        vo.setCreateTime(set.getCreateTime());
        vo.setName(set.getName());
        vo.setDesc(set.getDesc());
        for (Integer memberId : parseSetMemberIds(set.getMembers())) {
            AlgorithmParamConfig member = algorithmParamConfigMapper.selectById(memberId);
            if (member != null) {
                vo.getMembers().add(toAlgorithmParamConfigVO(member));
            }
        }
        return vo;
    }

    /** 新增配置组；组内参数同步标记 is_member */
    public AlgorithmParamConfigSetVO addAlgorithmParamConfigSet(AlgorithmParamConfigSetParam param) {
        if (param == null) {
            throw new RuntimeException("配置组不能为空");
        }
        String name = trimToNull(param.getName());
        if (name == null) {
            throw new RuntimeException("组名称不能为空");
        }
        AlgorithmParamConfigSet set = new AlgorithmParamConfigSet();
        set.setName(name);
        set.setDesc(trimToNull(param.getDesc()));
        set.setCreateTime(new Date());
        set.setMembers("[]");
        algorithmParamConfigSetMapper.insert(set);
        updateSetMembers(set, normalizeMemberIds(param.getMemberIds()));
        log.info("新增参数配置组: id={}, name={}, members={}", set.getId(), name, set.getMembers());
        return toAlgorithmParamConfigSetVO(algorithmParamConfigSetMapper.selectById(set.getId()));
    }

    /** 编辑配置组：名称 / 简介 / 成员；成员增删会同步 is_member */
    public void updateAlgorithmParamConfigSet(AlgorithmParamConfigSetParam param) {
        if (param == null || param.getId() == null) {
            throw new RuntimeException("配置组 id 不能为空");
        }
        AlgorithmParamConfigSet set = requireAlgorithmParamConfigSet(param.getId());
        String name = trimToNull(param.getName());
        if (name == null) {
            throw new RuntimeException("组名称不能为空");
        }
        set.setName(name);
        set.setDesc(trimToNull(param.getDesc()));
        // 不传 memberIds 表示「本次只改名称/简介」，保留原成员
        List<Integer> memberIds = param.getMemberIds() == null
                ? parseSetMemberIds(set.getMembers())
                : normalizeMemberIds(param.getMemberIds());
        updateSetMembers(set, memberIds);
        log.info("更新参数配置组: id={}, name={}, members={}", set.getId(), name, set.getMembers());
    }

    /**
     * 删除配置组。
     *
     * <p>组内还有参数时直接拒绝 —— 否则那些参数会在用户没察觉的情况下悄悄回到
     * 「单独配置」页签。想删组，得先把成员全部移出。
     */
    public void deleteAlgorithmParamConfigSet(Integer id) {
        AlgorithmParamConfigSet set = requireAlgorithmParamConfigSet(id);
        List<Integer> memberIds = parseSetMemberIds(set.getMembers());
        if (!memberIds.isEmpty()) {
            throw new RuntimeException(
                    "配置组内还有 " + memberIds.size() + " 个参数，请先全部移出后再删除配置组");
        }
        algorithmParamConfigSetMapper.deleteById(id);
        log.info("删除参数配置组: id={}, name={}", id, set.getName());
    }

    private AlgorithmParamConfigSet requireAlgorithmParamConfigSet(Integer id) {
        if (id == null) {
            throw new RuntimeException("配置组 id 不能为空");
        }
        AlgorithmParamConfigSet set = algorithmParamConfigSetMapper.selectById(id);
        if (set == null) {
            throw new RuntimeException("配置组不存在: " + id);
        }
        return set;
    }

    /**
     * 重写某个组的名称/简介/成员，并同步 is_member。
     *
     * <p>同步范围取「旧成员 ∪ 新成员」：被移出组的参数必须一起重算，
     * 否则它会永远挂着 is_member=1，从「单独配置」页签里消失。
     */
    private void updateSetMembers(AlgorithmParamConfigSet set, List<Integer> memberIds) {
        List<Integer> oldMembers = parseSetMemberIds(set.getMembers());
        List<Integer> normalized = new ArrayList<>();
        for (Integer memberId : memberIds) {
            if (memberId == null || normalized.contains(memberId)) {
                continue;
            }
            // 只收真实存在的参数，避免 members 里留下脏 id（详情页会查不到）
            AlgorithmParamConfig member = algorithmParamConfigMapper.selectById(memberId);
            if (member == null) {
                throw new RuntimeException("参数不存在: " + memberId);
            }
            // 系统内置参数不允许入组：它们由 db/*.sql 预置、全局共享，
            // 挂进某个组会让「单独配置」页看不到它们，语义上也不该被"归档"。
            // 只拦新加入的 —— 老成员即使（被手工改库）已是系统参数也能照常移出。
            if (!oldMembers.contains(memberId) && Boolean.TRUE.equals(member.getIfSystem())) {
                throw new RuntimeException("系统内置参数不能加入配置组：" + member.getName());
            }
            normalized.add(memberId);
        }
        String membersJson = JSON.toJSONString(normalized);
        com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<AlgorithmParamConfigSet> uw =
                new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
        uw.eq("id", set.getId())
                .set("name", set.getName())
                .set("`desc`", set.getDesc())
                .set("members", membersJson);
        algorithmParamConfigSetMapper.update(null, uw);
        set.setMembers(membersJson);

        Set<Integer> affected = new LinkedHashSet<>(oldMembers);
        affected.addAll(normalized);
        refreshMemberFlags(affected);
    }

    /**
     * 重算一批参数的 is_member：只要还挂在任意一个组的 members 里就是 1，否则 0。
     */
    private void refreshMemberFlags(Collection<Integer> paramIds) {
        if (paramIds == null || paramIds.isEmpty()) {
            return;
        }
        Set<Integer> allMembers = new HashSet<>();
        List<AlgorithmParamConfigSet> sets = algorithmParamConfigSetMapper.selectList(null);
        if (sets != null) {
            for (AlgorithmParamConfigSet set : sets) {
                allMembers.addAll(parseSetMemberIds(set.getMembers()));
            }
        }
        for (Integer paramId : paramIds) {
            if (paramId == null || algorithmParamConfigMapper.selectById(paramId) == null) {
                continue;
            }
            com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<AlgorithmParamConfig> uw =
                    new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
            uw.eq("id", paramId).set("is_member", allMembers.contains(paramId) ? 1 : 0);
            algorithmParamConfigMapper.update(null, uw);
        }
    }

    /** members 文本 → id 列表；脏数据当作空，不阻塞页面 */
    private List<Integer> parseSetMemberIds(String raw) {
        List<Integer> result = new ArrayList<>();
        if (Texts.isBlank(raw)) {
            return result;
        }
        try {
            JSONArray array = JSON.parseArray(raw.trim());
            if (array != null) {
                for (int i = 0; i < array.size(); i++) {
                    Integer id = array.getInteger(i);
                    if (id != null && !result.contains(id)) {
                        result.add(id);
                    }
                }
            }
        } catch (Exception e) {
            log.warn("配置组成员不是合法 JSON，已按空处理: {}", raw);
        }
        return result;
    }

    private List<Integer> normalizeMemberIds(List<Integer> memberIds) {
        List<Integer> result = new ArrayList<>();
        if (memberIds == null) {
            return result;
        }
        for (Integer id : memberIds) {
            if (id != null && !result.contains(id)) {
                result.add(id);
            }
        }
        return result;
    }

    private AlgorithmParamConfigSetVO toAlgorithmParamConfigSetVO(AlgorithmParamConfigSet set) {
        AlgorithmParamConfigSetVO vo = new AlgorithmParamConfigSetVO();
        vo.setId(set.getId());
        vo.setCreateTime(set.getCreateTime());
        vo.setName(set.getName());
        vo.setDesc(set.getDesc());
        List<Integer> memberIds = parseSetMemberIds(set.getMembers());
        vo.setMemberIds(memberIds);
        vo.setMemberCount(memberIds.size());
        return vo;
    }

    /** 默认参数名唯一：拼命令行时它就是参数标识，重复会导致下游无法区分 */
    private void ensureParamNameAvailable(String paramName, Integer excludeId) {
        List<AlgorithmParamConfig> same = algorithmParamConfigMapper.selectList(
                new QueryWrapper<AlgorithmParamConfig>().lambda()
                        .eq(AlgorithmParamConfig::getParamName, paramName));
        if (same == null) {
            return;
        }
        for (AlgorithmParamConfig row : same) {
            if (excludeId == null || !excludeId.equals(row.getId())) {
                throw new RuntimeException("默认参数名已存在：" + paramName);
            }
        }
    }

    /** 值类型归一化：空值按 text（普通文本）处理，未知值直接报错 */
    private String normalizeAlgorithmValueType(String valueType) {
        String type = trimToNull(valueType);
        if (type == null) {
            return "text";
        }
        type = type.toLowerCase();
        if (!ALGORITHM_VALUE_TYPES.contains(type)) {
            throw new RuntimeException("未知的值类型: " + valueType);
        }
        return type;
    }

    /**
     * 单选 / 多选的候选项校验与归一化。
     *
     * <p>入参是前端拼好的 JSON 数组字符串 [{key,value}]，这里逐项校验：
     * key 必填且同一参数内不重复；value 缺省时用 key 兜底（界面上至少能显示出来）。
     * 值类型不是单选/多选时一律返回 null（落库即清空默认值）。
     */
    private String normalizeAlgorithmDefaultValue(String valueType, String raw) {
        // ratio / multiple / map 三者都用 [{key,value}] 表达内容，校验逻辑一致
        if (!"ratio".equals(valueType) && !"multiple".equals(valueType) && !"map".equals(valueType)) {
            return null;
        }
        if (Texts.isBlank(raw)) {
            throw new RuntimeException("值类型为单选 / 多选 / 键值对时，必须至少配置一项");
        }
        JSONArray array;
        try {
            array = JSON.parseArray(raw.trim());
        } catch (Exception e) {
            throw new RuntimeException("选项不是合法的 JSON 数组: " + e.getMessage());
        }
        if (array == null || array.isEmpty()) {
            throw new RuntimeException("值类型为单选 / 多选 / 键值对时，必须至少配置一项");
        }
        JSONArray normalized = new JSONArray();
        Set<String> keys = new LinkedHashSet<>();
        for (int i = 0; i < array.size(); i++) {
            Object item = array.get(i);
            if (!(item instanceof JSONObject)) {
                throw new RuntimeException("选项格式应为 {\"key\":\"..\",\"value\":\"..\"}");
            }
            JSONObject obj = (JSONObject) item;
            String key = trimToNull(obj.getString("key"));
            if (key == null) {
                throw new RuntimeException("第 " + (i + 1) + " 个选项缺少 key");
            }
            if (!keys.add(key)) {
                throw new RuntimeException("选项 key 重复：" + key);
            }
            String label = trimToNull(obj.getString("value"));
            JSONObject one = new JSONObject(true);
            one.put("key", key);
            one.put("value", label == null ? key : label);
            normalized.add(one);
        }
        return normalized.toJSONString();
    }

    /**
     * key / value 别名只服务 map 类型：其它类型一律落 NULL，
     * 避免「先存成 map 又改成文字」时留下过期别名。
     */
    private static String normalizeMapAlias(String valueType, String alias) {
        return "map".equals(valueType) ? trimToNull(alias) : null;
    }

    private AlgorithmParamConfigVO toAlgorithmParamConfigVO(AlgorithmParamConfig row) {
        AlgorithmParamConfigVO vo = new AlgorithmParamConfigVO();
        vo.setId(row.getId());
        vo.setName(row.getName());
        vo.setParamName(row.getParamName());
        vo.setIfSystem(Boolean.TRUE.equals(row.getIfSystem()));
        vo.setValueType(row.getValueType());
        vo.setDefaultValue(row.getDefaultValue());
        vo.setKeyAlias(row.getKeyAlias());
        vo.setValueAlias(row.getValueAlias());
        vo.setDesc(row.getDesc());
        vo.setCreateTime(row.getCreateTime());
        vo.setIsMember(Boolean.TRUE.equals(row.getIsMember()));
        return vo;
    }

    /** 去空白；空串一律归一成 null，避免库里出现 "" 与 null 两种空值 */
    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
