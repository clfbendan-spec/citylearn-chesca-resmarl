package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.citylearn.common.Result;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.param.PipelineStepConfig;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.param.PyFileParam;
import com.citylearn.vo.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * α 扫描结果查询（原 BaseDataService 的一部分，按领域拆出）。
 *
 * <p>数据源是 citylearnpy/ablation_results 下的 registry 索引与 summary 文件，
 * 因此本类只依赖文件路径配置，不碰数据库。</p>
 */
@Slf4j
@Service
public class AlphaSweepService {

    @Resource
    private FileResourceProperties fileResourceProperties;

    /**
     * α 扫描 registry：citylearnpy/ablation_results/registry/index.json
     */
    public List<Map<String, Object>> listAlphaSweepRuns() {
        Path indexPath = getAlphaSweepRegistryIndexPath();
        if (!Files.isRegularFile(indexPath)) {
            return Collections.emptyList();
        }
        try {
            String text = new String(Files.readAllBytes(indexPath), StandardCharsets.UTF_8);
            if (text.startsWith("\uFEFF")) {
                text = text.substring(1);
            }
            Object parsed = JSON.parse(text);
            if (parsed instanceof JSONArray) {
                return toMapList((JSONArray) parsed);
            }
            if (parsed instanceof JSONObject) {
                JSONArray runs = ((JSONObject) parsed).getJSONArray("runs");
                return runs == null ? Collections.emptyList() : toMapList(runs);
            }
        } catch (Exception e) {
            log.warn("读取 α 扫描 registry 失败: {}", e.getMessage());
        }
        return Collections.emptyList();
    }

    public Map<String, Object> getAlphaSweepDetail(String runId) throws IOException {
        if (runId == null || runId.trim().isEmpty()) {
            throw new IllegalArgumentException("runId 不能为空");
        }
        List<Map<String, Object>> runs = listAlphaSweepRuns();
        Map<String, Object> entry = null;
        for (Map<String, Object> r : runs) {
            if (runId.equals(String.valueOf(r.get("run_id")))) {
                entry = r;
                break;
            }
        }
        Path summaryPath = null;
        Path pyRoot = Paths.get(fileResourceProperties.getPythonFilePath()).normalize();
        if (entry != null && entry.get("rel_dir") != null) {
            summaryPath = pyRoot.resolve(String.valueOf(entry.get("rel_dir")))
                    .resolve(entry.get("summary_file") != null
                            ? String.valueOf(entry.get("summary_file"))
                            : "alpha_sweep_summary.json")
                    .normalize();
        }
        if (summaryPath == null || !Files.isRegularFile(summaryPath)) {
            // 兜底：按 run_id 目录扫描
            Path candidate = pyRoot.resolve("ablation_results").resolve(runId).resolve("alpha_sweep_summary.json");
            if (Files.isRegularFile(candidate)) {
                summaryPath = candidate;
            }
        }
        if (summaryPath == null || !Files.isRegularFile(summaryPath)) {
            throw new FileNotFoundException("未找到 α 扫描结果: " + runId);
        }
        String text = new String(Files.readAllBytes(summaryPath), StandardCharsets.UTF_8);
        if (text.startsWith("\uFEFF")) {
            text = text.substring(1);
        }
        JSONObject obj = JSON.parseObject(text);
        Map<String, Object> result = new LinkedHashMap<>(obj);
        result.put("_summary_path", summaryPath.toAbsolutePath().toString());
        return result;
    }

    private Path getAlphaSweepRegistryIndexPath() {
        return Paths.get(fileResourceProperties.getPythonFilePath(), "ablation_results", "registry", "index.json")
                .normalize();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> toMapList(JSONArray arr) {
        List<Map<String, Object>> list = new ArrayList<>();
        if (arr == null) {
            return list;
        }
        for (int i = 0; i < arr.size(); i++) {
            Object item = arr.get(i);
            if (item instanceof Map) {
                list.add(new LinkedHashMap<>((Map<String, Object>) item));
            } else if (item instanceof JSONObject) {
                list.add(new LinkedHashMap<String, Object>(((JSONObject) item)));
            }
        }
        return list;
    }
}
