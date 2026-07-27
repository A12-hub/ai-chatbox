import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ======================================================
# PROJECT AND ENVIRONMENT CONFIGURATION
# ======================================================

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
CHATBOX_FILE = FRONTEND_DIR / "index.html"
DATABASE_FILE = BACKEND_DIR / "chatbot_users.db"

load_dotenv(
    BACKEND_DIR / ".env",
    override=True,
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:1b",
).strip()

SESSION_COOKIE_NAME = "chatbot_session"
SESSION_DAYS = 7

RESPONSE_LENGTH_TOKENS = {
    "short": 220,
    "medium": 520,
    "long": 1000,
}


# ======================================================
# FASTAPI APPLICATION
# ======================================================

app = FastAPI(
    title="AI Chatbot Assistant",
    description=(
        "A protected Computer Science AI chatbot powered by Ollama."
    ),
    version="6.0.0",
)

# CORS is retained for development tools such as VS Code Live Server.
# The recommended method is to open the project through port 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# CHATBOT INSTRUCTIONS
# ======================================================

SYSTEM_INSTRUCTIONS = """
You are a Computer Science AI Learning Assistant.

Your main role is to help university students and beginners
understand computer science and technology.

You answer questions about:

- computer programming;
- Python;
- HTML, CSS and JavaScript;
- web development;
- software engineering;
- databases;
- artificial intelligence;
- operating systems;
- computer networking;
- cybersecurity awareness;
- computer applications;
- basic computer troubleshooting.

Instructions:

1. Use clear and simple English.
2. Explain technical words before using them extensively.
3. Give practical examples where appropriate.
4. Use numbered steps when explaining procedures.
5. Use supplied conversation history for follow-up questions.
6. Politely redirect questions outside computer science.
7. Never claim to perform an action you did not perform.
8. Provide safe, legal and ethical guidance.
9. Format lists clearly and place code in fenced code blocks.
""".strip()


# ======================================================
# REQUEST MODELS
# ======================================================

class RegistrationRequest(BaseModel):
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
    )
    email: str = Field(
        ...,
        min_length=5,
        max_length=254,
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
    )


class LoginRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=5,
        max_length=254,
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
    )


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )


class ChatSettings(BaseModel):
    model: str | None = Field(
        default=None,
        max_length=200,
    )

    temperature: float = Field(
        default=0.4,
        ge=0.0,
        le=2.0,
    )

    response_length: Literal[
        "short",
        "medium",
        "long",
    ] = "medium"

    system_prompt: str = Field(
        default="",
        max_length=3000,
    )


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )

    history: list[HistoryMessage] = Field(
        default_factory=list,
    )

    settings: ChatSettings = Field(
        default_factory=ChatSettings,
    )


# ======================================================
# DATABASE FUNCTIONS
# ======================================================

def get_database() -> sqlite3.Connection:
    """Open the local SQLite database."""

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    """Create the user and session tables when they do not exist."""

    with get_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id
            ON sessions(user_id)
            """
        )

        connection.commit()


initialise_database()


# ======================================================
# PASSWORD AND SESSION HELPERS
# ======================================================

def normalise_email(email_address: str) -> str:
    return email_address.strip().lower()


def valid_email(email_address: str) -> bool:
    """Perform a simple local email-format check."""

    if email_address.count("@") != 1:
        return False

    local_part, domain_part = email_address.split("@")

    return bool(
        local_part
        and domain_part
        and "." in domain_part
        and not email_address.startswith(".")
        and not email_address.endswith(".")
    )


def hash_password(password: str) -> tuple[str, str]:
    """Create a salted PBKDF2 password hash."""

    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        250_000,
    )

    return salt.hex(), password_hash.hex()


def verify_password(
    password: str,
    stored_salt: str,
    stored_hash: str,
) -> bool:
    """Check a password against its stored hash."""

    try:
        salt = bytes.fromhex(stored_salt)
    except ValueError:
        return False

    calculated_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        250_000,
    ).hex()

    return hmac.compare_digest(
        calculated_hash,
        stored_hash,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(user_id: int) -> str:
    """Create a persistent login session in SQLite."""

    token = secrets.token_urlsafe(40)
    created_at = utc_now()
    expires_at = created_at + timedelta(days=SESSION_DAYS)

    with get_database() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE expires_at <= ?",
            (created_at.isoformat(),),
        )

        connection.execute(
            """
            INSERT INTO sessions (
                token,
                user_id,
                expires_at,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                token,
                user_id,
                expires_at.isoformat(),
                created_at.isoformat(),
            ),
        )

        connection.commit()

    return token


def delete_session(token: str | None) -> None:
    if not token:
        return

    with get_database() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token = ?",
            (token,),
        )
        connection.commit()


def get_current_user(request: Request) -> sqlite3.Row | None:
    """Return the logged-in user represented by the session cookie."""

    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        return None

    now_text = utc_now().isoformat()

    with get_database() as connection:
        user = connection.execute(
            """
            SELECT
                users.id,
                users.full_name,
                users.email,
                users.created_at
            FROM sessions
            INNER JOIN users
                ON users.id = sessions.user_id
            WHERE sessions.token = ?
              AND sessions.expires_at > ?
            """,
            (token, now_text),
        ).fetchone()

        if user is None:
            connection.execute(
                "DELETE FROM sessions WHERE token = ?",
                (token,),
            )
            connection.commit()

    return user


def require_current_user(request: Request) -> sqlite3.Row:
    user = get_current_user(request)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "You must log in before using the chatbot."
            ),
        )

    return user


# ======================================================
# AUTHENTICATION PAGE HTML
# ======================================================

AUTH_STYLES = """
:root {
    color-scheme: light;
    --navy: #092743;
    --blue: #155b91;
    --gold: #d7a625;
    --background: #edf4f8;
    --text: #17324a;
    --muted: #617587;
    --danger: #b42318;
    --success: #157347;
}

* {
    box-sizing: border-box;
}

body {
    min-height: 100vh;
    margin: 0;
    padding: 24px;
    display: grid;
    place-items: center;
    font-family: Arial, Helvetica, sans-serif;
    color: var(--text);
    background:
        radial-gradient(circle at top right, #2c79ad 0, transparent 34%),
        linear-gradient(135deg, #061c31, #123e62 55%, #0d2d49);
}

.auth-shell {
    width: min(100%, 440px);
}

.auth-card {
    padding: 34px;
    border: 1px solid rgba(255, 255, 255, 0.38);
    border-radius: 22px;
    background: rgba(255, 255, 255, 0.97);
    box-shadow: 0 26px 70px rgba(0, 0, 0, 0.28);
}

.brand-mark {
    width: 66px;
    height: 66px;
    margin: 0 auto 14px;
    display: grid;
    place-items: center;
    border-radius: 18px;
    color: white;
    background: linear-gradient(145deg, var(--blue), var(--navy));
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 1px;
    box-shadow: 0 12px 28px rgba(9, 39, 67, 0.25);
}

h1 {
    margin: 0;
    text-align: center;
    font-size: clamp(1.7rem, 5vw, 2.15rem);
    color: var(--navy);
}

.subtitle {
    margin: 10px 0 26px;
    text-align: center;
    line-height: 1.55;
    color: var(--muted);
}

label {
    display: block;
    margin: 15px 0 7px;
    font-size: 0.94rem;
    font-weight: 700;
}

input {
    width: 100%;
    padding: 13px 14px;
    border: 1px solid #b8c8d3;
    border-radius: 10px;
    background: white;
    color: var(--text);
    font: inherit;
}

input:focus {
    border-color: var(--blue);
    outline: 3px solid rgba(21, 91, 145, 0.16);
}

button {
    width: 100%;
    margin-top: 22px;
    padding: 14px 16px;
    border: 0;
    border-radius: 11px;
    color: white;
    background: linear-gradient(135deg, var(--blue), var(--navy));
    font: inherit;
    font-weight: 800;
    cursor: pointer;
    box-shadow: 0 10px 24px rgba(9, 39, 67, 0.22);
}

button:disabled {
    opacity: 0.65;
    cursor: wait;
}

.message {
    min-height: 24px;
    margin: 16px 0 0;
    text-align: center;
    line-height: 1.45;
    color: var(--danger);
}

.message.success {
    color: var(--success);
}

.switch-page {
    margin: 18px 0 0;
    text-align: center;
    color: var(--muted);
}

.switch-page a {
    color: var(--blue);
    font-weight: 800;
    text-decoration: none;
}

.switch-page a:hover {
    text-decoration: underline;
}

.privacy-note {
    margin: 20px 0 0;
    padding-top: 16px;
    border-top: 1px solid #dde6eb;
    text-align: center;
    font-size: 0.82rem;
    line-height: 1.5;
    color: var(--muted);
}

@media (max-width: 520px) {
    body {
        padding: 14px;
    }

    .auth-card {
        padding: 25px 20px;
        border-radius: 17px;
    }
}
"""


def login_page(error_message: str = "") -> str:
    safe_error = html.escape(error_message)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | AI Chatbot Assistant</title>
    <style>{AUTH_STYLES}</style>
</head>
<body>
    <main class="auth-shell">
        <section class="auth-card" aria-labelledby="page-title">
            <div class="brand-mark" aria-hidden="true">AI</div>
            <h1 id="page-title">Welcome Back</h1>
            <p class="subtitle">
                Log in to access the Computer Science AI Chatbot Assistant.
            </p>

            <form id="login-form">
                <label for="email">Email address</label>
                <input
                    id="email"
                    name="email"
                    type="email"
                    autocomplete="email"
                    required
                >

                <label for="password">Password</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    autocomplete="current-password"
                    required
                >

                <button id="submit-button" type="submit">Log In</button>
            </form>

            <p id="message" class="message" aria-live="polite">{safe_error}</p>

            <p class="switch-page">
                Do not have an account?
                <a href="/register">Register here</a>
            </p>

            <p class="privacy-note">
                Your account is stored locally on this computer.
                Chatbot responses may be inaccurate, so verify important information.
            </p>
        </section>
    </main>

    <script>
        const form = document.getElementById("login-form");
        const message = document.getElementById("message");
        const button = document.getElementById("submit-button");

        form.addEventListener("submit", async (event) => {{
            event.preventDefault();
            message.classList.remove("success");
            message.textContent = "Logging in...";
            button.disabled = true;

            try {{
                const response = await fetch("/api/login", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json"
                    }},
                    credentials: "same-origin",
                    body: JSON.stringify({{
                        email: document.getElementById("email").value.trim(),
                        password: document.getElementById("password").value
                    }})
                }});

                const result = await response.json();

                if (!response.ok) {{
                    message.textContent = result.detail || "Login failed.";
                    return;
                }}

                message.classList.add("success");
                message.textContent = "Login successful. Opening chatbot...";
                window.location.replace("/chatbox");
            }} catch (error) {{
                console.error(error);
                message.textContent = "The server could not be reached.";
            }} finally {{
                button.disabled = false;
            }}
        }});
    </script>
</body>
</html>"""


def registration_page() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Registration | AI Chatbot Assistant</title>
    <style>{AUTH_STYLES}</style>
</head>
<body>
    <main class="auth-shell">
        <section class="auth-card" aria-labelledby="page-title">
            <div class="brand-mark" aria-hidden="true">AI</div>
            <h1 id="page-title">Create Account</h1>
            <p class="subtitle">
                Register once, then use your account to access the chatbot.
            </p>

            <form id="registration-form">
                <label for="full-name">Full name</label>
                <input
                    id="full-name"
                    name="full_name"
                    type="text"
                    autocomplete="name"
                    minlength="2"
                    required
                >

                <label for="email">Email address</label>
                <input
                    id="email"
                    name="email"
                    type="email"
                    autocomplete="email"
                    required
                >

                <label for="password">Password</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    autocomplete="new-password"
                    minlength="6"
                    required
                >

                <label for="confirm-password">Confirm password</label>
                <input
                    id="confirm-password"
                    name="confirm_password"
                    type="password"
                    autocomplete="new-password"
                    minlength="6"
                    required
                >

                <button id="submit-button" type="submit">Create Account</button>
            </form>

            <p id="message" class="message" aria-live="polite"></p>

            <p class="switch-page">
                Already registered?
                <a href="/">Return to login</a>
            </p>

            <p class="privacy-note">
                Passwords are protected using salted password hashing.
                Your account is stored in the local SQLite database.
            </p>
        </section>
    </main>

    <script>
        const form = document.getElementById("registration-form");
        const message = document.getElementById("message");
        const button = document.getElementById("submit-button");

        form.addEventListener("submit", async (event) => {{
            event.preventDefault();
            message.classList.remove("success");

            const password = document.getElementById("password").value;
            const confirmation = document.getElementById("confirm-password").value;

            if (password !== confirmation) {{
                message.textContent = "The two passwords do not match.";
                return;
            }}

            message.textContent = "Creating your account...";
            button.disabled = true;

            try {{
                const response = await fetch("/api/register", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json"
                    }},
                    body: JSON.stringify({{
                        full_name: document.getElementById("full-name").value.trim(),
                        email: document.getElementById("email").value.trim(),
                        password
                    }})
                }});

                const result = await response.json();

                if (!response.ok) {{
                    message.textContent = result.detail || "Registration failed.";
                    return;
                }}

                message.classList.add("success");
                message.textContent = "Registration successful. Opening login...";

                window.setTimeout(() => {{
                    window.location.replace("/");
                }}, 900);
            }} catch (error) {{
                console.error(error);
                message.textContent = "The server could not be reached.";
            }} finally {{
                button.disabled = false;
            }}
        }});
    </script>
</body>
</html>"""


CHATBOX_AUTH_INJECTION = """
<style>
    #auth-session-controls {
        position: fixed;
        top: 14px;
        right: 16px;
        z-index: 99999;
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 12px;
        background: rgba(8, 32, 54, 0.92);
        color: white;
        font-family: Arial, Helvetica, sans-serif;
        box-shadow: 0 10px 26px rgba(0, 0, 0, 0.24);
        backdrop-filter: blur(8px);
    }

    #auth-session-name {
        max-width: 180px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 13px;
    }

    #auth-logout-button {
        margin: 0;
        padding: 7px 11px;
        border: 0;
        border-radius: 8px;
        background: #ffffff;
        color: #092743;
        font: inherit;
        font-size: 13px;
        font-weight: 800;
        cursor: pointer;
    }

    @media (max-width: 600px) {
        #auth-session-controls {
            top: 8px;
            right: 8px;
        }

        #auth-session-name {
            display: none;
        }
    }
</style>

<div id="auth-session-controls" aria-label="Account controls">
    <span id="auth-session-name">Signed in</span>
    <button id="auth-logout-button" type="button">Log Out</button>
</div>

<script>
    (async function protectChatboxPage() {
        const nameElement = document.getElementById("auth-session-name");
        const logoutButton = document.getElementById("auth-logout-button");

        try {
            const response = await fetch("/api/me", {
                credentials: "same-origin"
            });

            if (!response.ok) {
                window.location.replace("/");
                return;
            }

            const user = await response.json();
            nameElement.textContent = user.full_name || "Signed in";
        } catch (error) {
            console.error(error);
            window.location.replace("/");
            return;
        }

        logoutButton.addEventListener("click", async () => {
            logoutButton.disabled = true;

            try {
                await fetch("/api/logout", {
                    method: "POST",
                    credentials: "same-origin"
                });
            } finally {
                window.location.replace("/");
            }
        });
    })();
</script>
"""


def build_protected_chatbox_html() -> str:
    """Read the current frontend and add session controls."""

    if not CHATBOX_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "frontend/index.html was not found. Expected location: "
                f"{CHATBOX_FILE}"
            ),
        )

    chatbot_html = CHATBOX_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if "auth-session-controls" in chatbot_html:
        return chatbot_html

    closing_body_index = chatbot_html.lower().rfind("</body>")

    if closing_body_index == -1:
        return chatbot_html + CHATBOX_AUTH_INJECTION

    return (
        chatbot_html[:closing_body_index]
        + CHATBOX_AUTH_INJECTION
        + chatbot_html[closing_body_index:]
    )


# ======================================================
# OLLAMA HELPER FUNCTIONS
# ======================================================

def get_ollama_status() -> dict:
    """Check whether Ollama is running and list installed models."""

    try:
        response = httpx.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5.0,
        )
        response.raise_for_status()

        data = response.json()
        installed_models = set()

        for model in data.get("models", []):
            model_name = (
                model.get("name")
                or model.get("model")
                or ""
            ).strip()

            if model_name:
                installed_models.add(model_name)

        return {
            "online": True,
            "model_installed": OLLAMA_MODEL in installed_models,
            "installed_models": sorted(installed_models),
        }

    except Exception:
        return {
            "online": False,
            "model_installed": False,
            "installed_models": [],
        }


def resolve_model(requested_model: str | None) -> str:
    """Use an installed model selected in the chatbot settings."""

    status = get_ollama_status()

    if not status["online"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Ollama is offline. Open Ollama from the Windows Start "
                "menu or run 'ollama serve'."
            ),
        )

    selected_model = (
        requested_model.strip()
        if requested_model and requested_model.strip()
        else OLLAMA_MODEL
    )

    if selected_model not in status["installed_models"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The selected model '{selected_model}' is not installed. "
                "Installed models: "
                f"{', '.join(status['installed_models']) or 'none'}."
            ),
        )

    return selected_model


def build_system_prompt(custom_prompt: str) -> str:
    """Preserve the main role and add the user's response preference."""

    clean_custom_prompt = custom_prompt.strip()

    if not clean_custom_prompt:
        return SYSTEM_INSTRUCTIONS

    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        "Additional response preference from chatbot settings:\n"
        f"{clean_custom_prompt}"
    )


def create_messages(chat_request: ChatRequest) -> list[dict[str, str]]:
    """Build the conversation sent to Ollama."""

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                chat_request.settings.system_prompt
            ),
        }
    ]

    for item in chat_request.history[-12:]:
        messages.append(
            {
                "role": item.role,
                "content": item.content,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": chat_request.message.strip(),
        }
    )

    return messages


def create_generation_options(settings: ChatSettings) -> dict:
    """Translate frontend settings into Ollama options."""

    return {
        "temperature": settings.temperature,
        "num_predict": RESPONSE_LENGTH_TOKENS[
            settings.response_length
        ],
    }


def format_sse_event(event_name: str, data: dict) -> str:
    """Convert data into a Server-Sent Event block."""

    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def friendly_ollama_error(error: Exception) -> str:
    """Convert common Ollama errors into simple messages."""

    error_text = str(error).lower()

    if (
        "connection refused" in error_text
        or "connecterror" in error_text
        or "all connection attempts failed" in error_text
    ):
        return (
            "Ollama is not running. Open Ollama from the Windows Start "
            "menu or run 'ollama serve', then try again."
        )

    if "not found" in error_text and "model" in error_text:
        return (
            "The selected local AI model is not installed. "
            "Open Settings and choose an installed model."
        )

    if "timed out" in error_text or "timeout" in error_text:
        return (
            "The local AI model took too long to respond. "
            "Wait a moment and try again."
        )

    return (
        "The local AI model could not complete the request. "
        "Check the VS Code terminal for details."
    )


# ======================================================
# LOGIN, REGISTRATION AND PAGE ROUTES
# ======================================================

@app.get("/", response_class=HTMLResponse)
def show_login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(
            url="/chatbox",
            status_code=303,
        )

    return HTMLResponse(login_page())


@app.get("/register", response_class=HTMLResponse)
def show_registration_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(
            url="/chatbox",
            status_code=303,
        )

    return HTMLResponse(registration_page())


@app.get("/chatbox", response_class=HTMLResponse)
def show_chatbox_page(request: Request):
    if get_current_user(request) is None:
        return RedirectResponse(
            url="/",
            status_code=303,
        )

    return HTMLResponse(build_protected_chatbox_html())


@app.get("/index.html")
def block_direct_index_access():
    """Prevent users from bypassing login through /index.html."""

    return RedirectResponse(
        url="/",
        status_code=303,
    )


@app.post("/api/register")
def register_user(data: RegistrationRequest):
    full_name = " ".join(data.full_name.strip().split())
    email_address = normalise_email(data.email)

    if len(full_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Please enter your full name.",
        )

    if not valid_email(email_address):
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address.",
        )

    if len(data.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters.",
        )

    salt, password_hash = hash_password(data.password)

    try:
        with get_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    password_hash,
                    password_salt,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    full_name,
                    email_address,
                    password_hash,
                    salt,
                    utc_now().isoformat(),
                ),
            )
            connection.commit()
            user_id = cursor.lastrowid

    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail=(
                "An account already exists with this email address."
            ),
        ) from error

    return {
        "success": True,
        "message": "Registration successful.",
        "user_id": user_id,
    }


@app.post("/api/login")
def login_user(data: LoginRequest):
    email_address = normalise_email(data.email)

    with get_database() as connection:
        user = connection.execute(
            """
            SELECT
                id,
                full_name,
                email,
                password_hash,
                password_salt
            FROM users
            WHERE email = ?
            """,
            (email_address,),
        ).fetchone()

    if user is None or not verify_password(
        data.password,
        user["password_salt"],
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email address or password.",
        )

    session_token = create_session(user["id"])

    response = JSONResponse(
        content={
            "success": True,
            "message": "Login successful.",
            "user": {
                "full_name": user["full_name"],
                "email": user["email"],
            },
        }
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )

    return response


@app.get("/api/me")
def read_current_user(request: Request):
    user = require_current_user(request)

    return {
        "id": user["id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


@app.post("/api/logout")
def logout_user(request: Request):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    delete_session(session_token)

    response = JSONResponse(
        content={
            "success": True,
            "message": "Logout successful.",
        }
    )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )

    return response


# ======================================================
# STATUS ROUTES
# ======================================================

@app.get("/api/status")
def backend_status() -> dict:
    status = get_ollama_status()

    return {
        "message": "AI Chatbot Assistant backend is running successfully.",
        "provider": "Ollama",
        "model": OLLAMA_MODEL,
        "streaming": True,
        "ollama_online": status["online"],
        "model_installed": status["model_installed"],
    }


@app.get("/health")
def health_check() -> dict:
    status = get_ollama_status()

    return {
        "status": (
            "healthy"
            if status["online"] and status["model_installed"]
            else "attention_required"
        ),
        "provider": "Ollama",
        "model": OLLAMA_MODEL,
        "streaming": True,
        "ollama_online": status["online"],
        "model_installed": status["model_installed"],
        "installed_models": status["installed_models"],
    }


@app.get("/models")
def list_models(request: Request) -> dict:
    require_current_user(request)
    status = get_ollama_status()

    return {
        "ollama_online": status["online"],
        "default_model": OLLAMA_MODEL,
        "models": status["installed_models"],
    }


# ======================================================
# PROTECTED NON-STREAMING CHAT ROUTE
# ======================================================

@app.post("/chat")
def normal_chat(
    chat_request: ChatRequest,
    request: Request,
) -> dict:
    require_current_user(request)
    clean_message = chat_request.message.strip()

    if not clean_message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    selected_model = resolve_model(
        chat_request.settings.model
    )

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": selected_model,
                "messages": create_messages(chat_request),
                "options": create_generation_options(
                    chat_request.settings
                ),
                "stream": False,
            },
            timeout=300.0,
        )

        response.raise_for_status()
        data = response.json()

        reply = (
            data.get("message", {})
            .get("content", "")
            .strip()
        )

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The local AI model returned an empty reply.",
            )

        return {
            "reply": reply,
            "provider": "Ollama",
            "model": selected_model,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Ollama non-streaming error: {error}")

        raise HTTPException(
            status_code=502,
            detail=friendly_ollama_error(error),
        ) from error


# ======================================================
# PROTECTED STREAMING CHAT ROUTE
# ======================================================

@app.post("/chat/stream")
def stream_chat(
    chat_request: ChatRequest,
    request: Request,
) -> StreamingResponse:
    require_current_user(request)
    clean_message = chat_request.message.strip()

    if not clean_message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    selected_model = resolve_model(
        chat_request.settings.model
    )

    def generate_stream() -> Generator[str, None, None]:
        try:
            timeout = httpx.Timeout(
                connect=10.0,
                read=300.0,
                write=30.0,
                pool=30.0,
            )

            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": selected_model,
                        "messages": create_messages(chat_request),
                        "options": create_generation_options(
                            chat_request.settings
                        ),
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if not line:
                            continue

                        data = json.loads(line)

                        if data.get("error"):
                            yield format_sse_event(
                                "error",
                                {"message": data["error"]},
                            )
                            return

                        text_delta = (
                            data.get("message", {})
                            .get("content", "")
                        )

                        if text_delta:
                            yield format_sse_event(
                                "delta",
                                {"text": text_delta},
                            )

                        if data.get("done"):
                            yield format_sse_event(
                                "done",
                                {
                                    "done": True,
                                    "provider": "Ollama",
                                    "model": data.get(
                                        "model",
                                        selected_model,
                                    ),
                                },
                            )
                            return

        except Exception as error:
            print(f"Ollama streaming error: {error}")

            yield format_sse_event(
                "error",
                {"message": friendly_ollama_error(error)},
            )

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ======================================================
# FRONTEND STATIC FILES
# ======================================================

# Keep this mount at the bottom so the protected routes above
# are checked before ordinary frontend files such as CSS, JS and images.
if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(
            directory=str(FRONTEND_DIR),
            html=False,
        ),
        name="frontend",
    )
