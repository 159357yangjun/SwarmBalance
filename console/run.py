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

from console.preflight import run_checks


def _import_uvicorn():
    """延后导入 Web 框架依赖。

    原先 `import uvicorn` 写在模块顶部，早于 run_checks()：任何没装依赖的解释器
    （评审跳过 venv 直接 `python -m console.run`）都会在 import 阶段拿到一段裸
    ModuleNotFoundError traceback，而 preflight 里那条"该装什么"的说明永远印不出来。
    """
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or "uvicorn"
        raise SystemExit(
            "缺少 Web 控制台依赖：%s\n"
            "本项目要求 Python 3.10 虚拟环境，请先执行：\n"
            "    python -m venv .venv310\n"
            "    .venv310\\Scripts\\activate        (Windows)\n"
            "    source .venv310/bin/activate      (Linux/macOS)\n"
            "    python -m pip install -r requirements.txt\n"
            "只想临时演示，可用便携模式（仅需 fastapi + uvicorn）：\n"
            "    python -m pip install -r console/requirements.txt\n"
            "详见 README『环境安装』与『答辩应急：便携 Web 模式』两节。" % missing
        )
    return uvicorn


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
    uvicorn = _import_uvicorn()
    print(f"控制台启动中：{url}")
    # 预热走后台线程、端口照常早开：实测若把预热挪到绑定端口之前，虽然首个
    # /api/snapshot 从 4.3s 降到 0.12s，但浏览器要等 8.5s 才能开始加载 CDN 资源，
    # 总可用时间反而从 5.8s 退化到 8.5s。早开端口 + 预热期返回 warming 让前端轮询，
    # 才能让 CDN 加载与地图解析并行（见 server.snapshot 的 202 分支）。
    print("正在后台预热本地 OSM 地图（就绪前页面会显示加载中）。Ctrl+C 可停止服务。")
    if not args.no_browser and args.host in {"127.0.0.1", "localhost"}:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("console.server:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
