import os
import re
import json
import urllib.request
import urllib.parse
import threading
from typing import Dict, Any, List, Optional, Tuple
import langdetect
import regex

# langdetect is non-deterministic by default (same text can yield different languages run-to-run).
langdetect.DetectorFactory.seed = 0

try:
    import ctranslate2
    from transformers import NllbTokenizerFast, AutoTokenizer
    from huggingface_hub import snapshot_download
    CT2_AVAILABLE = True
except ImportError:
    CT2_AVAILABLE = False

try:
    import sentencepiece as spm
    SPM_AVAILABLE = True
except ImportError:
    SPM_AVAILABLE = False

from .segmenter import SentenceSegmenter
from .masker import DiscordMasker
from .ru_slang import normalize_ru
from .config import load_config

# Map common ISO-639-1 language codes to NLLB-200 language tokens
NLLB_LANG_MAP = {
    "en": "eng_Latn",
    "ja": "jpn_Jpan",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",  # langdetect's code for Simplified Chinese
    "zh-tw": "zho_Hant",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ru": "rus_Cyrl",
    "ko": "kor_Hang",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "ar": "arb_Arab",
    "hi": "hin_Deva",
    "vi": "vie_Latn",
    "th": "tha_Thai",
    "id": "ind_Latn",
    "pl": "pol_Latn",
    "nl": "nld_Latn",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "sv": "swe_Latn",
    "cs": "ces_Latn",
    "el": "ell_Grek",
    "he": "heb_Hebr",
}

DEFAULT_MODEL_REPO = "Tushe/nllb-200-600M-ct2-int8"
OPUS_RU_EN_REPO = "jiangzhuo9357/opus-mt-ru-en-ct2"
OPUS_EN_RU_REPO = "jiangzhuo9357/opus-mt-en-ru-ct2"
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


class TranslationEngine:
    """
    Hybrid Offline/Online Neural Machine Translation engine:
    - Russian <-> English Option 1 (Default, "opus_mt"): Dedicated Helsinki-NLP OPUS-MT RU<->EN
      CTranslate2 specialist + expanded Russian Slang & Modern Euphemisms normalizer.
    - Russian <-> English Option 2 ("google_gtx"): Free Google Translate GTX endpoint + Russian
      Slang & Modern Euphemisms normalizer, with automatic offline fallback to Option 1.
    - All 200+ other languages: Meta NLLB-200 CTranslate2 INT8 with full Sentence Boundary Detection.
    """

    def __init__(self):
        self.config = load_config()
        self.lock = threading.Lock()
        self.translator: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model_path = os.path.join(MODELS_DIR, "nllb-200-600m-int8")
        self.is_loading = False
        self.load_error: Optional[str] = None
        self.is_ready = False

        # Dedicated Russian <-> English OPUS-MT CTranslate2 specialist models
        self.opus_lock = threading.Lock()
        self.opus_models: Dict[str, Dict[str, Any]] = {}

    def get_status(self) -> Dict[str, Any]:
        self.config = load_config()
        return {
            "is_ready": self.is_ready,
            "is_loading": self.is_loading,
            "model_downloaded": os.path.exists(self.model_path),
            "opus_ru_en_downloaded": os.path.exists(os.path.join(MODELS_DIR, "opus-mt-ru-en", "model.bin")),
            "load_error": self.load_error,
            "device": self.config.get("device", "cpu"),
            "accuracy_mode": self.config.get("accuracy_mode", "deep_thought"),
            "ru_translation_engine": self.config.get("ru_translation_engine", "opus_mt"),
        }

    def set_ru_engine(self, engine_name: str) -> str:
        if engine_name in ("opus_mt", "google_gtx", "nllb"):
            self.config["ru_translation_engine"] = engine_name
        return self.config.get("ru_translation_engine", "opus_mt")

    def ensure_model_downloaded(self, progress_callback=None) -> str:
        """Downloads the int8 quantized NLLB model (~620MB) if not already present."""
        os.makedirs(MODELS_DIR, exist_ok=True)
        if not os.path.exists(os.path.join(self.model_path, "model.bin")):
            print(f"[Engine] Downloading offline model from {DEFAULT_MODEL_REPO} to {self.model_path}...")
            snapshot_download(
                repo_id=DEFAULT_MODEL_REPO,
                local_dir=self.model_path,
                local_dir_use_symlinks=False
            )
            print("[Engine] Offline model download complete.")
        return self.model_path

    def _get_opus_specialist(self, direction: str) -> Optional[Dict[str, Any]]:
        """
        Loads (and auto-downloads if needed) the dedicated OPUS-MT CTranslate2 model
        for 'ru-en' or 'en-ru'.
        """
        if not CT2_AVAILABLE or not SPM_AVAILABLE:
            return None

        with self.opus_lock:
            if direction in self.opus_models:
                return self.opus_models[direction]

            repo = OPUS_RU_EN_REPO if direction == "ru-en" else OPUS_EN_RU_REPO
            local_dir = os.path.join(MODELS_DIR, f"opus-mt-{direction}")
            os.makedirs(local_dir, exist_ok=True)

            try:
                if not os.path.exists(os.path.join(local_dir, "model.bin")):
                    print(f"[Engine] Downloading dedicated Russian specialist model ({repo})...")
                    snapshot_download(repo_id=repo, local_dir=local_dir, local_dir_use_symlinks=False)

                device = self.config.get("device", "cpu")
                threads = max(2, int(self.config.get("max_cpu_threads", 2)))
                translator = ctranslate2.Translator(
                    local_dir,
                    device=device,
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=threads,
                )
                sp_src = spm.SentencePieceProcessor(model_file=os.path.join(local_dir, "source.spm"))
                sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(local_dir, "target.spm"))

                bundle = {"translator": translator, "sp_src": sp_src, "sp_tgt": sp_tgt}
                self.opus_models[direction] = bundle
                print(f"[Engine] Dedicated OPUS-MT ({direction}) specialist loaded and ready!")
                return bundle
            except Exception as e:
                print(f"[Engine] OPUS-MT ({direction}) load warning, falling back to NLLB: {e}")
                return None

    def load_model(self) -> bool:
        if self.is_ready:
            return True

        with self.lock:
            if self.is_ready:
                return True
            self.is_loading = True
            self.load_error = None

            try:
                if not CT2_AVAILABLE:
                    raise RuntimeError("ctranslate2 or transformers package not available")

                self.ensure_model_downloaded()

                device = self.config.get("device", "cpu")
                compute_type = self.config.get("compute_type", "int8")
                threads = self.config.get("max_cpu_threads", 2)

                print(f"[Engine] Loading CTranslate2 model on device: {device} ({compute_type}) with {threads} threads...")

                self.translator = ctranslate2.Translator(
                    self.model_path,
                    device=device,
                    compute_type=compute_type,
                    inter_threads=1,
                    intra_threads=threads
                )

                try:
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path,
                        src_lang="eng_Latn",
                        local_files_only=True,
                    )
                except Exception:
                    try:
                        self.tokenizer = NllbTokenizerFast.from_pretrained(
                            "facebook/nllb-200-distilled-600M",
                            local_files_only=True,
                        )
                    except Exception:
                        self.tokenizer = NllbTokenizerFast.from_pretrained(
                            "facebook/nllb-200-distilled-600M"
                        )

                self.is_ready = True
                self.is_loading = False
                print("[Engine] Translation engine loaded and ready!")
                return True

            except Exception as e:
                self.is_loading = False
                self.load_error = str(e)
                print(f"[Engine] Failed to load model: {e}")
                return False

    # Characters from scripts that are never English.
    _NON_LATIN_SCRIPT = re.compile(
        r"[\u0370-\u03FF\u0400-\u04FF\u0500-\u052F\u0590-\u05FF\u0600-\u06FF\u0900-\u097F"
        r"\u0E00-\u0E7F\u1100-\u11FF\u3040-\u30FF\u3130-\u318F\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]"
    )
    _ACCENTED_LATIN = re.compile(r"[\u00C0-\u00FF\u0100-\u024F]")

    _ENGLISH_WORDS = frozenset("""
        about after again all also always any anyone are around as at away back be because been
        before being best better big both but by came can cant could day did didnt do does doesnt doing
        done dont down each even ever every first for from get gets getting give go goes going gone good got
        great had has have he her here him his how i if im into is isnt it its ive just know last later let
        lets like little long look lot made make many may more most much must my need never new next not
        nothing now of off ok okay once one only other our out over people please put really right said
        same say see she should since some someone something soon still such sure take than thank thanks that
        thats the their them then there these they thing things think this those though time to today tomorrow
        tonight too try two up us use very want way we well went were what when where which while who why
        with without wont work would yeah yes yet you your youre yours
        hi hello hey bye yo sup thx ty tysm pls plz np nvm idk idc imo imho tbh btw brb afk gg wp ggwp glhf gl hf
        lol lmao lmfao rofl omg omfg wtf wth smh fr ngl irl dm dms rn ikr jk lmk wyd hbu ez op nerf buff
        noob nub pog poggers kek xd haha hahaha hehe lul k kk yep yup nope nah cool nice dude bro
        guys guy true false mood raid boss server channel online offline game play playing join ready
    """.split())

    def detect_language(self, text: str) -> str:
        clean = re.sub(r"https?://\S+|<[^>]+>|:[\w\-~]+:|@\S+|\[[^\]]*\]", " ", text)
        clean = re.sub(r"[\d\W_]+", " ", clean).strip()
        if len(clean) < 2:
            return "und"

        if self._NON_LATIN_SCRIPT.search(clean):
            try:
                return langdetect.detect(clean)
            except Exception:
                return "und"

        words = clean.lower().split()
        has_accents = bool(self._ACCENTED_LATIN.search(clean))

        if not has_accents and words:
            english_hits = sum(1 for w in words if w in self._ENGLISH_WORDS)
            if english_hits / len(words) >= 0.6:
                return "en"

        try:
            candidates = langdetect.detect_langs(clean)
        except Exception:
            return "und"
        if not candidates:
            return "und"
        best = candidates[0]

        min_prob = 0.80 if has_accents else 0.95
        min_words = 2 if has_accents else 3
        if best.prob >= min_prob and len(words) >= min_words:
            return best.lang
        return "und"

    def to_nllb_lang(self, lang_code: str) -> str:
        code_clean = lang_code.lower().strip()
        return NLLB_LANG_MAP.get(code_clean, "eng_Latn")

    @staticmethod
    def _translate_via_google_gtx(text: str, src_lang: str, tgt_lang: str) -> Optional[str]:
        """
        Free keyless Google Translate GTX endpoint (Option 2 for Russian).
        Returns None on network error so the caller can automatically fall back to Option 1 (offline OPUS-MT).
        """
        try:
            params = urllib.parse.urlencode({
                "client": "gtx",
                "sl": src_lang,
                "tl": tgt_lang,
                "dt": "t",
                "q": text,
            })
            url = f"https://translate.googleapis.com/translate_a/single?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data, list) and data[0]:
                    return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
        except Exception as e:
            print(f"[Engine] Google GTX fallback to offline OPUS-MT: {e}")
        return None

    def _translate_tasks_opus(
        self,
        batch_tasks: List[Dict[str, Any]],
        direction: str,
        use_ru_slang: bool,
        beam_size: int,
    ) -> bool:
        """
        Translates `batch_tasks` using the dedicated OPUS-MT CTranslate2 specialist ('ru-en' or 'en-ru')
        with full Sentence Boundary Detection so multi-sentence messages never truncate.
        """
        bundle = self._get_opus_specialist(direction)
        if not bundle:
            return False

        sp_src = bundle["sp_src"]
        sp_tgt = bundle["sp_tgt"]
        translator = bundle["translator"]

        flat_sentences: List[List[str]] = []
        task_slices: List[Tuple[int, int]] = []

        for task in batch_tasks:
            raw = normalize_ru(task["content"]) if use_ru_slang else task["content"]
            sents = SentenceSegmenter.split_sentences(raw)
            if not sents:
                sents = [raw]
            start_idx = len(flat_sentences)
            for s in sents:
                flat_sentences.append(sp_src.encode(s, out_type=str) + ["</s>"])
            task_slices.append((start_idx, len(flat_sentences)))

        if not flat_sentences:
            return True

        results = translator.translate_batch(
            flat_sentences,
            beam_size=beam_size,
            max_decoding_length=256,
            repetition_penalty=1.15,
        )

        for task, (s_idx, e_idx) in zip(batch_tasks, task_slices):
            decoded_sents = []
            for r in results[s_idx:e_idx]:
                hyp = [tok for tok in r.hypotheses[0] if tok != "</s>"]
                decoded = sp_tgt.decode(hyp).strip()
                if decoded:
                    decoded_sents.append(decoded)
            task["translated"] = " ".join(decoded_sents).strip()

        return True

    def translate_text(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "en",
        mode: Optional[str] = None,
        ru_engine: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Translates text with full sentence preservation, context awareness,
        and Discord token protection.
        """
        if not text or not text.strip():
            return {"translated_text": text, "source_lang": source_lang or "en", "target_lang": target_lang}

        try:
            import emoji
            text = emoji.emojize(text, language="alias")
        except Exception:
            pass

        if not source_lang or source_lang == "auto":
            source_lang = self.detect_language(text)

        def skip(reason: str) -> Dict[str, Any]:
            return {
                "translated_text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "skipped": True,
                "skip_reason": reason,
            }

        if source_lang == "und":
            return skip("language undetermined")

        src_base = source_lang.lower().strip().split("-")[0]
        tgt_base = target_lang.lower().strip().split("-")[0]

        if src_base == tgt_base:
            return skip("already in target language")

        if source_lang.lower().strip() not in NLLB_LANG_MAP:
            return skip(f"unsupported source language '{source_lang}'")
        if self.to_nllb_lang(source_lang) == self.to_nllb_lang(target_lang):
            return skip("source and target map to the same model language")

        accuracy_mode = mode or self.config.get("accuracy_mode", "deep_thought")
        beam_size = self.config.get("beam_size", 4) if accuracy_mode == "deep_thought" else 1
        active_ru_engine = ru_engine or self.config.get("ru_translation_engine", "opus_mt")

        # Regex recognizing Unicode emojis, Discord custom emojis, mentions, links, and code blocks
        icon_pattern = regex.compile(
            r"(\p{Extended_Pictographic}(?:[\ufe0e\ufe0f]|\p{Emoji_Modifier}|\u200d\p{Extended_Pictographic})*|"
            r"<a?:[\w\-]+:\d+>|"
            r":[\w\-]+:|"
            r"<@!?\d+>|"
            r"<@&\d+>|"
            r"<#\d+>|"
            r"https?://\S+|"
            r"```[\s\S]*?```|"
            r"`[^`]+`)"
        )

        lines = text.split("\n")
        line_structures = []
        batch_tasks = []

        for line in lines:
            if not line.strip():
                line_structures.append([])
                continue

            parts = icon_pattern.split(line)
            current_line_tokens = []

            for part in parts:
                if not part:
                    continue

                if icon_pattern.fullmatch(part.strip()):
                    current_line_tokens.append({"type": "verbatim", "content": part})
                elif part.strip():
                    leading_ws = part[:len(part) - len(part.lstrip())]
                    trailing_ws = part[len(part.rstrip()):]
                    trimmed = part.strip()

                    bullet_prefix = ""
                    for b in ["- ", "* ", "• ", "> ", "1. ", "2. ", "3. ", "4. ", "5. "]:
                        if trimmed.startswith(b):
                            bullet_prefix = b
                            trimmed = trimmed[len(b):]
                            break

                    if trimmed:
                        token_entry = {
                            "type": "translatable",
                            "leading": leading_ws,
                            "bullet": bullet_prefix,
                            "content": trimmed,
                            "trailing": trailing_ws,
                            "translated": trimmed
                        }
                        current_line_tokens.append(token_entry)
                        batch_tasks.append(token_entry)
                    else:
                        current_line_tokens.append({"type": "verbatim", "content": part})
                else:
                    current_line_tokens.append({"type": "verbatim", "content": part})

            line_structures.append(current_line_tokens)

        used_engine_label = accuracy_mode

        if batch_tasks:
            use_ru_slang = (src_base == "ru" and self.config.get("ru_slang_normalize", True))
            is_ru_en_pair = (src_base == "ru" and tgt_base == "en") or (src_base == "en" and tgt_base == "ru")
            direction = "ru-en" if src_base == "ru" else "en-ru"

            handled = False

            # --- Russian Specialist Routing (Option 1: OPUS-MT Offline, Option 2: Google GTX + Offline Fallback) ---
            if is_ru_en_pair:
                if active_ru_engine == "google_gtx":
                    all_ok = True
                    for task in batch_tasks:
                        norm_content = normalize_ru(task["content"]) if use_ru_slang else task["content"]
                        gtx_res = self._translate_via_google_gtx(norm_content, src_base, tgt_base)
                        if gtx_res:
                            task["translated"] = gtx_res
                        else:
                            all_ok = False
                            break
                    if all_ok:
                        handled = True
                        used_engine_label = "google_gtx"

                if not handled and active_ru_engine in ("opus_mt", "google_gtx"):
                    if self._translate_tasks_opus(batch_tasks, direction, use_ru_slang, beam_size):
                        handled = True
                        used_engine_label = "opus_mt"

            # --- General 200-Language NLLB-200 Fallback (with full Sentence Boundary Detection) ---
            if not handled:
                if not self.is_ready:
                    success = self.load_model()
                    if not success:
                        return {
                            "error": f"Model failed to load: {self.load_error}",
                            "translated_text": text,
                            "source_lang": source_lang,
                            "target_lang": target_lang
                        }

                src_nllb = self.to_nllb_lang(source_lang)
                tgt_nllb = self.to_nllb_lang(target_lang)

                with self.lock:
                    self.tokenizer.src_lang = src_nllb
                    flat_tokenized: List[List[str]] = []
                    task_slices: List[Tuple[int, int]] = []

                    for task in batch_tasks:
                        raw = normalize_ru(task["content"]) if use_ru_slang else task["content"]
                        sents = (SentenceSegmenter.split_sentences(raw) or [raw]) if len(raw) > 80 else [raw]
                        s_idx = len(flat_tokenized)
                        for s in sents:
                            flat_tokenized.append(
                                self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(s))
                            )
                        task_slices.append((s_idx, len(flat_tokenized)))

                    target_prefix = [[tgt_nllb]] * len(flat_tokenized)
                    results = self.translator.translate_batch(
                        flat_tokenized,
                        target_prefix=target_prefix,
                        beam_size=beam_size,
                        max_decoding_length=256,
                        repetition_penalty=1.2,
                        length_penalty=1.0 if accuracy_mode == "deep_thought" else 0.6
                    )

                    for task, (s_idx, e_idx) in zip(batch_tasks, task_slices):
                        decoded_sents = []
                        for res in results[s_idx:e_idx]:
                            hyp = res.hypotheses[0]
                            if hyp and hyp[0] == tgt_nllb:
                                hyp = hyp[1:]
                            decoded = self.tokenizer.decode(
                                self.tokenizer.convert_tokens_to_ids(hyp),
                                skip_special_tokens=True
                            ).strip()
                            if decoded:
                                decoded_sents.append(decoded)
                        task["translated"] = " ".join(decoded_sents).strip()

        reconstructed_lines = []
        for line_tokens in line_structures:
            if not line_tokens:
                reconstructed_lines.append("")
                continue

            assembled_line = []
            for entry in line_tokens:
                if entry["type"] == "verbatim":
                    assembled_line.append(entry["content"])
                else:
                    assembled_line.append(f"{entry['leading']}{entry['bullet']}{entry['translated']}{entry['trailing']}")
            reconstructed_lines.append("".join(assembled_line))

        final_text = "\n".join(reconstructed_lines)

        def _norm(s: str) -> str:
            return re.sub(r"[\W_]+", "", s).lower()
        if _norm(final_text) == _norm(text):
            return skip("translation identical to original")

        return {
            "original_text": text,
            "translated_text": final_text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "accuracy_mode": used_engine_label,
            "sentences_count": len(batch_tasks)
        }


engine_instance = TranslationEngine()
