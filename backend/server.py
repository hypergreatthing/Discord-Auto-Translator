from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .config import load_config, save_config
from .engine import engine_instance
from .ocr import ImageOCREngine
from .priority import set_process_priority, apply_thread_limits

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
