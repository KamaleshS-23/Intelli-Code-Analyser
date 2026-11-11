// State management
let currentScanData = null;
let currentWorkdirPath = null;
let currentScanStack = null;
let currentOptimizationResult = null;
let selectedIssueKeys = new Set();
let visibleIssueKeys = new Set();
let networkInstance = null;
let authToken = localStorage.getItem('techDebtAuthToken');
let knowledgeNetworkInstance = null;

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const btnUpload = document.getElementById('btn-upload');
const stackSelect = document.getElementById('stack-select');
const btnSampleScan = document.getElementById('btn-sample-scan');
const scannerLoader = document.getElementById('scanner-loader');
const resultsPanel = document.getElementById('results-panel');
const authOverlay = document.getElementById('auth-overlay');
const signInButton = document.getElementById('btn-signin');
const authEmail = document.getElementById('auth-email');
const authPassword = document.getElementById('auth-password');
const authError = document.getElementById('auth-error');
const userChip = document.getElementById('user-chip');
const userAvatar = document.getElementById('user-avatar');
const historyModal = document.getElementById('history-modal');
const aiMessageInput = document.getElementById('ai-message-input');
const aiChatThread = document.getElementById('ai-chat-thread');
const btnAiSend = document.getElementById('btn-ai-send');
const btnAiSummary = document.getElementById('btn-ai-summary');
const btnAiToggle = document.getElementById('btn-ai-toggle');
const btnAiClose = document.getElementById('btn-ai-close');
const aiAssistantPanel = document.getElementById('ai-assistant-panel');

// Tabs
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanes = document.querySelectorAll('.tab-pane');

// Modal Elements
const smellModal = document.getElementById('smell-modal');
const modalOverlay = document.getElementById('modal-overlay');
const modalCloseBtn = document.getElementById('modal-close-btn');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    setupStackOptions();
    setupDragAndDrop();
    setupTabSwitching();
    setupEventHandlers();
    setupModalHandlers();
    setupAuth();
    setupAIChat();
});

// --- Event Handlers ---
function getSelectedStack() {
    return (stackSelect?.value || 'java').toLowerCase();
}

async function setupStackOptions() {
    const description = document.getElementById('stack-description');
    if (!stackSelect || !description) return;

    const fallbackDescriptions = {
        java: 'Java projects and Java-specific debt rules.',
        python: 'Python projects and Python-specific debt rules.',
        web: 'Frontend projects: HTML, CSS, and JavaScript.',
        django: 'Django/Python backends with HTML, CSS, and JavaScript.',
        nodejs: 'Node.js projects with JavaScript, HTML, and CSS.'
    };
    const updateDescription = () => {
        description.textContent = fallbackDescriptions[getSelectedStack()] || '';
    };
    stackSelect.addEventListener('change', updateDescription);
    updateDescription();

    try {
        const response = await fetch('/api/stacks');
        if (!response.ok) throw new Error(`Stack list request failed (${response.status}).`);
        const data = await response.json();
        if (!Array.isArray(data.options) || !data.options.length) {
            throw new Error('The server returned no supported stack profiles.');
        }

        const selected = data.default || getSelectedStack();
        stackSelect.innerHTML = data.options.map(option =>
            `<option value="${escapeHtml(option.id)}">${escapeHtml(option.label)}</option>`
        ).join('');
        stackSelect.value = data.options.some(option => option.id === selected)
            ? selected
            : data.options[0].id;
        for (const option of data.options) {
            fallbackDescriptions[option.id] = option.description;
        }
        updateDescription();
    } catch (error) {
        console.error('Unable to load stack profiles:', error);
    }
}

function setupEventHandlers() {
    btnSampleScan.addEventListener('click', () => runScan(`/api/sample?stack=${encodeURIComponent(getSelectedStack())}`));
    stackSelect?.addEventListener('change', updateRefactorStackLabel);
    updateRefactorStackLabel();

    btnUpload.addEventListener('click', () => {
        const file = fileInput.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('stack', getSelectedStack());

        runScan('/api/scan-upload', 'POST', formData);
    });

    document.getElementById('btn-history')?.addEventListener('click', loadHistory);
    document.getElementById('btn-history-refresh')?.addEventListener('click', loadHistory);
    document.getElementById('btn-logout')?.addEventListener('click', logout);
    document.getElementById('btn-download-report')?.addEventListener('click', downloadReportPdf);
    document.getElementById('btn-print-report')?.addEventListener('click', printReport);
    document.getElementById('btn-refactor-select-all')?.addEventListener('click', () => {
        document.querySelectorAll('#refactor-issue-list input[type="checkbox"]').forEach(input => {
            input.checked = true;
            selectedIssueKeys.add(input.dataset.issueKey);
        });
        updateIssueSelectionUI();
    });
    document.getElementById('btn-refactor-clear-selection')?.addEventListener('click', () => {
        document.querySelectorAll('#refactor-issue-list input[type="checkbox"]').forEach(input => {
            input.checked = false;
        });
        selectedIssueKeys.clear();
        updateIssueSelectionUI();
    });
    document.getElementById('refactor-issue-list')?.addEventListener('change', event => {
        const checkbox = event.target.closest('input[type="checkbox"][data-issue-key]');
        if (!checkbox) return;
        if (checkbox.checked) selectedIssueKeys.add(checkbox.dataset.issueKey);
        else selectedIssueKeys.delete(checkbox.dataset.issueKey);
        updateIssueSelectionUI();
    });
    document.getElementById('btn-generate-optimized')?.addEventListener('click', generateOptimizedCode);
    document.addEventListener('click', event => {
        if (event.target.closest('#btn-download-optimized, #btn-download-optimized-comparison')) {
            downloadOptimizedCode();
        }
    });
    document.addEventListener('change', event => {
        const fileSelect = event.target.closest('#comparison-file-select');
        if (fileSelect) renderComparison(fileSelect.value, true);
    });
    document.addEventListener('click', event => {
        if (event.target.closest('#btn-download-comparison-report')) {
            downloadComparisonReport();
        }
    });
    signInButton?.addEventListener('click', () => authOverlay.classList.remove('hidden'));
    btnAiToggle?.addEventListener('click', () => toggleAIChatPanel());
    btnAiClose?.addEventListener('click', () => toggleAIChatPanel(false));

    // Expand / Shorten Bot Box Button with Flexible Arrows Icon
    document.getElementById('btn-ai-expand')?.addEventListener('click', togglePanelSize);

    btnAiSend?.addEventListener('click', () => sendAIChatMessage(aiMessageInput.value));
    aiMessageInput?.addEventListener('keydown', event => {
        if (event.key === 'Enter') sendAIChatMessage(aiMessageInput.value);
    });

    setupFeaturePills();
    setupResizableChatPanel();

    document.getElementById('auth-close-btn')?.addEventListener('click', () => authOverlay.classList.add('hidden'));
    authOverlay?.addEventListener('click', event => {
        if (event.target === authOverlay) authOverlay.classList.add('hidden');
    });
}

// 5 Core Feature Modes & Prompts
let currentAIMode = 'explain';
const MODE_PROMPTS = {
    'explain': [
        { text: '🔍 Top Debt Issues', msg: 'Explain the biggest technical-debt issues in this project and their severity.' },
        { text: '📊 Severity Breakdown', msg: 'Break down all technical debt findings by severity (Critical, High, Medium, Low) and affected classes.' },
        { text: '⚠️ Maintainability Impact', msg: 'Which classes pose the highest maintenance risk and defect potential?' },
        { text: '🛡️ Security Vulnerabilities', msg: 'Explain the vulnerable or outdated dependencies found in this project.' }
    ],
    'root-cause': [
        { text: '🧠 UserService God Class', msg: 'Perform root-cause analysis: Why is demo.UserService a God Class and which SOLID principles are violated?' },
        { text: '🔄 Circular Dependency Cause', msg: 'Why does a circular dependency exist between AuditLogService and UserService?' },
        { text: '⚡ Cyclomatic Complexity', msg: 'What is the architectural root cause of high cyclomatic complexity in InvoiceService and UserService?' },
        { text: '📦 Anti-Pattern Identification', msg: 'Identify all architectural anti-patterns in this project (God Class, Feature Envy, Long Method).' }
    ],
    'graph': [
        { text: '🕸️ Circular Dependencies', msg: 'Query knowledge graph: What are the circular dependency cycles in this project and how are they linked?' },
        { text: '📈 Class Coupling Metrics', msg: 'Show afferent (fan-in) and efferent (fan-out) coupling metrics for the top classes.' },
        { text: '💥 Blast Radius Analysis', msg: 'What is the blast radius if I refactor or modify demo.UserService?' },
        { text: '🔗 Caller-Callee Hierarchy', msg: 'Explain the dependency relationship between AuditLogService and UserService.' }
    ],
    'refactor': [
        { text: '🛠️ Refactor processPayment', msg: 'Refactor and generate clean Java code for demo.UserService.processPayment to reduce its complexity.' },
        { text: '📦 Decompose God Class', msg: 'Generate refactored Java code to split UserService into AuthService, PaymentService, and ProfileService.' },
        { text: '🔄 Decouple Circular Dependency', msg: 'Generate clean Java code and interface to eliminate the circular dependency between AuditLogService and UserService.' },
        { text: '💡 Extract Method in InvoiceService', msg: 'Refactor demo.InvoiceService.calculateCustomerDiscount using Extract Method and Strategy Pattern.' }
    ],
    'validation': [
        { text: '✅ Before-After Diff: UserService', msg: 'Generate a unified before-after code diff for demo.UserService and run build/test validation.' },
        { text: '🧪 Validate calculateCustomerDiscount', msg: 'Show before-after diff and validate syntax, types, and complexity reduction for calculateCustomerDiscount.' },
        { text: '📋 Full Build/Test Verification', msg: 'Prove and validate the proposed refactorings with complexity deltas and build pass status.' },
        { text: '🔍 Eliminate Circular Dependency Diff', msg: 'Show before-after diff proving the decoupling of AuditLogService from UserService.' }
    ]
};

function setupFeaturePills() {
    const pills = document.querySelectorAll('.ai-pill');
    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            currentAIMode = pill.dataset.mode || 'explain';
            renderModePrompts(currentAIMode);
        });
    });
    renderModePrompts(currentAIMode);
}

function renderModePrompts(mode) {
    const container = document.getElementById('ai-suggested-prompts');
    if (!container) return;
    const prompts = MODE_PROMPTS[mode] || MODE_PROMPTS['explain'];
    container.innerHTML = prompts.map(p => `
        <button class="prompt-chip" type="button" data-message="${escapeHtml(p.msg)}">${escapeHtml(p.text)}</button>
    `).join('');

    container.querySelectorAll('.prompt-chip').forEach(chip => {
        chip.addEventListener('click', () => sendAIChatMessage(chip.dataset.message || ''));
    });
}

// Resizing Bot Box with Flexible Arrows & Drag
let panelState = 'normal'; // 'normal' | 'expanded' | 'compact'
function togglePanelSize() {
    if (!aiAssistantPanel) return;
    const expandIcon = document.getElementById('ai-expand-icon');

    if (panelState === 'normal') {
        aiAssistantPanel.classList.remove('compact');
        aiAssistantPanel.classList.add('expanded');
        aiAssistantPanel.style.width = '';
        aiAssistantPanel.style.height = '';
        panelState = 'expanded';
        if (expandIcon) expandIcon.className = 'fa-solid fa-compress';
    } else if (panelState === 'expanded') {
        aiAssistantPanel.classList.remove('expanded');
        aiAssistantPanel.classList.add('compact');
        aiAssistantPanel.style.width = '';
        aiAssistantPanel.style.height = '';
        panelState = 'compact';
        if (expandIcon) expandIcon.className = 'fa-solid fa-arrows-left-right';
    } else {
        aiAssistantPanel.classList.remove('compact', 'expanded');
        aiAssistantPanel.style.width = '';
        aiAssistantPanel.style.height = '';
        panelState = 'normal';
        if (expandIcon) expandIcon.className = 'fa-solid fa-up-right-and-down-left-from-center';
    }
}

function setupResizableChatPanel() {
    const handle = document.getElementById('ai-resize-handle');
    if (!handle || !aiAssistantPanel) return;

    let isResizing = false;
    let startX, startY, startWidth, startHeight;

    const onPointerDown = (e) => {
        isResizing = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = aiAssistantPanel.getBoundingClientRect();
        startWidth = rect.width;
        startHeight = rect.height;

        aiAssistantPanel.classList.add('is-resizing');
        document.addEventListener('pointermove', onPointerMove);
        document.addEventListener('pointerup', onPointerUp);
        e.preventDefault();
    };

    const onPointerMove = (e) => {
        if (!isResizing) return;
        // Panel is anchored at bottom-right, so dragging top-left expands width & height
        const deltaX = startX - e.clientX;
        const deltaY = startY - e.clientY;

        const newWidth = Math.min(Math.max(startWidth + deltaX, 350), window.innerWidth - 30);
        const newHeight = Math.min(Math.max(startHeight + deltaY, 400), window.innerHeight - 30);

        aiAssistantPanel.style.width = `${newWidth}px`;
        aiAssistantPanel.style.height = `${newHeight}px`;
    };

    const onPointerUp = () => {
        isResizing = false;
        aiAssistantPanel.classList.remove('is-resizing');
        document.removeEventListener('pointermove', onPointerMove);
        document.removeEventListener('pointerup', onPointerUp);
    };

    handle.addEventListener('pointerdown', onPointerDown);
}

function setupAIChat() {
    if (!aiChatThread) return;
    aiChatThread.innerHTML = `
        <div class="ai-message ai-message-bot">
            <div class="ai-bubble">
                Welcome to your <strong>AI Technical Debt Assistant</strong>! Select one of the <strong>5 Core Features</strong> above:
                <br>🔍 <strong>Debt Explanation</strong> | 🧠 <strong>Root-Cause Analysis</strong> | 🕸️ <strong>Knowledge Graph</strong> | 🛠️ <strong>Refactoring</strong> | ✅ <strong>Diff & Validation</strong>
            </div>
        </div>
    `;
    toggleAIChatPanel(false);
}

function toggleAIChatPanel(forceOpen = null) {
    if (!aiAssistantPanel || !btnAiToggle) return;
    const shouldOpen = forceOpen === null ? aiAssistantPanel.classList.contains('hidden') : forceOpen;
    aiAssistantPanel.classList.toggle('hidden', !shouldOpen);
    btnAiToggle.setAttribute('aria-expanded', String(shouldOpen));

    if (shouldOpen && aiMessageInput) {
        setTimeout(() => aiMessageInput.focus(), 50);
    }
}

// Global copy-code helper for generated refactorings & diffs
window.copyCode = function(button) {
    const pre = button.closest('.ai-code-wrapper')?.querySelector('pre');
    if (!pre) return;
    navigator.clipboard.writeText(pre.innerText).then(() => {
        const orig = button.textContent;
        button.textContent = 'Copied!';
        setTimeout(() => button.textContent = orig, 1800);
    });
};

function formatAIMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // 1. Unified Diff blocks: ```diff ... ```
    html = html.replace(/```diff\r?\n([\s\S]*?)```/g, (match, code) => {
        const lines = code.split('\n').map(line => {
            if (line.startsWith('+')) {
                return `<span class="diff-line-add">${line}</span>`;
            } else if (line.startsWith('-')) {
                return `<span class="diff-line-del">${line}</span>`;
            }
            return line;
        }).join('\n');
        return `
            <div class="ai-code-wrapper">
                <div class="ai-code-header">
                    <span><i class="fa-solid fa-code-compare"></i> Unified Code Diff (Before vs After)</span>
                    <button class="copy-code-btn" type="button" onclick="copyCode(this)">Copy Diff</button>
                </div>
                <pre><code>${lines}</code></pre>
            </div>
        `;
    });

    // 2. Java and code blocks: ```java ... ```
    html = html.replace(/```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```/g, (match, lang, code) => {
        const displayLang = (lang || 'JAVA').toUpperCase();
        return `
            <div class="ai-code-wrapper">
                <div class="ai-code-header">
                    <span><i class="fa-brands fa-java"></i> ${displayLang}</span>
                    <button class="copy-code-btn" type="button" onclick="copyCode(this)">Copy Code</button>
                </div>
                <pre><code>${code.trim()}</code></pre>
            </div>
        `;
    });

    // 3. Validation Callout: [PASSED] or VALIDATION: PASSED
    html = html.replace(/(✅\s*VALIDATION\s*PASSED[^\n<]*)/gi, `<div class="ai-validation-box"><h4><i class="fa-solid fa-circle-check"></i> Build & Test Validation</h4><p>$1</p></div>`);

    // 4. Markdown Tables: | col | col |
    html = html.replace(/(?:^|\n)(\|[^\n]+\|\r?\n\|[-:| ]+\|\r?\n(?:\|[^\n]+\|\r?\n?)+)/g, (match, table) => {
        const rows = table.trim().split('\n');
        if (rows.length < 3) return match;
        const headers = rows[0].split('|').slice(1, -1).map(h => `<th>${h.trim()}</th>`).join('');
        const bodyRows = rows.slice(2).map(r => {
            const cells = r.split('|').slice(1, -1).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<div class="table-responsive" style="overflow-x:auto;margin:0.6rem 0;"><table><thead><tr>${headers}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
    });

    // 5. Headings & basic markup
    html = html.replace(/^### (.*$)/gim, '<h4 style="color:var(--accent-cyan);margin:0.5rem 0 0.25rem;">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 style="color:#ffffff;margin:0.7rem 0 0.35rem;">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 style="color:#ffffff;margin:0.8rem 0 0.45rem;">$1</h2>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08);padding:0.15rem 0.35rem;border-radius:4px;font-size:0.82rem;">$1</code>');
    html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li style="margin-left:1rem;margin-bottom:0.2rem;">$1</li>');
    html = html.replace(/\n/g, '<br>');

    return html;
}

function appendAIMessage(role, message, evidence = []) {
    if (!aiChatThread) return;

    const wrapper = document.createElement('div');
    wrapper.className = `ai-message ai-message-${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'ai-bubble';

    if (role === 'bot') {
        bubble.innerHTML = formatAIMarkdown(message);
    } else {
        bubble.innerHTML = escapeHtml(message).replace(/\n/g, '<br>');
    }

    if (evidence && evidence.length) {
        const evidenceList = document.createElement('ul');
        evidenceList.className = 'ai-evidence';
        evidence.slice(0, 4).forEach(item => {
            const li = document.createElement('li');
            li.textContent = `${item.rule || 'Finding'}: ${item.class_name || 'Unknown'}${item.severity ? ` (${item.severity})` : ''}`;
            evidenceList.appendChild(li);
        });
        bubble.appendChild(evidenceList);
    }

    wrapper.appendChild(bubble);
    aiChatThread.appendChild(wrapper);
    aiChatThread.scrollTop = aiChatThread.scrollHeight;
}

async function sendAIChatMessage(messageText) {
    const message = (messageText || '').trim();
    if (!message) return;
    if (!currentScanData) {
        appendAIMessage('bot', 'Please run a project scan first before asking the AI assistant.');
        return;
    }

    appendAIMessage('user', message);
    if (aiMessageInput) aiMessageInput.value = '';

    const sendButton = document.getElementById('btn-ai-send');
    if (sendButton) {
        sendButton.disabled = true;
        sendButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Thinking...';
    }

    try {
        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(authHeaders())
            },
            body: JSON.stringify({
                project_id: currentScanData.project_name || 'default',
                scan_id: currentScanData._output_file || '',
                message,
                context: {
                    mode: currentAIMode,
                    file: '',
                    class: '',
                    method: '',
                    finding_id: ''
                }
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'The AI assistant could not answer this request.');
        }

        appendAIMessage('bot', data.message || 'No answer returned.', data.evidence || []);
    } catch (error) {
        appendAIMessage('bot', error.message || 'AI request failed.');
    } finally {
        if (sendButton) {
            sendButton.disabled = false;
            sendButton.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send';
        }
    }
}

function setupAuth() {
    document.getElementById('btn-login').addEventListener('click', () => submitAuth('/api/auth/login'));
    document.getElementById('btn-register').addEventListener('click', () => submitAuth('/api/auth/register'));
    [authEmail, authPassword].forEach(input => input.addEventListener('keydown', event => {
        if (event.key === 'Enter') submitAuth('/api/auth/login');
    }));

    if (authToken) {
        fetch('/api/auth/me', { headers: authHeaders() })
            .then(response => response.ok ? response.json() : Promise.reject())
            .then(user => showAuthenticatedUser(user))
            .catch(() => clearAuth());
    }
}

async function submitAuth(endpoint) {
    authError.classList.add('hidden');
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({ email: authEmail.value.trim(), password: authPassword.value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Authentication failed.');
        authToken = data.token;
        localStorage.setItem('techDebtAuthToken', authToken);
        showAuthenticatedUser(data.user);
    } catch (error) {
        authError.textContent = error.message;
        authError.classList.remove('hidden');
    }
}

function authHeaders() {
    return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

function showAuthenticatedUser(user) {
    const email = typeof user.email === 'string' ? user.email.trim() : '';
    userAvatar.textContent = email.charAt(0).toUpperCase() || '?';
    userAvatar.title = email ? `Signed in as ${email}` : 'Signed-in user';
    userAvatar.setAttribute('aria-label', userAvatar.title);
    userChip.classList.remove('hidden');
    signInButton.classList.add('hidden');
    authOverlay.classList.add('hidden');
}

function clearAuth() {
    authToken = null;
    localStorage.removeItem('techDebtAuthToken');
    userChip.classList.add('hidden');
    signInButton.classList.remove('hidden');
    authOverlay.classList.add('hidden');
}

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', headers: authHeaders() });
    clearAuth();
}

async function loadHistory(openModal = true) {
    try {
        const response = await fetch('/api/history', { headers: authHeaders() });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not load history.');
        renderHistory(data);
        if (openModal) historyModal.classList.remove('hidden');
    } catch (error) {
        alert(error.message);
    }
}

function renderHistory(data) {
    const loginList = document.getElementById('login-history-list');
    loginList.innerHTML = data.logins.length
        ? data.logins.map(item => `<li><strong>${escapeHtml(item.event)}</strong><span>${formatDate(item.created_at)}</span></li>`).join('')
        : '<li>No login history yet.</li>';

    const scanList = document.getElementById('scan-history-list');
    scanList.innerHTML = data.scans.length ? data.scans.map(scan => `
        <article class="history-scan">
            <strong>${escapeHtml(scan.project_name || 'Unnamed project')}</strong>
            <span>${formatDate(scan.created_at)} | score ${scan.debt_score} | ${scan.issue_count} issue(s)</span>
            <p>${scan.suggestions.length} saved suggestion(s)</p>
        </article>
    `).join('') : '<p>No saved scans yet.</p>';
    renderHistoryTab(data);
    renderReport(data);
}

function formatDate(value) {
    return value ? new Date(value).toLocaleString() : 'Unknown time';
}

function sanitizeFileName(value) {
    return String(value || 'Project').replace(/[\\/:*?"<>|]/g, '').trim() || 'Project';
}

function printReport() {
    const reportContent = document.getElementById('report-content');
    if (!reportContent || !currentScanData) {
        alert('Generate a scan report before printing.');
        return;
    }

    const onAfterPrint = () => {
        document.body.classList.remove('report-print-mode');
        window.removeEventListener('afterprint', onAfterPrint);
    };

    document.body.classList.add('report-print-mode');
    window.addEventListener('afterprint', onAfterPrint);
    window.print();
}

async function downloadReportPdf() {
    const reportContent = document.getElementById('report-content');
    if (!currentScanData) {
        alert('Generate a scan report before downloading the PDF.');
        return;
    }
    if (currentOptimizationResult?.optimized_scan && currentOptimizationResult?.comparison) {
        await downloadComparisonReport('btn-download-report', 'report-download-status');
        return;
    }
    if (!reportContent) {
        alert('Generate a scan report before downloading the PDF.');
        return;
    }

    const reportTitle = sanitizeFileName(currentScanData.project_name || 'Project');
    const dateStamp = new Date().toISOString().slice(0, 10);
    const fileName = `${reportTitle}_Technical_Debt_Report_${dateStamp}.pdf`;

    try {
        if (!window.jspdf) {
            throw new Error('PDF export libraries failed to load.');
        }

        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF('p', 'mm', 'a4');

        const exportRoot = document.createElement('div');
        exportRoot.className = 'report-export-sheet';
        exportRoot.innerHTML = reportContent.innerHTML;
        Object.assign(exportRoot.style, {
            position: 'relative',
            width: '794px',
            maxWidth: '794px',
            minHeight: '1000px',
            background: '#ffffff',
            color: '#111827',
            padding: '18px',
            boxSizing: 'border-box',
            fontFamily: 'Segoe UI, sans-serif',
            lineHeight: '1.45',
            zIndex: '1',
            opacity: '1',
            visibility: 'visible',
            display: 'block',
            left: '0',
            top: '0'
        });
        document.body.appendChild(exportRoot);

        try {
            if (!window.html2canvas) {
                throw new Error('PDF export libraries failed to load.');
            }

            const canvas = await window.html2canvas(exportRoot, {
                scale: 1.6,
                backgroundColor: '#ffffff',
                useCORS: true,
                scrollX: 0,
                scrollY: 0,
                windowWidth: 794,
                windowHeight: exportRoot.scrollHeight + 100,
                width: 794,
                height: exportRoot.scrollHeight
            });

            const imgData = canvas.toDataURL('image/png');
            const pageWidth = pdf.internal.pageSize.getWidth();
            const pageHeight = pdf.internal.pageSize.getHeight();
            const margin = 10;
            const imgWidth = pageWidth - margin * 2;
            const imageHeight = (canvas.height * imgWidth) / canvas.width;
            let remainingHeight = imageHeight;
            let currentY = 0;

            while (remainingHeight > 0) {
                const pageRemaining = pageHeight - margin * 2;
                pdf.addImage(
                    imgData,
                    'PNG',
                    margin,
                    margin - currentY,
                    imgWidth,
                    imageHeight,
                    undefined,
                    'FAST'
                );

                remainingHeight -= pageRemaining;
                if (remainingHeight > 0) {
                    pdf.addPage();
                    currentY += pageRemaining;
                }
            }

            pdf.save(fileName);
        } finally {
            exportRoot.remove();
        }
    } catch (error) {
        console.error('PDF export failed:', error);
        alert('The PDF export failed. Please try again or use the browser print option.');
    }
}

function setupModalHandlers() {
    const closeModal = () => {
        smellModal.classList.add('hidden');
    };
    modalCloseBtn.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', closeModal);
    document.getElementById('history-close-btn').addEventListener('click', () => historyModal.classList.add('hidden'));
    document.getElementById('history-overlay').addEventListener('click', () => historyModal.classList.add('hidden'));
    
    // Close on Escape key
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !smellModal.classList.contains('hidden')) {
            closeModal();
        }
    });
}

// --- Drag & Drop ---
function setupDragAndDrop() {
    // Prevent defaults
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Highlight drop zone
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    // Handle dropped files
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect();
        }
    });

    fileInput.addEventListener('change', handleFileSelect);
}

function handleFileSelect() {
    const file = fileInput.files[0];
    if (file) {
        if (!file.name.endsWith('.zip')) {
            alert('Only ZIP archives are supported.');
            fileInput.value = '';
            fileInfo.textContent = '';
            btnUpload.disabled = true;
            return;
        }
        fileInfo.textContent = `Selected: ${file.name} (${formatBytes(file.size)})`;
        btnUpload.disabled = false;
    } else {
        fileInfo.textContent = '';
        btnUpload.disabled = true;
    }
}

// --- Tab Switching ---
function setupTabSwitching() {
    const scanSummary = document.getElementById('scan-results-content');
    const codeSmellsPane = document.getElementById('tab-smells');
    if (scanSummary && codeSmellsPane) {
        codeSmellsPane.prepend(scanSummary);
    }

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');

            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetPane = document.getElementById(tabId);
            if (targetPane) targetPane.classList.add('active');

            // Resize network graph when its tab becomes active, as vis needs correct client bounding rect
            if (tabId === 'tab-graph' && networkInstance) {
                setTimeout(() => {
                    networkInstance.fit();
                }, 100);
            }
            if (tabId === 'tab-knowledge' && knowledgeNetworkInstance) {
                setTimeout(() => knowledgeNetworkInstance.fit(), 100);
            }
            if (tabId === 'tab-history' && authToken) loadHistory();
            if (tabId === 'tab-report') renderReportFromCurrentData();
        });
    });

    document.getElementById('btn-open-upload')?.addEventListener('click', () => {
        document.querySelector('.tab-btn[data-tab="tab-upload"]')?.click();
    });
}

// --- Running Scans ---
async function runScan(endpoint, method = 'GET', body = null) {
    // Keep navigation and the upload page available while a scan runs.
    scannerLoader.classList.add('active');
    
    // Smooth scroll to loader
    scannerLoader.scrollIntoView({ behavior: 'smooth', block: 'center' });

    try {
        const options = { method, headers: authHeaders() };
        if (body) {
            options.body = body;
        } else if (method === 'POST') {
            // For POST requests without FormData, make content-type application/json if needed
            options.headers.Accept = 'application/json';
        }

        const response = await fetch(endpoint, options);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'An error occurred during the scan.');
        }

        currentScanData = data.scan_result || data;
        currentWorkdirPath = data.workdir_path || currentScanData.project_path || null;
        currentScanStack = data.stack || currentScanData.statistics?.stack || getSelectedStack();
        currentOptimizationResult = null;
        selectedIssueKeys.clear();
        displayResults(currentScanData);
        renderComparison();

    } catch (error) {
        console.error(error);
        alert(`Scan failed: ${error.message}`);
    } finally {
        scannerLoader.classList.remove('active');
    }
}

// --- Displaying Results ---
function displayResults(data) {
    // Update Header
    document.getElementById('project-title').textContent = `Project: ${data.project_name || 'Uploaded Project'}`;
    document.getElementById('project-path-text').textContent = data.project_path || 'Uploaded Zip Archive';
    const classLabel = document.getElementById('stat-classes-label');
    const classesCount = data.statistics
        ? (data.statistics.total_classes + data.statistics.total_interfaces)
        : 0;
    const hasParsedClasses = classesCount > 0;
    if (classLabel) {
        classLabel.textContent = hasParsedClasses
            ? 'Classes & Interfaces'
            : 'Source Files';
    }
    
    const scanTime = data.statistics ? data.statistics.scan_time_seconds : 0;
    document.getElementById('scan-time-value').textContent = `${scanTime}s`;

    // Update Statistics Cards
    const debtScore = data.debt_report ? data.debt_report.total_score : 0;
    document.getElementById('stat-debt-score').textContent = debtScore;

    // Set debt level indicator
    const debtBadge = document.getElementById('debt-level-badge');
    if (debtScore < 10) {
        debtBadge.textContent = 'Low Technical Debt';
        debtBadge.className = 'stat-desc badge badge-low';
    } else if (debtScore <= 35) {
        debtBadge.textContent = 'Medium Technical Debt';
        debtBadge.className = 'stat-desc badge badge-medium';
    } else {
        debtBadge.textContent = 'High Technical Debt';
        debtBadge.className = 'stat-desc badge badge-high';
    }

    document.getElementById('stat-classes-count').textContent =
        hasParsedClasses
            ? classesCount
            : (data.statistics?.total_files || 0);
    document.getElementById('stat-files-parsed').textContent = `${data.statistics?.parsed_files || 0} file(s) parsed successfully`;

    const couplingCount = data.statistics ? data.statistics.dependency_edges : 0;
    const circularCount = data.statistics ? data.statistics.circular_dependencies : 0;
    document.getElementById('stat-coupling-count').textContent = couplingCount;
    document.getElementById('stat-cyclic-count').textContent = `${circularCount} circular dependency chain(s)`;

    // Vulnerability summaries
    const outdatedCount = data.dependency_report?.outdated_dependencies?.length || 0;
    document.getElementById('stat-vulns-count').textContent = outdatedCount;
    
    const frameworks = data.dependency_report?.detected_frameworks || [];
    document.getElementById('stat-frameworks-detected').textContent = frameworks.length > 0 
        ? frameworks.join(', ') 
        : 'No major frameworks';

    // Reset and Render Tabs
    renderWebMetrics(data.statistics?.web_analysis);
    renderDjangoMetrics(data.statistics?.django_analysis);
    renderNodeMetrics(data.statistics?.node_analysis);
    renderCodeSmellsTable(data.debt_report?.issues || []);
    renderFrameworkTags(frameworks);
    renderVulnerabilitiesTable(data.dependency_report?.outdated_dependencies || []);
    renderDependencyGraph(data);
    renderKnowledgeGraph(data);
    renderReportFromCurrentData();
    renderRefactorIssues();

    // Reveal scan data and switch to the first results section.
    document.getElementById('scan-results-content').classList.remove('hidden');
    tabButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.tab === 'tab-smells');
    });
    tabPanes.forEach(pane => {
        pane.classList.toggle('active', pane.id === 'tab-smells');
    });
    resultsPanel.scrollIntoView({ behavior: 'smooth' });
}

function makeIssueKey(issue) {
    return [
        issue.rule || '',
        issue.class_name || '',
        issue.method_name || '',
        issue.file_path || ''
    ].join('|');
}

function renderRefactorIssues() {
    const container = document.getElementById('refactor-issue-list');
    const stackLabel = document.getElementById('refactor-stack-label');
    const generateButton = document.getElementById('btn-generate-optimized');
    if (!container || !stackLabel || !generateButton) return;

    const issues = currentScanData?.debt_report?.issues || [];
    const issueKeys = new Set(issues.map(makeIssueKey));
    selectedIssueKeys = new Set(
        [...selectedIssueKeys].filter(key => issueKeys.has(key))
    );
    visibleIssueKeys = issueKeys;
    const status = document.getElementById('refactor-status');
    const result = document.getElementById('refactor-result');
    if (status) status.textContent = '';
    if (result) result.classList.add('hidden');
    updateRefactorStackLabel();
    updateIssueSelectionUI();

    if (!currentScanData) {
        container.innerHTML = '<p class="empty-state">Run a scan to select issues for optimization.</p>';
        return;
    }
    if (!currentWorkdirPath) {
        container.innerHTML = '<p class="empty-state">No source project directory is available for this scan. Upload or scan a project directory before generating optimized code.</p>';
        return;
    }
    if (!issues.length) {
        container.innerHTML = '<p class="empty-state">The latest scan has no issues to optimize.</p>';
        return;
    }

    const severityOrder = ['critical', 'high', 'medium', 'low'];
    const groups = new Map(severityOrder.map(severity => [severity, []]));
    const otherIssues = [];
    issues.forEach((issue, index) => {
        const severity = String(issue.severity || '').toLowerCase();
        if (groups.has(severity)) groups.get(severity).push({ issue, index });
        else otherIssues.push({ issue, index });
    });

    const renderIssue = ({ issue, index }) => {
        const key = makeIssueKey(issue);
        const severity = String(issue.severity || 'Unknown');
        const normalizedSeverity = severity.toLowerCase();
        const severityClass = normalizedSeverity === 'critical'
            ? 'badge-high'
            : ['high', 'medium', 'low'].includes(normalizedSeverity)
                ? `badge-${normalizedSeverity}`
                : '';
        const location = [
            issue.class_name || 'Unknown class',
            issue.method_name || '',
            issue.file_path || 'Unknown file'
        ].filter(Boolean).join(' · ');
        return `
            <label class="refactor-issue-card">
                <input type="checkbox" class="refactor-issue-checkbox"
                    data-issue-key="${escapeHtml(key)}"
                    ${selectedIssueKeys.has(key) ? 'checked' : ''}
                    aria-label="Select issue ${index + 1}">
                <span class="refactor-issue-details">
                    <span class="refactor-issue-heading">
                        <strong>${escapeHtml(issue.rule || 'Finding')}</strong>
                        <span class="badge ${severityClass}">${escapeHtml(severity)}</span>
                    </span>
                    <span class="refactor-issue-location">${escapeHtml(location)}</span>
                    <span>${escapeHtml(issue.message || 'No issue description provided.')}</span>
                    <span class="refactor-issue-suggestion"><strong>Suggestion:</strong> ${escapeHtml(issue.suggestion || 'No suggestion provided.')}</span>
                </span>
            </label>
        `;
    };

    const sections = severityOrder
        .filter(severity => groups.get(severity).length)
        .map(severity => `
            <section class="refactor-severity-group">
                <h3>${severity[0].toUpperCase()}${severity.slice(1)} <span>(${groups.get(severity).length})</span></h3>
                ${groups.get(severity).map(renderIssue).join('')}
            </section>
        `);
    if (otherIssues.length) {
        sections.push(`
            <section class="refactor-severity-group">
                <h3>Other <span>(${otherIssues.length})</span></h3>
                ${otherIssues.map(renderIssue).join('')}
            </section>
        `);
    }
    container.innerHTML = sections.join('');
    updateIssueSelectionUI();
}

function updateRefactorStackLabel() {
    const stackLabel = document.getElementById('refactor-stack-label');
    if (!stackLabel) return;
    const detectedStack = currentScanStack
        || currentScanData?.stack
        || currentScanData?.statistics?.stack;
    stackLabel.textContent = detectedStack || getSelectedStack();
}

function updateIssueSelectionUI() {
    const selectedCount = document.getElementById('refactor-selected-count');
    const generateButton = document.getElementById('btn-generate-optimized');
    if (selectedCount) {
        selectedCount.textContent = `Selected: ${selectedIssueKeys.size}`;
    }
    if (generateButton) {
        generateButton.disabled = (
            selectedIssueKeys.size === 0
            || !currentScanData
            || !currentWorkdirPath
        );
    }
}

async function generateOptimizedCode() {
    const status = document.getElementById('refactor-status');
    const generateButton = document.getElementById('btn-generate-optimized');
    const resultContainer = document.getElementById('refactor-result');
    if (!currentScanData || !currentWorkdirPath) {
        if (status) status.textContent = 'Scan or upload a project before generating optimized code.';
        return;
    }

    const selectedKeys = [...selectedIssueKeys];
    if (!selectedKeys.length) {
        if (status) status.textContent = 'Select at least one issue to optimize.';
        return;
    }

    const selectAll = visibleIssueKeys.size > 0
        && [...visibleIssueKeys].every(key => selectedIssueKeys.has(key));
    generateButton.disabled = true;
    if (resultContainer) resultContainer.classList.add('hidden');
    if (status) status.innerHTML = '<span class="spinner refactor-spinner"></span> Generating optimized code...';

    try {
        const response = await fetch('/api/refactor/generate', {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_path: currentWorkdirPath,
                baseline_scan: currentScanData,
                issue_keys: selectedKeys,
                select_all: selectAll,
                stack: currentScanStack || getSelectedStack(),
                max_issues: 50
            })
        });
        const data = await response.json();
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error(
                    'The running backend does not have the refactor API route loaded. Restart the backend using the current backend/api/main.py, then refresh this page.'
                );
            }
            throw new Error(data.detail || 'Optimized code generation failed.');
        }

        currentOptimizationResult = data;
        renderOptimizationResult();
        renderComparison();
        if (status) {
            const failedCount = data.failed_issues?.length || 0;
            const generatedCount = data.generated_files?.length || 0;
            if (!generatedCount) {
                status.textContent = `No files were optimized. ${failedCount} issue(s) failed; see details below.`;
            } else if (failedCount) {
                status.textContent = `Partially optimized ${generatedCount} file(s); ${failedCount} issue(s) failed. See details below.`;
            } else {
                status.textContent = `Optimized ${generatedCount} file(s) successfully.`;
            }
        }
    } catch (error) {
        console.error('Optimized code generation failed:', error);
        if (status) status.textContent = `Generation failed: ${error.message}`;
    } finally {
        updateIssueSelectionUI();
    }
}

function renderOptimizationResult() {
    const container = document.getElementById('refactor-result');
    if (!container || !currentOptimizationResult) return;

    const files = currentOptimizationResult.generated_files || [];
    const failures = currentOptimizationResult.failed_issues || [];
    container.innerHTML = `
        ${files.length
            ? `<div class="refactor-success-message"><i class="fa-solid fa-circle-check"></i> Optimized ${files.length} file(s).</div>`
            : '<div class="refactor-failure-message"><i class="fa-solid fa-circle-exclamation"></i> No files were optimized. Review the failure details below and check your AI provider configuration.</div>'}
        <h3>Generated Files</h3>
        ${files.length
            ? `<ul class="refactor-file-list">${files.map(file => `<li>${escapeHtml(file)}</li>`).join('')}</ul>`
            : '<p class="empty-state">No files were generated.</p>'}
        ${failures.length
            ? `<h3>Issues not optimized</h3><ul class="refactor-file-list">${failures.map(item => `<li>${escapeHtml(item.issue?.file_path || item.issue?.rule || 'Issue')}: ${escapeHtml(item.error || 'Unknown error')}</li>`).join('')}</ul>`
            : ''}
        ${files.length && currentOptimizationResult.download_url
            ? '<button class="btn btn-glow" id="btn-download-optimized" type="button"><i class="fa-solid fa-download"></i> Download Optimized Code</button>'
            : ''}
    `;
    container.classList.remove('hidden');
}

function formatComparisonPath(filePath) {
    if (!filePath) return '';
    const parts = String(filePath).split(/[\\/]+/).filter(Boolean);
    return parts.slice(-3).join('/');
}

function renderComparisonList(title, items, variant) {
    const entries = Array.isArray(items) ? items : [];
    const content = entries.length
        ? entries.map(item => {
            if (typeof item === 'string') {
                return `<li class="comparison-issue"><strong>${escapeHtml(item)}</strong></li>`;
            }
            if (!item || typeof item !== 'object') {
                return `<li class="comparison-issue"><strong>${escapeHtml(String(item))}</strong></li>`;
            }

            const issueName = [
                item.rule || 'Finding',
                item.method_name || ''
            ].filter(Boolean).join(' · ');
            const className = item.class_name || '';
            const filePath = formatComparisonPath(item.file_path);
            return `
                <li class="comparison-issue">
                    <strong>${escapeHtml(issueName)}</strong>
                    ${className ? `<span class="comparison-issue-class">${escapeHtml(className)}</span>` : ''}
                    ${filePath ? `<code title="${escapeHtml(item.file_path || '')}">${escapeHtml(filePath)}</code>` : ''}
                    ${item.message ? `<span class="comparison-issue-message">${escapeHtml(item.message)}</span>` : ''}
                </li>
            `;
        }).join('')
        : '<li class="comparison-empty">No items</li>';

    return `
        <section class="comparison-section comparison-section-${variant}">
            <h3>${escapeHtml(title)} <span class="comparison-count">${entries.length}</span></h3>
            <ul>${content}</ul>
        </section>
    `;
}

function formatComparisonNumber(value, decimals = 0) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '0';
    return number.toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimals
    });
}

function renderFileComparison(fileComparisons, selectedPath, isOpen) {
    if (!Array.isArray(fileComparisons) || !fileComparisons.length) return '';
    const selectedFile = fileComparisons.find(file => file.path === selectedPath)
        || fileComparisons[0];
    const options = fileComparisons.map(file => `
        <option value="${escapeHtml(file.path)}" ${file.path === selectedFile.path ? 'selected' : ''}>
            ${escapeHtml(file.path)}
        </option>
    `).join('');

    return `
        <details class="comparison-code-details" ${isOpen ? 'open' : ''}>
            <summary>
                <span>View file-by-file code</span>
                <small>${fileComparisons.length} optimized file${fileComparisons.length === 1 ? '' : 's'}</small>
            </summary>
            <label class="comparison-file-picker" for="comparison-file-select">Choose a file</label>
            <select id="comparison-file-select" class="comparison-file-select">${options}</select>
            <div class="comparison-code-grid">
                <section class="comparison-code-pane comparison-code-before">
                    <h4><span>Before</span><code>${escapeHtml(selectedFile.path)}</code></h4>
                    <pre aria-label="Original code"><code>${escapeHtml(selectedFile.before_code || '')}</code></pre>
                </section>
                <section class="comparison-code-pane comparison-code-after">
                    <h4><span>After</span><code>${escapeHtml(selectedFile.path)}</code></h4>
                    <pre aria-label="Updated code"><code>${escapeHtml(selectedFile.after_code || '')}</code></pre>
                </section>
            </div>
        </details>
    `;
}

function renderComparison(selectedFilePath = null, fileComparisonOpen = false) {
    updateReportDownloadMode();
    const container = document.getElementById('comparison-content');
    if (!container) return;
    if (!currentOptimizationResult) {
        container.innerHTML = '<p class="empty-state">Generate optimized code first to view comparison.</p>';
        return;
    }

    const result = currentOptimizationResult;
    const comparison = result.comparison || {};
    const baseline = result.baseline_summary || {};
    const optimized = result.optimized_summary || {};
    const baselineSeverity = baseline.severity_counts || {};
    const optimizedSeverity = optimized.severity_counts || {};
    const severityOrder = ['critical', 'high', 'medium', 'low'];
    const severityNames = [...new Set([
        ...severityOrder.filter(name => baselineSeverity[name] !== undefined || optimizedSeverity[name] !== undefined),
        ...Object.keys(baselineSeverity),
        ...Object.keys(optimizedSeverity)
    ])];
    const severityRows = severityNames.length
        ? severityNames.map(name => {
            const beforeCount = Number(baselineSeverity[name] || 0);
            const afterCount = Number(optimizedSeverity[name] || 0);
            const delta = afterCount - beforeCount;
            const deltaClass = delta < 0 ? 'is-better' : delta > 0 ? 'is-worse' : 'is-unchanged';
            const deltaLabel = delta > 0 ? `+${delta}` : String(delta);
            return `
                <tr>
                    <td><span class="severity-label severity-${escapeHtml(name.toLowerCase())}">${escapeHtml(name)}</span></td>
                    <td>${formatComparisonNumber(beforeCount)}</td>
                    <td>${formatComparisonNumber(afterCount)}</td>
                    <td><span class="comparison-delta ${deltaClass}">${escapeHtml(deltaLabel)}</span></td>
                </tr>
            `;
        }).join('')
        : '<tr><td colspan="4">No severity data</td></tr>';

    const baselineScore = Number(comparison.baseline_score ?? baseline.total_score ?? 0);
    const currentScore = Number(comparison.current_score ?? optimized.total_score ?? 0);
    const scoreDelta = Number(comparison.score_delta ?? currentScore - baselineScore);
    const improvement = Number(comparison.improvement_percent ?? 0);
    const scoreState = scoreDelta < 0 ? 'is-better' : scoreDelta > 0 ? 'is-worse' : 'is-unchanged';
    const summaryLabel = scoreDelta < 0
        ? `Debt reduced by ${formatComparisonNumber(Math.abs(scoreDelta))} points`
        : scoreDelta > 0
            ? `Debt increased by ${formatComparisonNumber(scoreDelta)} points`
            : 'Debt score is unchanged';
    const baselineIssueCount = Number(
        comparison.baseline_issue_count ?? baseline.issue_count ?? 0
    );
    const currentIssueCount = Number(
        comparison.current_issue_count ?? optimized.issue_count ?? 0
    );
    const issueDelta = Number(
        comparison.issue_count_delta ?? (currentIssueCount - baselineIssueCount)
    );
    const issueDeltaClass = issueDelta < 0 ? 'is-better' : issueDelta > 0 ? 'is-worse' : 'is-unchanged';
    const generatedCount = (result.generated_files || []).length;

    container.innerHTML = `
        <div class="comparison-summary ${scoreState}">
            <span class="comparison-summary-indicator">${scoreDelta < 0 ? '↓' : scoreDelta > 0 ? '↑' : '↔'}</span>
            <div><strong>${escapeHtml(summaryLabel)}</strong><span>Lower debt scores indicate improvement.</span></div>
        </div>
        <div class="comparison-metrics">
            <div class="comparison-metric comparison-metric-before"><span>Before</span><small>Debt score</small><strong>${formatComparisonNumber(baselineScore)}</strong></div>
            <div class="comparison-metric comparison-metric-after"><span>After</span><small>Debt score</small><strong>${formatComparisonNumber(currentScore)}</strong></div>
            <div class="comparison-metric ${scoreState}"><span>Score change</span><small>After minus before</small><strong>${scoreDelta > 0 ? '+' : ''}${formatComparisonNumber(scoreDelta)}</strong></div>
            <div class="comparison-metric ${scoreState}"><span>Debt reduction</span><small>Relative to baseline</small><strong>${formatComparisonNumber(improvement, 1)}%</strong></div>
            <div class="comparison-metric comparison-metric-before"><span>Before</span><small>Issues</small><strong>${formatComparisonNumber(baselineIssueCount)}</strong></div>
            <div class="comparison-metric comparison-metric-after"><span>After</span><small>Issues</small><strong>${formatComparisonNumber(currentIssueCount)}</strong></div>
            <div class="comparison-metric ${issueDeltaClass}"><span>Issue change</span><small>After minus before</small><strong>${issueDelta > 0 ? '+' : ''}${formatComparisonNumber(issueDelta)}</strong></div>
            <div class="comparison-metric"><span>Files optimized</span><small>Generated source files</small><strong>${formatComparisonNumber(generatedCount)}</strong></div>
        </div>
        <section class="comparison-section">
            <h3>Issues by severity <span class="comparison-section-caption">Lower counts are better</span></h3>
            <div class="vulns-table-wrapper">
                <table class="dashboard-table comparison-severity-table">
                    <thead><tr><th>Severity</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
                    <tbody>${severityRows}</tbody>
                </table>
            </div>
        </section>
        <div class="comparison-lists">
            ${renderComparisonList('Fixed issues', comparison.fixed_issues, 'fixed')}
            ${renderComparisonList('New issues', comparison.new_issues, 'new')}
            ${renderComparisonList('Still present', comparison.still_present, 'present')}
            ${renderComparisonList('Improved classes', comparison.improved_classes, 'improved')}
            ${renderComparisonList('Worsened classes', comparison.worsened_classes, 'worsened')}
        </div>
        ${renderFileComparison(result.file_comparisons, selectedFilePath, fileComparisonOpen)}
        <div class="comparison-report-actions">
            <button class="btn btn-primary" id="btn-download-comparison-report" type="button">
                <i class="fa-solid fa-file-pdf"></i> Download Comparison Report
            </button>
            <span id="comparison-report-status" role="status" aria-live="polite"></span>
        </div>
        ${result.download_url
            ? '<button class="btn btn-glow" id="btn-download-optimized-comparison" type="button"><i class="fa-solid fa-download"></i> Download Optimized Code</button>'
            : ''}
    `;
}

async function downloadComparisonReport(
    buttonId = 'btn-download-comparison-report',
    statusId = 'comparison-report-status'
) {
    const button = document.getElementById(buttonId);
    const status = document.getElementById(statusId);
    const result = currentOptimizationResult;
    if (!currentScanData || !result?.optimized_scan || !result?.comparison) {
        if (status) status.textContent = 'Generate an optimized comparison before downloading this report.';
        return;
    }

    if (button) button.disabled = true;
    if (status) status.textContent = 'Generating PDF report...';
    try {
        const metadata = {
            ...(result.optimization_meta || {}),
            generated_files: result.generated_files || [],
            file_comparisons: result.file_comparisons || [],
            selected_issues: result.selected_issues || [],
            failed_issue_details: result.failed_issues || []
        };
        const response = await fetch('/api/report/comparison', {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                baseline_scan: currentScanData,
                optimized_scan: result.optimized_scan,
                comparison: result.comparison,
                optimization_meta: metadata
            })
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `Report request failed (${response.status}).`);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
            || 'intelli_code_comparison_report.pdf';
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        if (status) status.textContent = 'PDF report downloaded.';
    } catch (error) {
        console.error('Comparison report generation failed:', error);
        if (status) status.textContent = `Report generation failed: ${error.message}`;
    } finally {
        if (button) button.disabled = false;
    }
}

function updateReportDownloadMode() {
    const button = document.getElementById('btn-download-report');
    const reportStatus = document.getElementById('report-status');
    if (!button || !reportStatus) return;

    const hasComparison = Boolean(
        currentOptimizationResult?.optimized_scan
        && currentOptimizationResult?.comparison
    );
    button.innerHTML = hasComparison
        ? '<i class="fa-solid fa-file-pdf"></i> Download Comparison Report'
        : '<i class="fa-solid fa-file-pdf"></i> Download PDF';
    button.title = hasComparison
        ? 'Download the same before-and-after PDF shown in the Comparison section.'
        : 'Download the current scan report.';
    reportStatus.textContent = hasComparison ? 'Before / After Comparison' : 'Current scan';
    const downloadStatus = document.getElementById('report-download-status');
    if (downloadStatus) downloadStatus.textContent = '';
}

function downloadOptimizedCode() {
    if (currentOptimizationResult?.download_url) {
        window.location.assign(currentOptimizationResult.download_url);
    }
}

function renderWebMetrics(webAnalysis) {
    const panel = document.getElementById('web-metrics-panel');
    const grid = document.getElementById('web-metrics-grid');
    if (!panel || !grid) return;
    if (!webAnalysis?.metrics) {
        panel.classList.add('hidden');
        grid.replaceChildren();
        return;
    }

    const metrics = webAnalysis.metrics;
    const html = metrics.html?.totals || {};
    const css = metrics.css?.totals || {};
    const js = metrics.javascript?.totals || {};
    const coupling = Object.values(metrics.coupling || {});
    const orphanDomReferences = new Set(coupling.flatMap(entry => [
        ...(entry.orphan_js_id_names || []).map(name => `id:${name}`),
        ...(entry.orphan_html_id_names || []).map(name => `id:${name}`),
        ...(entry.orphan_js_class_names || []).map(name => `class:${name}`),
        ...(entry.orphan_html_class_names || []).map(name => `class:${name}`)
    ])).size;
    const domCoupling = coupling.length
        ? coupling.reduce((total, entry) => total + entry.dom_coupling_score, 0) / coupling.length
        : 0;
    const cards = [
        ['Web debt score', webAnalysis.summary?.debt_score ?? 0],
        ['HTML elements', html.elements || 0],
        ['Semantic ratio', `${Math.round((html.semantic_ratio || 0) * 100)}%`],
        ['Inline styles / handlers', `${html.inline_styles || 0} / ${html.inline_handlers || 0}`],
        ['CSS rules / declarations', `${css.rules || 0} / ${css.declarations || 0}`],
        ['CSS !important', css.important_count || 0],
        ['CSS duplicate selectors / colors', `${css.duplicate_selectors || 0} / ${css.hardcoded_colors || 0}`],
        ['JavaScript LOC / functions', `${js.loc || 0} / ${js.functions || 0}`],
        ['JavaScript var / let / const', `${js.var_count || 0} / ${js.let_count || 0} / ${js.const_count || 0}`],
        ['JavaScript safety flags', `${js.eval_calls || 0} eval · ${js.innerHTML_uses || 0} innerHTML`],
        ['DOM coupling score', domCoupling.toFixed(2)],
        ['HTML classes', html.class_count || 0],
        ['CSS unique selectors', css.unique_selectors || 0],
        ['Orphan DOM IDs / classes', orphanDomReferences]
    ];
    grid.innerHTML = cards.map(([label, value]) => `
        <div class="web-metric-card">
            <span>${label}</span>
            <strong>${value}</strong>
        </div>
    `).join('');
    panel.classList.remove('hidden');
}

function renderDjangoMetrics(djangoAnalysis) {
    const panel = document.getElementById('django-metrics-panel');
    const grid = document.getElementById('django-metrics-grid');
    if (!panel || !grid) return;
    if (!djangoAnalysis?.metrics) {
        panel.classList.add('hidden');
        grid.replaceChildren();
        return;
    }

    const metrics = djangoAnalysis.metrics;
    const views = Object.values(metrics.views || {});
    const templates = Object.values(metrics.templates || {});
    const architecture = metrics.architecture || {};
    const orm = metrics.orm || {};
    const templateTotals = templates.reduce((total, item) => ({
        safeFilters: total.safeFilters + (item.safe_filters || 0),
        inlineScripts: total.inlineScripts + (item.inline_scripts || 0),
        ifBlocks: total.ifBlocks + (item.if_blocks || 0)
    }), { safeFilters: 0, inlineScripts: 0, ifBlocks: 0 });
    const queryCounts = Object.values(orm.queries_per_function || {});
    const queryTotal = queryCounts.reduce((total, count) => total + count, 0);
    const cards = [
        ['Django debt score', djangoAnalysis.summary?.debt_score ?? 0],
        ['Django version', metrics.django_version || 'Not detected'],
        ['Django apps', architecture.app_count || 0],
        ['Views / maximum LOC', `${views.reduce((total, item) => total + (item.view_count || 0), 0)} / ${Math.max(0, ...views.map(item => item.max_view_loc || 0))}`],
        ['ORM queries / functions', `${queryTotal} / ${queryCounts.length}`],
        ['N+1 / loop-query risks', orm.n_plus_one_risk || 0],
        ['Templates / conditional blocks', `${templates.length} / ${templateTotals.ifBlocks}`],
        ['Unsafe filters / inline scripts', `${templateTotals.safeFilters} / ${templateTotals.inlineScripts}`],
        ['Fat model / view files', `${architecture.fat_models || 0} / ${architecture.fat_views || 0}`]
    ];
    grid.innerHTML = cards.map(([label, value]) => `
        <div class="web-metric-card">
            <span>${label}</span>
            <strong>${value}</strong>
        </div>
    `).join('');
    panel.classList.remove('hidden');
}

function renderNodeMetrics(nodeAnalysis) {
    const panel = document.getElementById('node-metrics-panel');
    const grid = document.getElementById('node-metrics-grid');
    if (!panel || !grid) return;
    if (!nodeAnalysis?.metrics) {
        panel.classList.add('hidden');
        grid.replaceChildren();
        return;
    }

    const metrics = nodeAnalysis.metrics;
    const packages = metrics.packages || {};
    const dependencies = metrics.dependencies || {};
    const asyncFiles = Object.values(metrics.async || {});
    const securityFiles = Object.values(metrics.security || {});
    const routes = Object.values(metrics.routes || {});
    const total = (items, key) => items.reduce((sum, item) => sum + (item[key] || 0), 0);
    const cards = [
        ['Node.js debt score', nodeAnalysis.summary?.debt_score ?? 0],
        ['Framework', nodeAnalysis.framework || 'Node.js core'],
        ['Package / lockfile', `${dependencies.total || 0} / ${packages.lockfile ? 'present' : 'missing'}`],
        ['Dependencies (production / dev)', `${dependencies.production || 0} / ${dependencies.dev || 0}`],
        ['Package scripts', (packages.scripts || []).length],
        ['Async / await / promise chains', `${total(asyncFiles, 'async_functions')} / ${total(asyncFiles, 'await_count')} / ${total(asyncFiles, 'then_count')}`],
        ['Promise rejection handlers', total(asyncFiles, 'catch_count')],
        ['Routes / write routes', `${total(routes, 'route_count')} / ${total(routes, 'writes')}`],
        ['Security signals: eval / exec', `${total(securityFiles, 'eval_calls')} / ${total(securityFiles, 'exec_calls')}`],
        ['Hardcoded secrets', total(securityFiles, 'hardcoded_secrets')]
    ];
    grid.innerHTML = cards.map(([label, value]) => `
        <div class="web-metric-card">
            <span>${label}</span>
            <strong>${value}</strong>
        </div>
    `).join('');
    panel.classList.remove('hidden');
}

// --- Render Code Smells ---
function getSmellPhase(ruleName = '') {
    const normalized = String(ruleName || '').trim();
    const phaseSequence = [
        { phase: '1. File / Package', rules: ['PackageStructure', 'UnnecessaryPackageDeclaration', 'MultipleClassesInOneFile', 'UnusedClass', 'ClassWithOnlyData', 'UnresolvedTodo', 'MissingDocstring'] },
        { phase: '2. Imports', rules: ['UnusedImport', 'UnusedImports', 'DuplicateImport', 'WildcardImport', 'ImportOrdering', 'UnnecessaryImport'] },
        { phase: '3. Class / Interface / Enum', rules: ['GodClass', 'LargeClass', 'ExcessiveInheritance', 'DeepInheritance', 'HighCoupling', 'UtilityClassWithInstanceMethods'] },
        { phase: '4. Fields / Variables', rules: ['UnusedVariable', 'UnusedField', 'MutableClassAttribute', 'MutableDefaultArgument', 'VariableDeclaredTooEarly', 'VariableNeverReassigned', 'MagicNumber', 'MagicNumbers', 'PoorVariableName', 'DuplicateLocalVariable', 'VarInsteadOfLetConst', 'GlobalVariablePollution'] },
        { phase: '5. Constructors', rules: ['DuplicateConstructors', 'ExcessiveConstructorParameters', 'ConstructorDoingTooMuch'] },
        { phase: '6. Methods', rules: ['LongMethod', 'DuplicateMethod', 'MethodTooComplex', 'MethodMultipleResponsibilities', 'MethodNeverCalled', 'PrivateMethodUnused', 'MethodCouldBeStatic', 'HighCyclomaticComplexity', 'DeadMethod', 'DeepNesting', 'LongFunction', 'CallbackHell'] },
        { phase: '7. Parameters', rules: ['ExcessiveParameterList', 'UnusedParameter', 'ParameterReassignment', 'MethodWithTooManyParameters'] },
        { phase: '8. Statements', rules: ['DuplicateCode', 'EmptyStatement', 'DuplicateStatements', 'UnnecessaryTemporaryVariable', 'UnnecessaryObjectCreation', 'StringConcatenationInLoop', 'LooseEquality', 'InlineStyle', 'InlineEventHandler', 'DeprecatedTag', 'MissingDoctype'] },
        { phase: '9. Conditions', rules: ['ComplexCondition', 'NestedIf', 'DuplicateCondition', 'BooleanComparison', 'ConditionalComplexity'] },
        { phase: '10. Switch', rules: ['DuplicateSwitchLogic', 'LargeSwitch', 'MissingDefaultCase'] },
        { phase: '11. Loops', rules: ['UnnecessaryLoop', 'NestedLoop', 'LoopInvariantCode', 'UnnecessaryLoopCalculation'] },
        { phase: '12. Expressions', rules: ['RedundantExpression', 'ConstantExpression', 'StringConcatenationInLoop'] },
        { phase: '13. Exceptions', rules: ['EmptyCatchBlock', 'EmptyExceptBlock', 'BroadExceptionHandling', 'GenericExceptionHandling', 'SwallowingException', 'ThrowingGenericException', 'UnclosedResource'] },
        { phase: '14. OOP Design', rules: ['ExtractMethod', 'ExtractClass', 'MoveMethod', 'MoveField', 'ExtractInterface', 'ReplaceInheritanceWithComposition', 'ReplaceConditionalWithPolymorphism'] },
        { phase: '15. Dependencies / Coupling', rules: ['HighCoupling', 'CircularDependency', 'FeatureEnvy', 'DependencyCycle', 'CyclicDependency'] },
        { phase: '16. Dead / Unused Code', rules: ['UnusedImports', 'UnusedMethods', 'UnusedFields', 'UnusedClasses', 'UnreachableCode', 'UnusedParameter', 'DeadMethod', 'UnusedCssClass', 'UndefinedCssClass', 'UnusedJsFunction'] },
        { phase: '17. Performance', rules: ['InefficientLookup', 'RepeatedExpensiveOperation', 'InefficientStringOperations', 'WrongCollectionChoice', 'UnnecessaryObjectCreation', 'MissingEventListenerCleanup'] },
        { phase: '18. Security / Reliability', rules: ['HardcodedCredentials', 'DjangoHardcodedSecret', 'DjangoDebugEnabled', 'DjangoRawSql', 'DynamicCodeExecution', 'UnsafeDynamicExecution', 'SqlInjection', 'HardcodedAPIKey', 'HardcodedSecret', 'UnsafeSQL', 'UnsafeDeserialization', 'WeakHashAlgorithm', 'WeakCryptographicAlgorithm', 'UnvalidatedInput', 'InsecureFileHandling', 'ResourceLeak', 'UnsafeEval', 'UnsafeInnerHTML', 'MissingImageAlt'] },
        { phase: '19. Complexity / Metrics', rules: ['HighCyclomaticComplexity', 'MagicNumber', 'DeepNesting', 'LargeClass', 'GodClass', 'ConsoleStatement', 'ConsoleLogInProduction', 'InlineHtmlStyle', 'CssImportantOverride', 'ExcessiveImportant', 'HardcodedColor', 'DuplicateSelector', 'DeepSelectorNesting', 'NonSemanticDivSoup', 'NodeSynchronousIo'] },
        { phase: '20. General Review', rules: [] }
    ];

    const match = phaseSequence.find(group =>
        group.rules.some(rule => {
            const target = String(rule).toLowerCase();
            const value = normalized.toLowerCase();
            return value === target || value.includes(target) || target.includes(value);
        })
    );

    return match ? match.phase : '20. General Review';
}

function renderCodeSmellsTable(issues) {
    const container = document.getElementById('smells-tbody');
    container.innerHTML = '';

    if (issues.length === 0) {
        container.innerHTML = `
            <div class="empty-phase-state">
                <i class="fa-solid fa-circle-check"></i>
                No design or code smells detected! Your code is clean.
            </div>
        `;
        return;
    }

    const phaseOrder = {
        '1. File / Package': 1,
        '2. Imports': 2,
        '3. Class / Interface / Enum': 3,
        '4. Fields / Variables': 4,
        '5. Constructors': 5,
        '6. Methods': 6,
        '7. Parameters': 7,
        '8. Statements': 8,
        '9. Conditions': 9,
        '10. Switch': 10,
        '11. Loops': 11,
        '12. Expressions': 12,
        '13. Exceptions': 13,
        '14. OOP Design': 14,
        '15. Dependencies / Coupling': 15,
        '16. Dead / Unused Code': 16,
        '17. Performance': 17,
        '18. Security / Reliability': 18,
        '19. Complexity / Metrics': 19,
        '20. General Review': 20
    };

    const phaseGroups = new Map();
    const orderedPhases = Object.keys(phaseOrder).sort((a, b) => phaseOrder[a] - phaseOrder[b]);

    issues.forEach(issue => {
        const phase = getSmellPhase(issue.rule);
        if (!phaseGroups.has(phase)) phaseGroups.set(phase, []);
        phaseGroups.get(phase).push(issue);
    });

    orderedPhases.forEach(phase => {
        const phaseIssues = phaseGroups.get(phase) || [];
        if (!phaseIssues.length) return;

        const item = document.createElement('div');
        item.className = 'smell-phase-item';

        const phaseHeader = document.createElement('button');
        phaseHeader.type = 'button';
        phaseHeader.className = 'smell-phase-header';
        phaseHeader.innerHTML = `
            <span>${escapeHtml(phase)}</span>
            <span class="smell-phase-count">${phaseIssues.length}</span>
        `;

        const phaseBody = document.createElement('div');
        phaseBody.className = 'smell-phase-body hidden';

        const list = document.createElement('div');
        list.className = 'smell-phase-list';

        phaseIssues
            .slice()
            .sort((a, b) => String(a.rule).localeCompare(String(b.rule)))
            .forEach(issue => {
                const row = document.createElement('div');
                const severity = String(issue.severity || 'low');
                const severityClass = `badge-${severity.toLowerCase()}`;
                row.className = 'smell-row';
                row.innerHTML = `
                    <div class="smell-row-main">
                        <strong>${escapeHtml(issue.rule)}</strong>
                        <span class="smell-location">${escapeHtml(issue.class_name || 'Unknown class')}</span>
                    </div>
                    <div class="smell-row-meta">
                        <span>Line: ${issue.line_number ?? 'N/A'}</span>
                        <span>Score: ${issue.metric_value ?? 'N/A'}</span>
                        <span class="badge ${severityClass}">${escapeHtml(severity)}</span>
                    </div>
                    <button class="btn-view-detail" data-id="${escapeHtml(issue.rule)}-${escapeHtml(issue.class_name)}-${issue.line_number}">View Detail</button>
                `;

                row.querySelector('.btn-view-detail').addEventListener('click', () => showSmellDetail(issue));
                list.appendChild(row);
            });

        phaseBody.appendChild(list);
        phaseHeader.addEventListener('click', () => {
            phaseBody.classList.toggle('hidden');
            phaseHeader.classList.toggle('expanded');
        });

        item.appendChild(phaseHeader);
        item.appendChild(phaseBody);
        container.appendChild(item);
    });
}

function showSmellDetail(issue) {
    document.getElementById('modal-smell-title').textContent = `${issue.rule} Smell Detail`;
    
    const severityBadge = document.getElementById('modal-smell-severity');
    severityBadge.className = `badge badge-${issue.severity.toLowerCase()}`;
    severityBadge.textContent = issue.severity;

    document.getElementById('modal-smell-class').textContent = issue.class_name;
    document.getElementById('modal-smell-line').textContent = issue.line_number;
    document.getElementById('modal-smell-desc').textContent = issue.message;
    
    const remediationText = document.getElementById('modal-smell-remediation');
    if (issue.suggestion) {
        document.getElementById('modal-remediation-section').classList.remove('hidden');
        remediationText.textContent = issue.suggestion;
    } else {
        document.getElementById('modal-remediation-section').classList.add('hidden');
    }

    smellModal.classList.remove('hidden');
}

// --- Render Frameworks and Vulnerabilities ---
function renderFrameworkTags(frameworks) {
    const container = document.getElementById('framework-tags');
    container.innerHTML = '';
    
    if (frameworks.length === 0) {
        container.innerHTML = `<span class="text-muted">No specific frameworks detected.</span>`;
        return;
    }

    frameworks.forEach(fw => {
        const tag = document.createElement('span');
        tag.className = 'framework-tag';
        tag.textContent = fw;
        container.appendChild(tag);
    });
}

function renderVulnerabilitiesTable(vulns) {
    const tbody = document.getElementById('vulns-tbody');
    tbody.innerHTML = '';

    const buildTool = currentScanData.dependency_report?.build_tool || 'N/A';
    document.getElementById('build-tool-badge').textContent = buildTool;

    if (vulns.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                    <i class="fa-solid fa-shield-halved" style="color: var(--accent-emerald); font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
                    No known vulnerable/outdated dependencies detected.
                </td>
            </tr>
        `;
        return;
    }

    vulns.forEach(v => {
        const tr = document.createElement('tr');
        
        // Critical or High styling
        const severityLower = v.severity.toLowerCase();
        const severityClass = severityLower === 'critical' ? 'badge-high' : `badge-${severityLower}`;
        
        tr.innerHTML = `
            <td>
                <strong>${escapeHtml(v.group)}</strong><span style="color: var(--text-muted);">:</span>${escapeHtml(v.artifact)}
            </td>
            <td><span class="badge ${severityClass}">${escapeHtml(v.severity)}</span></td>
            <td><code class="code-block">${escapeHtml(v.current_version)}</code></td>
            <td><code class="code-block" style="color: var(--accent-emerald);">${escapeHtml(v.minimum_safe_version)}</code></td>
            <td><span class="dependency-reason">${escapeHtml(v.reason)}</span></td>
        `;

        tbody.appendChild(tr);
    });
}

// --- Render Dependency Graph ---
function renderDependencyGraph(data) {
    const container = document.getElementById('network-graph');
    
    // Clear sidebar selection
    document.getElementById('no-node-selected-msg').classList.remove('hidden');
    document.getElementById('node-metrics-info').classList.add('hidden');

    const graphStats = data.statistics?.graph;
    if (!graphStats || !data.classes || data.classes.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; color: var(--text-muted); padding: 4rem;">
                No dependency graph metrics available.
            </div>
        `;
        return;
    }

    const classesMap = {};
    data.classes.forEach(cls => {
        classesMap[cls.package + '.' + cls.name] = cls;
    });

    const coupling = graphStats.coupling_metrics || {};
    const nodesArray = [];
    const edgesArray = [];

    // Create Nodes
    Object.keys(coupling).forEach(fqn => {
        const metric = coupling[fqn];
        const parts = fqn.split('.');
        const shortName = parts[parts.length - 1];
        
        // Size proportional to afferent coupling (incoming edges)
        const size = 15 + (metric.afferent_coupling * 5);
        
        // Color based on Instability Index (0 = stable = cyan, 1 = unstable = red/pink)
        const instability = metric.instability;
        const color = getInstabilityColor(instability);

        nodesArray.push({
            id: fqn,
            label: shortName,
            title: fqn,
            shape: 'dot',
            size: size,
            color: {
                background: color,
                border: '#1e293b',
                highlight: {
                    background: color,
                    border: '#f8fafc'
                }
            },
            font: {
                color: '#f8fafc',
                face: 'Inter',
                size: 12
            },
            borderWidth: 2,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.4)',
                size: 8,
                x: 0,
                y: 4
            }
        });
    });

    // Create Edges
    const rawEdges = data.dependencies || [];
    rawEdges.forEach(edge => {
        edgesArray.push({
            from: edge.from,
            to: edge.to,
            arrows: 'to',
            color: {
                color: 'rgba(99, 102, 241, 0.4)',
                highlight: '#6366f1',
                hover: '#a855f7'
            },
            label: edge.type !== 'calls' ? edge.type : '',
            font: {
                color: '#64748b',
                face: 'Inter',
                size: 9,
                align: 'middle'
            },
            width: 1.5,
            smooth: {
                type: 'cubicBezier',
                roundness: 0.4
            }
        });
    });

    const nodes = new vis.DataSet(nodesArray);
    const edges = new vis.DataSet(edgesArray);

    const graphData = { nodes, edges };
    const options = {
        interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: true
        },
        physics: {
            stabilization: {
                iterations: 150,
                fit: true
            },
            barnesHut: {
                gravitationalConstant: -2000,
                centralGravity: 0.3,
                springLength: 95,
                springConstant: 0.04
            }
        }
    };

    networkInstance = new vis.Network(container, graphData, options);

    // Click handler on nodes
    networkInstance.on('click', (params) => {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showNodeDetails(nodeId, coupling[nodeId]);
        } else {
            // Hide details
            document.getElementById('no-node-selected-msg').classList.remove('hidden');
            document.getElementById('node-metrics-info').classList.add('hidden');
        }
    });
}

function renderKnowledgeGraph(data) {
    const container = document.getElementById('knowledge-graph');
    const classes = data.classes || [];
    if (!classes.length) {
        container.innerHTML = '<p class="empty-state">No class structure was found for this scan.</p>';
        return;
    }

    const nodes = [];
    const edges = [];
    const packages = new Set();
    const classIds = new Map();
    const projectId = 'kg:project';
    nodes.push({ id: projectId, label: data.project_name || 'Project', group: 'project', shape: 'star', size: 28 });

    classes.forEach(cls => {
        const packageName = cls.package || '(default)';
        const packageId = `kg:package:${packageName}`;
        const fqn = packageName === '(default)' ? cls.name : `${packageName}.${cls.name}`;
        const classId = `kg:class:${fqn}`;
        classIds.set(fqn, classId);
        if (!packages.has(packageName)) {
            packages.add(packageName);
            nodes.push({ id: packageId, label: packageName, group: 'package', shape: 'box' });
            edges.push({ from: projectId, to: packageId, arrows: 'to' });
        }
        nodes.push({ id: classId, label: cls.name, group: 'class', title: fqn, shape: 'dot', size: 20 });
        edges.push({ from: packageId, to: classId, arrows: 'to' });

        (cls.methods || []).forEach((method, index) => {
            const methodId = `kg:method:${fqn}:${method.name}:${index}`;
            nodes.push({ id: methodId, label: method.name, group: 'method', shape: 'ellipse', size: 12 });
            edges.push({ from: classId, to: methodId, arrows: 'to', dashes: true });
        });
    });

    (data.dependencies || []).forEach(dependency => {
        const from = classIds.get(dependency.from) || classIds.get(dependency.from?.split('.').slice(-2).join('.'));
        const to = classIds.get(dependency.to) || classIds.get(dependency.to?.split('.').slice(-2).join('.'));
        if (from && to) edges.push({ from, to, arrows: 'to', color: { color: '#f59e0b' } });
    });

    knowledgeNetworkInstance = new vis.Network(
        container,
        { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) },
        {
            interaction: { hover: true, navigationButtons: true },
            physics: { stabilization: { iterations: 120 }, barnesHut: { gravitationalConstant: -1800 } },
            groups: {
                project: { color: { background: '#f59e0b', border: '#fbbf24' }, font: { color: '#f8fafc' } },
                package: { color: { background: '#06b6d4', border: '#67e8f9' }, font: { color: '#f8fafc' } },
                class: { color: { background: '#6366f1', border: '#a5b4fc' }, font: { color: '#f8fafc' } },
                method: { color: { background: '#10b981', border: '#6ee7b7' }, font: { color: '#f8fafc', size: 10 } }
            }
        }
    );
    knowledgeNetworkInstance.on('click', params => {
        const nodeId = params.nodes[0];
        if (!nodeId) return;
        const node = knowledgeNetworkInstance.body.nodes[nodeId];
        const selected = node && node.options;
        document.getElementById('knowledge-details-sidebar').dataset.nodeType = selected.group;
        document.getElementById('no-kg-node-selected-msg').classList.add('hidden');
        document.getElementById('kg-node-metrics-info').classList.remove('hidden');
        document.getElementById('kg-node-name').textContent = selected.label;
        document.getElementById('kg-node-kind').textContent = selected.group;
        document.getElementById('kg-node-degree').textContent = knowledgeNetworkInstance.getConnectedEdges(nodeId).length;
        document.getElementById('kg-node-desc').textContent = `${selected.label} is connected to ${knowledgeNetworkInstance.getConnectedEdges(nodeId).length} project element(s).`;
    });
}

function renderReportFromCurrentData() {
    if (!currentScanData) return;
    if (!authToken) {
        renderReport({ scans: [] });
        return;
    }
    fetch('/api/history', { headers: authHeaders() })
        .then(response => response.ok ? response.json() : Promise.reject())
        .then(renderReport)
        .catch(() => renderReport({ scans: [] }));
}

function renderReport(data) {
    const report = document.getElementById('report-content');
    if (!currentScanData) {
        report.innerHTML = '<p class="empty-state">Run a scan to generate a report.</p>';
        return;
    }

    const stats = currentScanData.statistics || {};
    const debt = currentScanData.debt_report || {};
    const dependency = currentScanData.dependency_report || {};
    const issues = Array.isArray(debt.issues) ? debt.issues : [];
    const ruleCounts = debt.rule_counts || {};
    const severityCounts = debt.severity_counts || {};
    const frameworks = Array.isArray(dependency.detected_frameworks) ? dependency.detected_frameworks : [];
    const outdatedDeps = Array.isArray(dependency.outdated_dependencies) ? dependency.outdated_dependencies : [];
    const vulnerabilityItems = Array.isArray(dependency.outdated_dependencies) ? dependency.outdated_dependencies : [];
    const projectName = currentScanData.project_name || 'Uploaded Project';
    const totalFiles = Number(stats.total_files || stats.parsed_files || 0);
    const parsedFiles = Number(stats.parsed_files || 0);
    const failedFiles = Number(stats.failed_files || Math.max(totalFiles - parsedFiles, 0));
    const totalClasses = Number(stats.total_classes || 0);
    const totalInterfaces = Number(stats.total_interfaces || 0);
    const totalMethods = Number(stats.total_methods || 0);
    const totalFields = Number(stats.total_fields || 0);
    const totalIssues = issues.length;
    const scanDuration = Number(stats.scan_time_seconds || 0);
    const dependencyEdges = Number(stats.dependency_edges || 0);
    const circularDependencies = Number(stats.circular_dependencies || 0);
    const totalDependencies = Number((dependency.dependencies || []).length || dependencyEdges || 0);

    const severityMap = { critical: 0, high: 0, medium: 0, low: 0 };
    issues.forEach(issue => {
        const key = String(issue.severity || '').toLowerCase();
        if (severityMap[key] !== undefined) severityMap[key] += 1;
    });

    const parseSuccessRate = totalFiles ? (parsedFiles / totalFiles) * 100 : 0;
    const parseFailureRate = totalFiles ? (failedFiles / totalFiles) * 100 : 0;
    const filesPerSecond = scanDuration > 0 ? parsedFiles / scanDuration : 0;
    const avgParseTimePerFile = parsedFiles ? scanDuration / parsedFiles : 0;
    const issueDensity = parsedFiles ? totalIssues / parsedFiles : 0;
    const issuesPerClass = totalClasses ? totalIssues / totalClasses : 0;
    const issuesPerMethod = totalMethods ? totalIssues / totalMethods : 0;
    const criticalPct = totalIssues ? (severityMap.critical / totalIssues) * 100 : 0;
    const highPct = totalIssues ? (severityMap.high / totalIssues) * 100 : 0;
    const mediumPct = totalIssues ? (severityMap.medium / totalIssues) * 100 : 0;
    const lowPct = totalIssues ? (severityMap.low / totalIssues) * 100 : 0;

    const topRules = Object.entries(ruleCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const highestRule = topRules[0] ? topRules[0][0] : 'N/A';
    const dependencyVulnerabilityRate = totalDependencies ? (outdatedDeps.length / totalDependencies) * 100 : 0;

    const saved = Array.isArray(data.scans) ? data.scans : [];
    const first = saved[0];
    const firstIsCurrent = first && first.project_name === projectName && first.debt_score === (debt.total_score || 0) && first.issue_count === totalIssues;
    const previous = firstIsCurrent ? saved[1] : first;
    const scoreDelta = previous ? previous.debt_score - (debt.total_score || 0) : null;
    const issueDelta = previous ? previous.issue_count - totalIssues : null;

    const formatPercent = (value) => {
        if (!Number.isFinite(Number(value))) return 'N/A';
        return `${Number(value).toFixed(1)}%`;
    };

    const formatMetric = (value) => {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A';
        return Number(value).toFixed(2);
    };

    const buildCategoryBuckets = () => {
        const buckets = {
            Complexity: 0,
            Coupling: 0,
            'Dead Code': 0,
            'Duplicate Code': 0,
            Design: 0,
            Maintainability: 0,
            Dependency: 0,
            Security: 0
        };

        Object.entries(ruleCounts).forEach(([rule, count]) => {
            const name = String(rule).toLowerCase();
            if (['longmethod', 'highcyclomaticcomplexity', 'deepnesting', 'magicnumber'].some(v => name.includes(v))) buckets.Complexity += count;
            if (['highcoupling', 'featureenvy', 'circulardependency', 'dependencycycle', 'cyclicdependency'].some(v => name.includes(v))) buckets.Coupling += count;
            if (['unusedvariable', 'deadmethod', 'unusedparameter', 'unusedimport', 'unusedfield', 'unusedclass'].some(v => name.includes(v))) buckets['Dead Code'] += count;
            if (['duplicatecode', 'duplicate', 'duplicated'].some(v => name.includes(v))) buckets['Duplicate Code'] += count;
            if (['godclass', 'largeclass', 'deepinheritance', 'extractclass', 'extractmethod'].some(v => name.includes(v))) buckets.Design += count;
            if (['magicnumber', 'missingjavadoc', 'longmethod', 'excessiveparameterlist', 'poorvariablename'].some(v => name.includes(v))) buckets.Maintainability += count;
            if (['hardcodedcredentials', 'security', 'genericexceptionhandling', 'unclosedresource', 'insecurefilehandling', 'unsafe'].some(v => name.includes(v))) buckets.Security += count;
            if (['circulardependency', 'highcoupling', 'featureenvy'].some(v => name.includes(v))) buckets.Dependency += count;
        });

        return Object.entries(buckets).map(([category, value]) => ({ category, value, percent: totalIssues ? (value / totalIssues) * 100 : 0 }));
    };

    const categoryStats = buildCategoryBuckets().filter(item => item.value > 0);
    const severityRows = [
        ['Critical', severityMap.critical, criticalPct],
        ['High', severityMap.high, highPct],
        ['Medium', severityMap.medium, mediumPct],
        ['Low', severityMap.low, lowPct]
    ];

    const ruleTableRows = topRules.map(([rule, count]) => {
        const percent = totalIssues ? (count / totalIssues) * 100 : 0;
        return `<tr><td>${escapeHtml(rule)}</td><td>${count}</td><td>${formatPercent(percent)}</td></tr>`;
    }).join('') || '<tr><td colspan="3">No rule data available.</td></tr>';

    const interpretationText = `The scan identified ${totalIssues} technical-debt issues across ${parsedFiles} successfully analyzed files. The largest concentration belongs to ${escapeHtml(highestRule)}, and the measured issue density is ${formatMetric(issueDensity)} issues per file. The analyzer parsed ${formatPercent(parseSuccessRate)} of discovered files in ${formatMetric(scanDuration)} seconds, producing ${formatMetric(filesPerSecond)} files/second.`;

    const validationStatus = `Formal accuracy measurement is not available for this scan because no ground-truth dataset has been provided. The report therefore relies on measured analysis quality indicators such as parse success rate, rule execution coverage, and analyzed file counts.`;

    const projectSummaryCards = `
        <div class="report-summary-grid">
            <div class="report-metric"><span>Parse Success</span><strong>${formatPercent(parseSuccessRate)}</strong></div>
            <div class="report-metric"><span>Files / Second</span><strong>${formatMetric(filesPerSecond)}</strong></div>
            <div class="report-metric"><span>Issues Detected</span><strong>${totalIssues}</strong></div>
            <div class="report-metric"><span>Dependencies</span><strong>${totalDependencies}</strong></div>
            <div class="report-metric"><span>Scan Duration</span><strong>${formatMetric(scanDuration)}s</strong></div>
            <div class="report-metric"><span>Precision</span><strong>N/A</strong></div>
        </div>
    `;

    report.innerHTML = `
        <div class="report-document">
            ${projectSummaryCards}

            <section class="report-section">
                <h3>1. Project Overview</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Project name</span><strong>${escapeHtml(projectName)}</strong></div>
                    <div class="report-card"><span>Build tool</span><strong>${escapeHtml(dependency.build_tool || 'N/A')}</strong></div>
                    <div class="report-card"><span>Scan duration</span><strong>${formatMetric(scanDuration)}s</strong></div>
                    <div class="report-card"><span>Analysis date</span><strong>${new Date().toLocaleDateString()}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>2. Build & Environment Information</h3>
                <ul class="report-list">
                    <li><strong>Measured:</strong> Build tool: ${escapeHtml(dependency.build_tool || 'N/A')}</li>
                    <li><strong>Measured:</strong> Total files discovered: ${totalFiles}</li>
                    <li><strong>Measured:</strong> Files parsed successfully: ${parsedFiles}</li>
                    <li><strong>Measured:</strong> Files failed to parse: ${failedFiles}</li>
                    <li><strong>Measured:</strong> Detected frameworks: ${frameworks.length ? frameworks.map(f => escapeHtml(f)).join(', ') : 'No major framework list available.'}</li>
                </ul>
            </section>

            <section class="report-section">
                <h3>3. Codebase Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Total Files</span><strong>${totalFiles}</strong></div>
                    <div class="report-card"><span>Parsed Files</span><strong>${parsedFiles}</strong></div>
                    <div class="report-card"><span>Failed Files</span><strong>${failedFiles}</strong></div>
                    <div class="report-card"><span>Classes</span><strong>${totalClasses}</strong></div>
                    <div class="report-card"><span>Interfaces</span><strong>${totalInterfaces}</strong></div>
                    <div class="report-card"><span>Methods</span><strong>${totalMethods}</strong></div>
                    <div class="report-card"><span>Variables</span><strong>${totalFields}</strong></div>
                    <div class="report-card"><span>Dependency Links</span><strong>${dependencyEdges}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>5A. Statistical Analysis</h3>
                <table class="report-table">
                    <thead><tr><th>Statistic</th><th>Value</th><th>Type</th></tr></thead>
                    <tbody>
                        <tr><td>Total Files</td><td>${totalFiles}</td><td>Measured</td></tr>
                        <tr><td>Parsed Files</td><td>${parsedFiles}</td><td>Measured</td></tr>
                        <tr><td>Failed Files</td><td>${failedFiles}</td><td>Measured</td></tr>
                        <tr><td>Classes</td><td>${totalClasses}</td><td>Measured</td></tr>
                        <tr><td>Interfaces</td><td>${totalInterfaces}</td><td>Measured</td></tr>
                        <tr><td>Methods</td><td>${totalMethods}</td><td>Measured</td></tr>
                        <tr><td>Variables</td><td>${totalFields}</td><td>Measured</td></tr>
                        <tr><td>Dependencies</td><td>${totalDependencies}</td><td>Measured</td></tr>
                        <tr><td>Technical Debt Issues</td><td>${totalIssues}</td><td>Measured</td></tr>
                        <tr><td>Security Issues</td><td>${outdatedDeps.length}</td><td>Measured</td></tr>
                        <tr><td>Circular Dependencies</td><td>${circularDependencies}</td><td>Measured</td></tr>
                        <tr><td>Parse Success Rate</td><td>${formatPercent(parseSuccessRate)}</td><td>Calculated</td></tr>
                        <tr><td>Issue Density</td><td>${formatMetric(issueDensity)}</td><td>Calculated</td></tr>
                        <tr><td>Files per Second</td><td>${formatMetric(filesPerSecond)}</td><td>Calculated</td></tr>
                    </tbody>
                </table>
            </section>

            <section class="report-section">
                <h3>File Parsing Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Parse Success Rate</span><strong>${formatPercent(parseSuccessRate)}</strong></div>
                    <div class="report-card"><span>Parse Failure Rate</span><strong>${formatPercent(parseFailureRate)}</strong></div>
                    <div class="report-card"><span>Files / Second</span><strong>${formatMetric(filesPerSecond)}</strong></div>
                    <div class="report-card"><span>Avg Parse Time / File</span><strong>${formatMetric(avgParseTimePerFile)}s</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Codebase Distribution</h3>
                <div class="distribution-list">
                    <div class="distribution-row"><span>Classes</span><div class="distribution-bar"><i style="width:${totalClasses ? (totalClasses / Math.max(totalClasses + totalInterfaces + totalMethods + totalFields, 1)) * 100 : 0}%"></i></div><strong>${totalClasses}</strong></div>
                    <div class="distribution-row"><span>Interfaces</span><div class="distribution-bar"><i style="width:${totalInterfaces ? (totalInterfaces / Math.max(totalClasses + totalInterfaces + totalMethods + totalFields, 1)) * 100 : 0}%"></i></div><strong>${totalInterfaces}</strong></div>
                    <div class="distribution-row"><span>Methods</span><div class="distribution-bar"><i style="width:${totalMethods ? (totalMethods / Math.max(totalClasses + totalInterfaces + totalMethods + totalFields, 1)) * 100 : 0}%"></i></div><strong>${totalMethods}</strong></div>
                    <div class="distribution-row"><span>Variables</span><div class="distribution-bar"><i style="width:${totalFields ? (totalFields / Math.max(totalClasses + totalInterfaces + totalMethods + totalFields, 1)) * 100 : 0}%"></i></div><strong>${totalFields}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Technical Debt Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Total Issues</span><strong>${totalIssues}</strong></div>
                    <div class="report-card"><span>Issues / File</span><strong>${formatMetric(issueDensity)}</strong></div>
                    <div class="report-card"><span>Issues / Class</span><strong>${formatMetric(issuesPerClass)}</strong></div>
                    <div class="report-card"><span>Issues / Method</span><strong>${formatMetric(issuesPerMethod)}</strong></div>
                    <div class="report-card"><span>Critical Issues</span><strong>${severityMap.critical}</strong></div>
                    <div class="report-card"><span>High Issues</span><strong>${severityMap.high}</strong></div>
                    <div class="report-card"><span>Medium Issues</span><strong>${severityMap.medium}</strong></div>
                    <div class="report-card"><span>Low Issues</span><strong>${severityMap.low}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Technical Debt Distribution</h3>
                <table class="report-table">
                    <thead><tr><th>Severity</th><th>Count</th><th>Percentage</th></tr></thead>
                    <tbody>
                        ${severityRows.map(([label, count, pct]) => `<tr><td>${label}</td><td>${count}</td><td>${formatPercent(pct)}</td></tr>`).join('')}
                    </tbody>
                </table>
            </section>

            <section class="report-section">
                <h3>Technical Debt by Category</h3>
                <table class="report-table">
                    <thead><tr><th>Category</th><th>Issues</th><th>% of Total</th></tr></thead>
                    <tbody>
                        ${categoryStats.length ? categoryStats.map(item => `<tr><td>${escapeHtml(item.category)}</td><td>${item.value}</td><td>${formatPercent(item.percent)}</td></tr>`).join('') : '<tr><td colspan="3">No category data available.</td></tr>'}
                    </tbody>
                </table>
            </section>

            <section class="report-section">
                <h3>Rule Frequency Analysis</h3>
                <table class="report-table">
                    <thead><tr><th>Rule</th><th>Occurrences</th><th>Percentage</th></tr></thead>
                    <tbody>
                        ${ruleTableRows}
                    </tbody>
                </table>
            </section>

            <section class="report-section">
                <h3>Complexity Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Total Analyzed Methods</span><strong>${totalMethods}</strong></div>
                    <div class="report-card"><span>Average Complexity</span><strong>N/A</strong></div>
                    <div class="report-card"><span>High Complexity Methods</span><strong>${issues.filter(issue => String(issue.rule).toLowerCase().includes('cyclomatic') || String(issue.rule).toLowerCase().includes('complexity')).length}</strong></div>
                    <div class="report-card"><span>Threshold Status</span><strong>System threshold used by backend</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Coupling Analysis Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Classes Analyzed</span><strong>${totalClasses}</strong></div>
                    <div class="report-card"><span>Average Coupling</span><strong>N/A</strong></div>
                    <div class="report-card"><span>Max Coupling</span><strong>N/A</strong></div>
                    <div class="report-card"><span>Dependency Links</span><strong>${dependencyEdges}</strong></div>
                    <div class="report-card"><span>Circular Dependency Chains</span><strong>${circularDependencies}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Dependency Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Total Dependencies</span><strong>${totalDependencies}</strong></div>
                    <div class="report-card"><span>External Dependencies</span><strong>${frameworks.length}</strong></div>
                    <div class="report-card"><span>Outdated Dependencies</span><strong>${outdatedDeps.length}</strong></div>
                    <div class="report-card"><span>Vulnerable Dependencies</span><strong>${outdatedDeps.length}</strong></div>
                    <div class="report-card"><span>Vulnerability Rate</span><strong>${formatPercent(dependencyVulnerabilityRate)}</strong></div>
                    <div class="report-card"><span>Outdated Rate</span><strong>${formatPercent(dependencyVulnerabilityRate)}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Security Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Total Dependency Vulnerabilities</span><strong>${outdatedDeps.length}</strong></div>
                    <div class="report-card"><span>Critical</span><strong>${outdatedDeps.filter(d => String(d.severity || '').toLowerCase() === 'critical').length}</strong></div>
                    <div class="report-card"><span>High</span><strong>${outdatedDeps.filter(d => String(d.severity || '').toLowerCase() === 'high').length}</strong></div>
                    <div class="report-card"><span>Medium</span><strong>${outdatedDeps.filter(d => String(d.severity || '').toLowerCase() === 'medium').length}</strong></div>
                    <div class="report-card"><span>Low</span><strong>${outdatedDeps.filter(d => String(d.severity || '').toLowerCase() === 'low').length}</strong></div>
                    <div class="report-card"><span>Dependencies Affected</span><strong>${outdatedDeps.length}</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Code Duplication Statistics</h3>
                <div class="report-grid">
                    <div class="report-card"><span>Duplicated Blocks</span><strong>${issues.filter(issue => String(issue.rule).toLowerCase().includes('duplicate')).length}</strong></div>
                    <div class="report-card"><span>Duplicated Lines</span><strong>N/A</strong></div>
                    <div class="report-card"><span>Affected Files</span><strong>N/A</strong></div>
                    <div class="report-card"><span>Duplication %</span><strong>N/A</strong></div>
                </div>
            </section>

            <section class="report-section">
                <h3>Analysis Efficiency</h3>
                <table class="report-table">
                    <thead><tr><th>Analysis Stage</th><th>Time</th></tr></thead>
                    <tbody>
                        <tr><td>Project Discovery</td><td>N/A</td></tr>
                        <tr><td>Source Parsing</td><td>${formatMetric(scanDuration)}s</td></tr>
                        <tr><td>Dependency Analysis</td><td>N/A</td></tr>
                        <tr><td>Debt Detection</td><td>N/A</td></tr>
                        <tr><td>Graph Construction</td><td>N/A</td></tr>
                        <tr><td>Report Generation</td><td>N/A</td></tr>
                        <tr><td>Total Scan</td><td>${formatMetric(scanDuration)}s</td></tr>
                    </tbody>
                </table>
                <p class="report-note">Stage-level timing is not currently instrumented; only total scan duration is directly available from the backend.</p>
            </section>

            <section class="report-section">
                <h3>Detection Accuracy & Reliability</h3>
                <table class="report-table">
                    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                    <tbody>
                        <tr><td>True Positives</td><td>N/A</td></tr>
                        <tr><td>False Positives</td><td>N/A</td></tr>
                        <tr><td>False Negatives</td><td>N/A</td></tr>
                        <tr><td>Precision</td><td>N/A – Ground truth unavailable</td></tr>
                        <tr><td>Recall</td><td>N/A – Ground truth unavailable</td></tr>
                        <tr><td>F1 Score</td><td>N/A – Ground truth unavailable</td></tr>
                    </tbody>
                </table>
                <p class="report-note">${escapeHtml(validationStatus)}</p>
            </section>

            <section class="report-section">
                <h3>Statistical Interpretation</h3>
                <p class="report-list">${escapeHtml(interpretationText)}</p>
            </section>

            <section class="report-section">
                <h3>Why Automated Analysis Improves Analysis Efficiency</h3>
                <ul class="report-list">
                    <li>Automated static analysis applies the same formal rules consistently across the analyzed project.</li>
                    <li>It reduces repetitive manual inspection and allows large sets of source files to be reviewed systematically.</li>
                    <li>It can automatically construct dependency relationships and highlight repeated patterns across classes.</li>
                    <li>It creates machine-readable output that can be stored, compared, and exported for review.</li>
                </ul>
            </section>

            <section class="report-section">
                <h3>How Detection Reliability Can Be Improved</h3>
                <ul class="report-list">
                    <li>Improve parsing quality and project coverage.</li>
                    <li>Calibrate rule thresholds against real-world codebases.</li>
                    <li>Validate findings using a ground-truth dataset.</li>
                    <li>Track false positives and false negatives during rule refinement.</li>
                    <li>Use historical comparison and regression testing to improve consistency.</li>
                </ul>
            </section>

            <section class="report-section">
                <h3>Final Summary</h3>
                <p class="report-list">This project shows measurable technical debt, dependency risk, and maintainability pressure. The measured indicators confirm a significant number of issue clusters, especially in ${escapeHtml(highestRule)}, while the current scan also demonstrates that the platform can quantify the analysis with parse-rate, issue-density, and throughput statistics. Accuracy claims remain explicitly marked as unavailable until a validated ground-truth dataset is provided.</p>
            </section>

            <section class="report-section">
                <h3>Detailed Appendix</h3>
                <ul class="report-list">
                    ${issues.slice(0, 10).map(issue => `<li>${escapeHtml(issue.rule || 'Issue')} — ${escapeHtml(issue.message || 'Detected finding')} (${escapeHtml(issue.class_name || 'Unknown class')})</li>`).join('') || '<li>No issue appendix entries available.</li>'}
                </ul>
            </section>
        </div>
    `;
}

function formatDelta(value) {
    if (value === null) return 'Baseline';
    if (value > 0) return `<span class="delta-positive">-${value}</span>`;
    if (value < 0) return `<span class="delta-negative">+${Math.abs(value)}</span>`;
    return 'No change';
}

function renderHistoryTab(data) {
    const container = document.getElementById('tab-history-content');
    if (!data.scans.length) {
        container.innerHTML = '<p class="empty-state">No saved scans yet.</p>';
        return;
    }
    container.innerHTML = data.scans.map(scan => `
        <article class="history-tab-item">
            <div><strong>${escapeHtml(scan.project_name || 'Unnamed project')}</strong><span>${formatDate(scan.created_at)}</span></div>
            <div class="history-tab-stats"><span>Score: ${scan.debt_score}</span><span>Issues: ${scan.issue_count}</span><span>Suggestions: ${scan.suggestions.length}</span></div>
        </article>`).join('');
}

function showNodeDetails(fqn, metric) {
    if (!metric) return;
    
    document.getElementById('no-node-selected-msg').classList.add('hidden');
    document.getElementById('node-metrics-info').classList.remove('hidden');

    document.getElementById('selected-class-name').textContent = fqn;
    
    const parts = fqn.split('.');
    parts.pop();
    const pkg = parts.join('.');
    document.getElementById('selected-class-pkg').textContent = pkg || '(default)';

    document.getElementById('selected-class-ca').textContent = metric.afferent_coupling;
    document.getElementById('selected-class-ce').textContent = metric.efferent_coupling;
    
    const instability = metric.instability;
    document.getElementById('selected-class-instability').textContent = instability.toFixed(2);
    
    // Instability fill
    const fill = document.getElementById('instability-fill');
    fill.style.width = `${instability * 100}%`;

    // Instability explanation
    const desc = document.getElementById('instability-desc');
    if (instability === 0 && metric.afferent_coupling > 0) {
        desc.textContent = "This class is fully STABLE (I = 0). Many classes depend on it, but it depends on nothing. Changing this class requires care because of ripple effects.";
    } else if (instability === 1 && metric.efferent_coupling > 0) {
        desc.textContent = "This class is fully UNSTABLE (I = 1). It depends on other classes but has no dependants. It is very easy to modify without impacting other files.";
    } else if (metric.afferent_coupling === 0 && metric.efferent_coupling === 0) {
        desc.textContent = "This class is isolated. It has no afferent or efferent dependencies.";
    } else {
        desc.textContent = `This class has moderate instability (I = ${instability.toFixed(2)}). It is partially stable: it calls other modules and is also called by other modules.`;
    }
}

// Helper: map instability (0-1) to cyan/purple/pink gradient
function getInstabilityColor(instability) {
    // 0 = stable (pure cyan #06b6d4)
    // 1 = unstable (rose #f43f5e)
    // Interpolate RGB:
    // Cyan: rgb(6, 182, 212)
    // Rose: rgb(244, 63, 94)
    const r = Math.round(6 + (244 - 6) * instability);
    const g = Math.round(182 + (63 - 182) * instability);
    const b = Math.round(212 + (94 - 212) * instability);
    return `rgb(${r}, ${g}, ${b})`;
}

// --- Utilities ---
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
