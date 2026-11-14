package com.citylearn.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 任务生命周期埋点：把「建任务 → 起进程 → 状态迁移 → 收尾」的每一步落成一行 JSON。
 *
 * <p><b>为什么需要它</b>：任务执行引擎是 {@code BaseDataService} 里最重的一块（约 90 个方法、
 * 115 个方法连成的强连通块）。拆它之前必须先有「行为可比对的东西」——HTTP 响应基线只能覆盖
 * 查询接口，跑一次训练的几十个分钟里状态怎么走、进程什么时候起、退出码是多少，基线一概兜不住。
 * 有了这个埋点，拆分前后各跑一次同样的脚本，把两份 {@code task_trace.jsonl} 对齐就能看出差异。</p>
 *
 * <p><b>零侵入</b>：本类只写日志 / 追加一个文件，<b>不读库、不改状态、不参与任何判断</b>。
 * 内部所有异常一律吞掉（最坏情况是少一行埋点），绝不允许因为它让任务失败。</p>
 *
 * <p><b>两类出口</b>：</p>
 * <ul>
 *   <li>日志（logger 名 {@code TASK_TRACE}）——实时看；</li>
 *   <li>{@code <任务目录>/task_trace.jsonl} —— 追加写，任务跑完仍在，可跨版本 diff。</li>
 * </ul>
 *
 * <p>示例行：</p>
 * <pre>
 * {"ts":"2026-10-20T17:30:01.123","taskId":"a1b2","event":"STATUS","from":0,"to":1,"elapsedMs":73412}
 * </pre>
 *
 * <p>事件名约定：{@code BORN}（任务行落库）、{@code LAUNCH}（准备起进程）、
 * {@code PROCESS_START} / {@code PROCESS_EXIT}（进程已起 / 已退出，带 pid、code）、
 * {@code STATUS}（状态迁移，带 from / to / reason）、{@code STOP_REQUEST}（用户点终止）、
 * {@code RELAY}（子任务→父任务接力）、{@code ASYNC_ENTER} / {@code ASYNC_EXIT}（后台线程进出）。</p>
 */
public final class TaskTracer {

    /** 每个任务目录下的埋点文件名。 */
    public static final String TRACE_FILE = "task_trace.jsonl";

    private static final Logger log = LoggerFactory.getLogger("TASK_TRACE");

    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS").withZone(ZoneId.systemDefault());

    /** 任务起点时间戳，用于每条事件带 elapsedMs。只是诊断用，超限直接清空，不做 LRU。 */
    private static final Map<String, Long> STARTED_AT = new ConcurrentHashMap<>();
    private static final int MAX_TRACKED = 4096;

    private TaskTracer() {
    }

    /**
     * 任务行刚落库时调用，登记生命周期起点。
     *
     * @param taskDir 任务目录（可为 null：目录还没建时只记日志）
     * @param taskId  任务 id
     * @param pyId    脚本 id（编排任务为 null）
     * @param source  来源：{@code editor}（代码编辑器直接执行）/ {@code pipeline}（编排任务）/ {@code pipeline-sub}（子任务）
     */
    public static void born(Path taskDir, String taskId, String pyId, String source) {
        markStarted(taskId);
        emit(taskDir, taskId, "BORN", null, null, source, "pyId", pyId);
    }

    /** 普通事件（不涉及状态变化）。{@code kv} 按 key, value, key, value 交替传。 */
    public static void event(Path taskDir, String taskId, String name, String... kv) {
        emit(taskDir, taskId, name, null, null, null, kv);
    }

    /**
     * 状态迁移。
     *
     * @param from   迁移前状态（拿不到就传 null，只记 to）
     * @param to     迁移后状态
     * @param reason 触发原因（如 success / user-stopped / reconcile-interrupted / relay）
     */
    public static void transition(Path taskDir, String taskId, Integer from, int to, String reason) {
        emit(taskDir, taskId, "STATUS", from, to, reason);
    }

    /** 已结束状态：1-执行完成 / 2-执行失败 / 3-运行终止 / 4-已中断。 */
    public static boolean isTerminal(Integer status) {
        return status != null && (status == 1 || status == 2 || status == 3 || status == 4);
    }

    // ------------------------------------------------------------------ 内部

    private static void markStarted(String taskId) {
        if (taskId == null) {
            return;
        }
        if (STARTED_AT.size() > MAX_TRACKED) {
            // 纯诊断数据，溢出直接清：宁可丢 elapsedMs，也不要无界增长
            STARTED_AT.clear();
        }
        STARTED_AT.put(taskId, System.currentTimeMillis());
    }

    private static void emit(Path taskDir, String taskId, String name, Integer from, Integer to,
                             String reason, String... kv) {
        try {
            Long started = taskId == null ? null : STARTED_AT.get(taskId);
            StringBuilder sb = new StringBuilder(192);
            sb.append("{\"ts\":\"").append(TS.format(Instant.now())).append('"');
            appendString(sb, "taskId", taskId);
            appendString(sb, "event", name);
            if (from != null) {
                sb.append(",\"from\":").append(from);
            }
            if (to != null) {
                sb.append(",\"to\":").append(to);
            }
            appendString(sb, "reason", clip(reason));
            if (started != null) {
                sb.append(",\"elapsedMs\":").append(System.currentTimeMillis() - started);
            }
            if (kv != null) {
                for (int i = 0; i + 1 < kv.length; i += 2) {
                    appendString(sb, kv[i], clip(kv[i + 1]));
                }
            }
            sb.append('}');
            String line = sb.toString();

            log.info(line);

            if (taskDir != null) {
                Path file = taskDir.resolve(TRACE_FILE);
                Files.createDirectories(taskDir);
                Files.write(file, (line + System.lineSeparator()).getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            }
        } catch (Exception e) {
            // 埋点永远不能影响业务：这里连 warn 都不打（避免异常路径把日志刷屏）
            log.debug("任务埋点写入失败, taskId={}, event={}, err={}", taskId, name, e.getMessage());
        }
    }

    private static void appendString(StringBuilder sb, String key, String value) {
        if (value == null) {
            return;
        }
        sb.append(",\"").append(escape(key)).append("\":\"").append(escape(value)).append('"');
    }

    /** 单字段上限 300 字符：异常消息可能很长，不让它把一行埋点撑爆。 */
    private static String clip(String value) {
        if (value == null || value.length() <= 300) {
            return value;
        }
        return value.substring(0, 297) + "...";
    }

    private static String escape(String raw) {
        StringBuilder out = new StringBuilder(raw.length() + 8);
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.toString();
    }
}
