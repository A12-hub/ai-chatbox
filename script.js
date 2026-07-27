const API_BASE_URL = "http://127.0.0.1:8000";
const STREAM_API_URL = `${API_BASE_URL}/chat/stream`;
const DEFAULT_LOGO_URL = "assets/unimak-logo.jfif";

const STORAGE_KEYS = {
    history: "computerScienceChatHistory",
    theme: "computerScienceChatTheme",
    autoSpeak: "computerScienceAutoSpeak",
    settings: "computerScienceChatSettings"
};

const DEFAULT_SETTINGS = {
    model: "llama3.2:1b",
    temperature: 0.4,
    responseLength: "medium",
    systemPrompt: "",
    chatSize: "standard"
};

const WELCOME_TEXT =
    "Hello! I am your University of Makeni Computer Science AI Assistant. " +
    "Ask me about programming, web development, artificial intelligence, " +
    "databases, networking or computer troubleshooting.";

const MAXIMUM_CONTEXT_MESSAGES = 12;

const landingPage = document.getElementById("landingPage");
const openChatButton = document.getElementById("openChatButton");
const chatLauncher = document.getElementById("chatLauncher");
const chatWidget = document.getElementById("chatWidget");
const closeChatButton = document.getElementById("closeChatButton");
const themeButton = document.getElementById("themeButton");
const settingsButton = document.getElementById("settingsButton");
const expandButton = document.getElementById("expandButton");
const newChatButton = document.getElementById("newChatButton");

const chatWindow = document.getElementById("chatWindow");
const screenReaderAnnouncements =
    document.getElementById("screenReaderAnnouncements");
const chatForm = document.getElementById("chatForm");
const userInput = document.getElementById("userInput");
const sendButton = document.getElementById("sendButton");
const voiceButton = document.getElementById("voiceButton");
const autoSpeakButton = document.getElementById("autoSpeakButton");
const clearButton = document.getElementById("clearButton");
const characterCounter =
    document.getElementById("characterCounter");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const suggestionButtons =
    document.querySelectorAll(".suggestion-button");

const settingsPanel = document.getElementById("settingsPanel");
const closeSettingsButton =
    document.getElementById("closeSettingsButton");
const modelSelect = document.getElementById("modelSelect");
const responseLengthSelect =
    document.getElementById("responseLengthSelect");
const temperatureInput =
    document.getElementById("temperatureInput");
const temperatureValue =
    document.getElementById("temperatureValue");
const systemPromptInput =
    document.getElementById("systemPromptInput");
const chatSizeSelect =
    document.getElementById("chatSizeSelect");
const saveSettingsButton =
    document.getElementById("saveSettingsButton");
const resetSettingsButton =
    document.getElementById("resetSettingsButton");

let conversationHistory = loadConversationHistory();
let currentSettings = loadSettings();
let isSending = false;
let isListening = false;
let speechRecognition = null;
let autoSpeakEnabled =
    localStorage.getItem(STORAGE_KEYS.autoSpeak) === "true";
let lastFocusedElement = null;
let settingsReturnFocus = null;
let isFullScreen = false;


function safeJsonParse(value, fallback) {
    try {
        return JSON.parse(value);
    } catch {
        return fallback;
    }
}


function loadConversationHistory() {
    const stored = safeJsonParse(
        localStorage.getItem(STORAGE_KEYS.history) || "[]",
        []
    );

    return Array.isArray(stored) ? stored : [];
}


function saveConversationHistory() {
    localStorage.setItem(
        STORAGE_KEYS.history,
        JSON.stringify(conversationHistory.slice(-100))
    );
}


function addHistoryMessage(role, content) {
    conversationHistory.push({
        role,
        content,
        createdAt: new Date().toISOString()
    });

    saveConversationHistory();
}


function loadSettings() {
    const savedSettings = safeJsonParse(
        localStorage.getItem(STORAGE_KEYS.settings) || "{}",
        {}
    );

    return {
        ...DEFAULT_SETTINGS,
        ...savedSettings
    };
}


function saveSettingsToStorage() {
    localStorage.setItem(
        STORAGE_KEYS.settings,
        JSON.stringify(currentSettings)
    );
}


function announce(message) {
    screenReaderAnnouncements.textContent = "";

    window.setTimeout(() => {
        screenReaderAnnouncements.textContent = message;
    }, 30);
}


function getFocusableElements(container) {
    return Array.from(
        container.querySelectorAll(
            [
                "button:not([disabled])",
                "textarea:not([disabled])",
                "select:not([disabled])",
                "input:not([disabled])",
                "[href]",
                "[tabindex]:not([tabindex='-1'])"
            ].join(",")
        )
    ).filter(element => {
        return (
            !element.hidden &&
            element.offsetParent !== null &&
            element.getAttribute("aria-hidden") !== "true"
        );
    });
}


function trapFocus(event) {
    if (
        event.key !== "Tab" ||
        !chatWidget.classList.contains("open")
    ) {
        return;
    }

    const focusableElements =
        getFocusableElements(chatWidget);

    if (focusableElements.length === 0) {
        event.preventDefault();
        chatWidget.focus();
        return;
    }

    const firstElement = focusableElements[0];
    const lastElement =
        focusableElements[focusableElements.length - 1];

    if (
        event.shiftKey &&
        document.activeElement === firstElement
    ) {
        event.preventDefault();
        lastElement.focus();
    } else if (
        !event.shiftKey &&
        document.activeElement === lastElement
    ) {
        event.preventDefault();
        firstElement.focus();
    }
}


function openChat() {
    lastFocusedElement = document.activeElement;

    chatWidget.classList.add("open");
    chatLauncher.classList.add("hidden");

    chatWidget.setAttribute("aria-hidden", "false");
    chatLauncher.setAttribute("aria-expanded", "true");

    if ("inert" in landingPage) {
        landingPage.inert = true;
    }

    window.setTimeout(() => {
        userInput.focus();
        announce("AI chatbot opened.");
    }, 170);
}


function closeChat() {
    closeSettings(false);

    chatWidget.classList.remove("open");
    chatLauncher.classList.remove("hidden");

    chatWidget.setAttribute("aria-hidden", "true");
    chatLauncher.setAttribute("aria-expanded", "false");

    if ("inert" in landingPage) {
        landingPage.inert = false;
    }

    if (lastFocusedElement) {
        lastFocusedElement.focus();
    } else {
        chatLauncher.focus();
    }

    announce("AI chatbot closed.");
}


function openSettings() {
    settingsReturnFocus = document.activeElement;

    settingsPanel.hidden = false;
    settingsPanel.setAttribute("aria-hidden", "false");
    settingsButton.setAttribute("aria-expanded", "true");

    populateSettingsForm();
    loadModels();

    closeSettingsButton.focus();
}


function closeSettings(restoreFocus = true) {
    settingsPanel.hidden = true;
    settingsPanel.setAttribute("aria-hidden", "true");
    settingsButton.setAttribute("aria-expanded", "false");

    if (restoreFocus && settingsReturnFocus) {
        settingsReturnFocus.focus();
    }
}


function applyTheme(themeName) {
    const darkMode = themeName === "dark";

    document.body.classList.toggle(
        "dark-mode",
        darkMode
    );

    themeButton.textContent = darkMode ? "☀️" : "🌙";
    themeButton.title = darkMode
        ? "Switch to light mode"
        : "Switch to dark mode";

    localStorage.setItem(
        STORAGE_KEYS.theme,
        darkMode ? "dark" : "light"
    );
}


function toggleTheme() {
    applyTheme(
        document.body.classList.contains("dark-mode")
            ? "light"
            : "dark"
    );
}


function applyChatSize(size) {
    const allowedSizes = [
        "compact",
        "standard",
        "large"
    ];

    const safeSize = allowedSizes.includes(size)
        ? size
        : "standard";

    chatWidget.classList.remove(
        "size-compact",
        "size-standard",
        "size-large"
    );

    chatWidget.classList.add(`size-${safeSize}`);
}


function toggleFullScreen() {
    isFullScreen = !isFullScreen;

    chatWidget.classList.toggle(
        "full-screen",
        isFullScreen
    );

    expandButton.setAttribute(
        "aria-pressed",
        String(isFullScreen)
    );

    expandButton.textContent = isFullScreen ? "🗗" : "⛶";
    expandButton.title = isFullScreen
        ? "Exit full-screen chatbot"
        : "Open full-screen chatbot";
}


function getCurrentTime(dateValue = null) {
    const date = dateValue
        ? new Date(dateValue)
        : new Date();

    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    });
}


function scrollToBottom() {
    chatWindow.scrollTop = chatWindow.scrollHeight;
}


function resizeTextarea() {
    userInput.style.height = "auto";
    userInput.style.height =
        `${Math.min(userInput.scrollHeight, 145)}px`;
}


function updateCharacterCounter() {
    characterCounter.textContent =
        `${userInput.value.length} / 4000`;
}


function setLoadingState(loading) {
    isSending = loading;

    userInput.disabled = loading;
    sendButton.disabled = loading;
    voiceButton.disabled = loading;

    suggestionButtons.forEach(button => {
        button.disabled = loading;
    });

    chatWindow.setAttribute(
        "aria-busy",
        String(loading)
    );

    sendButton.textContent = loading ? "Working…" : "Send";

    if (!loading) {
        userInput.focus();
    }
}


function displayWelcomeMessage() {
    chatWindow.innerHTML = "";

    const welcomeBox = document.createElement("div");
    welcomeBox.id = "welcomeMessage";
    welcomeBox.className = "welcome-message";

    const logo = document.createElement("img");
    logo.className = "welcome-logo";
    logo.src = DEFAULT_LOGO_URL;
    logo.alt = "University of Makeni logo";

    const heading = document.createElement("h3");
    heading.textContent = "How can I help?";

    const paragraph = document.createElement("p");
    paragraph.textContent = WELCOME_TEXT;

    welcomeBox.appendChild(logo);
    welcomeBox.appendChild(heading);
    welcomeBox.appendChild(paragraph);
    chatWindow.appendChild(welcomeBox);
}


function removeWelcomeMessage() {
    document.getElementById("welcomeMessage")?.remove();
}


function renderAssistantText(container, text) {
    container.innerHTML = "";

    const lines = text.replace(/\r\n/g, "\n").split("\n");
    let list = null;
    let listType = null;
    let codeBlock = null;
    let inCodeBlock = false;

    function closeList() {
        if (list) {
            container.appendChild(list);
            list = null;
            listType = null;
        }
    }

    function closeCodeBlock() {
        if (codeBlock) {
            const pre = document.createElement("pre");
            const code = document.createElement("code");

            code.textContent = codeBlock.join("\n");
            pre.appendChild(code);
            container.appendChild(pre);
            codeBlock = null;
        }
    }

    for (const rawLine of lines) {
        const line = rawLine.trimEnd();

        if (line.trim().startsWith("```")) {
            closeList();

            if (inCodeBlock) {
                closeCodeBlock();
                inCodeBlock = false;
            } else {
                codeBlock = [];
                inCodeBlock = true;
            }

            continue;
        }

        if (inCodeBlock) {
            codeBlock.push(rawLine);
            continue;
        }

        const unorderedMatch =
            line.match(/^\s*[-*]\s+(.+)/);
        const orderedMatch =
            line.match(/^\s*\d+[.)]\s+(.+)/);

        if (unorderedMatch || orderedMatch) {
            const requiredType =
                unorderedMatch ? "ul" : "ol";

            if (!list || listType !== requiredType) {
                closeList();
                list = document.createElement(requiredType);
                listType = requiredType;
            }

            const item = document.createElement("li");
            item.textContent = unorderedMatch
                ? unorderedMatch[1]
                : orderedMatch[1];

            list.appendChild(item);
            continue;
        }

        closeList();

        if (!line.trim()) {
            continue;
        }

        const paragraph = document.createElement("p");
        paragraph.textContent =
            line.replace(/^#{1,6}\s+/, "");
        container.appendChild(paragraph);
    }

    closeList();

    if (inCodeBlock) {
        closeCodeBlock();
    }
}


function createMessage(
    text,
    role,
    dateValue = null,
    isError = false
) {
    const message = document.createElement("article");

    if (isError) {
        message.className = "message error-message";
    } else if (role === "user") {
        message.className = "message user-message";
    } else {
        message.className = "message assistant-message";
    }

    const content = document.createElement("div");
    content.className = "message-content";

    if (role === "assistant" && !isError) {
        renderAssistantText(content, text);
    } else {
        content.textContent = text;
    }

    const information = document.createElement("div");
    information.className = "message-information";

    const label = document.createElement("span");
    label.textContent = isError
        ? `System • ${getCurrentTime(dateValue)}`
        : role === "user"
            ? `You • ${getCurrentTime(dateValue)}`
            : `Assistant • ${getCurrentTime(dateValue)}`;

    information.appendChild(label);
    message.appendChild(content);
    message.appendChild(information);

    return { message, content, information };
}


function addAssistantButtons(information, text) {
    if (information.querySelector(".message-action")) {
        return;
    }

    const speakButton = document.createElement("button");
    speakButton.className = "message-action";
    speakButton.type = "button";
    speakButton.textContent = "🔊";
    speakButton.title = "Read reply aloud";
    speakButton.setAttribute(
        "aria-label",
        "Read this reply aloud"
    );

    speakButton.addEventListener("click", () => {
        speakText(text);
    });

    const copyButton = document.createElement("button");
    copyButton.className = "message-action";
    copyButton.type = "button";
    copyButton.textContent = "Copy";
    copyButton.title = "Copy reply";

    copyButton.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(text);
            copyButton.textContent = "Copied";

            window.setTimeout(() => {
                copyButton.textContent = "Copy";
            }, 1200);
        } catch {
            copyButton.textContent = "Failed";
        }
    });

    information.appendChild(speakButton);
    information.appendChild(copyButton);
}


function addMessage(
    text,
    role,
    save = true,
    dateValue = null,
    isError = false
) {
    removeWelcomeMessage();

    const createdMessage = createMessage(
        text,
        role,
        dateValue,
        isError
    );

    if (role === "assistant" && !isError && text) {
        addAssistantButtons(
            createdMessage.information,
            text
        );
    }

    chatWindow.appendChild(createdMessage.message);

    if (
        save &&
        (role === "user" || role === "assistant")
    ) {
        addHistoryMessage(role, text);
    }

    scrollToBottom();
    return createdMessage;
}


function createStreamingMessage() {
    removeWelcomeMessage();

    const message = createMessage("", "assistant");
    message.content.textContent = "";
    message.content.classList.add("streaming-cursor");

    chatWindow.appendChild(message.message);
    scrollToBottom();

    return message;
}


function displaySavedHistory() {
    chatWindow.innerHTML = "";

    if (conversationHistory.length === 0) {
        displayWelcomeMessage();
        return;
    }

    conversationHistory.forEach(item => {
        addMessage(
            item.content,
            item.role,
            false,
            item.createdAt
        );
    });

    scrollToBottom();
}


function parseSseEvent(eventBlock) {
    let eventName = "message";
    const dataLines = [];

    for (const line of eventBlock.split("\n")) {
        if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
        }

        if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
        }
    }

    if (dataLines.length === 0) {
        return null;
    }

    return {
        eventName,
        data: JSON.parse(dataLines.join("\n"))
    };
}


async function sendMessage(message) {
    if (isSending) {
        return;
    }

    addMessage(message, "user", true);
    const streamingMessage = createStreamingMessage();
    let assistantReply = "";

    setLoadingState(true);
    announce("The assistant is generating a reply.");

    try {
        const response = await fetch(
            STREAM_API_URL,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                },
                body: JSON.stringify({
                    message,
                    history:
                        conversationHistory
                            .slice(0, -1)
                            .slice(-MAXIMUM_CONTEXT_MESSAGES)
                            .map(item => ({
                                role: item.role,
                                content: item.content
                            })),
                    settings: {
                        model: currentSettings.model,
                        temperature:
                            Number(currentSettings.temperature),
                        response_length:
                            currentSettings.responseLength,
                        system_prompt:
                            currentSettings.systemPrompt
                    }
                })
            }
        );

        if (!response.ok) {
            let errorMessage =
                `Backend error ${response.status}.`;

            try {
                const errorData = await response.json();
                errorMessage =
                    errorData.detail || errorMessage;
            } catch {
                // Keep the fallback message.
            }

            throw new Error(errorMessage);
        }

        if (!response.body) {
            throw new Error(
                "The browser could not read the streaming response."
            );
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const result = await reader.read();

            if (result.done) {
                break;
            }

            buffer += decoder.decode(
                result.value,
                { stream: true }
            );

            buffer = buffer.replace(/\r\n/g, "\n");
            const blocks = buffer.split("\n\n");
            buffer = blocks.pop() || "";

            for (const block of blocks) {
                if (!block.trim()) {
                    continue;
                }

                const event = parseSseEvent(block);

                if (!event) {
                    continue;
                }

                if (event.eventName === "delta") {
                    assistantReply += event.data.text || "";
                    streamingMessage.content.textContent =
                        assistantReply;
                    scrollToBottom();
                }

                if (event.eventName === "error") {
                    throw new Error(
                        event.data.message ||
                        "The local AI request failed."
                    );
                }
            }
        }

        if (!assistantReply.trim()) {
            throw new Error(
                "The local AI returned an empty reply."
            );
        }

        streamingMessage.content.classList.remove(
            "streaming-cursor"
        );

        renderAssistantText(
            streamingMessage.content,
            assistantReply
        );

        addAssistantButtons(
            streamingMessage.information,
            assistantReply
        );

        addHistoryMessage("assistant", assistantReply);
        announce("The assistant reply is complete.");

        if (autoSpeakEnabled) {
            speakText(assistantReply);
        }
    } catch (error) {
        streamingMessage.message.remove();

        const errorMessage = error instanceof TypeError
            ? (
                "Unable to connect to the backend. " +
                "Make sure FastAPI is running on port 8000."
            )
            : (
                error.message ||
                "An unexpected error occurred."
            );

        addMessage(
            errorMessage,
            "assistant",
            false,
            null,
            true
        );

        announce(`Chatbot error: ${errorMessage}`);
        console.error("Chatbot error:", error);
    } finally {
        setLoadingState(false);
        userInput.value = "";
        updateCharacterCounter();
        resizeTextarea();
    }
}


function cleanSpeechText(text) {
    return text
        .replace(/[`*_#>~-]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}


function speakText(text) {
    if (!("speechSynthesis" in window)) {
        announce(
            "Spoken replies are not supported by this browser."
        );
        return;
    }

    const speechText = cleanSpeechText(text);

    if (!speechText) {
        return;
    }

    window.speechSynthesis.cancel();

    const speech =
        new SpeechSynthesisUtterance(speechText);

    speech.lang = "en-US";
    speech.rate = 1;
    speech.pitch = 1;

    window.speechSynthesis.speak(speech);
}


function updateAutoSpeakButton() {
    autoSpeakButton.textContent = autoSpeakEnabled
        ? "🔊 Auto-speak on"
        : "🔇 Auto-speak off";

    autoSpeakButton.setAttribute(
        "aria-pressed",
        String(autoSpeakEnabled)
    );
}


function toggleAutoSpeak() {
    autoSpeakEnabled = !autoSpeakEnabled;

    localStorage.setItem(
        STORAGE_KEYS.autoSpeak,
        String(autoSpeakEnabled)
    );

    if (
        !autoSpeakEnabled &&
        "speechSynthesis" in window
    ) {
        window.speechSynthesis.cancel();
    }

    updateAutoSpeakButton();
}


function setupVoiceInput() {
    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        voiceButton.disabled = true;
        voiceButton.title =
            "Voice input is not supported by this browser";
        return;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.lang = "en-US";
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.maxAlternatives = 1;

    speechRecognition.onstart = () => {
        isListening = true;
        voiceButton.classList.add("listening");
        voiceButton.textContent = "■";
        voiceButton.title = "Stop listening";
        announce("Voice input started.");
    };

    speechRecognition.onresult = event => {
        const spokenText =
            event.results[0][0].transcript.trim();

        userInput.value = userInput.value
            ? `${userInput.value.trim()} ${spokenText}`
            : spokenText;

        updateCharacterCounter();
        resizeTextarea();
    };

    speechRecognition.onerror = event => {
        if (event.error !== "no-speech") {
            announce(
                `Voice input error: ${event.error}.`
            );
        }
    };

    speechRecognition.onend = () => {
        isListening = false;
        voiceButton.classList.remove("listening");
        voiceButton.textContent = "🎤";
        voiceButton.title = "Voice input";
        announce("Voice input stopped.");
        userInput.focus();
    };
}


function toggleVoiceInput() {
    if (!speechRecognition || isSending) {
        return;
    }

    if (isListening) {
        speechRecognition.stop();
        return;
    }

    try {
        speechRecognition.start();
    } catch (error) {
        console.error("Voice input error:", error);
    }
}


async function checkBackendStatus() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/health`,
            { cache: "no-store" }
        );

        if (!response.ok) {
            throw new Error("Health check failed.");
        }

        const data = await response.json();

        if (data.ollama_online && data.model_installed) {
            statusDot.className = "status-dot online";
            statusText.textContent =
                `Online • ${data.model}`;

            if (!currentSettings.model) {
                currentSettings.model = data.model;
            }
        } else if (data.ollama_online) {
            statusDot.className = "status-dot offline";
            statusText.textContent =
                "Configured model is missing";
        } else {
            statusDot.className = "status-dot offline";
            statusText.textContent = "Ollama is offline";
        }
    } catch {
        statusDot.className = "status-dot offline";
        statusText.textContent = "Backend offline";
    }
}


async function loadModels() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/models`,
            { cache: "no-store" }
        );

        if (!response.ok) {
            throw new Error("Could not load models.");
        }

        const data = await response.json();
        const models = data.models || [];

        modelSelect.innerHTML = "";

        if (models.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "No local models detected";
            modelSelect.appendChild(option);
            return;
        }

        for (const model of models) {
            const option = document.createElement("option");
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        }

        modelSelect.value = models.includes(currentSettings.model)
            ? currentSettings.model
            : data.default_model;
    } catch (error) {
        announce(error.message);
    }
}


function populateSettingsForm() {
    modelSelect.value = currentSettings.model;
    responseLengthSelect.value =
        currentSettings.responseLength;
    temperatureInput.value =
        String(currentSettings.temperature);
    temperatureValue.textContent =
        Number(currentSettings.temperature).toFixed(1);
    systemPromptInput.value =
        currentSettings.systemPrompt;
    chatSizeSelect.value = currentSettings.chatSize;
}


function saveSettings() {
    currentSettings = {
        model: modelSelect.value || DEFAULT_SETTINGS.model,
        temperature: Number(temperatureInput.value),
        responseLength: responseLengthSelect.value,
        systemPrompt: systemPromptInput.value.trim(),
        chatSize: chatSizeSelect.value
    };

    saveSettingsToStorage();
    applyChatSize(currentSettings.chatSize);
    announce("Chatbot settings saved.");
    closeSettings();
}


function resetSettings() {
    currentSettings = { ...DEFAULT_SETTINGS };
    saveSettingsToStorage();
    populateSettingsForm();
    applyChatSize(currentSettings.chatSize);
    announce("Chatbot settings reset.");
}


function startNewConversation() {
    const confirmed =
        conversationHistory.length === 0 ||
        window.confirm(
            "Start a new conversation and clear the current browser history?"
        );

    if (!confirmed) {
        return;
    }

    conversationHistory = [];
    localStorage.removeItem(STORAGE_KEYS.history);

    if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
    }

    displayWelcomeMessage();
    userInput.value = "";
    updateCharacterCounter();
    resizeTextarea();
    userInput.focus();
    announce("A new conversation has started.");
}


openChatButton.addEventListener("click", openChat);
chatLauncher.addEventListener("click", openChat);
closeChatButton.addEventListener("click", closeChat);
themeButton.addEventListener("click", toggleTheme);
settingsButton.addEventListener("click", openSettings);
closeSettingsButton.addEventListener(
    "click",
    () => closeSettings()
);
expandButton.addEventListener("click", toggleFullScreen);
newChatButton.addEventListener("click", startNewConversation);
clearButton.addEventListener("click", startNewConversation);
autoSpeakButton.addEventListener("click", toggleAutoSpeak);
voiceButton.addEventListener("click", toggleVoiceInput);


temperatureInput.addEventListener("input", () => {
    temperatureValue.textContent =
        Number(temperatureInput.value).toFixed(1);
});


chatSizeSelect.addEventListener("change", () => {
    applyChatSize(chatSizeSelect.value);
});


saveSettingsButton.addEventListener("click", saveSettings);
resetSettingsButton.addEventListener("click", resetSettings);


chatForm.addEventListener("submit", event => {
    event.preventDefault();

    const message = userInput.value.trim();

    if (!message) {
        announce(
            "Please enter a question before pressing Send."
        );
        userInput.focus();
        return;
    }

    sendMessage(message);
});


userInput.addEventListener("input", () => {
    updateCharacterCounter();
    resizeTextarea();
});


userInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chatForm.requestSubmit();
    }
});


suggestionButtons.forEach(button => {
    button.addEventListener("click", () => {
        userInput.value = button.dataset.question || "";
        updateCharacterCounter();
        resizeTextarea();
        userInput.focus();
    });
});


chatWidget.addEventListener("keydown", trapFocus);


document.addEventListener("keydown", event => {
    if (event.key !== "Escape") {
        return;
    }

    if (!settingsPanel.hidden) {
        closeSettings();
    } else if (chatWidget.classList.contains("open")) {
        closeChat();
    }
});


applyTheme(
    localStorage.getItem(STORAGE_KEYS.theme) || "light"
);
applyChatSize(currentSettings.chatSize);
updateAutoSpeakButton();
displaySavedHistory();
updateCharacterCounter();
resizeTextarea();
setupVoiceInput();
checkBackendStatus();

window.setInterval(checkBackendStatus, 30000);
