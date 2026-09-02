package com.citylearn.controller;

import com.citylearn.service.LocalFileService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import javax.annotation.Resource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Path;

/**
 * 本地图片资源访问接口，供前端直接作为 img src 使用
 *
 * 示例：GET /web/file/image?filePath=building-01.jpg
 */
@RestController
@Api(value = "FileResourceController", tags = {"文件资源"})
@RequestMapping("/web/file")
public class FileResourceController {

    @Resource
    private LocalFileService localFileService;

    @ApiOperation("根据相对路径读取本地图片")
    @GetMapping("/image/{filePath}")
    public ResponseEntity<FileSystemResource> getImage(@PathVariable String filePath) {
        try {
            Path path = localFileService.resolveImage(filePath);
            String contentType = localFileService.probeContentType(path);
            FileSystemResource resource = new FileSystemResource(path.toFile());
            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(contentType))
                    .header(HttpHeaders.CACHE_CONTROL, "max-age=3600")
                    .body(resource);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        } catch (IOException e) {
            return ResponseEntity.notFound().build();
        }
    }
}
