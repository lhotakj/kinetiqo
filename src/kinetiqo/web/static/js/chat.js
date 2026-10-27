(() => {
    'use strict';
    const app = document.getElementById('chat-app');
    if (!app) return;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || document.querySelector('input[name="csrf_token"]')?.value || '';
    const sessions = document.getElementById('chat-sessions');
    const messages = document.getElementById('chat-messages');
    const scrollContainer = document.getElementById('chat-scroll');
    const empty = document.getElementById('chat-empty');
    const composer = document.getElementById('chat-composer');
    const input = document.getElementById('chat-input');
    const send = document.getElementById('chat-send');
    const status = document.getElementById('chat-status');
    const model = document.getElementById('chat-model');
    const modelTrigger = document.getElementById('chat-model-trigger');
    const modelSelectedLabel = document.getElementById('chat-model-selected');
    const modelMenu = document.getElementById('chat-model-menu');
    const modelDefaultIndicator = document.getElementById('chat-model-default-indicator');
    const activeModelBadge = document.getElementById('chat-active-model');
    const suggestionsPopup = document.getElementById('chat-suggestions-popup');
    let sessionId = JSON.parse(app.dataset.initialSessionId || 'null');
    const userName = JSON.parse(app.dataset.userName || '"Athlete"') || 'Athlete';

    const PREFERRED_MODELS = ['gemini-3.1-flash-lite', 'gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash'];

    const escapeHtml = (str) => {
        return (str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    const tryParseToChartJson = (text, lang) => {
        const raw = (text || '').trim();
        if (!raw) return null;

        const lowerLang = (lang || '').trim().toLowerCase();

        if (lowerLang === 'chart' || lowerLang === 'chartjs' || lowerLang === 'chart.js') {
            return raw;
        }

        if (lowerLang === 'json' && raw.startsWith('{')) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed && parsed.type && parsed.data) {
                    return raw;
                }
            } catch (_) {}
        }

        // Automatic fallback: If model emits ```radar, ```spider, or Mermaid radar syntax
        if (lowerLang === 'radar' || lowerLang === 'spider' || (lowerLang === 'mermaid' && /^\s*radar\b/im.test(raw))) {
            if (raw.startsWith('{')) {
                try {
                    const parsed = JSON.parse(raw);
                    if (parsed && parsed.type) return raw;
                } catch (_) {}
            }
            const lines = raw.split(/\r?\n/);
            let title = '';
            const labels = [];
            const values = [];

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || trimmed === 'radar' || trimmed.startsWith('%%')) continue;
                const titleMatch = trimmed.match(/^title\s+(.*)$/i);
                if (titleMatch) {
                    title = titleMatch[1].trim();
                    continue;
                }
                const pairMatch = trimmed.match(/^["']?([^"':\n]+)["']?\s*:\s*([0-9.]+)/);
                if (pairMatch) {
                    labels.push(pairMatch[1].trim());
                    values.push(Number.parseFloat(pairMatch[2]));
                }
            }

            if (labels.length >= 2 && values.length >= 2) {
                const chartConfig = {
                    type: 'radar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: title || 'Power Profile (W)',
                            data: values,
                            borderColor: '#ea580c',
                            backgroundColor: 'rgba(234, 88, 12, 0.2)',
                            pointBackgroundColor: '#ea580c'
                        }]
                    },
                    options: {
                        plugins: {
                            title: { display: Boolean(title), text: title || 'Power Profile' }
                        }
                    }
                };
                return JSON.stringify(chartConfig, null, 2);
            }
        }

        return null;
    };

    const buildChartContainerHtml = (codeText) => {
        const rawCode = (codeText || '').trim();
        return `<div class="chat-chart-container my-3 rounded-xl border border-warm-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-3 shadow-xs" data-rendered="false">
            <div class="flex items-center justify-between pb-2 mb-2 border-b border-warm-100 dark:border-zinc-800 text-[11px] text-gray-500 dark:text-zinc-400 select-none">
                <span class="font-mono font-medium flex items-center gap-1.5 text-gray-700 dark:text-zinc-300 min-w-0">
                    <svg class="w-3.5 h-3.5 text-orange-500 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <line x1="18" y1="20" x2="18" y2="10"/>
                        <line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                    <span class="chat-chart-title truncate max-w-[280px]">Interactive Chart</span>
                </span>
                <button type="button" class="chat-chart-toggle cursor-pointer hover:text-orange-600 dark:hover:text-orange-400 transition px-1.5 py-0.5 rounded text-[11px] flex items-center gap-1" title="Toggle between chart and source code">
                    <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>
                    <span>View code</span>
                </button>
            </div>
            <div class="chat-chart-canvas-wrapper relative w-full h-[320px] max-h-[420px] py-1 flex items-center justify-center">
                <canvas class="chat-chart-canvas w-full h-full"></canvas>
            </div>
            <pre class="chat-chart-code hidden overflow-x-auto rounded-lg bg-zinc-900 p-2.5 text-xs text-zinc-100 font-mono dark:bg-black/40 border border-zinc-700/60 mt-1"><code>${escapeHtml(rawCode)}</code></pre>
        </div>`;
    };

    if (typeof window.marked !== 'undefined' && typeof window.marked.use === 'function') {
        try {
            window.marked.use({
                breaks: true,
                gfm: true,
                renderer: {
                    link({ href, title, text }) {
                        const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
                        return `<a href="${href || '#'}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
                    },
                    code(codeOrToken, infostring) {
                        let lang = '';
                        let text = '';
                        if (codeOrToken && typeof codeOrToken === 'object') {
                            lang = (codeOrToken.lang || '').trim().toLowerCase();
                            text = codeOrToken.text || '';
                        } else {
                            lang = (infostring || '').trim().toLowerCase();
                            text = codeOrToken || '';
                        }
                        const chartJson = tryParseToChartJson(text, lang);
                        if (chartJson) {
                            return buildChartContainerHtml(chartJson);
                        }
                        return false;
                    }
                }
            });
        } catch (err) {
            console.warn('Failed to configure marked:', err);
        }
    }

    const renderMarkdown = (text) => {
        if (!text) return '';
        const cleaned = text.replace(/(?:^|\n)\s*\*?Copy the block above[\s\S]*?Mermaid live editor[^\n]*\*?/gi, '');
        if (typeof window.marked !== 'undefined' && typeof window.marked.parse === 'function') {
            try {
                return window.marked.parse(cleaned);
            } catch (err) {
                console.warn('Marked parse error, using fallback:', err);
            }
        }
        const codeBlocks = [];
        let processed = cleaned.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const id = `__CB_${codeBlocks.length}__`;
            const chartJson = tryParseToChartJson(code.trim(), lang);
            if (chartJson) {
                codeBlocks.push(buildChartContainerHtml(chartJson));
            } else {
                codeBlocks.push(`<pre class="my-3 overflow-x-auto rounded-xl bg-zinc-900 p-3 text-xs text-zinc-100 font-mono dark:bg-black/40 border border-zinc-700/60"><code>${escapeHtml(code.trim())}</code></pre>`);
            }
            return id;
        });

        processed = escapeHtml(processed);

        codeBlocks.forEach((block, idx) => {
            processed = processed.replace(`__CB_${idx}__`, block);
        });

        // Inline code
        processed = processed.replace(/`([^`]+)`/g, '<code class="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5 text-xs font-mono font-medium text-orange-600 dark:text-orange-400">$1</code>');

        // Headers
        processed = processed.replace(/^### (.*$)/gim, '<h3 class="text-base font-bold text-gray-900 dark:text-white mt-4 mb-1.5">$1</h3>');
        processed = processed.replace(/^## (.*$)/gim, '<h2 class="text-lg font-bold text-gray-900 dark:text-white mt-5 mb-2">$1</h2>');
        processed = processed.replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold text-gray-900 dark:text-white mt-6 mb-2.5">$1</h1>');

        // Bold & Italic
        processed = processed.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
        processed = processed.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900 dark:text-white">$1</strong>');
        processed = processed.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>');

        // Blockquotes
        processed = processed.replace(/^\> (.*$)/gim, '<blockquote class="border-l-4 border-orange-500 pl-3 my-2 italic text-gray-600 dark:text-gray-300">$1</blockquote>');

        // Tables: match all table rows even if EOF or trailing spaces
        processed = processed.replace(/((?:^[ \t]*\|[^\n]*\|[ \t]*(?:\r?\n|$))+)/gm, (tableBlock) => {
            const lines = tableBlock.trim().split(/\r?\n/).map(l => l.trim()).filter(Boolean);
            if (lines.length < 2) return tableBlock;
            if (!/^\|(?:\s*:?-+:?\s*\|)+$/.test(lines[1])) return tableBlock;

            const headers = lines[0].split('|').slice(1, -1).map(h => h.trim());
            const rows = lines.slice(2).map(line => line.split('|').slice(1, -1).map(c => c.trim()));

            let html = '<div class="my-3 overflow-x-auto rounded-xl border border-warm-200 dark:border-zinc-700 shadow-sm"><table class="w-full text-left text-xs border-collapse">';
            html += '<thead class="bg-warm-100 dark:bg-zinc-800 text-gray-800 dark:text-gray-200 uppercase font-semibold"><tr>';
            headers.forEach(h => {
                html += `<th class="px-3 py-2 border-b border-warm-200 dark:border-zinc-700">${h}</th>`;
            });
            html += '</tr></thead><tbody class="divide-y divide-warm-100 dark:divide-zinc-800 bg-white dark:bg-zinc-900">';
            rows.forEach(r => {
                html += '<tr class="hover:bg-warm-50/50 dark:hover:bg-zinc-800/50">';
                r.forEach(c => {
                    html += `<td class="px-3 py-2 text-gray-700 dark:text-gray-300">${c}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table></div>';
            return html;
        });

        // Unordered Lists
        processed = processed.replace(/^\s*[\-\*]\s+(.*$)/gim, '<li class="ml-4 list-disc">$1</li>');
        // Ordered Lists
        processed = processed.replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li class="ml-4 list-decimal" value="$1">$2</li>');

        processed = processed.replace(/((?:<li class="ml-4 list-disc">.*?<\/li>\s*)+)/gis, '<ul class="my-2 space-y-1">$1</ul>');
        processed = processed.replace(/((?:<li class="ml-4 list-decimal".*?<\/li>\s*)+)/gis, '<ol class="my-2 space-y-1">$1</ol>');

        // Horizontal Rules
        processed = processed.replace(/^---$/gim, '<hr class="my-4 border-warm-200 dark:border-zinc-700"/>');

        // Paragraphs
        const paras = processed.split(/\n{2,}/);
        return paras.map(p => {
            p = p.trim();
            if (!p) return '';
            if (/^<(h\d|pre|table|ul|ol|blockquote|div|hr)/.test(p)) return p;
            return `<p class="my-1.5 leading-relaxed">${p.replace(/\n/g, '<br/>')}</p>`;
        }).join('');
    };

    const request = async (url, options = {}) => {
        const headers = { ...options.headers, 'X-CSRFToken': csrfToken };
        if (options.body) headers['Content-Type'] = 'application/json';
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.error?.message || 'Request failed.');
        }
        return response.status === 204 ? null : response.json();
    };

    const scrollToBottom = () => {
        if (scrollContainer) {
            scrollContainer.scrollTop = scrollContainer.scrollHeight;
        }
    };

    const setStatus = (text, error = false) => {
        status.textContent = text;
        status.className = error
            ? 'rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300'
            : 'rounded-xl border border-warm-200 bg-warm-50 p-3 text-sm text-gray-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-gray-300';
        status.classList.remove('hidden');
        scrollToBottom();
    };

    const modelNamesMap = new Map();
    let defaultModelId = '';
    let defaultModelProvider = '';
    let modelCatalog = [];

    const getProviderIconPath = (provider) => {
        const key = String(provider || '').trim().toLowerCase();
        if (key.includes('gemini')) return '/static/icons/ai_gemini.svg';
        if (key.includes('openrouter')) return '/static/icons/ai_openrouter.svg';
        if (key.includes('ollama')) return '/static/icons/ai_ollama.svg';
        if (key.includes('vercel')) return '/static/icons/ai_vercel.svg';
        return '';
    };

    const formatToolName = (name) => (name || '').replace(/^kinetiqo_/, '').replace(/_/g, ' ');

    const renderChartJsInElement = (rootElement) => {
        if (!rootElement || typeof window.Chart === 'undefined') return;

        const containers = rootElement.querySelectorAll('.chat-chart-container');
        if (!containers || containers.length === 0) return;

        const isDark = document.documentElement.classList.contains('dark') || document.body.classList.contains('dark');
        const defaultTextColor = isDark ? '#d4d4d8' : '#374151';
        const defaultGridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)';

        containers.forEach(container => {
            if (container.dataset.rendered === 'true') return;

            const codeEl = container.querySelector('.chat-chart-code code');
            const canvas = container.querySelector('.chat-chart-canvas');
            const wrapper = container.querySelector('.chat-chart-canvas-wrapper');
            const toggleBtn = container.querySelector('.chat-chart-toggle');
            const codePre = container.querySelector('.chat-chart-code');

            if (!codeEl || !canvas || !wrapper) return;
            const codeText = codeEl.textContent.trim();
            if (!codeText) return;

            if (toggleBtn && !toggleBtn._hooked) {
                toggleBtn._hooked = true;
                toggleBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const isCodeHidden = codePre.classList.contains('hidden');
                    const span = toggleBtn.querySelector('span');
                    if (isCodeHidden) {
                        codePre.classList.remove('hidden');
                        wrapper.classList.add('hidden');
                        if (span) span.textContent = 'View chart';
                    } else {
                        codePre.classList.add('hidden');
                        wrapper.classList.remove('hidden');
                        if (span) span.textContent = 'View code';
                    }
                });
            }

            try {
                let cleanJson = codeText
                    .replace(/\/\/.*$/gm, '')
                    .replace(/,(\s*[\]}])/g, '$1');
                const config = JSON.parse(cleanJson);

                if (!config.options) config.options = {};
                config.options.responsive = true;
                config.options.maintainAspectRatio = false;

                if (!config.options.plugins) config.options.plugins = {};
                if (!config.options.plugins.legend) config.options.plugins.legend = {};
                if (!config.options.plugins.legend.labels) config.options.plugins.legend.labels = {};
                if (!config.options.plugins.legend.labels.color) config.options.plugins.legend.labels.color = defaultTextColor;

                if (config.options.plugins.title) {
                    if (!config.options.plugins.title.color) {
                        config.options.plugins.title.color = defaultTextColor;
                    }
                    const titleText = Array.isArray(config.options.plugins.title.text)
                        ? config.options.plugins.title.text.join(' ')
                        : String(config.options.plugins.title.text || '');
                    const titleSpan = container.querySelector('.chat-chart-title');
                    if (titleSpan && titleText.trim()) {
                        titleSpan.textContent = titleText.trim();
                    }
                }

                if (config.options.scales) {
                    Object.keys(config.options.scales).forEach(scaleKey => {
                        const scale = config.options.scales[scaleKey];
                        if (scale) {
                            if (!scale.ticks) scale.ticks = {};
                            if (!scale.ticks.color) scale.ticks.color = defaultTextColor;
                            if (!scale.ticks.backdropColor) scale.ticks.backdropColor = 'transparent';
                            if (!scale.grid) scale.grid = {};
                            if (!scale.grid.color) scale.grid.color = defaultGridColor;
                            if (!scale.angleLines) scale.angleLines = {};
                            if (!scale.angleLines.color) scale.angleLines.color = defaultGridColor;
                            if (!scale.pointLabels) scale.pointLabels = {};
                            if (!scale.pointLabels.color) scale.pointLabels.color = defaultTextColor;
                            if (scale.title && !scale.title.color) scale.title.color = defaultTextColor;
                        }
                    });
                }

                if (canvas._chartInstance) {
                    canvas._chartInstance.destroy();
                    canvas._chartInstance = null;
                }

                const ctx = canvas.getContext('2d');
                canvas._chartInstance = new window.Chart(ctx, config);
                container.dataset.rendered = 'true';
            } catch (err) {
                console.warn('Chart.js render error:', err);
                wrapper.innerHTML = `<div class="text-xs text-amber-600 dark:text-amber-400 py-1.5 px-1 flex items-center gap-1.5"><svg class="w-3.5 h-3.5 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><span>Chart preview error (${escapeHtml(err.message)}). Source displayed below.</span></div>`;
                if (codePre) codePre.classList.remove('hidden');
                if (toggleBtn) {
                    const span = toggleBtn.querySelector('span');
                    if (span) span.textContent = 'View chart';
                }
                container.dataset.rendered = 'error';
            }
        });
    };

    const observeThemeChangesForCharts = () => {
        try {
            const observer = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    if (m.attributeName === 'class') {
                        document.querySelectorAll('.chat-chart-container').forEach(c => {
                            c.dataset.rendered = 'false';
                            renderChartJsInElement(c.closest('article') || c.parentElement);
                        });
                        break;
                    }
                }
            });
            observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        } catch (err) {
            console.warn('Failed to observe theme changes for charts:', err);
        }
    };

    const refreshSeparators = (footer) => {
        const provSlot = footer.querySelector('.chat-provenance-slot');
        const modelBadge = footer.querySelector('.chat-model-badge');
        const badge = footer.querySelector('.chat-tokens-badge');
        const thinkingBadge = footer.querySelector('.chat-thinking-badge');
        const downloadBtns = footer.querySelectorAll('.chat-download-btn');

        const sepProv = footer.querySelector('.chat-footer-sep-prov');
        const sepModel = footer.querySelector('.chat-footer-sep-model');
        const sepTokens = footer.querySelector('.chat-footer-sep-tokens');

        const hasProv = Boolean(provSlot && provSlot.children.length > 0);
        const hasModel = Boolean(modelBadge && modelBadge.textContent.trim().length > 0);
        const hasTokens = Boolean(badge && !badge.classList.contains('hidden') && badge.textContent.trim().length > 0);
        const hasThinking = Boolean(thinkingBadge && !thinkingBadge.classList.contains('hidden') && thinkingBadge.textContent.trim().length > 0);
        const hasDownload = Boolean(Array.from(downloadBtns).some((btn) => {
            const hiddenByClass = btn.classList.contains('hidden');
            const hiddenByAttr = btn.hasAttribute('hidden');
            const hiddenByStyle = btn.style.display === 'none';
            return !(hiddenByClass || hiddenByAttr || hiddenByStyle);
        }));

        if (sepProv) {
            sepProv.classList.toggle('hidden', !(hasProv && (hasModel || hasThinking || hasTokens || hasDownload)));
        }
        if (sepModel) {
            sepModel.classList.toggle('hidden', !(hasModel && (hasThinking || hasTokens || hasDownload)));
        }
        if (sepTokens) {
            sepTokens.classList.toggle('hidden', !(hasTokens && hasDownload));
        }
    };

    const updateFooterModel = (article, modelId) => {
        if (!modelId) return;
        article._modelId = modelId;
        const footer = ensureFooter(article);
        const modelBadge = footer.querySelector('.chat-model-badge');
        if (!modelBadge) return;
        const displayName = modelNamesMap.get(modelId) || modelId;
        modelBadge.textContent = displayName;
        modelBadge.title = `Model: ${modelId}`;
        refreshSeparators(footer);
    };

    const appendProvenance = (article, rawProvenance) => {
        let records = [];
        try {
            records = typeof rawProvenance === 'string' ? JSON.parse(rawProvenance) : (Array.isArray(rawProvenance) ? rawProvenance : []);
        } catch {
            return;
        }
        if (!Array.isArray(records) || records.length === 0) return;

        const footer = ensureFooter(article);
        const slot = footer.querySelector('.chat-provenance-slot');
        const contentBox = footer.querySelector('.chat-provenance-content');
        const ul = contentBox?.querySelector('ul');
        if (!slot || !contentBox || !ul) return;

        slot.replaceChildren();
        ul.replaceChildren();

        const countText = `${records.length} local ${records.length === 1 ? 'query' : 'queries'}`;
        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'chat-provenance-btn cursor-pointer inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-orange-600 dark:text-zinc-400 dark:hover:text-orange-400 transition';
        toggleBtn.title = 'View local data queries used';
        toggleBtn.setAttribute('aria-expanded', 'false');
        toggleBtn.innerHTML = `
            <span>Data used (${countText})</span>
            <svg class="chat-provenance-chevron w-3 h-3 transition-transform duration-150 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
        `;

        records.forEach((rec) => {
            const li = document.createElement('li');
            li.className = 'chat-provenance-item';
            const toolName = formatToolName(rec.tool);
            const duration = rec.duration_ms ? ` (${rec.duration_ms}ms)` : '';
            li.textContent = `${toolName}${duration}`;
            ul.appendChild(li);
        });

        toggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const isHidden = contentBox.classList.toggle('hidden');
            toggleBtn.setAttribute('aria-expanded', (!isHidden).toString());
            const chevron = toggleBtn.querySelector('.chat-provenance-chevron');
            if (chevron) {
                chevron.classList.toggle('rotate-180', !isHidden);
            }
            scrollToBottom();
        });

        slot.appendChild(toggleBtn);
        refreshSeparators(footer);
    };

    const ensureFooter = (article) => {
        let footer = article.querySelector('.chat-msg-footer');
        if (!footer) {
            footer = document.createElement('div');
            footer.className = 'chat-msg-footer mt-4 pt-2.5 flex flex-col select-none';

            const row = document.createElement('div');
            row.className = 'chat-footer-main-row flex items-center justify-end gap-2 text-xs text-gray-500 dark:text-zinc-400 flex-wrap';

            // Provenance toggle slot
            const provSlot = document.createElement('div');
            provSlot.className = 'chat-provenance-slot';
            row.appendChild(provSlot);

            // Separator between provenance and model
            const sepProv = document.createElement('span');
            sepProv.className = 'chat-footer-sep-prov hidden text-gray-300 dark:text-zinc-600 select-none';
            sepProv.textContent = '·';
            row.appendChild(sepProv);

            // Model name badge (same style, font size, and color as tokens badge)
            const modelBadge = document.createElement('span');
            modelBadge.className = 'chat-model-badge text-xs text-gray-500 dark:text-zinc-400 whitespace-nowrap';
            row.appendChild(modelBadge);

            // Separator between model and tokens (or download)
            const sepModel = document.createElement('span');
            sepModel.className = 'chat-footer-sep-model hidden text-gray-300 dark:text-zinc-600 select-none';
            sepModel.textContent = '·';
            row.appendChild(sepModel);

            // Tokens & duration badge (same font, style, size, color as Data used)
            const badge = document.createElement('span');
            badge.className = 'chat-tokens-badge text-xs text-gray-500 dark:text-zinc-400 whitespace-nowrap';
            row.appendChild(badge);

            // While generating, display elapsed-time counter in place of download actions.
            const thinkingBadge = document.createElement('span');
            thinkingBadge.className = 'chat-thinking-badge hidden text-xs text-gray-500 dark:text-zinc-400 whitespace-nowrap';
            row.appendChild(thinkingBadge);

            // Separator between tokens and download
            const sepTokens = document.createElement('span');
            sepTokens.className = 'chat-footer-sep-tokens hidden text-gray-300 dark:text-zinc-600 select-none';
            sepTokens.textContent = '·';
            row.appendChild(sepTokens);

            // Download response as Markdown (.md) button
            const downloadMdBtn = document.createElement('button');
            downloadMdBtn.type = 'button';
            downloadMdBtn.className = 'chat-download-btn chat-download-md-btn cursor-pointer inline-flex items-center gap-1 text-xs text-gray-500 hover:text-orange-600 dark:text-zinc-400 dark:hover:text-orange-400 transition';
            downloadMdBtn.title = 'Download response as Markdown (.md)';
            downloadMdBtn.setAttribute('aria-label', 'Download response as Markdown');
            downloadMdBtn.innerHTML = `
                <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" style="color: rgb(163, 163, 163);">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                <svg class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor" style="color: rgb(163, 163, 163);" aria-hidden="true">
                    <path d="M14.85 3H1.15C.52 3 0 3.52 0 4.15v7.69C0 12.48.52 13 1.15 13h13.69c.64 0 1.15-.52 1.15-1.15V4.15C16 3.52 15.48 3 14.85 3zM9 11H7V8.5L5.5 10 4 8.5V11H2V5h2l1.5 2L7 5h2v6zm2.5 0L9 7.5h1.5V5h2v2.5H14L11.5 11z"/>
                </svg>
            `;
            downloadMdBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const mdContent = article._rawMarkdown || article.querySelector('.chat-text')?.textContent || '';
                if (!mdContent) return;
                const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                a.download = `kinetiqo-response-${ts}.md`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            });
            row.appendChild(downloadMdBtn);

            // Download response as HTML (.html) button
            const downloadHtmlBtn = document.createElement('button');
            downloadHtmlBtn.type = 'button';
            downloadHtmlBtn.className = 'chat-download-btn chat-download-html-btn cursor-pointer inline-flex items-center gap-1 text-xs text-gray-500 hover:text-orange-600 dark:text-zinc-400 dark:hover:text-orange-400 transition';
            downloadHtmlBtn.title = 'Download response as HTML (.html)';
            downloadHtmlBtn.setAttribute('aria-label', 'Download response as HTML');
            downloadHtmlBtn.innerHTML = `
                <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" style="color: rgb(163, 163, 163);">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                <svg class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor" style="color: rgb(163, 163, 163);" aria-hidden="true">
                    <path d="M1.5 0h21l-1.91 21.563L11.977 24l-8.564-2.438L1.5 0zm7.031 9.75l-.232-2.718 10.059-.003.23-2.622L5.412 4.41l.698 8.01h9.126l-.326 3.426-2.91.804-2.955-.81-.188-2.11H6.248l.33 4.171L12 19.351l5.379-1.443.744-8.158H8.531z"/>
                </svg>
            `;
            downloadHtmlBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                const textContainer = article.querySelector('.chat-text');
                if (!textContainer) return;

                const clone = textContainer.cloneNode(true);

                // Preserve rendered charts as embedded base64 images
                const origChartContainers = article.querySelectorAll('.chat-chart-container');
                const cloneChartContainers = clone.querySelectorAll('.chat-chart-container');
                origChartContainers.forEach((origC, idx) => {
                    const cloneC = cloneChartContainers[idx];
                    if (!cloneC) return;
                    const origCanvas = origC.querySelector('canvas');
                    if (origCanvas) {
                        try {
                            const dataUrl = origCanvas.toDataURL('image/png');
                            const img = document.createElement('img');
                            img.src = dataUrl;
                            img.alt = 'Chart';
                            img.style.maxWidth = '100%';
                            img.style.height = 'auto';
                            const wrapper = cloneC.querySelector('.chat-chart-canvas-wrapper');
                            if (wrapper) wrapper.replaceWith(img);
                        } catch (err) {
                            console.warn('Failed to convert chart canvas to data URL:', err);
                        }
                    }
                    const toggleHeader = cloneC.firstElementChild;
                    const codePre = cloneC.querySelector('.chat-chart-code');
                    if (toggleHeader) toggleHeader.remove();
                    if (codePre) codePre.remove();
                });

                clone.querySelectorAll('*').forEach(el => {
                    if (el.closest('svg')) return;
                    el.removeAttribute('class');
                    el.removeAttribute('style');
                });

                const imgs = Array.from(clone.querySelectorAll('img'));
                for (const img of imgs) {
                    const src = img.getAttribute('src');
                    if (src && !src.startsWith('data:')) {
                        try {
                            const res = await fetch(src);
                            const blob = await res.blob();
                            const base64 = await new Promise((resolve, reject) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.onerror = reject;
                                reader.readAsDataURL(blob);
                            });
                            img.setAttribute('src', base64);
                        } catch (err) {
                            console.warn('Failed to encode image to base64:', err);
                        }
                    }
                }

                const cleanBody = clone.innerHTML.trim();
                const fullHtml = `<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <title>Kinetiqo Response</title>\n</head>\n<body>\n${cleanBody}\n</body>\n</html>`;

                const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                a.download = `kinetiqo-response-${ts}.html`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            });
            row.appendChild(downloadHtmlBtn);

            footer.appendChild(row);

            // Collapsible provenance content list (no extra background, right-aligned)
            const contentBox = document.createElement('div');
            contentBox.className = 'chat-provenance-content hidden mt-2 text-xs text-right';
            const ul = document.createElement('ul');
            ul.className = 'chat-provenance-list space-y-1';
            contentBox.appendChild(ul);
            footer.appendChild(contentBox);

            article.appendChild(footer);
            refreshSeparators(footer);
        }
        return footer;
    };

    const setDownloadButtonsState = (article, visible) => {
        const footer = ensureFooter(article);
        const downloadBtns = footer.querySelectorAll('.chat-download-btn');
        downloadBtns.forEach((btn) => {
            if (visible) {
                btn.classList.remove('hidden', 'opacity-60', 'pointer-events-none', 'cursor-not-allowed');
                btn.removeAttribute('hidden');
                btn.style.display = '';
                btn.disabled = false;
                btn.setAttribute('aria-disabled', 'false');
                return;
            }
            btn.classList.add('hidden', 'opacity-60', 'pointer-events-none', 'cursor-not-allowed');
            btn.setAttribute('hidden', 'hidden');
            btn.style.display = 'none';
            btn.disabled = true;
            btn.setAttribute('aria-disabled', 'true');
        });
    };

    const setFooterThinkingState = (article, elapsedSeconds) => {
        const footer = ensureFooter(article);
        const thinkingBadge = footer.querySelector('.chat-thinking-badge');
        const tokensBadge = footer.querySelector('.chat-tokens-badge');

        article._isThinking = true;
        if (thinkingBadge) {
            const safeSeconds = Math.max(0, Number.parseInt(String(elapsedSeconds || 0), 10) || 0);
            thinkingBadge.textContent = `Thinking for ${safeSeconds}s`;
            thinkingBadge.classList.remove('hidden');
        }
        if (tokensBadge) {
            tokensBadge.classList.add('hidden');
        }
        setDownloadButtonsState(article, false);
        refreshSeparators(footer);
    };

    const clearFooterThinkingState = (article) => {
        const footer = ensureFooter(article);
        const thinkingBadge = footer.querySelector('.chat-thinking-badge');
        const tokensBadge = footer.querySelector('.chat-tokens-badge');

        article._isThinking = false;
        if (thinkingBadge) {
            thinkingBadge.textContent = '';
            thinkingBadge.classList.add('hidden');
        }
        if (tokensBadge) {
            tokensBadge.classList.remove('hidden');
        }
        if (!article._hideDownloadsPermanently) {
            setDownloadButtonsState(article, true);
        }
        refreshSeparators(footer);
    };

    const updateFooterInfo = (article, inTokens = null, outTokens = null, durationStr = null) => {
        const footer = ensureFooter(article);
        const badge = footer.querySelector('.chat-tokens-badge');
        if (!badge) return;

        if (inTokens !== undefined && inTokens !== null) article._inTokens = inTokens;
        if (outTokens !== undefined && outTokens !== null) article._outTokens = outTokens;
        if (durationStr !== undefined && durationStr !== null) article._durationStr = durationStr;

        const currentIn = article._inTokens;
        const currentOut = article._outTokens;
        const currentDur = article._durationStr;

        const parts = [];
        if (currentIn !== null && currentIn !== undefined) parts.push(`${Number(currentIn).toLocaleString()} in`);
        if (currentOut !== null && currentOut !== undefined) parts.push(`${Number(currentOut).toLocaleString()} out`);

        if (parts.length > 0) {
            let text = `Tokens: ${parts.join(' · ')}`;
            if (currentDur) {
                text += ` · ${currentDur}`;
            }
            badge.textContent = text;
        } else if (currentDur) {
            badge.textContent = currentDur;
        } else {
            badge.textContent = '';
        }

        badge.classList.toggle('hidden', Boolean(article._isThinking));

        refreshSeparators(footer);
    };

    const messageNode = (role, content = '', toolProvenance = null, inputTokens = null, outputTokens = null, modelId = null) => {
        const article = document.createElement('article');
        article.dataset.role = role;

        if (role === 'user') {
            article.className = 'chat-msg-user';
            article.style.cssText = 'margin-left: auto; max-width: 85%; border-radius: 16px 16px 4px 16px; background: #ea580c; color: white; padding: 12px 18px; font-size: 14px; line-height: 1.5; word-break: break-word; box-shadow: 0 1px 2px rgba(0,0,0,0.06);';

            const senderHeader = document.createElement('div');
            senderHeader.className = 'chat-sender-header';
            senderHeader.style.cssText = 'display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-bottom: 6px; font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.92);';
            const nameEl = document.createElement('span');
            nameEl.textContent = userName || 'Athlete';
            senderHeader.appendChild(nameEl);
            article.appendChild(senderHeader);
        } else {
            article.className = 'chat-msg-assistant';
            const isDark = document.documentElement.classList.contains('dark') || document.body.classList.contains('dark');
            const bg = isDark ? '#262629' : '#ffffff';
            const color = isDark ? '#f4f4f5' : '#1f2937';
            const border = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
            article.style.cssText = `margin-right: auto; width: 100%; max-width: 100%; border-radius: 16px; background: ${bg}; color: ${color}; padding: 18px 22px; font-size: 14px; line-height: 1.6; word-break: break-word; border: 1px solid ${border}; box-shadow: 0 1px 3px rgba(0,0,0,0.04);`;
        }

        const textContainer = document.createElement('div');
        textContainer.className = 'chat-text';
        if (role === 'assistant') {
            article._rawMarkdown = content;
            textContainer.innerHTML = renderMarkdown(content);
            renderChartJsInElement(article);
        } else {
            textContainer.textContent = content;
        }
        article.appendChild(textContainer);

        if (toolProvenance) {
            appendProvenance(article, toolProvenance);
        }
        if (role === 'assistant') {
            ensureFooter(article);
            if (modelId) {
                updateFooterModel(article, modelId);
            }
            if (inputTokens || outputTokens) {
                updateFooterInfo(article, inputTokens, outputTokens);
            }
        }
        messages.appendChild(article);
        scrollToBottom();
        return article;
    };

    try {
        localStorage.removeItem('kinetiqo_chat_prompt_history');
    } catch (_) {}

    const suggestionPrompts = (() => {
        try {
            const raw = app.dataset.initialPrompts;
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    })();

    const loadAllPrompts = async () => {
        try {
            const payload = await request('/api/chat/prompts');
            if (payload && Array.isArray(payload.prompts)) {
                payload.prompts.forEach((p) => {
                    const clean = (p || '').trim();
                    if (clean && !suggestionPrompts.includes(clean)) {
                        suggestionPrompts.push(clean);
                    }
                });
            }
        } catch {
            // Silently ignore if background prompt fetch fails
        }
    };

    // Prompt history browsing strictly scoped to user turns in the active chat (not localStorage)
    let currentChatHistory = [];
    let historyIndex = -1;
    let currentDraft = '';

    const recordUserPrompt = (text) => {
        const clean = (text || '').trim();
        if (!clean) return;
        if (currentChatHistory.length === 0 || currentChatHistory[currentChatHistory.length - 1] !== clean) {
            currentChatHistory.push(clean);
        }
        if (!suggestionPrompts.includes(clean)) {
            suggestionPrompts.push(clean);
        }
        historyIndex = -1;
        currentDraft = '';
    };

    const resetChatHistory = () => {
        currentChatHistory = [];
        historyIndex = -1;
        currentDraft = '';
    };

    const showMessages = (list) => {
        messages.replaceChildren();
        currentChatHistory = [];
        (list || []).forEach((item) => {
            messageNode(item.role, item.content, item.tool_provenance, item.input_tokens, item.output_tokens, item.model_id);
            if (item.role === 'user' && typeof item.content === 'string') {
                const clean = item.content.trim();
                if (clean && (currentChatHistory.length === 0 || currentChatHistory[currentChatHistory.length - 1] !== clean)) {
                    currentChatHistory.push(clean);
                }
                if (clean && !suggestionPrompts.includes(clean)) {
                    suggestionPrompts.push(clean);
                }
            }
        });
        historyIndex = -1;
        currentDraft = '';
        empty.classList.toggle('hidden', (list || []).length > 0);
        status.classList.add('hidden');
        scrollToBottom();
    };

    const isDefaultModel = (modelId, provider) => {
        if (!defaultModelId || !modelId || modelId !== defaultModelId) return false;
        if (!defaultModelProvider) return true;
        return (provider || '') === defaultModelProvider;
    };

    const getModelMenuItems = () => {
        if (!modelMenu) return [];
        return Array.from(modelMenu.querySelectorAll('.chat-model-item'));
    };

    const getFocusedModelItemIndex = () => {
        const items = getModelMenuItems();
        const active = document.activeElement;
        return items.findIndex((item) => item === active);
    };

    const focusModelItemByIndex = (index) => {
        const items = getModelMenuItems();
        if (items.length === 0) return;
        const safeIndex = Math.max(0, Math.min(index, items.length - 1));
        items[safeIndex].focus();
    };

    const closeModelDropdown = (restoreFocus = false) => {
        if (!modelMenu || !modelTrigger) return;
        modelMenu.classList.remove('open');
        modelTrigger.setAttribute('aria-expanded', 'false');
        if (restoreFocus) {
            modelTrigger.focus();
        }
    };

    const openModelDropdown = (focusMode = null) => {
        if (!modelMenu || !modelTrigger) return;
        modelMenu.classList.add('open');
        modelTrigger.setAttribute('aria-expanded', 'true');
        if (!focusMode) return;

        const items = getModelMenuItems();
        if (items.length === 0) return;

        let targetIndex = 0;
        if (focusMode === 'selected') {
            const selectedIndex = items.findIndex((item) => item.dataset.modelId === model.value);
            targetIndex = selectedIndex >= 0 ? selectedIndex : 0;
        } else if (focusMode === 'last') {
            targetIndex = items.length - 1;
        } else if (focusMode === 'first') {
            targetIndex = 0;
        }

        window.requestAnimationFrame(() => {
            focusModelItemByIndex(targetIndex);
        });
    };

    const toggleModelDropdown = () => {
        if (!modelMenu || !modelTrigger) return;
        const isOpen = modelMenu.classList.contains('open');
        if (isOpen) {
            closeModelDropdown();
        } else {
            openModelDropdown();
        }
    };

    const updateActiveModelDisplay = () => {
        if (!model) return;
        const selectedOpt = model.options[model.selectedIndex];
        const selectedLabel = selectedOpt ? (selectedOpt.text || selectedOpt.value) : (model.value || '');
        const selectedProvider = selectedOpt?.dataset.provider || '';
        if (activeModelBadge) {
            activeModelBadge.textContent = selectedLabel;
        }
        if (modelSelectedLabel) {
            modelSelectedLabel.textContent = selectedLabel;
        }
        if (modelDefaultIndicator) {
            modelDefaultIndicator.classList.toggle('visible', isDefaultModel(model.value, selectedProvider));
        }
        if (modelMenu) {
            modelMenu.querySelectorAll('.chat-model-item').forEach((itemEl) => {
                const isSelected = itemEl.dataset.modelId === model.value;
                itemEl.classList.toggle('is-selected', isSelected);
                itemEl.setAttribute('aria-selected', isSelected ? 'true' : 'false');
                const starEl = itemEl.querySelector('.chat-model-item-default-star');
                if (starEl) {
                    const itemProvider = itemEl.dataset.provider || '';
                    starEl.classList.toggle('visible', isDefaultModel(itemEl.dataset.modelId || '', itemProvider));
                }
            });
        }
    };

    const renderModelDropdown = () => {
        if (!modelMenu || !model) return;
        modelMenu.replaceChildren();
        if (!modelCatalog.length) {
            return;
        }

        const grouped = new Map();
        modelCatalog.forEach((item) => {
            const key = item.provider || 'unknown';
            if (!grouped.has(key)) {
                grouped.set(key, { label: item.groupLabel || key, items: [] });
            }
            grouped.get(key).items.push(item);
        });

        grouped.forEach((group) => {
            const groupEl = document.createElement('div');
            groupEl.className = 'chat-model-group';

            const headerEl = document.createElement('div');
            headerEl.className = 'chat-model-group-header';

            const groupProviderKey = String(group.items[0]?.provider || '').trim().toLowerCase();
            const groupIconPath = getProviderIconPath(groupProviderKey);
            if (groupIconPath) {
                const groupIconImg = document.createElement('img');
                groupIconImg.className = 'chat-model-group-icon';
                groupIconImg.src = groupIconPath;
                groupIconImg.alt = '';
                groupIconImg.dataset.provider = groupProviderKey;
                groupIconImg.setAttribute('aria-hidden', 'true');
                headerEl.appendChild(groupIconImg);
            }

            const labelEl = document.createElement('div');
            labelEl.className = 'chat-model-group-label';
            labelEl.textContent = group.label;
            headerEl.appendChild(labelEl);
            groupEl.appendChild(headerEl);

            group.items.forEach((item) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'chat-model-item';
                btn.dataset.modelId = item.id;
                btn.dataset.provider = item.provider;
                btn.setAttribute('role', 'option');
                btn.setAttribute('aria-selected', 'false');

                const mainWrap = document.createElement('span');
                mainWrap.className = 'chat-model-item-main';


                const textEl = document.createElement('span');
                textEl.className = 'chat-model-item-label';
                textEl.textContent = item.name;
                mainWrap.appendChild(textEl);

                const starEl = document.createElement('span');
                starEl.className = 'chat-model-item-default-star';
                starEl.setAttribute('aria-hidden', 'true');
                starEl.textContent = '★';

                btn.appendChild(mainWrap);
                btn.appendChild(starEl);
                btn.id = `chat-model-item-${item.provider}-${item.id}`.replace(/[^a-zA-Z0-9_-]/g, '-');
                btn.addEventListener('click', () => {
                    model.value = item.id;
                    model.dispatchEvent(new Event('change', { bubbles: true }));
                    closeModelDropdown(true);
                });

                groupEl.appendChild(btn);
            });

            modelMenu.appendChild(groupEl);
        });

        updateActiveModelDisplay();
    };

    const getSelectedProvider = () => {
        const selectedOpt = model?.options[model.selectedIndex];
        return selectedOpt?.dataset.provider || 'gemini';
    };

    const getSelectedModelId = () => {
        return model?.value || '';
    };

    const loadModels = async () => {
        const payload = await request('/api/chat/models?provider=all');
        const groups = Array.isArray(payload.providers) ? payload.providers : [];
        const serverDefault = payload.default_model || null;
        const flatModels = [];
        modelNamesMap.clear();
        modelCatalog = [];
        model.replaceChildren();

        if (groups.length === 0) {
            // Fallback: try individual providers if grouped returned empty
            const geminiPayload = await request('/api/chat/models?provider=gemini').catch(() => ({ models: [] }));
            const geminiModels = geminiPayload.models || [];
            if (geminiModels.length > 0) {
                groups.push({
                    provider: 'gemini',
                    display_name: 'Google Gemini',
                    models: geminiModels
                });
            }
        }

        if (groups.length === 0) {
            throw new Error('No AI models are available. Please configure an API key in Settings.');
        }

        groups.forEach((group) => {
            const displayName = group.display_name || group.provider;
            const optgroup = document.createElement('optgroup');
            optgroup.label = displayName;
            (group.models || []).forEach((item) => {
                if (item.enabled === false) return;
                const modelName = item.display_name || item.name || item.id;
                modelNamesMap.set(item.id, modelName);
                const option = document.createElement('option');
                option.value = item.id;
                option.dataset.provider = group.provider;
                option.textContent = modelName;
                optgroup.appendChild(option);
                flatModels.push({ ...item, provider: group.provider });
                modelCatalog.push({
                    id: item.id,
                    provider: group.provider,
                    groupLabel: displayName,
                    name: modelName
                });
            });
            if (optgroup.children.length > 0) {
                model.appendChild(optgroup);
            }
        });

        if (flatModels.length === 0) {
            throw new Error('No AI models found for your configured providers.');
        }

        const savedModel = localStorage.getItem('kinetiqo_chat_model');
        const priorValue = model.value;
        const matchedServerDefault = serverDefault
            && flatModels.some((item) => item.id === serverDefault.model_id && (!serverDefault.provider || item.provider === serverDefault.provider));

        const matchedSaved = savedModel && flatModels.some((item) => item.id === savedModel);
        const preferred = (matchedServerDefault ? flatModels.find((item) => item.id === serverDefault.model_id && (!serverDefault.provider || item.provider === serverDefault.provider)) : null)
            || (matchedSaved ? flatModels.find((item) => item.id === savedModel) : null)
            || flatModels.find((item) => item.id === priorValue)
            || PREFERRED_MODELS.map((p) => flatModels.find((item) => item.id === p)).find(Boolean)
            || flatModels[0];

        const defaultChoice = (matchedServerDefault
            ? flatModels.find((item) => item.id === serverDefault.model_id && (!serverDefault.provider || item.provider === serverDefault.provider))
            : null) || preferred;

        defaultModelId = defaultChoice?.id || '';
        defaultModelProvider = defaultChoice?.provider || '';

        model.value = preferred.id;
        localStorage.setItem('kinetiqo_chat_model', preferred.id);
        renderModelDropdown();
        updateActiveModelDisplay();

        // Refresh model badges in already-rendered messages
        document.querySelectorAll('.chat-msg-assistant').forEach((art) => {
            if (art._modelId) updateFooterModel(art, art._modelId);
        });
    };

    let sessionsCache = [];

    model.addEventListener('change', () => {
        localStorage.setItem('kinetiqo_chat_model', model.value);
        updateActiveModelDisplay();
        if (sessionId) {
            request(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
                method: 'PATCH',
                body: JSON.stringify({ provider: getSelectedProvider(), model_id: model.value })
            }).catch((err) => {
                console.warn('Failed to persist session model change:', err);
            });
        }
    });

    if (modelTrigger) {
        modelTrigger.addEventListener('click', () => {
            toggleModelDropdown();
        });
        modelTrigger.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                openModelDropdown('selected');
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                openModelDropdown('last');
            } else if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openModelDropdown('selected');
            } else if (e.key === 'Escape') {
                closeModelDropdown(true);
            }
        });
    }

    if (modelMenu) {
        modelMenu.addEventListener('keydown', (e) => {
            const items = getModelMenuItems();
            if (items.length === 0) return;

            const currentIndex = getFocusedModelItemIndex();
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length;
                focusModelItemByIndex(nextIndex);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prevIndex = currentIndex < 0 ? items.length - 1 : (currentIndex - 1 + items.length) % items.length;
                focusModelItemByIndex(prevIndex);
            } else if (e.key === 'Home') {
                e.preventDefault();
                focusModelItemByIndex(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                focusModelItemByIndex(items.length - 1);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closeModelDropdown(true);
            } else if (e.key === 'Tab') {
                closeModelDropdown(false);
            }
        });
    }

    const loadSessions = async () => {
        const payload = await request('/api/chat/sessions');
        sessionsCache = payload.sessions || [];
        sessions.replaceChildren();
        sessionsCache.forEach((item) => {
            const itemDiv = document.createElement('div');
            const isActive = item.session_id === sessionId;
            itemDiv.className = `chat-session-item group ${isActive ? 'active' : ''}`;
            itemDiv.setAttribute('role', 'button');
            itemDiv.setAttribute('tabindex', '0');
            itemDiv.title = item.title;

            const titleSpan = document.createElement('span');
            titleSpan.className = 'chat-session-title';
            titleSpan.textContent = item.title;
            itemDiv.appendChild(titleSpan);

            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'chat-session-delete';
            deleteBtn.title = 'Delete conversation';
            deleteBtn.setAttribute('aria-label', `Delete conversation ${item.title}`);
            deleteBtn.innerHTML = `
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            `;
            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                e.preventDefault();
                try {
                    await request(`/api/chat/sessions/${encodeURIComponent(item.session_id)}`, { method: 'DELETE' });
                    if (sessionId === item.session_id) {
                        sessionId = null;
                        history.replaceState(null, '', '/chat');
                        messages.replaceChildren();
                        resetChatHistory();
                        empty.classList.remove('hidden');
                        status.classList.add('hidden');
                    }
                    await loadSessions();
                } catch (err) {
                    setStatus(err.message, true);
                }
            });
            itemDiv.appendChild(deleteBtn);

            itemDiv.addEventListener('click', () => openSession(item.session_id));
            itemDiv.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openSession(item.session_id);
                }
            });
            sessions.appendChild(itemDiv);
        });
    };

    const openSession = async (id) => {
        sessionId = id;
        history.replaceState(null, '', `/chat/${encodeURIComponent(id)}`);
        await loadSessions();
        const currentSession = sessionsCache.find((s) => s.session_id === id);
        if (currentSession && currentSession.model_id) {
            if ([...model.options].some((opt) => opt.value === currentSession.model_id)) {
                model.value = currentSession.model_id;
                updateActiveModelDisplay();
            }
        }
        const payload = await request(`/api/chat/sessions/${encodeURIComponent(id)}/messages`);
        showMessages(payload.messages);
    };

    const createSession = async () => {
        const payload = await request('/api/chat/sessions', {
            method: 'POST',
            body: JSON.stringify({ provider: getSelectedProvider(), model_id: getSelectedModelId() })
        });
        await loadSessions();
        await openSession(payload.session.session_id);
    };

    document.getElementById('new-chat').addEventListener('click', () => {
        sessionId = null;
        history.replaceState(null, '', '/chat');
        messages.replaceChildren();
        resetChatHistory();
        empty.classList.remove('hidden');
        status.classList.add('hidden');
        loadSessions();
    });

    const clearHistoryBtn = document.getElementById('clear-history');
    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener('click', async () => {
            if (!window.confirm('Are you sure you want to delete all chat history? This cannot be undone.')) {
                return;
            }
            try {
                await request('/api/chat/sessions', { method: 'DELETE' });
                sessionId = null;
                history.replaceState(null, '', '/chat');
                messages.replaceChildren();
                resetChatHistory();
                empty.classList.remove('hidden');
                status.classList.add('hidden');
                await loadSessions();
            } catch (err) {
                setStatus(err.message, true);
            }
        });
    }

    document.querySelectorAll('.chat-suggestion').forEach((button) => button.addEventListener('click', () => {
        input.value = button.textContent.trim().replace(/^[^\w]+/, '');
        input.focus();
    }));

    const isCursorOnFirstLine = (textarea) => {
        const selStart = textarea.selectionStart;
        const textBefore = textarea.value.slice(0, selStart);
        return !textBefore.includes('\n');
    };

    const isCursorOnLastLine = (textarea) => {
        const selEnd = textarea.selectionEnd;
        const textAfter = textarea.value.slice(selEnd);
        return !textAfter.includes('\n');
    };

    // Copilot-Style History Autocomplete Suggestions
    let activeSuggestions = [];
    let suggestionSelectedIndex = -1;

    const hideSuggestions = () => {
        if (!suggestionsPopup) return;
        suggestionsPopup.classList.add('hidden');
        suggestionsPopup.classList.remove('visible');
        suggestionsPopup.replaceChildren();
        activeSuggestions = [];
        suggestionSelectedIndex = -1;
    };

    const highlightMatch = (text, query) => {
        if (!query) return escapeHtml(text);
        const qLower = query.toLowerCase();
        const tLower = text.toLowerCase();
        const idx = tLower.indexOf(qLower);
        if (idx === -1) return escapeHtml(text);
        const before = escapeHtml(text.slice(0, idx));
        const match = escapeHtml(text.slice(idx, idx + query.length));
        const after = escapeHtml(text.slice(idx + query.length));
        return `${before}<span class="chat-suggestion-match">${match}</span>${after}`;
    };

    const selectSuggestionItem = (idx) => {
        suggestionSelectedIndex = idx;
        if (!suggestionsPopup) return;
        const items = suggestionsPopup.querySelectorAll('.chat-suggestion-item');
        items.forEach((it, i) => {
            const isSelected = i === idx;
            it.classList.toggle('active', isSelected);
            it.setAttribute('aria-selected', isSelected.toString());
            if (isSelected) {
                it.scrollIntoView({ block: 'nearest' });
            }
        });
    };

    const applySuggestion = (text) => {
        input.value = text;
        hideSuggestions();
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
        historyIndex = -1;
        currentDraft = text;
    };

    const renderSuggestions = (query) => {
        if (!suggestionsPopup) return;
        const cleanQuery = (query || '').trim().toLowerCase();
        if (!cleanQuery) {
            hideSuggestions();
            return;
        }

        const candidates = [...suggestionPrompts].reverse();
        const matched = [];
        const seen = new Set();

        candidates.forEach((prompt) => {
            const pClean = (prompt || '').trim();
            const pLower = pClean.toLowerCase();
            if (!pClean || pLower === cleanQuery) return;
            if (pLower.includes(cleanQuery) && !seen.has(pClean)) {
                seen.add(pClean);
                matched.push(pClean);
            }
        });

        if (matched.length === 0) {
            hideSuggestions();
            return;
        }

        activeSuggestions = matched.slice(0, 5);
        suggestionSelectedIndex = -1;
        suggestionsPopup.replaceChildren();

        activeSuggestions.forEach((prompt, idx) => {
            const item = document.createElement('div');
            item.className = 'chat-suggestion-item';
            item.dataset.index = idx.toString();
            item.setAttribute('role', 'option');
            item.setAttribute('id', `chat-suggestion-opt-${idx}`);
            item.setAttribute('aria-selected', 'false');

            const iconSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            iconSvg.setAttribute('class', 'w-3.5 h-3.5 flex-shrink-0 text-gray-400 dark:text-zinc-500');
            iconSvg.setAttribute('fill', 'none');
            iconSvg.setAttribute('stroke', 'currentColor');
            iconSvg.setAttribute('viewBox', '0 0 24 24');
            iconSvg.setAttribute('aria-hidden', 'true');
            iconSvg.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>';
            item.appendChild(iconSvg);

            const textSpan = document.createElement('span');
            textSpan.className = 'chat-suggestion-text';
            textSpan.innerHTML = highlightMatch(prompt, query.trim());
            item.appendChild(textSpan);

            item.addEventListener('mouseenter', () => {
                selectSuggestionItem(idx);
            });

            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                applySuggestion(prompt);
            });

            suggestionsPopup.appendChild(item);
        });

        const legend = document.createElement('div');
        legend.className = 'chat-suggestion-legend';
        legend.innerHTML = '<span>History suggestions</span><span>↑↓ to navigate · Tab/Enter to choose · Esc to dismiss</span>';
        suggestionsPopup.appendChild(legend);

        suggestionsPopup.classList.remove('hidden');
        suggestionsPopup.classList.add('visible');
    };

    input.addEventListener('input', () => {
        historyIndex = -1;
        currentDraft = input.value;
        renderSuggestions(input.value);
    });

    document.addEventListener('click', (e) => {
        if (suggestionsPopup && !suggestionsPopup.classList.contains('hidden')) {
            if (!composer.contains(e.target) && !suggestionsPopup.contains(e.target)) {
                hideSuggestions();
            }
        }
        if (modelMenu && modelTrigger) {
            const clickedInsideModelDropdown = modelTrigger.contains(e.target) || modelMenu.contains(e.target);
            if (!clickedInsideModelDropdown) {
                closeModelDropdown();
            }
        }
    });

    input.addEventListener('keydown', (e) => {
        const isSuggestionsOpen = suggestionsPopup && !suggestionsPopup.classList.contains('hidden') && activeSuggestions.length > 0;

        if (isSuggestionsOpen) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                suggestionSelectedIndex = (suggestionSelectedIndex + 1) % activeSuggestions.length;
                selectSuggestionItem(suggestionSelectedIndex);
                return;
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                suggestionSelectedIndex = (suggestionSelectedIndex - 1 + activeSuggestions.length) % activeSuggestions.length;
                selectSuggestionItem(suggestionSelectedIndex);
                return;
            } else if (e.key === 'Tab' || (e.key === 'Enter' && suggestionSelectedIndex >= 0)) {
                if (suggestionSelectedIndex >= 0 && suggestionSelectedIndex < activeSuggestions.length) {
                    e.preventDefault();
                    applySuggestion(activeSuggestions[suggestionSelectedIndex]);
                    return;
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                hideSuggestions();
                return;
            }
        }

        if (e.key === 'ArrowUp') {
            if (currentChatHistory.length > 0) {
                if (historyIndex === -1) {
                    if (isCursorOnFirstLine(input)) {
                        currentDraft = input.value;
                        historyIndex = currentChatHistory.length - 1;
                        input.value = currentChatHistory[historyIndex];
                        input.setSelectionRange(input.value.length, input.value.length);
                        e.preventDefault();
                    }
                } else if (historyIndex > 0) {
                    historyIndex--;
                    input.value = currentChatHistory[historyIndex];
                    input.setSelectionRange(input.value.length, input.value.length);
                    e.preventDefault();
                } else if (historyIndex === 0) {
                    e.preventDefault();
                }
            }
        } else if (e.key === 'ArrowDown') {
            if (historyIndex !== -1) {
                if (historyIndex < currentChatHistory.length - 1) {
                    historyIndex++;
                    input.value = currentChatHistory[historyIndex];
                    input.setSelectionRange(input.value.length, input.value.length);
                    e.preventDefault();
                } else {
                    historyIndex = -1;
                    input.value = currentDraft;
                    input.setSelectionRange(input.value.length, input.value.length);
                    e.preventDefault();
                }
            }
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            hideSuggestions();
            composer.requestSubmit();
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    });

    let activeAbortController = null;
    let isResponding = false;

    const cancelCurrentTurn = () => {
        if (activeAbortController) {
            activeAbortController.abort();
        }
    };

    send.addEventListener('click', (e) => {
        if (isResponding) {
            e.preventDefault();
            e.stopPropagation();
            cancelCurrentTurn();
        }
    });

    composer.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (isResponding) {
            cancelCurrentTurn();
            return;
        }
        const content = input.value.trim();
        if (!content) return;
        hideSuggestions();
        historyIndex = -1;
        currentDraft = '';

        const origSendHtml = send.innerHTML;
        const origSendClass = send.className;
        const turnStartTime = performance.now();
        activeAbortController = new AbortController();
        isResponding = true;

        send.className = 'chat-send-btn chat-cancel-btn';
        send.type = 'button';
        send.disabled = false;
        send.title = 'Cancel prompt generation';
        send.setAttribute('aria-label', 'Cancel prompt generation');
        send.innerHTML = '<span class="font-bold text-[13px] leading-none select-none">■</span><span>Cancel</span>';

        let answer = null;
        let thinkingCounterInterval = null;

        try {
            composer.classList.add('composer-responding');
            if (!sessionId) await createSession();
            recordUserPrompt(content);
            status.classList.add('hidden');
            const chosenProvider = getSelectedProvider();
            const chosenModelId = model.value;
            const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ content, model_id: chosenModelId, provider: chosenProvider }),
                signal: activeAbortController.signal
            });
            if (!response.ok || !response.body) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error?.message || 'Chat request failed.');
            }
            input.value = '';
            messageNode('user', content);
            answer = messageNode('assistant', '', null, null, null, chosenModelId);
            ensureFooter(answer);
            answer._hideDownloadsPermanently = false;
            setFooterThinkingState(answer, 0);
            thinkingCounterInterval = window.setInterval(() => {
                const elapsedSeconds = Math.floor((performance.now() - turnStartTime) / 1000);
                setFooterThinkingState(answer, elapsedSeconds);
            }, 1000);
            const answerText = answer.querySelector('.chat-text');
            empty.classList.add('hidden');

            let thinkingEl = document.createElement('div');
            thinkingEl.className = 'chat-loading-indicator flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 py-1';
            thinkingEl.innerHTML = '<img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading" width="18" height="18" class="inline-block"><span>Thinking…</span>';
            answer.insertBefore(thinkingEl, answerText);

            let toolStatusEl = null;
            const executedTools = [];
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let rawAssistantMarkdown = '';

            while (true) {
                const chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, { stream: true });
                const events = buffer.split('\n\n');
                buffer = events.pop();
                events.forEach((raw) => {
                    const eventLine = raw.split('\n').find((line) => line.startsWith('event:'));
                    const dataLine = raw.split('\n').find((line) => line.startsWith('data:'));
                    if (!dataLine) return;
                    const eventType = eventLine?.slice(6).trim();
                    const payload = JSON.parse(dataLine.slice(5));

                    if (eventType === 'tool_call') {
                        if (thinkingEl) {
                            thinkingEl.remove();
                            thinkingEl = null;
                        }
                        if (!toolStatusEl) {
                            toolStatusEl = document.createElement('div');
                            toolStatusEl.className = 'chat-tool-status mb-2 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2';
                            answer.insertBefore(toolStatusEl, answerText);
                        }
                        const toolNum = executedTools.length + 1;
                        toolStatusEl.innerHTML = `<img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading" width="16" height="16" class="inline-block"><span>Consulting ${formatToolName(payload.tool)} (query ${toolNum})…</span>`;
                        executedTools.push({ tool: payload.tool });
                        scrollToBottom();
                    } else if (eventType === 'tool_result') {
                        if (toolStatusEl) {
                            toolStatusEl.innerHTML = `<span class="text-green-500 text-sm font-bold">✓</span><span>Retrieved ${formatToolName(payload.tool)} (${executedTools.length} queries completed)</span>`;
                            scrollToBottom();
                        }
                    } else if (eventType === 'usage') {
                        updateFooterInfo(answer, payload.input_tokens, payload.output_tokens);
                        scrollToBottom();
                    } else if (eventType === 'completed') {
                        if (payload.model_id) {
                            updateFooterModel(answer, payload.model_id);
                            scrollToBottom();
                        }
                    } else if (eventType === 'text_delta') {
                        if (thinkingEl) {
                            thinkingEl.remove();
                            thinkingEl = null;
                        }
                        if (toolStatusEl) {
                            toolStatusEl.remove();
                            toolStatusEl = null;
                        }
                        rawAssistantMarkdown += payload.text || '';
                        answer._rawMarkdown = rawAssistantMarkdown;
                        answerText.innerHTML = renderMarkdown(rawAssistantMarkdown);
                        scrollToBottom();
                    } else if (eventType === 'error') {
                        if (thinkingEl) {
                            thinkingEl.remove();
                            thinkingEl = null;
                        }
                        if (toolStatusEl) {
                            toolStatusEl.remove();
                            toolStatusEl = null;
                        }
                        answerText.innerHTML = `<div class="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300 flex items-start gap-2"><span class="font-bold text-red-500 text-sm leading-none">⚠️</span><span>${escapeHtml(payload.message)}</span></div>`;
                        answer._hideDownloadsPermanently = true;
                        setDownloadButtonsState(answer, false);
                        refreshSeparators(ensureFooter(answer));
                        setStatus(payload.message, true);
                    }
                });
            }

            if (thinkingEl) thinkingEl.remove();
            if (toolStatusEl) toolStatusEl.remove();

            if (rawAssistantMarkdown) {
                answer._rawMarkdown = rawAssistantMarkdown;
                answerText.innerHTML = renderMarkdown(rawAssistantMarkdown);
                renderChartJsInElement(answer);
            }

            const totalDurationSec = `${((performance.now() - turnStartTime) / 1000).toFixed(1)}s`;
            updateFooterInfo(answer, null, null, totalDurationSec);

            if (executedTools.length > 0 && !answer.querySelector('.chat-provenance-btn')) {
                appendProvenance(answer, executedTools);
                scrollToBottom();
            }
            await loadSessions();
        } catch (error) {
            if (error.name === 'AbortError' || activeAbortController?.signal.aborted) {
                const lastAssistant = messages.querySelector('.chat-msg-assistant:last-of-type');
                if (lastAssistant) {
                    const thinking = lastAssistant.querySelector('.chat-loading-indicator');
                    if (thinking) thinking.remove();
                    const toolSt = lastAssistant.querySelector('.chat-tool-status');
                    if (toolSt) toolSt.remove();

                    const answerText = lastAssistant.querySelector('.chat-text');
                    if (answerText) {
                        const cancelPill = document.createElement('div');
                        cancelPill.className = 'chat-cancelled-indicator';
                        cancelPill.innerHTML = '<span class="text-xs font-bold leading-none select-none">■</span><span>Cancelled</span>';
                        if (!lastAssistant._rawMarkdown) {
                            answerText.innerHTML = '<p class="text-xs text-gray-500 dark:text-zinc-400 italic">Prompt cancelled</p>';
                        }
                        lastAssistant.insertBefore(cancelPill, answerText.nextSibling);
                    }
                    renderChartJsInElement(lastAssistant);
                    scrollToBottom();
                }
            } else {
                setStatus(error.message, true);
            }
        } finally {
            if (thinkingCounterInterval) {
                window.clearInterval(thinkingCounterInterval);
            }
            if (answer) {
                clearFooterThinkingState(answer);
            }
            isResponding = false;
            activeAbortController = null;
            send.className = origSendClass;
            send.type = 'submit';
            send.disabled = false;
            send.title = 'Send message';
            send.setAttribute('aria-label', 'Send message');
            send.innerHTML = origSendHtml;
            composer.classList.remove('composer-responding');
            input.focus();
        }
    });

    observeThemeChangesForCharts();

    Promise.all([loadModels(), loadSessions(), loadAllPrompts()])
        .then(() => sessionId ? openSession(sessionId) : null)
        .catch((error) => setStatus(error.message, true));
})();

