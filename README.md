# 🌐 Discord Auto Translator (Gamer-Friendly Offline AI)

An offline, open-source real-time auto-translation system built specifically for Discord users and gamers. It ensures **complete sentence and thought accuracy**, displays translations **inline directly beneath foreign messages**, performs **image OCR and link preview translations**, and allows you to **auto-translate outgoing replies back to the channel's foreign language**.

---

## ⚡ Key Highlights & Gamer-Friendly Optimizations

- **🎮 Zero Gaming Lag (Low Process Priority):**
  - Runs at `BELOW_NORMAL` or `IDLE` priority via Windows native scheduler APIs.
  - Automatically caps AI inference to 2 CPU worker threads so your games (CS2, Valorant, Warzone, Apex, etc.) maintain 100% core access and zero frame stutter.
- **🧠 Complete Thoughts & Sentence Integrity (Not Word-by-Word):**
  - Powered by **CTranslate2 INT8** with **Meta's NLLB-200** (No Language Left Behind) model across 200+ languages.
  - Context-aware **Sentence Boundary Detection (SBD)** splits complex thoughts into natural semantic sentences.
  - **Beam Search Decoding (Beam Width: 4)** evaluates full sentence hypotheses to ensure natural grammar, idioms, and colloquial flow.
  - **Discord Token Masking** ensures mentions (`<@123>`), custom emojis (`<:pepe:456>`), channel links (`<#general>`), and code blocks are never altered or corrupted during translation.
- **🖼️ Image OCR & Embed Translation:**
  - Uses Windows 10/11 hardware-accelerated native OCR (`Windows.Media.Ocr`), consuming **zero additional GPU VRAM** and **zero extra model weight**.
  - **On-Demand OCR button** over image attachments (or toggleable Auto-Scan) with content hash caching so the same image is never scanned twice.
  - Translates link preview embeds inline.
- **💬 Auto-Translate Outgoing Responses:**
  - Click the `🌐` button on the chat bar (or press `Alt + T`) to automatically translate what you type into the channel's active foreign language before sending.
  - Optional **Bilingual Outgoing Mode** (sends both the translated foreign text and your original in parentheses).

---

## 📁 Project Architecture

```
discord auto translator/
├── backend/
│   ├── main.py            # Daemon entry point (starts server + system tray)
│   ├── engine.py          # CTranslate2 NLLB-200 offline translation engine
│   ├── segmenter.py       # Multi-language Sentence Boundary Detector
│   ├── masker.py          # Discord mention/emoji/link token protector
│   ├── ocr.py             # Windows native hardware OCR with image caching
│   ├── priority.py        # Windows process priority & thread affinity manager
│   ├── server.py          # FastAPI REST API (http://127.0.0.1:49152)
│   ├── tray.py            # Windows System Tray app (Gaming mode toggle)
│   └── config.py          # Config loader and persistence
├── plugins/
│   ├── betterdiscord/
│   │   └── DiscordAutoTranslator.plugin.js  # Drop-in BetterDiscord plugin
│   └── vencord/
│       └── index.tsx                        # Vencord userplugin source
├── tests/
│   └── test_components.py # Verification unit test suite
└── start_translator.bat   # One-click Windows launcher
```

---

## 📥 Download

1. Go to the [**Releases**](https://github.com/hypergreatthing/Discord-Auto-Translator/releases) page and download the latest `DiscordAutoTranslator-vX.Y.Z.zip`.
2. **Right-click the ZIP → Extract All...** and pick a permanent folder (e.g. `Documents`). Don't run it from inside the ZIP.
3. Open the extracted folder and double-click **`Easy_Install.bat`** (details below).

> The first time the translator starts, it downloads the ~600 MB AI translation model once. After that it works fully offline.

---

## 🚀 One-Click Easy Install (For Anyone)

Just double-click:
```bat
Easy_Install.bat
```
This automated setup wizard handles everything automatically:
1. **Detects BetterDiscord** and copies the plugin file directly to `%APPDATA%\BetterDiscord\plugins\`. (Prompts with a download link if BetterDiscord is missing).
2. **Checks Python** and auto-installs Python 3.12 via Windows `winget` if missing.
3. **Creates an isolated environment** (`.venv`) and installs all required neural translation & OCR dependencies.
4. **Creates a Desktop Shortcut** (`Discord Auto Translator`) with silent background startup (no annoying black console window!).
5. **Prompts for Windows Startup** so it can launch seamlessly in the system tray when Windows boots.

*(To cleanly uninstall anytime, double-click `Uninstall.bat`)*

---

### Manual Launching Options

- **Silent Launch (System Tray Only):** Double-click `start_silent.vbs` (or use the Desktop shortcut).
- **Console Debug Launch:** Double-click `start_translator.bat` (shows debug logs).

#### For Vencord:
If using Vencord, add `plugins/vencord/index.tsx` to your userplugins directory and build.

---

## 🎮 System Tray Controls

Right-click the `🌐` icon in your Windows System Tray (near the clock):

| Menu Item | Description |
| :--- | :--- |
| **🎮 Gaming Mode (Low CPU Priority)** | Checked by default. Lowers process priority to `BELOW_NORMAL` / `IDLE` and caps CPU cores to 2. |
| **Quality: Deep Thought** | Uses multi-sentence segmentation + Beam Search (width 4) for optimal grammar. |
| **Quality: Fast Mode** | Uses greedy decoding for instantaneous, low-latency casual chat. |
| **Auto-Scan All Images (OCR)** | Keep unchecked for gaming (allows clicking "Translate Image" on demand). |
| **API Documentation & Status** | Opens `http://127.0.0.1:49152/docs` in your browser. |
| **Quit** | Gracefully stops the background server and unloads models. |

---

## ⚙️ Plugin In-Chat Features

1. **Inline Translation Under Messages:**
   Foreign text automatically gets translated and displayed directly below the original message in a sleek, non-intrusive container:
   ```
   User: こんにちは！今日のレイドは何時からですか？
   ↳ 🌐 JA → EN • Deep Thought  [📋 Copy]
     Hello! What time does today's raid start?
   ```
2. **Translate Images (OCR):**
   Hovering over any image attachment shows a `🌐 Translate Image` button. Clicking it scans and translates the image in real time.
3. **Outgoing Auto-Reply:**
   Click the `🌐` icon on the left of the chat input box (or press `Alt + T`). When enabled, typing a response in English will automatically be translated to Japanese/Spanish/etc. when sent!

---

## 📱 Translating Discord on Phones (Android & iOS)

> **Important:** This project's plugin and translation engine only work on **Windows desktop Discord**.
> They do **not** run on phones. The backend only listens on `127.0.0.1` (this PC), so phones cannot connect to it.
>
> The guides below use tools **built into the phone** (or Google's own apps). They do **not** modify, patch, or
> inject anything into the Discord app, so there's no ban risk from Discord client modding.

### Quick Comparison

| Method | Platform | Effort per message | Works offline* | Translates in place on screen |
| :--- | :--- | :--- | :--- | :--- |
| Google Translate **Tap to Translate** | Android | Copy message → tap bubble | Yes | No (shows popup) |
| **Circle to Search** → Translate | Android (supported phones) | Long-press nav bar → Translate | No | **Yes** (whole screen) |
| Google **Lens** screenshot | Android | Screenshot → Lens → Translate | Partly | Yes (on screenshot) |
| **Translate shortcut** (clipboard) | iOS | Copy message → Back Tap | Yes | No (shows popup) |
| **Screenshot shortcut** (OCR) | iOS | Back Tap only | Yes | No (shows popup) |
| **Live Text** in Photos | iOS | Screenshot → Photos → Translate | Yes | Yes (on screenshot) |

\*Offline only after you download the language packs (steps below).

---

### 🤖 Android: Screen Overlay Methods

#### Option A — Google Translate "Tap to Translate" (recommended, works on almost any Android)

A small floating bubble appears over Discord whenever you copy text. Tap it to see the translation.

**One-time setup:**
1. Install **Google Translate** from the Play Store (often preinstalled).
2. Open Google Translate → tap your **profile picture** (top right) → **Settings** → **Tap to Translate**.
3. Turn on **Use Tap to Translate**. When asked, allow **"Display over other apps"**.
4. *(Optional, for offline use)* In Google Translate → profile picture → **Downloaded languages** → download the languages your servers use (e.g. Russian, Japanese) and **English**.

**Daily use in Discord:**
1. **Long-press** a foreign message → tap **Copy Text**.
2. The **Translate bubble** appears on the edge of your screen → tap it.
3. The translation pops up over Discord. Tap outside it to go back.

**Replying in their language:** Type your reply in the Translate popup (switch the language direction), tap **Copy**, then paste into Discord.

> Tip: On Android 13+, copying text also shows a small clipboard preview in the corner with a **Translate** suggestion — that works too.

#### Option B — Circle to Search (translates the whole screen in place)

Available on many recent phones (e.g. Google Pixel 6 and newer, Samsung Galaxy S23/S24 and newer, and others — check your phone).

1. With a Discord channel open, **long-press the home button or the navigation bar** at the bottom of the screen.
2. Tap the **Translate** icon (the "文A" symbol).
3. Every message on the screen is **replaced in place with translated text**, keeping the layout.
4. Scroll? Close and repeat — it translates one screen at a time.

> Needs an internet connection. If you don't see Translate, update the **Google** app.

#### Option C — Google Lens on a screenshot (fallback for any phone)

1. Take a **screenshot** of the Discord chat.
2. Open it in **Google Photos** → tap **Lens** → **Translate**.
3. The translated text is drawn over the screenshot.

> ⚠️ **About third-party "screen translator" apps** (floating bubble apps from the Play Store):
> they work, but most need **Accessibility** or **screen recording** permission and send your screen to their
> cloud servers. Only use them if you trust the developer. The Google options above don't need those permissions.

---

### 🍎 iOS (iPhone/iPad): Stock iOS Methods

No sideloading, no modded Discord. Uses Apple's built-in **Translate** app and **Shortcuts** app.

**One-time setup (all options):**
1. Make sure the **Translate** app is installed (it ships with iOS; re-download from the App Store if deleted).
2. Open **Settings** → **Apps** → **Translate** (on older iOS: **Settings** → **Translate**) → **Downloaded Languages** →
   download the languages your servers use plus **English**.
3. Turn on **On-Device Mode** there if you want everything to stay private and work offline.

#### Option A — "Translate Clipboard" Shortcut + Back Tap (recommended)

Copy a message, tap the back of your phone twice, and the translation pops up.

**Create the shortcut:**
1. Open the **Shortcuts** app → tap **+** (top right).
2. Tap **Add Action**, search for and add these actions in order:
   1. **Get Clipboard**
   2. **Translate Text** — tap the language field and set *To* = **English** (leave *From* as **Detect Language**)
   3. **Show Result** (or **Quick Look**)
3. Tap the name at the top → rename it **Translate Discord** → **Done**.

**Bind it to Back Tap:**
1. **Settings** → **Accessibility** → **Touch** → **Back Tap** → **Double Tap**.
2. Scroll down to **Shortcuts** → choose **Translate Discord**.

*(iPhone 15 Pro and newer: you can instead assign it to the **Action Button** in **Settings** → **Action Button** → **Shortcut**.)*

**Daily use in Discord:**
1. **Long-press** a foreign message → **Copy Text**.
2. **Double-tap the back** of your iPhone → the translation appears.

**Replying:** Make a second shortcut the same way but set *To* = the other language (e.g. **Russian**) and replace
**Show Result** with **Copy to Clipboard**. Type your reply, select all → copy, double-tap/run it, then paste into Discord.

#### Option B — "Translate Screen" Shortcut (no copying needed)

Reads the text straight off your screen.

1. Create a new shortcut with these actions in order:
   1. **Take Screenshot**
   2. **Extract Text from Image** (set input to the screenshot)
   3. **Translate Text** → *To* = **English**
   4. **Quick Look**
2. Name it **Translate Screen** and assign it to **Back Tap → Triple Tap** (same steps as above).

Now, with any Discord channel open, **triple-tap the back** of your phone to translate everything visible.

> Note: This grabs *all* text on screen (usernames, timestamps, channel names too), so the output is a bit messier
> than Option A — but it's faster for reading a whole conversation.

#### Option C — Live Text in Photos (translation drawn over the image)

1. Take a **screenshot** of the Discord chat → tap the thumbnail (or open it in **Photos**).
2. Tap the **Live Text** icon (a small box with lines, bottom right) → tap **Translate**.
3. The translated text is overlaid directly on the screenshot.

---

### What you won't get on mobile (compared to the desktop plugin)

- ❌ Automatic translations under every message (you have to trigger each one)
- ❌ Auto-translated outgoing replies (you copy/paste instead)
- ❌ Translated channel names, categories, and member roles in the sidebars
- ❌ Discord custom emoji preservation in translated text
- ✅ Everything above works with the **official, unmodified Discord app**
