package com.citylearn.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 本地文件（图片）资源根目录配置
 */
@Component
@ConfigurationProperties(prefix = "citylearn.file")
public class FileResourceProperties {

    /**
     * 图片文件存放的根目录，支持相对路径或绝对路径
     */
    private String imageBasePath = "D:/citylearn-demo/uploads/images";

    public String getImageBasePath() {
        return imageBasePath;
    }

    public void setImageBasePath(String imageBasePath) {
        this.imageBasePath = imageBasePath;
    }


    private String outFilePath = "D:/citylearn-demo/output";

    public String getOutFilePath() {
        return outFilePath;
    }

    public void setOutFilePath(String outFilePath) {
        this.outFilePath = outFilePath;
    }

    private String pythonFilePath = "D:/citylearn-demo/citylearnpy";

    public String getPythonFilePath() {
        return pythonFilePath;
    }

    public void setPythonFilePath(String pythonFilePath) {
        this.pythonFilePath = pythonFilePath;
    }
}
