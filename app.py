"""
Hebo — AI Voice Assistant
Free, fast, and deployable on Streamlit Community Cloud.

Stack (all free tiers):
- Brain: Groq (Llama 3.3 70B) — extremely fast inference, free API
- Ears (Speech-to-Text): Groq Whisper Large v3 Turbo
- Mouth (Text-to-Speech): gTTS (Google Translate TTS, free, no key needed)
- Tools: DuckDuckGo web search (free, no key needed)
"""

import base64
import datetime
import io
import json
import os

import streamlit as st
from audio_recorder_streamlit import audio_recorder
from duckduckgo_search import DDGS
from groq import Groq
from gtts import gTTS

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
st.set_page_config(page_title="Hebo — AI Voice Assistant", page_icon="🤖", layout="centered")

GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
LLM_MODEL = "llama-3.3-70b-versatile"
WHISPER_MODEL = "whisper-large-v3-turbo"

if not GROQ_API_KEY:
    st.error(
        "⚠️ No GROQ_API_KEY found.\n\n"
        "Get a **free** key at https://console.groq.com/keys and add it to "
        "`.streamlit/secrets.toml` locally, or in your app's *Settings → Secrets* "
        "once deployed on Streamlit Cloud."
    )
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are Hebo, a helpful, friendly, and highly capable AI voice assistant.
You can hold natural conversations, answer questions, reason through problems, and use tools
(like live web search) when you need current information you don't already know.
Since your replies are often read aloud, keep them natural, warm, and reasonably concise
unless the user asks for something detailed.
Today's date is {date}.
"""

# ----------------------------------------------------------------------
# SESSION STATE
# ----------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(date=datetime.date.today())}
    ]
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True

# ----------------------------------------------------------------------
# TOOLS (this is what makes Hebo an "agent" instead of a plain chatbot)
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
                "Search the live web for current events, facts, prices, or anything "
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
# SPEECH TO TEXT
# ----------------------------------------------------------------------
def transcribe_audio(audio_bytes: bytes) -> str:
    try:
        transcription = client.audio.transcriptions.create(
            file=("audio.wav", audio_bytes),
            model=WHISPER_MODEL,
        )
        return transcription.text
    except Exception as e:
        return f"[Transcription error: {e}]"

# ----------------------------------------------------------------------
# TEXT TO SPEECH
# ----------------------------------------------------------------------
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
        f'<audio autoplay controls src="data:audio/mp3;base64,{b64}"></audio>',
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------
# LLM CALL (with tool-calling loop)
# ----------------------------------------------------------------------
def get_hebo_response(messages):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=1024,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        messages.append(msg)
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            result = AVAILABLE_FUNCTIONS[fn_name](**fn_args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                }
            )
        second_response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return second_response.choices[0].message.content

    return msg.content

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
st.title("🤖 Hebo — Your AI Voice Assistant")
st.caption("Fast, free, and always listening. Powered by Groq + Streamlit.")

with st.sidebar:
    st.header("⚙️ Settings")
    st.session_state.voice_enabled = st.toggle("🔊 Voice replies", value=True)
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = st.session_state.messages[:1]
        st.rerun()
    st.markdown("---")
    st.markdown("**Brain:** Llama 3.3 70B via Groq")
    st.markdown("**Ears:** Whisper Large v3 Turbo via Groq")
    st.markdown("**Voice:** Google TTS (free)")
    st.markdown("**Tools:** Live web search (DuckDuckGo)")

# Render chat history
for m in st.session_state.messages[1:]:
    if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

col1, col2 = st.columns([1, 5])
with col1:
    st.write("")
    audio_bytes = audio_recorder(text="", icon_size="2x", key="recorder")
with col2:
    text_input = st.chat_input("Type a message to Hebo, or use the mic →")

user_text = None
if audio_bytes:
    with st.spinner("🎙️ Transcribing..."):
        user_text = transcribe_audio(audio_bytes)
if text_input:
    user_text = text_input

if user_text:
    with st.chat_message("user"):
        st.markdown(user_text)
    st.session_state.messages.append({"role": "user", "content": user_text})

    with st.chat_message("assistant"):
        with st.spinner("💭 Hebo is thinking..."):
            reply = get_hebo_response(st.session_state.messages)
        st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

        if st.session_state.voice_enabled:
            with st.spinner("🔊 Generating voice..."):
                audio_out = synthesize_speech(reply)
            autoplay_audio(audio_out)
