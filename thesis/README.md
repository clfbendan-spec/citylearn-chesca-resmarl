# 学位论文 LaTeX 工程

《基于多智能体强化学习的建筑群节能控制策略及可视化研发》的 XeLaTeX 工程，基于北京科技大学
学位论文模板（`ustbthesis.cls`）与 GB/T 7714-2015 参考文献样式。

当前编译结果：**92 页 / 6.4 MB**，0 编译错误，0 未定义引用。

## 目录结构

```
thesis/
├── main.tex                  主文件：封面信息、宏包、章节引入
├── ustbthesis.cls            北科大论文模板（封面、页眉页脚、标题层级）
├── gb7714-2015*.bbx/.cbx     国标参考文献样式（biblatex）
├── gb7714-2015-gbk.def       GBK 编码映射
├── contents/                 正文源文件
│   ├── abstract.tex          中英文摘要
│   ├── chap1.tex ~ chap6.tex 六章正文
│   ├── dataset.tex           数据集与答辩信息
│   ├── mresume.tex           作者简历
│   └── thanks.tex            致谢
├── images/
│   ├── image/                封面图（校徽等）
│   └── pictures/             正文插图（.pdf 矢量图 + .png 位图）
├── scripts/                  插图生成脚本（matplotlib，可重跑）
├── myrefs.bib                参考文献库
└── README.md                 本文件
```

## 编译方式

需安装 TeX Live（或 MiKTeX），并勾选 XeLaTeX、Biber、中文字体（推荐安装 Times New Roman / SimSun，
否则模板会回退到 ctex 内置字体，个别圈号字符可能缺字形）。

```bash
# 标准四步（顺序不能换：biber 必须在第二趟 xelatex 之后才能取到 .bcf）
xelatex -interaction=nonstopmode main.tex
biber main
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

或 `latexmk -xelatex main.tex`。

> ⚠️ **不要用 `latexmk -pdf`**：它会误选 pdflatex，报 `The xeCJK package requires XeTeX to function`。
>
> ⚠️ 新增 `\label` 后第一趟编译必然报 `undefined references`，跑完四步即消失；若四步后仍 undefined，
> 说明 label 拼写或所在环境（如 `\caption` 之外）有问题。

## 在 VS Code 里写论文（LaTeX Workshop）

推荐扩展只有一个：**LaTeX Workshop**（`James-Yu.latex-workshop`）。它提供语法高亮、命令补全、
侧边栏大纲、保存即编译、SyncTeX 正反向同步和内置 PDF 预览，其余扩展都是锦上添花。

配置已随仓库提供，两处各一份、内容一致：

- `thesis/.vscode/settings.json` —— 在 VS Code 里**直接打开 `thesis/`** 时生效
- `.vscode/settings.json`（仓库根）—— 打开整个仓库时生效

| 操作 | 快捷键 |
|------|--------|
| 编译（latexmk: xelatex） | `Ctrl+Alt+B` |
| 查看 PDF（右侧分栏，跟随光标） | `Ctrl+Alt+V` |
| 源码 ↔ PDF 双向跳转 | `Ctrl+Alt+J`；PDF 上**双击**跳回源码 |

> ★★ **不能给 `latex-workshop.latex.outDir` 设子目录（如 `%DIR%/out`）。**
> `main.tex` 用 `\include{contents/*}`，在 `-output-directory` 模式下 xelatex 会去找
> `out/contents/` 写子 `.aux`，目录不存在即报 `I can't write on file 'contents/abstract.aux'`
> 并 `Emergency stop`——实测只出 6 页、**PDF 根本不生成**，界面上只剩一屏编译日志。
> 必须保持 `"latex-workshop.latex.outDir": "%DIR%"`（原地输出）。
>
> 另两项与"好用"直接相关：`autoClean.run` 必须为 `never`（否则每次保存都删掉 `.aux`/`.fdb_latexmk`，
> latexmk 的增量编译失效，92 页每次全量重编）；`linting.chktex.enabled` 建议 `false`
> （chktex 对中文全角标点、CJK 间距误报极多，会把"问题"面板刷满）。

## 图表复现

正文插图全部由脚本生成，改口径后可重跑（**不要**手改 png/pdf）：

| 图 | 文件名 | 生成脚本 |
|----|--------|----------|
| 图 1-1 核心难题与改进方案 | `核心难题与改进方案.png` | `_redraw_fig1_1.py` |
| 图 2-1 CHESCA 单步流程图 | `CHESCA单步流程图.png` | `scripts/gen_chesca_step_flow_fig.py` |
| 图 2-2 三动作技术架构 | `CHESCA三动作技术架构.png` | `scripts/gen_placeholder_figs.py::fig_three_actions` |
| 图 2-3 CHESCA-ResMARL 框架 | `CHESCA-ResMARL框架.png` | `scripts/gen_chesca_resmarl_framework_fig.py` |
| 图 2-4 残差合成示意 | `残差合成图.png` | `_redraw_fig2_4.py` |
| 图 5-1 算法实验流程 | `算法实验流程图.png` | `scripts/gen_placeholder_figs.py::fig_experiment_pipeline` |

> ⚠️ `scripts/gen_placeholder_figs.py` 中的 `fig_residual_fusion()` 是**已废弃**的旧版图 2-4 生成器，
> 直接跑该脚本的 `__main__` 会覆盖`_redraw_fig2_4.py` 的成果。请只调用需要的单个函数。
>
> 脚本用 `Path(__file__).resolve().parent.parent / "images" / "pictures"` 定位输出目录，
> 与正文 `\includegraphics` 的相对路径一致；因此在任意工作目录下执行都能正确落盘。

## 已知待补项

1. `contents/mresume.tex`：教育经历、科研工作、奖励与已发表论文需按实际情况填写（当前为占位）。
2. `contents/dataset.tex`：答辩委员会名单、资助信息待填。
3. 全稿训练算法口径存在两处表述待统一（第五章按 CTDE-IPPO/MAPPO 叙述，第二章按独立 SAC + 凸组合
   残差叙述），需与导师确认后择一。

## 写作约定

- 中文直引号必须用 `“ ”`：XeLaTeX 下英文 `"` 前后都会排成右引号。
- 圈号字符（①②③）在 Times New Roman 中无字形，正文避免使用。
- 参考文献的 `note` 字段在 `@mastersthesis` 中会被打印进参考文献列表，注释请写在 `%` 行。
- 学位论文（`@mastersthesis`）必须给 `address`；电子资源必须给 `urldate`。
