package com.citylearn.common;

/**
 * 字符串判空的统一口径。
 *
 * <p>拆自 {@code BaseDataService}（2026-10-20）：该类里原本自带一份 {@code isBlank}，
 * 拆出的 service 也要用同一套语义，所以上提到公共工具，避免各写一份后语义漂移
 * （例如有的实现把全角空格也当空白，有的不当）。
 */
public final class Texts {

    private Texts() {
    }

    /** null 或仅含空白 → true。 */
    public static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    /** 取反，读起来比 {@code !isBlank(x)} 顺。 */
    public static boolean isNotBlank(String value) {
        return !isBlank(value);
    }
}
