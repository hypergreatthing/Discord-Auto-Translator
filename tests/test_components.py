import unittest
import os
import sys
import psutil
from PIL import Image, ImageDraw

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.priority import set_process_priority, apply_thread_limits
from backend.masker import DiscordMasker
from backend.segmenter import SentenceSegmenter
from backend.config import load_config, save_config
from backend.ocr import ImageOCREngine

class TestTranslatorCore(unittest.TestCase):

    def test_priority_control(self):
        """Verify Windows process priority can be lowered for gaming."""
        success = set_process_priority("BELOW_NORMAL")
        self.assertTrue(success)
        proc = psutil.Process(os.getpid())
        self.assertEqual(proc.nice(), psutil.BELOW_NORMAL_PRIORITY_CLASS)

        # Test switching to IDLE
        success_idle = set_process_priority("IDLE")
        self.assertTrue(success_idle)
        self.assertEqual(proc.nice(), psutil.IDLE_PRIORITY_CLASS)

        # Switch back to BELOW_NORMAL
        set_process_priority("BELOW_NORMAL")

    def test_discord_token_masking(self):
        """Verify Discord mentions, channels, emojis, and URLs are protected."""
        raw = "Hey <@123456789>, check out <#987654321> and this link https://discord.com! <:pepe:112233>"
        masked, placeholders = DiscordMasker.mask(raw)

        self.assertNotIn("<@123456789>", masked)
        self.assertNotIn("https://discord.com", masked)
        self.assertNotIn("<:pepe:112233>", masked)

        unmasked = DiscordMasker.unmask(masked, placeholders)
        self.assertEqual(unmasked, raw)

    def test_sentence_segmenter_complete_thoughts(self):
        """Verify complete sentence boundaries are preserved without breaking on abbreviations."""
        text = "Hello Dr. Smith! The match starts at 3.15 p.m. Are you ready? We need to win today."
        sentences = SentenceSegmenter.split_sentences(text)

        # Four complete thought units
        self.assertEqual(len(sentences), 4)
        self.assertIn("Hello Dr. Smith!", sentences[0])
        self.assertIn("The match starts at 3.15 p.m.", sentences[1])
        self.assertIn("Are you ready?", sentences[2])
        self.assertIn("We need to win today.", sentences[3])

    def test_windows_native_ocr(self):
        """Verify Windows native OCR can extract text from an image."""
        img = Image.new("RGBA", (400, 150), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((30, 40), "TRANSLATOR TEST", fill=(0, 0, 0))

        temp_img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ocr.png")
        img.save(temp_img_path)

        try:
            result = ImageOCREngine.process_and_translate(temp_img_path, target_lang="en")
            extracted = result.get("text", "").upper()
            self.assertTrue("TRANSLATOR" in extracted or "TEST" in extracted)
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    def test_offline_neural_translation(self):
        """Verify offline neural translation translates full sentence thoughts."""
        from backend.engine import engine_instance
        res = engine_instance.translate_text("こんにちは！元気ですか？", target_lang="en")
        self.assertEqual(res.get("target_lang"), "en")
        translated = res.get("translated_text", "").lower()
        print(f"\n[Test Result] -> '{res.get('translated_text')}'")
        self.assertTrue("hello" in translated or "how are you" in translated or "good" in translated)

if __name__ == "__main__":
    unittest.main()
