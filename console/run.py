"""可视化控制台一键启动入口。

用法：
    python -m console.run            # 默认 127.0.0.1:8765
    python -m console.run --port 9000

启动后浏览器打开 http://127.0.0.1:8765/ 即可。
"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="无人机调度仿真可视化控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    print(f"控制台启动中：http://{args.host}:{args.port}/")
    print("首次请求会加载 OSM 地图（约 5 秒），请稍候。")
    uvicorn.run("console.server:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
