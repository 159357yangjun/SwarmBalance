"""可视化控制台一键启动入口。

用法：
    python -m console.run                 # 默认 127.0.0.1:8765，并自动打开浏览器
    python -m console.run --port 9000
    python -m console.run --no-browser
    python -m console.run --skip-preflight  # 仅高级排障使用
"""

import argparse
import threading
import webbrowser

import uvicorn

from console.preflight import run_checks


def main():
    parser = argparse.ArgumentParser(description="群智优衡——异构无人机集群三维协同调度仿真平台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--skip-preflight", action="store_true", help="跳过环境预检（仅排障使用）")
    parser.add_argument("--portable", action="store_true", help="便携 Web 模式：允许内置 OSM 解析器，缺少桌面/OR-Tools 依赖时降级运行")
    args = parser.parse_args()

    if not args.skip_preflight:
        result = run_checks(portable=args.portable)
        for msg in result["warnings"]:
            print(f"[预检警告] {msg}")
        if result["errors"]:
            print("\n[启动预检失败]")
            for i, msg in enumerate(result["errors"], 1):
                print(f"  {i}. {msg}")
            print("\n请先按 README『环境安装』完成修复；如仅做开发排障，可临时加 --skip-preflight。")
            raise SystemExit(2)
        print("[启动预检] 通过" + ("（便携 Web 模式）" if args.portable else ""))

    url = f"http://{args.host}:{args.port}/"
    print(f"控制台启动中：{url}")
    print("正在后台预热本地 OSM 地图（通常数秒内就绪）。Ctrl+C 可停止服务。")
    if not args.no_browser and args.host in {"127.0.0.1", "localhost"}:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("console.server:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
