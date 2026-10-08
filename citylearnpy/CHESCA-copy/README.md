# CHESCA
Code for the paper "Winning the 2023 CityLearn Challenge: a Community-based Hierarchical Energy Systems Coordination Algorithm"


## Requirements
- Python
- citylearn (pip install CityLearn==2.1b12 for 2023 challenge environment)
- numpy
- xgboost

## Local evaluation（副本）

本目录为 **CHESCA-copy**，供 `CHESCA.py` 修改实验使用。  
原版对照：`CHESCA-main/` + `local_evaluation.py`。

```bash
cd ..
python CHESCA.py
python CHESCA.py --output-dir ./outkpis/my_task
```

In order to evaluate using a different dataset, change the SCHEMA path to the path of the schema you want to test. 

See data/schemas/ for available schemas.
