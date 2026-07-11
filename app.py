"""
Hebo — AI Voice Assistant (v2)
Free, fast, deployable on Streamlit Community Cloud.

Stack (all free tiers):
- Brain: Groq (Llama 3.3 70B / 3.1 8B) — extremely fast inference, free API
- Ears (Speech-to-Text): Groq Whisper Large v3 Turbo
- Mouth (Text-to-Speech): gTTS (Google Translate TTS, free, no key needed)
- Tools: DuckDuckGo web search (free, no key needed)

v2 additions: call-style voice mode, multi-chat sidebar (like ChatGPT/Claude),
dark custom UI, model switcher, specialist persona (trading / wealth mindset / coding).
"""

import base64
import datetime
import io
import json
import os
import time
import uuid

import streamlit as st
from audio_recorder_streamlit import audio_recorder
from duckduckgo_search import DDGS
from groq import Groq
from gtts import gTTS

# ----------------------------------------------------------------------
# PAGE CONFIG + THEME
# ----------------------------------------------------------------------
st.set_page_config(page_title="Hebo — AI Assistant", page_icon="🤖", layout="wide")

CUSTOM_CSS = """
<style>
#MainMenu, footer, header {visibility: hidden;}

h1 {
    background: linear-gradient(90deg, #7dd3fc, #a78bfa, #f472b6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-weight: 800;
}

div[data-testid="stChatMessage"] {
    border: 1px solid #262730; border-radius: 14px;
    padding: 4px 6px; margin-bottom: 10px;
}

.hebo-badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    background: #1f2937; color: #93c5fd; font-size: 12px; margin-right: 6px;
}
.call-status {
    text-align: center; font-size: 15px; opacity: 0.75; margin-top: 6px;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
WHISPER_MODEL = "whisper-large-v3-turbo"
MODEL_OPTIONS = {
    "🧠 Smart (70B) — best quality": "llama-3.3-70b-versatile",
    "⚡ Fast (8B) — instant replies": "llama-3.1-8b-instant",
}

if not GROQ_API_KEY:
    st.error(
        "⚠️ No GROQ_API_KEY found.\n\n"
        "Get a **free** key at https://console.groq.com/keys and add it to "
        "`.streamlit/secrets.toml` locally, or in your app's *Settings → Secrets* "
        "once deployed on Streamlit Cloud."
    )
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are Hebo — a sharp, no-fluff AI assistant with three areas of deep expertise:

1. TRADING & MARKETS: You understand technical analysis, risk management, position sizing,
   market structure, macro factors, and common strategies across stocks, crypto, and forex.
   You explain concepts clearly and give balanced, educational information — not confident
   "buy/sell now" calls. You always note that markets are risky, past performance doesn't
   guarantee future results, and you are not a licensed financial advisor, so the user should
   do their own research and/or consult a professional before risking real money.

2. WEALTH-BUILDING & SUCCESS MINDSET: You coach on financial discipline, income growth,
   saving/investing habits, entrepreneurship, productivity, and mental resilience. You're
   motivating but realistic — no empty hype, no guaranteed-riches promises. You give concrete,
   actionable steps, not vague platitudes.

3. CODING: You are an expert software engineer across Python, JavaScript/TypeScript, web dev,
   and general CS fundamentals. You write clean, correct, well-commented code, explain your
   reasoning briefly, and proactively point out bugs, edge cases, or better approaches.

General style: Be direct, confident, and warm — like a smart friend who tells you the truth.
Keep spoken replies natural and conversational since they're often read aloud; keep text
replies well-formatted with headers/bullets/code blocks when useful. Use tools (web search)
when you need current information — prices, news, recent events — rather than guessing.
Today's date is {date}.
"""

# ----------------------------------------------------------------------
# SESSION STATE — multi-chat support
# ----------------------------------------------------------------------
def new_chat():
    cid = str(uuid.uuid4())[:8]
    st.session_state.chats[cid] = {
        "title": "New chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(date=datetime.date.today())}
        ],
    }
    st.session_state.current_chat = cid


if "chats" not in st.session_state:
    st.session_state.chats = {}
    new_chat()
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True
if "call_mode" not in st.session_state:
    st.session_state.call_mode = False
if "model_choice" not in st.session_state:
    st.session_state.model_choice = MODEL_OPTIONS["🧠 Smart (70B) — best quality"]

current = st.session_state.chats[st.session_state.current_chat]
messages = current["messages"]

# ----------------------------------------------------------------------
# TOOLS
# ----------------------------------------------------------------------
def web_search(query: str, max_results: int = 4) -> str:
    """Free web search via DuckDuckGo — no API key required."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        return "\n\n".join(
            f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}" for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live web for current events, prices, news, or anything "
                "Hebo doesn't already know or that may have changed recently."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"],
            },
        },
    }
]
AVAILABLE_FUNCTIONS = {"web_search": web_search}

# ----------------------------------------------------------------------
# STT / TTS
# ----------------------------------------------------------------------
MIN_AUDIO_BYTES = 4000  # filters out empty/near-silent blips (esp. from auto_start call mode)
                         # before they ever reach the Groq API


def transcribe_audio(audio_bytes: bytes) -> str | None:
    """Returns the transcript, or None if there wasn't enough real audio to transcribe."""
    if not audio_bytes or len(audio_bytes) < MIN_AUDIO_BYTES:
        return None
    try:
        transcription = client.audio.transcriptions.create(
            file=("audio.wav", audio_bytes), model=WHISPER_MODEL
        )
        return transcription.text
    except Exception as e:
        st.toast(f"Transcription error: {e}", icon="⚠️")
        return None


def synthesize_speech(text: str) -> bytes:
    try:
        tts = gTTS(text=text, lang="en")
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.warning(f"Voice generation failed: {e}")
        return b""


def autoplay_audio(audio_bytes: bytes):
    if not audio_bytes:
        return
    b64 = base64.b64encode(audio_bytes).decode()
    st.markdown(
        f'<audio autoplay src="data:audio/mp3;base64,{b64}"></audio>', unsafe_allow_html=True
    )

# ----------------------------------------------------------------------
# LLM CALL (tool-calling loop)
# ----------------------------------------------------------------------
def get_hebo_response(msgs, model):
    response = client.chat.completions.create(
        model=model, messages=msgs, tools=TOOLS, tool_choice="auto",
        temperature=0.7, max_tokens=1024,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        msgs.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            result = AVAILABLE_FUNCTIONS[fn_name](**fn_args)
            msgs.append(
                {"role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": result}
            )
        second = client.chat.completions.create(
            model=model, messages=msgs, temperature=0.7, max_tokens=1024
        )
        return second.choices[0].message.content
    return msg.content


def type_out(placeholder, text: str, delay: float = 0.015):
    """Renders text word-by-word for a typewriter effect, like other AI chat apps."""
    shown = ""
    words = text.split(" ")
    for i, word in enumerate(words):
        shown += word + (" " if i < len(words) - 1 else "")
        placeholder.markdown(shown + "▌")
        time.sleep(delay)
    placeholder.markdown(shown)


def handle_user_message(user_text: str):
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_text)
    messages.append({"role": "user", "content": user_text})

    if current["title"] == "New chat":
        current["title"] = user_text[:40] + ("..." if len(user_text) > 40 else "")

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("💭 Hebo is thinking..."):
            reply = get_hebo_response(messages, st.session_state.model_choice)
        placeholder = st.empty()
        type_out(placeholder, reply)
        messages.append({"role": "assistant", "content": reply})

        if st.session_state.voice_enabled:
            with st.spinner("🔊 Generating voice..."):
                audio_out = synthesize_speech(reply)
            autoplay_audio(audio_out)

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🤖 Hebo")
    if st.button("➕ New chat"):
        new_chat()
        st.rerun()

    st.markdown("---")
    st.caption("CHATS")
    for cid, chat in list(st.session_state.chats.items())[::-1]:
        label = ("📍 " if cid == st.session_state.current_chat else "") + chat["title"]
        if st.button(label, key=f"switch_{cid}"):
            st.session_state.current_chat = cid
            st.rerun()

    st.markdown("---")
    st.caption("SETTINGS")
    st.session_state.model_choice = MODEL_OPTIONS[
        st.selectbox("Model", list(MODEL_OPTIONS.keys()))
    ]
    st.session_state.voice_enabled = st.toggle("🔊 Voice replies", value=True)
    st.session_state.call_mode = st.toggle("📞 Call mode", value=False)

    if len(st.session_state.chats) > 1 and st.button("🗑️ Delete this chat"):
        del st.session_state.chats[st.session_state.current_chat]
        st.session_state.current_chat = list(st.session_state.chats.keys())[-1]
        st.rerun()

    st.markdown("---")
    st.markdown(
        '<span class="hebo-badge">Llama 3 · Groq</span>'
        '<span class="hebo-badge">Whisper STT</span>'
        '<span class="hebo-badge">Free</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        "⚠️ Hebo's trading/finance info is educational only — not financial advice. "
        "Always do your own research."
    )

# ----------------------------------------------------------------------
# MAIN AREA
# ----------------------------------------------------------------------
st.title("🤖 Hebo")
st.caption("Your trading, wealth-mindset & coding co-pilot — fast, free, voice-enabled.")

for m in messages[1:]:
    if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
        avatar = "🧑" if m["role"] == "user" else "🤖"
        with st.chat_message(m["role"], avatar=avatar):
            st.markdown(m["content"])

# ----------------------------------------------------------------------
# INPUT AREA — call mode vs normal mode
# ----------------------------------------------------------------------
if st.session_state.call_mode:
    st.markdown(
        '<p class="call-status">📞 Call mode — tap the mic, speak, then pause. '
        'Hebo replies out loud. Tap again for your next turn.</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([2, 1, 2])
    with c2:
        audio_bytes = audio_recorder(
            text="", icon_size="3x", key="call_recorder", pause_threshold=2.0
        )
    if audio_bytes:
        with st.spinner("🎙️ Transcribing..."):
            user_text = transcribe_audio(audio_bytes)
        if user_text and user_text.strip():
            handle_user_message(user_text)
else:
    col1, col2 = st.columns([1, 6])
    with col1:
        st.write("")
        audio_bytes = audio_recorder(text="", icon_size="2x", key="recorder", pause_threshold=2.0)
    with col2:
        text_input = st.chat_input("Message Hebo — trading, mindset, code, anything...")

    user_text = None
    if audio_bytes:
        with st.spinner("🎙️ Transcribing..."):
            user_text = transcribe_audio(audio_bytes)
    if text_input:
        user_text = text_input

    if user_text:
        handle_user_message(user_text)
