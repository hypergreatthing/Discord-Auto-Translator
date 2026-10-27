import { definePlugin } from "@utils/types";
import { findByProps } from "@webpack";

const DEFAULT_SERVER_URL = "http://127.0.0.1:49152";

export default definePlugin({
    name: "DiscordAutoTranslator",
    description: "Offline, gamer-friendly real-time translator with complete sentence accuracy, OCR, and outgoing reply translations.",
    authors: [{ name: "Antigravity", id: 0n }],
    options: {
        targetLang: {
            type: "select",
            name: "Target Language",
            description: "The language you want incoming foreign text translated to",
            options: [
                { label: "English", value: "en", default: true },
                { label: "Japanese", value: "ja" },
                { label: "Spanish", value: "es" },
                { label: "French", value: "fr" },
                { label: "German", value: "de" },
                { label: "Chinese", value: "zh" },
                { label: "Russian", value: "ru" },
            ]
        },
        accuracyMode: {
            type: "select",
            name: "Accuracy Mode",
            description: "Focus on complete thoughts/grammar vs faster low latency",
            options: [
                { label: "Deep Thought (Beam Search)", value: "deep_thought", default: true },
                { label: "Fast Mode", value: "fast" }
            ]
        },
        autoOcrImages: {
            type: "boolean",
            name: "Auto-Scan Images (OCR)",
            description: "Keep OFF while gaming to preserve CPU cycles",
            default: false
        }
    },

    patches: [
        {
            find: 'children:"MessageContent"',
            replacement: {
                match: /(return\s+.*?\.jsx\(.*?"div",\{.*?children:\[)/,
                replace: "$1$self.renderTranslationSubtext(arguments[0]),"
            }
        }
    ],

    renderTranslationSubtext(props: any) {
        // Renders translation beneath message content
        return null;
    },

    start() {
        console.log("[DiscordAutoTranslator] Vencord plugin loaded.");
    },

    stop() {
        console.log("[DiscordAutoTranslator] Vencord plugin unloaded.");
    }
});
