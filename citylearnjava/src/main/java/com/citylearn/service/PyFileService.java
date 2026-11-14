package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.citylearn.common.AlgorithmConfigJson;
import com.citylearn.common.Texts;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.PyFileMapper;
import com.citylearn.entity.PyFile;
import com.citylearn.param.PyFileParam;
import com.citylearn.vo.PyFileVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 代码编辑器的「脚本文件」域：文件列表、内容读写、新建、改名/改简介、删除、算法配置保存。
 *
 * <p>从 {@code BaseDataService} 按功能域拆出（依赖分析显示这一簇与任务执行域之间
 * 没有内部调用，是耦合最低的一块）。脚本内容落盘在配置的 Python 根目录，
 * 元数据落 {@code py_file} 表。</p>
 */
@Service
@Slf4j
public class PyFileService {

    /** 脚本类型合法取值：train 只训练 / eval 只评估 / both 训练+评估一体 */
    private static final Set<String> SCRIPT_TYPES = new HashSet<>(Arrays.asList("train", "eval", "both"));

    @Resource
    private PyFileMapper pyFileMapper;

    @Resource
    private FileResourceProperties fileResourceProperties;

    private Path scriptPath(String fileName) {
        if (fileName == null || fileName.trim().isEmpty()) {
            throw new IllegalArgumentException("Python 文件名不能为空");
        }
        Path root = Paths.get(fileResourceProperties.getPythonFilePath()).toAbsolutePath().normalize();
        Path path = root.resolve(fileName).normalize();
        if (!path.startsWith(root)) {
            throw new IllegalArgumentException("Python 文件必须位于配置的脚本目录内");
        }
        return path;
    }

    /**
     * 代码编辑器「文件列表」。
     *
     * @param createUser 创建人（Controller 固定传 admin）
     * @param scriptType 脚本类型筛选项：train / eval / both；
     *                   传 null、空串或 "all" 表示不筛选（返回全部类型）。
     *                   非法取值按「不筛选」处理并记 warn，避免前端参数拼错导致列表空白。
     */
    public List<PyFileVO> getPyFileList(String createUser, String scriptType) {
        String normalized = normalizeScriptTypeFilter(scriptType);
        List<PyFile> list = pyFileMapper.getPyFileList(createUser, normalized);
        return JSON.parseArray(JSON.toJSONString(list), PyFileVO.class);
    }

    /**
     * 归一化脚本类型筛选值：null / "" / "all" / 非法值 → null（不筛选）。
     * 与前端 MonacoEditor.normalizeScriptType 的语义保持一致。
     */
    private String normalizeScriptTypeFilter(String scriptType) {
        if (scriptType == null) {
            return null;
        }
        String value = scriptType.trim().toLowerCase();
        if (value.isEmpty() || "all".equals(value)) {
            return null;
        }
        if (SCRIPT_TYPES.contains(value)) {
            return value;
        }
        log.warn("getPyFileList 收到未知的 scriptType 筛选值: {}，已忽略该筛选（返回全部类型）", scriptType);
        return null;
    }

    /**
     * 读取脚本正文。文件缺失时返回空串（历史行为，调用方据此判断为空脚本）。
     */
    public String getPyFile(String id) {
        PyFile pyFile = pyFileMapper.selectById(id);

        try {
            return Files.readString(scriptPath(pyFile.getFileName()), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.error("读取脚本内容失败: {}", e.getMessage(), e);
        }
        return "";
    }

    /**
     * 保存脚本：三选一 —— 改文件名（同时移动磁盘文件）/ 改简介 / 写正文。
     */
    public void savePyFile(PyFileParam pyFileParam) throws Exception {
        PyFile pyFile = pyFileMapper.selectById(pyFileParam.getId());

        if (null != pyFileParam.getFileName()) {
            List<PyFile> list = pyFileMapper.selectList(new QueryWrapper<PyFile>().lambda()
                    .eq(PyFile::getFileName, pyFileParam.getFileName())
                    .ne(PyFile::getId, pyFile.getId()));
            if (null != list && list.size() > 0) {
                throw new Exception("文件名已存在");
            }

            Path source = scriptPath(pyFile.getFileName());
            Path target = scriptPath(pyFileParam.getFileName());
            try {
                Files.move(source, target);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
            pyFile.setFileName(pyFileParam.getFileName());
            pyFileMapper.updateById(pyFile);

        } else if (null != pyFileParam.getDescription()) {
            pyFile.setDescription(pyFileParam.getDescription());
            pyFileMapper.updateById(pyFile);
        } else {
            Files.write(scriptPath(pyFile.getFileName()), pyFileParam.getCode().getBytes(StandardCharsets.UTF_8));
        }
    }

    /**
     * 新建脚本：id 取时间戳，同时落库与建空文件。
     */
    public PyFileVO addPyFile() throws IOException {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyyMMddHHmmss");
        Date newDate = new Date();
        PyFile pyFile = new PyFile();
        pyFile.setId(sdf.format(newDate));
        pyFile.setFileName(pyFile.getId() + ".py");
        pyFile.setDescription("无");
        pyFile.setCreateUser("admin");
        pyFile.setIfSystem(false);
        // 新脚本必须可见；该字段只控制脚本列表，执行记录展示另由 py_task 管理。
        pyFile.setIfShow(true);
        // 新建文件默认「训练+评估一体」；需要区分时改 py_file.script_type（train/eval/both）
        pyFile.setScriptType("both");
        pyFile.setCreateTime(newDate);
        pyFileMapper.insert(pyFile);
        Files.createFile(scriptPath(pyFile.getFileName()));
        return JSON.parseObject(JSON.toJSONString(pyFile), PyFileVO.class);
    }

    /**
     * 删除脚本（只删元数据；磁盘文件保留，便于误删后按 id 找回）。
     */
    public void deletePyFile(PyFileParam pyFileParam) {
        if (pyFileParam == null || pyFileParam.getId() == null || pyFileParam.getId().trim().isEmpty()) {
            throw new RuntimeException("文件 id 不能为空");
        }
        PyFile existing = pyFileMapper.selectById(pyFileParam.getId());
        if (existing == null) {
            throw new RuntimeException("文件不存在");
        }
        if (Boolean.TRUE.equals(existing.getIfSystem())) {
            throw new RuntimeException("系统内置文件不可删除");
        }
        pyFileMapper.deleteById(pyFileParam.getId());
    }

    /**
     * 保存脚本的「算法配置」JSON。
     *
     * @param pyFileId        脚本 id
     * @param algorithmConfig JSON 数组字符串；空值视为清空配置
     */
    public void savePyFileAlgorithmConfig(String pyFileId, String algorithmConfig) {
        if (Texts.isBlank(pyFileId)) {
            throw new RuntimeException("文件 id 不能为空");
        }
        PyFile file = pyFileMapper.selectById(pyFileId);
        if (file == null) {
            throw new RuntimeException("文件不存在: " + pyFileId);
        }
        String normalized = AlgorithmConfigJson.normalize(algorithmConfig);
        PyFile update = new PyFile();
        update.setId(pyFileId);
        update.setAlgorithmConfig(normalized);
        pyFileMapper.updateById(update);
        log.info("保存脚本算法配置, pyFileId={}, 配置={}", pyFileId, normalized);
    }
}
