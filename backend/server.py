from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .config import load_config, save_config
from .engine import engine_instance
from .ocr import ImageOCREngine
from .priority import set_process_priority, apply_thread_limits
from .voice_engine import voice_engine_instance

app = FastAPI(title="Discord Auto Translator Core", version="1.0.0")

# Enable CORS for Discord desktop client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TranslateRequest(BaseModel):
    text: str
    source_lang: Optional[str] = "auto"
    target_lang: Optional[str] = "en"
    mode: Optional[str] = None

class OCRTranslateRequest(BaseModel):
    image_url: str
    target_lang: Optional[str] = "en"

class ConfigUpdateRequest(BaseModel):
    gaming_mode: Optional[bool] = None
    process_priority: Optional[str] = None
    max_cpu_threads: Optional[int] = None
    accuracy_mode: Optional[str] = None
    beam_size: Optional[int] = None
    default_target_lang: Optional[str] = None
    default_reply_lang: Optional[str] = None
    bilingual_reply: Optional[bool] = None
    auto_ocr_images: Optional[bool] = None
    translate_links: Optional[bool] = None

@app.get("/")
def root():
    return {"status": "ok", "service": "Discord Auto Translator Companion"}

PROTOCOL_VERSION = 1
SERVICE_NAME = "discord-auto-translator"

@app.get("/handshake")
def handshake():
    """Identifies this backend so plugins can verify they're talking to the right service."""
    return {
        "service": SERVICE_NAME,
        "protocol": PROTOCOL_VERSION,
        "version": app.version,
        "ready": True,
    }

@app.get("/ping")
def ping():
    """Lightweight keep-alive check; does no model or config work."""
    return {"pong": True}

@app.get("/status")
def get_status():
    cfg = load_config()
    status = engine_instance.get_status()
    status.update({
        "gaming_mode": cfg.get("gaming_mode", True),
        "process_priority": cfg.get("process_priority", "BELOW_NORMAL"),
        "max_cpu_threads": cfg.get("max_cpu_threads", 2),
    })
    return status

@app.get("/config")
def get_config():
    return load_config()

@app.post("/config")
def update_config(req: ConfigUpdateRequest):
    cfg = load_config()
    req_dict = req.model_dump(exclude_unset=True)
    cfg.update(req_dict)
    save_config(cfg)

    # Re-apply priority/threads if changed
    if "process_priority" in req_dict or "gaming_mode" in req_dict:
        priority_level = "BELOW_NORMAL" if cfg.get("gaming_mode") else cfg.get("process_priority", "NORMAL")
        set_process_priority(priority_level)

    if "max_cpu_threads" in req_dict:
        apply_thread_limits(cfg.get("max_cpu_threads", 2))

    return {"status": "updated", "config": cfg}

@app.post("/translate")
def translate(req: TranslateRequest):
    if not req.text or not req.text.strip():
        return {"translated_text": "", "source_lang": req.source_lang, "target_lang": req.target_lang}

    cfg = load_config()
    target_lang = req.target_lang or cfg.get("default_target_lang", "en")
    mode = req.mode or cfg.get("accuracy_mode", "deep_thought")

    result = engine_instance.translate_text(
        text=req.text,
        source_lang=req.source_lang,
        target_lang=target_lang,
        mode=mode
    )
    return result

@app.post("/ocr_translate")
def ocr_translate(req: OCRTranslateRequest):
    if not req.image_url:
        raise HTTPException(status_code=400, detail="Missing image_url")

    cfg = load_config()
    target_lang = req.target_lang or cfg.get("default_target_lang", "en")

    result = ImageOCREngine.process_and_translate(
        image_source=req.image_url,
        target_lang=target_lang
    )
    return result

@app.post("/update")
def pull_latest_from_github():
    """Pulls the latest code from GitHub for the local repo if it's a git checkout."""
    import os
    import subprocess
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(repo_dir, ".git")):
        return {"updated": False, "reason": "Not a git repository"}
    try:
        proc = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=20
        )
        return {
            "updated": proc.returncode == 0,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
    except Exception as e:
        return {"updated": False, "error": str(e)}


# ==========================================================
# Real-Time Per-User Voice Translation Endpoints
# ==========================================================
class VoiceTrackUserRequest(BaseModel):
    user_id: str
    enabled: bool = True
    username: Optional[str] = "User"
    source_lang: Optional[str] = "ru"
    target_lang: Optional[str] = "en"
    tts: Optional[bool] = True
    output_device_name: Optional[str] = None

class VoiceSpeakingEventRequest(BaseModel):
    user_id: str
    speaking: bool
    username: Optional[str] = None

class VoiceAudioChunkRequest(BaseModel):
    user_id: str
    audio_b64: str
    sample_rate: Optional[int] = 16000
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    username: Optional[str] = None

@app.get("/voice/status")
def voice_status():
    return voice_engine_instance.get_status()

@app.post("/voice/track_user")
def voice_track_user(req: VoiceTrackUserRequest):
    cfg = load_config()
    tgt = req.target_lang or cfg.get("default_target_lang", "en")
    return voice_engine_instance.set_tracked_user(
        user_id=req.user_id,
        enabled=req.enabled,
        username=req.username or "User",
        source_lang=req.source_lang or "auto",
        target_lang=tgt,
        tts=bool(req.tts),
        output_device_name=req.output_device_name,
    )

@app.post("/voice/clear_users")
def voice_clear_users():
    return voice_engine_instance.clear_tracked_users()

@app.post("/voice/speaking")
def voice_speaking_event(req: VoiceSpeakingEventRequest):
    res = voice_engine_instance.notify_user_speaking(
        user_id=req.user_id,
        speaking=req.speaking,
        username=req.username,
    )
    return res or {"ok": True}

@app.post("/voice/translate_chunk")
def voice_translate_chunk(req: VoiceAudioChunkRequest):
    if not req.audio_b64:
        raise HTTPException(status_code=400, detail="Missing audio_b64")
    return voice_engine_instance.translate_audio_chunk(
        user_id=req.user_id,
        audio_b64=req.audio_b64,
        sample_rate=req.sample_rate or 16000,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        username=req.username,
    )

@app.get("/voice/captions")
def voice_get_captions(since_seq: int = 0):
    return {"captions": voice_engine_instance.get_captions_since(since_seq)}


