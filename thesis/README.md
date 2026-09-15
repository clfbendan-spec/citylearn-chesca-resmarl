# 毕业论文 LaTeX 工程

本目录是基于参考模板（`gs参考-毕业论文的latex版本_集成参考文献和说明-2`）生成的研究生毕业论文 LaTeX 工程，主题与开题报告《基于多智能体强化学习的建筑群节能控制策略及可视化研发》一致。

## 目录结构
- `main.tex`：主文件，含封面信息与章节引入
- `ustbthesis.cls` / `gb7714-2015*`：北科大模板与国标参考文献样式（从参考模板拷贝）
- `images/`：封面校徽等图形
- `contents/`：摘要、六章正文、致谢、作者简历、数据集
- `myrefs.bib`：参考文献库（含用户指定的 FAIA240757、Energies 17 20 5211、ICLR2023、arXiv:2012.10504）

## 编译方式
需安装 TeX Live（或 MiKTeX）并勾选 XeLaTeX、Biber、中文字体（建议安装署名字体或使用 ctex 内置字体）。
```
xelatex main.tex
biber main
xelatex main.tex
xelatex main.tex
```
或直接用 latexmk：`latexmk -xelatex -pdf main.tex`

## 首次使用需要做的修改
1. 封面信息：作者、学号、学院、导师、日期已按开题报告预填，请核对。
2. `contents/mresume.tex`：教育经历、科研工作、奖励与论文请按实际填写。
3. `contents/dataset.tex`：答辩委员会、页数与资助信息待填。
4. `images/pictures/`：请补充系统截图、架构图、实验结果图，并在正文对应 `\includegraphics` 处完善。
5. 参考文献：`myrefs.bib` 为主要文献，后续随实验补充。

## 重要提示
正文第五、六章如实标注了“实验尚未完成充分统计”，这是当前项目的真实状态；**在补全多种子统计、基线对比与显著性检验前，不宜在论文中宣称最终性能优势**。第五章的实验结论待实验结果完整后重新撰写。