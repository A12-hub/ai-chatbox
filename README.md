# AI Chatbot Assistant — Updated Existing Project

This is the same existing project, updated in place. The Ollama backend,
streaming replies, voice input, spoken replies, dark mode, follow-up context,
and browser history are preserved.

## Added features

- Compact, Standard and Large chatbot sizes
- Full-screen chatbot button
- University of Makeni logo on the landing page, welcome screen and chatbot profile
- Better formatting for numbered lists, bullet lists and fenced code blocks
- Short, Medium and Long response-length options
- Additional system-prompt setting
- Model selector for locally installed Ollama models
- Temperature control
- Accessible screen-reader announcements
- Keyboard focus trap in the open chatbot
- Escape closes Settings first and then closes the chatbot
- Strong visible keyboard focus rings
- Professional responsive phone layout
- AI accuracy disclaimer and browser-storage privacy note

## Logo

The logo is stored at:

frontend/assets/unimak-logo.jfif

To change it later, replace that file with another image using the same filename.

## Start the existing project

From the existing project folder:

1. Activate the existing environment:
   .\venv\Scripts\Activate.ps1

2. Start the backend:
   python -m uvicorn backend.main:app --reload

3. Open a second terminal and start the frontend:
   python -m http.server 5500 --directory frontend

4. Open:
   http://127.0.0.1:5500
