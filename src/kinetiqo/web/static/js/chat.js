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

    if (typeof window.marked !== 'undefined' && typeof window.marked.use === 'function') {
        try {
            window.marked.use({
                breaks: true,
                gfm: true,
                renderer: {
                    link({ href, title, text }) {
                        const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
                        return `<a href="${href || '#'}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
                    }
                }
            });
        } catch (err) {
            console.warn('Failed to configure marked:', err);
        }
    }

    const renderMarkdown = (text) => {
        if (!text) return '';
        if (typeof window.marked !== 'undefined' && typeof window.marked.parse === 'function') {
            try {
                return window.marked.parse(text);
            } catch (err) {
                console.warn('Marked parse error, using fallback:', err);
            }
        }
        const codeBlocks = [];
        let processed = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const id = `__CB_${codeBlocks.length}__`;
            codeBlocks.push(`<pre class="my-3 overflow-x-auto rounded-xl bg-zinc-900 p-3 text-xs text-zinc-100 font-mono dark:bg-black/40 border border-zinc-700/60"><code>${escapeHtml(code.trim())}</code></pre>`);
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

    const formatToolName = (name) => (name || '').replace(/^kinetiqo_/, '').replace(/_/g, ' ');

    const refreshSeparators = (footer) => {
        const provSlot = footer.querySelector('.chat-provenance-slot');
        const modelBadge = footer.querySelector('.chat-model-badge');
        const badge = footer.querySelector('.chat-tokens-badge');
        const downloadBtns = footer.querySelectorAll('.chat-download-btn');

        const sepProv = footer.querySelector('.chat-footer-sep-prov');
        const sepModel = footer.querySelector('.chat-footer-sep-model');
        const sepTokens = footer.querySelector('.chat-footer-sep-tokens');

        const hasProv = Boolean(provSlot && provSlot.children.length > 0);
        const hasModel = Boolean(modelBadge && modelBadge.textContent.trim().length > 0);
        const hasTokens = Boolean(badge && badge.textContent.trim().length > 0);
        const hasDownload = Boolean(Array.from(downloadBtns).some(btn => !btn.classList.contains('hidden')));

        if (sepProv) {
            sepProv.classList.toggle('hidden', !(hasProv && (hasModel || hasTokens || hasDownload)));
        }
        if (sepModel) {
            sepModel.classList.toggle('hidden', !(hasModel && (hasTokens || hasDownload)));
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
                clone.querySelectorAll('*').forEach(el => {
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

    const STORAGE_KEY_PROMPTS = 'kinetiqo_chat_prompt_history';
    const MAX_STORED_PROMPTS = 100;

    const initialServerPrompts = (() => {
        try {
            const raw = app.dataset.initialPrompts;
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    })();

    const loadStoredPrompts = () => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY_PROMPTS);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    };

    let promptHistory = [];
    let historyIndex = -1;
    let currentDraft = '';

    const syncPromptHistory = (sessionMessages = null) => {
        const stored = loadStoredPrompts();
        const set = new Set([...initialServerPrompts, ...stored]);
        if (sessionMessages && Array.isArray(sessionMessages)) {
            sessionMessages.filter(m => m.role === 'user').forEach(m => {
                if (m.content && m.content.trim()) set.add(m.content.trim());
            });
        }
        promptHistory = Array.from(set);
    };
    syncPromptHistory();

    const saveStoredPrompt = (text) => {
        if (!text || !text.trim()) return;
        const clean = text.trim();
        let list = loadStoredPrompts().filter(p => p !== clean);
        list.push(clean);
        if (list.length > MAX_STORED_PROMPTS) {
            list = list.slice(-MAX_STORED_PROMPTS);
        }
        try {
            localStorage.setItem(STORAGE_KEY_PROMPTS, JSON.stringify(list));
        } catch (err) {
            console.warn('Failed to save prompt to localStorage:', err);
        }
        if (!initialServerPrompts.includes(clean)) {
            initialServerPrompts.push(clean);
        }
        syncPromptHistory();
    };

    const loadAllPrompts = async () => {
        try {
            const payload = await request('/api/chat/prompts');
            if (payload && Array.isArray(payload.prompts)) {
                payload.prompts.forEach(p => {
                    const clean = (p || '').trim();
                    if (clean && !initialServerPrompts.includes(clean)) {
                        initialServerPrompts.push(clean);
                    }
                });
                syncPromptHistory();
            }
        } catch {
            // Silently ignore if background prompt fetch fails
        }
    };

    const showMessages = (list) => {
        messages.replaceChildren();
        list.forEach((item) => messageNode(item.role, item.content, item.tool_provenance, item.input_tokens, item.output_tokens, item.model_id));
        syncPromptHistory(list);
        historyIndex = -1;
        currentDraft = '';
        empty.classList.toggle('hidden', list.length > 0);
        status.classList.add('hidden');
        scrollToBottom();
    };

    const updateActiveModelDisplay = () => {
        if (activeModelBadge && model) {
            const selectedOpt = model.options[model.selectedIndex];
            activeModelBadge.textContent = selectedOpt ? (selectedOpt.text || selectedOpt.value) : (model.value || '');
        }
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
            const optgroup = document.createElement('optgroup');
            optgroup.label = group.display_name || group.provider;
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

        model.value = preferred.id;
        localStorage.setItem('kinetiqo_chat_model', preferred.id);
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
                        syncPromptHistory();
                        historyIndex = -1;
                        currentDraft = '';
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
        syncPromptHistory();
        historyIndex = -1;
        currentDraft = '';
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
                syncPromptHistory();
                historyIndex = -1;
                currentDraft = '';
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

        const candidates = [...promptHistory].reverse();
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
            if (promptHistory.length > 0) {
                if (historyIndex === -1) {
                    if (isCursorOnFirstLine(input)) {
                        currentDraft = input.value;
                        historyIndex = promptHistory.length - 1;
                        input.value = promptHistory[historyIndex];
                        input.setSelectionRange(input.value.length, input.value.length);
                        e.preventDefault();
                    }
                } else if (historyIndex > 0) {
                    historyIndex--;
                    input.value = promptHistory[historyIndex];
                    input.setSelectionRange(input.value.length, input.value.length);
                    e.preventDefault();
                } else if (historyIndex === 0) {
                    e.preventDefault();
                }
            }
        } else if (e.key === 'ArrowDown') {
            if (historyIndex !== -1) {
                if (historyIndex < promptHistory.length - 1) {
                    historyIndex++;
                    input.value = promptHistory[historyIndex];
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
        saveStoredPrompt(content);
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

        try {
            composer.classList.add('composer-responding');
            if (!sessionId) await createSession();
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
            const answer = messageNode('assistant', '', null, null, null, chosenModelId);
            ensureFooter(answer);
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
                        const downloadBtns = answer.querySelectorAll('.chat-download-btn');
                        downloadBtns.forEach(btn => btn.classList.add('hidden'));
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
                    scrollToBottom();
                }
            } else {
                setStatus(error.message, true);
            }
        } finally {
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

    Promise.all([loadModels(), loadSessions(), loadAllPrompts()])
        .then(() => sessionId ? openSession(sessionId) : null)
        .catch((error) => setStatus(error.message, true));
})();

