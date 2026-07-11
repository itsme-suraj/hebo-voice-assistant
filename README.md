# 🤖 Hebo — AI Voice Assistant

Hebo is a free, fast, voice-enabled AI assistant built with Streamlit. Talk to it or type to
it, and it talks back — with live web search built in so it isn't limited to stale knowledge.

**Why it's free & fast:**
| Part | Tool | Cost |
|---|---|---|
| Brain (LLM) | [Groq](https://console.groq.com) — Llama 3.3 70B | Free tier, extremely fast inference |
| Ears (Speech-to-Text) | Groq Whisper Large v3 Turbo | Free tier |
| Voice (Text-to-Speech) | gTTS (Google Translate TTS) | Free, no key needed |
| Web search tool | DuckDuckGo | Free, no key needed |
| Hosting | Streamlit Community Cloud | Free |

---

## 1. Get your free Groq API key

1. Go to https://console.groq.com/keys
2. Sign up (free) and click **Create API Key**
3. Copy the key — you'll need it below

This is the only key Hebo needs. Everything else (search, TTS) is keyless.

## 2. Run it locally

```bash
git clone https://github.com/YOUR_USERNAME/hebo.git
cd hebo
pip install -r requirements.txt

# add your key
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then open .streamlit/secrets.toml and paste your real GROQ_API_KEY

streamlit run app.py
```

Your browser will open Hebo at `http://localhost:8501`.

## 3. Push to GitHub

```bash
git init
git add .
git commit -m "Hebo: my AI voice assistant"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hebo.git
git push -u origin main
```

`.gitignore` already keeps your real `secrets.toml` (and your API key) out of the repo.

## 4. Deploy on Streamlit Community Cloud (free)

1. Go to https://share.streamlit.io and sign in with GitHub
2. Click **New app**, pick your `hebo` repo, branch `main`, file `app.py`
3. Before deploying (or after, in **Settings → Secrets**), add:
   ```toml
   GROQ_API_KEY = "gsk_your_real_key_here"
   ```
4. Click **Deploy** — Hebo will be live at a public `*.streamlit.app` URL in about a minute

## How it works

- **`app.py`** — the whole app: UI, speech-to-text, the LLM conversation loop, tool-calling
  (web search), and text-to-speech, all in one file for simplicity.
- Conversation history lives in `st.session_state`, so it resets when the browser tab is
  closed/reloaded (add a database later if you want persistent memory across sessions — see
  "Ideas to extend" below).
- Hebo decides on its own when to call the `web_search` tool — e.g. if you ask about today's
  news or a fact it isn't sure about, it will search DuckDuckGo, read the results, and answer
  using them.

## Ideas to extend Hebo

- **Persistent memory**: store `st.session_state.messages` in a small SQLite file or a free
  tier of Supabase/Firebase so Hebo remembers past conversations.
- **More tools**: add a calculator, calendar, weather API, or code execution tool to the
  `TOOLS` list and `AVAILABLE_FUNCTIONS` dict in `app.py` — the pattern is copy-paste.
- **Custom wake word / hands-free mode**: swap `audio_recorder_streamlit` for
  `streamlit-webrtc` for continuous listening.
- **Different voice**: swap `gTTS` for `edge-tts` (free, more natural-sounding voices) if you
  want higher quality speech.
- **Vision**: Groq also serves vision models (e.g. Llama 4 Scout) — let users upload an image
  and have Hebo describe or answer questions about it.

## Troubleshooting

- **"No GROQ_API_KEY found"** — you haven't added the key to `secrets.toml` (local) or the
  Streamlit Cloud secrets panel (deployed).
- **Mic button does nothing** — browsers require HTTPS (or `localhost`) for mic access;
  Streamlit Cloud serves HTTPS automatically, so this only affects unusual local setups.
- **Slow responses** — Groq is normally very fast; if it's slow, check
  https://groqstatus.com for outages.
