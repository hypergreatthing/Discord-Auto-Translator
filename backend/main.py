import os
import sys
import threading
import time
import uvicorn

from .config import load_config
from .priority import set_process_priority, apply_thread_limits
from .server import app
from .tray import SystemTrayApp

class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.server = None

    def run(self):
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="info",
            loop="asyncio"
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self):
        if self.server:
            self.server.should_exit = True

def main():
    print("=" * 60)
    print(" Discord Auto Translator - Local AI Companion Daemon")
    print("=" * 60)

    cfg = load_config()

    # Apply Gaming-friendly priority settings immediately at startup
    priority_mode = "BELOW_NORMAL" if cfg.get("gaming_mode", True) else cfg.get("process_priority", "NORMAL")
    set_process_priority(priority_mode)
    apply_thread_limits(cfg.get("max_cpu_threads", 2))

    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 49152)

    print(f"[Main] Starting companion API on http://{host}:{port}...")
    server_thread = ServerThread(host, port)
    server_thread.start()

    def on_quit():
        print("[Main] Shutting down server...")
        server_thread.stop()
        sys.exit(0)

    print("[Main] Initializing Windows System Tray icon...")
    tray_app = SystemTrayApp(on_quit_callback=on_quit)
    tray_app.run()

if __name__ == "__main__":
    main()
