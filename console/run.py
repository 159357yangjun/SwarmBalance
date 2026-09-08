"""可视化控制台一键启动入口。

用法：
    python -m console.run                 # 默认 127.0.0.1:8765
    python -m console.run --port 9000
    python -m console.run --open          # 启动后自动打开浏览器（一键启动）

启动后浏览器打开 http://127.0.0.1:8765/ 即可。
"""

import argparse
import threading
import webbrowser

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="无人机调度仿真可视化控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true",
                        help="启动后自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    if args.open:
        # 延迟 2 秒等 uvicorn 就绪后自动打开浏览器
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()

    print(f"控制台启动中：{url}")
    print("首次请求会加载 OSM 地图（约 5 秒），请稍候。")
    uvicorn.run("console.server:app", host=args.host, port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
