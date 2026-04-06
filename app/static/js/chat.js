// Auth check
const token = localStorage.getItem('token');
if (!token) {
    window.location.href = '/login.html';
}

// UI elements
const messagesEl = document.getElementById('messages');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const logoutBtn = document.getElementById('logout-btn');
const userNameEl = document.getElementById('user-name');

// State
let conversationHistory = [];
let isStreaming = false;

// Init
userNameEl.textContent = localStorage.getItem('userName') || '';

// Configure marked
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true,
});

showWelcome();

// Event listeners
chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage();
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

newChatBtn.addEventListener('click', () => {
    conversationHistory = [];
    messagesEl.innerHTML = '';
    showWelcome();
});

logoutBtn.addEventListener('click', () => {
    localStorage.clear();
    window.location.href = '/login.html';
});

function showWelcome() {
    messagesEl.innerHTML = `
        <div class="welcome">
            <p class="mt-3">Query across 10 enterprise systems spanning 3 operating divisions. Ask questions in plain English — I'll pull data from the right systems and merge it for you.</p>
            <div class="db-overview">
                <div class="row g-3 mt-3">
                    <div class="col-md-6">
                        <div class="card h-100"><div class="card-body">
                            <h6 class="card-title">Industrial Division <span class="text-muted small">(~$250M)</span></h6>
                            <p class="card-text text-muted small">
                                <strong>Salesforce</strong> CRM &middot; <strong>NetSuite</strong> Finance &middot; <strong>SAP</strong> Operations<br>
                                Fasteners, Tools, Electrical &middot; Northeast & Midwest
                            </p>
                        </div></div>
                    </div>
                    <div class="col-md-6">
                        <div class="card h-100"><div class="card-body">
                            <h6 class="card-title">Energy Division <span class="text-muted small">(~$150M)</span></h6>
                            <p class="card-text text-muted small">
                                <strong>Legacy CRM</strong> &middot; <strong>QuickBooks</strong> Finance &middot; <strong>Oracle SCM</strong><br>
                                Safety Equipment, HVAC, Electrical &middot; West & Gulf Coast
                            </p>
                        </div></div>
                    </div>
                    <div class="col-md-6">
                        <div class="card h-100"><div class="card-body">
                            <h6 class="card-title">Safety Division <span class="text-muted small">(~$100M)</span></h6>
                            <p class="card-text text-muted small">
                                <strong>HubSpot</strong> CRM &middot; Shared NetSuite Finance &middot; 3PL fulfillment<br>
                                Premium safety equipment &middot; Nationwide
                            </p>
                        </div></div>
                    </div>
                    <div class="col-md-6">
                        <div class="card h-100"><div class="card-body">
                            <h6 class="card-title">Corporate HQ</h6>
                            <p class="card-text text-muted small">
                                <strong>Workday</strong> HR (all divisions) &middot; <strong>NetSuite</strong> Consolidation &middot; <strong>Zendesk</strong> Support<br>
                                Employee data, financial rollups, support tickets
                            </p>
                        </div></div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isStreaming) return;

    // Clear welcome on first message
    if (conversationHistory.length === 0) {
        messagesEl.innerHTML = '';
    }

    // Add user message
    appendMessage('user', text);
    conversationHistory.push({ role: 'user', content: text });
    userInput.value = '';
    isStreaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = '...';

    // Create assistant message container
    const assistantEl = appendMessage('assistant', '');
    const contentEl = assistantEl.querySelector('.content');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
                message: text,
                history: conversationHistory.slice(-40),  // Cap at 20 exchanges
            }),
        });

        if (res.status === 401) {
            localStorage.clear();
            window.location.href = '/login.html';
            return;
        }

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Request failed');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();  // Keep incomplete line

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') continue;

                try {
                    const event = JSON.parse(payload);
                    if (event.type === 'text') {
                        fullText += event.content;
                        contentEl.innerHTML = marked.parse(fullText);
                    } else if (event.type === 'tool_status') {
                        const indicator = document.createElement('div');
                        indicator.className = 'tool-indicator';
                        indicator.textContent = event.message;
                        contentEl.appendChild(indicator);
                    } else if (event.type === 'image') {
                        const img = document.createElement('img');
                        img.src = `data:image/png;base64,${event.data}`;
                        contentEl.appendChild(img);
                    } else if (event.type === 'file') {
                        const link = document.createElement('a');
                        link.href = event.url;
                        link.download = event.filename;
                        link.className = 'file-download';
                        link.innerHTML = `📄 Download ${event.filename}`;
                        link.target = '_blank';
                        contentEl.appendChild(link);
                    } else if (event.type === 'error') {
                        contentEl.innerHTML += `<div class="alert alert-danger">${event.message}</div>`;
                    }
                } catch {
                    // Skip malformed events
                }
            }
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        conversationHistory.push({ role: 'assistant', content: fullText });

    } catch (err) {
        contentEl.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    } finally {
        isStreaming = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }
}

function appendMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (role === 'user') {
        div.textContent = content;
    } else {
        div.innerHTML = `<div class="content">${content}</div>`;
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
}
