package com.citylearn.common;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * 仿真导出目录的定位规则（从 BaseDataService 抽出，供多个 service 复用）。
 *
 * <p>任务的导出数据可能直接落在任务目录，也可能落在其下的某个子目录（旧任务/流水线子任务），
 * 这两条规则原先散落在读取仪表盘与首页能源的代码里，抽到这里避免各写一份。</p>
 */
public final class SimulationDataPaths {

    private SimulationDataPaths() {
    }

    /** 任务目录规则：{outFilePath}/outkpis/{taskId}。 */
    public static Path taskDir(String outFilePath, String taskId) {
        return Paths.get(outFilePath, "outkpis", taskId);
    }

    /** 任务目录里若没有 exported_data_*.csv，就按名称序遍历子目录找第一个有的。 */
    public static Path resolve(Path taskDir) throws IOException {
        if (!Files.exists(taskDir)) {
            return taskDir;
        }
        if (hasExportedDataCsv(taskDir)) {
            return taskDir;
        }
        try (Stream<Path> children = Files.list(taskDir)) {
            List<Path> subdirs = children.filter(Files::isDirectory)
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .collect(Collectors.toList());
            for (Path sub : subdirs) {
                if (hasExportedDataCsv(sub)) {
                    return sub;
                }
            }
        }
        return taskDir;
    }

    /** 目录下是否存在 exported_data_*.csv。 */
    public static boolean hasExportedDataCsv(Path dir) throws IOException {
        if (!Files.isDirectory(dir)) {
            return false;
        }
        try (Stream<Path> stream = Files.list(dir)) {
            return stream.anyMatch(p -> Files.isRegularFile(p)
                    && p.getFileName().toString().startsWith("exported_data_")
                    && p.getFileName().toString().endsWith(".csv"));
        }
    }
}