"""One shared runtime for HTTP routers: session, locks and temporary scenario state."""
from __future__ import annotations
import sys
import threading
from fastapi.responses import JSONResponse
from swarmbalance.application.session import SimSession
from swarmbalance.application.scene_library import SceneLibrary
from swarmbalance.paths import CONFIG_DIR


class WebRuntime:
    def __init__(self):
        self.session = None
        self.session_lock = threading.Lock()
        self.operation_lock = threading.RLock()
        self.warm_done = threading.Event()
        self.scenario_backup_text = None
        self.scenario_backup_runtime = None
        self.scene_library = SceneLibrary(CONFIG_DIR / "scenes")

    def get_session(self) -> SimSession:
        if self.session is None:
            with self.session_lock:
                if self.session is None:
                    self.session = SimSession()
                    self.session.reset(algorithm="greedy", seed=100)
        return self.session

    def warming_response(self):
        if self.warm_done.is_set() or self.session is not None:
            return None
        return JSONResponse({"warming": True, "detail": "仿真会话正在后台预热，请稍候"}, status_code=202)

    def warmup(self):
        def warm():
            try:
                self.get_session()
            except Exception as exc:
                print(f"[预热] 会话初始化失败，将在首次请求时重试：{exc}", file=sys.stderr)
            finally:
                self.warm_done.set()
        threading.Thread(target=warm, name="session-warmup", daemon=True).start()


runtime = WebRuntime()
