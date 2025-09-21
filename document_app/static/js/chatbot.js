document.addEventListener('DOMContentLoaded', function() {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    function sendMessage() {
        const message = userInput.value.trim();
        if (message) {
            appendMessage(message, 'user');
            userInput.value = '';
            // Simulate bot response
            setTimeout(() => {
                appendMessage('This is a simulated response.', 'bot');
            }, 1000);
        }
    }

    function appendMessage(message, sender) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message', sender);

        const icon = document.createElement('div');
        icon.classList.add('message-icon');
        icon.innerHTML = `<i class="fas fa-${sender === 'bot' ? 'robot' : 'user'}"></i>`;

        const content = document.createElement('div');
        content.classList.add('message-content');
        content.innerHTML = `<p>${message}</p>`;

        if (sender === 'user') {
            messageElement.appendChild(content);
            messageElement.appendChild(icon);
        } else {
            messageElement.appendChild(icon);
            messageElement.appendChild(content);
        }

        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});