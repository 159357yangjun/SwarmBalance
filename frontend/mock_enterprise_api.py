"""最小可运行的"企业订单服务"模拟器 —— 用于在没有真实网关时验证 EnterpriseDataSource。

启动后监听 127.0.0.1:8765，按 README/enterprise_data_source 约定的 REST 契约
返回样例机队 / 机巢 / 订单；订单按 release_after（启动后多少秒公开）分波发布，
便于演示 PollingOrderSource 只拾取"新到订单"的去重行为。

用法：
    python mock_enterprise_api.py [port]     # 阻塞在本进程
    from mock_enterprise_api import start_server
    url = start_server(port=8765)            # 作为库在后台线程启动
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DRONES = [
    {"id": "D01", "model": "meituan_v4", "lon": 121.500, "lat": 31.260, "capacity_kg": 2.4},
    {"id": "D02", "model": "meituan_v4", "lon": 121.501, "lat": 31.260, "capacity_kg": 2.4},
    {"id": "D03", "model": "sf_ark40", "lon": 121.500, "lat": 31.261, "capacity_kg": 10.0},
    {"id": "D04", "model": "dji_flycart30", "lon": 121.502, "lat": 31.260, "capacity_kg": 30.0},
]

NESTS = [
    {"id": "N01", "lon": 121.500, "lat": 31.260, "charging_power": 50.0, "swap_time_s": 180, "berths": 1},
    {"id": "N02", "lon": 121.512, "lat": 31.263, "charging_power": 50.0, "swap_time_s": 180, "berths": 2},
]

# release_after：该订单在服务启动多少秒后才对外可见（用于演示实时"新到订单"）
ORDERS = [
    {"order_id": "O1001", "pickup_lon": 121.500, "pickup_lat": 31.260,
     "dropoff_lon": 121.512, "dropoff_lat": 31.263, "weight_kg": 1.2,
     "volume_m3": 0.2, "priority": 2, "deadline_s": 1200, "release_after": 0.0},
    {"order_id": "O1002", "pickup_lon": 121.500, "pickup_lat": 31.260,
     "dropoff_lon": 121.518, "dropoff_lat": 31.265, "weight_kg": 8.0,
     "volume_m3": 1.5, "priority": 1, "deadline_s": 1800, "release_after": 0.0},
    {"order_id": "O1003", "pickup_lon": 121.501, "pickup_lat": 31.261,
     "dropoff_lon": 121.508, "dropoff_lat": 31.264, "weight_kg": 1.0,
     "volume_m3": 0.1, "priority": 3, "deadline_s": 600, "release_after": 2.0},
    {"order_id": "O1004", "pickup_lon": 121.502, "pickup_lat": 31.260,
     "dropoff_lon": 121.519, "dropoff_lat": 31.266, "weight_kg": 18.0,
     "volume_m3": 3.0, "priority": 2, "deadline_s": 2400, "release_after": 2.0},
]

_START = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/v1/drones":
            self._json({"items": DRONES})
        elif self.path == "/api/v1/nests":
            self._json({"items": NESTS})
        elif self.path == "/api/v1/orders":
            now = time.time() - (_START or time.time())
            items = [o for o in ORDERS if o.get("release_after", 0.0) <= now]
            self._json({"items": [{k: v for k, v in o.items() if k != "release_after"} for o in items]})
        else:
            self.send_error(404)

    def _json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # 静默访问日志


def start_server(port: int = 8765) -> str:
    global _START
    _START = time.time()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    _START = time.time()
    print(f"mock 企业网关监听 127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()