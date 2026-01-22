// chat.js

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
    if (modal) modal.classList.remove('hidden');
    // Scroll to bottom
    scrollToBottom();
    // Mark as read
    markOrgMessagesRead();
}

function closeChatModal() {
    const modal = document.getElementById('chat-modal');
    if (modal) modal.classList.add('hidden');
}

function startOrgPolling() {
    // Only call if we have the Org chat button (means we are Org/Doctor)
    const isOrg = document.getElementById('org-chat-btn');
    if (isOrg) {
        loadMessages(); // Initial load
        chatPollingInterval = setInterval(loadMessages, 5000); // Poll every 5s
    }
}

async function loadMessages(userId = null) {
    try {
        const url = userId ? `/api/chat/messages/history?user_id=${userId}` : '/api/chat/messages/history';
        const response = await fetch(url);
        if (!response.ok) {
            console.error("Chat Server Error:", response.status);
            return;
        }
        const messages = await response.json();

        // Determine mode based on whether userId was passed
        const roleMode = userId ? 'support' : 'org';

        // Notification logic for Org:
        if (roleMode === 'org') {
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
        }

        renderMessages(messages, roleMode);
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
            // Reload immediately using unified function
            loadMessages(currentChatUserId);

            // If Support dashboard, reload thread list too
            const threadContainer = document.getElementById('chat-threads');
            if (threadContainer && typeof loadThreads === 'function') {
                loadThreads();
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
    const isAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 100;

    container.innerHTML = '';

    messages.forEach(msg => {
        const div = document.createElement('div');
        div.setAttribute('data-msg-id', msg.id);
        div.className = 'chat-message-bubble';
        div.style.maxWidth = '80%';
        div.style.minWidth = '80px';
        div.style.padding = '8px 12px';
        div.style.borderRadius = '8px';
        div.style.marginBottom = '8px';
        div.style.position = 'relative';
        div.style.fontSize = '14px';
        div.style.boxShadow = '0 1px 2px rgba(0,0,0,0.1)';
        div.style.display = 'flex';
        div.style.flexDirection = 'column';

        let isMe = false;
        if (role === 'org') {
            isMe = (msg.recipient_id === null);
        } else {
            isMe = (msg.recipient_id !== null);
        }

        if (isMe) {
            div.style.alignSelf = 'flex-end';
            div.style.backgroundColor = '#dcf8c6';
            div.style.marginLeft = 'auto';
        } else {
            div.style.alignSelf = 'flex-start';
            div.style.backgroundColor = '#ffffff';
            div.style.marginRight = 'auto';
        }

        let statusHtml = '';
        if (isMe) {
            const checkColor = msg.is_read ? '#9333ea' : '#9ca3af';
            statusHtml = `
                    <span style="display: inline-flex; margin-left: 4px; vertical-align: middle;" title="${msg.is_read ? 'Прочитано' : 'Доставлено'}">
                        <svg width="16" height="11" viewBox="0 0 16 11" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M1 6L4.5 9.5L11 3" stroke="${checkColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M5 6L8.5 9.5L15 3" stroke="${checkColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </span>
                `;
        }

        // Reactions display
        let reactionsHtml = '';
        if (msg.reactions && Object.keys(msg.reactions).length > 0) {
            reactionsHtml = '<div style="display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap;">';
            for (const [emoji, count] of Object.entries(msg.reactions)) {
                reactionsHtml += `
                    <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '${emoji}')" 
                            style="background: rgba(0,0,0,0.08); border: 1px solid rgba(0,0,0,0.12); 
                                   border-radius: 12px; padding: 3px 7px; font-size: 13px; 
                                   cursor: pointer; display: inline-flex; align-items: center; gap: 3px;
                                   transition: all 0.15s ease;">
                        <span style="line-height: 1;">${emoji}</span>
                        <span style="color: #666; font-size: 11px; font-weight: 500;">${count}</span>
                    </button>
                `;
            }
            reactionsHtml += '</div>';
        }

        const pickerAlign = isMe ? 'right: 0;' : 'left: 0;';
        const reactionPicker = `
            <div class="reaction-picker" data-msg-id="${msg.id}" style="display: none; position: absolute; top: 100%; ${pickerAlign}
                 background: white; border-radius: 20px; padding: 6px 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); 
                 margin-top: 4px; z-index: 100; gap: 4px;">
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '👍')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px;">👍</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '❤️')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px;">❤️</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '😂')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px;">😂</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '😮')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px;">😮</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '🔥')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px;">🔥</button>
            </div>
        `;

        div.innerHTML = `
            <div>${msg.body}</div>
            <div style="font-size: 10px; color: #999; text-align: right; margin-top: 4px; display: flex; align-items: center; justify-content: flex-end; gap: 4px;">
                ${new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                ${statusHtml}
            </div>
            ${reactionsHtml}
            ${reactionPicker}
        `;

        let hideTimeout;
        const showPicker = () => {
            clearTimeout(hideTimeout);
            document.querySelectorAll('.reaction-picker').forEach(p => {
                if (p !== div.querySelector('.reaction-picker')) p.style.display = 'none';
            });
            const picker = div.querySelector('.reaction-picker');
            if (picker) picker.style.display = 'flex';
        };

        const hidePicker = () => {
            hideTimeout = setTimeout(() => {
                const picker = div.querySelector('.reaction-picker');
                if (picker) picker.style.display = 'none';
            }, 100);
        };

        div.addEventListener('mouseenter', showPicker);
        div.addEventListener('mouseleave', hidePicker);

        container.appendChild(div);
    });

    if (isAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
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

window.addEventListener('focus', () => blinkTitle(false));
document.addEventListener('click', () => blinkTitle(false));

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
            if (badge) badge.innerText = unread;
            if (notif) {
                notif.style.display = 'inline-flex';
                notif.classList.add('blink-animation');
            }
            if (badge) badge.style.display = 'block';
            blinkTitle(true);
        } else {
            if (notif) {
                notif.style.display = 'inline-flex';
                notif.classList.remove('blink-animation');
            }
            if (badge) badge.style.display = 'none';
            blinkTitle(false);
        }
    } catch (e) {
        console.error("Notif Error", e);
    }
}

// --- Reaction Functions ---
async function toggleReaction(messageId, emoji) {
    try {
        const response = await fetch(`/api/chat/messages/${messageId}/react`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ emoji: emoji })
        });

        if (response.ok) {
            // Reload context-aware
            loadMessages(currentChatUserId);
        }
    } catch (e) {
        console.error("Reaction Error:", e);
    }
}
