package com.citylearn.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.CitylearnDatasetMapper;
import com.citylearn.entity.CitylearnDataset;
import com.citylearn.vo.CitylearnDatasetVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.annotation.Resource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.stream.Collectors;

@Slf4j
@Service
public class CitylearnDatasetService {

    @Resource
    private CitylearnDatasetMapper citylearnDatasetMapper;

    @Resource
    private FileResourceProperties fileResourceProperties;

    @Resource
    private JdbcTemplate jdbc;

    public String resolveCurrency(String schemaKey) {
        if (schemaKey == null || schemaKey.isBlank()) return null;
        String key = schemaKey;
        if (key.matches("\\d+")) {
            CitylearnDataset row = citylearnDatasetMapper.selectById(key);
            if (row == null) return null;
            key = row.getSchemaKey();
        }
        try {
            String currency = readCurrency(resolveDatasetDir(key));
            if (currency != null) return currency;
        } catch (Exception error) {
            log.debug("Unable to read currency metadata for dataset {}", key, error);
        }
        // Legacy generated releases may predate currency in their manifest.
        List<String> currencies = jdbc.query(
                "SELECT JSON_UNQUOTE(JSON_EXTRACT(c.metadata,'$.currency')) FROM community_dataset_owner o "
                + "JOIN community_dataset_release r ON r.id=o.release_id "
                + "JOIN managed_community c ON c.id=o.community_id WHERE BINARY r.schema_key=BINARY ?",
                (rs, n) -> rs.getString(1), key);
        return currencies.size() == 1 ? normalizeCurrency(currencies.get(0)) : null;
    }

    static String readCurrency(Path directory) throws java.io.IOException {
        Path manifest = directory.resolve("manifest.json");
        if (Files.isRegularFile(manifest)) {
            Map<?, ?> metadata = new ObjectMapper().readValue(manifest.toFile(), Map.class);
            Object building = metadata.get("building");
            String currency = normalizeCurrency(building instanceof Map ? ((Map<?, ?>) building).get("currency") : metadata.get("currency"));
            if (currency != null) return currency;
        }
        // The bundled original Online1 has no community publication manifest.
        return "citylearn_challenge_2023_phase_2_online_evaluation_1".equals(directory.getFileName().toString())
                ? "USD" : null;
    }

    private static String normalizeCurrency(Object value) {
        String currency = value instanceof String ? ((String) value).trim().toUpperCase(Locale.ROOT) : "";
        return currency.isEmpty() ? null : currency;
    }

    public List<CitylearnDatasetVO> listEnabledDatasets() {
        List<CitylearnDataset> rows = citylearnDatasetMapper.selectList(
                new LambdaQueryWrapper<CitylearnDataset>()
                        .eq(CitylearnDataset::getEnabled, 1)
                        .orderByAsc(CitylearnDataset::getSortOrder)
                        .orderByAsc(CitylearnDataset::getId)
        );
        if (rows == null || rows.isEmpty()) {
            throw new RuntimeException("citylearn_dataset 表无数据，请先执行 db/citylearn_dataset.sql");
        }
        return rows.stream().map(this::toVo).collect(Collectors.toList());
    }

    public CitylearnDataset findBySchemaKey(String schemaKey) {
        if (schemaKey == null || schemaKey.trim().isEmpty()) {
            return null;
        }
        return citylearnDatasetMapper.selectOne(
                new LambdaQueryWrapper<CitylearnDataset>()
                        .eq(CitylearnDataset::getSchemaKey, schemaKey.trim())
                        .last("LIMIT 1")
        );
    }

    /**
     * 解析数据集绝对目录：优先用库表 relative_path，否则回退到 schema 名探测。
     */
    public Path resolveDatasetDir(String schemaKey) {
        CitylearnDataset row = findBySchemaKey(schemaKey);
        String root = fileResourceProperties.getPythonFilePath();
        if (root == null || root.trim().isEmpty()) {
            throw new RuntimeException("未配置 citylearn.file.python-file-path");
        }
        Path pythonRoot = Paths.get(root.trim());

        List<Path> tried = new ArrayList<>();
        if (row != null && row.getRelativePath() != null && !row.getRelativePath().trim().isEmpty()) {
            Path p = pythonRoot.resolve(row.getRelativePath().trim()).normalize();
            tried.add(p);
            if (Files.isDirectory(p) && Files.isRegularFile(p.resolve("Building_1.csv"))) {
                return p;
            }
        }

        String key = (schemaKey == null || schemaKey.trim().isEmpty())
                ? CityLearnLocalDatasetService.DEFAULT_SCHEMA
                : schemaKey.trim();
        String[] roots = {
                "CHESCA-copy/data/schemas",
                "CHESCA-main/data/schemas",
                "data/schemas",
                "datasets"
        };
        for (String rel : roots) {
            Path candidate = pythonRoot.resolve(rel).resolve(key).normalize();
            tried.add(candidate);
            if (Files.isDirectory(candidate) && Files.isRegularFile(candidate.resolve("Building_1.csv"))) {
                return candidate;
            }
        }
        throw new RuntimeException("找不到本地数据集目录 schema=" + key + " tried=" + tried);
    }

    private CitylearnDatasetVO toVo(CitylearnDataset row) {
        CitylearnDatasetVO vo = new CitylearnDatasetVO();
        vo.setId(row.getId());
        vo.setSchemaKey(row.getSchemaKey());
        vo.setDisplayName(row.getDisplayName());
        vo.setRelativePath(row.getRelativePath());
        vo.setBuildingCount(row.getBuildingCount());
        vo.setTimeSteps(row.getTimeSteps());
        vo.setChescaCompatible(row.getChescaCompatible() != null && row.getChescaCompatible() == 1);
        vo.setDescription(row.getDescription());
        return vo;
    }
}
