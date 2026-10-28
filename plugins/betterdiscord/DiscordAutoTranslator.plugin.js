/**
 * @name DiscordAutoTranslator
 * @author Antigravity
 * @description Offline, gamer-friendly real-time auto-translator with complete sentence accuracy, inline translation under foreign messages, embed & image OCR translation, and auto-translating outgoing responses.
 * @version 0.1.0
 */

module.exports = class DiscordAutoTranslator {
    constructor() {
        this.defaultSettings = {
            targetLang: "en",
            accuracyMode: "deep_thought", // "deep_thought" (complete sentence context) or "fast"
            translateOutgoing: false,     // Global auto-translate outgoing toggle
            defaultOutgoingLang: "auto",  // "auto" or specific language code (ja, es, etc.)
            channelOverrides: {},         // Per-channel manual target language overrides { channelId: "ja" }
            channelActive: {},            // Per-channel ON/OFF state { channelId: true }
            defaultServerEnabled: true,   // Incoming translation for servers with no saved rule
            serverRules: {},              // Per-server rules { guildId|"@me": { enabled: bool, sourceLang: "auto"|"ja"... } }
            bilingualOutgoing: false,     // Send both translated and (original in parens)
            autoOcrImages: false,         // Gamer-friendly: false = on-demand click
            translateLinks: true,         // Translate link preview embeds
            translateChannels: true,      // Auto-translate foreign channel names in sidebar
            translateCategories: true,    // Auto-translate category headers in sidebar
            translateMemberGroups: true,  // Auto-translate member list role categories in user list
            translateHeaderTitle: true,   // Auto-translate active channel header title
            channelDisplayMode: "suffix", // "suffix" [Translated], "subtitle", "replace", "tooltip"
            serverUrl: "http://127.0.0.1:49152"
        };
        this.settings = Object.assign({}, this.defaultSettings);
        this.translationCache = new Map();
        this.channelNameCache = new Map(); // Fast memory cache for translated channel/category names
        this.emojiAssociationMap = new Map(); // Registry for server-specific emoji & image tag associations
        this.channelLanguages = new Map(); // Dynamically detected foreign languages per channel
        this.observer = null;
        this.channelScanInterval = null;
        this.lastChannelId = null;
        this.navHandler = null;
    }

    start() {
        this.loadSettings();
        this.startKeepAlive();
        this.injectStyles();
        this.initObserver();
        this.initChannelScanner();
        this.hookChatBar();
        this.hookNavigation();
        this.showWelcomeToast();
        console.log("[DiscordAutoTranslator] Started successfully.");
    }

    stop() {
        this.stopKeepAlive();
        this.clearStyles();
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
        }
        if (this.channelScanInterval) {
            clearInterval(this.channelScanInterval);
            this.channelScanInterval = null;
        }
        this.unhookNavigation();
        this.unhookChatBar();
        this.translationCache.clear();
        this.channelNameCache.clear();
        this.emojiAssociationMap.clear();
        this.cleanupChannelBadges();
        console.log("[DiscordAutoTranslator] Stopped.");
    }

    onSwitch() {
        this.handleChannelSwitch();
    }

    hookNavigation() {
        this.lastChannelId = this.getCurrentChannelId();
        this.navHandler = () => {
            const cur = this.getCurrentChannelId();
            if (cur && cur !== this.lastChannelId) {
                this.handleChannelSwitch();
            }
        };
        window.addEventListener("popstate", this.navHandler);
        window.addEventListener("hashchange", this.navHandler);
    }

    unhookNavigation() {
        if (this.navHandler) {
            window.removeEventListener("popstate", this.navHandler);
            window.removeEventListener("hashchange", this.navHandler);
            this.navHandler = null;
        }
    }

    loadSettings() {
        try {
            let saved = null;
            if (typeof BdApi !== "undefined") {
                if (BdApi.Data && typeof BdApi.Data.load === "function") {
                    saved = BdApi.Data.load("DiscordAutoTranslator", "settings");
                } else if (typeof BdApi.loadData === "function") {
                    saved = BdApi.loadData("DiscordAutoTranslator", "settings");
                }
            }
            if (saved) Object.assign(this.settings, saved);
        } catch (e) {
            console.error("[DiscordAutoTranslator] Failed to load settings:", e);
        }
    }

    saveSettings() {
        try {
            if (typeof BdApi !== "undefined") {
                if (BdApi.Data && typeof BdApi.Data.save === "function") {
                    BdApi.Data.save("DiscordAutoTranslator", "settings", this.settings);
                } else if (typeof BdApi.saveData === "function") {
                    BdApi.saveData("DiscordAutoTranslator", "settings", this.settings);
                }
            }
        } catch (e) {
            console.error("[DiscordAutoTranslator] Failed to save settings:", e);
        }
    }

    showToast(msg, options = {}) {
        if (typeof BdApi !== "undefined") {
            if (BdApi.UI && typeof BdApi.UI.showToast === "function") {
                BdApi.UI.showToast(msg, options);
            } else if (typeof BdApi.showToast === "function") {
                BdApi.showToast(msg, options);
            } else {
                console.log(`[DiscordAutoTranslator Toast] ${msg}`);
            }
        }
    }

    showWelcomeToast() {
        this.showToast("🌐 Offline Auto-Translator Active (Gamer-Friendly)", { type: "info" });
    }

    injectStyles() {
        const css = `
            /* Container for inline translation below original message */
            .dat-translation-container {
                display: flex;
                flex-direction: column;
                margin-top: 4px;
                padding: 6px 10px;
                background: rgba(32, 34, 37, 0.6);
                border-left: 3px solid #5865F2;
                border-radius: 4px;
                font-size: 0.9em;
                color: #dcddde;
                line-height: 1.35;
                animation: datFadeIn 0.2s ease-in-out;
            }

            @keyframes datFadeIn {
                from { opacity: 0; transform: translateY(-2px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .dat-header {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 2px;
                font-size: 0.75em;
                font-weight: 600;
                color: #8e9297;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .dat-badge {
                background: #5865F2;
                color: white;
                padding: 1px 5px;
                border-radius: 3px;
                font-size: 0.85em;
            }

            .dat-text {
                color: #f6f6f7;
                white-space: pre-wrap;
                word-break: break-word;
            }

            .dat-inline-emoji {
                width: 1.35em;
                height: 1.35em;
                vertical-align: -0.22em;
                display: inline-block;
                margin: 0 1px;
            }

            .dat-copy-btn {
                background: transparent;
                border: none;
                cursor: pointer;
                color: #b9bbbe;
                padding: 0 4px;
                font-size: 0.9em;
                transition: color 0.15s;
            }
            .dat-copy-btn:hover {
                color: #ffffff;
            }

            /* Image OCR Button & Box */
            .dat-ocr-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                margin-top: 4px;
                padding: 3px 8px;
                background: #4f545c;
                color: white;
                font-size: 0.75em;
                border: none;
                border-radius: 3px;
                cursor: pointer;
                transition: background 0.15s;
            }
            .dat-ocr-btn:hover {
                background: #5865F2;
            }

            .dat-ocr-result {
                margin-top: 4px;
                padding: 6px;
                background: rgba(0, 0, 0, 0.4);
                border-left: 3px solid #f1c40f;
                border-radius: 3px;
                font-size: 0.85em;
            }

            /* Outgoing translation chat toggle button & badge */
            .dat-chatbar-btn {
                background: transparent;
                border: none;
                cursor: pointer;
                padding: 3px 6px;
                margin-right: 4px;
                border-radius: 4px;
                display: flex;
                align-items: center;
                gap: 4px;
                color: #b9bbbe;
                font-size: 0.8em;
                font-weight: 700;
                transition: background 0.15s, color 0.15s;
            }
            .dat-chatbar-btn.active {
                color: #ffffff;
                background: #5865F2;
            }
            .dat-chatbar-btn:hover {
                color: #ffffff;
                background: rgba(88, 101, 242, 0.4);
            }

            /* Quick language picker popup menu */
            .dat-lang-popup {
                position: absolute;
                bottom: 54px;
                left: 10px;
                background: #2b2d31;
                border: 1px solid #1e1f22;
                border-radius: 8px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
                z-index: 10000;
                padding: 8px;
                display: flex;
                flex-direction: column;
                gap: 3px;
                min-width: 220px;
                animation: datFadeIn 0.15s ease-in-out;
            }
            .dat-popup-title {
                font-size: 0.72em;
                font-weight: 700;
                color: #949ba4;
                text-transform: uppercase;
                margin-bottom: 4px;
                padding: 2px 6px;
            }
            .dat-lang-item {
                padding: 6px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.85em;
                color: #dbdee1;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: background 0.1s, color 0.1s;
            }
            .dat-lang-item:hover {
                background: #5865F2;
                color: #ffffff;
            }
            .dat-lang-item.selected {
                color: #5865F2;
                font-weight: 700;
            }
            .dat-lang-item.selected:hover {
                color: #ffffff;
            }

            /* Channel & Category Translation in Sidebar */
            .dat-chan-name-flex {
                display: flex !important;
                align-items: center !important;
                width: 100% !important;
                min-width: 0 !important;
                overflow: hidden !important;
            }

            .dat-chan-orig {
                flex: 1 1 auto !important;
                min-width: 28px !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                white-space: nowrap !important;
            }

            .dat-channel-badge {
                flex: 0 0 auto !important;
                max-width: 75% !important;
                margin-left: 6px !important;
                padding: 1px 6px !important;
                font-size: 0.82em !important;
                font-weight: 600 !important;
                line-height: 1.25 !important;
                color: #5865F2 !important;
                background: rgba(88, 101, 242, 0.18) !important;
                border: 1px solid rgba(88, 101, 242, 0.4) !important;
                border-radius: 4px !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                vertical-align: middle !important;
                pointer-events: auto !important;
                cursor: default !important;
                transition: all 0.15s ease-in-out !important;
            }

            [data-list-item-id^="channels___"]:hover .dat-channel-badge,
            [class*="containerDefault_"]:hover .dat-channel-badge {
                max-width: 95% !important;
                background: rgba(88, 101, 242, 0.35) !important;
                border-color: #5865F2 !important;
                color: #ffffff !important;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4) !important;
            }

            .dat-channel-badge.cat {
                font-size: 0.72em !important;
                text-transform: uppercase !important;
                letter-spacing: 0.5px !important;
                background: rgba(235, 69, 158, 0.18) !important;
                border-color: rgba(235, 69, 158, 0.45) !important;
                color: #eb459e !important;
            }

            .dat-channel-badge.role {
                font-size: 0.85em !important;
                text-transform: uppercase !important;
                letter-spacing: 0.5px !important;
                background: rgba(88, 101, 242, 0.18) !important;
                border-color: rgba(88, 101, 242, 0.45) !important;
                color: #5865F2 !important;
                margin-left: 6px !important;
                margin-right: 4px !important;
            }
            .dat-role-orig {
                display: inline-block;
                vertical-align: middle;
            }

            /* Subtitle 2-Line Layout Mode */
            .dat-has-subtitle {
                height: auto !important;
                min-height: 40px !important;
                flex-wrap: wrap !important;
                padding-top: 2px !important;
                padding-bottom: 3px !important;
            }
            .dat-has-subtitle [class*="linkTop_"],
            .dat-has-subtitle [class*="mainContent_"] {
                width: 100% !important;
            }
            .dat-channel-subtitle {
                display: flex !important;
                align-items: center !important;
                gap: 4px !important;
                width: 100% !important;
                font-size: 0.74em !important;
                font-weight: 600 !important;
                color: #5865F2 !important;
                padding-left: 26px !important;
                line-height: 1.25 !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                white-space: nowrap !important;
                margin-top: -1px !important;
                pointer-events: none !important;
                transition: color 0.15s ease !important;
            }
            .dat-has-subtitle:hover .dat-channel-subtitle {
                color: #ffffff !important;
            }

            .dat-header-badge {
                display: inline-flex;
                align-items: center;
                margin-left: 8px;
                padding: 2px 7px;
                font-size: 0.75em;
                font-weight: 600;
                color: #5865F2;
                background: rgba(88, 101, 242, 0.15);
                border: 1px solid rgba(88, 101, 242, 0.4);
                border-radius: 4px;
                vertical-align: middle;
            }
        `;

        const styleId = "DiscordAutoTranslator-css";
        if (typeof BdApi !== "undefined") {
            if (BdApi.DOM && typeof BdApi.DOM.addStyle === "function") {
                return BdApi.DOM.addStyle(styleId, css);
            }
            if (typeof BdApi.injectCSS === "function") {
                return BdApi.injectCSS(styleId, css);
            }
        }
        let styleEl = document.getElementById(styleId);
        if (!styleEl) {
            styleEl = document.createElement("style");
            styleEl.id = styleId;
            document.head.appendChild(styleEl);
        }
        styleEl.textContent = css;
    }

    clearStyles() {
        const styleId = "DiscordAutoTranslator-css";
        if (typeof BdApi !== "undefined") {
            if (BdApi.DOM && typeof BdApi.DOM.removeStyle === "function") {
                return BdApi.DOM.removeStyle(styleId);
            }
            if (typeof BdApi.clearCSS === "function") {
                return BdApi.clearCSS(styleId);
            }
        }
        const styleEl = document.getElementById(styleId);
        if (styleEl) styleEl.remove();
    }

    /* ==========================================================
       Sidebar Channel & Category Name Translation Scanner
       ========================================================== */
    initChannelScanner() {
        this.scanAllChannels();
        this.channelScanInterval = setInterval(() => {
            const curChannel = this.getCurrentChannelId();
            if (curChannel && curChannel !== this.lastChannelId) {
                this.handleChannelSwitch();
            } else {
                this.scanAllChannels();
                this.scanMemberGroups();
                this.processHeaderTitle();
            }
        }, 1200);
    }

    handleChannelSwitch() {
        const curChannel = this.getCurrentChannelId();
        this.lastChannelId = curChannel;

        // 1. Immediately update header title badge for new channel
        this.processHeaderTitle();

        // 2. Scan and translate all messages currently on screen
        this.processAllMessagesOnScreen();

        // 3. Scan sidebar channels & categories
        this.scanAllChannels();

        // 4. Scan member list role categories
        this.scanMemberGroups();

        // 5. Update chat bar toggle button for new channel
        this.updateChatBarButton();

        // 6. Staggered scans to catch messages loaded over the network as user opens the channel
        setTimeout(() => { this.processAllMessagesOnScreen(); this.scanMemberGroups(); }, 150);
        setTimeout(() => { this.processAllMessagesOnScreen(); this.scanMemberGroups(); }, 400);
        setTimeout(() => { this.processAllMessagesOnScreen(); this.scanMemberGroups(); }, 800);
        setTimeout(() => { this.processAllMessagesOnScreen(); this.scanMemberGroups(); }, 1500);
    }

    cleanupChannelBadges() {
        document.querySelectorAll(".dat-channel-badge, .dat-header-badge, .dat-channel-subtitle").forEach(el => el.remove());
        document.querySelectorAll(".dat-has-subtitle").forEach(el => el.classList.remove("dat-has-subtitle"));
        document.querySelectorAll(".dat-chan-name-flex").forEach(el => el.classList.remove("dat-chan-name-flex"));
        document.querySelectorAll("[data-dat-channel-processed]").forEach(el => {
            delete el.dataset.datChannelProcessed;
        });
        document.querySelectorAll("[data-dat-role-processed]").forEach(el => {
            delete el.dataset.datRoleProcessed;
        });
        document.querySelectorAll("[data-dat-header-channel]").forEach(el => {
            delete el.dataset.datHeaderChannel;
        });
    }

    /* ==========================================================
       Member List Role Categories Translation
       ========================================================== */
    scanMemberGroups() {
        if (!this.settings.translateMemberGroups) return;
        const groups = document.querySelectorAll('[class*="membersGroup_"], [class*="membersGroup"]');
        groups.forEach(g => {
            const hasDisplay = this.settings.channelDisplayMode === "subtitle"
                ? !!g.querySelector(".dat-channel-subtitle")
                : (this.settings.channelDisplayMode === "suffix" ? !!g.querySelector(".dat-channel-badge") : true);
            if (!g.dataset.datRoleProcessed || !hasDisplay) {
                this.processMemberGroupElement(g);
            }
        });
    }

    async processMemberGroupElement(groupEl) {
        groupEl.dataset.datRoleProcessed = "true";
        if (!this.settings.translateMemberGroups) return;

        const clone = groupEl.cloneNode(true);
        clone.querySelectorAll(".dat-channel-badge, .dat-channel-subtitle").forEach(b => b.remove());
        const fullText = clone.textContent.trim();

        if (!fullText || fullText.length < 2) return;

        const countMatch = fullText.match(/^(.*?)\s*([—–\-]\s*\d+|\(\d+\))$/);
        const roleTitle = countMatch ? countMatch[1].trim() : fullText;
        const countSuffix = countMatch ? countMatch[2].trim() : "";

        if (!this.isForeignText(roleTitle, this.settings.targetLang)) return;

        const cleaned = this.cleanChannelName(roleTitle);
        if (!cleaned) return;

        const lowerClean = cleaned.toLowerCase();
        const statusMap = {
            "онлайн": "Online",
            "онлајн": "Online",
            "в сети": "Online",
            "вне сети": "Offline",
            "не в сети": "Offline",
            "неактивен": "Offline",
            "отошел": "Idle",
            "не беспокоить": "Do Not Disturb",
            "オンライン": "Online",
            "オフライン": "Offline",
            "離席中": "Idle",
            "取り込み中": "Do Not Disturb",
            "在线": "Online",
            "离线": "Offline",
            "闲置": "Idle",
            "请勿打扰": "Do Not Disturb"
        };

        const cacheKey = `role:${this.settings.targetLang}:${lowerClean}`;
        let transText = statusMap[lowerClean] || this.channelNameCache.get(cacheKey);

        if (!transText) {
            try {
                const res = await this.fetchTranslation(cleaned, "auto", this.settings.targetLang);
                if (res && res.translated_text && res.translated_text.toLowerCase() !== cleaned.toLowerCase() && res.source_lang !== this.settings.targetLang) {
                    transText = this.formatTitleCase(res.translated_text);
                    this.channelNameCache.set(cacheKey, transText);
                }
            } catch (e) {
                console.error("[DiscordAutoTranslator] Error translating member role group:", e);
            }
        }

        if (!transText) return;

        this.applyMemberGroupTranslation(groupEl, roleTitle, countSuffix, transText);
    }

    applyMemberGroupTranslation(groupEl, origRole, countSuffix, transText) {
        if (!groupEl || !transText) return;

        const fullOrig = countSuffix ? `${origRole} ${countSuffix}` : origRole;
        groupEl.title = `Original: ${fullOrig}\nTranslated: ${transText}`;

        const mode = this.settings.channelDisplayMode || "suffix";

        if (mode === "tooltip") {
            groupEl.querySelectorAll(".dat-channel-badge, .dat-channel-subtitle").forEach(b => b.remove());
            return;
        }

        if (mode === "replace") {
            groupEl.querySelectorAll(".dat-channel-badge, .dat-channel-subtitle").forEach(b => b.remove());
            const displayTitle = transText.toUpperCase();
            groupEl.textContent = countSuffix ? `${displayTitle} ${countSuffix}` : displayTitle;
            return;
        }

        if (mode === "subtitle") {
            groupEl.querySelectorAll(".dat-channel-badge").forEach(b => b.remove());
            let subtitle = groupEl.querySelector(".dat-channel-subtitle");
            if (!subtitle) {
                subtitle = document.createElement("div");
                subtitle.className = "dat-channel-subtitle";
                subtitle.style.paddingLeft = "0";
                subtitle.style.marginTop = "2px";
                groupEl.appendChild(subtitle);
            }
            subtitle.innerText = `🌐 ${transText.toUpperCase()}`;
            return;
        }

        // Mode: "suffix" (default)
        groupEl.querySelectorAll(".dat-channel-subtitle").forEach(s => s.remove());
        let badge = groupEl.querySelector(".dat-channel-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "dat-channel-badge role";

            const span = groupEl.querySelector("span");
            const targetEl = span || groupEl;
            targetEl.innerHTML = `<span class="dat-role-orig">${origRole}</span>`;
            targetEl.appendChild(badge);
            if (countSuffix) {
                const countSpan = document.createElement("span");
                countSpan.className = "dat-role-count";
                countSpan.style.marginLeft = "4px";
                countSpan.textContent = countSuffix;
                targetEl.appendChild(countSpan);
            }
        }
        badge.innerText = `[${transText.toUpperCase()}]`;
    }

    scanAllChannels() {
        if (!this.settings.translateChannels) return;

        // 1. Text, Voice, Announcement, Forum channels
        const channels = document.querySelectorAll('[data-list-item-id^="channels___"]');
        channels.forEach(ch => {
            const hasDisplay = this.settings.channelDisplayMode === "subtitle"
                ? !!ch.querySelector(".dat-channel-subtitle")
                : (this.settings.channelDisplayMode === "suffix" ? !!ch.querySelector(".dat-channel-badge") : true);
            if (!ch.dataset.datChannelProcessed || !hasDisplay) {
                this.processChannelElement(ch);
            }
        });

        // 2. Categories
        if (this.settings.translateCategories) {
            const categories = document.querySelectorAll('[class*="category_"], [class*="containerDefault_"] [class*="wrapper_"][role="listitem"], [data-list-item-id*="category"]');
            categories.forEach(cat => {
                if (!cat.dataset.datChannelProcessed || (this.settings.channelDisplayMode === "suffix" && !cat.querySelector(".dat-channel-badge"))) {
                    this.processCategoryElement(cat);
                }
            });
        }
    }

    isForeignText(text, targetLang = "en") {
        if (!text || text.length < 2) return false;

        if (targetLang === "en") {
            const hasForeignChar = /[\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\u0600-\u06FF\u0590-\u05FF\u0370-\u03FF\u0E00-\u0E7F\u00C0-\u00FF]/.test(text);
            if (hasForeignChar) return true;

            const isPureAscii = /^[\x00-\x7F]+$/.test(text);
            if (isPureAscii) return false;
            return true;
        }

        return true;
    }

    cleanChannelName(rawName) {
        if (!rawName) return "";
        let clean = rawName
            .replace(/^[\s#・｜|~:—\-_/]+/, "")
            .replace(/[\s#・｜|~:—\-_/]+$/, "")
            .replace(/[-_]/g, " ")
            .trim();

        if (clean === clean.toUpperCase() && clean.length > 2) {
            clean = clean.toLowerCase();
        }
        return clean;
    }

    formatTitleCase(str) {
        if (!str) return "";
        let text = str.replace(/^[•\-–—]\s*/, "").replace(/[.!?,;]+$/, "").trim();
        return text.replace(/\b([a-z])/g, (_, c) => c.toUpperCase());
    }

    async processChannelElement(channelEl) {
        channelEl.dataset.datChannelProcessed = "true";

        const itemId = channelEl.getAttribute("data-list-item-id") || "";
        const channelId = itemId.includes("___") ? itemId.split("___")[1] : null;

        const nameEl = channelEl.querySelector('[class*="name__"], [class*="name_"], [class*="channelName__"], [class*="channelName_"]') || channelEl;
        if (!nameEl) return;

        let rawName = "";
        try {
            const ChannelStore = (typeof BdApi !== "undefined" && BdApi.Webpack) 
                ? (BdApi.Webpack.getStore("ChannelStore") || BdApi.Webpack.getByStoreName("ChannelStore") || BdApi.Webpack.getByKeys("getChannel"))
                : null;
            if (ChannelStore && channelId) {
                const ch = ChannelStore.getChannel(channelId);
                if (ch && ch.name) rawName = ch.name;
            }
        } catch (_) {}

        if (!rawName) {
            const clone = nameEl.cloneNode(true);
            clone.querySelectorAll(".dat-channel-badge").forEach(b => b.remove());
            rawName = clone.textContent.trim();
        }

        if (!rawName || rawName.length < 2) return;
        if (!this.isForeignText(rawName, this.settings.targetLang)) return;

        const cleaned = this.cleanChannelName(rawName);
        if (!cleaned) return;

        const cacheKey = `chan:${this.settings.targetLang}:${cleaned}`;
        let transText = this.channelNameCache.get(cacheKey);

        if (!transText) {
            try {
                const res = await this.fetchTranslation(cleaned, "auto", this.settings.targetLang);
                if (res && res.translated_text && res.translated_text.toLowerCase() !== cleaned.toLowerCase() && res.source_lang !== this.settings.targetLang) {
                    transText = this.formatTitleCase(res.translated_text);
                    this.channelNameCache.set(cacheKey, transText);
                }
            } catch (e) {
                console.error("[DiscordAutoTranslator] Error translating channel name:", e);
            }
        }

        if (!transText) return;

        this.applyChannelTranslationToElement(channelEl, nameEl, rawName, transText, false);
    }

    async processCategoryElement(catEl) {
        catEl.dataset.datChannelProcessed = "true";

        const nameEl = catEl.querySelector('h2, [class*="name_"], [class*="categoryName_"]') || catEl;
        if (!nameEl) return;

        const clone = nameEl.cloneNode(true);
        clone.querySelectorAll(".dat-channel-badge").forEach(b => b.remove());
        const rawName = clone.textContent.trim();

        if (!rawName || rawName.length < 2) return;
        if (!this.isForeignText(rawName, this.settings.targetLang)) return;

        const cleaned = this.cleanChannelName(rawName);
        if (!cleaned) return;

        const cacheKey = `cat:${this.settings.targetLang}:${cleaned}`;
        let transText = this.channelNameCache.get(cacheKey);

        if (!transText) {
            try {
                const res = await this.fetchTranslation(cleaned, "auto", this.settings.targetLang);
                if (res && res.translated_text && res.translated_text.toLowerCase() !== cleaned.toLowerCase() && res.source_lang !== this.settings.targetLang) {
                    transText = this.formatTitleCase(res.translated_text);
                    this.channelNameCache.set(cacheKey, transText);
                }
            } catch (e) {
                console.error("[DiscordAutoTranslator] Error translating category name:", e);
            }
        }

        if (!transText) return;

        this.applyChannelTranslationToElement(catEl, nameEl, rawName, transText, true);
    }

    applyChannelTranslationToElement(channelEl, nameEl, origName, transText, isCategory = false) {
        if (!channelEl || !nameEl || !transText) return;

        const tooltipStr = `Original: #${origName}\nTranslated: ${transText}`;
        channelEl.title = tooltipStr;

        const mode = this.settings.channelDisplayMode || "suffix";

        if (mode === "tooltip") {
            nameEl.querySelectorAll(".dat-channel-badge, .dat-channel-subtitle").forEach(b => b.remove());
            return;
        }

        if (mode === "replace") {
            nameEl.querySelectorAll(".dat-channel-badge, .dat-channel-subtitle").forEach(b => b.remove());
            nameEl.title = `Original: #${origName}`;
            nameEl.textContent = transText;
            return;
        }

        if (mode === "subtitle" && !isCategory) {
            // Remove any old suffix badge
            nameEl.querySelectorAll(".dat-channel-badge").forEach(b => b.remove());

            const linkEl = channelEl.querySelector('a, [class*="link_"]') || channelEl;
            linkEl.classList.add("dat-has-subtitle");

            let subtitle = linkEl.querySelector(".dat-channel-subtitle");
            if (!subtitle) {
                subtitle = document.createElement("div");
                subtitle.className = "dat-channel-subtitle";
                linkEl.appendChild(subtitle);
            }
            subtitle.innerText = `🌐 ${transText}`;
            subtitle.title = tooltipStr;
            return;
        }

        // Mode: "suffix" (default)
        // Clean up any subtitle from subtitle mode
        const linkEl = channelEl.querySelector('a, [class*="link_"]') || channelEl;
        linkEl.classList.remove("dat-has-subtitle");
        linkEl.querySelectorAll(".dat-channel-subtitle").forEach(s => s.remove());

        // Make nameEl a flex container so original name can shrink and badge stays visible!
        nameEl.classList.add("dat-chan-name-flex");

        let origSpan = nameEl.querySelector(".dat-chan-orig");
        if (!origSpan) {
            origSpan = document.createElement("span");
            origSpan.className = "dat-chan-orig";
            origSpan.textContent = origName;
            nameEl.innerHTML = "";
            nameEl.appendChild(origSpan);
        } else {
            origSpan.textContent = origName;
        }

        let badge = nameEl.querySelector(".dat-channel-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = `dat-channel-badge ${isCategory ? "cat" : ""}`;
            nameEl.appendChild(badge);
        }
        badge.innerText = `[${transText}]`;
        badge.title = tooltipStr;
    }

    async processHeaderTitle() {
        if (!this.settings.translateHeaderTitle) return;

        const header = document.querySelector('section[class*="title_"], [class*="titleWrapper_"]');
        if (!header) return;

        const titleEl = header.querySelector('h1[class*="title_"], h2[class*="title_"], [class*="channelName_"], [class*="title_"]');
        if (!titleEl) return;

        const channelId = this.getCurrentChannelId();
        if (!channelId) return;

        if (header.dataset.datHeaderChannel === channelId && header.querySelector(".dat-header-badge")) {
            return;
        }
        header.dataset.datHeaderChannel = channelId;

        header.querySelectorAll(".dat-header-badge").forEach(b => b.remove());

        let rawName = "";
        try {
            const ChannelStore = (typeof BdApi !== "undefined" && BdApi.Webpack)
                ? (BdApi.Webpack.getStore("ChannelStore") || BdApi.Webpack.getByStoreName("ChannelStore") || BdApi.Webpack.getByKeys("getChannel"))
                : null;
            if (ChannelStore) {
                const ch = ChannelStore.getChannel(channelId);
                if (ch && ch.name) rawName = ch.name;
            }
        } catch (_) {}

        if (!rawName) {
            const clone = titleEl.cloneNode(true);
            clone.querySelectorAll(".dat-header-badge").forEach(b => b.remove());
            rawName = clone.textContent.trim();
        }

        if (!rawName || !this.isForeignText(rawName, this.settings.targetLang)) return;

        const cleaned = this.cleanChannelName(rawName);
        if (!cleaned) return;

        const cacheKey = `chan:${this.settings.targetLang}:${cleaned}`;
        let transText = this.channelNameCache.get(cacheKey);

        const applyHeaderBadge = (trans) => {
            let badge = header.querySelector(".dat-header-badge");
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "dat-header-badge";
                titleEl.insertAdjacentElement("afterend", badge);
            }
            badge.innerText = `🌐 ${trans}`;
            badge.title = `Original: ${rawName} | Translated: ${trans}`;
        };

        if (transText) {
            applyHeaderBadge(transText);
        } else {
            try {
                const res = await this.fetchTranslation(cleaned, "auto", this.settings.targetLang);
                if (res && res.translated_text && res.translated_text.toLowerCase() !== cleaned.toLowerCase()) {
                    transText = this.formatTitleCase(res.translated_text);
                    this.channelNameCache.set(cacheKey, transText);
                    applyHeaderBadge(transText);
                }
            } catch (e) {
                console.error("[DiscordAutoTranslator] Error translating header title:", e);
            }
        }
    }

    /* ==========================================================
       Message & Media DOM Observer for Real-Time Inline Rendering
       ========================================================== */
    initObserver() {
        this.observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        this.processMessageElement(node);
                    }
                }
            }
        });

        // Observe the permanent app root container so observer NEVER detaches on channel switch!
        const rootContainer = document.getElementById("app-mount") || document.body;
        this.observer.observe(rootContainer, { childList: true, subtree: true });

        // Process any existing messages already on screen
        this.processAllMessagesOnScreen();
    }

    processAllMessagesOnScreen() {
        const messages = document.querySelectorAll('[id^="message-content-"]:not([data-dat-processed])');
        messages.forEach((el) => {
            this.processMessageContent(el);
        });

        const images = document.querySelectorAll('img[class*="imageContent_"]:not([data-dat-ocr-processed]), [class*="imageWrapper_"] img:not([data-dat-ocr-processed])');
        images.forEach((img) => {
            this.processImageElement(img);
        });
    }

    processMessageElement(element) {
        if (!element) return;

        // Check if the node itself is message-content
        if (element.id && element.id.startsWith("message-content-")) {
            this.processMessageContent(element);
            return;
        }

        // Find message text elements inside added element
        if (typeof element.querySelectorAll === "function") {
            const messageContents = element.querySelectorAll('[id^="message-content-"]');
            messageContents.forEach((el) => this.processMessageContent(el));

            const images = element.querySelectorAll('img[class*="imageContent_"], [class*="imageWrapper_"] img');
            images.forEach((img) => this.processImageElement(img));
        }
    }

    /* ==========================================================
       Emoji & Server-Specific Image Association Registry
       ========================================================== */
    saveEmojiAssociation(name, data) {
        if (!name || !data || !data.src) return;
        const clean = name.toLowerCase().replace(/:/g, "").trim();
        if (!clean) return;
        this.emojiAssociationMap.set(clean, data);
        this.emojiAssociationMap.set(`:${clean}:`, data);
    }

    resolveEmojiUrl(name) {
        if (!name) return null;
        const clean = name.toLowerCase().replace(/:/g, "").trim();
        if (this.emojiAssociationMap.has(clean)) {
            return this.emojiAssociationMap.get(clean);
        }
        if (this.emojiAssociationMap.has(`:${clean}:`)) {
            return this.emojiAssociationMap.get(`:${clean}:`);
        }

        // Check Webpack EmojiStore if available
        try {
            const EmojiStore = (typeof BdApi !== "undefined" && BdApi.Webpack)
                ? (BdApi.Webpack.getStore("EmojiStore") || BdApi.Webpack.getByStoreName("EmojiStore") || BdApi.Webpack.getByProps("getCustomEmojiById"))
                : null;
            if (EmojiStore) {
                const guildId = this.getCurrentGuildId();
                const emojis = EmojiStore.getGuildEmojis ? EmojiStore.getGuildEmojis(guildId) : null;
                if (emojis) {
                    const list = Array.isArray(emojis) ? emojis : Object.values(emojis);
                    const match = list.find(e => e && e.name && e.name.toLowerCase() === clean);
                    if (match && match.id) {
                        const ext = match.animated ? "gif" : "webp";
                        const src = `https://cdn.discordapp.com/emojis/${match.id}.${ext}?size=44&quality=lossless`;
                        const data = { src, id: match.id, isAnimated: !!match.animated, alt: `:${match.name}:` };
                        this.saveEmojiAssociation(clean, data);
                        return data;
                    }
                }
            }
        } catch (_) {}
        return null;
    }

    getCurrentGuildId() {
        const match = window.location.pathname.match(/\/channels\/(\d+)/);
        return match ? match[1] : null;
    }

    /* ==========================================================
       Per-Server Incoming Translation Rules
       ========================================================== */
    getCurrentServerKey() {
        const match = window.location.pathname.match(/\/channels\/(\d+|@me)/);
        return match ? match[1] : null;
    }

    getSourceLangOptions() {
        return [
            { code: "auto", name: "Any language" },
            { code: "ja", name: "Japanese" },
            { code: "ko", name: "Korean" },
            { code: "zh", name: "Chinese" },
            { code: "ru", name: "Russian" },
            { code: "es", name: "Spanish" },
            { code: "fr", name: "French" },
            { code: "de", name: "German" },
            { code: "pt", name: "Portuguese" },
            { code: "it", name: "Italian" },
        ];
    }

    getServerRule(serverKey) {
        const defaults = { enabled: this.settings.defaultServerEnabled !== false, sourceLang: "auto" };
        if (!serverKey) return defaults;
        const saved = this.settings.serverRules && this.settings.serverRules[serverKey];
        return Object.assign(defaults, saved || {});
    }

    setServerRule(serverKey, patch) {
        if (!serverKey) return;
        if (!this.settings.serverRules) this.settings.serverRules = {};
        this.settings.serverRules[serverKey] = Object.assign(this.getServerRule(serverKey), patch);
        this.saveSettings();
        this.refreshMessageTranslations();
    }

    refreshMessageTranslations() {
        document.querySelectorAll(".dat-translation-container").forEach((el) => el.remove());
        document.querySelectorAll("[data-dat-processed]").forEach((el) => delete el.dataset.datProcessed);
        this.processAllMessagesOnScreen();
    }

    extractCleanMessageText(element) {
        let text = "";
        const walk = (node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                text += node.textContent;
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                // Ignore timestamps and (edited) tag indicators
                if (node.tagName === "TIME" || 
                    (node.className && typeof node.className === "string" && (node.className.includes("edited") || node.className.includes("timestamp")))) {
                    return;
                }
                if (node.tagName === "IMG") {
                    const src = node.src || "";
                    const alt = node.alt || "";
                    const idMatch = src.match(/\/emojis\/(\d+)\.(webp|gif|png)/);
                    const emojiId = node.dataset.id || (idMatch ? idMatch[1] : null);
                    const isAnimated = src.includes(".gif") || /[?&]animated=true/.test(src);
                    const cleanName = (node.dataset.name || alt.replace(/:/g, "")).toLowerCase().trim();

                    // Save association in the registry immediately
                    if (cleanName && src) {
                        this.saveEmojiAssociation(cleanName, {
                            src: src,
                            id: emojiId,
                            isAnimated: isAnimated,
                            alt: alt || `:${cleanName}:`
                        });
                    }

                    // Preserve Discord custom emoji token <:name:id> so backend treats it verbatim
                    if (emojiId && cleanName) {
                        text += isAnimated ? `<a:${cleanName}:${emojiId}>` : `<:${cleanName}:${emojiId}>`;
                    } else if (alt) {
                        text += alt;
                    }
                    return;
                } else if (node.tagName === "BR") {
                    text += "\n";
                } else {
                    const isBlock = ["DIV", "P", "LI"].includes(node.tagName);
                    for (const child of node.childNodes) {
                        walk(child);
                    }
                    if (isBlock && !text.endsWith("\n")) {
                        text += "\n";
                    }
                }
            }
        };
        walk(element);
        return text.trim() || element.innerText.trim();
    }

    async processMessageContent(contentEl) {
        if (contentEl.dataset.datProcessed) return;
        contentEl.dataset.datProcessed = "true";

        // Pre-scan all images in message and container to populate emoji association map
        const parentContainer = contentEl.closest('[id^="chat-messages-"]') || contentEl.parentElement || contentEl;
        const imgs = parentContainer.querySelectorAll('img');
        imgs.forEach(img => {
            const src = img.src || "";
            const alt = img.alt || "";
            const idMatch = src.match(/\/emojis\/(\d+)/);
            const emojiId = img.dataset.id || (idMatch ? idMatch[1] : null);
            const isAnimated = src.includes(".gif") || /[?&]animated=true/.test(src);
            const cleanName = (img.dataset.name || alt.replace(/:/g, "")).toLowerCase().trim();
            if (cleanName && src) {
                this.saveEmojiAssociation(cleanName, {
                    src: src,
                    id: emojiId,
                    isAnimated: isAnimated,
                    alt: alt || `:${cleanName}:`
                });
            }
        });

        const text = this.extractCleanMessageText(contentEl);
        if (!text || text.length < 2) return;

        // Skip code blocks if they are purely syntax
        if (text.startsWith("```") && text.endsWith("```") && !text.includes("\n")) return;

        const channelId = this.getCurrentChannelId();

        // Per-server rule: skip entirely (no backend call) if disabled for this server
        const serverRule = this.getServerRule(this.getCurrentServerKey());
        if (!serverRule.enabled) return;

        try {
            const res = await this.fetchTranslation(text, "auto", this.settings.targetLang);
            const norm = (s) => (s || "").replace(/[^\p{L}\p{N}]+/gu, "").toLowerCase();
            if (!res || res.skipped || !res.translated_text ||
                !res.source_lang || res.source_lang === "und" ||
                res.source_lang === this.settings.targetLang ||
                norm(res.translated_text) === norm(text)) {
                return;
            }

            // Per-server source filter: only translate messages detected as the chosen language
            if (serverRule.sourceLang !== "auto" &&
                res.source_lang.toLowerCase().split("-")[0] !== serverRule.sourceLang.toLowerCase()) {
                return;
            }

            // Save active foreign language for this channel to empower smart outgoing auto-replies
            if (channelId && res.source_lang && res.source_lang !== this.settings.targetLang) {
                this.channelLanguages.set(channelId, res.source_lang);
            }

            // Render translated thought below original message
            this.renderInlineTranslation(contentEl, res);

        } catch (err) {
            console.error("[DiscordAutoTranslator] Translation error:", err);
        }
    }

    renderInlineTranslation(anchorEl, result) {
        // Prevent duplicate rendering
        if (anchorEl.parentElement.querySelector(".dat-translation-container")) return;

        const container = document.createElement("div");
        container.className = "dat-translation-container";

        const header = document.createElement("div");
        header.className = "dat-header";

        const badge = document.createElement("span");
        badge.className = "dat-badge";
        const srcCode = (result.source_lang || "auto").toUpperCase();
        const tgtCode = (result.target_lang || this.settings.targetLang).toUpperCase();
        badge.innerText = `🌐 ${srcCode} → ${tgtCode}`;

        const modeBadge = document.createElement("span");
        modeBadge.style.opacity = "0.7";
        modeBadge.innerText = result.accuracy_mode === "deep_thought" ? "• Deep Thought" : "• Fast";

        const copyBtn = document.createElement("button");
        copyBtn.className = "dat-copy-btn";
        copyBtn.innerText = "📋 Copy";
        copyBtn.onclick = (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(result.translated_text);
            copyBtn.innerText = "✓ Copied";
            setTimeout(() => { copyBtn.innerText = "📋 Copy"; }, 1500);
        };

        header.appendChild(badge);
        header.appendChild(modeBadge);
        header.appendChild(copyBtn);

        const body = document.createElement("div");
        body.className = "dat-text";
        body.innerHTML = this.formatTranslationHtml(result.translated_text);

        container.appendChild(header);
        container.appendChild(body);

        // Place directly beneath original text element
        anchorEl.insertAdjacentElement("afterend", container);
    }

    formatTranslationHtml(text) {
        if (!text) return "";
        const escapeAttr = (s) => String(s)
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        const emojiImg = (src, name) =>
            `<img class="dat-inline-emoji" src="${escapeAttr(src)}" alt=":${escapeAttr(name)}:" title=":${escapeAttr(name)}:" draggable="false">`;

        let escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Single pass: a full Discord custom emoji token <a:name:id> / <:name:id> is matched FIRST
        // (as a whole, tolerating stray spaces the MT model may insert), so the :name: shortcode
        // alternative can never match inside it.
        const tokenRe = /&lt;\s*(a?)\s*:\s*([\w\-~]+)\s*:\s*(\d{5,})\s*&gt;|:([\w\-~]+):/g;

        return escaped.replace(tokenRe, (match, anim, tokName, tokId, shortName) => {
            if (tokId) {
                const ext = anim ? "gif" : "webp";
                const src = `https://cdn.discordapp.com/emojis/${tokId}.${ext}?size=44&quality=lossless`;
                this.saveEmojiAssociation(tokName, { src, id: tokId, isAnimated: !!anim, alt: `:${tokName}:` });
                return emojiImg(src, tokName);
            }
            if (shortName) {
                const assoc = this.resolveEmojiUrl(shortName);
                if (assoc && assoc.src) return emojiImg(assoc.src, shortName);
            }
            return match;
        });
    }

    /* ==========================================================
       Image & Link OCR Processing
       ========================================================== */
    processImageElement(imgEl) {
        if (imgEl.dataset.datOcrProcessed) return;
        imgEl.dataset.datOcrProcessed = "true";

        const imgUrl = imgEl.src;
        if (!imgUrl || imgUrl.startsWith("data:") && imgUrl.length < 50) return;

        const parent = imgEl.closest('[class*="imageWrapper_"]') || imgEl.parentElement;
        if (!parent || parent.querySelector(".dat-ocr-btn")) return;

        const btn = document.createElement("button");
        btn.className = "dat-ocr-btn";
        btn.innerText = "🌐 Translate Image";

        btn.onclick = async (e) => {
            e.stopPropagation();
            btn.innerText = "⏳ Scanning...";
            btn.disabled = true;

            try {
                const res = await this.fetchImageOcr(imgUrl, this.settings.targetLang);
                if (res && res.has_text && res.translated_text) {
                    btn.innerText = "✓ Translated";
                    let resBox = parent.querySelector(".dat-ocr-result");
                    if (!resBox) {
                        resBox = document.createElement("div");
                        resBox.className = "dat-ocr-result";
                        parent.appendChild(resBox);
                    }
                    resBox.innerHTML = `<strong>🌐 OCR (${(res.source_lang || "").toUpperCase()}):</strong> ${res.translated_text}`;
                } else {
                    btn.innerText = "No Text Detected";
                    setTimeout(() => { btn.innerText = "🌐 Translate Image"; btn.disabled = false; }, 2000);
                }
            } catch (err) {
                btn.innerText = "OCR Failed";
                console.error("[DiscordAutoTranslator] OCR Error:", err);
                setTimeout(() => { btn.innerText = "🌐 Translate Image"; btn.disabled = false; }, 2000);
            }
        };

        parent.appendChild(btn);

        // If auto OCR is enabled, trigger automatically
        if (this.settings.autoOcrImages) {
            btn.click();
        }
    }

    /* ==========================================================
       Outgoing Chat Input Hook (Auto-Translate Replies)
       ========================================================== */
    isOutgoingEnabledFor(channelId) {
        if (!channelId) return !!this.settings.translateOutgoing;
        if (this.settings.channelActive && channelId in this.settings.channelActive) {
            return !!this.settings.channelActive[channelId];
        }
        return !!this.settings.translateOutgoing;
    }

    setOutgoingEnabledFor(channelId, active) {
        if (!this.settings.channelActive) this.settings.channelActive = {};
        if (channelId) {
            this.settings.channelActive[channelId] = active;
        }
        this.settings.translateOutgoing = active;
        this.saveSettings();
    }

    getOutgoingTargetLang(channelId) {
        // 1. User manual override for this channel
        if (channelId && this.settings.channelOverrides && this.settings.channelOverrides[channelId]) {
            return this.settings.channelOverrides[channelId];
        }
        // 2. Automatically detected foreign language in this channel
        if (channelId && this.channelLanguages.has(channelId)) {
            return this.channelLanguages.get(channelId);
        }
        // 3. Fallback to default outgoing setting or Japanese
        return (this.settings.defaultOutgoingLang && this.settings.defaultOutgoingLang !== "auto")
            ? this.settings.defaultOutgoingLang
            : "ja";
    }

    setChannelOutgoingTargetLang(channelId, langCode) {
        if (!this.settings.channelOverrides) this.settings.channelOverrides = {};
        if (channelId) {
            if (langCode === "auto") {
                delete this.settings.channelOverrides[channelId];
            } else {
                this.settings.channelOverrides[channelId] = langCode;
            }
            this.saveSettings();
        }
    }

    /* ==========================================================
       Outgoing Chat Input Hook (Auto-Translate Replies)
       ========================================================== */
    hookChatBar() {
        // Method 1: Patch MessageActions.sendMessage
        try {
            if (typeof BdApi !== "undefined" && BdApi.Patcher) {
                BdApi.Patcher.unpatchAll("DiscordAutoTranslator");
            }

            const MessageActions = (typeof BdApi !== "undefined" && BdApi.Webpack)
                ? (BdApi.Webpack.getByKeys("sendMessage", "editMessage") || BdApi.Webpack.getByKeys("sendMessage") || BdApi.Webpack.getModule(m => m && m.sendMessage))
                : null;

            if (MessageActions && typeof BdApi.Patcher !== "undefined") {
                BdApi.Patcher.instead("DiscordAutoTranslator", MessageActions, "sendMessage", (thisObject, args, orig) => {
                    const channelId = args && args[0];
                    const msg = args && args[1];
                    const isEnabled = this.isOutgoingEnabledFor(channelId);

                    // If outgoing auto-translation is disabled, immediately call original sendMessage with all original arguments
                    if (!isEnabled || !msg || typeof msg.content !== "string" || !msg.content.trim() || msg.content.startsWith("/")) {
                        return orig.apply(thisObject, args);
                    }

                    const targetLang = this.getOutgoingTargetLang(channelId);
                    if (!targetLang || targetLang === this.settings.targetLang) {
                        return orig.apply(thisObject, args);
                    }

                    // Perform asynchronous translation only when outgoing translation is actively enabled for this channel
                    return (async () => {
                        try {
                            const origText = msg.content;
                            const res = await this.fetchTranslation(origText, this.settings.targetLang, targetLang);
                            if (res && res.translated_text) {
                                if (this.settings.bilingualOutgoing) {
                                    msg.content = `${res.translated_text}\n*(Original: ${origText})*`;
                                } else {
                                    msg.content = res.translated_text;
                                }
                            }
                        } catch (err) {
                            console.error("[DiscordAutoTranslator] Outgoing translation failed:", err);
                        }
                        return orig.apply(thisObject, args);
                    })();
                });
                console.log("[DiscordAutoTranslator] Successfully patched MessageActions.sendMessage");
            }
        } catch (e) {
            console.warn("[DiscordAutoTranslator] MessageActions patch fallback:", e);
        }

        // Method 2: Chat input bar button with visual indicator and right-click language picker
        this.chatBarInterval = setInterval(() => {
            const chatButtons = document.querySelector('[class*="channelBottomBarArea_"] [class*="buttons_"]') ||
                                document.querySelector('[class*="chatContent_"] [class*="buttons_"]') ||
                                document.querySelector('[class*="buttons_"]');
            if (!chatButtons || chatButtons.querySelector(".dat-chatbar-btn")) return;

            const channelId = this.getCurrentChannelId();
            const isEnabled = this.isOutgoingEnabledFor(channelId);
            const targetLang = this.getOutgoingTargetLang(channelId);

            const btn = document.createElement("button");
            btn.className = `dat-chatbar-btn ${isEnabled ? "active" : ""}`;
            btn.title = `Auto-Translate Outgoing: ${isEnabled ? "ON (" + targetLang.toUpperCase() + ")" : "OFF"}\nLeft-click to toggle, Right-click to choose language (Alt+T)`;
            btn.innerHTML = `🌐 ${isEnabled ? targetLang.toUpperCase() : ""}`;

            // Left-click: Toggle ON/OFF for current channel
            btn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const currentChan = this.getCurrentChannelId();
                const nowActive = !this.isOutgoingEnabledFor(currentChan);
                this.setOutgoingEnabledFor(currentChan, nowActive);

                const currentLang = this.getOutgoingTargetLang(currentChan);
                btn.classList.toggle("active", nowActive);
                btn.innerHTML = `🌐 ${nowActive ? currentLang.toUpperCase() : ""}`;
                btn.title = `Auto-Translate Outgoing: ${nowActive ? "ON (" + currentLang.toUpperCase() + ")" : "OFF"}\nLeft-click to toggle, Right-click to choose language (Alt+T)`;
                this.showToast(`Auto-Translate Outgoing: ${nowActive ? "ENABLED (" + currentLang.toUpperCase() + ")" : "DISABLED"}`, { type: "info" });
            };

            // Right-click: Open quick language picker popup
            btn.oncontextmenu = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const currentChan = this.getCurrentChannelId();
                this.openQuickLangPicker(btn, currentChan);
            };

            chatButtons.prepend(btn);
        }, 1000);

        // Hotkey Alt+T toggles outgoing translation
        this.onKeyDownHandler = (e) => {
            if (e.key === "t" && e.altKey) {
                const btn = document.querySelector(".dat-chatbar-btn");
                if (btn) btn.click();
            }
        };

        document.addEventListener("keydown", this.onKeyDownHandler, true);
    }

    updateChatBarButton() {
        const btn = document.querySelector(".dat-chatbar-btn");
        if (!btn) return;
        const channelId = this.getCurrentChannelId();
        const isEnabled = this.isOutgoingEnabledFor(channelId);
        const targetLang = this.getOutgoingTargetLang(channelId);
        btn.classList.toggle("active", isEnabled);
        btn.innerHTML = `🌐 ${isEnabled ? targetLang.toUpperCase() : ""}`;
        btn.title = `Auto-Translate Outgoing: ${isEnabled ? "ON (" + targetLang.toUpperCase() + ")" : "OFF"}\nLeft-click to toggle, Right-click to choose language (Alt+T)`;
    }

    openQuickLangPicker(btn, channelId) {
        const existing = document.querySelector(".dat-lang-popup");
        if (existing) { existing.remove(); return; }

        const currentLang = this.getOutgoingTargetLang(channelId);
        const popup = document.createElement("div");
        popup.className = "dat-lang-popup";

        // ---- Per-server incoming translation controls ----
        const guildId = this.getCurrentServerKey();
        if (guildId) {
            const rule = this.getServerRule(guildId);

            const srvTitle = document.createElement("div");
            srvTitle.className = "dat-popup-title";
            srvTitle.innerText = guildId === "@me" ? "Direct Messages (Incoming)" : "This Server (Incoming)";
            popup.appendChild(srvTitle);

            const toggleItem = document.createElement("div");
            toggleItem.className = `dat-lang-item ${rule.enabled ? "selected" : ""}`;
            toggleItem.innerHTML = `<span>Auto-translate here</span>${rule.enabled ? "✓" : "OFF"}`;
            toggleItem.onclick = (e) => {
                e.stopPropagation();
                const now = !this.getServerRule(guildId).enabled;
                this.setServerRule(guildId, { enabled: now });
                toggleItem.className = `dat-lang-item ${now ? "selected" : ""}`;
                toggleItem.innerHTML = `<span>Auto-translate here</span>${now ? "✓" : "OFF"}`;
                this.showToast(`Incoming translation for this server: ${now ? "ENABLED" : "DISABLED"}`, { type: "info" });
            };
            popup.appendChild(toggleItem);

            const fromRow = document.createElement("div");
            fromRow.className = "dat-lang-item";
            fromRow.style.cursor = "default";
            const fromLabel = document.createElement("span");
            fromLabel.innerText = "Only from:";
            const fromSelect = document.createElement("select");
            fromSelect.style.cssText = "background:#2f3136;color:white;border:1px solid #202225;border-radius:4px;padding:2px;max-width:60%;";
            this.getSourceLangOptions().forEach((l) => {
                const opt = document.createElement("option");
                opt.value = l.code;
                opt.textContent = l.name;
                if (rule.sourceLang === l.code) opt.selected = true;
                fromSelect.appendChild(opt);
            });
            fromSelect.onclick = (e) => e.stopPropagation();
            fromSelect.onchange = (e) => {
                e.stopPropagation();
                this.setServerRule(guildId, { sourceLang: fromSelect.value });
                const picked = fromSelect.options[fromSelect.selectedIndex].textContent;
                this.showToast(`Translating from: ${picked}`, { type: "info" });
            };
            fromRow.appendChild(fromLabel);
            fromRow.appendChild(fromSelect);
            popup.appendChild(fromRow);
        }

        const title = document.createElement("div");
        title.className = "dat-popup-title";
        title.innerText = "Translate Outgoing To:";
        popup.appendChild(title);

        const languages = [
            { code: "auto", name: "⚡ Auto-Detect (from chat)" },
            { code: "ja", name: "🇯🇵 Japanese (ja)" },
            { code: "es", name: "🇪🇸 Spanish (es)" },
            { code: "fr", name: "🇫🇷 French (fr)" },
            { code: "de", name: "🇩🇪 German (de)" },
            { code: "zh", name: "🇨🇳 Chinese (zh)" },
            { code: "ru", name: "🇷🇺 Russian (ru)" },
            { code: "ko", name: "🇰🇷 Korean (ko)" },
            { code: "pt", name: "🇵🇹 Portuguese (pt)" },
            { code: "it", name: "🇮🇹 Italian (it)" },
        ];

        languages.forEach((l) => {
            const item = document.createElement("div");
            const isSelected = (l.code === "auto" && !this.settings.channelOverrides?.[channelId]) || currentLang === l.code;
            item.className = `dat-lang-item ${isSelected ? "selected" : ""}`;
            item.innerHTML = `<span>${l.name}</span>${isSelected ? "✓" : ""}`;

            item.onclick = (e) => {
                e.stopPropagation();
                this.setChannelOutgoingTargetLang(channelId, l.code);
                popup.remove();

                const nowLang = this.getOutgoingTargetLang(channelId);
                const isEnabled = this.isOutgoingEnabledFor(channelId);
                btn.innerHTML = `🌐 ${isEnabled ? nowLang.toUpperCase() : ""}`;
                btn.title = `Auto-Translate Outgoing: ${isEnabled ? "ON (" + nowLang.toUpperCase() + ")" : "OFF"}\nLeft-click to toggle, Right-click to choose language (Alt+T)`;
                this.showToast(`Channel target language: ${l.name}`, { type: "info" });
            };

            popup.appendChild(item);
        });

        const closeHandler = (e) => {
            if (!popup.contains(e.target) && e.target !== btn) {
                popup.remove();
                document.removeEventListener("click", closeHandler);
            }
        };
        setTimeout(() => document.addEventListener("click", closeHandler), 50);

        const chatTextArea = btn.closest('[class*="channelTextArea_"]') || btn.parentElement;
        chatTextArea.appendChild(popup);
    }

    unhookChatBar() {
        if (typeof BdApi !== "undefined" && BdApi.Patcher) {
            BdApi.Patcher.unpatchAll("DiscordAutoTranslator");
        }
        if (this.chatBarInterval) clearInterval(this.chatBarInterval);
        if (this.onKeyDownHandler) {
            document.removeEventListener("keydown", this.onKeyDownHandler, true);
        }
        document.querySelectorAll(".dat-chatbar-btn, .dat-lang-popup").forEach((b) => b.remove());
    }

    /* ==========================================================
       API Networking with Local Companion Daemon
       ========================================================== */
    /* ----------------------------------------------------------
       Backend handshake + keep-alive
       ---------------------------------------------------------- */
    async fetchWithTimeout(path, options = {}, timeoutMs = 2000) {
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
        console.log(`[DiscordAutoTranslator] Backend ${online ? "connected" : "unreachable - translation bypassed"}.`);
        if (online) {
            if (BdApi && BdApi.UI && BdApi.UI.showToast) BdApi.UI.showToast("Auto Translator backend connected", { type: "success" });
        } else {
            this.translationCache.clear();
        }
    }

    async performHandshake() {
        try {
            const resp = await this.fetchWithTimeout("/handshake", {}, 2000);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.service !== "discord-auto-translator" || !data.ready) throw new Error("Unexpected service");
            this.setBackendOnline(true);
            return true;
        } catch (e) {
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
        } catch (e) {
            this.setBackendOnline(false);
            return false;
        }
    }

    startKeepAlive() {
        this.stopKeepAlive();
        this.backendOnline = false;
        this.performHandshake();
        // Ping every 10s while online; retry the handshake every 5s while offline.
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

    async fetchTranslation(text, srcLang = "auto", tgtLang = "en") {
        const cacheKey = `${srcLang}:${tgtLang}:${text}`;
        if (this.translationCache.has(cacheKey)) {
            return this.translationCache.get(cacheKey);
        }

        // Bypass translation entirely when the backend isn't running.
        if (!this.backendOnline) return null;

        let resp;
        try {
            resp = await this.fetchWithTimeout("/translate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: text,
                    source_lang: srcLang,
                    target_lang: tgtLang,
                    mode: this.settings.accuracyMode
                })
            }, 30000);
        } catch (e) {
            this.setBackendOnline(false);
            return null;
        }

        if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
        const data = await resp.json();
        this.translationCache.set(cacheKey, data);
        return data;
    }

    async fetchImageOcr(imageUrl, tgtLang = "en") {
        if (!this.backendOnline) return null;

        let resp;
        try {
            resp = await this.fetchWithTimeout("/ocr_translate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    image_url: imageUrl,
                    target_lang: tgtLang
                })
            }, 60000);
        } catch (e) {
            this.setBackendOnline(false);
            return null;
        }

        if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
        return await resp.json();
    }

    getCurrentChannelId() {
        const match = window.location.pathname.match(/\/channels\/\d+\/(\d+)/);
        return match ? match[1] : null;
    }

    /* ==========================================================
       BetterDiscord Settings Panel
       ========================================================== */
    getSettingsPanel() {
        const panel = document.createElement("div");
        panel.style.padding = "10px";
        panel.style.color = "#dcddde";

        panel.innerHTML = `
            <h2 style="color: white; margin-bottom: 12px;">Discord Auto-Translator Settings</h2>

            <div style="margin-bottom: 16px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px;">Your Primary / Target Language:</label>
                <select id="dat-target-lang" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                    <option value="en" ${this.settings.targetLang === "en" ? "selected" : ""}>English (en)</option>
                    <option value="es" ${this.settings.targetLang === "es" ? "selected" : ""}>Spanish (es)</option>
                    <option value="ja" ${this.settings.targetLang === "ja" ? "selected" : ""}>Japanese (ja)</option>
                    <option value="fr" ${this.settings.targetLang === "fr" ? "selected" : ""}>French (fr)</option>
                    <option value="de" ${this.settings.targetLang === "de" ? "selected" : ""}>German (de)</option>
                    <option value="zh" ${this.settings.targetLang === "zh" ? "selected" : ""}>Chinese Simplified (zh)</option>
                    <option value="ru" ${this.settings.targetLang === "ru" ? "selected" : ""}>Russian (ru)</option>
                    <option value="ko" ${this.settings.targetLang === "ko" ? "selected" : ""}>Korean (ko)</option>
                    <option value="pt" ${this.settings.targetLang === "pt" ? "selected" : ""}>Portuguese (pt)</option>
                </select>
            </div>

            <div style="margin-bottom: 16px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px;">Translation Accuracy Mode:</label>
                <select id="dat-accuracy-mode" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                    <option value="deep_thought" ${this.settings.accuracyMode === "deep_thought" ? "selected" : ""}>Complete Thought (Full Sentence SBD + Beam Search) [Recommended]</option>
                    <option value="fast" ${this.settings.accuracyMode === "fast" ? "selected" : ""}>Fast Mode (Greedy Search / Low Latency)</option>
                </select>
                <small style="color: #8e9297; display: block; margin-top: 4px;">Ensures full thought correctness instead of naive single-word translation.</small>
            </div>

            <div style="margin-bottom: 16px;">
                <label style="display: block; font-weight: 600; margin-bottom: 6px;">Default Outgoing Target Language:</label>
                <select id="dat-default-outgoing-lang" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                    <option value="auto" ${this.settings.defaultOutgoingLang === "auto" ? "selected" : ""}>⚡ Auto-Detect (from active channel messages)</option>
                    <option value="ja" ${this.settings.defaultOutgoingLang === "ja" ? "selected" : ""}>🇯🇵 Japanese (ja)</option>
                    <option value="es" ${this.settings.defaultOutgoingLang === "es" ? "selected" : ""}>🇪🇸 Spanish (es)</option>
                    <option value="fr" ${this.settings.defaultOutgoingLang === "fr" ? "selected" : ""}>🇫🇷 French (fr)</option>
                    <option value="de" ${this.settings.defaultOutgoingLang === "de" ? "selected" : ""}>🇩🇪 German (de)</option>
                    <option value="zh" ${this.settings.defaultOutgoingLang === "zh" ? "selected" : ""}>🇨🇳 Chinese (zh)</option>
                    <option value="ru" ${this.settings.defaultOutgoingLang === "ru" ? "selected" : ""}>🇷🇺 Russian (ru)</option>
                    <option value="ko" ${this.settings.defaultOutgoingLang === "ko" ? "selected" : ""}>🇰🇷 Korean (ko)</option>
                    <option value="pt" ${this.settings.defaultOutgoingLang === "pt" ? "selected" : ""}>🇵🇹 Portuguese (pt)</option>
                </select>
                <small style="color: #8e9297; display: block; margin-top: 4px;">When auto-translate is active, messages you type will be translated to this language. You can also right-click the 🌐 button in chat to override per channel.</small>
            </div>

            <div style="margin-bottom: 14px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dat-bilingual-outgoing" ${this.settings.bilingualOutgoing ? "checked" : ""}>
                    <span>Bilingual Outgoing Replies (Send translated message + original in parens)</span>
                </label>
            </div>

            <div style="margin-bottom: 14px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dat-auto-ocr" ${this.settings.autoOcrImages ? "checked" : ""}>
                    <span>Auto-Scan All Images with OCR (Keep OFF for best gaming performance)</span>
                </label>
            </div>

            <div style="margin-bottom: 14px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="dat-translate-links" ${this.settings.translateLinks ? "checked" : ""}>
                    <span>Translate Link Preview Embeds</span>
                </label>
            </div>

            <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(255, 255, 255, 0.08);">
                <h3 style="color: white; margin-bottom: 10px; font-size: 1.05em;">Sidebar & Channel Translation</h3>

                <div style="margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="dat-translate-channels" ${this.settings.translateChannels ? "checked" : ""}>
                        <span>Translate Foreign Channel Names in Sidebar</span>
                    </label>
                </div>

                <div style="margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="dat-translate-categories" ${this.settings.translateCategories ? "checked" : ""}>
                        <span>Translate Server Category Headers in Sidebar</span>
                    </label>
                </div>

                <div style="margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="dat-translate-roles" ${this.settings.translateMemberGroups ? "checked" : ""}>
                        <span>Translate Member List Role Categories (User List Sidebar)</span>
                    </label>
                </div>

                <div style="margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="dat-translate-header" ${this.settings.translateHeaderTitle ? "checked" : ""}>
                        <span>Translate Active Channel Title in Top Header Bar</span>
                    </label>
                </div>

                <div style="margin-bottom: 14px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 6px;">Channel Translation Display Style:</label>
                    <select id="dat-channel-mode" style="background: #2f3136; color: white; border: 1px solid #202225; padding: 6px; border-radius: 4px; width: 100%;">
                        <option value="suffix" ${this.settings.channelDisplayMode === "suffix" ? "selected" : ""}>Suffix Badge (Prioritized — badge never cut off) [Recommended]</option>
                        <option value="subtitle" ${this.settings.channelDisplayMode === "subtitle" ? "selected" : ""}>Subtitle Underneath (2-Line layout — full width for long names)</option>
                        <option value="replace" ${this.settings.channelDisplayMode === "replace" ? "selected" : ""}>Replace Name (# Common Chat — original shown on hover)</option>
                        <option value="tooltip" ${this.settings.channelDisplayMode === "tooltip" ? "selected" : ""}>Tooltip Only (Vanilla sidebar, translation on hover)</option>
                    </select>
                </div>
            </div>
        `;

        // Bind change listeners
        panel.querySelector("#dat-target-lang").onchange = (e) => {
            this.settings.targetLang = e.target.value;
            this.saveSettings();
            this.cleanupChannelBadges();
            this.scanAllChannels();
            this.scanMemberGroups();
        };
        panel.querySelector("#dat-accuracy-mode").onchange = (e) => {
            this.settings.accuracyMode = e.target.value;
            this.saveSettings();
        };
        panel.querySelector("#dat-default-outgoing-lang").onchange = (e) => {
            this.settings.defaultOutgoingLang = e.target.value;
            this.saveSettings();
        };
        panel.querySelector("#dat-bilingual-outgoing").onchange = (e) => {
            this.settings.bilingualOutgoing = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dat-auto-ocr").onchange = (e) => {
            this.settings.autoOcrImages = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dat-translate-links").onchange = (e) => {
            this.settings.translateLinks = e.target.checked;
            this.saveSettings();
        };
        panel.querySelector("#dat-translate-channels").onchange = (e) => {
            this.settings.translateChannels = e.target.checked;
            this.saveSettings();
            this.cleanupChannelBadges();
            if (this.settings.translateChannels) this.scanAllChannels();
        };
        panel.querySelector("#dat-translate-categories").onchange = (e) => {
            this.settings.translateCategories = e.target.checked;
            this.saveSettings();
            this.cleanupChannelBadges();
            if (this.settings.translateCategories) this.scanAllChannels();
        };
        panel.querySelector("#dat-translate-roles").onchange = (e) => {
            this.settings.translateMemberGroups = e.target.checked;
            this.saveSettings();
            this.cleanupChannelBadges();
            if (this.settings.translateMemberGroups) this.scanMemberGroups();
        };
        panel.querySelector("#dat-translate-header").onchange = (e) => {
            this.settings.translateHeaderTitle = e.target.checked;
            this.saveSettings();
            this.cleanupChannelBadges();
            if (this.settings.translateHeaderTitle) this.processHeaderTitle();
        };
        panel.querySelector("#dat-channel-mode").onchange = (e) => {
            this.settings.channelDisplayMode = e.target.value;
            this.saveSettings();
            this.cleanupChannelBadges();
            if (this.settings.translateChannels) this.scanAllChannels();
        };

        return panel;
    }
};
