"""
Real-time per-user voice transcription and translation engine.

Shares the existing CTranslate2 runtime and TranslationEngine (including Russian slang
normalization in `ru_slang.py`). Supports two audio capture modes:
  1. Direct PCM/WAV chunks posted from the DiscordVoiceTranslator plugin (WebAudio capture), OR
  2. Windows WASAPI system loopback capture demuxed by Discord `SPEAKING` start/stop events
     for the selected user IDs.

When at least one user is actively being voice-translated, this module can optionally boost
the backend process priority to NORMAL and allocate 4 CPU threads so transcription stays real-time,
and automatically restores BELOW_NORMAL gaming priority when no users are being tracked.
"""
import base64
import io
import os
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from .config import load_config
from .engine import engine_instance
from .priority import apply_thread_limits, set_process_priority

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    import pyaudiowpatch as pyaudio
    WASAPI_AVAILABLE = True
except ImportError:
    WASAPI_AVAILABLE = False


class VoiceTranslatorEngine:
    """
    Manages per-user voice translation sessions, Whisper STT model lifecycle,
    and WASAPI loopback / WebAudio chunk transcription.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.whisper_model: Optional[Any] = None
        self.whisper_model_size: str = "base"
        self.is_loading: bool = False
        self.load_error: Optional[str] = None

        # Tracked users: { user_id: { "username": str, "source_lang": str, "target_lang": str, "tts": bool } }
        self.tracked_users: Dict[str, Dict[str, Any]] = {}

        # Active speaking buffers per user (for WASAPI loopback demux or chunk assembly)
        self.speaking_state: Dict[str, Dict[str, Any]] = {}

        # Recent translated captions ring buffer (for polling or WebSocket broadcast)
        self.recent_captions: List[Dict[str, Any]] = []
        self._caption_seq: int = 0
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

        # WASAPI loopback background thread
        self._loopback_thread: Optional[threading.Thread] = None
        self._loopback_running: bool = False
        self._boosted_priority: bool = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "whisper_available": WHISPER_AVAILABLE,
            "wasapi_available": WASAPI_AVAILABLE,
            "whisper_loaded": self.whisper_model is not None,
            "whisper_model_size": self.whisper_model_size,
            "is_loading": self.is_loading,
            "load_error": self.load_error,
            "tracked_users": self.tracked_users,
            "boosted_priority": self._boosted_priority,
        }

    def _sync_priority_for_voice(self) -> None:
        """
        Boosts CPU priority/threads while actively translating a user's voice,
        and restores low-priority gaming mode when idle.
        """
        cfg = load_config()
        has_active_users = len(self.tracked_users) > 0
        if has_active_users and not self._boosted_priority:
            set_process_priority("NORMAL")
            apply_thread_limits(max(4, cfg.get("max_cpu_threads", 2)))
            self._boosted_priority = True
        elif not has_active_users and self._boosted_priority:
            priority_level = "BELOW_NORMAL" if cfg.get("gaming_mode", True) else cfg.get("process_priority", "NORMAL")
            set_process_priority(priority_level)
            apply_thread_limits(cfg.get("max_cpu_threads", 2))
            self._boosted_priority = False

    def ensure_whisper_loaded(self, model_size: Optional[str] = None) -> bool:
        if not WHISPER_AVAILABLE:
            self.load_error = "faster-whisper is not installed in .venv"
            return False

        target_size = model_size or self.whisper_model_size or "base"
        if self.whisper_model is not None and self.whisper_model_size == target_size:
            return True

        with self.lock:
            if self.whisper_model is not None and self.whisper_model_size == target_size:
                return True
            self.is_loading = True
            self.load_error = None
            try:
                cfg = load_config()
                device = cfg.get("device", "cpu")
                compute_type = "int8" if device == "cpu" else cfg.get("compute_type", "int8")
                models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "whisper")
                os.makedirs(models_dir, exist_ok=True)

                print(f"[VoiceEngine] Loading faster-whisper '{target_size}' ({compute_type}) on {device}...")
                self.whisper_model = WhisperModel(
                    target_size,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=4,
                    download_root=models_dir,
                )
                self.whisper_model_size = target_size
                self.is_loading = False
                print(f"[VoiceEngine] faster-whisper '{target_size}' ready.")
                return True
            except Exception as e:
                self.load_error = str(e)
                self.is_loading = False
                print(f"[VoiceEngine] Failed to load faster-whisper: {e}")
                return False

    # ------------------------------------------------------------------
    # Per-User Tracking Management
    # ------------------------------------------------------------------
    def set_tracked_user(
        self,
        user_id: str,
        enabled: bool,
        username: str = "User",
        source_lang: str = "ru",
        target_lang: str = "en",
        tts: bool = True,
    ) -> Dict[str, Any]:
        user_id = str(user_id)
        if enabled:
            self.tracked_users[user_id] = {
                "user_id": user_id,
                "username": username or f"User-{user_id[-4:]}",
                "source_lang": (source_lang or "auto").lower(),
                "target_lang": (target_lang or "en").lower(),
                "tts": bool(tts),
            }
            self._sync_priority_for_voice()
            if WASAPI_AVAILABLE and not self._loopback_running:
                self._start_wasapi_loopback()
        else:
            self.tracked_users.pop(user_id, None)
            self.speaking_state.pop(user_id, None)
            self._sync_priority_for_voice()
            if not self.tracked_users:
                self._stop_wasapi_loopback()

        return self.get_status()

    def clear_tracked_users(self) -> Dict[str, Any]:
        self.tracked_users.clear()
        self.speaking_state.clear()
        self._sync_priority_for_voice()
        self._stop_wasapi_loopback()
        return self.get_status()

    # ------------------------------------------------------------------
    # Speaking Demux Events (used with WASAPI Loopback)
    # ------------------------------------------------------------------
    def notify_user_speaking(self, user_id: str, speaking: bool, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Called by the Discord plugin whenever Discord dispatches a `SPEAKING` event
        for a tracked user. Slices the WASAPI loopback buffer for that user's utterance.
        """
        user_id = str(user_id)
        if user_id not in self.tracked_users:
            return None

        if username:
            self.tracked_users[user_id]["username"] = username

        state = self.speaking_state.get(user_id)
        if speaking:
            if not state or not state.get("active"):
                self.speaking_state[user_id] = {
                    "active": True,
                    "started_at": time.time(),
                    "frames": [],
                }
            return None
        else:
            if not state or not state.get("active"):
                return None
            state["active"] = False
            frames = state.get("frames", [])
            state["frames"] = []
            if not frames:
                return None
            pcm_16k = np.concatenate(frames, axis=0)
            # Ignore very short mic clicks (<0.35s at 16kHz)
            if len(pcm_16k) < int(16000 * 0.35):
                return None
            threading.Thread(
                target=self._process_utterance_numpy,
                args=(user_id, pcm_16k),
                daemon=True,
            ).start()
            return {"queued": True, "samples": int(len(pcm_16k))}

    # ------------------------------------------------------------------
    # Direct Audio Chunk API (WebAudio / MediaRecorder from Discord Renderer)
    # ------------------------------------------------------------------
    def translate_audio_chunk(
        self,
        user_id: str,
        audio_b64: str,
        sample_rate: int = 16000,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Accepts base64-encoded 16-bit PCM (or WAV) audio from the plugin for a specific user,
        runs Whisper STT -> NLLB + Russian slang translation, and emits a caption event.
        """
        user_id = str(user_id)
        user_cfg = self.tracked_users.get(user_id, {})
        src_lang = (source_lang or user_cfg.get("source_lang") or "auto").lower()
        tgt_lang = (target_lang or user_cfg.get("target_lang") or "en").lower()
        uname = username or user_cfg.get("username") or f"User-{user_id[-4:]}"

        raw_bytes = base64.b64decode(audio_b64)
        pcm_f32 = self._decode_to_float32_16k(raw_bytes, sample_rate)
        if len(pcm_f32) < int(16000 * 0.3):
            return {"skipped": True, "reason": "audio too short"}

        return self._transcribe_and_translate(
            user_id=user_id,
            username=uname,
            pcm_16k=pcm_f32,
            source_lang=src_lang,
            target_lang=tgt_lang,
        )

    def _decode_to_float32_16k(self, raw_bytes: bytes, sample_rate: int) -> np.ndarray:
        # Check if WAV header is present
        if raw_bytes[:4] == b"RIFF":
            with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                if channels > 1:
                    pcm = pcm.reshape(-1, channels).mean(axis=1)
        else:
            pcm = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if sample_rate != 16000 and len(pcm) > 0:
            duration = len(pcm) / float(sample_rate)
            target_len = int(duration * 16000)
            if target_len > 0:
                pcm = np.interp(
                    np.linspace(0.0, 1.0, target_len, endpoint=False),
                    np.linspace(0.0, 1.0, len(pcm), endpoint=False),
                    pcm,
                ).astype(np.float32)
        return pcm

    def _process_utterance_numpy(self, user_id: str, pcm_16k: np.ndarray) -> None:
        user_cfg = self.tracked_users.get(user_id)
        if not user_cfg:
            return
        self._transcribe_and_translate(
            user_id=user_id,
            username=user_cfg.get("username", "User"),
            pcm_16k=pcm_16k,
            source_lang=user_cfg.get("source_lang", "auto"),
            target_lang=user_cfg.get("target_lang", "en"),
        )

    def _transcribe_and_translate(
        self,
        user_id: str,
        username: str,
        pcm_16k: np.ndarray,
        source_lang: str,
        target_lang: str,
    ) -> Dict[str, Any]:
        # Skip near-silent buffers
        rms = float(np.sqrt(np.mean(np.square(pcm_16k)))) if len(pcm_16k) else 0.0
        if rms < 0.004:
            return {"skipped": True, "reason": "silence"}

        if not self.ensure_whisper_loaded():
            return {"error": self.load_error or "Whisper model unavailable"}

        whisper_lang = None if source_lang in ("auto", "", "und") else source_lang.split("-")[0]

        try:
            segments, info = self.whisper_model.transcribe(
                pcm_16k,
                language=whisper_lang,
                task="transcribe",
                beam_size=2,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            transcript = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
            detected_lang = (info.language if info and getattr(info, "language", None) else (whisper_lang or "auto"))
        except Exception as e:
            return {"error": f"Transcription error: {e}"}

        if not transcript or len(transcript) < 2:
            return {"skipped": True, "reason": "empty transcript"}

        # Translate via the shared NLLB + Russian slang engine so colloquialisms are handled!
        eff_source = detected_lang if source_lang == "auto" else source_lang
        if eff_source == target_lang:
            translated_text = transcript
        else:
            mt_res = engine_instance.translate_text(
                text=transcript,
                source_lang=eff_source,
                target_lang=target_lang,
                mode="deep_thought",
            )
            translated_text = mt_res.get("translated_text") or transcript

        self._caption_seq += 1
        event = {
            "seq": self._caption_seq,
            "timestamp": time.time(),
            "user_id": user_id,
            "username": username,
            "source_lang": eff_source,
            "target_lang": target_lang,
            "original_text": transcript,
            "translated_text": translated_text,
            "tts": bool(self.tracked_users.get(user_id, {}).get("tts", True)),
        }
        self.recent_captions.append(event)
        if len(self.recent_captions) > 50:
            self.recent_captions = self.recent_captions[-50:]

        for cb in list(self._listeners):
            try:
                cb(event)
            except Exception:
                pass

        return event

    def get_captions_since(self, since_seq: int = 0) -> List[Dict[str, Any]]:
        return [c for c in self.recent_captions if c["seq"] > since_seq]

    # ------------------------------------------------------------------
    # Windows WASAPI Loopback Capture (zero-config fallback)
    # ------------------------------------------------------------------
    def _start_wasapi_loopback(self) -> None:
        if not WASAPI_AVAILABLE or self._loopback_running:
            return
        self._loopback_running = True
        self._loopback_thread = threading.Thread(target=self._wasapi_loop, daemon=True)
        self._loopback_thread.start()

    def _stop_wasapi_loopback(self) -> None:
        self._loopback_running = False

    def _wasapi_loop(self) -> None:
        p = None
        stream = None
        try:
            p = pyaudio.PyAudio()
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers.get("isLoopbackDevice"):
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            rate = int(default_speakers["defaultSampleRate"])
            channels = int(default_speakers["maxInputChannels"]) or 2
            chunk_frames = int(rate * 0.1)  # 100ms slices

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                frames_per_buffer=chunk_frames,
                input=True,
                input_device_index=default_speakers["index"],
            )
            print(f"[VoiceEngine] WASAPI loopback active on '{default_speakers['name']}' ({rate}Hz, {channels}ch)")

            while self._loopback_running and self.tracked_users:
                raw = stream.read(chunk_frames, exception_on_overflow=False)
                active_ids = [uid for uid, st in self.speaking_state.items() if st.get("active")]
                if not active_ids:
                    continue

                pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if channels > 1:
                    pcm = pcm.reshape(-1, channels).mean(axis=1)
                if rate != 16000 and len(pcm) > 0:
                    target_len = int(len(pcm) * 16000 / rate)
                    pcm = np.interp(
                        np.linspace(0.0, 1.0, target_len, endpoint=False),
                        np.linspace(0.0, 1.0, len(pcm), endpoint=False),
                        pcm,
                    ).astype(np.float32)

                now = time.time()
                for uid in active_ids:
                    st = self.speaking_state.get(uid)
                    if not st:
                        continue
                    st["frames"].append(pcm)
                    # Flush rolling 4.5s utterances even if user speaks non-stop
                    total_samples = sum(len(f) for f in st["frames"])
                    if total_samples >= 16000 * 4.5:
                        utterance = np.concatenate(st["frames"], axis=0)
                        st["frames"] = []
                        st["started_at"] = now
                        threading.Thread(
                            target=self._process_utterance_numpy,
                            args=(uid, utterance),
                            daemon=True,
                        ).start()

        except Exception as e:
            print(f"[VoiceEngine] WASAPI loopback stopped: {e}")
        finally:
            self._loopback_running = False
            try:
                if stream:
                    stream.stop_stream()
                    stream.close()
                if p:
                    p.terminate()
            except Exception:
                pass


voice_engine_instance = VoiceTranslatorEngine()
