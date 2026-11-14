package com.citylearn.common;

import java.util.UUID;

/**
 * 主键生成规则（原 {@code config/SystemConfig#getUUID} 抽出）。
 *
 * <p>本项目所有业务主键都是「32 位无横线小写 UUID」，与数据库 {@code varchar(32)} 列宽一致。
 * 集中在一处，避免每个实体各自拼 {@code UUID.randomUUID().toString().replace("-", "")}。</p>
 */
public final class Ids {

    private Ids() {
    }

    /** 32 位无横线 UUID（例：{@code 3f2a1b4c5d6e4f7a8b9c0d1e2f3a4b5c}）。 */
    public static String uuid() {
        return UUID.randomUUID().toString().replace("-", "");
    }
}