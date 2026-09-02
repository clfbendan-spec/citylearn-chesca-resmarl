package com.citylearn.service;

import com.citylearn.config.FileResourceProperties;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * 本地图片文件读取服务
 */
@Service
public class LocalFileService {

    private static final Set<String> ALLOWED_EXTENSIONS = new HashSet<>(
            Arrays.asList("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg")
    );

    @Resource
    private FileResourceProperties fileResourceProperties;

    /**
     * 根据相对路径解析本地图片文件
     *
     * @param filePath 相对路径，如 building-01.jpg 或 sub/building-01.jpg
     */
    public Path resolveImage(String filePath) throws IOException {
        if (!StringUtils.hasText(filePath)) {
            throw new IllegalArgumentException("文件路径不能为空");
        }
        String normalized = filePath.replace("\\", "/").trim();
        if (normalized.contains("..")) {
            throw new IllegalArgumentException("非法的文件路径");
        }
        while (normalized.startsWith("/")) {
            normalized = normalized.substring(1);
        }

        String extension = getExtension(normalized);
        if (!ALLOWED_EXTENSIONS.contains(extension)) {
            throw new IllegalArgumentException("不支持的图片格式");
        }

        Path basePath = Paths.get(fileResourceProperties.getImageBasePath()).toAbsolutePath().normalize();
        if (!Files.exists(basePath)) {
            Files.createDirectories(basePath);
        }

        Path target = basePath.resolve(normalized).normalize();
        if (!target.startsWith(basePath)) {
            throw new IllegalArgumentException("非法的文件路径");
        }
        if (!Files.exists(target) || !Files.isRegularFile(target)) {
            throw new IOException("文件不存在");
        }
        return target;
    }

    public String probeContentType(Path path) throws IOException {
        String contentType = Files.probeContentType(path);
        if (contentType != null) {
            return contentType;
        }
        String ext = getExtension(path.getFileName().toString());
        switch (ext) {
            case "jpg":
            case "jpeg":
                return "image/jpeg";
            case "png":
                return "image/png";
            case "gif":
                return "image/gif";
            case "bmp":
                return "image/bmp";
            case "webp":
                return "image/webp";
            case "svg":
                return "image/svg+xml";
            default:
                return "application/octet-stream";
        }
    }

    private String getExtension(String fileName) {
        int index = fileName.lastIndexOf('.');
        if (index < 0 || index == fileName.length() - 1) {
            return "";
        }
        return fileName.substring(index + 1).toLowerCase();
    }
}
