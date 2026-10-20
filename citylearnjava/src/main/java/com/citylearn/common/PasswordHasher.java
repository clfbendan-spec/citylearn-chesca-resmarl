package com.citylearn.common;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * 密码哈希：bcrypt + 每用户随机盐（盐由 bcrypt 自己生成并嵌在哈希串里）。
 *
 * <p><b>为什么不用 MD5/SHA</b>：那些是「快」哈希，一张显卡每秒能算上亿次，
 * 弱口令几乎瞬间被彩虹表/爆破破掉。bcrypt 的设计目标是「故意慢」，
 * 单次校验约 50~100 ms，对正常登录无感，对爆破是几个数量级的成本提升。
 *
 * <p><b>存储格式</b>：{@code {bcrypt}$2a$10$<22位盐><31位摘要>}，总长 68 字符
 * （表字段 varchar(128) 足够）。前缀 {@code {bcrypt}} 是自加的，
 * 用来区分「已哈希」与「历史明文」——旧密码在库里是裸串，没有前缀。
 *
 * <p><b>兼容与迁移</b>：{@link #matches(String, String)} 对裸串退化为恒定时间明文比较，
 * 让老账号仍能登录；登录成功后由 {@code UserService.login} 判定 {@link #isHashed(String)} 为 false
 * 即写回哈希，于是每个账号在「下一次登录时」自动完成升级，无需停机。
 *
 * <p><b>注意</b>：bcrypt 只取密码前 72 字节，超长部分会被忽略；
 * 本项目密码长度限制 128 字符，中文按 UTF-8 三字节计也不会触到该边界（超过也只会被截断，不影响安全）。
 */
@Component
public class PasswordHasher {

    /** 哈希前缀：区分哈希与历史明文。 */
    public static final String PREFIX_BCRYPT = "{bcrypt}";

    /** 强度 10 ⇒ 2^10 轮，OWASP 对 bcrypt 的下限要求就是 work factor ≥ 10。 */
    private static final int BCRYPT_STRENGTH = 10;

    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(BCRYPT_STRENGTH);

    /**
     * 把明文密码转成可入库的哈希串（每次调用盐都不同，同一个密码两次编码结果不同，属正常）。
     */
    public String encode(String rawPassword) {
        if (rawPassword == null || rawPassword.isEmpty()) {
            throw new IllegalArgumentException("密码不能为空");
        }
        return PREFIX_BCRYPT + encoder.encode(rawPassword);
    }

    /** 库里这一串是否已经是 bcrypt 哈希（false ⇒ 历史遗留明文，应尽快升级）。 */
    public boolean isHashed(String storedPassword) {
        return storedPassword != null && storedPassword.startsWith(PREFIX_BCRYPT);
    }

    /**
     * 校验明文密码与库中存储值是否匹配。已哈希走 bcrypt 比对，裸串走恒定时间明文比对。
     */
    public boolean matches(String rawPassword, String storedPassword) {
        if (rawPassword == null || storedPassword == null || storedPassword.isEmpty()) {
            return false;
        }
        if (isHashed(storedPassword)) {
            try {
                return encoder.matches(rawPassword, storedPassword.substring(PREFIX_BCRYPT.length()));
            } catch (IllegalArgumentException e) {
                // 哈希串被手工改坏（手工改库、字段被截断等）⇒ 视为不匹配，不要让登录接口抛 500
                return false;
            }
        }
        return MessageDigest.isEqual(
                rawPassword.getBytes(StandardCharsets.UTF_8),
                storedPassword.getBytes(StandardCharsets.UTF_8));
    }
}
