/**
 * @name DiscordVoiceTranslator
 * @author Antigravity
 * @description Real-time per-user voice translator for Discord voice channels. Right-click any user in a voice channel (or use the voice bar) to translate their spoken language into your default language with live captions and optional TTS voice dubbing. Shares the local companion backend.
 * @version 0.1.0
 * @source https://github.com/hypergreatthing/Discord-Auto-Translator
 * @updateUrl https://raw.githubusercontent.com/hypergreatthing/Discord-Auto-Translator/main/plugins/betterdiscord/DiscordVoiceTranslator.plugin.js
 */

module.exports = class DiscordVoiceTranslator {
    constructor() {
        this.version = "0.1.0";
        this.updateUrl = "https://raw.githubusercontent.com/hypergreatthing/Discord-Auto-Translator/main/plugins/betterdiscord/DiscordVoiceTranslator.plugin.js";
        this.defaultSettings = {
            targetLang: "en",
            defaultSourceLang: "ru",
            enableSubtitles: true,
            enableTts: true,
            duckOriginalVolume: true,
            duckedVolumePercent: 20,   // Lower original speaker volume to 20% when TTS dubbing is on
            ttsVolume: 0.9,
            ttsRate: 1.05,
            subtitleDurationSec: 8,
            autoUpdate: true,
            serverUrl: "http://127.0.0.1:49152"
        };
        this.settings = Object.assign({}, this.defaultSettings);

        // { [userId]: { userId, username, sourceLang, tts, originalVolume } }
        this.trackedUsers = new Map();
        this.speakingState = new Map(); // userId -> boolean
        this.lastCaptionSeq = 0;

        this.backendOnline = false;
        this.keepAliveTimer = null;
        this.captionPollTimer = null;
        this.uiScanTimer = null;
        this.updateCheckInterval = null;
        this.fluxUnsubscribe = null;
        this.contextMenuHandler = null;
    }

    start() {
        this.loadSettings();
        this.injectStyles();
        this.startKeepAlive();
        this.startAutoUpdater();
        this.hookSpeakingEvents();
        this.hookUserContextMenu();
        this.startCaptionPolling();
        console.log(`[DiscordVoiceTranslator] v${this.version} started.`);
    }

    stop() {
        this.stopKeepAlive();
        this.stopAutoUpdater();
        this.stopCaptionPolling();
        this.unhookSpeakingEvents();
        this.unhookUserContextMenu();
        this.restoreAllUserVolumes();
        if (this.backendOnline) {
            this.fetchWithTimeout("/voice/clear_users", { method: "POST" }, 2000).catch(() => {});
        }
        this.trackedUsers.clear();
        this.speakingState.clear();
        this.removeOverlayElements();
        this.clearStyles();
        console.log("[DiscordVoiceTranslator] Stopped.");
    }

    /* ==========================================================
       Settings Persistence
       ========================================================== */
    loadSettings() {
        try {
            if (typeof BdApi !== "undefined" && BdApi.Data) {
                const saved = BdApi.Data.load("DiscordVoiceTranslator", "settings");
                if (saved) Object.assign(this.settings, saved);
            }
        } catch (e) {
            console.error("[DiscordVoiceTranslator] Failed to load settings:", e);
        }
    }

    saveSettings() {
        try {
            if (typeof BdApi !== "undefined" && BdApi.Data) {
                BdApi.Data.save("DiscordVoiceTranslator", "settings", this.settings);
            }
        } catch (e) {
            console.error("[DiscordVoiceTranslator] Failed to save settings:", e);
        }
    }

    showToast(msg, options = {}) {
        if (typeof BdApi !== "undefined" && BdApi.UI && typeof BdApi.UI.showToast === "function") {
            BdApi.UI.showToast(msg, options);
        } else {
            console.log(`[DiscordVoiceTranslator] ${msg}`);
        }
    }

    getSupportedLanguages() {
        return [
            { code: "auto", name: "⚡ Auto-Detect Spoken Language" },
            { code: "ru", name: "🇷🇺 Russian (ru)" },
            { code: "ja", name: "🇯🇵 Japanese (ja)" },
            { code: "es", name: "🇪🇸 Spanish (es)" },
            { code: "fr", name: "🇫🇷 French (fr)" },
            { code: "de", name: "🇩🇪 German (de)" },
            { code: "zh", name: "🇨🇳 Chinese (zh)" },
            { code: "ko", name: "🇰🇷 Korean (ko)" },
            { code: "pt", name: "🇵🇹 Portuguese (pt)" },
            { code: "it", name: "🇮🇹 Italian (it)" },
            { code: "en", name: "🇺🇸 English (en)" },
        ];
    }

    /* ==========================================================
       Backend Handshake & Keep-Alive
       ========================================================== */
    async fetchWithTimeout(path, options = {}, timeoutMs = 2500) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeoutMs);
        try {
            return await fetch(`${this.settings.serverUrl}${path}`, Object.assign({}, options, { signal: ctrl.signal }));
        } finally {
            clearTimeout(timer);
        }
    }

    setBackendOnline(online) {
        if (this.backendOnline === online) return;
        this.backendOnline = online;
        if (online) {
            // Re-sync any tracked users with the backend when it comes online
            for (const u of this.trackedUsers.values()) {
                this.syncTrackedUserWithBackend(u, true);
            }
        }
        this.updateStatusPill();
    }

    async performHandshake() {
        try {
            const resp = await this.fetchWithTimeout("/handshake", {}, 2000);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.service !== "discord-auto-translator" || !data.ready) throw new Error("Unexpected service");
            this.setBackendOnline(true);
            return true;
        } catch (_) {
            this.setBackendOnline(false);
            return false;
        }
    }

    async pingBackend() {
        if (!this.backendOnline) return this.performHandshake();
        try {
            const resp = await this.fetchWithTimeout("/ping", {}, 2000);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return true;
        } catch (_) {
            this.setBackendOnline(false);
            return false;
        }
    }

    startKeepAlive() {
        this.stopKeepAlive();
        this.backendOnline = false;
        this.performHandshake();
        const tick = async () => {
            await this.pingBackend();
            this.keepAliveTimer = setTimeout(tick, this.backendOnline ? 10000 : 5000);
        };
        this.keepAliveTimer = setTimeout(tick, 5000);
    }

    stopKeepAlive() {
        if (this.keepAliveTimer) {
            clearTimeout(this.keepAliveTimer);
            this.keepAliveTimer = null;
        }
    }

    /* ==========================================================
       Per-User Voice Tracking & Volume Ducking
       ========================================================== */
    async setUserVoiceTranslation(userId, username, sourceLang, enabled = true) {
        if (!userId) return;
        userId = String(userId);

        if (!this.backendOnline) {
            this.showToast("Translator backend is offline! Start the companion daemon first.", { type: "error" });
            return;
        }

        if (enabled) {
            const existing = this.trackedUsers.get(userId);
            const origVol = existing ? existing.originalVolume : this.getUserLocalVolume(userId);
            const entry = {
                userId,
                username: username || (existing && existing.username) || this.resolveUsername(userId),
                sourceLang: sourceLang || this.settings.defaultSourceLang || "ru",
                tts: !!this.settings.enableTts,
                originalVolume: origVol,
            };
            this.trackedUsers.set(userId, entry);

            if (this.settings.enableTts && this.settings.duckOriginalVolume) {
                this.setUserLocalVolume(userId, this.settings.duckedVolumePercent);
            }

            await this.syncTrackedUserWithBackend(entry, true);
            this.showToast(
                `🎧 Translating ${entry.username}'s voice (${entry.sourceLang.toUpperCase()} → ${this.settings.targetLang.toUpperCase()})`,
                { type: "success" }
            );
        } else {
            const existing = this.trackedUsers.get(userId);
            if (existing && typeof existing.originalVolume === "number") {
                this.setUserLocalVolume(userId, existing.originalVolume);
            }
            this.trackedUsers.delete(userId);
            this.speakingState.delete(userId);
            await this.syncTrackedUserWithBackend({ userId, username }, false);
            this.showToast(`Stopped translating ${username || "user"}'s voice.`, { type: "info" });
        }

        this.updateStatusPill();
        this.decorateVoiceChannelUsers();
    }

    async syncTrackedUserWithBackend(entry, enabled) {
        if (!this.backendOnline) return;
        try {
            await this.fetchWithTimeout("/voice/track_user", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: String(entry.userId),
                    enabled: !!enabled,
                    username: entry.username || "User",
                    source_lang: entry.sourceLang || "auto",
                    target_lang: this.settings.targetLang || "en",
                    tts: !!this.settings.enableTts,
                }),
            }, 4000);
        } catch (err) {
            console.warn("[DiscordVoiceTranslator] Failed to sync tracked user:", err);
        }
    }

    getUserLocalVolume(userId) {
        try {
            if (typeof BdApi !== "undefined" && BdApi.Webpack) {
                const MediaEngineStore = BdApi.Webpack.getStore
                    ? BdApi.Webpack.getStore("MediaEngineStore")
                    : BdApi.Webpack.getByKeys("getLocalVolume");
                if (MediaEngineStore && typeof MediaEngineStore.getLocalVolume === "function") {
                    return MediaEngineStore.getLocalVolume(userId);
                }
            }
        } catch (_) {}
        return 100;
    }

    setUserLocalVolume(userId, volumePercent) {
        try {
            if (typeof BdApi !== "undefined" && BdApi.Webpack) {
                const MediaEngineActions = BdApi.Webpack.getByKeys("setLocalVolume", "toggleLocalMute");
                if (MediaEngineActions && typeof MediaEngineActions.setLocalVolume === "function") {
                    MediaEngineActions.setLocalVolume(userId, volumePercent);
                }
            }
        } catch (_) {}
    }

    restoreAllUserVolumes() {
        for (const [uid, entry] of this.trackedUsers.entries()) {
            if (typeof entry.originalVolume === "number") {
                this.setUserLocalVolume(uid, entry.originalVolume);
            }
        }
    }

    resolveUsername(userId) {
        try {
            if (typeof BdApi !== "undefined" && BdApi.Webpack) {
                const UserStore = BdApi.Webpack.getStore
                    ? BdApi.Webpack.getStore("UserStore")
                    : BdApi.Webpack.getByKeys("getUser", "getCurrentUser");
                if (UserStore && typeof UserStore.getUser === "function") {
                    const u = UserStore.getUser(userId);
                    if (u) return u.globalName || u.username || `User-${String(userId).slice(-4)}`;
                }
            }
        } catch (_) {}
        return `User-${String(userId).slice(-4)}`;
    }

    /* ==========================================================
       Discord SPEAKING Event Hooks (FluxDispatcher + DOM Fallback)
       ========================================================== */
    hookSpeakingEvents() {
        // 1. Hook Discord's internal FluxDispatcher for instant SPEAKING events
        try {
            if (typeof BdApi !== "undefined" && BdApi.Webpack) {
                const Dispatcher = BdApi.Webpack.getByKeys("dispatch", "subscribe");
                if (Dispatcher && typeof Dispatcher.subscribe === "function") {
                    const handler = (event) => {
                        if (!event || !event.userId) return;
                        const uid = String(event.userId);
                        if (!this.trackedUsers.has(uid)) return;
                        const isSpeaking = Boolean(event.speakingFlags && event.speakingFlags > 0);
                        this.handleUserSpeakingChange(uid, isSpeaking);
                    };
                    Dispatcher.subscribe("SPEAKING", handler);
                    this.fluxUnsubscribe = () => {
                        try { Dispatcher.unsubscribe("SPEAKING", handler); } catch (_) {}
                    };
                }
            }
        } catch (err) {
            console.warn("[DiscordVoiceTranslator] FluxDispatcher hook fallback:", err);
        }

        // 2. Periodic DOM & VoiceState fallback + voice user badge decorator
        this.uiScanTimer = setInterval(() => {
            this.decorateVoiceChannelUsers();
            this.pollDomSpeakingIndicators();
        }, 250);
    }

    unhookSpeakingEvents() {
        if (this.fluxUnsubscribe) {
            this.fluxUnsubscribe();
            this.fluxUnsubscribe = null;
        }
        if (this.uiScanTimer) {
            clearInterval(this.uiScanTimer);
            this.uiScanTimer = null;
        }
    }

    handleUserSpeakingChange(userId, isSpeaking) {
        const prev = !!this.speakingState.get(userId);
        if (prev === isSpeaking) return;
        this.speakingState.set(userId, isSpeaking);

        if (!this.backendOnline || !this.trackedUsers.has(userId)) return;
        const entry = this.trackedUsers.get(userId);
        this.fetchWithTimeout("/voice/speaking", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                speaking: isSpeaking,
                username: entry ? entry.username : undefined,
            }),
        }, 2000).catch(() => {});
    }

    pollDomSpeakingIndicators() {
        if (!this.backendOnline || this.trackedUsers.size === 0) return;
        // Fallback if FluxDispatcher wasn't matched: check avatar speaking rings in the voice channel list
        document.querySelectorAll('[class*="voiceUser_"], [data-list-item-id^="voice-user"]').forEach((el) => {
            const uid = el.dataset.dvtUserId;
            if (!uid || !this.trackedUsers.has(uid)) return;
            const avatarSpeaking = !!el.querySelector('[class*="avatarSpeaking_"], [class*="speaking_"]');
            this.handleUserSpeakingChange(uid, avatarSpeaking);
        });
    }

    /* ==========================================================
       Right-Click Context Menu & Voice User Picker UI
       ========================================================== */
    hookUserContextMenu() {
        this.contextMenuHandler = (e) => {
            // Detect right-click on a voice user row or any user element with an avatar
            const target = e.target;
            if (!target || typeof target.closest !== "function") return;

            const voiceRow = target.closest('[class*="voiceUser_"], [class*="user_"][class*="content_"], [data-list-item-id*="voice"]');
            if (!voiceRow) return;

            const userInfo = this.extractUserFromElement(voiceRow);
            if (!userInfo || !userInfo.userId) return;

            // Inject our "Translate Voice" quick menu into Discord's context menu or as a floating popover
            setTimeout(() => this.injectContextMenuItem(userInfo, e.clientX, e.clientY), 40);
        };
        document.addEventListener("contextmenu", this.contextMenuHandler, true);
    }

    unhookUserContextMenu() {
        if (this.contextMenuHandler) {
            document.removeEventListener("contextmenu", this.contextMenuHandler, true);
            this.contextMenuHandler = null;
        }
    }

    extractUserFromElement(el) {
        if (!el) return null;
        // 1. Check cached dataset
        if (el.dataset && el.dataset.dvtUserId) {
            return {
                userId: el.dataset.dvtUserId,
                username: el.dataset.dvtUsername || this.resolveUsername(el.dataset.dvtUserId),
            };
        }
        // 2. Extract user ID from avatar image URL: /avatars/<userId>/...
        const img = el.querySelector('img[src*="/avatars/"], [style*="/avatars/"]');
        if (img) {
            const src = img.src || img.getAttribute("style") || "";
            const m = src.match(/\/avatars\/(\d{15,22})\//);
            if (m) {
                const userId = m[1];
                const nameEl = el.querySelector('[class*="username_"], [class*="name_"]');
                const username = (nameEl && nameEl.textContent.trim()) || this.resolveUsername(userId);
                el.dataset.dvtUserId = userId;
                el.dataset.dvtUsername = username;
                return { userId, username };
            }
        }
        // 3. React fiber fallback
        try {
            const key = Object.keys(el).find((k) => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$"));
            let fiber = key ? el[key] : null;
            let depth = 0;
            while (fiber && depth < 18) {
                const props = fiber.memoizedProps;
                if (props && props.user && props.user.id) {
                    const userId = String(props.user.id);
                    const username = props.user.globalName || props.user.username || this.resolveUsername(userId);
                    el.dataset.dvtUserId = userId;
                    el.dataset.dvtUsername = username;
                    return { userId, username };
                }
                fiber = fiber.return;
                depth++;
            }
        } catch (_) {}
        return null;
    }

    injectContextMenuItem(userInfo, x, y) {
        document.querySelectorAll(".dvt-context-box").forEach((b) => b.remove());

        const isTracked = this.trackedUsers.has(userInfo.userId);
        const currentEntry = this.trackedUsers.get(userInfo.userId);
        const selectedLang = (currentEntry && currentEntry.sourceLang) || this.settings.defaultSourceLang || "ru";

        const box = document.createElement("div");
        box.className = "dvt-context-box";

        const header = document.createElement("div");
        header.className = "dvt-context-title";
        header.textContent = `🎧 Voice Translate: ${userInfo.username}`;
        box.appendChild(header);

        const toggleBtn = document.createElement("button");
        toggleBtn.className = `dvt-context-btn ${isTracked ? "active" : ""}`;
        toggleBtn.textContent = isTracked
            ? `✓ Translating (${selectedLang.toUpperCase()} → ${this.settings.targetLang.toUpperCase()}) — Click to Stop`
            : `▶ Start Translating ${userInfo.username}`;

        const langSelect = document.createElement("select");
        langSelect.className = "dvt-context-select";
        this.getSupportedLanguages().forEach((l) => {
            const opt = document.createElement("option");
            opt.value = l.code;
            opt.textContent = `From: ${l.name}`;
            if (l.code === selectedLang) opt.selected = true;
            langSelect.appendChild(opt);
        });

        toggleBtn.onclick = (ev) => {
            ev.stopPropagation();
            this.setUserVoiceTranslation(userInfo.userId, userInfo.username, langSelect.value, !isTracked);
            box.remove();
        };

        langSelect.onchange = (ev) => {
            ev.stopPropagation();
            this.settings.defaultSourceLang = langSelect.value;
            this.saveSettings();
            if (this.trackedUsers.has(userInfo.userId)) {
                this.setUserVoiceTranslation(userInfo.userId, userInfo.username, langSelect.value, true);
            }
        };

        box.appendChild(toggleBtn);
        box.appendChild(langSelect);

        // Try attaching inside Discord's open context menu if present; otherwise position near cursor
        const menu = document.querySelector('[role="menu"][class*="menu_"]');
        if (menu) {
            menu.appendChild(box);
        } else {
            box.style.position = "fixed";
            box.style.left = `${Math.min(window.innerWidth - 260, Math.max(12, x))}px`;
            box.style.top = `${Math.min(window.innerHeight - 130, Math.max(12, y))}px`;
            document.body.appendChild(box);
            const close = (ev) => {
                if (!box.contains(ev.target)) {
                    box.remove();
                    document.removeEventListener("mousedown", close, true);
                }
            };
            setTimeout(() => document.addEventListener("mousedown", close, true), 50);
        }
    }

    decorateVoiceChannelUsers() {
        document.querySelectorAll('[class*="voiceUser_"]').forEach((row) => {
            const info = this.extractUserFromElement(row);
            if (!info) return;

            let badge = row.querySelector(".dvt-user-badge");
            const tracked = this.trackedUsers.get(info.userId);

            if (tracked) {
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = "dvt-user-badge";
                    const content = row.querySelector('[class*="content_"]') || row;
                    content.appendChild(badge);
                }
                badge.textContent = `🎧 ${tracked.sourceLang.toUpperCase()}→${this.settings.targetLang.toUpperCase()}`;
                badge.title = "Voice translation active (Click to stop)";
                badge.onclick = (e) => {
                    e.stopPropagation();
                    this.setUserVoiceTranslation(info.userId, info.username, tracked.sourceLang, false);
                };
            } else if (badge) {
                badge.remove();
            }
        });
    }

    /* ==========================================================
       Live Subtitle Overlay & TTS Voice Dubbing
       ========================================================== */
    startCaptionPolling() {
        this.stopCaptionPolling();
        this.captionPollTimer = setInterval(async () => {
            if (!this.backendOnline || this.trackedUsers.size === 0) return;
            try {
                const resp = await this.fetchWithTimeout(`/voice/captions?since_seq=${this.lastCaptionSeq}`, {}, 2500);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data && Array.isArray(data.captions)) {
                    for (const cap of data.captions) {
                        if (cap.seq > this.lastCaptionSeq) {
                            this.lastCaptionSeq = cap.seq;
                        }
                        this.handleIncomingCaption(cap);
                    }
                }
            } catch (_) {}
        }, 450);
    }

    stopCaptionPolling() {
        if (this.captionPollTimer) {
            clearInterval(this.captionPollTimer);
            this.captionPollTimer = null;
        }
    }

    handleIncomingCaption(cap) {
        if (!cap || !cap.translated_text) return;
        if (this.settings.enableSubtitles) {
            this.renderSubtitleToast(cap);
        }
        if (this.settings.enableTts && cap.tts !== false) {
            this.speakTranslation(cap.translated_text, cap.target_lang || this.settings.targetLang);
        }
    }

    renderSubtitleToast(cap) {
        let container = document.getElementById("dvt-subtitle-overlay");
        if (!container) {
            container = document.createElement("div");
            container.id = "dvt-subtitle-overlay";
            document.body.appendChild(container);
        }

        const line = document.createElement("div");
        line.className = "dvt-subtitle-line";
        const srcTag = (cap.source_lang || "auto").toUpperCase();
        const tgtTag = (cap.target_lang || this.settings.targetLang).toUpperCase();

        const meta = document.createElement("div");
        meta.className = "dvt-subtitle-meta";
        meta.textContent = `🎧 ${cap.username} (${srcTag} → ${tgtTag})`;

        const main = document.createElement("div");
        main.className = "dvt-subtitle-text";
        main.textContent = cap.translated_text;

        const orig = document.createElement("div");
        orig.className = "dvt-subtitle-orig";
        orig.textContent = cap.original_text;

        line.appendChild(meta);
        line.appendChild(main);
        if (cap.original_text && cap.original_text !== cap.translated_text) {
            line.appendChild(orig);
        }

        container.appendChild(line);
        while (container.children.length > 4) {
            container.firstChild.remove();
        }

        const ttl = Math.max(3, Number(this.settings.subtitleDurationSec) || 8) * 1000;
        setTimeout(() => {
            line.classList.add("fade-out");
            setTimeout(() => line.remove(), 300);
        }, ttl);
    }

    speakTranslation(text, langCode) {
        try {
            if (!("speechSynthesis" in window)) return;
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = langCode || "en-US";
            utter.volume = Math.min(1, Math.max(0.1, Number(this.settings.ttsVolume) || 0.9));
            utter.rate = Math.min(1.5, Math.max(0.7, Number(this.settings.ttsRate) || 1.05));
            window.speechSynthesis.speak(utter);
        } catch (e) {
            console.warn("[DiscordVoiceTranslator] TTS playback error:", e);
        }
    }

    updateStatusPill() {
        let pill = document.getElementById("dvt-status-pill");
        if (this.trackedUsers.size === 0) {
            if (pill) pill.remove();
            return;
        }
        if (!pill) {
            pill = document.createElement("div");
            pill.id = "dvt-status-pill";
            document.body.appendChild(pill);
        }
        const names = Array.from(this.trackedUsers.values()).map((u) => `${u.username} (${u.sourceLang.toUpperCase()})`).join(", ");
        pill.innerHTML = `<span>🎧 Voice Translating: <strong>${names}</strong></span><button id="dvt-stop-all-btn" title="Stop all voice translations">✕</button>`;
        const stopBtn = pill.querySelector("#dvt-stop-all-btn");
        if (stopBtn) {
            stopBtn.onclick = () => {
                for (const u of Array.from(this.trackedUsers.values())) {
                    this.setUserVoiceTranslation(u.userId, u.username, u.sourceLang, false);
                }
            };
        }
    }

    removeOverlayElements() {
        document.querySelectorAll("#dvt-subtitle-overlay, #dvt-status-pill, .dvt-context-box, .dvt-user-badge").forEach((el) => el.remove());
    }

    /* ==========================================================
       GitHub Auto-Updater
       ========================================================== */
    startAutoUpdater() {
        this.stopAutoUpdater();
        if (this.settings.autoUpdate !== false) {
            setTimeout(() => this.checkForUpdates(false), 5000);
        }
        this.updateCheckInterval = setInterval(() => {
            if (this.settings.autoUpdate !== false) this.checkForUpdates(false);
        }, 6 * 60 * 60 * 1000);
    }

    stopAutoUpdater() {
        if (this.updateCheckInterval) {
            clearInterval(this.updateCheckInterval);
            this.updateCheckInterval = null;
        }
    }

    compareSemver(vA, vB) {
        const clean = (v) => String(v || "0.0.0").replace(/^v/i, "").trim().split(".").map((n) => parseInt(n, 10) || 0);
        const a = clean(vA);
        const b = clean(vB);
        for (let i = 0; i < 3; i++) {
            const diff = (a[i] || 0) - (b[i] || 0);
            if (diff !== 0) return diff > 0 ? 1 : -1;
        }
        return 0;
    }

    async checkForUpdates(manual = false) {
        try {
            const url = `${this.updateUrl}?t=${Date.now()}`;
            const resp = (typeof BdApi !== "undefined" && BdApi.Net && typeof BdApi.Net.fetch === "function")
                ? await BdApi.Net.fetch(url, { cache: "no-store" })
                : await fetch(url, { cache: "no-store" });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const remoteCode = await resp.text();
            if (!remoteCode || !remoteCode.includes("@name DiscordVoiceTranslator")) return false;

            const verMatch = remoteCode.match(/@version\s+([0-9]+\.[0-9]+\.[0-9A-Za-z.\-_]+)/);
            const remoteVersion = verMatch ? verMatch[1].trim() : null;
            if (!remoteVersion) return false;

            if (this.compareSemver(remoteVersion, this.version) > 0) {
                const fs = require("fs");
                const path = require("path");
                const pluginsFolder = (typeof BdApi !== "undefined" && BdApi.Plugins && BdApi.Plugins.folder)
                    ? BdApi.Plugins.folder
                    : __dirname;
                fs.writeFileSync(path.join(pluginsFolder, "DiscordVoiceTranslator.plugin.js"), remoteCode, "utf8");
                if (this.backendOnline) {
                    this.fetchWithTimeout("/update", { method: "POST" }, 10000).catch(() => {});
                }
                this.showToast(`Discord Voice Translator auto-updated to v${remoteVersion}!`, { type: "success" });
                return true;
            } else if (manual) {
                this.showToast(`Discord Voice Translator is up to date (v${this.version}).`, { type: "success" });
            }
        } catch (err) {
            if (manual) this.showToast(`Voice update check failed: ${err.message || err}`, { type: "error" });
        }
        return false;
    }

    /* ==========================================================
       Styles & Settings Panel
       ========================================================== */
    injectStyles() {
        const css = `
            .dvt-context-box {
                background: #18191c;
                border: 1px solid rgba(88, 101, 242, 0.55);
                border-radius: 6px;
                padding: 8px;
                margin-top: 6px;
                z-index: 10005;
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 220px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
            }
            .dvt-context-title {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                color: #b9bbbe;
                letter-spacing: 0.4px;
            }
            .dvt-context-btn {
                background: #5865F2;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                text-align: left;
            }
            .dvt-context-btn.active {
                background: #ed4245;
            }
            .dvt-context-select {
                background: #2f3136;
                color: #ffffff;
                border: 1px solid #202225;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
            }
            .dvt-user-badge {
                display: inline-flex;
                align-items: center;
                margin-left: 6px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 700;
                color: #ffffff;
                background: #5865F2;
                border-radius: 10px;
                cursor: pointer;
            }
            #dvt-subtitle-overlay {
                position: fixed;
                bottom: 84px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 6px;
                pointer-events: none;
                max-width: 680px;
                width: 85%;
            }
            .dvt-subtitle-line {
                background: rgba(18, 19, 22, 0.92);
                border-left: 4px solid #5865F2;
                border-radius: 6px;
                padding: 8px 14px;
                color: #ffffff;
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.55);
                transition: opacity 0.25s ease;
            }
            .dvt-subtitle-line.fade-out {
                opacity: 0;
            }
            .dvt-subtitle-meta {
                font-size: 11px;
                font-weight: 700;
                color: #8ea1e1;
                margin-bottom: 2px;
            }
            .dvt-subtitle-text {
                font-size: 15px;
                font-weight: 600;
                color: #ffffff;
                line-height: 1.35;
            }
            .dvt-subtitle-orig {
                font-size: 12px;
                color: #a3a6aa;
                margin-top: 2px;
                font-style: italic;
            }
            #dvt-status-pill {
                position: fixed;
                bottom: 18px;
                right: 18px;
                z-index: 9999;
                background: #202225;
                border: 1px solid #5865F2;
                color: #ffffff;
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.45);
            }
            #dvt-status-pill button {
                background: transparent;
                border: none;
                color: #ed4245;
                font-weight: 700;
                cursor: pointer;
                font-size: 13px;
            }
        `;
        if (typeof BdApi !== "undefined" && BdApi.DOM) {
            BdApi.DOM.addStyle("DiscordVoiceTranslatorStyles", css);
        }
    }

    clearStyles() {
        if (typeof BdApi !== "undefined" && BdApi.DOM) {
            BdApi.DOM.removeStyle("DiscordVoiceTranslatorStyles");
        }
    }

    getSettingsPanel() {
        const panel = document.createElement("div");
        panel.style.padding = "12px";
        panel.style.color = "#dcddde";

        const langOptionsHtml = (selected) =>
            this.getSupportedLanguages()
                .filter((l) => l.code !== "auto")
                .map((l) => `<option value="${l.code}" ${selected === l.code ? "selected" : ""}>${l.name}</option>`)
                .join("");

        panel.innerHTML = `
            <h2 style="color: white; margin-bottom: 6px;">Discord Voice Translator <span style="font-size: 0.7em; color: #8e9297;">v${this.version}</span></h2>
            <p style="color: #b9bbbe; font-size: 12px; margin-bottom: 14px;">
                Right-click any user inside a Discord voice channel to start or stop translating their voice in real time.
                Note: Active voice translation temporarily boosts the companion backend to NORMAL CPU priority (4 threads).
            </p>

            <div style="margin-bottom: 14px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px;">Your Target Language (Translate Into):</label>
                <select id="dvt-target-lang" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                    ${langOptionsHtml(this.settings.targetLang)}
                </select>
            </div>

            <div style="margin-bottom: 14px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px;">Default Speaker Language (Translate From):</label>
                <select id="dvt-source-lang" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                    ${this.getSupportedLanguages().map((l) => `<option value="${l.code}" ${this.settings.defaultSourceLang === l.code ? "selected" : ""}>${l.name}</option>`).join("")}
                </select>
            </div>

            <div style="margin-bottom: 12px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dvt-subtitles" ${this.settings.enableSubtitles ? "checked" : ""}>
                    <span>Show Live Floating Subtitle Captions</span>
                </label>
            </div>

            <div style="margin-bottom: 12px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dvt-tts" ${this.settings.enableTts ? "checked" : ""}>
                    <span>Speak Translated Audio (TTS Voice Dubbing)</span>
                </label>
            </div>

            <div style="margin-bottom: 14px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dvt-duck" ${this.settings.duckOriginalVolume ? "checked" : ""}>
                    <span>Auto-Duck Original Speaker Volume to ${this.settings.duckedVolumePercent}% while Translating</span>
                </label>
            </div>

            <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: space-between;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dvt-auto-update" ${this.settings.autoUpdate !== false ? "checked" : ""}>
                    <span>Automatically check GitHub for updates</span>
                </label>
                <button id="dvt-check-update-btn" style="background: #5865F2; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: 600;">Check for Updates Now</button>
            </div>
        `;

        panel.querySelector("#dvt-target-lang").onchange = (e) => {
            this.settings.targetLang = e.target.value;
            this.saveSettings();
        };
        panel.querySelector("#dvt-source-lang").onchange = (e) => {
            this.settings.defaultSourceLang = e.target.value;
            this.saveSettings();
        };
        panel.querySelector("#dvt-subtitles").onchange = (e) => {
            this.settings.enableSubtitles = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dvt-tts").onchange = (e) => {
            this.settings.enableTts = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dvt-duck").onchange = (e) => {
            this.settings.duckOriginalVolume = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dvt-auto-update").onchange = (e) => {
            this.settings.autoUpdate = e.target.checked;
            this.saveSettings();
        };
        const btn = panel.querySelector("#dvt-check-update-btn");
        if (btn) {
            btn.onclick = async () => {
                btn.disabled = true;
                btn.innerText = "Checking...";
                await this.checkForUpdates(true);
                btn.disabled = false;
                btn.innerText = "Check for Updates Now";
            };
        }

        return panel;
    }
};
