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
        div.setAttribute('data-msg-id', msg.id);
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

        let statusHtml = '';
        if (isMe) {
            // Determine check color: purple #9333ea if read, gray if not
            const checkColor = msg.is_read ? '#9333ea' : '#9ca3af';

            // Double check SVG
            statusHtml = `
                    <span style="display: inline-flex; margin-left: 4px; vertical-align: middle;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M4 12.6111L8.92308 17.5L20 6.5" stroke="${checkColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M4 12.6111L8.92308 17.5L20 6.5" stroke="${checkColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" transform="translate(-5, 0)" opacity="${msg.is_read ? '1' : '0'}" /> 
                        </svg>
                    </span>
                `;

            // Better SVG for double check logic
            statusHtml = `
                    <span style="display: inline-flex; margin-left: 4px; vertical-align: middle;" title="${msg.is_read ? 'Прочитано' : 'Доставлено'}">
                        <svg width="16" height="11" viewBox="0 0 16 11" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <!-- First check -->
                            <path d="M1 6L4.5 9.5L11 3" stroke="${checkColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                            <!-- Second check (visible overlapping) -->
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

        // Reaction picker - позиция зависит от того, чье сообщение
        const pickerAlign = isMe ? 'right: 0;' : 'left: 0;';
        const reactionPicker = `
            <div class="reaction-picker" data-msg-id="${msg.id}" style="display: none; position: absolute; top: 100%; ${pickerAlign}
                 background: white; border-radius: 20px; padding: 6px 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); 
                 margin-top: 4px; z-index: 100; gap: 4px;">
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '👍')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px; transition: transform 0.1s;" onmouseenter="this.style.transform='scale(1.3)'" onmouseleave="this.style.transform='scale(1)'">👍</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '❤️')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px; transition: transform 0.1s;" onmouseenter="this.style.transform='scale(1.3)'" onmouseleave="this.style.transform='scale(1)'">❤️</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '😂')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px; transition: transform 0.1s;" onmouseenter="this.style.transform='scale(1.3)'" onmouseleave="this.style.transform='scale(1)'">😂</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '😮')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px; transition: transform 0.1s;" onmouseenter="this.style.transform='scale(1.3)'" onmouseleave="this.style.transform='scale(1)'">😮</button>
                <button onclick="event.stopPropagation(); toggleReaction(${msg.id}, '🔥')" style="background: none; border: none; font-size: 20px; cursor: pointer; padding: 4px 6px; transition: transform 0.1s;" onmouseenter="this.style.transform='scale(1.3)'" onmouseleave="this.style.transform='scale(1)'">🔥</button>
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

        // Improved hover handling with timeout to prevent flickering
        let hideTimeout;

        const showPicker = () => {
            clearTimeout(hideTimeout);

            // Hide all other pickers first
            document.querySelectorAll('.reaction-picker').forEach(p => {
                if (p !== div.querySelector('.reaction-picker')) {
                    p.style.display = 'none';
                }
            });

            const picker = div.querySelector('.reaction-picker');
            if (picker) {
                picker.style.display = 'flex';
            }
        };

        const hidePicker = () => {
            hideTimeout = setTimeout(() => {
                const picker = div.querySelector('.reaction-picker');
                if (picker) {
                    picker.style.display = 'none';
                }
            }, 50); // Reduced to 50ms for faster hiding
        };

        div.addEventListener('mouseenter', showPicker);
        div.addEventListener('mouseleave', hidePicker);

        // Keep picker visible when hovering over it
        const picker = div.querySelector('.reaction-picker');
        if (picker) {
            picker.addEventListener('mouseenter', showPicker);
            picker.addEventListener('mouseleave', hidePicker);
        }


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
            const result = await response.json();

            // Immediate visual feedback - update just this message's reactions
            const container = document.getElementById('chat-messages');
            if (container) {
                // Find the message bubble that contains this message ID
                const allMessages = container.querySelectorAll('[data-msg-id]');
                allMessages.forEach(msgDiv => {
                    const picker = msgDiv.querySelector(`.reaction-picker[data-msg-id="${messageId}"]`);
                    if (picker) {
                        // This is our message, update its reactions
                        // For now, just reload all messages
                        // In future, could update inline for smoother UX
                    }
                });
            }

            // Reload messages to show updated reactions
            setTimeout(() => {
                if (currentChatUserId) {
                    loadMessagesForSupport();
                } else {
                    loadMessages();
                }
            }, 100); // Small delay for smooth transition
        }
    } catch (e) {
        console.error("Reaction Error:", e);
    }
}
