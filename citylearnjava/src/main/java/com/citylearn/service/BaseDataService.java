package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.citylearn.common.AlgorithmConfigJson;
import com.citylearn.common.Ids;
import com.citylearn.common.Result;
import com.citylearn.common.SimulationDataPaths;
import com.citylearn.common.TaskNaming;
import com.citylearn.common.TaskTracer;
import com.citylearn.common.Texts;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.param.PipelineStepConfig;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.param.PyFileParam;
import com.citylearn.vo.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * <p>
 *  服务实现类
 * </p>
 *
 * @author Your Name
 * @since 2025-06-08
 */
@Slf4j
@Service
public class BaseDataService {

    @Resource
    private KpisMapper kpisMapper;
    @Resource
    private PyFileMapper pyFileMapper;
    @Resource
    private AlgorithmParamConfigMapper algorithmParamConfigMapper;
    @Resource
    private PyTaskMapper pyTaskMapper;
    @Resource
    private CitylearnDatasetMapper citylearnDatasetMapper;
    @Resource
    private CitylearnDatasetService citylearnDatasetService;
    @Resource
    private FileResourceProperties fileResourceProperties;

    private final ConcurrentHashMap<String, HomeEnergyFlowVO> homeEnergyFlowCache = new ConcurrentHashMap<>();
    @Resource(name = "pythonTaskExecutor")
    private Executor pythonTaskExecutor;
    @Resource
    private BatteryMinSocConfigService batteryMinSocConfigService;
    @Resource
    private CityLearnLocalDatasetService cityLearnLocalDatasetService;

    private static Map<String, List<String>> CONSOLE_MAP = new HashMap<>();

    private static Map<String, Integer> CONSOLE_INDEX_MAP = new HashMap<>();

    /** 任务实时 stdout 缓冲（按行追加，供轮询读取） */
    private static final ConcurrentHashMap<String, StringBuilder> TASK_OUTPUT_BUFFER = new ConcurrentHashMap<>();

    /** 运行中的 Python 进程（taskId -> Process），供「终止运行」按钮 kill 用 */
    private static final ConcurrentHashMap<String, Process> RUNNING_PROCESS = new ConcurrentHashMap<>();

    /**
     * 被用户手动终止的任务集合（taskId）。
     * 进程被 destroy 后退出码必然非 0，靠这个标记把它区分成「运行终止(3)」而不是「执行失败(2)」。
     */
    private static final Set<String> STOPPED_TASKS = ConcurrentHashMap.newKeySet();

    /**
     * 任务状态：后端服务在任务执行期间重启 → 任务已中断。
     * 与 PyTaskVO.statusDescOf 保持一致（0执行中 1执行完成 2执行失败 3运行终止 4已中断）。
     */
    public static final int TASK_STATUS_INTERRUPTED = 4;

    /** 服务重启导致任务中断时写入 error.log 的说明（前端会展示在输出区下方）。 */
    private static final String INTERRUPTED_TASK_MESSAGE =
            "后端服务在任务执行期间被重启，该任务已中断。\n"
            + "已产生的日志保留在任务目录的 output.log 中，本页面显示的就是它的内容，重启后不会再有新增。\n"
            + "如需完整结果，请重新执行该脚本。";

    /** 任务目录下的实时日志文件名：由 Python 进程直接写入（见 runPythonProcess 的 stdout 重定向）。 */
    private static final String TASK_LOG_FILE = "output.log";

    /**
     * 任务目录下的进程信息文件名（两行：pid、进程启动时刻毫秒）。
     * 用途：JVM 重启后内存里的 Process 对象已丢失，靠它找回子进程以便终止与续监控。
     */
    private static final String TASK_PID_FILE = "task.pid";

    private static final String TASK_EXIT_CODE_FILE = "exit_code.txt";

    /**
     * Multi-agent 续训断点相对「任务目录」的路径（P19-1）。
     *
     * <p>与 {@code Multi-agent.py} 里 {@code CKPT_DIR = 'checkpoints/multi_agent_resume'} 的
     * 默认解析结果一致：脚本被复制到任务目录后执行，其 {@code Path(__file__).parent} 即任务目录，
     * 因此不传 {@code --checkpoint-dir} 时断点天然落在 {@code <任务目录>/checkpoints/multi_agent_resume}。
     *
     * <p>约定：每个 Multi-agent 训练任务都在自己的目录下留一份断点（含
     * {@code train_progress.json}：已训练轮数 / 最差和 / {@code mid_eval_history} 不适曲线），
     * 使「从某个已完成任务续训」成为可能，且源任务快照保持不可变。
     */
    private static final String MARL_CKPT_REL_DIR = "checkpoints/multi_agent_resume";

    private static final String AAC_CKPT_REL_DIR = "checkpoints/aacmadrl";
    private static final String AAC_MODEL_MANIFEST = "model_manifest.json";

    /** 断点进度文件名（与 Multi-agent.py 的 CKPT_PROGRESS 一致）。 */
    private static final String MARL_CKPT_PROGRESS_FILE = "train_progress.json";

    /**
     * 全局兜底断点目录（相对 {@code citylearnpy}）：任务目录里找不到断点时按顺序再找这几个。
     *
     * <p>都是「所有任务共用」的老目录 —— 早期训练脚本不接收 {@code --checkpoint-dir}，
     * 把模型写在了全局目录里（互相覆盖，无法区分是哪一次训练的）：
     * <ul>
     *   <li>{@code checkpoints/multi_agent_sac} —— 2026-10-09 实测 0efa38cb 等「只训练」简易任务写在这里；</li>
     *   <li>{@code checkpoints/multi_agent_resume} —— 脚本 {@code DEFAULT_CHECKPOINT_DIR} 的当前默认值。</li>
     * </ul>
     * 兜底只让历史记录「看得见、可选」，加载到的是该目录里最后写入的那一版模型。
     */
    private static final String[] MARL_GLOBAL_CKPT_REL_DIRS = {
            "checkpoints/multi_agent_sac",
            "checkpoints/multi_agent_resume",
    };

    /** 统一的 Python 任务包装器（位于 citylearnpy 下），负责转发脚本并把退出码落盘。 */
    private static final String TASK_RUNNER_FILE = "_task_runner.py";

    @PostConstruct
    public void init() {
        reconcileInterruptedTasks();
    }

    /**
     * 启动对账：处理数据库中仍标记为「执行中(0)」的任务。
     *
     * <p>背景：任务的实时状态与日志缓冲（CONSOLE_MAP / TASK_OUTPUT_BUFFER /
     * RUNNING_PROCESS）都是 JVM 内存态，后端进程一死就全没了，而 py_task 里的 status
     * 仍是 0。但**子进程不一定跟着死** —— 由于 Python 的 stdout 已由操作系统重定向到
     * 任务目录的 output.log（不走 Java 管道），JVM 被杀并不会让它撞 broken pipe，
     * 它很可能仍在正常跑、仍在写日志。所以不能一律标记为中断，而要按进程是否真的存活来分派：
     *
     * <ul>
     *   <li><b>进程仍存活</b>（task.pid 能找回且校验通过）→ 保持「执行中」，
     *       调用 {@link #reattachRunningTask} 重新挂载监控。前端 checkRunningTask 会再次
     *       命中它，继续轮询 output.log 显示实时日志，「终止运行」按钮也能按 PID 真终止。</li>
     *   <li><b>进程已不在，但留下了"已跑完"的凭据</b>（exit_code.txt，或日志里有 KPI 段）
     *       → 说明它在 JVM 停机期间自己正常结束了，交给 {@link #settleFinishedTask}
     *       按退出码回填「执行完成(1)」或「执行失败(2)」，并把 KPI 入库。</li>
     *   <li><b>进程已不在、也没有任何凭据</b> → 改判为「已中断(4)」并写 error.log 说明，
     *       避免僵尸任务让前端一直显示「执行中」、并让 runPyFile 的
     *       「该文件已有任务执行中」拦截永久堵死该脚本。</li>
     * </ul>
     *
     * <p>放在 @PostConstruct（而非 ApplicationReadyEvent）：它在内嵌 Tomcat 开始接收请求
     * 之前执行，能避免"前端请求先到、对账还没跑"的竞态。本方法失败不抛异常，不影响启动。
     *
     * <p>注：仅适用于单实例部署；若将来多实例共用同一库，需改为按实例标识对账。
     */
    @PostConstruct
    public void reconcileInterruptedTasks() {
        try {
            List<PyTask> stale = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                    .eq(PyTask::getStatus, 0));
            if (stale == null || stale.isEmpty()) {
                return;
            }
            int reattached = 0;
            int recovered = 0;
            int interrupted = 0;
            for (PyTask task : stale) {
                Optional<ProcessHandle> handle = readTaskProcessHandle(task.getId());
                if (handle.isPresent()) {
                    reattachRunningTask(task.getId(), handle.get());
                    reattached++;
                    log.warn("启动对账：任务仍在运行，已重新挂载监控, taskId={}, pid={}",
                            task.getId(), handle.get().pid());
                    continue;
                }
                // 进程已不在 ≠ 一定是被中断：它可能是 JVM 停机期间自己正常跑完的。
                // 先按"已结束"的凭据回填结果，实在没有凭据才判中断（见 settleFinishedTask）。
                if (settleFinishedTask(task)) {
                    recovered++;
                } else {
                    interrupted++;
                }
            }
            log.warn("启动对账完成：执行中任务 {} 个 → 仍在运行 {} 个（已续监控）、"
                            + "停机期间已结束 {} 个（已回填结果）、已中断 {} 个",
                    stale.size(), reattached, recovered, interrupted);
        } catch (Exception e) {
            // 对账失败不能影响服务启动，任务列表退化为旧行为（显示执行中）
            log.error("启动对账「执行中」任务失败，已跳过（不影响服务启动）", e);
        }
    }

    /**
     * 启动对账：任务进程已不在时，先判断它是「JVM 停机期间正常结束了」还是「真被中断」。
     *
     * <p>此前这里是一律标 4-已中断，会漏判一种情况：脚本在 JVM 停机期间自己跑完了
     * （写了 exit_code.txt，或日志里落了 KPI 段），重启后却被说成"已中断"，
     * 一个成功的任务就这么被扔掉了。这里把 {@link #reattachRunningTask} 的判据顺序搬过来：
     *
     * <ol>
     *   <li><b>exit_code.txt</b> 存在 → 退出码 0 判成功、非 0 判失败。
     *       首选判据：由 _task_runner.py 在脚本结束时落盘，语义完整。</li>
     *   <li><b>退回日志启发式</b>：日志含 KPI 段（outputkpi）判成功。
     *       仅用于进程被强杀、包装器来不及写退出码的情况。</li>
     *   <li>两者都没有 → 才判 4-已中断，并写 error.log 说明。</li>
     * </ol>
     *
     * <p>注意：判据 2 只用于「exit_code.txt 缺失」的兜底，不会把一个"正常结束但不打印
     * KPI 段"的脚本误判成失败 —— 那种脚本仍会留下 exit_code.txt，走判据 1。
     *
     * @return true 表示已按「已结束」回填成功 / 失败；false 表示判为已中断
     */
    private boolean settleFinishedTask(PyTask task) {
        String taskId = task.getId();
        String output = readTaskOutputLog(taskId);
        Integer exitCode = readTaskExitCode(taskId);
        if (exitCode != null) {
            if (exitCode == 0) {
                parseAndSaveKpis(output, task.getPyId());
                markPyTaskSuccess(taskId);
                log.warn("启动对账：任务停机期间已正常结束，判定为执行完成（exit_code.txt = 0）, taskId={}",
                        taskId);
            } else {
                markPyTaskFailed(taskId,
                        "后端服务在任务执行期间重启；该任务随后结束，退出码=" + exitCode
                      + "。详情见任务目录下的 output.log。");
                log.warn("启动对账：任务停机期间已结束，判定为执行失败（exit_code.txt = {}）, taskId={}",
                        exitCode, taskId);
            }
            return true;
        }
        if (output != null && output.contains("outputkpi")) {
            // 退回：进程被强杀时包装器来不及写退出码，只能用日志启发式
            parseAndSaveKpis(output, task.getPyId());
            markPyTaskSuccess(taskId);
            log.warn("启动对账：任务停机期间已正常结束，判定为执行完成"
                    + "（无退出码文件，依据日志含 outputkpi 段）, taskId={}", taskId);
            return true;
        }
        PyTask update = new PyTask();
        update.setId(taskId);
        update.setStatus(TASK_STATUS_INTERRUPTED);
        update.setUpdateTime(new Date());
        pyTaskMapper.updateById(update);
        TaskTracer.transition(getTaskDir(taskId), taskId, 0, TASK_STATUS_INTERRUPTED, "reconcile-interrupted");
        saveTaskErrorLog(taskId, INTERRUPTED_TASK_MESSAGE);
        // 子任务被中断（后端重启期间进程已不在）→ 父任务同步为已中断
        onSubTaskFinished(taskId, TASK_STATUS_INTERRUPTED);
        log.warn("启动对账：任务进程已不在，且无退出码文件与 KPI 段，标记为已中断, taskId={}, pyId={}",
                taskId, task.getPyId());
        return false;
    }

    /**
     * 后端重启后，为一个「子进程仍在运行」的任务重新挂载监控。
     *
     * <p>结果判定优先级：
     * <ol>
     *   <li><b>exit_code.txt</b>（由 _task_runner.py 在脚本结束时落盘）→ 退出码 0 判成功、
     *       非 0 判失败。这是首选：重启后拿不到子进程的真实退出码（它已不是本 JVM 的直系子进程）。</li>
     *   <li><b>退回日志启发式</b>：日志里出现 KPI 段（outputkpi）判成功。仅用于进程被强杀、
     *       包装器来不及写退出码的情况。</li>
     * </ol>
     *
     * <p>期间用户可以随时点「终止运行」：stopPyTask 会先写 STOPPED_TASKS 再按 PID 杀进程，
     * 本线程醒来时若发现已被终止或状态已不是 0，就直接退出、不覆盖状态。
     */
    private void reattachRunningTask(String taskId, ProcessHandle handle) {
        Thread watcher = new Thread(() -> {
            try {
                while (handle.isAlive()) {
                    Thread.sleep(3000L);
                }
                if (STOPPED_TASKS.contains(taskId)) {
                    log.info("重挂载任务已被用户终止，交由 stopPyTask 收尾, taskId={}", taskId);
                    return;
                }
                PyTask latest = pyTaskMapper.selectById(taskId);
                if (latest == null || !Integer.valueOf(0).equals(latest.getStatus())) {
                    log.info("重挂载任务状态已被其它流程改写，跳过回填, taskId={}, status={}",
                            taskId, latest == null ? null : latest.getStatus());
                    return;
                }
                String output = readTaskOutputLog(taskId);
                Integer exitCode = readTaskExitCode(taskId);
                if (exitCode != null) {
                    // 首选：包装器落盘的退出码，比"日志里有没有 KPI 段"可靠得多
                    if (exitCode == 0) {
                        parseAndSaveKpis(output, latest.getPyId());
                        markPyTaskSuccess(taskId);
                        log.info("重挂载任务判定为执行完成（exit_code.txt = 0）, taskId={}", taskId);
                    } else {
                        markPyTaskFailed(taskId,
                                "后端服务在任务执行期间重启；该任务随后结束，退出码=" + exitCode
                              + "。详情见任务目录下的 output.log。");
                        log.warn("重挂载任务判定为执行失败（exit_code.txt = {}）, taskId={}", exitCode, taskId);
                    }
                } else if (output != null && output.contains("outputkpi")) {
                    // 退回：进程被强杀时包装器来不及写退出码，只能用日志启发式
                    parseAndSaveKpis(output, latest.getPyId());
                    markPyTaskSuccess(taskId);
                    log.info("重挂载任务判定为执行完成（无退出码文件，依据日志含 outputkpi 段）, taskId={}", taskId);
                } else {
                    markPyTaskFailed(taskId,
                            "后端服务在任务执行期间重启，进程随后结束，且未留下退出码文件（可能被强杀）。"
                          + "请依据任务目录下的 output.log 判断实际结果。");
                    log.warn("重挂载任务已结束，既无退出码文件、日志也无 KPI 段，标记为执行失败, taskId={}", taskId);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                log.error("重挂载任务监控异常, taskId={}", taskId, e);
            }
        }, "py-reattach-" + taskId);
        watcher.setDaemon(true);
        watcher.start();
    }
    /**
     * 原始数据：默认从 CityLearn 2023 local schema CSV 读取并封装为 BuildingDataVO。
     */
    public List<BuildingDataVO> getList(String buildingId, Integer month, Integer hour, Integer dayType,
                                        String datasetSchema, String date) {
        return cityLearnLocalDatasetService.getBuildingRows(
                buildingId, datasetSchema, month, hour, dayType, date);
    }

    public List<BuildingDataVO> getList(String buildingId, Integer month, Integer hour, Integer dayType,
                                        String datasetSchema) {
        return getList(buildingId, month, hour, dayType, datasetSchema, null);
    }

    public List<BuildingDataVO> getList(String buildingId, Integer month, Integer hour, Integer dayType) {
        return getList(buildingId, month, hour, dayType, CityLearnLocalDatasetService.DEFAULT_SCHEMA, null);
    }

    @Value("${citylearn.python.executable:python}")
    private String pythonExecutable;

    @Value("${citylearn.python.aac-executable:}")
    private String aacPythonExecutable;

    private static  final  List<String> LINE_TITLE=new ArrayList<String>(){{
        add("allTimePeakAverage");
        add("annualNormalizedUnservedEnergyTotal");
        add("carbonEmissionsTotal");
        add("costTotal");
        add("dailyOneMinusLoadFactorAverage");
        add("dailyPeakAverage");
        add("discomfortColdDeltaAverage");
        add("discomfortColdDeltaMaximum");
        add("discomfortColdDeltaMinimum");
        add("discomfortColdProportion");
        add("discomfortHotDeltaAverage");
        add("discomfortHotDeltaMaximum");
        add("discomfortHotDeltaMinimum");
        add("discomfortHotProportion");
        add("discomfortProportion");
        add("electricityConsumptionTotal");
        add("monthlyOneMinusLoadFactorAverage");
        add("oneMinusThermalResilienceProportion");
        add("powerOutageNormalizedUnservedEnergyTotal");
        add("rampingAverage");
        add("zeroNetEnergy");
    }} ;

    private static  final  List<String> LINE_TXT_TITLE=new ArrayList<String>(){{
        add("全时段峰值平均值");
        add("年度标准化未满足能源总量");
        add("碳排放总量");
        add("总成本");
        add("日平均(1-负荷率)");
        add("日峰值平均值");
        add("低温不适温差平均值");
        add("低温不适温差最大值");
        add("低温不适温差最小值");
        add("低温不适温差比例");
        add("高温不适温差平均值");
        add("高温不适温差最大值");
        add("高温不适温差最小值");
        add("高温不适温差比例");
        add("不适比例");
        add("电量消耗总量");
        add("月平均(1-负荷率)");
        add("热弹性不足比例");
        add("停电未满足能源总量");
        add("负荷爬坡率");
        // 零净能耗：CityLearn 的 zero_net_energy 是「控制净取电量 ÷ 无控制基准」的归一化比值，
        // 越低越好（不是"达标率"）—— 与前端 kpiLabels.js 的 KPI_HIGHER_IS_BETTER 口径一致。
        add("零净能耗（归一化）");

    }} ;
    public List<KpisTransVO> getKpis(String agentType) {
        List<Kpis> kpisList=kpisMapper.selectList(new QueryWrapper<Kpis>()
                .lambda()
                .eq(Kpis::getAgentType,agentType));

        if(null==kpisList || kpisList.size()==0){
            return new ArrayList<>();
        }

        JSONArray jsonArray=JSON.parseArray(JSON.toJSONString(kpisList));

        List<KpisTransVO> returnList=new ArrayList<>();
        for(int i=0;i<LINE_TITLE.size();i++){
            String title=LINE_TITLE.get(i);
            KpisTransVO kpisTransVO=new KpisTransVO();
            kpisTransVO.setLine1(LINE_TXT_TITLE.get(i));
            kpisTransVO.setLine2(jsonArray.getJSONObject(0).getBigDecimal(title));
            kpisTransVO.setLine3(jsonArray.getJSONObject(1).getBigDecimal(title));
            kpisTransVO.setLine4(jsonArray.getJSONObject(2).getBigDecimal(title));
            kpisTransVO.setLine5(jsonArray.getJSONObject(3).getBigDecimal(title));
            returnList.add(kpisTransVO);
        }

        return returnList;
    }

    /*
     * ============================================================================
     * 2026-10-10：【算法配置 -> 命令行参数】的白名单机制已**整体取消**
     * ============================================================================
     * 原机制
     *   ALGORITHM_CONFIG_CLI_WHITELIST（key = 脚本文件名小写，value = 允许传的选项名集合）
     *   + buildAlgorithmConfigCliWhitelist()。只有登记过的脚本、且登记在名单里的选项，
     *   才允许把「配置」弹窗里的值翻成 `--选项名 值`。初衷是防「配置里残留了脚本 argparse
     *   不认的参数 => unrecognized arguments => 脚本 exit 2」。
     *
     * 现在
     *   **界面配置了什么就传什么**，不再按脚本裁剪。语义简单、可预期：
     *   谁配错，谁就能在 output.log 里看到 argparse 报错（exit 2），自己回去删掉那条配置。
     *   仍会跳过的只剩三类：未命名 / 无值 / 值是不可当 CLI 传的数组或对象（map、multiple）。
     *
     * 守卫改由脚本侧承担
     *   各入口用 argparse.parse_known_args()：不认识的选项打一行日志后忽略，不中断运行
     *   （CHESCA.py、以及 district_marl 的 District_MARL_train.py / District_MARL_eval.py 均已如此）。
     *
     * 注：RESUME_SUPPORTED_SCRIPTS（下方）保留 —— 那是「续训」开关的能力表，
     *     与本次取消的参数白名单不是一回事。
     * ============================================================================
     */

    /**
     * 声明了 {@code --resume}（断点续训）的脚本文件名（小写）。
     *
     * <p><b>当前为空</b>：2026-10-07 核对时，Multi-agent.py / -train.py 都已移除该参数
     * （脚本内注释：SAC 的 import「已随 --resume 撤下而删，模型构建在 utils/train_phase」）。
     * 留空可保证代码编辑器的「续训」开关不会给脚本塞它不认的参数 —— 那会让脚本
     * argparse 直接 "unrecognized arguments: --resume" 退出。开关本身会降级为
     * 「忽略并提示」（见 runPythonTaskAsync 里的 resume 分支）。
     *
     * <p>将来脚本恢复续训能力时，把 {@code multi-agent.py} 等加回本集合即可，
     * 无需改动别处逻辑。
     */
    private static final Set<String> RESUME_SUPPORTED_SCRIPTS = new HashSet<>();

    /**
     * 取本次执行要用的脚本配置 JSON：**优先任务级配置**（{@code py_task.config}，编排任务的
     * 两张卡），没有才回落到脚本文件自己的配置（{@code py_file.algorithm_config}，代码编辑器
     * 里点「执行」的路径）。
     *
     * <p>任务级配置的外层是卡片 JSON（{@link PipelineStepConfig}）—— 里面装着 pyId / 数据集 /
     * 训练轮数 等展示与元信息，真正当命令行参数用的是它内层的 {@code config} 字段
     * （与 py_file.algorithm_config 完全同格式）。
     */
    private String resolveConfigJsonForTask(String taskId, String pyFileId) {
        if (!isBlank(taskId)) {
            PyTask task = pyTaskMapper.selectById(taskId);
            if (task != null && !isBlank(task.getConfig())) {
                PipelineStepConfig step = parsePipelineStepConfig(task.getConfig());
                if (step != null && !isBlank(step.getConfig())) {
                    return step.getConfig();
                }
            }
        }
        PyFile pyFile = isBlank(pyFileId) ? null : pyFileMapper.selectById(pyFileId);
        return pyFile == null ? null : pyFile.getAlgorithmConfig();
    }

    /**
     * 把脚本配置（任务级 py_task.config 内层 config，或脚本文件的 py_file.algorithm_config）
     * 翻译成命令行参数：{@code param_name → --param_name value}。
     *
     * <p>支持两种落库格式（与 {@link AlgorithmConfigJson#normalize(String)} 同口径）：v2 分组
     * {@code [{type,params:[...]}]} 与旧扁平 {@code [{id,param_name,value}]}。参数项既可能是
     * 目录参数（{@code id = algorithm_param_config.id}），也可能是界面上手填的「自定义参数」
     * （{@code id} 是 uuid，只能靠它自己的 param_name 认）。
     *
     * <p>取值语义：目录里 {@code value_type=special} 的参数（当前就是两个数据集）存的是
     * citylearn_dataset.id，这里换成 schema 目录名再传；值不是合法 id（历史数据可能直接存了
     * schema 名）就原样透传。值是数组/对象的（map、multiple 这类）当不了 CLI 值，跳过。
     *
     * <p>2026-10-10 起<b>不再按脚本裁剪</b>：配置里配了什么就翻成什么命令行
     * （原来的「按脚本白名单过滤」机制已取消）。
     * 仍会跳过的只有三类：未命名、无值、值是不可当 CLI 传的数组/对象（map / multiple）。
     *
     * @param pyFileId   脚本 id
     * @param pyFileName 脚本文件名（仅用于日志）
     * @param resume     本次是否续训；为 true 时 checkpoint-dir 由后端钉死（固定断点目录），
     *                   配置里的同名参数忽略，避免续训找不到断点
     * @return flag → value，保持参数项在配置里的顺序；同一参数出现多次以最后一次为准
     */
    private Map<String, String> resolveAlgorithmConfigArgs(String taskId, String pyFileId,
                                                           String pyFileName, boolean resume) {
        Map<String, String> result = new LinkedHashMap<>();
        String configJson = resolveConfigJsonForTask(taskId, pyFileId);
        if (isBlank(configJson)) {
            return result;
        }
        // 2026-10-10：白名单机制已取消 —— 界面配置了什么就传什么（见上方字段注释）。
        JSONArray array;
        try {
            // 用上面 resolveConfigJsonForTask 的结果：**任务级配置优先**（编排任务两张卡），
            // 没有才回落到脚本级（py_file.algorithm_config）。
            // ⚠️ 这里以前误写成 pyFile.getAlgorithmConfig() ⇒ 任务级配置形同虚设，
            //    任务管理页「配置」里改的东西传不进去（2026-10-08 实测踩到）。
            array = JSON.parseArray(configJson.trim());
        } catch (Exception e) {
            log.warn("解析 {} 的算法配置失败，本次按 Java 原参数执行: {}", pyFileName, e.getMessage());
            return result;
        }
        if (array == null) {
            return result;
        }
        // 参数目录：按 id 反查目录里的 param_name 与 value_type
        // （界面上 param_name 允许被改成别名，id 才是稳定键）
        Map<String, AlgorithmParamConfig> catalogById = new HashMap<>();
        for (AlgorithmParamConfig def : algorithmParamConfigMapper.selectList(null)) {
            if (def != null && def.getId() != null) {
                catalogById.put(String.valueOf(def.getId()), def);
            }
        }
        List<String> skipped = new ArrayList<>();
        for (JSONObject param : flattenAlgorithmConfigParams(array)) {
            AlgorithmParamConfig def = catalogById.get(String.valueOf(param.get("id")));
            String flag = (def != null && !isBlank(def.getParamName()))
                    ? def.getParamName().trim()
                    : (param.getString("param_name") == null ? "" : param.getString("param_name").trim());
            if (isBlank(flag)) {
                skipped.add("(未命名)");
                continue;
            }
            String value = resolveAlgorithmConfigValue(def, param.get("value"));
            if (value == null) {
                skipped.add(flag);
                continue;
            }
            result.put("--" + flag, value);
        }
        if (resume && result.containsKey("--checkpoint-dir")) {
            log.warn("本次是续训：checkpoint-dir 由后端指定为固定断点目录，"
                    + "忽略配置里的 {}（否则续训会找不到上一轮断点）", result.get("--checkpoint-dir"));
            result.remove("--checkpoint-dir");
        }
        if (!skipped.isEmpty()) {
            log.info("{} 的算法配置里这些参数不按命令行传入（未命名 / 无值 / 值不可传）: {}",
                    pyFileName, skipped);
        }
        return result;
    }

    /** 把算法配置摊平成参数项列表（v2 分组取各组 params，旧扁平格式顶层就是参数项）。 */
    private static List<JSONObject> flattenAlgorithmConfigParams(JSONArray array) {
        List<JSONObject> items = new ArrayList<>();
        for (int i = 0; i < array.size(); i++) {
            JSONObject item = array.getJSONObject(i);
            if (item == null) {
                continue;
            }
            JSONArray params = item.getJSONArray("params");
            if (params == null) {
                items.add(item);
                continue;
            }
            for (int j = 0; j < params.size(); j++) {
                JSONObject param = params.getJSONObject(j);
                if (param != null) {
                    items.add(param);
                }
            }
        }
        return items;
    }

    /**
     * 解析一个配置参数的取值：数据集参数（目录里 value_type=special）由 id 换成 schema 目录名；
     * 其余原样返回。值为数组/对象、或空值时返回 null（表示这个参数不传）。
     */
    private String resolveAlgorithmConfigValue(AlgorithmParamConfig def, Object rawValue) {
        if (rawValue == null) {
            return null;
        }
        if (rawValue instanceof JSONArray || rawValue instanceof JSONObject) {
            log.warn("参数 {} 的值是数组/对象（map / multiple 之类），无法作为命令行参数传入，已跳过",
                    def == null ? "(自定义)" : def.getParamName());
            return null;
        }
        String text = String.valueOf(rawValue).trim();
        if (text.isEmpty()) {
            return null;
        }
        boolean isDataset = def != null
                && "special".equalsIgnoreCase(def.getValueType() == null ? "" : def.getValueType().trim());
        if (!isDataset) {
            return text;
        }
        Integer datasetId = parseDatasetId(rawValue);
        if (datasetId == null) {
            CitylearnDataset dataset = citylearnDatasetMapper.selectOne(new LambdaQueryWrapper<CitylearnDataset>()
                    .eq(CitylearnDataset::getSchemaKey, text).last("LIMIT 1"));
            if (dataset != null && !Integer.valueOf(1).equals(dataset.getEnabled()))
                throw new IllegalArgumentException("数据集已删除或停用，请重新选择数据集");
            return text;      // 不是 id（历史数据可能直接存了 schema 名）→ 原样透传
        }
        CitylearnDataset dataset = citylearnDatasetMapper.selectById(datasetId);
        if (dataset == null || isBlank(dataset.getSchemaKey())) {
            log.warn("数据集 id={} 在 citylearn_dataset 里查不到，按原值「{}」传给脚本", datasetId, text);
            return text;
        }
        if (!Integer.valueOf(1).equals(dataset.getEnabled()))
            throw new IllegalArgumentException("数据集已删除或停用，请重新选择数据集");
        return dataset.getSchemaKey();
    }

    /**
     * 把配置参数合并进 Java 拼好的参数表：<b>同名以配置为准</b>。
     *
     * <p>用户的预期就是「配置里填了就代替 Java 传的那份」，所以先删掉 Java 传的同名参数
     * （flag + 紧随其后的值），再把配置值追加到末尾 —— 只留一份，避免 argparse 收到重复选项。
     */
    private List<String> applyAlgorithmConfigArgs(List<String> extraArgs, Map<String, String> configArgs) {
        if (configArgs.isEmpty()) {
            return extraArgs;
        }
        List<String> merged = new ArrayList<>(extraArgs);
        for (String flag : configArgs.keySet()) {
            for (int i = 0; i < merged.size(); i++) {
                if (!flag.equals(merged.get(i))) {
                    continue;
                }
                // 紧随其后的不是另一个 --flag，就是本参数的值，一起删
                int removeCount = (i + 1 < merged.size() && !merged.get(i + 1).startsWith("--")) ? 2 : 1;
                for (int k = 0; k < removeCount && i < merged.size(); k++) {
                    merged.remove(i);
                }
                i--;
            }
        }
        for (Map.Entry<String, String> entry : configArgs.entrySet()) {
            merged.add(entry.getKey());
            merged.add(entry.getValue());
        }
        return merged;
    }

    /**
     * 编排任务两张卡片各自对应的「数据集参数」名。
     * 卡片上不再手选数据集，改为读卡片配置里这两个参数的值（= citylearn_dataset.id），
     * 再回填 datasetId / schemaKey / datasetName。
     */
    private static final String PIPELINE_TRAIN_DATASET_PARAM = "train-schema";
    private static final String PIPELINE_EVAL_DATASET_PARAM = "eval-schema";

    /**
     * 执行记录「展示/未展示」：仅执行完成的任务可切换；默认未展示。
     */
    public PyTaskVO updatePyTaskIfShow(String taskId, Boolean ifShow) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("执行记录不存在");
        }
        if (task.getStatus() == null || task.getStatus() != 1) {
            throw new RuntimeException("仅执行完成的记录可设置展示状态");
        }
        PyTask patch = new PyTask();
        patch.setId(taskId);
        patch.setIfShow(Boolean.TRUE.equals(ifShow));
        patch.setUpdateTime(new Date());
        pyTaskMapper.updateById(patch);
        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 执行记录展示名称：有值时仪表盘分组优先显示该名称；留空则回退「代码名+时间」。
     */
    public PyTaskVO updatePyTaskShowName(String taskId, String showName) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("执行记录不存在");
        }
        String normalized = showName == null ? "" : showName.trim();
        if (normalized.length() > 128) {
            throw new RuntimeException("展示名称最多 128 个字符");
        }
        // 允许清空为 null（updateById 默认忽略 null，需用 UpdateWrapper）
        com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<PyTask> uw =
                new com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper<>();
        uw.eq("id", taskId)
                .set("show_name", normalized.isEmpty() ? null : normalized)
                .set("update_time", new Date());
        pyTaskMapper.update(null, uw);
        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 软删除执行记录：if_delete 置为 true，列表不再返回。
     */
    public void deletePyTask(String taskId) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("执行记录不存在");
        }
        /*
         * 等待中的子任务不允许删除：它是「训练+评估」编排任务里排队等训练完成的评估子任务，
         * 训练一结束就会被自动拉起。删掉（软删）会让父任务卡在「没有评估子任务」的状态：
         * 训练完成后 startEvalSubTask 找不到它，只能把父任务标记为失败。
         * 想放弃整个任务，请等它跑完（或先终止正在跑的子任务）。
         */
        if (Integer.valueOf(PyTaskVO.TASK_STATUS_WAITING).equals(task.getStatus())) {
            throw new RuntimeException("该子任务正在等待中（前置任务完成后会自动开始），不可删除");
        }
        PyTask patch = new PyTask();
        patch.setId(taskId);
        patch.setIfDelete(true);
        patch.setIfShow(false);
        patch.setUpdateTime(new Date());
        pyTaskMapper.updateById(patch);

        /*
         * 删的是编排任务的父任务 → 连它的两个子任务一起软删。
         * 否则子任务记录会留在代码编辑器的记录页里（它们有 py_id，会按脚本列出来），
         * 变成一条点不出所以然的「…·训练 / …·评估」记录。
         */
        if (Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(task.getType())
                && !Boolean.TRUE.equals(task.getIsSubtask())) {
            for (String suffix : new String[]{
                    PyTaskVO.SUB_TASK_SUFFIX_TRAIN, PyTaskVO.SUB_TASK_SUFFIX_EVAL}) {
                PyTask sub = pyTaskMapper.selectById(PyTaskVO.subTaskIdOf(taskId, suffix));
                if (sub == null || Boolean.TRUE.equals(sub.getIfDelete())) {
                    continue;
                }
                PyTask subPatch = new PyTask();
                subPatch.setId(sub.getId());
                subPatch.setIfDelete(true);
                subPatch.setIfShow(false);
                subPatch.setUpdateTime(new Date());
                pyTaskMapper.updateById(subPatch);
                log.info("删除编排任务 {} 时一并软删其子任务 {}", taskId, sub.getId());
            }
        }
    }

    /**
     * 过滤掉「父任务已删除 / 不存在」的孤儿子任务。
     *
     * <p>子任务记录会按脚本出现在代码编辑器的记录列表里（带「子任务」标识），
     * 但父任务一旦删除就该一并不再展示 —— 否则记录页会留着一条没有归属的
     * 「…·训练 / …·评估」记录（历史数据里就有这种：父任务已删、子任务还在）。
     */
    private List<PyTask> filterOrphanSubTasks(List<PyTask> tasks) {
        if (tasks == null || tasks.isEmpty()) {
            return tasks;
        }
        Set<String> parentIds = new HashSet<>();
        for (PyTask t : tasks) {
            if (Boolean.TRUE.equals(t.getIsSubtask())) {
                String pid = PyTaskVO.parentTaskIdOf(t.getId());
                if (pid != null) {
                    parentIds.add(pid);
                }
            }
        }
        if (parentIds.isEmpty()) {
            return tasks;
        }
        Map<String, PyTask> parents = new HashMap<>();
        for (PyTask p : pyTaskMapper.selectBatchIds(parentIds)) {
            parents.put(p.getId(), p);
        }
        List<PyTask> result = new ArrayList<>();
        for (PyTask t : tasks) {
            if (Boolean.TRUE.equals(t.getIsSubtask())) {
                String pid = PyTaskVO.parentTaskIdOf(t.getId());
                PyTask parent = pid == null ? null : parents.get(pid);
                if (parent == null || Boolean.TRUE.equals(parent.getIfDelete())) {
                    continue;      // 孤儿子任务：不展示
                }
            }
            result.add(t);
        }
        return result;
    }

    /**
     * 仿真仪表盘：列出状态为「展示」且执行成功的代码记录；
     * 分组名优先用自定义展示名称，否则为「代码名+记录时间」。
     */
    public List<DashboardSimulationVO> getDashboardSimulations() {
        return getDashboardSimulations(true);
    }

    public List<DashboardSimulationVO> getDashboardSimulations(boolean shownOnly) {
        List<PyTask> showTasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(shownOnly, PyTask::getIfShow, true)
                .eq(PyTask::getStatus, 1)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime));
        List<DashboardSimulationVO> result = new ArrayList<>();
        if (showTasks == null || showTasks.isEmpty()) {
            return result;
        }
        Map<String, Integer> nameCount = new HashMap<>();
        Map<String, String> datasetNames = new HashMap<>();
        if (citylearnDatasetMapper != null) for (CitylearnDataset dataset : citylearnDatasetMapper.selectList(null)) {
            datasetNames.put(String.valueOf(dataset.getId()), dataset.getDisplayName());
            datasetNames.put(dataset.getSchemaKey(), dataset.getDisplayName());
        }
        for (PyTask task : showTasks) {
            PyFile pyFile = pyFileMapper.selectById(task.getPyId());
            if (pyFile == null) {
                continue;
            }
            if (!shownOnly && "train".equals(pyFile.getScriptType())) {
                continue;
            }
            String groupName = buildDashboardGroupName(pyFile, task);
            Integer n = nameCount.getOrDefault(groupName, 0);
            nameCount.put(groupName, n + 1);
            if (n > 0) {
                // 同名冲突时附加时间，保证仪表盘分组 key 唯一
                String timeSuffix = task.getCreateTime() == null
                        ? task.getId()
                        : new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(task.getCreateTime());
                groupName = groupName + " · " + timeSuffix;
            }
            DashboardSimulationVO vo = new DashboardSimulationVO();
            vo.setGroupName(groupName);
            vo.setRecordName(TaskNaming.groupName(pyFile.getFileName(), null));
            if (task.getShowName() != null && !task.getShowName().trim().isEmpty()) {
                vo.setRecordName(task.getShowName().trim());
            }
            vo.setPyId(pyFile.getId());
            vo.setTaskId(task.getId());
            vo.setFileName(pyFile.getFileName());
            vo.setTaskCreateTime(task.getCreateTime());
            try {
                Path taskDir = getTaskDir(task.getId());
                vo.setEvaluationDataset(dashboardEvaluationDataset(task, taskDir, resolveSimulationDataRoot(taskDir), datasetNames));
                Map<String, String> summary = new HashMap<>();
                for (Map<String, String> row : parseKpisCsvToRows(
                        readExportedKpisCsv(taskDir, resolveSimulationDataRoot(taskDir)))) {
                    String metric = row.getOrDefault("KPI", row.get("cost_function"));
                    if (metric != null) summary.put(metric, row.get("District"));
                }
                com.citylearn.common.DashboardKpiSummary.apply(vo, summary);
            } catch (IOException error) {
                log.warn("Unable to read dashboard KPI summary for task {}", task.getId(), error);
            }
            result.add(vo);
        }
        result.sort(Comparator.comparing(DashboardSimulationVO::getGroupName,
                Comparator.nullsLast(String::compareToIgnoreCase)));
        return result;
    }

    private String dashboardEvaluationDataset(PyTask task, Path taskDir, Path dataRoot, Map<String,String> names) {
        for (String filename : List.of("evaluation_manifest.json", "agent_config.json", "chesca_agent_config.json", "aacmadrl_config.json")) {
            for (Path directory : new LinkedHashSet<>(List.of(dataRoot, taskDir))) {
                Path path = directory.resolve(filename);
                try {
                    if (!Files.isRegularFile(path) || Files.size(path) > 1_000_000) continue;
                    JSONObject config = JSON.parseObject(Files.readString(path, StandardCharsets.UTF_8));
                    JSONObject resolved = config.getJSONObject("resolved_parameters");
                    String value = dashboardSchemaValue(resolved == null ? config : resolved);
                    if (!isBlank(value)) return names.getOrDefault(dashboardDatasetKey(value), dashboardDatasetKey(value));
                } catch (IOException | RuntimeException error) {
                    log.debug("Unable to read evaluation dataset from {}", path, error);
                }
            }
        }
        try {
            if (isBlank(task.getConfig())) return null;
            JSONObject step = JSON.parseObject(task.getConfig());
            if (!isBlank(step.getString("config"))) {
                List<JSONObject> params = flattenAlgorithmConfigParams(JSON.parseArray(step.getString("config")));
                for (String key : List.of("eval-schema", "schema")) for (JSONObject param : params) {
                    String name = Objects.toString(param.get("param_name"), "").replace('_', '-').replaceFirst("^--", "");
                    if (key.equals(name) && !isBlank(param.getString("value"))) {
                        String value = dashboardDatasetKey(param.getString("value"));
                        return names.getOrDefault(value, value);
                    }
                }
            }
            String value = step.getString("schemaKey");
            if (isBlank(value) && step.get("datasetId") != null) value = step.getString("datasetId");
            if (!isBlank(value)) return names.getOrDefault(dashboardDatasetKey(value),
                    isBlank(step.getString("datasetName")) ? dashboardDatasetKey(value) : step.getString("datasetName"));
        } catch (RuntimeException error) { log.debug("Unable to read dataset from task {}", task.getId(), error); }
        return null;
    }

    private static String dashboardSchemaValue(JSONObject config) {
        for (String name : List.of("eval_schema", "eval-schema", "schema", "schema_path")) {
            Object value = config.get(name);
            if (value instanceof String && !((String)value).isBlank()) return (String)value;
        }
        return null;
    }

    static String dashboardDatasetKey(String value) {
        String path = value.trim().replace('\\', '/').replaceAll("/+$", "");
        if (path.endsWith("/schema.json")) path = path.substring(0, path.length() - 12);
        return path.substring(path.lastIndexOf('/') + 1);
    }

    /**
     * 仿真仪表盘：加载指定成功任务目录下的 KPI 与 exported_data CSV。
     */
    public DashboardSimulationDetailVO getDashboardSimulationDetail(String taskId) throws IOException {
        return getDashboardSimulationDetail(taskId, false);
    }

    public DashboardSimulationDetailVO getDashboardSimulationDetail(String taskId, boolean pagedTrace) throws IOException {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())
                || task.getStatus() == null || task.getStatus() != 1) {
            throw new IllegalArgumentException("任务不存在、已删除或未执行成功");
        }
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            throw new RuntimeException("关联 Python 文件不存在");
        }
        Path taskDir = getTaskDir(taskId);
        Path dataRoot = resolveSimulationDataRoot(taskDir);

        DashboardSimulationDetailVO vo = new DashboardSimulationDetailVO();
        vo.setGroupName(buildDashboardGroupName(pyFile, task));
        vo.setPyId(pyFile.getId());
        vo.setTaskId(taskId);
        vo.setEvaluationAnalysis(new EvaluationAnalysisService().read(taskDir, taskId));
        String datasetKey = dashboardEvaluationDataset(task, taskDir, dataRoot, Collections.emptyMap());
        if (!isBlank(datasetKey)) vo.setCurrency(citylearnDatasetService.resolveCurrency(datasetKey));

        String kpisCsv = readExportedKpisCsv(taskDir, dataRoot);
        // Script-level KPI rows cannot prove which evaluation produced them.
        // Keep missing historical artifacts explicit instead of mixing runs.
        String normalizedKpisCsv = stripUtf8Bom(kpisCsv == null ? "" : kpisCsv);
        vo.setKpisCsv(normalizedKpisCsv);
        List<Map<String, String>> kpiRows = parseKpisCsvToRows(normalizedKpisCsv);
        if (kpiRows.isEmpty()) {
            vo.getArtifactWarnings().add("该评估记录没有可读取的任务级 KPI 文件，请重新评估；脚本级历史指标不能证明属于本次任务。");
        }
        vo.setKpiRows(kpiRows);

        Map<String, String> dataFiles = new LinkedHashMap<>();
        collectExportedDataCsv(dataRoot, dataFiles);
        if (dataFiles.isEmpty() && !dataRoot.equals(taskDir)) {
            collectExportedDataCsv(taskDir, dataFiles);
        }
        vo.setDataFiles(dataFiles);

        Map<String, Object> trace = pagedTrace ? getDashboardTracePage(taskId, 0,
                DecisionTracePageService.DEFAULT_LIMIT, null) : null;
        String chescaTraceCsv = pagedTrace ? (String) trace.get("chescaTraceCsv") : readChescaTraceCsv(taskDir, dataRoot);
        vo.setChescaTraceCsv(stripUtf8Bom(chescaTraceCsv == null ? "" : chescaTraceCsv));
        String decisionTraceJson = pagedTrace ? (String) trace.get("decisionTraceJson") : readDecisionTraceJson(taskDir, dataRoot);
        vo.setDecisionTraceJson(stripUtf8Bom(decisionTraceJson == null ? "" : decisionTraceJson));
        if (pagedTrace) vo.setTracePage((Map<String, Object>) trace.get("tracePage"));

        String agentConfigJson = readAgentConfigJson(taskDir, dataRoot);
        vo.setAgentConfigJson(stripUtf8Bom(agentConfigJson == null ? "" : agentConfigJson));
        vo.setResmarlSummary(buildResmarlSummary(agentConfigJson));
        if(dataFiles.isEmpty())vo.getArtifactWarnings().add("该历史记录未找到任务时序文件，请重新评估生成曲线。");
        if((decisionTraceJson==null||decisionTraceJson.isBlank())&&(chescaTraceCsv==null||chescaTraceCsv.isBlank()))vo.getArtifactWarnings().add("该历史记录没有保存决策推演日志，请重新评估；KPI 不能还原逐步决策。");
        return vo;
    }

    public Map<String, Object> getDashboardTracePage(String taskId, int offset,
                                                    int limit, Integer building) throws IOException {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())
                || !Integer.valueOf(1).equals(task.getStatus()))
            throw new IllegalArgumentException("任务不存在、已删除或未执行成功");
        Path root = getTaskDir(taskId);
        Path data = resolveSimulationDataRoot(root);
        return new DecisionTracePageService().read(root, findDecisionTraceJson(root, data),
                findChescaTraceCsv(root, data), offset, limit, building);
    }

    private PyTask findLatestSuccessTaskByPyId(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getStatus, 1)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime)
                .last("LIMIT 1"));
        if (tasks == null || tasks.isEmpty()) {
            return null;
        }
        return tasks.get(0);
    }

    private String stripPyExtension(String fileName) {
        return TaskNaming.stripPyExtension(fileName);
    }

    /** 仪表盘分组名：有展示名称用展示名称，否则代码名 + 记录创建时间 */
    private String buildDashboardGroupName(PyFile pyFile, PyTask task) {
        return TaskNaming.groupName(pyFile, task);
    }

    /** 仪表盘分组名回退：代码名 + 记录创建时间 */
    private String buildDashboardGroupName(String fileName, Date taskCreateTime) {
        return TaskNaming.groupName(fileName, taskCreateTime);
    }

    private Path resolveSimulationDataRoot(Path taskDir) throws IOException {
        return SimulationDataPaths.resolve(taskDir);
    }

    private boolean hasExportedDataCsv(Path dir) throws IOException {
        return SimulationDataPaths.hasExportedDataCsv(dir);
    }

    private Path findExportedKpisCsv(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("exported_kpis.csv");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("exported_kpis.csv");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "exported_kpis.csv".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readExportedKpisCsv(Path taskDir, Path dataRoot) throws IOException {
        Path kpiPath = findExportedKpisCsv(taskDir, dataRoot);
        if (kpiPath == null || !Files.exists(kpiPath)) {
            return "";
        }
        return new String(Files.readAllBytes(kpiPath), StandardCharsets.UTF_8);
    }

    private Path findChescaTraceCsv(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("chesca_trace.csv");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("chesca_trace.csv");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "chesca_trace.csv".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readChescaTraceCsv(Path taskDir, Path dataRoot) throws IOException {
        Path tracePath = findChescaTraceCsv(taskDir, dataRoot);
        if (tracePath == null || !Files.exists(tracePath)) {
            return "";
        }
        return new String(Files.readAllBytes(tracePath), StandardCharsets.UTF_8);
    }

    private Path findDecisionTraceJson(Path taskDir, Path dataRoot) throws IOException {
        Path inRoot = dataRoot.resolve("decision_trace.json");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("decision_trace.json");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "decision_trace.json".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readDecisionTraceJson(Path taskDir, Path dataRoot) throws IOException {
        Path jsonPath = findDecisionTraceJson(taskDir, dataRoot);
        if (jsonPath == null || !Files.exists(jsonPath)) {
            return "";
        }
        return new String(Files.readAllBytes(jsonPath), StandardCharsets.UTF_8);
    }

    private Path findAgentConfigJson(Path taskDir, Path dataRoot) throws IOException {
        Path genericInRoot = dataRoot.resolve("agent_config.json");
        if (Files.exists(genericInRoot)) {
            return genericInRoot;
        }
        Path genericInTask = taskDir.resolve("agent_config.json");
        if (Files.exists(genericInTask)) {
            return genericInTask;
        }
        Path inRoot = dataRoot.resolve("chesca_agent_config.json");
        if (Files.exists(inRoot)) {
            return inRoot;
        }
        Path inTask = taskDir.resolve("chesca_agent_config.json");
        if (Files.exists(inTask)) {
            return inTask;
        }
        if (!Files.exists(taskDir)) {
            return null;
        }
        try (Stream<Path> walk = Files.walk(taskDir, 2)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> "agent_config.json".equals(p.getFileName().toString())
                            || "chesca_agent_config.json".equals(p.getFileName().toString()))
                    .findFirst()
                    .orElse(null);
        }
    }

    private String readAgentConfigJson(Path taskDir, Path dataRoot) throws IOException {
        Path path = findAgentConfigJson(taskDir, dataRoot);
        if (path == null || !Files.exists(path)) {
            return "";
        }
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> buildResmarlSummary(String agentConfigJson) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("enabled", false);
        summary.put("marlMode", "none");
        summary.put("alpha", 0.0);
        summary.put("label", "");
        if (agentConfigJson == null || agentConfigJson.trim().isEmpty()) {
            return summary;
        }
        try {
            Map<String, Object> cfg = JSON.parseObject(agentConfigJson, Map.class);
            if (cfg == null) {
                return summary;
            }
            Object enabledObj = cfg.get("resmarl_enabled");
            boolean enabled = enabledObj != null && (
                    Boolean.TRUE.equals(enabledObj)
                            || "true".equalsIgnoreCase(String.valueOf(enabledObj))
                            || "1".equals(String.valueOf(enabledObj))
            );
            String marlMode = "none";
            Object modeObj = cfg.get("marl_mode");
            if (modeObj != null && !String.valueOf(modeObj).trim().isEmpty()) {
                marlMode = String.valueOf(modeObj).trim().toLowerCase();
                if ("central_residual".equals(marlMode)) {
                    marlMode = "multi_agent";
                }
            } else if (enabled) {
                marlMode = "multi_agent";
            }
            double alpha = 0.0;
            Object alphaObj = cfg.get("residual_alpha");
            if (alphaObj instanceof Number) {
                alpha = ((Number) alphaObj).doubleValue();
            } else if (alphaObj != null) {
                try {
                    alpha = Double.parseDouble(String.valueOf(alphaObj));
                } catch (NumberFormatException ignored) {
                    alpha = 0.0;
                }
            }
            summary.put("enabled", enabled);
            summary.put("marlMode", marlMode);
            summary.put("alpha", alpha);
            if (!enabled || "none".equals(marlMode)) {
                summary.put("label", "");
            } else if (alpha <= 0) {
                summary.put("label", "CHESCA-ResMARL α=0");
            } else {
                Object ckpt = cfg.get("multi_agent_checkpoint");
                String ckptTxt = ckpt != null ? String.valueOf(ckpt).trim() : "";
                if (!ckptTxt.isEmpty()) {
                    summary.put("label", String.format("CHESCA-ResMARL α=%.2f(预存模型)", alpha));
                } else {
                    summary.put("label", String.format("CHESCA-ResMARL α=%.2f(缺 checkpoint)", alpha));
                }
            }
        } catch (Exception e) {
            // keep defaults
        }
        return summary;
    }

    private static String stripUtf8Bom(String text) {
        if (text == null || text.isEmpty()) {
            return "";
        }
        if (text.charAt(0) == '\ufeff') {
            return text.substring(1);
        }
        return text;
    }

    /**
     * 将 exported_kpis.csv 解析为表格行（保留空单元格为 ""）。
     */
    private List<Map<String, String>> parseKpisCsvToRows(String csv) {
        List<Map<String, String>> rows = new ArrayList<>();
        if (csv == null || csv.trim().isEmpty()) {
            return rows;
        }
        String[] lines = csv.trim().split("\\r?\\n");
        if (lines.length < 2) {
            return rows;
        }
        String[] headers = lines[0].split(",", -1);
        for (int i = 0; i < headers.length; i++) {
            headers[i] = headers[i].trim().replace("\ufeff", "");
        }
        if (headers.length == 0) {
            return rows;
        }
        String kpiKey = headers[0];
        for (int lineIdx = 1; lineIdx < lines.length; lineIdx++) {
            String line = lines[lineIdx].trim();
            if (line.isEmpty()) {
                continue;
            }
            String[] fields = line.split(",", -1);
            if (fields.length == 0) {
                continue;
            }
            String kpiName = fields[0].trim();
            if (kpiName.isEmpty()) {
                continue;
            }
            Map<String, String> row = new LinkedHashMap<>();
            row.put(kpiKey, kpiName);
            for (int col = 1; col < headers.length; col++) {
                String value = col < fields.length ? fields[col].trim() : "";
                row.put(headers[col], value);
            }
            rows.add(row);
        }
        return rows;
    }

    public List<Map<String, String>> getPyFileKpiRows(String pyId) {
        return buildKpiRowsFromDb(pyId);
    }

    /**
     * 从 kpis 表（agentType=pyId）构建 KPI 表格行，固定 21 项指标。
     */
    private List<Map<String, String>> buildKpiRowsFromDb(String pyId) {
        List<Kpis> kpisList = kpisMapper.selectList(new QueryWrapper<Kpis>().lambda()
                .eq(Kpis::getAgentType, pyId));
        if (kpisList == null || kpisList.isEmpty()) {
            return new ArrayList<>();
        }
        JSONArray arr = JSON.parseArray(JSON.toJSONString(kpisList));
        String[] buildingNames = {"Building_1", "Building_2", "Building_3", "District"};
        JSONObject[] byBuilding = new JSONObject[4];
        for (int i = 0; i < arr.size(); i++) {
            JSONObject row = arr.getJSONObject(i);
            String name = row.getString("name");
            for (int j = 0; j < buildingNames.length; j++) {
                if (buildingNames[j].equals(name)) {
                    byBuilding[j] = row;
                }
            }
        }
        List<Map<String, String>> rows = new ArrayList<>();
        for (int i = 0; i < LINE_TITLE.size(); i++) {
            String field = LINE_TITLE.get(i);
            String snake = camelToSnake(field);
            Map<String, String> row = new LinkedHashMap<>();
            row.put("KPI", snake);
            for (int j = 0; j < buildingNames.length; j++) {
                String value = "";
                if (byBuilding[j] != null) {
                    BigDecimal v = byBuilding[j].getBigDecimal(field);
                    if (v != null) {
                        value = v.stripTrailingZeros().toPlainString();
                    }
                }
                row.put(buildingNames[j], value);
            }
            rows.add(row);
        }
        return rows;
    }

    /**
     * 任务目录无 exported_kpis.csv 时，从 kpis 表按 agentType=pyId 还原 CSV。
     */
    private String buildKpisCsvFromDb(String pyId) {
        List<Kpis> kpisList = kpisMapper.selectList(new QueryWrapper<Kpis>().lambda()
                .eq(Kpis::getAgentType, pyId));
        if (kpisList == null || kpisList.isEmpty()) {
            return "";
        }
        JSONArray arr = JSON.parseArray(JSON.toJSONString(kpisList));
        String[] buildingNames = {"Building_1", "Building_2", "Building_3", "District"};
        JSONObject[] byBuilding = new JSONObject[4];
        for (int i = 0; i < arr.size(); i++) {
            JSONObject row = arr.getJSONObject(i);
            String name = row.getString("name");
            for (int j = 0; j < buildingNames.length; j++) {
                if (buildingNames[j].equals(name)) {
                    byBuilding[j] = row;
                }
            }
        }
        StringBuilder sb = new StringBuilder("KPI,Building_1,Building_2,Building_3,District\n");
        for (int i = 0; i < LINE_TITLE.size(); i++) {
            String field = LINE_TITLE.get(i);
            String snake = camelToSnake(field);
            sb.append(snake);
            for (JSONObject building : byBuilding) {
                sb.append(",");
                if (building == null) {
                    continue;
                }
                BigDecimal value = building.getBigDecimal(field);
                if (value != null) {
                    sb.append(value.stripTrailingZeros().toPlainString());
                }
            }
            sb.append("\n");
        }
        return sb.toString();
    }

    private static String camelToSnake(String camel) {
        if (camel == null || camel.isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < camel.length(); i++) {
            char c = camel.charAt(i);
            if (Character.isUpperCase(c) && i > 0) {
                sb.append('_');
            }
            sb.append(Character.toLowerCase(c));
        }
        return sb.toString();
    }

    private void collectExportedDataCsv(Path dir, Map<String, String> dataFiles) throws IOException {
        if (!Files.isDirectory(dir)) {
            return;
        }
        try (Stream<Path> stream = Files.list(dir)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return name.startsWith("exported_data_") && name.endsWith(".csv");
                    })
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .forEach(p -> {
                        try {
                            dataFiles.put(p.getFileName().toString(),
                                    new String(Files.readAllBytes(p), StandardCharsets.UTF_8));
                        } catch (IOException e) {
                            log.warn("读取仿真数据文件失败: {}", p, e);
                        }
                    });
        }
    }

    /**
     * 异步启动 Python 脚本：创建 pyTask 后立即返回，结果通过 getPyTaskResult 查询。
     */
    public PyTaskVO runPyFile(PyFileParam pyFileParam) {
        PyFile pyFile = pyFileMapper.selectById(pyFileParam.getId());
        if (pyFile == null) {
            throw new RuntimeException("Python 文件不存在");
        }
        if (getRunningPyTask(pyFile.getId()) != null) {
            throw new RuntimeException("该 Python 文件已有任务正在执行中");
        }

        Path scriptPath = Paths.get(fileResourceProperties.getPythonFilePath(), pyFile.getFileName()).normalize();

        String taskId = Ids.uuid();

        insertPyTask(taskId, pyFile.getId());
        CONSOLE_MAP.put(taskId, Collections.synchronizedList(new ArrayList<>()));
        CONSOLE_INDEX_MAP.put(taskId, 0);
        TASK_OUTPUT_BUFFER.put(taskId, new StringBuilder());

        final String scriptToRun;
        final String taskOutputDir;
        try {
            scriptToRun = copyPythonScriptForTask(scriptPath.toString(), taskId);
            taskOutputDir = getTaskDir(taskId).toAbsolutePath().toString();
        } catch (IOException e) {
            markPyTaskFailed(taskId, "复制 Python 脚本失败: " + e.getMessage());
            throw new RuntimeException("复制 Python 脚本到任务目录失败", e);
        }

        final String pyFileId = pyFile.getId();
        final String pyFileName = pyFile.getFileName();
        // 「续训」开关（代码编辑器工具栏）：为 true 时给支持的脚本追加 --resume
        final boolean resume = Boolean.TRUE.equals(pyFileParam.getResume());
        // 续训来源任务（P19-1）：非空 = 从该已完成任务复制断点后再续训
        final String resumeFromTaskId = pyFileParam.getResumeFromTaskId();
        // P19-1 前置校验：指定了来源任务就必须有可用断点。放在提交异步任务之前，
        // 让前端能立即收到明确错误（异步失败只能靠轮询任务状态发现，体验差）。
        if (resume && resumeFromTaskId != null && !resumeFromTaskId.trim().isEmpty()
                && "Multi-agent.py".equalsIgnoreCase(pyFileName)) {
            Path srcProgress = getTaskDir(resumeFromTaskId.trim())
                    .resolve(MARL_CKPT_REL_DIR).resolve(MARL_CKPT_PROGRESS_FILE);
            if (!Files.isRegularFile(srcProgress)) {
                String msg = "所选任务没有可续训的断点（缺 " + MARL_CKPT_PROGRESS_FILE
                        + "）: " + resumeFromTaskId.trim();
                markPyTaskFailed(taskId, msg);
                throw new RuntimeException(msg);
            }
        }
        pythonTaskExecutor.execute(() -> runPythonTaskAsync(scriptToRun, taskId, pyFileId, taskOutputDir, pyFileName, resume, resumeFromTaskId));

        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /**
     * 查询异步任务状态与结果（执行中可轮询；完成后含 KPI 与完整输出）。
     */
    public PyTaskVO getPyTaskResult(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        String output = getLiveTaskOutput(taskId);
        if (output == null) {
            output = "";
        }
        String errorMessage = readTaskErrorLog(taskId);
        List<KpisTransVO> kpis = null;
        if (Integer.valueOf(1).equals(task.getStatus())) {
            kpis = getKpis(task.getPyId());
        }
        return buildPyTaskVO(task, output, errorMessage, kpis);
    }

    /**
     * 查询指定 Python 文件的全部任务记录，按创建时间倒序。
     */
    public List<PyTaskVO> getPyTaskList(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime));
        if (tasks == null || tasks.isEmpty()) {
            return new ArrayList<>();
        }
        // 父任务已删除的孤儿子任务不展示
        tasks = filterOrphanSubTasks(tasks);
        List<PyTaskVO> result = new ArrayList<>();
        for (PyTask task : tasks) {
            result.add(buildPyTaskVO(task, null, null));
        }
        return result;
    }

    /**
     * 查询**所有** Python 文件的执行记录，按创建时间倒序（供「任务记录」菜单使用）。
     *
     * <p>与 getPyTaskList 的区别：不限 pyId，且额外补齐 script_name（前端要显示代码名称）。
     */
    public List<PyTaskVO> getAllPyTaskList() {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime));
        List<PyTaskVO> result = toPyTaskVOsWithScriptName(tasks);
        // 编排任务补一个「复用了哪个历史训练任务」（任务管理页的执行确认文案与详情展示要用）。
        // 同一批 tasks 里就有 `<父id>-eval` 子任务行 ⇒ 不必再查库
        if (tasks != null && !tasks.isEmpty()) {
            Map<String, PyTask> byId = new HashMap<>();
            for (PyTask t : tasks) {
                byId.put(t.getId(), t);
            }
            for (PyTaskVO vo : result) {
                if (!Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(vo.getType())) {
                    continue;
                }
                PyTask evalSub = byId.get(PyTaskVO.subTaskIdOf(vo.getTaskId(), PyTaskVO.SUB_TASK_SUFFIX_EVAL));
                String value = evalSub == null ? null : trainModelValueOfJson(evalSub.getConfig());
                if (isReuseTrainModelValue(value, vo.getTaskId())) {
                    vo.setReuseTrainTaskId(value);
                }
            }
        }
        return result;
    }

    /**
     * 查询当前**正在执行**（status=0）的任务，供前端「运行中任务」指示器高频轮询。
     *
     * <p>不限文件、不限用户在哪个页面 —— 这样任何界面都能实时看到有哪些任务在跑、
     * 以及在它们结束时收到提示。返回体只含轻量字段（不含 output），所以可以每几秒调一次。
     */
    public List<PyTaskVO> getRunningPyTaskList() {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfDelete, false)
                .eq(PyTask::getStatus, 0)
                .orderByDesc(PyTask::getCreateTime));
        return toPyTaskVOsWithScriptName(tasks);
    }

    /**
     * 任务实体 → VO，并批量补齐 scriptName。
     * 文件名一次性查出来，避免逐条查库（N+1）；脚本已删除时保持 null。
     */
    private List<PyTaskVO> toPyTaskVOsWithScriptName(List<PyTask> tasks) {
        if (tasks == null || tasks.isEmpty()) {
            return new ArrayList<>();
        }
        // 父任务已删除的孤儿子任务不展示（记录页/任务记录菜单都会用到本方法）
        tasks = filterOrphanSubTasks(tasks);
        Set<String> pyIds = new HashSet<>();
        for (PyTask task : tasks) {
            if (task.getPyId() != null && !task.getPyId().isEmpty()) {
                pyIds.add(task.getPyId());
            }
        }
        Map<String, String> fileNameById = new HashMap<>();
        if (!pyIds.isEmpty()) {
            List<PyFile> files = pyFileMapper.selectBatchIds(pyIds);
            if (files != null) {
                for (PyFile file : files) {
                    fileNameById.put(file.getId(), file.getFileName());
                }
            }
        }
        List<PyTaskVO> result = new ArrayList<>();
        for (PyTask task : tasks) {
            PyTaskVO vo = buildPyTaskVO(task, null, null);
            vo.setScriptName(fileNameById.get(task.getPyId()));
            result.add(vo);
        }
        return result;
    }

    /**
     * 读取任务输出目录中复制的 Python 脚本内容。
     */
    public PyTaskScriptVO getPyTaskScript(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            throw new RuntimeException("关联 Python 文件不存在");
        }
        Path taskDir = getTaskDir(taskId);
        Path scriptPath = null;
        if (Files.exists(taskDir)) {
            scriptPath = taskDir.resolve(pyFile.getFileName());
            if (!Files.exists(scriptPath)) {
                try (Stream<Path> paths = Files.list(taskDir)) {
                    scriptPath = paths
                            .filter(p -> Files.isRegularFile(p) && p.getFileName().toString().endsWith(".py"))
                            .findFirst()
                            .orElse(null);
                } catch (IOException e) {
                    throw new RuntimeException("读取任务目录失败", e);
                }
            }
        } else {
            /*
             * 任务目录还没建 —— 说明这个任务还没真正跑起来（编排任务里 5-待执行 / 6-等待中的
             * 子任务，目录是启动那一刻才创建的）。这时回落到脚本文件本身：点开这条记录能看到
             * 将要执行的脚本（内容与启动时复制的那份完全一致），而不是弹「任务输出目录不存在」。
             */
            log.info("任务目录尚未创建（任务还没开始执行），改用脚本文件本身: taskId={}, dir={}",
                    taskId, taskDir);
        }
        if (scriptPath == null || !Files.exists(scriptPath)) {
            Path origin = Paths.get(fileResourceProperties.getPythonFilePath(), pyFile.getFileName())
                    .normalize();
            if (!Files.isRegularFile(origin)) {
                throw new RuntimeException("任务目录中未找到 Python 脚本，脚本文件也不存在: " + origin);
            }
            scriptPath = origin;
        }
        try {
            PyTaskScriptVO vo = new PyTaskScriptVO();
            vo.setTaskId(taskId);
            vo.setFileName(scriptPath.getFileName().toString());
            vo.setCode(new String(Files.readAllBytes(scriptPath), StandardCharsets.UTF_8));
            return vo;
        } catch (IOException e) {
            throw new RuntimeException("读取任务 Python 脚本失败", e);
        }
    }

    /**
     * 查询指定 Python 文件当前是否有执行中的任务（status=0）。
     */
    public PyTaskVO getRunningPyTask(String pyId) {
        List<PyTask> tasks = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getPyId, pyId)
                .eq(PyTask::getStatus, 0)
                .eq(PyTask::getIfDelete, false)
                .orderByDesc(PyTask::getCreateTime)
                .last("LIMIT 1"));
        if (tasks == null || tasks.isEmpty()) {
            return null;
        }
        return buildPyTaskVO(tasks.get(0), null, null);
    }

    private void insertPyTask(String taskId, String pyId) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setPyId(pyId);
        task.setStatus(0);
        task.setIfDelete(false);
        task.setIfShow(false);
        // 新任务一律「未提醒/未读」：执行结束后要在顶栏与对应文件上计数，
        // 直到用户在执行记录里点开它才会置为已读
        task.setIfNotified(false);
        task.setCreateTime(new Date());
        pyTaskMapper.insert(task);
        TaskTracer.born(getTaskDir(taskId), taskId, pyId, "editor");
    }

    /**
     * 新建「训练 + 评估」编排任务（py_task.type = 0）。
     *
     * <p><b>只落库、不执行</b>：编排任务的执行与详情逻辑尚未实现，所以状态写 5-待执行，
     * 而不是 0-执行中 —— 用 0 会带来三个副作用：
     * <ol>
     *   <li>列表上会一直显示"执行中"；</li>
     *   <li>顶栏「运行中」计数会把它算进去（getRunningPyTaskList 查 status=0）；</li>
     *   <li>后端重启对账 reconcileInterruptedTasks 也会查 status=0，会把它误标成「已中断」。</li>
     * </ol>
     *
     * <p><b>pyId 留空</b>：编排任务不属于任何一个脚本，代码编辑器的单文件记录列表
     * （getPyTaskList?pyId=）不应出现它；任务管理页靠 type=0 单独识别与展示。
     *
     * <p><b>if_notified 置 false</b>：编排任务还没跑过，保留「未读」的初始值 ——
     * 后续补上执行逻辑、任务真正跑完后，它就能自然地进入「待查看」流程。
     * 注意：未读判定认的是「已结束状态 1/2/3/4」，而本任务状态是 5-待执行，
     * 所以现在既不会显示「未读」，也不会计入顶栏「待查看」
     * （见 getPyTaskNoticeSummary 与前端 isUnreadTask）。
     *
     * @param param 训练卡 + 评估卡配置
     * @return 新建的任务 VO（type=0、status=5）
     */
    public PyTaskVO createPipelineTask(PipelineTaskParam param) {
        if (param == null) {
            throw new RuntimeException("请求体不能为空");
        }
        // 评估卡里若已经选好「历史成功训练任务」（train-task-id 非空），本次就**不训练**：
        // 不校验训练卡、不建训练子任务，执行时只跑评估子任务（见 executePipelineTask）。
        validatePipelineScript(param.getEvalConfig(), "eval", "评估卡");
        boolean directEvaluation = isDirectEvaluation(param.getEvalConfig());
        boolean reuseTrain = directEvaluation || isReuseTrainModel(param.getEvalConfig(), null);
        normalizePipelineStepConfig(param.getEvalConfig(), "评估卡");
        resolvePipelineDataset(param.getEvalConfig(), "评估卡", PIPELINE_EVAL_DATASET_PARAM, "评估数据集");
        if (!reuseTrain) {
            validatePipelineScript(param.getTrainConfig(), "train", "训练卡");
            validateTrainParams(param.getTrainConfig());
            normalizePipelineStepConfig(param.getTrainConfig(), "训练卡");
            resolvePipelineDataset(param.getTrainConfig(), "训练卡", PIPELINE_TRAIN_DATASET_PARAM, "训练数据集");
        }
        String taskName = validatePipelineTaskName(param.getTaskName());

        String taskId = Ids.uuid();
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setPyId(null);
        task.setType(PyTaskVO.TASK_TYPE_PIPELINE);
        task.setStatus(PyTaskVO.TASK_STATUS_PENDING);
        task.setTaskName(taskName);
        task.setIfDelete(false);
        task.setIfShow(false);
        task.setIfNotified(false);
        task.setIsSubtask(false);
        // 父任务不持有配置：两张卡的配置分别落在下面两个子任务的 config 上
        task.setConfig(null);
        task.setCreateTime(new Date());
        pyTaskMapper.insert(task);
        TaskTracer.born(getTaskDir(taskId), taskId, null, "pipeline");

        // 拆子任务：默认 <父id>-train / <父id>-eval（执行时由后台按顺序串联）；
        // 复用历史训练模型时只建 <父id>-eval（upsertSubTasks 内部判断）
        upsertSubTasks(taskId, taskName, param.getTrainConfig(), param.getEvalConfig());

        if (reuseTrain) {
            log.info("新建编排任务（复用历史训练模型，本次不训练）, taskId={}, 名称={}, 训练模型={}, 评估[数据集={}, 脚本={}]",
                    taskId, taskName, trainModelValueOf(param.getEvalConfig()),
                    param.getEvalConfig().getSchemaKey(), param.getEvalConfig().getScriptName());
        } else {
            log.info("新建编排任务, taskId={}, 名称={}, 训练[数据集={}, 脚本={}, 轮数={}, 批大小={}], 评估[数据集={}, 脚本={}]",
                    taskId, taskName,
                    param.getTrainConfig().getSchemaKey(), param.getTrainConfig().getScriptName(),
                    param.getTrainConfig().getTrainEpochs(), param.getTrainConfig().getTrainBatchSize(),
                    param.getEvalConfig().getSchemaKey(), param.getEvalConfig().getScriptName());
        }
        return buildPyTaskVO(task, null, null);
    }

    /**
     * 编辑编排任务（py_task.type = 0、status = 5 待执行）。
     *
     * <p>只允许改「还没跑过」的任务：一旦状态不再是 5，说明执行逻辑已经开始介入，
     * 此时改配置会让库里记的配置和实际跑的东西对不上，所以直接拒绝。
     * 该限制在服务端强制，不依赖前端是否隐藏了「编辑」按钮。
     *
     * <p>可改内容：任务名称 + 两张卡片的全部配置。
     */
    public PyTaskVO updatePipelineTask(PipelineTaskParam param) {
        if (param == null) {
            throw new RuntimeException("请求体不能为空");
        }
        if (isBlank(param.getTaskId())) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask existing = pyTaskMapper.selectById(param.getTaskId());
        if (existing == null || Boolean.TRUE.equals(existing.getIfDelete())) {
            throw new RuntimeException("任务不存在或已删除: " + param.getTaskId());
        }
        if (!Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(existing.getType())) {
            throw new RuntimeException("只有「训练+评估」编排任务可以编辑，该任务是代码编辑器直接执行的简易任务");
        }
        if (!Integer.valueOf(PyTaskVO.TASK_STATUS_PENDING).equals(existing.getStatus())) {
            throw new RuntimeException("只有「待执行」的编排任务可以编辑，当前状态："
                    + PyTaskVO.statusDescOf(existing.getStatus()));
        }

        // 与新建同一套判断：选了「历史成功训练任务」⇒ 本次不训练（不校验训练卡、不建训练子任务）
        validatePipelineScript(param.getEvalConfig(), "eval", "评估卡");
        boolean reuseTrain = isDirectEvaluation(param.getEvalConfig())
                || isReuseTrainModel(param.getEvalConfig(), param.getTaskId());
        normalizePipelineStepConfig(param.getEvalConfig(), "评估卡");
        resolvePipelineDataset(param.getEvalConfig(), "评估卡", PIPELINE_EVAL_DATASET_PARAM, "评估数据集");
        if (!reuseTrain) {
            validatePipelineScript(param.getTrainConfig(), "train", "训练卡");
            validateTrainParams(param.getTrainConfig());
            normalizePipelineStepConfig(param.getTrainConfig(), "训练卡");
            resolvePipelineDataset(param.getTrainConfig(), "训练卡", PIPELINE_TRAIN_DATASET_PARAM, "训练数据集");
        }
        String taskName = validatePipelineTaskName(param.getTaskName());

        PyTask update = new PyTask();
        update.setId(param.getTaskId());
        update.setTaskName(taskName);
        update.setUpdateTime(new Date());
        pyTaskMapper.updateById(update);

        // 两张卡的配置改由子任务承载：父任务只更新名称，子任务按 id upsert（配置整份覆盖）
        upsertSubTasks(param.getTaskId(), taskName, param.getTrainConfig(), param.getEvalConfig());

        existing.setTaskName(taskName);
        if (reuseTrain) {
            log.info("编辑编排任务（复用历史训练模型，本次不训练）, taskId={}, 名称={}, 训练模型={}, 评估[数据集={}, 脚本={}]",
                    param.getTaskId(), taskName, trainModelValueOf(param.getEvalConfig()),
                    param.getEvalConfig().getSchemaKey(), param.getEvalConfig().getScriptName());
        } else {
            log.info("编辑编排任务, taskId={}, 名称={}, 训练[数据集={}, 脚本={}, 轮数={}, 批大小={}], 评估[数据集={}, 脚本={}]",
                    param.getTaskId(), taskName,
                    param.getTrainConfig().getSchemaKey(), param.getTrainConfig().getScriptName(),
                    param.getTrainConfig().getTrainEpochs(), param.getTrainConfig().getTrainBatchSize(),
                    param.getEvalConfig().getSchemaKey(), param.getEvalConfig().getScriptName());
        }
        return buildPyTaskVO(existing, null, null);
    }

    /**
     * 查询编排任务详情（任务名称 + 两张卡片配置），供「编辑」弹窗回填。
     *
     * <p>列表接口不返回这两段 JSON（会被每 5 秒轮询），所以点编辑时单独取一次。
     * 非编排任务、或字段为空时对应配置返回 null，不抛异常 —— 让调用方自己决定怎么处理。
     */
    public PyTaskDetailVO getPyTaskDetail(String taskId) {
        if (isBlank(taskId)) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("任务不存在或已删除: " + taskId);
        }
        PyTaskDetailVO vo = new PyTaskDetailVO();
        vo.setTaskId(task.getId());
        vo.setTaskName(task.getTaskName());
        vo.setType(task.getType());
        vo.setStatus(task.getStatus());
        // 两张卡的配置落在两个子任务上（父任务 config 为空）；子任务缺失（历史数据未迁移）时给 null
        vo.setTrainConfig(parsePipelineStepConfig(
                subTaskConfigJson(task.getId(), PyTaskVO.SUB_TASK_SUFFIX_TRAIN)));
        vo.setEvalConfig(parsePipelineStepConfig(
                subTaskConfigJson(task.getId(), PyTaskVO.SUB_TASK_SUFFIX_EVAL)));
        return vo;
    }

    /** JSON 字符串 → 卡片配置；空值或解析失败返回 null（不让一条脏数据把接口打挂）。 */
    private PipelineStepConfig parsePipelineStepConfig(String json) {
        if (isBlank(json)) {
            return null;
        }
        try {
            return JSON.parseObject(json, PipelineStepConfig.class);
        } catch (Exception e) {
            log.warn("解析编排任务卡片配置失败，已按空处理: {}", json, e);
            return null;
        }
    }

    /* ======================= 编排任务：子任务（训练 / 评估） ======================= */

    /**
     * 评估卡里那条「训练模型」固定参数的 param_name（值 = 父任务 id）。
     *
     * <p>它会随该子任务的 config 一起被翻译成 {@code --train-task-id <父任务id>} 传给
     * Multi-agent-eval.py（见 {@link #resolveAlgorithmConfigArgs} 与脚本里的同名参数），
     * 脚本据此到 {@code <任务id>-train} 目录加载训练产出的模型。
     */
    private static final String TRAIN_MODEL_PARAM_NAME = "train-task-id";

    /**
     * 建立 / 刷新编排任务的两个子任务（{@code <父id>-train}、{@code <父id>-eval}）。
     *
     * <p>子任务同样是 py_task 的一行：type=1（“由脚本执行的任务”，与代码编辑器直接执行的
     * 任务同构）、is_subtask=1、config = 对应卡片的 JSON、状态 5-待执行。父任务不再持有配置。
     *
     * <p>评估子任务会在 config 里固定写入「训练模型」参数（值 = 父任务 id），前端把它渲染成
     * 不可删除的固定项。
     */
    private void upsertSubTasks(String parentTaskId, String taskName,
                                PipelineStepConfig trainStep, PipelineStepConfig evalStep) {
        // 复用历史训练任务 ⇒ 不建训练子任务（评估子任务的 config 里记着"用哪个任务训练出的模型"）
        boolean directEvaluation = isDirectEvaluation(evalStep);
        if (directEvaluation || isReuseTrainModel(evalStep, parentTaskId)) {
            removeTrainSubTaskIfPresent(parentTaskId);
        } else {
            upsertSubTask(parentTaskId, taskName, PyTaskVO.SUB_TASK_SUFFIX_TRAIN, "·训练", trainStep, false);
        }
        upsertSubTask(parentTaskId, taskName, PyTaskVO.SUB_TASK_SUFFIX_EVAL, "·评估", evalStep, !directEvaluation);
    }

    /**
     * 复用历史训练任务时，把上一次编辑留下的 {@code <父id>-train} 子任务行删掉。
     *
     * <p>编辑只允许在「待执行」状态进行 ⇒ 该行必然还没跑过（不带任何历史），
     * 留着会让详情页和执行逻辑误以为"这次还要训练一遍"。
     */
    private void removeTrainSubTaskIfPresent(String parentTaskId) {
        String trainId = PyTaskVO.subTaskIdOf(parentTaskId, PyTaskVO.SUB_TASK_SUFFIX_TRAIN);
        if (pyTaskMapper.selectById(trainId) != null) {
            pyTaskMapper.deleteById(trainId);
            log.info("编排任务 {} 本次复用历史训练模型 ⇒ 已删除训练子任务 {}", parentTaskId, trainId);
        }
    }

    private void upsertSubTask(String parentTaskId, String taskName, String suffix, String nameSuffix,
                               PipelineStepConfig step, boolean injectTrainModel) {
        if (step == null) {
            throw new RuntimeException("编排任务的卡片配置缺失（" + suffix + "），无法生成子任务");
        }
        String subId = PyTaskVO.subTaskIdOf(parentTaskId, suffix);
        String cardJson = JSON.toJSONString(injectTrainModel
                ? withTrainModelParam(step, parentTaskId) : step);
        String baseName = isBlank(taskName) ? "任务" : taskName.trim();
        PyTask sub = new PyTask();
        sub.setId(subId);
        sub.setPyId(step.getPyId());
        sub.setConfig(cardJson);
        sub.setTaskName(baseName + nameSuffix);
        PyTask existing = pyTaskMapper.selectById(subId);
        if (existing == null) {
            sub.setType(PyTaskVO.TASK_TYPE_SIMPLE);
            sub.setStatus(PyTaskVO.TASK_STATUS_PENDING);
            sub.setIfDelete(false);
            sub.setIfShow(false);
            sub.setIfNotified(false);
            sub.setIsSubtask(true);
            sub.setCreateTime(new Date());
            sub.setUpdateTime(new Date());
            pyTaskMapper.insert(sub);
            log.info("编排任务 {} 的子任务已创建: {}", parentTaskId, subId);
        } else {
            sub.setUpdateTime(new Date());
            pyTaskMapper.updateById(sub);
            log.info("编排任务 {} 的子任务已更新: {}", parentTaskId, subId);
        }
        // 埋点：只有「新建」才登记生命周期起点；更新已有子任务不重置起点
        if (existing == null) {
            TaskTracer.born(getTaskDir(subId), subId, sub.getPyId(), "pipeline-sub");
        }
    }

    /**
     * 往评估卡的脚本配置里固定写入「训练模型」参数（{@link #TRAIN_MODEL_PARAM_NAME}，值 = 父任务 id）。
     *
     * <p>幂等：已有同名参数就地覆盖值（防止用户手改导致评估找不到模型），没有就追加到
     * 「单独配置」组末尾。参数项按界面「自定义参数」的结构写入（uuid id + type=extra），
     * 这样前端配置弹窗能原样识别并显示成不可删除的固定项。
     */
    private PipelineStepConfig withTrainModelParam(PipelineStepConfig step, String parentTaskId) {
        JSONArray array;
        try {
            array = isBlank(step.getConfig()) ? new JSONArray() : JSON.parseArray(step.getConfig().trim());
        } catch (Exception e) {
            log.warn("评估卡的脚本配置不是合法 JSON 数组，将重建为只含「训练模型」的配置: {}", e.getMessage());
            array = new JSONArray();
        }
        if (array == null) {
            array = new JSONArray();
        }
        JSONObject alone = null;
        for (int i = 0; i < array.size(); i++) {
            JSONObject section = array.getJSONObject(i);
            if (section != null && "alone".equals(section.getString("type"))) {
                alone = section;
                break;
            }
        }
        if (alone == null) {
            alone = new JSONObject();
            alone.put("type", "alone");
            alone.put("params", new JSONArray());
            array.add(alone);
        }
        JSONArray params = alone.getJSONArray("params");
        if (params == null) {
            params = new JSONArray();
            alone.put("params", params);
        }
        int foundIndex = -1;
        JSONObject found = null;
        for (int i = 0; i < params.size(); i++) {
            JSONObject p = params.getJSONObject(i);
            if (p != null && TRAIN_MODEL_PARAM_NAME.equals(p.getString("param_name"))) {
                foundIndex = i;
                found = p;
                break;
            }
        }
        JSONObject fixed = new JSONObject(true);     // 保序：便于界面与日志阅读
        // 用户在「配置」里选了历史成功训练任务（值非空且不是本任务的训练子任务）⇒ 保留他的选择，
        // 本次任务就复用那次训练出的模型（不再训练）；否则按老逻辑注入父任务 id（= 本任务的训练子任务）
        String chosen = found == null ? null : found.getString("value");
        boolean reuse = isReuseTrainModelValue(chosen, parentTaskId);
        String value = reuse ? chosen.trim() : parentTaskId;
        fixed.put("name", "训练模型");
        fixed.put("id", found == null || found.get("id") == null ? Ids.uuid() : found.get("id"));
        fixed.put("type", "extra");
        fixed.put("param_name", TRAIN_MODEL_PARAM_NAME);
        fixed.put("value", value);
        // 说明文案里也一律不写 32 位任务 id（配置弹窗的叹号弹层会显示它，写 id 太长）
        fixed.put("extra_desc", reuse
                ? "任务编排固定注入：复用历史训练任务「" + shortTrainTaskLabel(value) + "」训练出的模型（本次不再训练），不可删除"
                : "任务编排固定注入：评估脚本据此加载本任务训练子任务产出的模型（本次先训练再评估），不可删除");
        if (foundIndex >= 0) {
            params.set(foundIndex, fixed);
        } else {
            params.add(fixed);
        }
        step.setConfig(array.toJSONString());
        return step;
    }

    /**
     * 编排任务的**评估子任务**该加载哪个模型目录：
     * {@code <目标任务>/checkpoints/multi_agent_resume}。
     *
     * <p>「目标」= 评估卡「训练模型」选的那个任务：
     * <ul>
     *   <li>选了历史成功训练任务（复用）→ 那个任务自己的目录；</li>
     *   <li>没选（本次先训练再评估）→ 本任务的训练子任务 {@code <父id>-train} 的目录 ——
     *       训练子任务跑完时模型就写在那儿（见 {@link #runPythonTaskAsync} 里的钉死逻辑）。</li>
     * </ul>
     *
     * <p>非编排任务（代码编辑器直接执行评估脚本）返回 {@code null}，
     * 由调用方回落到配置页的 {@code multi_agent_checkpoint}。
     */
    private String resolveSubTaskEvalCheckpoint(String taskId) {
        if (!PyTaskVO.isEvalSubTask(taskId)) {
            return null;
        }
        String parentId = PyTaskVO.parentTaskIdOf(taskId);
        if (isBlank(parentId)) {
            return null;
        }
        String chosen = trainModelValueOfJson(subTaskConfigJson(parentId, PyTaskVO.SUB_TASK_SUFFIX_EVAL));
        String target = isReuseTrainModelValue(chosen, parentId)
                ? chosen.trim()
                : PyTaskVO.subTaskIdOf(parentId, PyTaskVO.SUB_TASK_SUFFIX_TRAIN);
        Path dir = getTaskDir(target).resolve(MARL_CKPT_REL_DIR);
        // Missing task-owned weights must fail at load time, never borrow a shared model.
        return dir.toAbsolutePath().toString();
    }

    /**
     * 给「历史训练任务」做个人看的短标签：{@code 任务名 · 时间}，查不到就退回一句通用说法。
     *
     * <p>刻意**不返回 32 位任务 id** —— 这段文字会进评估卡固定参数的 extra_desc，
     * 在配置弹窗的叹号弹层里显示，写 id 太长且没有信息量（2026-10-08 使用者要求）。
     * 时间口径与 {@link #getTrainModelTaskList()} 一致：训练断点的 updated 优先，
     * 没有才用任务创建时间（yyyy-MM-dd HH:mm）。
     */
    private String shortTrainTaskLabel(String taskId) {
        PyTask t = isBlank(taskId) ? null : pyTaskMapper.selectById(taskId.trim());
        if (t == null) {
            return "历史训练任务";
        }
        String parentId = PyTaskVO.parentTaskIdOf(t.getId());
        PyTask parent = parentId == null ? null : pyTaskMapper.selectById(parentId);
        String name = parent != null && !isBlank(parent.getTaskName())
                ? parent.getTaskName() + "（训练）"
                : (isBlank(t.getTaskName()) ? "" : t.getTaskName());
        String time = "";
        Path progress = getTaskDir(t.getId()).resolve(MARL_CKPT_REL_DIR).resolve(MARL_CKPT_PROGRESS_FILE);
        if (Files.isRegularFile(progress)) {
            try {
                JSONObject json = JSON.parseObject(Files.readString(progress, StandardCharsets.UTF_8));
                if (json != null && json.getString("updated") != null) {
                    time = json.getString("updated").trim();
                }
            } catch (Exception e) {
                log.warn("解析训练断点失败（只影响展示）: {}", progress, e);
            }
        }
        if (isBlank(time) && (parent != null ? parent.getCreateTime() : t.getCreateTime()) != null) {
            Date created = parent != null ? parent.getCreateTime() : t.getCreateTime();
            time = new SimpleDateFormat("yyyy-MM-dd HH:mm").format(created);
        }
        if (time.length() > 16) {
            time = time.substring(0, 16);
        }
        if (isBlank(name)) {
            // 老记录没有任务名（代码编辑器直接跑的训练任务）⇒ 只用时间，与下拉里的写法一致
            return isBlank(time) ? "历史训练任务" : time;
        }
        return isBlank(time) ? name : name + " · " + time;
    }

    /** 取子任务行里的 config JSON（子任务不存在返回 null）。 */
    private String subTaskConfigJson(String parentTaskId, String suffix) {
        PyTask sub = pyTaskMapper.selectById(PyTaskVO.subTaskIdOf(parentTaskId, suffix));
        return sub == null ? null : sub.getConfig();
    }

    /**
     * 读出评估卡配置里「训练模型」参数的取值（{@link #TRAIN_MODEL_PARAM_NAME}），没有则返回 null。
     *
     * <p>取值语义（三态）：
     * <ul>
     *   <li>空 → 还没选，按老逻辑注入父任务 id（= 本任务的训练子任务）；</li>
     *   <li>= 父任务 id（或 {@code <父id>-train}）→ 同样按老逻辑，指本任务的训练子任务；</li>
     *   <li>其它非空值 → 用户从「历史成功训练任务」里选的记录，本次**复用**它的模型、不再训练。</li>
     * </ul>
     */
    private static String trainModelValueOf(PipelineStepConfig evalStep) {
        return evalStep == null ? null : trainModelValueOfJson(evalStep.getConfig());
    }

    /**
     * 从卡片 JSON 里读出「训练模型」的取值（解析失败按"没选"处理）。
     *
     * <p>两种入参形态都要认：
     * <ul>
     *   <li>前端 / 入参那边给的是**卡片数组**：{@code [{"type":"alone","params":[...]}]}；</li>
     *   <li>子任务行里存的是**序列化后的 PipelineStepConfig**：
     *       {@code {"config":"[ ... 卡片数组 ... ]", "pyId":"7", ...}} —— 先剥一层再解析。</li>
     * </ul>
     */
    private static String trainModelValueOfJson(String cardJson) {
        if (isBlank(cardJson)) {
            return null;
        }
        try {
            Object parsed = JSON.parse(cardJson.trim());
            if (parsed instanceof JSONObject) {
                JSONObject obj = (JSONObject) parsed;
                String inner = obj.getString("config");
                if (inner != null && !inner.trim().isEmpty()) {
                    return trainModelValueOfJson(inner);
                }
                JSONArray params = obj.getJSONArray("params");
                return params == null ? null : findTrainModelValue(params);
            }
            if (parsed instanceof JSONArray) {
                JSONArray array = (JSONArray) parsed;
                for (int i = 0; i < array.size(); i++) {
                    JSONObject section = array.getJSONObject(i);
                    if (section == null) {
                        continue;
                    }
                    JSONArray params = section.getJSONArray("params");
                    String value = params == null ? null : findTrainModelValue(params);
                    if (value != null) {
                        return value;
                    }
                }
            }
        } catch (Exception e) {
            log.warn("解析评估卡配置里的「训练模型」参数失败（按未选择处理）: {}", e.getMessage());
        }
        return null;
    }

    /** 在一组参数里找 {@code train-task-id} 的非空取值。 */
    private static String findTrainModelValue(JSONArray params) {
        for (int i = 0; i < params.size(); i++) {
            JSONObject p = params.getJSONObject(i);
            if (p == null || !TRAIN_MODEL_PARAM_NAME.equals(p.getString("param_name"))) {
                continue;
            }
            String value = p.getString("value");
            value = value == null ? "" : value.trim();
            return value.isEmpty() ? null : value;
        }
        return null;
    }

    /** 该取值是否表示"复用历史训练任务"（非空、且不是本任务的训练子任务）。 */
    private static boolean isReuseTrainModelValue(String value, String parentTaskId) {
        if (value == null || value.trim().isEmpty()) {
            return false;
        }
        if (isBlank(parentTaskId)) {
            // 新建时父任务 id 还不存在 ⇒ 值非空只可能是用户选的历史记录
            return true;
        }
        String v = value.trim();
        return !v.equals(parentTaskId)
                && !v.equals(PyTaskVO.subTaskIdOf(parentTaskId, PyTaskVO.SUB_TASK_SUFFIX_TRAIN));
    }

    /** 评估卡是否选择了"复用历史训练任务"（= 本次不训练、只跑评估子任务）。 */
    private static boolean isReuseTrainModel(PipelineStepConfig evalStep, String parentTaskId) {
        return isReuseTrainModelValue(trainModelValueOf(evalStep), parentTaskId);
    }

    /**
     * 查询编排任务的两个子任务（训练在前、评估在后），供任务管理页「详情」展开的子表格使用。
     * 角色由 id 后缀区分（{@code -train} / {@code -eval}），缺失的一方不占位。
     */
    public List<PyTaskVO> getSubTaskList(String parentTaskId) {
        if (isBlank(parentTaskId)) {
            throw new RuntimeException("taskId 不能为空");
        }
        List<PyTaskVO> list = new ArrayList<>();
        for (String suffix : new String[]{PyTaskVO.SUB_TASK_SUFFIX_TRAIN, PyTaskVO.SUB_TASK_SUFFIX_EVAL}) {
            PyTask sub = pyTaskMapper.selectById(PyTaskVO.subTaskIdOf(parentTaskId, suffix));
            if (sub == null || Boolean.TRUE.equals(sub.getIfDelete())) {
                continue;
            }
            PyTaskVO vo = buildPyTaskVO(sub, null, null);
            vo.setIsSubtask(true);
            PyFile pyFile = isBlank(sub.getPyId()) ? null : pyFileMapper.selectById(sub.getPyId());
            vo.setScriptName(pyFile == null ? null : pyFile.getFileName());
            list.add(vo);
        }
        return list;
    }

    /**
     * 执行「训练+评估」编排任务：父任务转 0-执行中、训练子任务立刻开跑、评估子任务置 6-等待中。
     *
     * <p>训练跑完由 {@link #onSubTaskFinished} 自动接力启动评估；任何一个子任务异常
     * （失败 / 终止 / 中断）都会把父任务同步为对应状态。
     */
    public PyTaskVO executePipelineTask(String taskId) {
        if (isBlank(taskId)) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null || Boolean.TRUE.equals(task.getIfDelete())) {
            throw new RuntimeException("任务不存在或已删除: " + taskId);
        }
        if (!Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(task.getType())) {
            throw new RuntimeException("只有「训练+评估」编排任务可以通过本接口执行");
        }
        if (!Integer.valueOf(PyTaskVO.TASK_STATUS_PENDING).equals(task.getStatus())) {
            throw new RuntimeException("只有「待执行」的任务可以执行，当前状态："
                    + PyTaskVO.statusDescOf(task.getStatus()));
        }
        String trainId = PyTaskVO.subTaskIdOf(taskId, PyTaskVO.SUB_TASK_SUFFIX_TRAIN);
        String evalId = PyTaskVO.subTaskIdOf(taskId, PyTaskVO.SUB_TASK_SUFFIX_EVAL);
        PyTask trainSub = pyTaskMapper.selectById(trainId);
        PyTask evalSub = pyTaskMapper.selectById(evalId);

        // 评估卡选了「历史成功训练任务」⇒ 本次**不训练**：只启动评估子任务。
        //   此时 <父id>-train 子任务本就不存在（upsertSubTasks 建的只有评估），
        //   也不置 6-等待中 —— 没有前置，评估直接开跑，跑完由 onSubTaskFinished 收父任务状态。
        if (evalSub != null
                && (isDirectEvaluation(parsePipelineStepConfig(evalSub.getConfig()))
                    || isReuseTrainModelValue(trainModelValueOfJson(evalSub.getConfig()), taskId))) {
            String reusedTaskId = trainModelValueOfJson(evalSub.getConfig());
            requireScriptRunnable(evalSub, "评估子任务");
            setTaskStatus(taskId, 0);
            setTaskStatus(evalId, 0);
            launchTaskProcess(evalSub);
            log.info("执行编排任务 {}（复用历史训练模型 {}）→ 仅启动评估子任务 {}",
                    taskId, reusedTaskId, evalId);
            return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
        }

        if (trainSub == null || evalSub == null) {
            throw new RuntimeException("子任务缺失（请重新保存该任务以生成子任务）: "
                    + trainId + " / " + evalId);
        }
        requireScriptRunnable(trainSub, "训练子任务");
        requireScriptRunnable(evalSub, "评估子任务");

        setTaskStatus(taskId, 0);
        setTaskStatus(trainId, 0);
        setTaskStatus(evalId, PyTaskVO.TASK_STATUS_WAITING);
        launchTaskProcess(trainSub);
        log.info("执行编排任务 {} → 训练子任务 {} 已启动，评估子任务 {} 置为等待中",
                taskId, trainId, evalId);
        return buildPyTaskVO(pyTaskMapper.selectById(taskId), null, null);
    }

    /** 执行前校验：子任务配了脚本、脚本存在、且没有同脚本的其它任务在跑。 */
    private void requireScriptRunnable(PyTask subTask, String label) {
        if (isBlank(subTask.getPyId())) {
            throw new RuntimeException(label + "没有配置脚本，请在任务里重新选择");
        }
        PyFile pyFile = pyFileMapper.selectById(subTask.getPyId());
        if (pyFile == null) {
            throw new RuntimeException(label + "关联的脚本不存在: " + subTask.getPyId());
        }
        PyTaskVO running = getRunningPyTask(pyFile.getId());
        if (running != null) {
            throw new RuntimeException(label + "的脚本已有任务在运行（"
                    + pyFile.getFileName() + "），请等它结束后再执行");
        }
    }

    /**
     * 启动一个「已存在」的任务行（子任务用）：复制脚本到任务目录，按任务自己的 config 跑。
     * 与 {@link #runPyFile} 的区别是不新建任务行（行已由编排流程建好）、不看编辑器「续训」开关。
     */
    private void launchTaskProcess(PyTask task) {
        String taskId = task.getId();
        TaskTracer.event(getTaskDir(taskId), taskId, "LAUNCH", "pyId", task.getPyId());
        PyFile pyFile = pyFileMapper.selectById(task.getPyId());
        if (pyFile == null) {
            markPyTaskFailed(taskId, "关联脚本不存在: " + task.getPyId());
            return;
        }
        final String scriptToRun;
        final String taskOutputDir;
        try {
            Path scriptPath = Paths.get(fileResourceProperties.getPythonFilePath(), pyFile.getFileName())
                    .normalize();
            scriptToRun = copyPythonScriptForTask(scriptPath.toString(), taskId);
            taskOutputDir = getTaskDir(taskId).toAbsolutePath().toString();
        } catch (IOException e) {
            markPyTaskFailed(taskId, "复制 Python 脚本失败: " + e.getMessage());
            return;
        }
        CONSOLE_MAP.put(taskId, Collections.synchronizedList(new ArrayList<>()));
        CONSOLE_INDEX_MAP.put(taskId, 0);
        TASK_OUTPUT_BUFFER.put(taskId, new StringBuilder());
        final String pyFileId = pyFile.getId();
        final String pyFileName = pyFile.getFileName();
        pythonTaskExecutor.execute(() -> runPythonTaskAsync(scriptToRun, taskId, pyFileId, taskOutputDir,
                pyFileName, false, null));
    }

    /**
     * 子任务收尾后的接力（后台心跳逻辑）：所有状态写入口最终都会走到这里。
     *
     * <ul>
     *   <li>训练子任务成功 → 启动评估子任务（评估从 6-等待中 转 0-执行中）</li>
     *   <li>训练子任务失败/终止/中断 → 父任务同步为同一状态</li>
     *   <li>评估子任务成功 → 父任务转 1-执行完成（评估子任务自己已是 1）</li>
     *   <li>评估子任务失败/终止/中断 → 父任务同步为同一状态，**训练子任务状态不动**</li>
     * </ul>
     *
     * <p>非子任务、或找不到父任务时直接返回 —— 代码编辑器直接执行的普通任务不受影响。
     * 任何异常都只记日志：接力失败不应该把已经落库的任务结果改坏。
     */
    private void onSubTaskFinished(String taskId, int status) {
        try {
            PyTask task = pyTaskMapper.selectById(taskId);
            if (task == null || !Boolean.TRUE.equals(task.getIsSubtask())) {
                return;
            }
            String parentId = PyTaskVO.parentTaskIdOf(taskId);
            if (parentId == null) {
                log.warn("子任务 id 不符合 <父id>-train/-eval 约定，跳过接力: {}", taskId);
                return;
            }
            TaskTracer.event(getTaskDir(taskId), taskId, "RELAY",
                    "parentId", parentId, "subTaskStatus", String.valueOf(status));
            if (PyTaskVO.isTrainSubTask(taskId)) {
                if (status == 1) {
                    startEvalSubTask(parentId);
                } else {
                    setTaskStatus(parentId, status);
                    log.info("训练子任务 {} 结束（状态 {}）→ 父任务 {} 同步为同一状态",
                            taskId, PyTaskVO.statusDescOf(status), parentId);
                }
            } else if (PyTaskVO.isEvalSubTask(taskId)) {
                setTaskStatus(parentId, status);
                log.info("评估子任务 {} 结束（状态 {}）→ 父任务 {} 同步为同一状态",
                        taskId, PyTaskVO.statusDescOf(status), parentId);
            }
        } catch (Exception e) {
            log.error("子任务接力处理失败, taskId={}, status={}", taskId, status, e);
        }
    }

    /** 训练子任务成功后启动评估子任务（等待中 → 执行中）。 */
    private void startEvalSubTask(String parentId) {
        PyTask parent = pyTaskMapper.selectById(parentId);
        if (parent == null || !Integer.valueOf(0).equals(parent.getStatus())
                || STOPPED_TASKS.contains(parentId)) {
            log.info("父任务已结束或正在终止，取消评估接力: {}", parentId);
            return;
        }
        String evalId = PyTaskVO.subTaskIdOf(parentId, PyTaskVO.SUB_TASK_SUFFIX_EVAL);
        PyTask evalSub = pyTaskMapper.selectById(evalId);
        if (evalSub == null) {
            log.error("训练已完成但评估子任务不存在: {}", evalId);
            markPyTaskFailed(parentId, "评估子任务不存在，无法继续评估: " + evalId);
            return;
        }
        Integer st = evalSub.getStatus();
        if (!Integer.valueOf(PyTaskVO.TASK_STATUS_WAITING).equals(st)
                && !Integer.valueOf(PyTaskVO.TASK_STATUS_PENDING).equals(st)) {
            log.warn("评估子任务当前状态为 {}（非等待中），跳过自动执行: {}",
                    PyTaskVO.statusDescOf(st), evalId);
            return;
        }
        setTaskStatus(evalId, 0);
        launchTaskProcess(evalSub);
        log.info("训练子任务完成 → 自动开始评估子任务 {}", evalId);
    }

    /** 只改状态与更新时间（父任务 / 评估子任务的接力用）。 */
    private void setTaskStatus(String taskId, int status) {
        PyTask update = new PyTask();
        update.setId(taskId);
        update.setStatus(status);
        update.setUpdateTime(new Date());
        pyTaskMapper.updateById(update);
        // 埋点：这条路径没有前置状态（不改库就读不到 from），留给 reason 说明是接力
        TaskTracer.transition(getTaskDir(taskId), taskId, null, status, "relay");
    }

    /** 校验并归一化任务名称：必填、最长 128（与 py_task.task_name 列宽一致）。 */
    private String validatePipelineTaskName(String taskName) {
        if (isBlank(taskName)) {
            throw new RuntimeException("任务名称不能为空");
        }
        String trimmed = taskName.trim();
        if (trimmed.length() > 128) {
            throw new RuntimeException("任务名称最长 128 个字符，当前 " + trimmed.length() + " 个");
        }
        return trimmed;
    }

    /**
     * 解析卡片要用的数据集，尽量补齐 datasetId / schemaKey / datasetName 三项（仅用于展示）。
     *
     * <p>数据集由「配置」弹窗里的数据集参数决定（训练卡 train-schema、评估卡 eval-schema，
     * 值即 citylearn_dataset.id）。**这里刻意不做「必须选数据集」的强制校验**：参数怎么配
     * 由用户自行决定，没配就让脚本用它自己的默认数据集 —— 真正传给脚本的值走
     * {@link #resolveAlgorithmConfigValue}（数据集 id 在那里被换成 schema 目录名）。
     *
     * <p>所以本方法只负责把「展示用」的三项填上（列表 / 编辑弹窗要显示数据集名称快照），
     * 数据集参数缺失、id 查不到、或已停用都只记日志、不抛异常。早先这里抛错，会把
     * 「用户就是不想配数据集」这种正常选择也拦下来（报「未选择数据集：请点「配置」…」）。
     *
     * @param step             卡片配置
     * @param cardName         卡片名（训练卡 / 评估卡），仅用于日志
     * @param datasetParamName 该卡片对应的数据集参数名（train-schema / eval-schema）
     * @param datasetLabel     该数据集参数的中文名（训练数据集 / 评估数据集），仅用于日志
     */
    private void resolvePipelineDataset(PipelineStepConfig step, String cardName,
                                        String datasetParamName, String datasetLabel) {
        if (step == null) {
            return;
        }
        // 配置里的数据集参数优先（它才是界面上的选择入口）
        Integer datasetId = extractDatasetIdFromConfig(step.getConfig(), datasetParamName);
        CitylearnDataset dataset = datasetId == null ? null : citylearnDatasetMapper.selectById(datasetId);
        if (datasetId != null && dataset == null) {
            log.warn("{}配置里的「{}」({}) 指向的数据集不存在: id={}（不拦截，执行时按原值传给脚本）",
                    cardName, datasetLabel, datasetParamName, datasetId);
        }
        if (dataset != null && (dataset.getEnabled() == null || dataset.getEnabled() != 1)) {
            log.warn("{}配置里的「{}」({}) 已停用: {}（不拦截，仍按该数据集执行）",
                    cardName, datasetLabel, datasetParamName, dataset.getDisplayName());
        }
        if (dataset != null) {
            step.setDatasetId(dataset.getId());
            step.setSchemaKey(dataset.getSchemaKey());
            step.setDatasetName(dataset.getDisplayName());
            return;
        }
        /*
         * 配置里没有该数据集参数：以配置为准把展示字段清空 —— 用户在「配置」里删掉了数据集，
         * 界面就不该再显示旧数据集。只有「这张卡根本没有配置」的老任务，才回落到客户端
         * 显式提交的 datasetId / schemaKey（同样只用于展示）。
         */
        if (isBlank(step.getConfig())
                && (step.getDatasetId() != null || !isBlank(step.getSchemaKey()))) {
            CitylearnDataset explicit = step.getDatasetId() == null
                    ? null : citylearnDatasetMapper.selectById(step.getDatasetId());
            if (explicit != null) {
                step.setSchemaKey(explicit.getSchemaKey());
                step.setDatasetName(explicit.getDisplayName());
            } else if (isBlank(step.getDatasetName())) {
                // 只有 schemaKey（老客户端）：至少把展示名兜成 schema 名
                step.setDatasetName(step.getSchemaKey());
            }
            return;
        }
        step.setDatasetId(null);
        step.setSchemaKey(null);
        step.setDatasetName(null);
        log.info("{}没有配置「{}」({})：不做强制要求，执行时用脚本默认数据集",
                cardName, datasetLabel, datasetParamName);
    }

    /**
     * 从卡片配置里取出数据集参数的取值（citylearn_dataset.id）。
     *
     * <p>按「参数定义 id」匹配而不是按名字匹配：配置里的 param_name 允许被用户改成别名，
     * 而 id（algorithm_param_config.id）是稳定的。兼容两种落库格式：
     * 新分组格式 {@code [{type,params:[...]}]} 与旧扁平格式 {@code [{id,param_name,value}]}。
     *
     * @return 数据集 id；配置里没这个参数、或值不是合法 id 时返回 null
     */
    private Integer extractDatasetIdFromConfig(String configJson, String datasetParamName) {
        if (isBlank(configJson)) {
            return null;
        }
        QueryWrapper<AlgorithmParamConfig> wrapper = new QueryWrapper<>();
        wrapper.lambda()
                .eq(AlgorithmParamConfig::getParamName, datasetParamName)
                .last("LIMIT 1");
        AlgorithmParamConfig def = algorithmParamConfigMapper.selectOne(wrapper);
        if (def == null || def.getId() == null) {
            log.warn("算法参数目录里没有数据集参数 {}，无法从卡片配置解析数据集", datasetParamName);
            return null;
        }
        JSONArray array;
        try {
            array = JSON.parseArray(configJson.trim());
        } catch (Exception e) {
            return null;
        }
        if (array == null) {
            return null;
        }
        for (int i = 0; i < array.size(); i++) {
            JSONObject item = array.getJSONObject(i);
            if (item == null) {
                continue;
            }
            JSONArray params = item.getJSONArray("params");
            if (params != null) {
                // 新格式：参数在分组的 params 里
                Integer found = findDatasetValueInParams(params, def.getId());
                if (found != null) {
                    return found;
                }
            } else if (isSameParamId(item.get("id"), def.getId())) {
                // 旧格式：顶层元素本身就是参数项
                return parseDatasetId(item.get("value"));
            }
        }
        return null;
    }

    /** 在分组的 params 数组里找数据集参数并解析其值 */
    private Integer findDatasetValueInParams(JSONArray params, Integer paramId) {
        for (int i = 0; i < params.size(); i++) {
            JSONObject param = params.getJSONObject(i);
            if (param != null && isSameParamId(param.get("id"), paramId)) {
                return parseDatasetId(param.get("value"));
            }
        }
        return null;
    }

    /**
     * 参数 id 比对：配置里的 id 可能是数字（目录参数）或 uuid 字符串（自定义参数），
     * 统一转成字符串比，避免 getInteger 在 uuid 上抛异常。
     */
    private static boolean isSameParamId(Object rawId, Integer targetId) {
        if (rawId == null || targetId == null) {
            return false;
        }
        return String.valueOf(rawId).trim().equals(String.valueOf(targetId));
    }

    /** 数据集 id 解析：兼容数字与字符串两种写法；非法值返回 null */
    private static Integer parseDatasetId(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            int id = ((Number) value).intValue();
            return id > 0 ? id : null;
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return null;
        }
        try {
            int id = Integer.parseInt(text);
            return id > 0 ? id : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /**
     * 校验卡片选中的脚本：必须存在，且 script_type 与卡片要求一致。
     * 前端下拉已经按类型过滤过，这里再校验一次 —— 接口不能依赖前端约束。
     */
    private void validatePipelineScript(PipelineStepConfig step, String expectedType, String cardName) {
        if (step == null || isBlank(step.getPyId())) {
            throw new RuntimeException(cardName + "未选择脚本");
        }
        PyFile file = pyFileMapper.selectById(step.getPyId());
        if (file == null) {
            throw new RuntimeException(cardName + "选择的脚本不存在（pyId=" + step.getPyId() + "）");
        }
        String actualType = file.getScriptType() == null ? "" : file.getScriptType().trim().toLowerCase();
        boolean baseline = "eval".equals(expectedType) && "NOCONTROL.py".equalsIgnoreCase(file.getFileName());
        if (!expectedType.equals(actualType) && !baseline) {
            throw new RuntimeException(String.format(
                    "%s只能选择 %s 类型的脚本，而「%s」的类型是 %s",
                    cardName, expectedType, file.getFileName(), actualType.isEmpty() ? "(未设置)" : actualType));
        }
        step.setScriptName(file.getFileName());
    }

    /** Resolve direct execution from the registered entrypoint and explicit model source. */
    private boolean isDirectEvaluation(PipelineStepConfig step) {
        if (step == null || isBlank(step.getPyId())) return false;
        PyFile file = pyFileMapper.selectById(step.getPyId());
        if (file == null) return false;
        if ("CHESCA.py".equalsIgnoreCase(file.getFileName())
                || "NOCONTROL.py".equalsIgnoreCase(file.getFileName())) return true;
        if (!"AACMADRL_eval.py".equalsIgnoreCase(file.getFileName())
                || !"on".equals(pipelineParamValue(step.getConfig(), "frozen-anchor"))) return false;
        if (!isBlank(trainModelValueOf(step))
                || !isBlank(pipelineParamValue(step.getConfig(), "checkpoint"))) {
            throw new RuntimeException("固定 Anchor 不能同时选择训练任务或 checkpoint");
        }
        return true;
    }

    private static String pipelineParamValue(String config, String name) {
        if (isBlank(config)) return null;
        Object parsed = JSON.parse(config);
        if (parsed instanceof JSONObject) {
            JSONObject object = (JSONObject) parsed;
            return pipelineParamValue(object.getString("config"), name);
        }
        if (!(parsed instanceof JSONArray)) return null;
        for (Object item : (JSONArray) parsed) {
            if (!(item instanceof JSONObject)) continue;
            JSONArray params = ((JSONObject) item).getJSONArray("params");
            if (params == null) continue;
            for (Object raw : params) {
                if (!(raw instanceof JSONObject)) continue;
                JSONObject param = (JSONObject) raw;
                if (name.equals(param.getString("param_name"))) {
                    String value = param.getString("value");
                    return value == null ? null : value.trim();
                }
            }
        }
        return null;
    }

    /** 训练卡额外要求训练轮数与批大小为正整数。 */
    private void validateTrainParams(PipelineStepConfig trainStep) {
        if (trainStep.getTrainEpochs() == null || trainStep.getTrainEpochs() <= 0) {
            throw new RuntimeException("训练卡的「训练轮数」必须大于 0");
        }
        if (trainStep.getTrainBatchSize() == null || trainStep.getTrainBatchSize() <= 0) {
            throw new RuntimeException("训练卡的「训练批大小」必须大于 0");
        }
    }

    /**
     * 归一化卡片上的「任务级脚本配置」。
     *
     * <p>留空表示不覆盖 —— 运行时沿用脚本文件自身的配置；有值则复用
     * {@link AlgorithmConfigJson#normalize(String)} 的同一套结构校验（与代码编辑器保存
     * py_file.algorithm_config 完全同口径），校验通过后把归一化结果写回入参。
     *
     * @param step     卡片配置
     * @param cardName 卡片名（训练卡 / 评估卡），仅用于报错提示
     */
    private void normalizePipelineStepConfig(PipelineStepConfig step, String cardName) {
        if (step == null) {
            return;
        }
        String config = step.getConfig();
        if (isBlank(config)) {
            step.setConfig(null);
            return;
        }
        try {
            step.setConfig(AlgorithmConfigJson.normalize(config));
        } catch (RuntimeException e) {
            throw new RuntimeException(cardName + "的脚本配置非法：" + e.getMessage());
        }
    }

    /** 判空语义统一定义在 {@link Texts}，这里保留薄委托，免得改几十处调用点。 */
    private static boolean isBlank(String value) {
        return Texts.isBlank(value);
    }

    /**
     * 任务通知汇总：运行中的任务 + 执行完但未读的数量（总数与按脚本聚合）。
     * 供顶栏指示器轮询、代码编辑器文件列表未读红点使用。
     */
    public PyTaskNoticeSummaryVO getPyTaskNoticeSummary() {
        PyTaskNoticeSummaryVO summary = new PyTaskNoticeSummaryVO();

        List<PyTask> running = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfDelete, false)
                .eq(PyTask::getStatus, 0)
                .orderByDesc(PyTask::getCreateTime));
        summary.setRunningTasks(toPyTaskVOsWithScriptName(running));

        /*
         * 未读 = 已结束 且 if_notified 为 0；这里把 NULL 也当作未读，避免历史上出现过空值漏统计。
         *
         * 「已结束」需要同时排除两种未结束状态：
         *   0-执行中   —— 还在跑，没有最终结果；
         *   5-待执行   —— 编排任务（type=0）创建后的状态，还没跑过任何东西。
         * 若只排除 0，编排任务会因为 if_notified=false 被算进「待查看」，
         * 顶栏就会出现一个点不掉、也不该出现的待查看数字。
         */
        List<PyTask> unread = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfDelete, false)
                .ne(PyTask::getStatus, 0)
                .ne(PyTask::getStatus, PyTaskVO.TASK_STATUS_PENDING)
                .and(w -> w.eq(PyTask::getIfNotified, false).or().isNull(PyTask::getIfNotified)));

        Map<String, Integer> unreadByPyId = new HashMap<>();
        int unreadCount = 0;
        if (unread != null && !unread.isEmpty()) {
            /*
             * 只统计「脚本仍存在」的记录。
             * 脚本已被删除的记录没有可查看的内容，在任务记录页也点不了「详情」，
             * 因此永远无法被标记为已读 —— 若把它们算进去，顶栏的「待查看」将永久
             * 停在某个数字上无法清零，看起来像 bug。
             */
            Set<String> pyIds = new HashSet<>();
            for (PyTask task : unread) {
                if (task.getPyId() != null && !task.getPyId().isEmpty()) {
                    pyIds.add(task.getPyId());
                }
            }
            Set<String> existingPyIds = new HashSet<>();
            if (!pyIds.isEmpty()) {
                List<PyFile> files = pyFileMapper.selectBatchIds(pyIds);
                if (files != null) {
                    for (PyFile file : files) {
                        existingPyIds.add(file.getId());
                    }
                }
            }
            for (PyTask task : unread) {
                if (task.getPyId() == null || !existingPyIds.contains(task.getPyId())) {
                    continue;
                }
                unreadCount++;
                unreadByPyId.merge(task.getPyId(), 1, Integer::sum);
            }
        }
        summary.setUnreadCount(unreadCount);
        summary.setUnreadByPyId(unreadByPyId);
        return summary;
    }

    /**
     * 把一条执行记录标记为「已读 / 已提醒」（执行记录列表点击后调用）。
     * 已经是已读时不重复写库。
     */
    public PyTaskVO markPyTaskNotified(String taskId) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        if (!Boolean.TRUE.equals(task.getIfNotified())) {
            PyTask update = new PyTask();
            update.setId(taskId);
            update.setIfNotified(true);
            update.setUpdateTime(new Date());
            pyTaskMapper.updateById(update);
            task.setIfNotified(true);
        }
        // 看的是子任务 → 父任务的「已读」由子任务汇总（父任务没有自己的记录可点）
        String parentId = PyTaskVO.parentTaskIdOf(taskId);
        if (parentId != null) {
            markParentNotifiedIfAllChildrenRead(parentId);
        }
        return buildPyTaskVO(task, null, null);
    }

    /**
     * 一键把「所有未读的执行记录」标记为已读（顶栏「待查看」气泡里的按钮调用）。
     *
     * <p>判定口径**刻意与 {@link #getPyTaskNoticeSummary()} 完全一致**：
     * 已结束（status 既不是 0-执行中、也不是 5-待执行）、未删除、{@code if_notified} 为 0 或 NULL、
     * 且所属脚本仍然存在。口径不一致会出现「点了已读但顶栏数字降不到 0」的假 bug。
     *
     * <p>子任务被标记后，顺带触发父任务的汇总（{@link #markParentNotifiedIfAllChildrenRead}）；
     * 父任务本身 py_id 为空、不参与未读统计，但列表里也想立刻显示成已读。
     *
     * @return 实际被标记的记录条数
     */
    public int markAllPyTaskNotified() {
        List<PyTask> unread = pyTaskMapper.selectList(new QueryWrapper<PyTask>().lambda()
                .eq(PyTask::getIfDelete, false)
                .ne(PyTask::getStatus, 0)
                .ne(PyTask::getStatus, PyTaskVO.TASK_STATUS_PENDING)
                .and(w -> w.eq(PyTask::getIfNotified, false).or().isNull(PyTask::getIfNotified)));
        if (unread == null || unread.isEmpty()) {
            return 0;
        }

        // 只处理「脚本仍存在」的记录 —— 与统计口径保持一致
        Set<String> pyIds = new HashSet<>();
        for (PyTask task : unread) {
            if (task.getPyId() != null && !task.getPyId().isEmpty()) {
                pyIds.add(task.getPyId());
            }
        }
        Set<String> existingPyIds = new HashSet<>();
        if (!pyIds.isEmpty()) {
            List<PyFile> files = pyFileMapper.selectBatchIds(pyIds);
            if (files != null) {
                for (PyFile file : files) {
                    existingPyIds.add(file.getId());
                }
            }
        }

        List<String> ids = new ArrayList<>();
        Set<String> parentIds = new LinkedHashSet<>();
        for (PyTask task : unread) {
            if (task.getPyId() == null || !existingPyIds.contains(task.getPyId())) {
                continue;
            }
            ids.add(task.getId());
            String parentId = PyTaskVO.parentTaskIdOf(task.getId());
            if (parentId != null) {
                parentIds.add(parentId);
            }
        }
        if (ids.isEmpty()) {
            return 0;
        }

        PyTask update = new PyTask();
        update.setIfNotified(true);
        update.setUpdateTime(new Date());
        pyTaskMapper.update(update, new QueryWrapper<PyTask>().lambda().in(PyTask::getId, ids));

        for (String parentId : parentIds) {
            markParentNotifiedIfAllChildrenRead(parentId);
        }
        log.info("一键已读：标记 {} 条执行记录为已读", ids.size());
        return ids.size();
    }

    /**
     * 父任务的「已读」由子任务汇总出来。
     *
     * <p>编排任务的父任务 {@code py_id} 为空，不会出现在代码编辑器「按文件」的记录列表里，
     * 也就没有可点的记录去调用 markPyTaskNotified —— 它的未读状态只能这样消：
     * 父任务<b>已结束</b>、且它名下（未删除的）子任务<b>全部已读</b>时，把父任务也标记为已读。
     *
     * <p>只汇总是刻意的：训练子任务刚看完、评估还没跑完时，父任务本就还没结束（不参与未读统计），
     * 也不会因为「只看了一个子任务」就把整条流水线提前算作已读。
     */
    private void markParentNotifiedIfAllChildrenRead(String parentId) {
        try {
            PyTask parent = pyTaskMapper.selectById(parentId);
            if (parent == null || Boolean.TRUE.equals(parent.getIfNotified())
                    || !PyTaskVO.isFinished(parent.getStatus())) {
                return;
            }
            for (String suffix : new String[]{
                    PyTaskVO.SUB_TASK_SUFFIX_TRAIN, PyTaskVO.SUB_TASK_SUFFIX_EVAL}) {
                PyTask sub = pyTaskMapper.selectById(PyTaskVO.subTaskIdOf(parentId, suffix));
                if (sub == null || Boolean.TRUE.equals(sub.getIfDelete())) {
                    continue;
                }
                if (!Boolean.TRUE.equals(sub.getIfNotified())) {
                    return;      // 还有子任务没看过
                }
            }
            PyTask update = new PyTask();
            update.setId(parentId);
            update.setIfNotified(true);
            update.setUpdateTime(new Date());
            pyTaskMapper.updateById(update);
            log.info("父任务的子任务都已查看 → 父任务标记为已读, parentId={}", parentId);
        } catch (Exception e) {
            // 汇总失败不影响「子任务已读」本身
            log.warn("汇总父任务已读状态失败, parentId={}", parentId, e);
        }
    }

    private void markPyTaskSuccess(String taskId) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setStatus(1);
        task.setUpdateTime(new Date());
        pyTaskMapper.updateById(task);
        TaskTracer.transition(getTaskDir(taskId), taskId, null, 1, "success");
        // 编排任务的子任务：训练成功要接力启动评估，评估成功要回写父任务（见 onSubTaskFinished）
        onSubTaskFinished(taskId, 1);
    }

    private void markPyTaskFailed(String taskId, String errorMessage) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setStatus(2);
        task.setUpdateTime(new Date());
        pyTaskMapper.updateById(task);
        TaskTracer.transition(getTaskDir(taskId), taskId, null, 2, errorMessage);
        saveTaskErrorLog(taskId, errorMessage);
        List<String> consoleList = CONSOLE_MAP.get(taskId);
        if (consoleList != null) {
            consoleList.add("$error");
        }
        // 子任务失败：父任务同步为失败（训练失败则不再启动评估）；父任务自身走到这里时是空操作
        onSubTaskFinished(taskId, 2);
    }

    /**
     * 任务被用户手动终止：状态置 3（运行终止）。
     * 与「执行失败」区分开——终止是用户主动行为，控制台给出终止说明而不是报错。
     */
    private void markPyTaskStopped(String taskId) {
        PyTask task = new PyTask();
        task.setId(taskId);
        task.setStatus(3);
        task.setUpdateTime(new Date());
        pyTaskMapper.updateById(task);
        TaskTracer.transition(getTaskDir(taskId), taskId, null, 3, "user-stopped");
        saveTaskErrorLog(taskId, "任务已被手动终止");
        List<String> consoleList = CONSOLE_MAP.get(taskId);
        if (consoleList != null) {
            consoleList.add("$end-3");
        }
        // 子任务被终止：父任务同步为运行终止（评估子任务被终止时训练子任务不动）
        onSubTaskFinished(taskId, 3);
    }

    /**
     * 终止正在运行的任务：kill 掉 Python 进程并把状态置为 3-运行终止。
     * 幂等：任务已结束（status != 0）时只返回当前状态，不重复处理。
     */
    public PyTaskVO stopPyTask(String taskId) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在");
        }
        boolean stoppedPipeline = Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(task.getType())
                && Integer.valueOf(3).equals(task.getStatus());
        if (!Integer.valueOf(0).equals(task.getStatus()) && !stoppedPipeline) {
            // 已结束（1/2/3）：不重复终止
            log.info("任务已结束，无需终止, taskId={}, status={}", taskId, task.getStatus());
            return getPyTaskResult(taskId);
        }
        if (Integer.valueOf(PyTaskVO.TASK_TYPE_PIPELINE).equals(task.getType())) {
            // Fence the relay before stopping workers: training can finish during cancellation.
            STOPPED_TASKS.add(taskId);
            markPyTaskStopped(taskId);
            List<PyTask> children = new ArrayList<>();
            for (String suffix : Arrays.asList(PyTaskVO.SUB_TASK_SUFFIX_TRAIN, PyTaskVO.SUB_TASK_SUFFIX_EVAL)) {
                PyTask child = pyTaskMapper.selectById(PyTaskVO.subTaskIdOf(taskId, suffix));
                if (child != null && (Integer.valueOf(0).equals(child.getStatus())
                        || Integer.valueOf(PyTaskVO.TASK_STATUS_PENDING).equals(child.getStatus())
                        || Integer.valueOf(PyTaskVO.TASK_STATUS_WAITING).equals(child.getStatus()))) {
                    children.add(child);
                    STOPPED_TASKS.add(child.getId());
                }
            }
            for (PyTask child : children) {
                if (!Integer.valueOf(0).equals(child.getStatus())) {
                    markPyTaskStopped(child.getId());
                }
            }
            for (PyTask child : children) {
                if (Integer.valueOf(0).equals(child.getStatus())) {
                    stopPyTask(child.getId());
                }
            }
            return getPyTaskResult(taskId);
        }
        STOPPED_TASKS.add(taskId);
        TaskTracer.event(getTaskDir(taskId), taskId, "STOP_REQUEST", "pyTaskStatus", String.valueOf(task.getStatus()));
        Process process = RUNNING_PROCESS.get(taskId);
        if (process != null) {
            killProcessTree(process.toHandle());
            log.info("已终止 Python 进程, taskId={}, alive={}", taskId, process.isAlive());
        } else {
            // 后端重启过：内存里已没有 Process 对象，改为按 task.pid 找回子进程并终止，
            // 这样重启后「终止运行」仍然是真终止，而不只是把记录标成已终止。
            Optional<ProcessHandle> handle = readTaskProcessHandle(taskId);
            if (handle.isPresent()) {
                killProcessTree(handle.get());
                log.info("服务重启后按 task.pid 终止 Python 进程, taskId={}, pid={}",
                        taskId, handle.get().pid());
            } else {
                log.warn("未找到运行中的进程（可能已结束，或服务曾重启且进程已退出）, taskId={}，仅更新状态为运行终止", taskId);
            }
        }
        markPyTaskStopped(taskId);
        appendTaskOutputLine(taskId,
                ">> 任务已被手动终止（状态：运行终止）",
                new StringBuilder(),
                CONSOLE_MAP.get(taskId),
                getTaskDir(taskId).resolve("output.log"));
        return getPyTaskResult(taskId);
    }

    /**
     * 后台线程里真正拉起 Python 进程。
     *
     * @param resume 是否断点续训（仅声明了 {@code --resume} 的脚本生效，
     *               见 {@link PyFileParam#getResume()}）
     */
    private void runPythonTaskAsync(String scriptToRun, String taskId, String pyFileId,
                                    String taskOutputDir, String pyFileName, boolean resume,
                                    String resumeFromTaskId) {
        try {
            TaskTracer.event(getTaskDir(taskId), taskId, "ASYNC_ENTER",
                    "script", pyFileName, "resume", String.valueOf(resume));
            List<String> extraArgs = new ArrayList<>();
            extraArgs.add("--output-dir");
            extraArgs.add(taskOutputDir);
            /*
             * CHESCA 系列（2026-10-08 起两条入口同一套）：
             *   · CHESCA.py（纯 CHESCA）与 CHESCA_ResMARL.py（CHESCA + SAC 残差）
             *     参数都改由代码编辑器「配置」弹窗挂到脚本上、执行时翻成命令行传入
             *     （2026-10-10 起不再过白名单，配置里配了什么就传什么）。
             *   · 都不再传 --min-soc-config（那条老路已废除）。
             *     为了任务详情页仍能查到"当时的配置是什么"，JSON 快照照写（**仅存档，脚本不读它**）。
             */
            if ("CHESCA.py".equalsIgnoreCase(pyFileName)
                    || "CHESCA_ResMARL.py".equalsIgnoreCase(pyFileName)) {
                boolean forResMarl = "CHESCA_ResMARL.py".equalsIgnoreCase(pyFileName);
                String configSnapshotPath = batteryMinSocConfigService.writeConfigJsonToTaskDir(
                        taskOutputDir, forResMarl);
                log.info("已写入 {} 配置快照（仅存档；参数走命令行传入）: {}",
                        pyFileName, configSnapshotPath);
            }
            // Multi-agent 系列：一体化 / 只训练 / 只评估 三种入口，参数各不相同。
            // 各脚本 argparse 只声明自己认的参数，传多了会直接
            // "unrecognized arguments" 报错，所以这里必须逐个对齐。
            //   Multi-agent.py        训练+评估一体：--train-schema/--eval-schema/--train-epochs
            //   Multi-agent-train.py  只训练 → 同上 + --checkpoint-dir 输出模型
            //   Multi-agent-eval.py   只评估 → --eval-schema + --checkpoint 读入模型
            //   Multi-agent_copy.py   早期精简副本，只认 --output-dir / --train-epochs
            //                         （旧代码给它传了 --train-schema/--eval-schema，
            //                           必然报错，这里一并修正）
            boolean isMarlFull = "Multi-agent.py".equalsIgnoreCase(pyFileName);
            boolean isMarlTrain = "Multi-agent-train.py".equalsIgnoreCase(pyFileName);
            boolean isMarlEval = "Multi-agent-eval.py".equalsIgnoreCase(pyFileName);
            if ("Multi-agent_copy.py".equalsIgnoreCase(pyFileName)) {
                Integer trainEpochs = batteryMinSocConfigService.getResMarlConfig().getMultiAgentTrainEpochs();
                if (trainEpochs != null && trainEpochs > 0) {
                    extraArgs.add("--train-epochs");
                    extraArgs.add(String.valueOf(trainEpochs));
                }
                log.info("Multi-agent_copy.py 为早期精简副本：只传 --output-dir / --train-epochs");
            }
            if (isMarlFull || isMarlTrain || isMarlEval) {
                ResMarlConfigVO resMarl = batteryMinSocConfigService.getResMarlConfig();
                String trainSchema = resMarl.getTrainSchema();
                if (trainSchema == null || trainSchema.trim().isEmpty()) {
                    trainSchema = "citylearn_challenge_2023_phase_2_local_evaluation";
                }
                String multiAgentEvalSchema = resMarl.getMultiAgentEvalSchema();
                if (multiAgentEvalSchema == null || multiAgentEvalSchema.trim().isEmpty()) {
                    multiAgentEvalSchema = "citylearn_challenge_2023_phase_2_online_evaluation_1";
                }
                // 训练侧（一体化 / 只训练）：需要训测两个 schema + 训练轮数
                if (isMarlFull || isMarlTrain) {
                    extraArgs.add("--train-schema");
                    extraArgs.add(trainSchema.trim());
                    extraArgs.add("--eval-schema");
                    extraArgs.add(multiAgentEvalSchema.trim());
                    Integer trainEpochs = resMarl.getMultiAgentTrainEpochs();
                    if (trainEpochs != null && trainEpochs > 0) {
                        extraArgs.add("--train-epochs");
                        extraArgs.add(String.valueOf(trainEpochs));
                    }
                }
                // 断点续训：按脚本能力过滤（见 RESUME_SUPPORTED_SCRIPTS）。
                // 硬传脚本不认的参数会 "unrecognized arguments" 直接退出，所以这里必须拦。
                if (resume) {
                    if (!RESUME_SUPPORTED_SCRIPTS.contains(pyFileName == null ? "" : pyFileName.trim().toLowerCase())) {
                        /*
                         * 2026-10-07：脚本重构后已没有 --resume（Multi-agent.py 里的注释写明
                         * 「原先这行 from ray.rllib.algorithms.sac import SAC（续训用）已随
                         * --resume 撤下而删，模型构建在 utils/train_phase」）。
                         * 继续注入会让脚本 argparse 直接 unrecognized arguments 退出 ⇒
                         * 这里降级为「忽略开关、按全新训练跑」并明确告知。
                         * 将来脚本恢复 --resume 时，把文件名加进 RESUME_SUPPORTED_SCRIPTS 即可。
                         */
                        log.warn("{} 当前不支持 --resume（脚本已移除该参数），本次忽略「续训」开关，按全新训练执行",
                                pyFileName);
                    } else if (isMarlFull) {
                        String fromTaskId = (resumeFromTaskId == null ? "" : resumeFromTaskId.trim());
                        if (!fromTaskId.isEmpty()) {
                            // P19-1：从「指定的已完成任务」续训。
                            //   ① 把源任务目录里的断点整份复制到本任务目录；
                            //   ② 不传 --checkpoint-dir → 脚本按 __file__ 相对路径解析到
                            //      <本任务目录>/checkpoints/multi_agent_resume，正好命中复制目标；
                            //   断点里的 train_progress.json（已训练轮数 / 最差和 / mid_eval_history
                            //   不适曲线）随复制一并继承，续训曲线与早停判据基线连续。
                            Path srcCkpt = getTaskDir(fromTaskId).resolve(MARL_CKPT_REL_DIR);
                            Path dstCkpt = getTaskDir(taskId).resolve(MARL_CKPT_REL_DIR);
                            if (!Files.isDirectory(srcCkpt)) {
                                throw new RuntimeException(
                                        "所选任务没有可续训的断点目录: " + fromTaskId + " → " + srcCkpt);
                            }
                            if (!Files.exists(srcCkpt.resolve(MARL_CKPT_PROGRESS_FILE))) {
                                throw new RuntimeException(
                                        "所选任务的断点缺少 " + MARL_CKPT_PROGRESS_FILE
                                                + "（无法确定已训练轮数）: " + fromTaskId);
                            }
                            int copied = copyDirectory(srcCkpt, dstCkpt);
                            extraArgs.add("--resume");
                            log.info("续训模式：来源任务={}，复制断点 {} 个文件 → {}；"
                                            + "--train-epochs 按「目标总轮数」解释，不适曲线一并继承",
                                    fromTaskId, copied, dstCkpt);
                        } else {
                            /*
                             * 兼容旧行为（前端未指定来源任务）：断点目录钉在脚本目录下的固定路径。
                             * 脚本是「复制到任务目录后再执行」的，其内置 CKPT_DIR 相对 __file__ 解析
                             * → output/outkpis/<taskId>/checkpoints/multi_agent_resume，每个任务一份，
                             * 换目录后会找不到上一轮断点（表现为「未找到可用 checkpoint → 从头训练」）。
                             * 开关关闭时维持原状（断点留在本任务目录里）。
                             */
                            Path resumeCkptDir = Paths.get(fileResourceProperties.getPythonFilePath(),
                                    "checkpoints", "multi_agent_resume").toAbsolutePath().normalize();
                            extraArgs.add("--checkpoint-dir");
                            extraArgs.add(resumeCkptDir.toString());
                            extraArgs.add("--resume");
                            log.info("续训模式（未指定来源任务）：断点目录={}（跨任务固定），"
                                            + "--train-epochs 按「目标总轮数」解释",
                                    resumeCkptDir);
                        }
                    } else {
                        log.warn("{} 未声明 --resume，本次忽略「续训」开关", pyFileName);
                    }
                }
                // 评估侧（只评估）：只需要评估 schema
                if (isMarlEval) {
                    extraArgs.add("--eval-schema");
                    extraArgs.add(multiAgentEvalSchema.trim());
                }
                // 训练任务（只训练 Multi-agent-train.py）的断点一律固定写进「本任务目录」：
                //   output/outkpis/<taskId>/checkpoints/multi_agent_resume
                // 简易任务与编排子任务都有稳定的 taskId（getTaskDir 不区分两者），
                // 统一落到任务目录后「训练写 → 评估读 → 任务管理查」三处才对得上；
                // 评估子任务/任务管理都靠任务 id 定位（见 Multi-agent-eval.py 的 --train-task-id）。
                // 放在 resMarl 的 checkpoint-dir 之后追加，同名参数以最后一个为准。
                if (isMarlTrain) {
                    Path trainCkptDir = getTaskDir(taskId).resolve(MARL_CKPT_REL_DIR);
                    extraArgs.add("--checkpoint-dir");
                    extraArgs.add(trainCkptDir.toAbsolutePath().toString());
                    log.info("训练任务：断点目录固定为 {}（供评估与任务管理按任务 id 定位）", trainCkptDir);
                }
                // checkpoint：只训练写、只评估读；一体化仍沿用旧逻辑（不传）。
                // 训练任务一律**按任务 id 定位**（上面已把 --checkpoint-dir 钉进本任务目录），
                // 不再用配置页那个全局目录 —— 它是所有任务共用的，写进去会互相覆盖，
                // 也会让「复用历史训练模型」定位不到对应任务的模型
                // （2026-10-08 实测：8 个训练子任务全写进同一个目录；
                //   2026-10-09 实测：只训练的简易任务也被这个字段写进了全局目录）。
                String checkpoint = resMarl.getMultiAgentCheckpoint();
                boolean hasCheckpoint = checkpoint != null && !checkpoint.trim().isEmpty();
                if (isMarlTrain && hasCheckpoint) {
                    log.info("训练任务：忽略配置页的 multi_agent_checkpoint={}"
                                    + "（该值只用于评估侧读取），断点写入本任务目录（供按任务 id 定位）",
                            checkpoint.trim());
                } else if (isMarlEval) {
                    String subCkpt = resolveSubTaskEvalCheckpoint(taskId);
                    if (subCkpt != null) {
                        extraArgs.add("--checkpoint");
                        extraArgs.add(subCkpt);
                        log.info("评估子任务：模型目录={}（按任务 id 定位，配置页的 {} 不参与）",
                                subCkpt, hasCheckpoint ? checkpoint.trim() : "(未配置)");
                    } else if (hasCheckpoint) {
                        extraArgs.add("--checkpoint");
                        extraArgs.add(checkpoint.trim());
                    } else {
                        log.warn("Multi-agent-eval.py 未配置 multi_agent_checkpoint，"
                                + "将回退脚本内置的默认断点目录（DEFAULT_CHECKPOINT_DIR）");
                    }
                }
                // 同步写入配置快照，便于任务目录追溯
                batteryMinSocConfigService.writeConfigJsonToTaskDir(taskOutputDir);
                log.info("Multi-agent 任务: {}（训练={}, 评估={}, 续训={}, 来源任务={}）, "
                                + "train_schema={}, eval_schema={}, checkpoint={}",
                        pyFileName, isMarlFull || isMarlTrain, isMarlFull || isMarlEval, resume && isMarlFull,
                        (resume && isMarlFull && resumeFromTaskId != null && !resumeFromTaskId.trim().isEmpty())
                                ? resumeFromTaskId.trim() : "-",
                        trainSchema, multiAgentEvalSchema, hasCheckpoint ? checkpoint.trim() : "(脚本默认)");
            }
            /*
             * 算法配置带入（「配置」弹窗里的参数）：
             * 取本次要用的配置 JSON 翻译成命令行参数（**任务级 py_task.config 优先**，
             * 没有才回落到脚本级 py_file.algorithm_config），同名以配置为准 ——
             * 也就是「配置里填了就代替 Java 从 res_marl 配置 / 脚本默认值拼的那份」。
             * 放在最后一步做，前面按脚本类型拼参数的逻辑不受影响。
             */
            Map<String, String> configArgs = resolveAlgorithmConfigArgs(taskId, pyFileId, pyFileName, resume);
            extraArgs = applyAlgorithmConfigArgs(extraArgs, configArgs);
            if (!configArgs.isEmpty()) {
                log.info("{} 已带入算法配置参数: {}", pyFileName, configArgs);
            }
            String result = runPythonProcess(scriptToRun, taskId, extraArgs.toArray(new String[0]));
            // output.log 由 Python 直接写入且已是完整日志，这里不再回写（回写会把文件截断）
            parseAndSaveKpis(result, pyFileId);
            markPyTaskSuccess(taskId);
            List<String> consoleList = CONSOLE_MAP.get(taskId);
            if (consoleList != null) {
                consoleList.add("$end-1");
            }
        } catch (TaskStoppedException e) {
            // 用户点了「终止运行」：进程退出码非 0 属正常，标为运行终止而不是失败
            log.warn("Python 任务被手动终止, taskId={}", taskId);
            markPyTaskStopped(taskId);
        } catch (Exception e) {
            // 兜底：状态已是终止（用户先点了终止，随后进程结束才抛异常）时不覆盖成失败
            if (STOPPED_TASKS.contains(taskId)) {
                log.warn("Python 任务已被终止，忽略结束时的异常, taskId={}, msg={}", taskId, e.getMessage());
                markPyTaskStopped(taskId);
                return;
            }
            log.error("Python 异步任务失败, taskId={}", taskId, e);
            markPyTaskFailed(taskId, e.getMessage());
        } finally {
            TaskTracer.event(getTaskDir(taskId), taskId, "ASYNC_EXIT");
            RUNNING_PROCESS.remove(taskId);
            STOPPED_TASKS.remove(taskId);
        }
    }

    private void parseAndSaveKpis(String result, String agentType) {
        List<Kpis> kpisList = new ArrayList<>();
        kpisList.add(new Kpis() {{ setName("Building_1"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("Building_2"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("Building_3"); setAgentType(agentType); }});
        kpisList.add(new Kpis() {{ setName("District"); setAgentType(agentType); }});

        try (BufferedReader reader = new BufferedReader(new StringReader(result))) {
            String line;
            int flag = 0;
            while ((line = reader.readLine()) != null) {
                if ("outputkpi".equals(line)) {
                    flag = 1;
                    continue;
                }
                if (flag == 1) {
                    line = line.trim();
                    if (!shouldParseKpiLine(line)) {
                        continue;
                    }
                    line = line.replaceAll("\\s+", " ");
                    String kpiName = line.split(" ", 2)[0];
                    List<String> values = extractKpiMetricValues(line, kpiName);
                    if (values.size() >= 4) {
                        kpiConsumer.accept(kpiName, kpisList, values.subList(0, 4));
                    }
                }
            }
            kpisMapper.delete(new QueryWrapper<Kpis>().lambda().eq(Kpis::getAgentType, agentType));
            kpisMapper.insert(kpisList);
        } catch (IOException e) {
            throw new RuntimeException("解析 KPI 结果时发生异常", e);
        }
    }

    private Path getTaskDir(String taskId) {
        return SimulationDataPaths.taskDir(fileResourceProperties.getOutFilePath(), taskId);
    }

    // =========================================================================
    // P19-1：断点续训 —— 断点复制 + 「可续训任务」查询
    // =========================================================================

    /**
     * 递归复制目录（用于把源任务的续训断点整份搬到本次任务目录）。
     *
     * <p>已存在同名文件直接覆盖（本任务目录通常为空，覆盖只发生在重复续训场景）。
     *
     * @return 复制的文件个数
     */
    private int copyDirectory(Path src, Path dst) throws IOException {
        if (!Files.isDirectory(src)) {
            throw new IOException("源目录不存在: " + src);
        }
        final int[] count = {0};
        try (Stream<Path> walk = Files.walk(src)) {
            for (Path p : walk.collect(Collectors.toList())) {
                Path target = dst.resolve(src.relativize(p));
                if (Files.isDirectory(p)) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(p, target, StandardCopyOption.REPLACE_EXISTING);
                    count[0]++;
                }
            }
        }
        return count[0];
    }

    /**
     * 「历史训练任务」的展示名，兜底顺序：
     * <b>父任务名（训练）→ 任务自己的名字 → 脚本名（训练）→ 短任务 id（训练）</b>；
     * 四者都取不到才返回 null（调用方显示占位）。
     *
     * <p>2026-10-09 按使用者要求给**老记录也补名字**：早期从代码编辑器直接跑的训练任务没有
     * {@code task_name}，以前只显示时间，续训表里整整一列都是「—」，不好认。现在退到脚本名
     * （如「Multi-agent（训练）」），再退到短 id。
     * ⚠️ 仍然**不放 32 位完整任务 id**（界面上放不下）—— 只用前 8 位，与前端 {@code shortTaskId} 同款 ✓。
     *
     * <p>规则只有这一份实现：评估卡的「复用历史成功训练任务」下拉
     * （{@link #getTrainModelTaskList()}）与代码编辑器「续训」来源任务表
     * （{@link #getResumableTaskList()}）共用，免得两处展示名各改一半、越走越远。
     *
     * @param t          任务本体（可为 null）
     * @param parent     它的父任务（编排任务）；没有父任务时传 null
     * @param scriptName 该次训练跑的脚本名（如 {@code Multi-agent-train.py}），可空
     */
    private String trainTaskDisplayName(PyTask t, PyTask parent, String scriptName) {
        /*
         * ① show_name（仪表盘「展示名称」，用户在记录页给执行记录起的名字 —— 如 seed1/seed2/seed3）
         *    最优先：这是使用者**显式**起的名字，比任何自动推断都可信（2026-10-09 使用者指出）
         *    ⇒ 老记录也没有名字的问题随之消失：type=1 简易任务直接用它 ✓
         *    写入入口：POST /updatePyTaskShowName（已有的仪表盘改名接口，不新增 UI ✓）
         */
        if (t != null && !isBlank(t.getShowName())) {
            return t.getShowName().trim();
        }
        if (parent != null && !isBlank(parent.getTaskName())) {
            return parent.getTaskName() + "（训练）";
        }
        if (t != null && !isBlank(t.getTaskName())) {
            return t.getTaskName();
        }
        if (!isBlank(scriptName)) {
            String s = scriptName.trim();
            if (s.toLowerCase().endsWith(".py")) {
                s = s.substring(0, s.length() - 3);      // 去扩展名：Multi-agent-train.py → Multi-agent-train
            }
            return s + "（训练）";
        }
        if (t != null && !isBlank(t.getId())) {
            String id = t.getId().trim();
            return (id.length() > 8 ? id.substring(0, 8) : id) + "（训练）";
        }
        return null;
    }

    /**
     * 列出「可用于续训」的任务：任务目录下存在
     * {@code checkpoints/multi_agent_resume/train_progress.json} 的任务。
     *
     * <p>返回字段：taskId、scriptName（任务目录里的脚本名）、epochsDone、trainEpochsTarget、
     * bestScore、updated（train_progress.json 的写入时间）、curvePoints（不适曲线的点数）、
     * taskStartTime（py_task 里的开始时间，用于展示与排序）。按 updated 倒序。
     *
     * <p>只读文件系统 + 一次 py_task 查询；单个任务解析失败只跳过，不影响整体列表。
     */
    public List<Map<String, Object>> getResumableTaskList() {
        List<Map<String, Object>> result = new ArrayList<>();
        Path outRoot = Paths.get(fileResourceProperties.getOutFilePath(), "outkpis");
        if (!Files.isDirectory(outRoot)) {
            return result;
        }
        // 预取任务元信息（脚本名/开始时间），避免逐个查库
        Map<String, PyTask> taskMeta = new HashMap<>();
        try {
            for (PyTask t : pyTaskMapper.selectList(null)) {
                taskMeta.put(t.getId(), t);
            }
        } catch (Exception e) {
            log.warn("查询 py_task 元信息失败（续训列表仍会返回文件系统结果）", e);
        }
        try (Stream<Path> dirs = Files.list(outRoot)) {
            List<Path> taskDirs = dirs.filter(Files::isDirectory).collect(Collectors.toList());
            for (Path taskDir : taskDirs) {
                try {
                    Path progress = taskDir.resolve(MARL_CKPT_REL_DIR).resolve(MARL_CKPT_PROGRESS_FILE);
                    if (!Files.isRegularFile(progress)) {
                        continue;
                    }
                    JSONObject json = JSON.parseObject(Files.readString(progress, StandardCharsets.UTF_8));
                    if (json == null) {
                        continue;
                    }
                    String taskId = taskDir.getFileName().toString();
                    // 脚本名：任务目录里第一个 Multi-agent*.py（副本文件名与 py_file.file_name 一致）
                    String scriptName = null;
                    try (Stream<Path> files = Files.list(taskDir)) {
                        scriptName = files
                                .filter(Files::isRegularFile)
                                .map(p -> p.getFileName().toString())
                                .filter(n -> n.toLowerCase().endsWith(".py"))
                                .findFirst().orElse(null);
                    } catch (Exception ignored) {
                        // 脚本名取不到不影响续训（只影响列表展示）
                    }
                    JSONArray hist = json.getJSONArray("mid_eval_history");
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("taskId", taskId);
                    item.put("scriptName", scriptName);
                    item.put("epochsDone", json.getInteger("epochs_done"));
                    item.put("trainEpochsTarget", json.getInteger("train_epochs_target"));
                    item.put("bestScore", json.getBigDecimal("best_score"));
                    item.put("updated", json.getString("updated"));
                    item.put("curvePoints", hist == null ? 0 : hist.size());
                    PyTask meta = taskMeta.get(taskId);
                    // 任务名（父任务名（训练）优先，其次自己的名字；老记录为 null）
                    //   ⇒ 前端「续训」来源任务表新增的「任务名称」列直接读 displayName ✓
                    String parentOfMeta = meta == null ? null : PyTaskVO.parentTaskIdOf(meta.getId());
                    item.put("displayName", trainTaskDisplayName(
                            meta, parentOfMeta == null ? null : taskMeta.get(parentOfMeta), scriptName));
                    item.put("taskName", meta == null ? null : meta.getTaskName());
                    item.put("taskStartTime", meta == null ? null : meta.getCreateTime());
                    result.add(item);
                } catch (Exception e) {
                    log.warn("解析续训断点失败，已跳过: {}", taskDir, e);
                }
            }
        } catch (IOException e) {
            log.warn("扫描续训断点目录失败: {}", outRoot, e);
        }
        // 按 train_progress.json 的 updated 倒序（该字符串为 yyyy-MM-dd HH:mm:ss，可直接字典序比较）
        result.sort((a, b) -> {
            String ua = (String) a.get("updated");
            String ub = (String) b.get("updated");
            if (ua == null && ub == null) {
                return 0;
            }
            if (ua == null) {
                return 1;
            }
            if (ub == null) {
                return -1;
            }
            return ub.compareTo(ua);
        });
        return result;
    }

    /**
     * 查询「以往**成功的训练任务**」，供任务管理页评估卡选择「复用历史训练模型」。
     *
     * <p>与 {@link #getResumableTaskList()} 的区别（后者是"可续训"，只扫磁盘断点、不看任务状态）：
     * <ul>
     *   <li>只收 status=1-执行完成的训练任务：编排任务里的 {@code <父id>-train} 子任务，
     *       或脚本属训练类的简易任务（script_type=train，或文件名以 Multi-agent 开头）；</li>
     *   <li>{@code checkpoints/multi_agent_resume} 下有 {@code train_progress.json}
     *       或 {@code rllib_checkpoint.json} 时 {@code modelReady=true}（可选、可直接复用）；
     *       模型已经丢了的历史任务也照样列出来，但 {@code modelReady=false}，
     *       前端显示「（模型已丢失）」并禁选 —— 记录要看得见，但选了加载不了；</li>
     *   <li>返回的 {@code taskId} 可直接填进评估卡的 {@code train-task-id}
     *       （脚本侧同时认 {@code <id>} 与 {@code <id>-train} 两种写法）。</li>
     * </ul>
     *
     * @param trainPyId 只列「由这个训练脚本（{@code py_file.id}）产出」的任务记录；
     *                  留空则不按脚本过滤（老调用方与独立页面仍拿全量）。
     *                  <p>为什么要有它：评估卡的「复用历史成功训练任务」下拉在编排任务里
     *                  属于某张具体的训练卡 —— 不按脚本过滤时，选了"区域级 MARL 训练"
     *                  也会把 Multi-agent / CHESCA 的训练记录全列出来，既噪音大、又可能
     *                  选到口径不匹配的模型（观测维度/奖励语义对不上，评估直接报错）。
     */
    public List<Map<String, Object>> getTrainModelTaskList(String trainPyId) {
        List<Map<String, Object>> result = new ArrayList<>();
        List<PyTask> all;
        try {
            all = pyTaskMapper.selectList(null);
        } catch (Exception e) {
            log.warn("查询任务列表失败，训练记录选择器将为空", e);
            return result;
        }
        Map<String, PyTask> taskById = new HashMap<>();
        Map<String, PyFile> fileById = new HashMap<>();
        try {
            for (PyFile f : pyFileMapper.selectList(null)) {
                fileById.put(f.getId(), f);
            }
        } catch (Exception e) {
            log.warn("查询脚本列表失败（只影响脚本名展示）", e);
        }
        for (PyTask t : all) {
            if (t == null || Boolean.TRUE.equals(t.getIfDelete())) {
                continue;
            }
            taskById.put(t.getId(), t);
        }
        for (PyTask t : taskById.values()) {
            if (!Integer.valueOf(1).equals(t.getStatus())) {      // 1 = 执行完成
                continue;
            }
            PyFile pyFile = isBlank(t.getPyId()) ? null : fileById.get(t.getPyId());
            String scriptName = pyFile == null ? null : pyFile.getFileName();
            String scriptType = pyFile == null || pyFile.getScriptType() == null
                    ? "" : pyFile.getScriptType().trim();
            // 训练类判定：id 后缀、脚本类型 train、或名字以 multi-agent 开头的（但排除 *-eval
            // 那种只评估的脚本 —— 它们的 script_type 是 eval，跑完也不产出模型）
            boolean trainTask = PyTaskVO.isTrainSubTask(t.getId())
                    || "train".equalsIgnoreCase(scriptType)
                    || (scriptName != null && scriptName.toLowerCase().startsWith("multi-agent")
                        && !"eval".equalsIgnoreCase(scriptType));
            if (!trainTask) {
                continue;
            }
            // 按「训练脚本」过滤：只留由指定脚本 id 跑出来的记录（编排子任务的 pyId
            // 就是训练卡选的脚本；简易任务就是代码编辑器里跑的那个脚本）。
            // 这样评估卡的「复用历史成功训练任务」下拉只显示左边所选训练脚本下的历史任务。
            if (!isBlank(trainPyId)
                    && !trainPyId.trim().equalsIgnoreCase(
                            t.getPyId() == null ? "" : t.getPyId().trim())) {
                continue;
            }
            boolean aacTask = isAacTrainScript(scriptName);
            Path ckptDir = getTaskDir(t.getId()).resolve(
                    aacTask ? AAC_CKPT_REL_DIR : MARL_CKPT_REL_DIR);
            // Keep historical records visible, but only their own model proves readiness.
            boolean modelReady = isUsableCheckpointDir(ckptDir);
            Path effectiveCkptDir = ckptDir;
            String parentId = PyTaskVO.parentTaskIdOf(t.getId());
            PyTask parent = parentId == null ? null : taskById.get(parentId);
            // 展示名一律不带 32 位任务 id（界面上放不下）：优先「父任务名（训练）」，
            // 其次任务自己的名字；老记录（代码编辑器直接跑的训练任务，taskName 为空）
            // 留空 —— 前端那时只显示时间（时间本身就是区分它们的信息）
            // 展示名规则与「续训」来源任务表共用同一份实现（见 trainTaskDisplayName ✓）；
            //   scriptName 作为老记录（无 task_name）的兜底名字 ✓
            String displayName = trainTaskDisplayName(t, parent, scriptName);

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("taskId", t.getId());
            item.put("displayName", displayName);
            item.put("taskName", t.getTaskName());
            item.put("parentTaskId", parentId);
            item.put("scriptName", scriptName);
            item.put("createTime", parent != null ? parent.getCreateTime() : t.getCreateTime());
            Path progress = effectiveCkptDir.resolve(MARL_CKPT_PROGRESS_FILE);
            if (Files.isRegularFile(progress)) {
                try {
                    JSONObject json = JSON.parseObject(Files.readString(progress, StandardCharsets.UTF_8));
                    if (json != null) {
                        item.put("epochsDone", json.getInteger("epochs_done"));
                        item.put("trainEpochsTarget", json.getInteger("train_epochs_target"));
                        item.put("bestScore", json.getBigDecimal("best_score"));
                        item.put("updated", json.getString("updated"));
                    }
                } catch (Exception e) {
                    log.warn("解析训练断点失败（只影响展示）: {}", progress, e);
                }
            }
            item.put("checkpointDir", effectiveCkptDir.toAbsolutePath().toString());
            item.put("modelReady", modelReady);
            item.put("modelFromGlobal", false);
            /*
             * 排序 / 展示用同一个时间：优先训练断点的 updated（= 模型最后写盘时间，最贴近
             * "这条记录"），没有断点进度才用任务创建时间。
             * 两者都是 yyyy-MM-dd HH:mm:ss 文本，可直接字典序比较 —— 这样界面上下拉里
             * 看到的时间就是倒序的（以前按创建时间排、却显示断点时间，看着是乱的）。
             */
            String sortTime = item.get("updated") == null ? "" : String.valueOf(item.get("updated")).trim();
            if (isBlank(sortTime)) {
                Date created = (Date) item.get("createTime");
                sortTime = created == null
                        ? "" : new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(created);
            }
            item.put("sortTime", sortTime);
            item.put("timeText", sortTime.length() > 16 ? sortTime.substring(0, 16) : sortTime);
            result.add(item);
        }
        result.sort((a, b) -> {
            String sa = a.get("sortTime") == null ? "" : String.valueOf(a.get("sortTime"));
            String sb = b.get("sortTime") == null ? "" : String.valueOf(b.get("sortTime"));
            int cmp = sb.compareTo(sa);                 // 倒序；没时间的排最后
            return cmp != 0 ? cmp
                    : String.valueOf(a.get("taskId")).compareTo(String.valueOf(b.get("taskId")));
        });
        return result;
    }

    /**
     * 在全局兜底目录（见 {@link #MARL_GLOBAL_CKPT_REL_DIRS}）里找第一个带可用模型的那个。
     *
     * @return 命中的目录绝对路径；都没命中返回 {@code null}
     */
    private Path resolveGlobalMarlCkptDir() {
        String root = fileResourceProperties.getPythonFilePath();
        if (isBlank(root)) {
            return null;
        }
        for (String rel : MARL_GLOBAL_CKPT_REL_DIRS) {
            Path dir = Paths.get(root.trim()).resolve(rel).toAbsolutePath().normalize();
            if (isUsableCheckpointDir(dir)) {
                return dir;
            }
        }
        return null;
    }

    /** 任务目录里的模型是否可用：目录存在，且带训练断点或 RLlib 的 checkpoint 标记。 */
    private static boolean isUsableCheckpointDir(Path ckptDir) {
        if (!Files.isDirectory(ckptDir)) {
            return false;
        }
        Path manifest = ckptDir.resolve(AAC_MODEL_MANIFEST);
        if (Files.isRegularFile(manifest)) {
            try {
                JSONObject json = JSON.parseObject(Files.readString(manifest, StandardCharsets.UTF_8));
                if (json == null || !"AACMADRL".equals(json.getString("algorithm"))
                        || !"model.pt".equals(json.getString("checkpoint"))) {
                    return false;
                }
                return Files.isRegularFile(ckptDir.resolve("model.pt"));
            } catch (Exception e) {
                return false;
            }
        }
        return Files.isRegularFile(ckptDir.resolve(MARL_CKPT_PROGRESS_FILE))
                || Files.isRegularFile(ckptDir.resolve("rllib_checkpoint.json"));
    }

    private static boolean isAacTrainScript(String scriptName) {
        return "AACMADRL_train.py".equalsIgnoreCase(scriptName);
    }

    /**
     * 读取指定任务的训练断点进度（含 {@code mid_eval_history} 不适曲线），供前端「续训」弹窗预览。
     *
     * <p>返回 {@code train_progress.json} 的原始结构 + 便捷字段（epochsDone / bestScore）。
     * 找不到断点时抛 {@link RuntimeException}，由 Controller 统一包装为 Result.fail。
     */
    public Map<String, Object> getTaskTrainProgress(String taskId) {
        if (taskId == null || taskId.trim().isEmpty()) {
            throw new RuntimeException("taskId 不能为空");
        }
        Path progress = getTaskDir(taskId.trim()).resolve(MARL_CKPT_REL_DIR)
                .resolve(MARL_CKPT_PROGRESS_FILE);
        if (!Files.isRegularFile(progress)) {
            throw new RuntimeException("该任务没有训练断点: " + taskId);
        }
        try {
            JSONObject json = JSON.parseObject(Files.readString(progress, StandardCharsets.UTF_8));
            if (json == null) {
                throw new RuntimeException("断点进度文件为空或格式不正确: " + taskId);
            }
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("taskId", taskId.trim());
            out.put("epochsDone", json.getInteger("epochs_done"));
            out.put("trainEpochsTarget", json.getInteger("train_epochs_target"));
            out.put("bestScore", json.getBigDecimal("best_score"));
            out.put("updated", json.getString("updated"));
            out.put("midEvalHistory", json.getJSONArray("mid_eval_history"));
            return out;
        } catch (IOException e) {
            throw new RuntimeException("读取训练断点失败: " + e.getMessage(), e);
        }
    }

    /**
     * 把子进程 PID 与启动时刻写入任务目录的 task.pid，供后端重启后找回该进程。
     * 写失败不影响任务执行（只影响重启后的"终止"能力）。
     */
    private void saveTaskPidFile(String taskId, Process process) {
        try {
            long pid = process.pid();
            long startMillis = -1L;
            try {
                startMillis = process.toHandle().info().startInstant()
                        .map(i -> i.toEpochMilli()).orElse(-1L);
            } catch (Exception ignored) {
                // 取不到启动时刻不影响终止：降级为 -1，校验时跳过该比对
            }
            Path path = getTaskDir(taskId).resolve(TASK_PID_FILE);
            Files.createDirectories(path.getParent());
            Files.write(path, (pid + "\n" + startMillis + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.warn("写入 task.pid 失败（不影响任务执行，仅影响重启后的终止能力）, taskId={}", taskId, e);
        }
    }

    /**
     * 从 task.pid 还原进程句柄，并做三重校验避免 PID 被系统回收后杀错无关进程：
     * ① 进程存活；② 命令行含 python；③ 启动时刻与记录一致（取不到则跳过）。
     */
    private Optional<ProcessHandle> readTaskProcessHandle(String taskId) {
        Path path = getTaskDir(taskId).resolve(TASK_PID_FILE);
        if (!Files.exists(path)) {
            return Optional.empty();
        }
        try {
            List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
            if (lines.isEmpty() || lines.get(0).trim().isEmpty()) {
                return Optional.empty();
            }
            long pid = Long.parseLong(lines.get(0).trim());
            long expectedStart = lines.size() > 1 && !lines.get(1).trim().isEmpty()
                    ? Long.parseLong(lines.get(1).trim()) : -1L;

            Optional<ProcessHandle> found = ProcessHandle.of(pid);
            if (!found.isPresent() || !found.get().isAlive()) {
                return Optional.empty();
            }
            ProcessHandle handle = found.get();
            // 注意：ProcessHandle.info() 直接返回 Info（不是 Optional），只有 Info 的各字段才是 Optional
            ProcessHandle.Info info = handle.info();
            String cmd = (info.command().orElse("") + " " + info.commandLine().orElse("")).trim();
            if (!cmd.toLowerCase().contains("python")) {
                log.warn("task.pid 记录的 PID {} 已不是 Python 进程（{}），视为 PID 被回收, taskId={}",
                        pid, cmd, taskId);
                return Optional.empty();
            }
            if (expectedStart > 0) {
                long actualStart = info.startInstant()
                        .map(i -> i.toEpochMilli()).orElse(-1L);
                if (actualStart > 0 && Math.abs(actualStart - expectedStart) > 5_000L) {
                    log.warn("task.pid 记录的 PID {} 启动时刻不匹配（期望 {}，实际 {}），视为 PID 被回收, taskId={}",
                            pid, expectedStart, actualStart, taskId);
                    return Optional.empty();
                }
            }
            return Optional.of(handle);
        } catch (Exception e) {
            log.warn("解析 task.pid 失败, taskId={}", taskId, e);
            return Optional.empty();
        }
    }

    /**
     * 任务包装器脚本的绝对路径；文件不存在时返回 null（调用方退回直接执行脚本）。
     */
    private Path taskRunnerPath() {
        try {
            Path path = Paths.get(fileResourceProperties.getPythonFilePath(), TASK_RUNNER_FILE);
            return Files.isRegularFile(path) ? path : null;
        } catch (Exception e) {
            log.warn("解析任务包装器路径失败: {}", e.getMessage());
            return null;
        }
    }

    /**
     * 读取任务退出码（_task_runner.py 写入的整数）。
     * 返回 null 表示文件不存在或不可解析 —— 典型情况是进程被强杀、来不及写。
     */
    private Integer readTaskExitCode(String taskId) {
        Path path = getTaskDir(taskId).resolve(TASK_EXIT_CODE_FILE);
        if (!Files.exists(path)) {
            return null;
        }
        try {
            String text = new String(Files.readAllBytes(path), StandardCharsets.UTF_8).trim();
            return text.isEmpty() ? null : Integer.valueOf(text);
        } catch (Exception e) {
            log.warn("读取 exit_code.txt 失败, taskId={}", taskId, e);
            return null;
        }
    }

    /**
     * 终止一个进程及其后代（Ray worker 等）。
     * 必须先杀后代再杀父进程，否则父进程一死，后代变成孤儿继续占资源。
     */
    private void killProcessTree(ProcessHandle handle) {
        try {
            handle.descendants().forEach(ProcessHandle::destroyForcibly);
        } catch (Exception e) {
            log.warn("终止子进程失败（继续尝试终止主进程）, pid={}", handle.pid(), e);
        }
        handle.destroy();
        try {
            handle.onExit().get(5, TimeUnit.SECONDS);
        } catch (Exception ignored) {
            // 超时或被中断都继续走强杀
        }
        if (handle.isAlive()) {
            handle.destroyForcibly();
        }
    }

    private void saveTaskErrorLog(String taskId, String errorMessage) {
        try {
            Path dir = getTaskDir(taskId);
            Files.createDirectories(dir);
            Files.write(dir.resolve("error.log"),
                    (errorMessage == null ? "" : errorMessage).getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            log.warn("写入任务错误日志失败, taskId={}", taskId, e);
        }
    }

    /**
     * 仅查询任务控制台输出与状态（供前端高频轮询）。
     */
    public PyTaskVO getPyTaskOutput(String taskId) {
        PyTask task = pyTaskMapper.selectById(taskId);
        if (task == null) {
            throw new RuntimeException("任务不存在: " + taskId);
        }
        String output = getLiveTaskOutput(taskId);
        PyTaskVO vo = new PyTaskVO();
        vo.setTaskId(task.getId());
        vo.setPyId(task.getPyId());
        vo.setType(task.getType());
        vo.setStatus(task.getStatus());
        vo.setStatusDesc(PyTaskVO.statusDescOf(task.getStatus()));
        vo.setOutput(output == null ? "" : output);
        vo.setErrorMessage(readTaskErrorLog(taskId));
        return vo;
    }

    /**
     * 读取任务实时/最终控制台输出（内存缓冲 + output.log，取内容更完整的一份）。
     */
    private String getLiveTaskOutput(String taskId) {
        StringBuilder buffer = TASK_OUTPUT_BUFFER.get(taskId);
        if (buffer != null) {
            synchronized (buffer) {
                if (buffer.length() > 0) {
                    return buffer.toString();
                }
            }
        }
        String file = readTaskOutputLog(taskId);
        if (file != null && !file.isEmpty()) {
            return file;
        }
        return readTaskConsoleFull(taskId);
    }

    private String readTaskOutputLog(String taskId) {
        Path path = getTaskDir(taskId).resolve("output.log");
        if (!Files.exists(path)) {
            return null;
        }
        try {
            return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.warn("读取任务输出日志失败, taskId={}", taskId, e);
            return null;
        }
    }

    /**
     * 读取任务已累计的全部控制台输出（不消耗增量游标）。
     */
    private String readTaskConsoleFull(String taskId) {
        List<String> list = CONSOLE_MAP.get(taskId);
        if (list == null || list.isEmpty()) {
            return null;
        }
        StringBuilder sb = new StringBuilder();
        synchronized (list) {
            for (String line : list) {
                if ("$end-1".equals(line) || "$error".equals(line) || "$exitcode".equals(line)
                        || "$end-3".equals(line)) {
                    continue;
                }
                sb.append(line);
            }
        }
        return sb.length() > 0 ? sb.toString() : null;
    }

    private String readTaskErrorLog(String taskId) {
        Path path = getTaskDir(taskId).resolve("error.log");
        if (!Files.exists(path)) {
            return null;
        }
        try {
            return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.warn("读取任务错误日志失败, taskId={}", taskId, e);
            return null;
        }
    }

    private PyTaskVO buildPyTaskVO(PyTask task, String output, String errorMessage) {
        return buildPyTaskVO(task, output, errorMessage, null);
    }

    private PyTaskVO buildPyTaskVO(PyTask task, String output, String errorMessage, List<KpisTransVO> kpis) {
        PyTaskVO vo = new PyTaskVO();
        vo.setTaskId(task.getId());
        vo.setPyId(task.getPyId());
        vo.setType(task.getType());
        vo.setIsSubtask(Boolean.TRUE.equals(task.getIsSubtask()));
        vo.setTaskName(task.getTaskName());
        vo.setStatus(task.getStatus());
        vo.setStatusDesc(PyTaskVO.statusDescOf(task.getStatus()));
        vo.setIfShow(Boolean.TRUE.equals(task.getIfShow()));
        vo.setShowName(task.getShowName());
        vo.setIfNotified(Boolean.TRUE.equals(task.getIfNotified()));
        vo.setOutput(output);
        vo.setErrorMessage(errorMessage);
        vo.setKpis(kpis);
        vo.setCreateTime(task.getCreateTime());
        vo.setUpdateTime(task.getUpdateTime());
        return vo;
    }

    private void appendTaskOutputLine(String taskId, String line, StringBuilder output, List<String> consoleList, Path liveLogPath) {
        String lineWithNewline = line + "\n";
        output.append(lineWithNewline);
        if (taskId != null) {
            StringBuilder buffer = TASK_OUTPUT_BUFFER.get(taskId);
            if (buffer != null) {
                synchronized (buffer) {
                    buffer.append(lineWithNewline);
                }
            }
        }
        if (consoleList != null) {
            consoleList.add(lineWithNewline);
        }
        if (liveLogPath != null) {
            try {
                Files.write(liveLogPath, lineWithNewline.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                log.debug("写入 output.log 失败（可能正在被读取）, taskId={}", taskId);
            }
        }
    }

    private String runPythonProcess(String scriptPath, String taskId, String... extraArgs)
            throws IOException, InterruptedException {
        StringBuilder output = new StringBuilder();
        List<String> command = new ArrayList<>();
        boolean aacTask = scriptPath != null
                && ("AACMADRL_train.py".equalsIgnoreCase(Paths.get(scriptPath).getFileName().toString())
                || "AACMADRL_eval.py".equalsIgnoreCase(Paths.get(scriptPath).getFileName().toString()));
        if (aacTask && (isBlank(aacPythonExecutable) || !Files.isRegularFile(Paths.get(aacPythonExecutable)))) {
            throw new IOException("AAC-MADRL 专用 Python 环境不存在；请设置 CITYLEARN_AAC_PYTHON: "
                    + (aacPythonExecutable == null ? "" : aacPythonExecutable));
        }
        command.add(aacTask ? aacPythonExecutable : pythonExecutable);
        command.add("-u");
        /*
         * 统一经 _task_runner.py 包装执行，让目标脚本的真实退出码落到任务目录的
         * exit_code.txt —— 后端重启后新 JVM 拿不到子进程退出码，只能靠这个文件判定结果
         * （否则只能靠"日志里有没有 KPI 段"猜，成功但不打印 KPI 的脚本会被误判为失败）。
         * 包装器缺失时退回直接执行脚本：少一个退出码文件，任务本身不受影响。
         */
        Path runner = taskRunnerPath();
        if (runner != null) {
            command.add(runner.toString());
            if (taskId != null) {
                // 清掉上一次运行可能留下的退出码，避免被误读成本次结果
                Path exitCodePath = getTaskDir(taskId).resolve(TASK_EXIT_CODE_FILE);
                Files.deleteIfExists(exitCodePath);
                command.add("--exit-code-file");
                command.add(exitCodePath.toAbsolutePath().toString());
            }
            // 用 -- 分隔，避免脚本自己的参数里出现 - 开头时被包装器误解析
            command.add("--");
            command.add(scriptPath);
        } else {
            log.warn("未找到任务包装器 {}，改为直接执行脚本"
                    + "（重启后将无法依据退出码判定结果，只能用日志启发式）", TASK_RUNNER_FILE);
            command.add(scriptPath);
        }
        if (extraArgs != null) {
            Collections.addAll(command, extraArgs);
        }
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Map<String, String> env = pb.environment();
        env.put("PYTHONUNBUFFERED", "1");
        env.put("PYTHONIOENCODING", "utf-8");
        env.put("PYTHONUTF8", "1");
        env.put("NO_COLOR", "1");
        if (aacTask) {
            env.put("CITYLEARNPY_DIR", Paths.get(fileResourceProperties.getPythonFilePath())
                    .toAbsolutePath().normalize().toString());
        }
        /*
         * 【可复现性】District-MARL 必须由父进程固定 PYTHONHASHSEED。
         *   Python 只在**解释器启动时**读一次该变量，进程内 os.environ 赋值完全无效
         *   ⇒ 只能在这里（启动子进程前）给。未固定时 str 哈希每进程不同 ⇒ 裸 set / 文本键
         *   dict 的迭代次序被置换 ⇒ 观测与动作次序错位；实测同 config + 同 seed 复跑 8 次
         *   std=0.039 / range=0.089，**大于全部 A/B 对比的效应量**（≤0.053）。
         *   仅对 District_MARL_* 生效：其它脚本保持原样，避免改变既有实验的可比性。
         *   （Python 侧 District_MARL_train.py / District_MARL_eval.py 还有一层
         *     "未设置就自我重启一次"的兜底，两处任一生效即可。）
         */
        if (scriptPath != null && scriptPath.contains("District_MARL")) {
            env.put("PYTHONHASHSEED", "0");
        }

        List<String> consoleList = taskId != null ? CONSOLE_MAP.get(taskId) : null;

        /*
         * 异步任务（taskId != null）：stdout/stderr 交给操作系统直接重定向到任务目录下的
         * output.log，Java 不再读管道。这是「后端重启后日志不丢、还能继续监控」的关键：
         *   ① Java 不持有管道读端 → JVM 被杀时 Python 不会撞 broken pipe，脚本会照常跑完并继续写日志；
         *   ② 写文件不像写管道那样会被缓冲区写满而阻塞；
         *   ③ 重启后的 Java 直接读同一个文件就能看到实时日志（getLiveTaskOutput 已优先读磁盘）。
         * 同步调用（taskId == null，如 updateLearn 跑 NOCONTROL）保持原样走管道，行为不变。
         */
        Path liveLogPath = null;
        if (taskId != null) {
            Path dir = getTaskDir(taskId);
            Files.createDirectories(dir);
            liveLogPath = dir.resolve(TASK_LOG_FILE);
            Files.deleteIfExists(liveLogPath);
            pb.redirectOutput(ProcessBuilder.Redirect.appendTo(liveLogPath.toFile()));
        }

        Process process = pb.start();
        if (taskId != null) {
            // 登记进程引用，供「终止运行」按钮 kill；同时落盘 PID，供后端重启后仍能终止
            RUNNING_PROCESS.put(taskId, process);
            saveTaskPidFile(taskId, process);
            TaskTracer.event(getTaskDir(taskId), taskId, "PROCESS_START",
                    "pid", String.valueOf(process.pid()),
                    "script", scriptPath == null ? "" : Paths.get(scriptPath).getFileName().toString(),
                    "args", String.valueOf(extraArgs == null ? 0 : extraArgs.length));
        }

        Thread stdoutThread = null;
        if (taskId == null) {
            final Path unusedLogPath = null;
            stdoutThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        synchronized (output) {
                            appendTaskOutputLine(null, line, output, null, unusedLogPath);
                        }
                    }
                } catch (IOException e) {
                    log.error("读取 Python 标准输出失败（同步调用）", e);
                }
            }, "python-stdout-sync");
            stdoutThread.setDaemon(true);
            stdoutThread.start();
        }

        int exitCode;
        try {
            exitCode = process.waitFor();
            if (stdoutThread != null) {
                stdoutThread.join(600_000);
            }
        } finally {
            if (taskId != null) {
                RUNNING_PROCESS.remove(taskId);
            }
        }

        if (taskId != null) {
            // 埋点：退出码是「成功 / 失败 / 终止」三种收尾的唯一客观依据，必须落下来
            TaskTracer.event(getTaskDir(taskId), taskId, "PROCESS_EXIT",
                    "code", String.valueOf(exitCode),
                    "stopped", String.valueOf(STOPPED_TASKS.contains(taskId)));
        }

        // 用户点了「终止运行」：进程是被 kill 的，退出码非 0 属预期，抛专用异常让上层标为「运行终止」
        if (taskId != null && STOPPED_TASKS.contains(taskId)) {
            if (consoleList != null) {
                consoleList.add("$end-3");
            }
            throw new TaskStoppedException("任务已被手动终止");
        }

        if (exitCode != 0) {
            if (consoleList != null) {
                consoleList.add("$exitcode");
            }
            throw new RuntimeException("Python脚本执行失败，退出码：" + exitCode);
        }

        if (taskId != null) {
            // 进程已退出 → 文件写入已结束，完整日志即 output.log
            String text = readTaskOutputLog(taskId);
            return text == null ? "" : text.trim();
        }
        synchronized (output) {
            return output.toString().trim();
        }
    }

    /** 用户手动终止任务时抛出的专用异常，用于把「终止」与「执行失败」区分开。 */
    public static class TaskStoppedException extends RuntimeException {
        public TaskStoppedException(String message) {
            super(message);
        }
    }

    @FunctionalInterface
    interface BiConsumer<T1,T2>{
        void accept(T1 a, T2 b);
    }

    @FunctionalInterface
    interface TriConsumer<T1,T2,T3>{
        void accept(T1 a, T2 b,T3 c);
    }

    private static final Pattern KPI_NUMBER_TOKEN = Pattern.compile(
            "^(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?|NaN|nan)$");

    private static boolean shouldParseKpiLine(String line) {
        if (line == null || line.isEmpty()) {
            return false;
        }
        if (line.startsWith("[") || line.startsWith("|") || line.startsWith("---")) {
            return false;
        }
        if (line.contains("rows x") || line.contains("columns]")) {
            return false;
        }
        if (line.startsWith("name ") || "cost_function".equals(line)) {
            return false;
        }
        if (line.contains("输出目录") || line.contains("KPI 文件") || line.contains("Writing buffered")) {
            return false;
        }
        String normalized = line.replaceAll("\\s+", " ");
        String kpiName = normalized.split(" ", 2)[0];
        return kpiConsumerMap.containsKey(kpiName);
    }

    private static List<String> extractKpiMetricValues(String line, String kpiName) {
        String rest = line.substring(line.indexOf(kpiName) + kpiName.length()).trim();
        List<String> values = new ArrayList<>();
        for (String token : rest.split("\\s+")) {
            if (token.isEmpty()) {
                continue;
            }
            if ("...".equals(token)) {
                values.add("NaN");
                continue;
            }
            if (KPI_NUMBER_TOKEN.matcher(token).matches()) {
                values.add(token);
            }
        }
        while (values.size() < 4) {
            values.add("NaN");
        }
        return values;
    }

    private static BigDecimal stringToBigDecimal(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String cleaned = value.trim();
        if ("NaN".equalsIgnoreCase(cleaned) || "nan".equalsIgnoreCase(cleaned)
                || "...".equals(cleaned) || "-".equals(cleaned)) {
            return null;
        }
        if ("inf".equalsIgnoreCase(cleaned) || "-inf".equalsIgnoreCase(cleaned)
                || "+inf".equalsIgnoreCase(cleaned)) {
            return null;
        }
        try {
            return new BigDecimal(cleaned);
        } catch (NumberFormatException e) {
            log.warn("无法解析 KPI 数值: {}", value);
            return null;
        }
    }

    private static Map<String, BiConsumer<Kpis,String>> kpiConsumerMap = new HashMap<String, BiConsumer<Kpis,String>>(){{
        put("all_time_peak_average", (kpis,value) -> kpis.setAllTimePeakAverage(stringToBigDecimal(value)));
        put("annual_normalized_unserved_energy_total", (kpis,value) -> kpis.setAnnualNormalizedUnservedEnergyTotal(stringToBigDecimal(value)));
        put("carbon_emissions_total", (kpis,value) -> kpis.setCarbonEmissionsTotal(stringToBigDecimal(value)));
        put("cost_total", (kpis,value) -> kpis.setCostTotal(stringToBigDecimal(value)));
        put("daily_one_minus_load_factor_average", (kpis,value) -> kpis.setDailyOneMinusLoadFactorAverage(stringToBigDecimal(value)));
        put("daily_peak_average", (kpis,value) -> kpis.setDailyPeakAverage(stringToBigDecimal(value)));
        put("discomfort_cold_delta_average", (kpis,value) -> kpis.setDiscomfortColdDeltaAverage(stringToBigDecimal(value)));
        put("discomfort_cold_delta_maximum", (kpis,value) -> kpis.setDiscomfortColdDeltaMaximum(stringToBigDecimal(value)));
        put("discomfort_cold_delta_minimum", (kpis,value) -> kpis.setDiscomfortColdDeltaMinimum(stringToBigDecimal(value)));
        put("discomfort_cold_proportion", (kpis,value) -> kpis.setDiscomfortColdProportion(stringToBigDecimal(value)));
        put("discomfort_hot_delta_average", (kpis,value) -> kpis.setDiscomfortHotDeltaAverage(stringToBigDecimal(value)));
        put("discomfort_hot_delta_maximum", (kpis,value) -> kpis.setDiscomfortHotDeltaMaximum(stringToBigDecimal(value)));
        put("discomfort_hot_delta_minimum", (kpis,value) -> kpis.setDiscomfortHotDeltaMinimum(stringToBigDecimal(value)));
        put("discomfort_hot_proportion", (kpis,value) -> kpis.setDiscomfortHotProportion(stringToBigDecimal(value)));
        put("discomfort_proportion", (kpis,value) -> kpis.setDiscomfortProportion(stringToBigDecimal(value)));
        put("electricity_consumption_total", (kpis,value) -> kpis.setElectricityConsumptionTotal(stringToBigDecimal(value)));
        put("monthly_one_minus_load_factor_average", (kpis,value) -> kpis.setMonthlyOneMinusLoadFactorAverage(stringToBigDecimal(value)));
        put("one_minus_thermal_resilience_proportion", (kpis,value) -> kpis.setOneMinusThermalResilienceProportion(stringToBigDecimal(value)));
        put("power_outage_normalized_unserved_energy_total", (kpis,value) -> kpis.setPowerOutageNormalizedUnservedEnergyTotal(stringToBigDecimal(value)));
        put("ramping_average", (kpis,value) -> kpis.setRampingAverage(stringToBigDecimal(value)));
        put("zero_net_energy", (kpis,value) -> kpis.setZeroNetEnergy(stringToBigDecimal(value)));

    }};

    private static final TriConsumer<String,List<Kpis>,List<String>> kpiConsumer = (kpiName ,kpiList, valueList) -> {
        if(null!=kpiConsumerMap.get(kpiName)) {
            for(int i=0;i<4;i++) {
                kpiConsumerMap.get(kpiName).accept(kpiList.get(i), valueList.get(i));
            }
        }

    };

    private static final Map<String,String> scriptMap=new HashMap<String,String>(){{
        put("baseLine","NOCONTROL.py");
        put("diSac","DISAC.py");
        put("multi","Multi-agent.py");
        put("single","Single-agent.py");
    }};
    public void updateLearn(String agentType) {
        String baseScriptPath="D:/Users/clfbe/anaconda3/envs/cl2/Lib/site-packages/citylearn/apply/";

        String fileName=scriptMap.get(agentType);
        if(null==fileName){
            return;
        }
        String scriptPath=baseScriptPath+fileName;

        //D:\Users\clfbe\anaconda3\envs\cl2\Lib\site-packages\citylearn\apply\NOCONTROL.py
        String result = executePythonScript(scriptPath, null, null);
        parseAndSaveKpis(result, agentType);
    }

    /**
     * 将 Python 脚本复制到任务目录：{outFilePath}/outkpis/{taskId}/
     *
     * @return 复制后的脚本绝对路径
     */
    private String copyPythonScriptForTask(String scriptPath, String taskId) throws IOException {
        Path source = Paths.get(scriptPath);
        if (!Files.exists(source)) {
            throw new RuntimeException("Python脚本不存在: " + scriptPath);
        }
        Path targetDir = Paths.get(fileResourceProperties.getOutFilePath(), "outkpis", taskId);
        Files.createDirectories(targetDir);
        Path target = targetDir.resolve(source.getFileName());
        Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
        log.info("已复制 Python 脚本: {} -> {}", source, target);
        return target.toAbsolutePath().toString();
    }

    /**
     * 同步执行 Python（用于 updateLearn 等内部调用，不创建 pyTask）。
     */
    public String executePythonScript(String scriptPath, String taskId, PyFile pyFile) {
        if (taskId != null) {
            throw new IllegalArgumentException("带 taskId 的执行请使用 runPyFile 异步接口");
        }
        try {
            String result = runPythonProcess(scriptPath, null);
            System.out.println(result);
            Files.write(Paths.get("D:/output.txt"), result.getBytes(StandardCharsets.UTF_8));
            return result;
        } catch (IOException | InterruptedException e) {
            throw new RuntimeException("执行Python脚本时发生异常", e);
        }
    }

    public void executePythonScriptNow(String scriptPath,String taskId) {
        List<String> list=CONSOLE_MAP.get(taskId);
        StringBuilder output = new StringBuilder();
        try {
            ProcessBuilder pb = new ProcessBuilder(pythonExecutable, scriptPath);
            pb.redirectErrorStream(true); // 合并标准输出和错误输出
            Process process = pb.start();

            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;

            while ((line = reader.readLine()) != null) {

               list.add(line+"\n");
            }

            int exitCode = process.waitFor(); // 等待脚本执行完成
            if (exitCode != 0) {
                list.add("$exitcode");
                throw new RuntimeException("Python脚本执行失败，退出码：" + exitCode);
            }
            list.add("$end-1");
        } catch (IOException | InterruptedException e) {
            list.add("$error");
            throw new RuntimeException("执行Python脚本时发生异常", e);
        }
    }

    public String getConsoleInfo(String taskId){
        Integer index=CONSOLE_INDEX_MAP.get(taskId);
        List<String> list=CONSOLE_MAP.get(taskId);
        if(null==index || index.equals(-1)){
            return "null";
        }
        StringBuilder sb=new StringBuilder();
        while(index<list.size()){
            String str=list.get(index);
            if("$end-1".equals(str) || "$error".equals(str) || "$exitcode".equals(str)
                    || "$end-3".equals(str)){
                CONSOLE_INDEX_MAP.put(taskId,-1);
            }else{
                sb.append(list.get(index++));
            }
        }
        if(!CONSOLE_INDEX_MAP.get(taskId).equals(-1)){
            CONSOLE_INDEX_MAP.put(taskId,index);
        }
        return sb.toString();
    }

}
