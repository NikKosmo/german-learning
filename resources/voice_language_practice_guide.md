# Voice Practice with LLMs for Language Learning

A guide to setting up free voice conversations with AI for language practice. Private, cost-effective, and customizable.

## What You Get

- 🎤 Voice input (speech-to-text) — processed locally on your device
- 🔊 Voice output (text-to-speech) — browser voices or local TTS
- 🧠 AI responses — local LLM or cloud API
- 🔒 Privacy — your voice never leaves your computer

## Prerequisites

- **Docker Desktop** installed and running
  - [Download for Mac](https://www.docker.com/products/docker-desktop/)
  - [Download for Windows](https://www.docker.com/products/docker-desktop/)
  - [Install on Linux](https://docs.docker.com/engine/install/)

---

# Part 1: Install Open WebUI

## What is Open WebUI?

Open WebUI is a self-hosted web interface for chatting with AI models. Think of it as your own private ChatGPT that runs on your computer.

**Key features for language learning:**
- 🎤 **Voice mode** — speak instead of typing, AI responds with voice
- 🔌 **Works with any LLM** — local (Ollama) or cloud (OpenRouter, OpenAI)
- 🔒 **Runs locally** — your conversations stay on your machine
- 🎨 **Custom personas** — create a language tutor with specific instructions

![Open WebUI Demo](https://raw.githubusercontent.com/open-webui/open-webui/main/demo.gif)

## Install Open WebUI

Open WebUI is the interface for voice conversations. You'll need it regardless of which LLM or TTS option you choose.

```bash
docker run -d \
  -p 3000:8080 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

Wait for the download to complete, then open: **http://localhost:3000**

### First Launch

1. Create a local account (stays on your computer, not cloud)
2. The first user automatically becomes admin

---

# Part 2: Choose Your LLM

Pick one option based on your hardware and preferences:

| Option | Best For | Requirements | Cost |
|--------|----------|--------------|------|
| **A: Local (Ollama)** | Privacy, offline use | 16GB+ RAM, modern CPU/GPU | Free |
| **B: Cloud (OpenRouter)** | Weak hardware, best quality | Internet connection | Free tier available |

---

## Option A: Local LLM with Ollama

Best for: Privacy-conscious users with capable hardware (16GB+ RAM).

### Step 1: Install Ollama

Download from [ollama.com](https://ollama.com/) and install.

### Step 2: Pull a Model

For language practice, Llama 3 8B is a good balance of quality and speed:

```bash
ollama pull llama3.1:8b
```

**Hardware recommendations:**

| Your RAM | Recommended Model | Command |
|----------|-------------------|---------|
| 8GB | Llama 3.2 3B | `ollama pull llama3.2:3b` |
| 16GB | Llama 3.1 8B | `ollama pull llama3.1:8b` |
| 32GB+ | Llama 3.1 70B | `ollama pull llama3.1:70b` |

### Step 3: Connect Open WebUI to Ollama

If Ollama is running on the same machine:

1. Go to **⚙️ Admin Settings** → **Connections**
2. Under **Ollama**, set URL to: `http://host.docker.internal:11434`
3. Click **Save**

Your Ollama models should now appear in the model selector.

---

## Option B: Cloud LLM with OpenRouter

Best for: Users with older/weaker hardware, or those who want access to the best models.

### Step 1: Get OpenRouter API Key

1. Go to [openrouter.ai](https://openrouter.ai/) and create an account
2. Navigate to [API Keys](https://openrouter.ai/settings/keys)
3. Click **Create Key**
4. Copy and save your API key

**Free Tier Limits:**
- 50 requests/day without payment
- 1000 requests/day if you add $10 credit (one-time, pay-as-you-go)

### Step 2: Connect Open WebUI to OpenRouter

1. Go to **⚙️ Admin Settings** → **Connections**
2. Under **OpenAI**, click the **wrench icon** (Manage)
3. Click **➕ Add New Connection**
4. Fill in:
   - **URL:** `https://openrouter.ai/api/v1`
   - **API Key:** paste your OpenRouter key
5. Click **Save**

### Recommended Free Models

| Model | ID | Notes |
|-------|-----|-------|
| Gemma 3 27B | `google/gemma-3-27b-it:free` | German, French, Italian, Spanish, Portuguese |
| Llama 4 Maverick | `meta-llama/llama-4-maverick:free` | 12 languages |
| Qwen 2.5 72B | `qwen/qwen-2.5-72b-instruct:free` | 29+ languages including German |

---

# Part 3: Choose Your TTS (Text-to-Speech)

Pick one option:

| Option | Best For | Quality | Setup |
|--------|----------|---------|-------|
| **A: Browser Voices** | Quick setup | Good | Easy |
| **B: Local TTS (Piper)** | Best quality, offline | Excellent | More steps |

---

## Option A: Browser Voices (Quick Setup)

Uses your browser's built-in text-to-speech. Works immediately, no extra setup.

1. Go to **⚙️ Admin Settings** → **Audio**
2. Set **Text-to-Speech Engine** to `Web API`
3. Under **TTS Voice**, select a voice for your target language:
   - German: `Anna` (local), `Google Deutsch` (cloud)
   - French: `Thomas` (local), `Google Français` (cloud)
   - Spanish: `Monica` (local), `Google Español` (cloud)
4. Click **Save**

> 💡 **More voices in Chrome:** Enable **"Allow non-local voices"** to see additional cloud-based voices (e.g., Google voices). Local voices work offline; cloud voices require internet but may sound more natural.

> ⚠️ **Browser Note:** Chrome works best. Safari may have issues with voice selection.

---

## Option B: Local TTS with OpenedAI-Speech

Higher quality voices, fully local, no cloud dependency.

### Step 1: Choose a Voice

Browse available voices at [Piper samples](https://rhasspy.github.io/piper-samples/). For German, recommended options:

| Voice | Quality | Gender |
|-------|---------|--------|
| `de_DE-thorsten-high` | High | Male |
| `de_DE-eva_k-x_low` | Low | Female |

The example below uses `thorsten-high`. For other voices/languages, find the download URLs at [Piper samples](https://rhasspy.github.io/piper-samples/).

### Step 2: Run OpenedAI-Speech

```bash
docker run -d \
  -p 8000:8000 \
  -v openedai-voices:/app/voices \
  -v openedai-config:/app/config \
  --name openedai-speech \
  --restart unless-stopped \
  ghcr.io/matatonic/openedai-speech-min
```

### Step 3: Download the Voice Model

```bash
docker exec openedai-speech bash -c "cd /app/voices && \
  curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx && \
  curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json"
```

### Step 4: Add Voice to Config

Create the config file:

```bash
cat << 'EOF' > /tmp/voice_to_speaker.yaml
tts-1:
  thorsten:
    model: voices/de_DE-thorsten-high.onnx
    speaker:
  alloy:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 79
  echo:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 134
  fable:
    model: voices/en_GB-northern_english_male-medium.onnx
    speaker:
  onyx:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 159
  nova:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 107
  shimmer:
    model: voices/en_US-libritts_r-medium.onnx
    speaker: 163
EOF
```

Copy to container and restart:

```bash
docker cp /tmp/voice_to_speaker.yaml openedai-speech:/app/config/voice_to_speaker.yaml
docker restart openedai-speech
```

### Step 5: Configure Open WebUI

1. Go to **Admin Settings → Audio**
2. Set **Text-to-Speech Engine** to `OpenAI`
3. Set **API Base URL** to:
   - Mac/Windows: `http://host.docker.internal:8000/v1`
   - Linux: `http://172.17.0.1:8000/v1`
   - Or use your local IP: `http://192.168.x.x:8000/v1`
4. Set **API Key** to `sk-111111111` (dummy key, not checked)
5. Select **thorsten** from the TTS Voice dropdown
6. Click **Save**

---

# Part 4: Create a Language Tutor

Create a custom persona with instructions for language practice.

1. Go to **Workspace** (sidebar) → **Models**
2. Click **➕ Create a Model**
3. Configure:
   - **Name:** `German Tutor` (or your target language)
   - **Base Model:** Select your model (Ollama or OpenRouter)
   - **System Prompt:** (see examples below)
4. Click **Save**

### Example System Prompts

#### Basic Conversation Partner (B1 level)

```
Du bist ein freundlicher deutscher Muttersprachler. Wir unterhalten uns locker über Alltagsthemen.

Regeln:
1. Sprich NUR auf Deutsch — keine englischen Wörter, keine Übersetzungen
2. Halte deine Antworten kurz (1-3 Sätze)
3. Benutze KEINE Emojis oder Sonderzeichen
4. Passe dein Vokabular an das B1-Niveau an
5. Stelle mir eine Frage, um das Gespräch fortzusetzen
```

#### With Corrections (B1 level)

```
Du bist ein Deutschlehrer. Deine Aufgabe ist es, mir beim Sprechen zu helfen.

Regeln:
1. Antworte NUR auf Deutsch — alles auf Deutsch, auch Erklärungen und Korrekturen
2. Halte deine Antworten auf 2-4 Sätze
3. Benutze KEINE Emojis oder Sonderzeichen
4. Passe dein Vokabular an das B1-Niveau an
5. Korrigiere mich NUR bei groben Fehlern — nicht bei jedem Fehler
6. Wenn du korrigierst, mach es kurz und natürlich im Gespräch
7. Stelle eine Folgefrage, um das Gespräch fortzusetzen
```

---

# Part 5: Start Practicing

1. Select your **Language Tutor** model from the dropdown
2. Click the **🎧 headphones icon** (or microphone) to start voice mode
3. Speak in your target language
4. Listen to the AI response
5. Repeat!

### Tips for Effective Practice

- Start with simple topics: weather, daily routine, hobbies
- Don't worry about mistakes — that's how you learn
- Try to respond quickly without overthinking
- Practice for 10-15 minutes daily rather than long sessions

---

# Troubleshooting

### No voices appear in TTS dropdown

- Try using **Chrome** instead of Safari
- Restart the browser completely
- Check system voice settings:
  - **Mac:** System Settings → Accessibility → Spoken Content
  - **Windows:** Settings → Time & Language → Speech

### Models not showing up (OpenRouter)

- Verify your API key is correct
- Check that the URL is exactly `https://openrouter.ai/api/v1`
- Try refreshing the page

### Ollama connection failed

- Make sure Ollama is running: `ollama serve`
- Check the URL: `http://host.docker.internal:11434`
- On Linux, try: `http://172.17.0.1:11434`

### Voice input not working

- Allow microphone access when browser prompts
- Check that no other app is using the microphone
- Try a different browser

### "Rate limit exceeded" error (OpenRouter)

- You've hit the daily free limit (50 or 1000 requests)
- Wait until the next day, or add credit to your OpenRouter account

### Local TTS not working

- Check OpenedAI-Speech is running: `docker ps`
- Verify the API URL uses `host.docker.internal` or your local IP, not `localhost`
- Check logs: `docker logs openedai-speech`

---

# Optional: Access from Phone (same Wi-Fi)

To practice on your phone while at home:

1. Find your computer's local IP:
   - **Mac:** System Settings → Network → Wi-Fi → Details → IP Address
   - **Windows:** `ipconfig` in Command Prompt → look for IPv4
2. On your phone, open: `http://[YOUR-IP]:3000`

---

# Resources

- [Open WebUI Documentation](https://docs.openwebui.com/)
- [Ollama Models](https://ollama.com/library)
- [OpenRouter Models](https://openrouter.ai/models)
- [OpenRouter Free Models](https://openrouter.ai/collections/free-models)
- [Piper Voice Samples](https://rhasspy.github.io/piper-samples/)
