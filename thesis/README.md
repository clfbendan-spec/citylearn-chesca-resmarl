# 学位论文源码

论文：《基于机器学习的建筑群能源管理与仿真评估平台设计与实现》。本目录按项目2026年11月15日修订与复核记录整理，保留完整正文及编译必需资源，附77页编译稿 `main.pdf`。

“精简”只指文件组成：不缩写论文内容，不修改实验数值。未收录历史章节备份、未引用插图、写作过程文档、临时检查产物或本机工具链。

## 文件

- `main.tex`：封面信息、排版兼容设置和章节入口。
- `contents/`：中英文摘要、六章正文、致谢、履历和论文数据集表。
- `myrefs.bib`：参考文献库。
- `ustbthesis.cls`、`gb7714-2015.*`、`gb7714-2015-gbk.def`：学校模板和引用样式。
- `images/`：当前正文实际引用的插图及封面标识资源。图片中的PDF是源图，不应作为编译垃圾删除。
- `build.ps1`、`build.bat`：XeLaTeX、Biber、XeLaTeX两次的完整编译流程。
- `scripts/check_manuscript.py`：可选的正文环境、图片、标签和引用键静态检查，仅依赖Python标准库。

## 编译

需要XeLaTeX、Biber，以及ctex、xeCJK、tabu、titlesec、biblatex等宏包。正文使用宋体、黑体及Times New Roman；保持学校版式需准备相应字体。当前版本在Windows便携MiKTeX 26.5环境验证，保留2023 LaTeX兼容层处理旧版tabu表格；其他版本需重新检查页数及目录链接。

工具已经加入PATH时：

```powershell
.\build.ps1
```

或通过参数指定同一套工具链目录，避免混用不同安装：

```powershell
.\build.ps1 -TexBin 'C:\path\to\miktex\bin\x64' -Clean
```

也可以设置 `THESIS_TEX_BIN` 后运行 `build.bat`。编译原地生成 `main.pdf`，日志与辅助文件由Git忽略。

其他系统可在本目录执行：

```sh
xelatex -interaction=nonstopmode -halt-on-error main.tex
biber main
xelatex -interaction=nonstopmode -halt-on-error main.tex
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

可选静态检查：`python scripts/check_manuscript.py`。静态检查不能替代编译和页面检查。使用VS Code时可安装LaTeX Workshop，选择XeLaTeX及Biber流程，保持输出目录为当前目录。

## 当前稿件状态

已修正证据表述、目录锚点、近空白页和数据集表留白，并完成学术润色。六种子统计来自保留的历史审计，部分原始运行摘要仍未恢复；不同评估协议的结果不直接推导共同基准下的优劣。

履历中的入学及毕业时间、学号、学制、提交时间仍待作者最终确认；科研工作、奖励、论文条目及答辩委员会信息按真实情况补齐。仓库版保留当前稿件，不擅自填充个人事实。本目录用于论文编辑和编译，不包含重新执行实验所需的全部数据和模型。
