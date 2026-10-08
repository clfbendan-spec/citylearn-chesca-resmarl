package com.citylearn.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.CitylearnDatasetMapper;
import com.citylearn.entity.CitylearnDataset;
import com.citylearn.vo.CitylearnDatasetVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
public class CitylearnDatasetService {

    @Resource
    private CitylearnDatasetMapper citylearnDatasetMapper;

    @Resource
    private FileResourceProperties fileResourceProperties;

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
