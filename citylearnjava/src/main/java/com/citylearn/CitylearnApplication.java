package com.citylearn;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.citylearn.dao")
public class CitylearnApplication {

    public static void main(String[] args) {
        SpringApplication.run(CitylearnApplication.class, args);
    }

}
