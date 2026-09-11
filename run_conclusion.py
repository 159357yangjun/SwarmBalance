"""项目根目录的一步执行入口。

最常用：
    python run_conclusion.py                 # 标准结项实验
    python run_conclusion.py --preset quick  # 快速自检
    python run_conclusion.py --preset paper  # 更高重复次数
"""
from experiments.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
