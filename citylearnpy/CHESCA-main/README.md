# CHESCA
Code for the paper "Winning the 2023 CityLearn Challenge: a Community-based Hierarchical Energy Systems Coordination Algorithm"


## Requirements
- Python
- citylearn (pip install CityLearn==2.1b12 for 2023 challenge environment)
- numpy
- xgboost

## Local evaluation
Run the following from the `citylearnpy` directory to locally evaluate the control algorithm:
```bash
cd ..
python local_evaluation.py
# 或指定导出目录（与 NOCONTROL.py 一致，供 Java 编辑器调用）
python local_evaluation.py --output-dir ./outkpis/my_task
```

In order to evaluate using a different dataset, change the SCHEMA path to the path of the schema you want to test. 

See data/schemas/ for available schemas.
