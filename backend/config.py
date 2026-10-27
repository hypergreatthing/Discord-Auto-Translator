import json
import os
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    # Server settings
    "host": "127.0.0.1",
    "port": 49152,

    # Gaming & Performance settings
    "gaming_mode": True,               # Low process priority & capped CPU threads
    "process_priority": "BELOW_NORMAL", # "IDLE", "BELOW_NORMAL", "NORMAL"
    "max_cpu_threads": 2,              # Limit threads so games have full core access
    "device": "cpu",                   # "cpu" (leaves 100% GPU to games) or "cuda"
    "compute_type": "int8",            # "int8" (ultra fast, tiny RAM) or "float16"

    # Translation Quality & Completeness
    "accuracy_mode": "deep_thought",   # "deep_thought" (full sentence SBD + beam search) vs "fast" (greedy)
    "beam_size": 4,                    # Beam search width for deep context & natural grammar
    "default_target_lang": "en",       # Target language for viewing foreign text
    "default_reply_lang": "auto",      # Language to translate outgoing replies to ("auto" = last received foreign lang)
    "bilingual_reply": False,          # If True, sends both translated text and (original in parens)

    # Image & Link Settings
    "auto_ocr_images": False,          # False = On-demand (click to OCR, saves gaming CPU); True = Always auto-scan
    "translate_links": True,           # Translate link preview embeds inline
}

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults in case new keys were added
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(data)
            return cfg
    except Exception as e:
        print(f"[Config] Error loading config: {e}. Falling back to defaults.")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[Config] Error saving config: {e}")
