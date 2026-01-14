// chat.js

// Utility function to convert UTC timestamp to Moscow time (UTC+3)
function toMoscowTime(utcTimestamp) {
    const date = new Date(utcTimestamp);
    // Add 3 hours for Moscow timezone
    date.setHours(date.getHours() + 3);
    return date;
}

// Global State
let chatPollingInterval = null;
let currentChatUserId = null; // For Support Dashboard

document.addEventListener('DOMContentLoaded', function () {
    // Determine Role based on elements present
    const isOrg = document.getElementById('org-chat-btn');
    const isSupport = document.getElementById('chat-notification');

    if (isOrg) {
        startOrgPolling();
    }

    if (isSupport) {
        startSupportNotificationPolling();
    }

    // Send on Enter
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') sendMessage();
        });
    }
});

// --- Organization Functions ---

function openChatModal() {
    const modal = document.getElementById('chat-modal');
    modal.classList.remove('hidden');
    // Scroll to bottom
    scrollToBottom();
    // Mark as read
    markOrgMessagesRead();
}

function closeChatModal() {
    const modal = document.getElementById('chat-modal');
    modal.classList.add('hidden');
}

function startOrgPolling() {
    loadMessages(); // Initial load
    chatPollingInterval = setInterval(loadMessages, 5000); // Poll every 5s
}

async function loadMessages() {
    try {
        const response = await fetch('/api/chat/messages/history');
        if (!response.ok) return;
        const messages = await response.json();

        // Blink check for Org:
        // If any message is Unread AND sent to me (recipient_id != null)
        const hasUnread = messages.some(m => m.recipient_id !== null && m.is_read === false);

        // Blink if unread and (hidden tab OR chat modal closed)
        const modal = document.getElementById('chat-modal');
        const isClosed = modal && modal.classList.contains('hidden');

        if (hasUnread && (document.hidden || isClosed)) {
            blinkTitle(true);
            const btn = document.getElementById('org-chat-btn');
            if (btn) btn.classList.add('blink-animation');
            const circle = document.getElementById('chat-btn-circle');
            if (circle) circle.classList.add('chat-btn-pulse');
        } else {
            const btn = document.getElementById('org-chat-btn');
            if (btn) btn.classList.remove('blink-animation');
            const circle = document.getElementById('chat-btn-circle');
            if (circle) circle.classList.remove('chat-btn-pulse');
        }

        renderMessages(messages, 'org');
    } catch (e) {
        console.error("Chat Error:", e);
    }
}

async function markOrgMessagesRead() {
    try {
        await fetch('/api/chat/messages/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({}) // Org reads his own messages
        });
        // Stop blinking immediately
        blinkTitle(false);
        const btn = document.getElementById('org-chat-btn');
        if (btn) btn.classList.remove('pulse-animation');
    } catch (e) {
        console.error("Mark Read Error:", e);
    }
}


async function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    try {
        const response = await fetch('/api/chat/messages/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ body: text, recipient_id: currentChatUserId }) // recipient_id is null for Org->Support
        });

        if (response.ok) {
            input.value = '';
            loadMessages(); // Reload immediately
            // If Support dashboard, reload thread too
            if (document.getElementById('chat-threads')) {
                loadThreads();
                loadThreadMessages(currentChatUserId);
            }
        }
    } catch (e) {
        console.error("Send Error:", e);
    }
}

function renderMessages(messages, role) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    // Store current scroll position to check if we are at bottom
    const isAtBottom = container.scrollHeight - container.scrollTop === container.clientHeight;

    container.innerHTML = '';

    messages.forEach(msg => {
        const div = document.createElement('div');
        div.style.maxWidth = '80%';
        div.style.minWidth = '80px';
        div.style.padding = '8px 12px';
        div.style.borderRadius = '8px';
        div.style.marginBottom = '8px';
        div.style.position = 'relative';
        div.style.fontSize = '14px';
        div.style.boxShadow = '0 1px 2px rgba(0,0,0,0.1)';

        // Logic depends on viewer role
        // For Org: My messages (sender_id = my_id) are Right/Green. Support messages are Left/White.
        // Identify "My" messages by sender_name? Or API should return 'is_me'?
        // Currently API just returns objects.
        // We can check if `msg.sender_id` == `data-user-id` (if we injected it).
        // OR: simpler heuristc: 
        // If Org View: sender_id matches current_user (we need to know current user id).
        // Let's rely on class injection or assume simpler:

        // Actually, easier to inject "is_me" from backend or check logic.
        // Let's assume standard bubble styles:
        // Left: White (Support/Other)
        // Right: Light Green (Me)

        // Backend `to_dict` has `sender_id`. We need `current_user.id` in JS.
        // Assuming `currentUserId` is injected in app_base.html globally.

        // Update: `current_user.id` is not currently in global JS.
        // But we can check `sender_name`.

        // Hack: If I am Org, and msg.recipient_id is NOT null (so it was sent TO me) -> Left.
        // If msg.recipient_id IS null (sent TO support) -> Right.

        let isMe = false;

        if (role === 'org') {
            // Org View:
            // Sent to Support (recipient_id is null) -> IT IS ME.
            isMe = (msg.recipient_id === null);
        } else {
            // Support View:
            // Sent by Support (recipient_id is NOT null, i.e. sent to Org) -> IT IS ME.
            isMe = (msg.recipient_id !== null);
        }

        if (isMe) {
            div.style.alignSelf = 'flex-end';
            div.style.backgroundColor = '#dcf8c6'; // Whatsapp Green
            div.style.marginLeft = 'auto'; // Float right
        } else {
            div.style.alignSelf = 'flex-start';
            div.style.backgroundColor = '#ffffff';
            div.style.marginRight = 'auto'; // Float left
        }

        div.innerHTML = `
            <div>${msg.body}</div>
            <div style="font-size: 10px; color: #999; text-align: right; margin-top: 4px;">
                ${toMoscowTime(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
        `;

        container.appendChild(div);
    });

    // Auto scroll if was at bottom or first load
    // Simple: always scroll to bottom for now
    container.scrollTop = container.scrollHeight;
}


function scrollToBottom() {
    const container = document.getElementById('chat-messages');
    if (container) container.scrollTop = container.scrollHeight;
}


// --- Support Functions ---

function startSupportNotificationPolling() {
    checkSupportNotifications();
    setInterval(checkSupportNotifications, 10000);
}

// --- Title Blinking Support ---
let originalTitle = document.title;
let blinkInterval = null;
let isBlinking = false;

function blinkTitle(shouldBlink) {
    if (shouldBlink) {
        if (isBlinking) return;
        isBlinking = true;
        let isOriginal = true;
        blinkInterval = setInterval(() => {
            document.title = isOriginal ? "🔔 Новое сообщение!" : originalTitle;
            isOriginal = !isOriginal;
        }, 1000);
    } else {
        if (!isBlinking) return;
        isBlinking = false;
        clearInterval(blinkInterval);
        document.title = originalTitle;
    }
}

// Stop blinking on focus or click
window.addEventListener('focus', () => blinkTitle(false));
document.addEventListener('click', () => blinkTitle(false));

// --- Org Polling Update ---
async function loadMessages() {
    try {
        const response = await fetch('/api/chat/messages/history');
        if (!response.ok) return;
        const messages = await response.json();

        // Blink check for Org:
        // If there is any unread message from Support (recipient_id is current_user.id or just NOT null logic from before)
        // Wait, 'is_read' field exists.
        // If Org receives message (recipient=me) and is_read=False -> Blink.
        // We need to know 'me'.
        // Simplified Logic: If last message is NOT me (from Support) and we are not focused/modal closed?
        // Actually, API returns `is_read`.
        // If any message in list has `recipient_id != null` (sent to me) AND `is_read == false` -> Blink.

        const hasUnread = messages.some(m => m.recipient_id !== null && m.is_read === false);
        if (hasUnread && document.hidden) {
            blinkTitle(true);
        } else if (hasUnread && document.getElementById('chat-modal').classList.contains('hidden')) {
            blinkTitle(true);
        }

        renderMessages(messages, 'org');
    } catch (e) {
        console.error("Chat Error:", e);
    }
}

// --- Support Polling Update ---
async function checkSupportNotifications() {
    try {
        const response = await fetch('/api/chat/threads');
        if (!response.ok) return;

        const threads = await response.json();
        let unread = 0;
        threads.forEach(t => unread += t.unread_count);

        const badge = document.getElementById('unread-badge');
        const notif = document.getElementById('chat-notification');

        if (unread > 0) {
            badge.innerText = unread;
            notif.style.display = 'inline-flex';
            badge.style.display = 'block';
            notif.classList.add('blink-animation');

            // Trigger Title Blink
            blinkTitle(true);

        } else {
            notif.style.display = 'inline-flex';
            badge.style.display = 'none';
            notif.classList.remove('blink-animation');
            blinkTitle(false);
        }
    } catch (e) {
        console.error("Notif Error", e);
    }
}
