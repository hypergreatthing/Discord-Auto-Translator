import io
import hashlib
import requests
from typing import Dict, Any, Optional
from PIL import Image

from .engine import engine_instance


# Cache OCR results by image content hash (MD5) to avoid redundant computation
OCR_CACHE: Dict[str, Dict[str, Any]] = {}

class ImageOCREngine:
    """
    Lightweight, gamer-friendly OCR engine using Windows 10/11 native APIs.
    Consumes zero extra GPU VRAM and caches image hashes.
    """

    @classmethod
    def fetch_image(cls, image_url_or_data: str) -> Optional[Image.Image]:
        try:
            if image_url_or_data.startswith("data:image"):
                # Handle base64 data URLs
                import base64
                header, encoded = image_url_or_data.split(",", 1)
                data = base64.b64decode(encoded)
                return Image.open(io.BytesIO(data))
            elif image_url_or_data.startswith("http://") or image_url_or_data.startswith("https://"):
                # Discord CDN attachment image
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(image_url_or_data, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return Image.open(io.BytesIO(resp.content))
            else:
                # Local file path
                return Image.open(image_url_or_data)
        except Exception as e:
            print(f"[OCR] Failed to load image from {image_url_or_data[:60]}...: {e}")
            return None

    @classmethod
    def get_image_hash(cls, img: Image.Image) -> str:
        with io.BytesIO() as buf:
            img.save(buf, format="PNG")
            return hashlib.md5(buf.getvalue()).hexdigest()

    @classmethod
    def process_and_translate(
        cls,
        image_source: str,
        target_lang: str = "en"
    ) -> Dict[str, Any]:
        """
        Extracts text from image and translates it to target language.
        """
        img = cls.fetch_image(image_source)
        if not img:
            return {"error": "Could not fetch or open image", "text": "", "translated_text": ""}

        img_hash = cls.get_image_hash(img)
        if img_hash in OCR_CACHE:
            cached = OCR_CACHE[img_hash]
            if cached.get("target_lang") == target_lang:
                return cached

        try:
            import winocr
        except ImportError:
            return {"error": "Windows OCR is not available on this platform", "text": "", "translated_text": ""}

        try:
            # Run fast native Windows OCR
            ocr_res = winocr.recognize_pil_sync(img)
            extracted_text = ocr_res.get("text", "").strip()

            if not extracted_text:
                result = {
                    "text": "",
                    "translated_text": "",
                    "has_text": False,
                    "target_lang": target_lang
                }
                OCR_CACHE[img_hash] = result
                return result

            # Translate extracted text
            translation_res = engine_instance.translate_text(
                text=extracted_text,
                source_lang="auto",
                target_lang=target_lang
            )

            result = {
                "text": extracted_text,
                "translated_text": translation_res.get("translated_text", ""),
                "source_lang": translation_res.get("source_lang", "unknown"),
                "target_lang": target_lang,
                "has_text": True
            }
            OCR_CACHE[img_hash] = result
            return result

        except Exception as e:
            print(f"[OCR] Error during recognition: {e}")
            return {"error": str(e), "text": "", "translated_text": ""}
