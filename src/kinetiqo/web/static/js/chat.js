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

    const renderMarkdown = (text) => {
        if (!text) return '';
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

        // Tables
        processed = processed.replace(/((?:\|[^\n]+\|\r?\n)+)/g, (tableBlock) => {
            const lines = tableBlock.trim().split(/\r?\n/).filter(Boolean);
            if (lines.length < 2) return tableBlock;
            if (!/^\|(?:\s*:?-+:?\s*\|)+$/.test(lines[1].trim())) return tableBlock;

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

    const formatToolName = (name) => (name || '').replace(/^kinetiqo_/, '').replace(/_/g, ' ');

    const appendProvenance = (article, rawProvenance) => {
        let records = [];
        try {
            records = typeof rawProvenance === 'string' ? JSON.parse(rawProvenance) : (Array.isArray(rawProvenance) ? rawProvenance : []);
        } catch {
            return;
        }
        if (!Array.isArray(records) || records.length === 0) return;
        const details = document.createElement('details');
        details.className = 'mt-3 border-t border-warm-200 pt-2 text-xs text-gray-500 dark:border-zinc-700 dark:text-gray-400';
        const summary = document.createElement('summary');
        summary.className = 'cursor-pointer font-medium hover:underline';
        summary.textContent = `Data used (${records.length} local ${records.length === 1 ? 'query' : 'queries'})`;
        details.appendChild(summary);
        const ul = document.createElement('ul');
        ul.className = 'mt-1.5 list-disc space-y-0.5 pl-4';
        records.forEach((rec) => {
            const li = document.createElement('li');
            const toolName = formatToolName(rec.tool);
            const duration = rec.duration_ms ? ` (${rec.duration_ms}ms)` : '';
            li.textContent = `${toolName}${duration}`;
            ul.appendChild(li);
        });
        details.appendChild(ul);
        article.appendChild(details);
    };

    const messageNode = (role, content = '', toolProvenance = null) => {
        const article = document.createElement('article');
        article.dataset.role = role;

        if (role === 'user') {
            article.className = 'chat-msg-user';
            article.style.cssText = 'margin-left: auto; max-width: 85%; border-radius: 16px 16px 4px 16px; background: #ea580c; color: white; padding: 12px 18px; font-size: 14px; line-height: 1.5; word-break: break-word; box-shadow: 0 1px 2px rgba(0,0,0,0.06);';
        } else {
            article.className = 'chat-msg-assistant';
            const isDark = document.documentElement.classList.contains('dark') || document.body.classList.contains('dark');
            const bg = isDark ? '#262629' : '#ffffff';
            const color = isDark ? '#f4f4f5' : '#1f2937';
            const border = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
            article.style.cssText = `margin-right: auto; width: 100%; max-width: 100%; border-radius: 16px; background: ${bg}; color: ${color}; padding: 18px 22px; font-size: 14px; line-height: 1.6; word-break: break-word; border: 1px solid ${border}; box-shadow: 0 1px 3px rgba(0,0,0,0.04);`;
        }

        const senderHeader = document.createElement('div');
        senderHeader.className = 'chat-sender-header';
        if (role === 'user') {
            senderHeader.style.cssText = 'display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-bottom: 6px; font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.92);';
            const nameEl = document.createElement('span');
            nameEl.textContent = userName || 'Athlete';
            senderHeader.appendChild(nameEl);
        } else {
            senderHeader.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 11px; font-weight: 600; color: #ea580c;';
            const iconEl = document.createElement('span');
            iconEl.textContent = '⚡';
            iconEl.style.fontSize = '12px';
            const nameEl = document.createElement('span');
            nameEl.textContent = 'Kinetiqo AI';
            senderHeader.appendChild(iconEl);
            senderHeader.appendChild(nameEl);
        }
        article.appendChild(senderHeader);

        const textContainer = document.createElement('div');
        textContainer.className = 'chat-text';
        if (role === 'assistant') {
            textContainer.innerHTML = renderMarkdown(content);
        } else {
            textContainer.textContent = content;
        }
        article.appendChild(textContainer);

        if (toolProvenance) {
            appendProvenance(article, toolProvenance);
        }
        messages.appendChild(article);
        scrollToBottom();
        return article;
    };

    const showMessages = (list) => {
        messages.replaceChildren();
        list.forEach((item) => messageNode(item.role, item.content, item.tool_provenance));
        empty.classList.toggle('hidden', list.length > 0);
        status.classList.add('hidden');
        scrollToBottom();
    };

    const updateActiveModelDisplay = () => {
        if (activeModelBadge && model) {
            activeModelBadge.textContent = model.value || '';
        }
    };

    const loadModels = async () => {
        const payload = await request('/api/chat/models?provider=gemini');
        const available = Array.isArray(payload.models) ? payload.models : [];
        if (available.length === 0) throw new Error('No Gemini text-generation models are available for this API key.');
        const savedModel = localStorage.getItem('kinetiqo_chat_model');
        const priorValue = model.value;
        model.replaceChildren();
        available.forEach((item) => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.display_name || item.id;
            model.appendChild(option);
        });
        const matchedSaved = savedModel && available.some((item) => item.id === savedModel);
        const preferred = (matchedSaved ? available.find((item) => item.id === savedModel) : null)
            || available.find((item) => item.id === priorValue)
            || PREFERRED_MODELS.map((p) => available.find((item) => item.id === p)).find(Boolean)
            || available[0];
        model.value = preferred.id;
        localStorage.setItem('kinetiqo_chat_model', preferred.id);
        updateActiveModelDisplay();
    };

    model.addEventListener('change', () => {
        localStorage.setItem('kinetiqo_chat_model', model.value);
        updateActiveModelDisplay();
    });

    const loadSessions = async () => {
        const payload = await request('/api/chat/sessions');
        sessions.replaceChildren();
        payload.sessions.forEach((item) => {
            const button = document.createElement('button');
            button.type = 'button';
            const isActive = item.session_id === sessionId;
            button.className = isActive
                ? 'min-h-10 w-full truncate rounded-xl px-3 py-2 text-left text-xs font-semibold bg-orange-100 text-orange-950 dark:bg-zinc-700 dark:text-white flex items-center gap-2 border border-orange-200 dark:border-zinc-600'
                : 'min-h-10 w-full truncate rounded-xl px-3 py-2 text-left text-xs font-medium text-gray-700 hover:bg-warm-200/80 dark:text-zinc-300 dark:hover:bg-zinc-750 flex items-center gap-2 transition';

            const iconSpan = document.createElement('span');
            iconSpan.className = 'opacity-70 text-xs shrink-0';
            iconSpan.textContent = '💬';
            button.appendChild(iconSpan);

            const titleSpan = document.createElement('span');
            titleSpan.className = 'truncate';
            titleSpan.textContent = item.title;
            button.appendChild(titleSpan);

            button.addEventListener('click', () => openSession(item.session_id));
            sessions.appendChild(button);
        });
    };

    const openSession = async (id) => {
        sessionId = id;
        history.replaceState(null, '', `/chat/${encodeURIComponent(id)}`);
        await loadSessions();
        const payload = await request(`/api/chat/sessions/${encodeURIComponent(id)}/messages`);
        showMessages(payload.messages);
    };

    const createSession = async () => {
        const payload = await request('/api/chat/sessions', {
            method: 'POST',
            body: JSON.stringify({ provider: 'gemini', model_id: model.value })
        });
        await loadSessions();
        await openSession(payload.session.session_id);
    };

    document.getElementById('new-chat').addEventListener('click', () => {
        sessionId = null;
        history.replaceState(null, '', '/chat');
        messages.replaceChildren();
        empty.classList.remove('hidden');
        status.classList.add('hidden');
        loadSessions();
    });

    document.querySelectorAll('.chat-suggestion').forEach((button) => button.addEventListener('click', () => {
        input.value = button.textContent.trim().replace(/^[^\w]+/, '');
        input.focus();
    }));

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            composer.requestSubmit();
        }
    });

    composer.addEventListener('submit', async (event) => {
        event.preventDefault();
        const content = input.value.trim();
        if (!content) return;
        const origSendHtml = send.innerHTML;
        try {
            if (!sessionId) await createSession();
            send.disabled = true;
            send.innerHTML = '<img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading" width="16" height="16" class="inline-block">';
            status.classList.add('hidden');
            const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ content, model_id: model.value })
            });
            if (!response.ok || !response.body) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error?.message || 'Chat request failed.');
            }
            input.value = '';
            messageNode('user', content);
            const answer = messageNode('assistant');
            const answerText = answer.querySelector('.chat-text');
            empty.classList.add('hidden');

            // Standard looping loading K indicator
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
                        toolStatusEl.innerHTML = `<img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading" width="16" height="16" class="inline-block"><span>Consulting ${formatToolName(payload.tool)}…</span>`;
                        executedTools.push({ tool: payload.tool });
                        scrollToBottom();
                    } else if (eventType === 'tool_result') {
                        if (toolStatusEl) {
                            toolStatusEl.innerHTML = `<span class="text-green-500 text-sm font-bold">✓</span><span>Retrieved ${formatToolName(payload.tool)}</span>`;
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
                        setStatus(payload.message, true);
                    }
                });
            }

            if (thinkingEl) thinkingEl.remove();
            if (toolStatusEl) toolStatusEl.remove();

            if (rawAssistantMarkdown) {
                answerText.innerHTML = renderMarkdown(rawAssistantMarkdown);
            }

            if (executedTools.length > 0 && !answer.querySelector('details')) {
                appendProvenance(answer, executedTools);
                scrollToBottom();
            }
            await loadSessions();
        } catch (error) {
            setStatus(error.message, true);
        } finally {
            send.disabled = false;
            send.innerHTML = origSendHtml;
        }
    });

    Promise.all([loadModels(), loadSessions()])
        .then(() => sessionId ? openSession(sessionId) : null)
        .catch((error) => setStatus(error.message, true));
})();

