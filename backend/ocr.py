import os
import io
import re
import base64
import hashlib
import threading
import requests
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont

from .engine import engine_instance


# Cache OCR results by image content hash + target_lang to avoid redundant computation
OCR_CACHE: Dict[str, Dict[str, Any]] = {}

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "ocr")


class ImageOCREngine:
    """
    Multilingual, gamer-friendly offline OCR & in-place image translator.
    Uses lightweight ONNX Runtime models (RapidOCR + PaddleOCR multilingual recognizers)
    supporting Russian/Cyrillic, Japanese, Chinese, Korean, and European languages on CPU,
    with Windows native OCR as a fallback.
    """

    _lock = threading.Lock()
    _recognizers: Dict[str, Any] = {}
    _models_checked = False

    @classmethod
    def _ensure_models_downloaded(cls) -> Dict[str, Tuple[str, str]]:
        """Ensures multilingual ONNX recognizer models (eslav, cjk, korean, latin) exist locally."""
        os.makedirs(MODELS_DIR, exist_ok=True)
        paths: Dict[str, Tuple[str, str]] = {}

        # 1. East Slavic (Russian, Ukrainian, Belarusian + English)
        eslav_m = os.path.join(MODELS_DIR, "languages", "eslav", "rec.onnx")
        eslav_k = os.path.join(MODELS_DIR, "languages", "eslav", "dict.txt")
        # 2. Unified CJK + Japanese (Hiragana/Katakana/Kanji + Chinese + English)
        cjk_m = os.path.join(MODELS_DIR, "languages", "cjk", "PP-OCRv5_mobile_rec.onnx")
        cjk_k = os.path.join(MODELS_DIR, "languages", "cjk", "ppocrv5_dict.txt")
        # 3. Korean
        ko_m = os.path.join(MODELS_DIR, "languages", "korean", "rec.onnx")
        ko_k = os.path.join(MODELS_DIR, "languages", "korean", "dict.txt")
        # 4. Latin (Spanish, French, German, Portuguese, Italian, English)
        lat_m = os.path.join(MODELS_DIR, "languages", "latin", "rec.onnx")
        lat_k = os.path.join(MODELS_DIR, "languages", "latin", "dict.txt")

        if not cls._models_checked:
            cls._models_checked = True
            try:
                from huggingface_hub import hf_hub_download
                if not (os.path.exists(eslav_m) and os.path.exists(eslav_k)):
                    hf_hub_download("monkt/paddleocr-onnx", "languages/eslav/rec.onnx", local_dir=MODELS_DIR)
                    hf_hub_download("monkt/paddleocr-onnx", "languages/eslav/dict.txt", local_dir=MODELS_DIR)
                if not (os.path.exists(cjk_m) and os.path.exists(cjk_k)):
                    cjk_dir = os.path.join(MODELS_DIR, "languages", "cjk")
                    os.makedirs(cjk_dir, exist_ok=True)
                    hf_hub_download("nathanfhh/PaddleOCR-ONNX", "PP-OCRv5_mobile_rec.onnx", local_dir=cjk_dir)
                    hf_hub_download("nathanfhh/PaddleOCR-ONNX", "ppocrv5_dict.txt", local_dir=cjk_dir)
                if not (os.path.exists(ko_m) and os.path.exists(ko_k)):
                    hf_hub_download("monkt/paddleocr-onnx", "languages/korean/rec.onnx", local_dir=MODELS_DIR)
                    hf_hub_download("monkt/paddleocr-onnx", "languages/korean/dict.txt", local_dir=MODELS_DIR)
                if not (os.path.exists(lat_m) and os.path.exists(lat_k)):
                    hf_hub_download("monkt/paddleocr-onnx", "languages/latin/rec.onnx", local_dir=MODELS_DIR)
                    hf_hub_download("monkt/paddleocr-onnx", "languages/latin/dict.txt", local_dir=MODELS_DIR)
            except Exception as e:
                print(f"[OCR] Model check warning: {e}")

        if os.path.exists(eslav_m) and os.path.exists(eslav_k):
            paths["eslav"] = (eslav_m, eslav_k)
        if os.path.exists(cjk_m) and os.path.exists(cjk_k):
            paths["cjk"] = (cjk_m, cjk_k)
        if os.path.exists(ko_m) and os.path.exists(ko_k):
            paths["korean"] = (ko_m, ko_k)
        if os.path.exists(lat_m) and os.path.exists(lat_k):
            paths["latin"] = (lat_m, lat_k)
        return paths

    @classmethod
    def _get_recognizer(cls, key: str):
        with cls._lock:
            if key in cls._recognizers:
                return cls._recognizers[key]
            from rapidocr_onnxruntime import RapidOCR
            paths = cls._ensure_models_downloaded()
            if key in paths:
                rec_m, rec_k = paths[key]
                ocr = RapidOCR(rec_model_path=rec_m, rec_keys_path=rec_k)
            else:
                ocr = RapidOCR()
            cls._recognizers[key] = ocr
            return ocr

    @classmethod
    def fetch_image(cls, image_url_or_data: str) -> Optional[Image.Image]:
        try:
            if image_url_or_data.startswith("data:image"):
                header, encoded = image_url_or_data.split(",", 1)
                data = base64.b64decode(encoded)
                return Image.open(io.BytesIO(data)).convert("RGB")
            elif image_url_or_data.startswith("http://") or image_url_or_data.startswith("https://"):
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                }
                resp = requests.get(image_url_or_data, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return Image.open(io.BytesIO(resp.content)).convert("RGB")
                # Fallback: if media.discordapp.net failed or returned 404/403, try cdn.discordapp.com
                if "media.discordapp.net" in image_url_or_data:
                    alt_url = image_url_or_data.replace("media.discordapp.net", "cdn.discordapp.com").split("?")[0]
                    resp2 = requests.get(alt_url, headers=headers, timeout=15)
                    if resp2.status_code == 200:
                        return Image.open(io.BytesIO(resp2.content)).convert("RGB")
            else:
                return Image.open(image_url_or_data).convert("RGB")
        except Exception as e:
            print(f"[OCR] Failed to load image from {image_url_or_data[:80]}...: {e}")
            return None
        return None

    @classmethod
    def get_image_hash(cls, img: Image.Image) -> str:
        with io.BytesIO() as buf:
            img.save(buf, format="PNG")
            return hashlib.md5(buf.getvalue()).hexdigest()

    @staticmethod
    def _has_non_ascii_letters(text: str) -> bool:
        return any(ord(ch) > 127 and ch.isalpha() for ch in text)

    @classmethod
    def _run_multilingual_ocr(
        cls,
        img: Image.Image,
        source_lang: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        Runs multilingual OCR and returns a list of regions:
        [{"box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "text": str, "score": float}]
        """
        arr = np.array(img)
        src = (source_lang or "auto").lower().split("-")[0]

        # Order recognizers by likelihood based on source_lang hint
        if src in ("ru", "uk", "be"):
            candidates = ["eslav", "cjk"]
        elif src in ("ja", "zh"):
            candidates = ["cjk", "eslav"]
        elif src == "ko":
            candidates = ["korean", "cjk"]
        elif src in ("es", "fr", "de", "pt", "it", "en"):
            candidates = ["latin", "cjk"]
        else:
            candidates = ["eslav", "cjk", "korean", "latin"]

        try:
            best_regions: List[Dict[str, Any]] = []
            best_score = -1.0

            for key in candidates:
                ocr = cls._get_recognizer(key)
                raw_res, _ = ocr(arr)
                if not raw_res:
                    continue

                regions = []
                total_conf = 0.0
                non_ascii_bonus = 0.0
                for item in raw_res:
                    box, text, conf = item[0], str(item[1]).strip(), float(item[2])
                    if not text or conf < 0.40:
                        continue
                    regions.append({"box": box, "text": text, "score": conf})
                    total_conf += conf
                    if cls._has_non_ascii_letters(text):
                        non_ascii_bonus += 0.04

                if not regions:
                    continue

                avg_score = (total_conf / len(regions)) + min(0.12, non_ascii_bonus)
                if avg_score > best_score:
                    best_score = avg_score
                    best_regions = regions

                # Early exit if confidence is already very high and matches target script
                if avg_score >= 0.92 and (src != "auto" or cls._has_non_ascii_letters(" ".join(r["text"] for r in regions))):
                    break

            return cls._merge_horizontal_regions(best_regions)
        except Exception as e:
            print(f"[OCR] RapidOCR fallback to winocr due to: {e}")

        # Fallback to Windows OCR if RapidOCR unavailable
        try:
            import winocr
            ocr_res = winocr.recognize_pil_sync(img)
            txt = ocr_res.get("text", "").strip()
            if txt:
                w, h = img.size
                return [{"box": [[10, 10], [w - 10, 10], [w - 10, h - 10], [10, h - 10]], "text": txt, "score": 0.8}]
        except Exception as e:
            print(f"[OCR] winocr fallback error: {e}")
        return []

    @staticmethod
    def _merge_horizontal_regions(regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges word/phrase boxes that sit on the same horizontal text line so full sentences
        are translated together with complete context and rendered cleanly in one box.
        """
        if len(regions) <= 1:
            return regions

        items = []
        for r in regions:
            pts = r["box"]
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            h = max(8.0, y2 - y1)
            cy = (y1 + y2) / 2.0
            items.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "h": h, "cy": cy,
                "text": r["text"],
                "score": r["score"],
            })

        items.sort(key=lambda it: (it["cy"], it["x1"]))
        lines: List[List[Dict[str, Any]]] = []
        for it in items:
            placed = False
            for line in lines:
                ref_cy = sum(x["cy"] for x in line) / len(line)
                ref_h = sum(x["h"] for x in line) / len(line)
                if abs(it["cy"] - ref_cy) <= 0.65 * min(it["h"], ref_h):
                    line.append(it)
                    placed = True
                    break
            if not placed:
                lines.append([it])

        merged: List[Dict[str, Any]] = []
        for line in lines:
            line.sort(key=lambda x: x["x1"])
            cur = dict(line[0])
            for nxt in line[1:]:
                gap = nxt["x1"] - cur["x2"]
                max_gap = 2.8 * max(cur["h"], nxt["h"])
                if gap <= max_gap:
                    cur["x1"] = min(cur["x1"], nxt["x1"])
                    cur["y1"] = min(cur["y1"], nxt["y1"])
                    cur["x2"] = max(cur["x2"], nxt["x2"])
                    cur["y2"] = max(cur["y2"], nxt["y2"])
                    cur["h"] = cur["y2"] - cur["y1"]
                    cur["cy"] = (cur["y1"] + cur["y2"]) / 2.0
                    cur["text"] = f"{cur['text']} {nxt['text']}".strip()
                    cur["score"] = (cur["score"] + nxt["score"]) / 2.0
                else:
                    merged.append({
                        "box": [[cur["x1"], cur["y1"]], [cur["x2"], cur["y1"]], [cur["x2"], cur["y2"]], [cur["x1"], cur["y2"]]],
                        "text": cur["text"],
                        "score": cur["score"],
                    })
                    cur = dict(nxt)
            merged.append({
                "box": [[cur["x1"], cur["y1"]], [cur["x2"], cur["y1"]], [cur["x2"], cur["y2"]], [cur["x1"], cur["y2"]]],
                "text": cur["text"],
                "score": cur["score"],
            })

        return merged

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont:
        size = max(11, min(64, int(size)))
        for font_path in (
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/msgothic.ttc",
        ):
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    @classmethod
    def _render_translated_image(cls, img: Image.Image, regions: List[Dict[str, Any]]) -> str:
        """
        Draws translated text directly over the detected foreign text bounding boxes
        and returns a base64 data:image/png URL.
        """
        canvas = img.copy().convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        arr = np.array(img)
        img_h, img_w = arr.shape[:2]

        for reg in regions:
            translated = (reg.get("translated_text") or "").strip()
            orig = (reg.get("text") or "").strip()
            if not translated:
                continue

            pts = reg["box"]
            xs = [int(p[0]) for p in pts]
            ys = [int(p[1]) for p in pts]
            x1 = max(0, min(xs) - 2)
            y1 = max(0, min(ys) - 2)
            x2 = min(img_w, max(xs) + 2)
            y2 = min(img_h, max(ys) + 2)
            box_w = max(24, x2 - x1)
            box_h = max(16, y2 - y1)

            # Sample border pixels to estimate local background color
            crop = arr[y1:y2, x1:x2]
            if crop.size > 0:
                border_pixels = np.concatenate([
                    crop[0, :, :],
                    crop[-1, :, :],
                    crop[:, 0, :],
                    crop[:, -1, :]
                ], axis=0)
                med = np.median(border_pixels, axis=0).astype(int)
                bg_r, bg_g, bg_b = int(med[0]), int(med[1]), int(med[2])
            else:
                bg_r, bg_g, bg_b = 28, 30, 35

            luminance = 0.299 * bg_r + 0.587 * bg_g + 0.114 * bg_b
            if luminance < 145:
                fill_rgba = (max(0, bg_r - 12), max(0, bg_g - 12), max(0, bg_b - 12), 235)
                text_rgba = (255, 255, 255, 255)
                stroke_rgba = (0, 0, 0, 220)
            else:
                fill_rgba = (min(255, bg_r + 12), min(255, bg_g + 12), min(255, bg_b + 12), 235)
                text_rgba = (15, 15, 18, 255)
                stroke_rgba = (255, 255, 255, 220)

            draw.rounded_rectangle([x1, y1, x2, y2], radius=4, fill=fill_rgba)

            # Fit font size so translated string fits inside [x1, y1, x2, y2]
            target_font_size = max(11, int(box_h * 0.72))
            font = cls._load_font(target_font_size)
            while target_font_size > 11:
                bbox = draw.textbbox((0, 0), translated, font=font)
                tw = bbox[2] - bbox[0]
                if tw <= box_w - 6:
                    break
                target_font_size -= 2
                font = cls._load_font(target_font_size)

            bbox = draw.textbbox((0, 0), translated, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x1 + max(2, (box_w - tw) // 2)
            ty = y1 + max(1, (box_h - th) // 2) - bbox[1]

            draw.text(
                (tx, ty),
                translated,
                font=font,
                fill=text_rgba,
                stroke_width=1,
                stroke_fill=stroke_rgba,
            )

        combined = Image.alpha_composite(canvas, overlay).convert("RGB")
        with io.BytesIO() as out_buf:
            combined.save(out_buf, format="PNG", optimize=True)
            b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"

    @classmethod
    def process_and_translate(
        cls,
        image_source: str,
        target_lang: str = "en",
        source_lang: str = "auto",
    ) -> Dict[str, Any]:
        """
        Extracts text from an image, translates each text region & the full text,
        and renders an in-place translated image data URL.
        """
        img = cls.fetch_image(image_source)
        if not img:
            return {"error": "Could not fetch or open image", "text": "", "translated_text": "", "has_text": False}

        img_hash = f"{cls.get_image_hash(img)}:{source_lang}:{target_lang}"
        if img_hash in OCR_CACHE:
            return OCR_CACHE[img_hash]

        try:
            regions = cls._run_multilingual_ocr(img, source_lang=source_lang)
            if not regions:
                result = {
                    "text": "",
                    "translated_text": "",
                    "has_text": False,
                    "target_lang": target_lang,
                }
                OCR_CACHE[img_hash] = result
                return result

            extracted_lines = [r["text"] for r in regions if r.get("text")]
            extracted_text = "\n".join(extracted_lines).strip()
            if not extracted_text:
                return {"text": "", "translated_text": "", "has_text": False, "target_lang": target_lang}

            # Translate each merged line with full sentence context
            translated_lines: List[str] = []
            detected_src = "auto"

            for r in regions:
                line_txt = r["text"]
                tr = engine_instance.translate_text(
                    text=line_txt,
                    source_lang=source_lang if source_lang != "auto" else "auto",
                    target_lang=target_lang,
                    mode="deep_thought",
                )
                tr_text = (tr.get("translated_text") or line_txt).strip()
                if tr.get("source_lang") and tr.get("source_lang") not in ("auto", "und", "unknown"):
                    detected_src = tr["source_lang"]
                r["translated_text"] = tr_text
                translated_lines.append(tr_text)

            full_translated = "\n".join(translated_lines).strip()
            translated_image_data_url = cls._render_translated_image(img, regions)

            result = {
                "text": extracted_text,
                "translated_text": full_translated,
                "translated_image_data_url": translated_image_data_url,
                "source_lang": detected_src,
                "target_lang": target_lang,
                "has_text": True,
                "regions_count": len(regions),
            }
            OCR_CACHE[img_hash] = result
            return result

        except Exception as e:
            print(f"[OCR] Error during recognition: {e}")
            return {"error": str(e), "text": "", "translated_text": "", "has_text": False}
