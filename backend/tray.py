import webbrowser
import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw, ImageFont
import pystray

from .config import load_config, save_config
from .priority import set_process_priority, apply_thread_limits

def create_tray_icon_image(is_gaming_mode: bool = True) -> Image.Image:
    """Generates a clean 64x64 tray icon."""
    width, height = 64, 64
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Background circle: Discord Blurple or Emerald Green if Gaming Mode active
    bg_color = (88, 101, 242) if not is_gaming_mode else (46, 204, 113)
    draw.ellipse([4, 4, 60, 60], fill=bg_color)

    # Stylized globe grid lines
    draw.ellipse([14, 14, 50, 50], outline=(255, 255, 255), width=3)
    draw.line([32, 14, 32, 50], fill=(255, 255, 255), width=3)
    draw.line([14, 32, 50, 32], fill=(255, 255, 255), width=3)

    return image

class SystemTrayApp:
    def __init__(self, on_quit_callback: Optional[Callable[[], None]] = None):
        self.config = load_config()
        self.on_quit_callback = on_quit_callback
        self.icon: Optional[pystray.Icon] = None

    def toggle_gaming_mode(self, icon, item):
        self.config = load_config()
        new_val = not self.config.get("gaming_mode", True)
        self.config["gaming_mode"] = new_val

        # Update process priority
        if new_val:
            self.config["process_priority"] = "BELOW_NORMAL"
            set_process_priority("BELOW_NORMAL")
            apply_thread_limits(self.config.get("max_cpu_threads", 2))
            print("[Tray] Gaming Mode ENABLED (Low CPU priority + 2 thread cap)")
        else:
            self.config["process_priority"] = "NORMAL"
            set_process_priority("NORMAL")
            print("[Tray] Gaming Mode DISABLED (Normal priority)")

        save_config(self.config)
        self.icon.icon = create_tray_icon_image(new_val)

    def set_accuracy_mode(self, mode: str):
        def handler(icon, item):
            self.config = load_config()
            self.config["accuracy_mode"] = mode
            save_config(self.config)
            print(f"[Tray] Accuracy mode changed to: {mode}")
        return handler

    def toggle_ocr_mode(self, icon, item):
        self.config = load_config()
        new_val = not self.config.get("auto_ocr_images", False)
        self.config["auto_ocr_images"] = new_val
        save_config(self.config)
        print(f"[Tray] Auto OCR set to: {new_val}")

    def open_dashboard(self, icon, item):
        port = self.config.get("port", 49152)
        webbrowser.open(f"http://127.0.0.1:{port}/docs")

    def quit_app(self, icon, item):
        print("[Tray] Exiting Discord Auto Translator...")
        if self.icon:
            self.icon.stop()
        if self.on_quit_callback:
            self.on_quit_callback()

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Discord Auto Translator", None, enabled=False),
            pystray.MenuItem("Status: Active on :49152", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🎮 Gaming Mode (Low CPU Priority)",
                self.toggle_gaming_mode,
                checked=lambda item: load_config().get("gaming_mode", True)
            ),
            pystray.MenuItem(
                "Quality: Deep Thought (Complete Sentences)",
                self.set_accuracy_mode("deep_thought"),
                checked=lambda item: load_config().get("accuracy_mode", "deep_thought") == "deep_thought"
            ),
            pystray.MenuItem(
                "Quality: Fast Mode (Low Latency)",
                self.set_accuracy_mode("fast"),
                checked=lambda item: load_config().get("accuracy_mode", "deep_thought") == "fast"
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Auto-Scan All Images (OCR)",
                self.toggle_ocr_mode,
                checked=lambda item: load_config().get("auto_ocr_images", False)
            ),
            pystray.MenuItem("API Documentation & Status", self.open_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )

    def run(self):
        gaming_active = self.config.get("gaming_mode", True)
        self.icon = pystray.Icon(
            name="DiscordAutoTranslator",
            icon=create_tray_icon_image(gaming_active),
            title="Discord Auto Translator (Companion Daemon)",
            menu=self.build_menu()
        )
        self.icon.run()
