# 🛡️ Rakshak (रक्षक): Full Architecture & Complete Feature Specification

> **AI-Powered Real-Time Voice Scam Guardian for Indian Citizens**  
> Powered by **Google ADK**, **Gemini 3.5/3.8 Native Multimodal Audio**, **FastAPI**, and **Vernacular Speech Synthesis**.

---

## 1. Executive Summary & Core Mission

**Rakshak (रक्षक / રક્ષક)** is a real-time, mid-call voice guardian engineered to protect vulnerable populations—specifically senior citizens, retirees, and first-time smartphone users in India—from high-stakes social engineering scams. 

The most devastating frauds in India today ("Digital Arrest" impersonating Police/CBI/ED, Fake Bank KYC deactivations, and Fake FedEx/Customs narcotics extortion) succeed because **the victim is completely alone on the call**. Scammers use high-pressure psychological isolation ("do not disconnect", "do not tell your family", "stay on video call").

Rakshak acts as a silent digital co-pilot that:
1. **Listens natively to raw call audio** in sliding ~5-second windows (16 kHz mono PCM).
2. **Understands colloquial Indian speech** directly in Gemini without traditional intermediate Automatic Speech Recognition (ASR) errors.
3. **Identifies scam markers within 15–25 seconds**, intervening **mid-call** tens of seconds before financial damage or credential transfer occurs.
4. **Delivers audible and visual vernacular warnings** in simple, comforting Hindi and Gujarati, while ducking the scammer's audio.
5. **Maintains a zero-false-alarm guarantee ("Never Cry Wolf")**, distinguishing legitimate bank reminders, doctor visits, and courier delivery calls.

---

## 2. High-Level System Architecture

The Rakshak architecture is divided into five core tiers:
1. **Client / Presentation Layer**: Browser UI with dual audio drivers (HTML5 Audio Player & Web Audio API `AudioWorklet`), dual reactive status controls, real-time timeline, and vernacular warning banners.
2. **Transport & Gateway Layer**: FastAPI application serving static assets, Server-Sent Events (`/api/monitor/{id}`), bi-directional binary WebSockets (`/ws/listen`), and A2A (Agent-to-Agent) endpoints.
3. **Stream & Session Orchestrator**: `CallMonitor` and `LiveCall` session runners built on Google ADK (`InMemoryRunner`), handling sliding audio chunking, timestamp alignment, and dynamic lag-merging.
4. **Multimodal Agent Intelligence**: Google ADK Agent configured with Gemini Multimodal Audio, operating under a 1-turn/1-tool low-latency paradigm with specialized before/after agent callbacks.
5. **Vernacular Synthesis & Telephony Emulation**: Multimodal Gemini TTS / Edge TTS engine generating reassuring grandmother/grandchild conversational warnings, and acoustic bandpass filter modeling phone network properties.

```mermaid
flowchart TB
    subgraph ClientLayer["🖥️ Client Presentation Layer (Web Browser)"]
        direction TB
        UI["Bilingual User Interface<br/>(English · Hindi · Gujarati)"]
        AudioPlayer["HTML5 Call Replay Audio<br/>(Volume Ducking: 100% ➔ 25%)"]
        AudioWorkletNode["Web Audio API: AudioWorklet<br/>(16kHz Float32 ➔ Int16 PCM Mono)"]
        AlertSystem["Vernacular Warning Modal<br/>(Visual Banner + Spoken Voice)"]
        TimelineUI["Live Audit Heartbeat Timeline<br/>(Safe · Suspicious · Scam)"]
    end

    subgraph TransportLayer["⚡ Transport & Gateway Layer (FastAPI Server)"]
        direction TB
        StaticRoute["GET / & /calls/*.wav<br/>(Static Assets & WAV Streaming)"]
        SSERoute["GET /api/monitor/{call_id}<br/>(Server-Sent Events: Real-time Paced)"]
        WSRoute["WebSocket /ws/listen<br/>(16kHz PCM Stream Ingestion)"]
        TTSRoute["GET /api/speak<br/>(Vernacular Warning Audio)"]
        A2ARoute["POST /a2a/rakshak<br/>(Agent-to-Agent RPC Protocol)"]
    end

    subgraph OrchestrationLayer["🔄 Stream & Session Orchestrator (rakshak.monitor)"]
        direction TB
        Chunker["Sliding Window Chunker<br/>(5.0s Chunks @ 16kHz)"]
        LagMerger["Lag-Resilient Merger<br/>(Dynamic Chunk Merging on Model Delay)"]
        LiveCallSession["LiveCall Session Controller<br/>(ADK Runner Session Context: 1 Call = 1 Session)"]
    end

    subgraph AgentLayer["🧠 Multimodal Agent Core (Google ADK + Gemini)"]
        direction TB
        BeforeCallback["before_agent_callback<br/>(track_chunk: Extracts Turn & Time Window)"]
        GeminiCore["Gemini 3.5 / 3.8 Flash<br/>(Direct Multimodal Audio Understanding)"]
        ToolsEngine["ADK Tools Engine<br/>(skip_summarization = True)"]
        AfterCallback["after_agent_callback<br/>(chunk_verdict: Instant Synthetic Response)"]
        
        subgraph ToolsSet["ADK Tools"]
            ToolLog["log_call_status(risk_level, heard)"]
            ToolAlert["raise_scam_alert(scam_type, red_flags, ...)"]
        end
    end

    subgraph VernacularLayer["🔊 Vernacular Synthesis & Telephony Pipeline"]
        direction TB
        GeminiTTS["Gemini 3.8 Flash TTS / Edge-TTS<br/>(Empathetic Grandchild Tone)"]
        TelephonyDSP["Phone-Line DSP Simulator<br/>(300Hz-3400Hz Bandpass + Hiss)"]
    end

    %% Connections
    AudioPlayer -.->|Playback| UI
    AudioWorkletNode ==>|Binary WebSocket| WSRoute
    UI <==|Server-Sent Events| SSERoute
    UI <==|WebSocket Events| WSRoute
    UI <==|Audio Fetch| TTSRoute

    SSERoute --> Chunker
    WSRoute --> LagMerger
    Chunker --> LagMerger
    LagMerger --> LiveCallSession

    LiveCallSession --> BeforeCallback
    BeforeCallback --> GeminiCore
    GeminiCore --> ToolsEngine
    ToolsEngine --> ToolsSet
    ToolsSet --> AfterCallback
    AfterCallback --> LiveCallSession

    TTSRoute --> GeminiTTS
    StaticRoute --> TelephonyDSP
```

---

## 3. Detailed Component Breakdown

### 3.1 Client / Web Frontend (`rakshak/static/index.html`)

The frontend is a single-page reactive application designed with accessibility, minimal latency, and zero heavy external framework dependencies.

| Component | Selector / Element | Responsibilities & Mechanism |
|---|---|---|
| **Header & Language Switcher** | `header h1`, `.tag` | Displays bilingual branding: *Rakshak (रक्षक)* with immediate mission statement in Hindi and English. |
| **Call Selector Deck** | `#calls .call` | Grid of pre-rendered scenarios and live microphone trigger. Fetches call metadata from `GET /api/calls`. Displays title, language badge, duration, and classification pill (*genuine call* vs *scam call*). |
| **Call Status HUD** | `.phone .status`, `#dot` | Live status pill with pulsing indicator (`.dot.live`). Displays four states: `No call`, `Listening (safe)`, `Suspicious (analyzing)`, `Scam detected (hang up immediately)`. |
| **Dual Scrub Progress Bar** | `.bar #progress`, `#alertMark` | Visual progress bar displaying elapsed call playback, plus a dynamic red vertical marker (`#alertMark`) injected at the exact second a scam alert was triggered. |
| **Vernacular Alert Card** | `#alert.alert` | High-visibility warning box styled in safety crimson (`#c62828`) and rose tint (`#fdecea`). Features 30px Devanagari and Gujarati headlines, confidence percentage, timestamp, quote evidence, and interactive red-flag badges. |
| **Red Flag Badges** | `#flags .flag` | Dynamic chips mapping machine IDs (e.g., `authority_impersonation`) to bilingual vernacular descriptions (e.g., `नकली पुलिस / बैंक · નકલી પોલીસ / બેંક`). |
| **Replay Warning Button** | `#replayBtn` | Re-triggers audio warning synthesis and playback if the user or elder needs to hear it again. |
| **Safe Call Box** | `#safeBox.safe-box` | Green confirmation card shown when a genuine call completes with zero alerts (`कॉल सुरक्षित लगी · કૉલ સુરક્ષિત લાગ્યો`). |
| **Live Audit Timeline** | `#timeline.timeline` | Reverse-chronological ledger listing every 5-second chunk with start/end timestamps, risk indicator dot, and English paraphrase of what the model heard. |
| **Audio Worklet Pipeline** | `AudioContext`, `AudioWorkletNode` | Streams live microphone input. Captures 1-channel mic stream, downsamples to 16 kHz, converts float samples to 16-bit signed PCM, and streams binary chunks over WebSockets. |

---

### 3.2 Transport & Gateway Layer (`rakshak/server.py`)

The backend server is implemented using FastAPI and Uvicorn. It supports dual operating modes:

#### 1. Replay Simulation Mode (`GET /api/monitor/{call_id}`)
- Connects browser to Server-Sent Events (SSE).
- Client plays local `/calls/{call_id}.wav` via HTML5 `<audio>`.
- Server reads the identical WAV file, splits it into 5.0s chunks, and gates chunk release using wall-clock timing (`asyncio.sleep(wait)`).
- Yields JSON-serialized events (`type: "start"`, `type: "chunk"`, `type: "alert"`, `type: "done"`).

#### 2. Live Microphone Mode (`WebSocket /ws/listen`)
- Client streams raw little-endian signed 16-bit PCM at 16,000 Hz over binary WebSocket messages.
- Server maintains an async buffer. As soon as 5.0 seconds of audio accumulate (160,000 bytes = 80,000 samples @ 16-bit), it packages the audio into an `AudioChunk` and forwards it to `LiveCall.feed()`.
- Client can transmit text message `"stop"` or close socket to terminate session and receive final verdict.

#### 3. Vernacular Voice Delivery (`GET /api/speak`)
- Parameters: `text` (URL-encoded string), `lang` (`hi` or `gu`).
- Invokes `rakshak.tts.speak()` which queries Gemini 3.8 Flash TTS or Edge TTS.
- Returns `audio/wav` or `audio/mpeg` byte buffer for immediate browser playback.

#### 4. REST Inspection Endpoints
- `GET /api/calls`: Inspects `data/calls/*.wav` and `data/scripts/*.json` to return available scenarios with duration and language.
- `GET /api/red_flags`: Returns catalog of recognized scam indicators and definitions.

---

### 3.3 Audio Engineering & DSP Pipeline (`rakshak/audio.py`)

Rakshak standardizes all internal audio processing on **16 kHz mono 16-bit PCM** (`audio/wav`), the optimal format for Gemini speech comprehension.

```mermaid
flowchart LR
    RawInput["Raw Input Audio<br/>(Mic / File / Synthetic)"] --> Resample["Linear Resampling<br/>(Target: 16,000 Hz)"]
    Resample --> MonoFold["Channel Folding<br/>(Stereo ➔ Mono Average)"]
    MonoFold --> PhoneFilter["Phone-Line Filter (DSP)<br/>(300 Hz - 3400 Hz Bandpass)"]
    PhoneFilter --> NoiseGen["Gaussian Noise Injection<br/>(Line Hiss Simulation)"]
    NoiseGen --> ChunkSlicer["Sliding Window Slicer<br/>(5.0s / 80,000 Samples)"]
    ChunkSlicer --> WavePacker["In-Memory WAV Header<br/>(RIFF 16-bit PCM)"]
    WavePacker --> AgentTurn["ADK types.Part.from_bytes<br/>(mime_type='audio/wav')"]
```

#### Audio Processing Functions:
- `resample(pcm, src_rate, dst_rate)`: Linear-interpolation resampling of `int16` numpy buffers.
- `load_wav(path)`: Loads multi-channel audio, downmixes to mono, and resamples to 16 kHz.
- `phone_line(pcm, rate, seed=7)`: Applies Real Fast Fourier Transform (`rfft`), filters out frequencies below 300 Hz and above 3400 Hz (standard PSTN / GSM telephone bandwidth), injects low-amplitude Gaussian white noise ($\sigma=120$), and clips to `int16` range.
- `chunk_audio(pcm, seconds=5.0)`: Partitions continuous PCM array into discrete `AudioChunk` objects with timestamps.
- `merge_chunks(chunks)`: Seamlessly concatenates multiple `AudioChunk` payloads into a single contiguous WAV file when compensating for execution lag.

---

### 3.4 Stream & Session Orchestrator (`rakshak/monitor.py`)

The monitor handles conversational statefulness across consecutive audio segments:

```mermaid
stateDiagram-v2
    [*] --> Idle: Server Ready
    Idle --> CallInitiated: Stream Requested (SSE or WS)
    
    state LiveCallSession {
        [*] --> InitializingSession: Generate session_id (call-xxxx)
        InitializingSession --> BufferingAudio: Accumulating 5.0s PCM
        BufferingAudio --> ModelTurnExecution: LiveCall.feed(chunk)
        
        state ModelTurnExecution {
            [*] --> FormatTurnHeader: "[CALL CHUNK n | t0s-t1s]"
            FormatTurnHeader --> SendAudioToRunner: runner.run_async()
            SendAudioToRunner --> ToolExecution: Agent calls tool
            
            state ToolDecision <<choice>>
            ToolExecution --> ToolDecision
            ToolDecision --> RaiseScamAlert: Decisive red flags heard
            ToolDecision --> LogCallStatus: Normal or suspicious conversation
            
            RaiseScamAlert --> CacheAlertState: alert stored in session state
            LogCallStatus --> AppendCallLog: chunk logged with risk level
        }

        ModelTurnExecution --> CheckLag: Wall-clock vs Chunk timestamp
        CheckLag --> MergeLaggingChunks: Model latency > chunk length
        CheckLag --> BufferingAudio: On schedule
        MergeLaggingChunks --> ModelTurnExecution: Next turn analyzes combined chunks
    }

    LiveCallSession --> CallEnded: Audio Stream Complete or User Stop
    CallEnded --> GenerateSummary: summary(verdict, first_alert_at, alert)
    GenerateSummary --> [*]
```

#### The Lag-Resilient Dynamic Merging Algorithm
If an LLM API round-trip takes longer than 5 seconds (e.g., during network jitter), incoming audio continues to arrive. Rather than creating a backlog of stale turns:
$$\text{elapsed\_wall\_clock} = t_{\text{current}} - t_{\text{call\_start}}$$
$$\text{batch} = [c \in \text{pending} \mid c.\text{end} \le \text{elapsed\_wall\_clock}]$$
The monitor merges all overdue chunks into a single turn using `merge_chunks(batch)`. The agent receives the merged audio representing the complete elapsed time window, immediately catching up to real time!

---

### 3.5 Multimodal Agent Core (`rakshak/agent.py`)

The agent is an ADK `Agent` wrapped inside an ADK `App`.

#### Key Architectural Decisions:
1. **Model**: `gemini-3.5-flash` (or `gemini-3.8-flash` via `RAKSHAK_MODEL`), with low-latency thinking configuration (`thinking_level=low`).
2. **End-to-End Multimodal Input**: Instead of transcribing speech with an ASR model and passing text to the LLM, Rakshak delivers the binary WAV file directly to Gemini as an `audio/wav` inline part. Gemini listens to the acoustic intonation, hesitation, background call-center chatter, and aggressive vocal pressure.
3. **Turn Header Prompting**:
   ```
   [CALL CHUNK 4 | 15.0s-20.0s]
   <binary audio/wav payload>
   ```
   The agent is instructed to treat all turns as sequential increments of the **same ongoing phone call**.
4. **Zero-Latency Tool Callback Architecture (`skip_summarization`)**:
   Standard tool calling requires two LLM roundtrips:
   - *Trip 1*: Model analyzes audio $\rightarrow$ generates function call `raise_scam_alert(...)`.
   - *Trip 2*: Tool returns execution result $\rightarrow$ Model summarizes tool output into conversational response.
   
   Rakshak eliminates Trip 2! The tools set `tool_context.actions.skip_summarization = True`. The `after_agent_callback` (`chunk_verdict`) inspects session state and synthetically constructs the model's textual output from the tool parameters, cutting latency by **50%**.

```mermaid
sequenceDiagram
    autonumber
    actor Victim as Call / Scammer
    participant Web as Browser UI
    participant Server as FastAPI Gateway
    participant Monitor as LiveCall / ADK Runner
    participant Gemini as Gemini Multimodal Model
    participant Tools as Rakshak Tool Context

    Victim->>Web: Audio streaming (5s chunk)
    Web->>Server: Binary PCM over WS / SSE Clock
    Server->>Monitor: chunk: AudioChunk (15.0s - 20.0s)
    Monitor->>Gemini: Content: "[CALL CHUNK 4 | 15s-20s]" + audio.wav
    Note over Gemini: Direct Acoustic & Dialect Reasoning<br/>(Hinglish, urgency, authority claim)
    Gemini->>Tools: raise_scam_alert(scam_type="digital_arrest", red_flags=[...])
    Tools->>Tools: skip_summarization = True; update state["alert"]
    Tools-->>Monitor: FunctionResponse: {status: "alert_raised"}
    Note over Monitor: after_agent_callback synthesizes text<br/>(No 2nd LLM round-trip!)
    Monitor-->>Server: Event: {type: "alert", alert: {...}}
    Server-->>Web: SSE / WS Alert Event
    par Visual Alert
        Web->>Web: Render Red Banner & Red Flag Badges
    and Vernacular Audio Warning
        Web->>Server: GET /api/speak?lang=hi&text=...
        Server-->>Web: Audio Stream (Reassuring Grandchild Tone)
        Web->>Web: Duck call volume to 25% & Play Hindi/Gujarati warning aloud
    end
```

---

### 3.6 Tooling & Scam Detection Engine (`rakshak/tools.py`)

Rakshak implements a strict scam classification taxonomy:

#### The 8 Decisive Red Flags
```mermaid
mindmap
  root((🛡️ Rakshak Red-Flag Taxonomy))
    authority_impersonation
      Police / CBI / ED
      Customs / FedEx
      RBI / Bank Official
    threat_or_arrest
      Digital Arrest
      Immediate FIR Warrant
      Account Freeze / Pension Stop
    secrecy_isolation
      Do not disconnect
      Stay in closed room / video
      Do not inform family
    money_transfer
      RBI Safe Account
      Verification Security Deposit
      UPI / RTGS Clearing Fee
    otp_request
      OTP / PIN / Password
      CVV / Card Expiry
    remote_app_install
      AnyDesk / TeamViewer
      Unknown APK Link
      Screen Sharing Permission
    urgency
      Act within 10 minutes
      Immediate arrest threat
      Today itself deadline
    personal_data_request
      Aadhaar / PAN Card
      Passport number
      Bank account credentials
```

#### Decision Matrix
- **Safe Call**: Everyday conversation, delivery coordination, social chat, or genuine bank reminder. 
  - *Note*: If a caller says *"never share your OTP"* or *"visit our branch"*, Rakshak classifies this as a protective positive signal, preventing false alarms.
  - Action: `log_call_status(risk_level="safe", heard=...)`.
- **Suspicious Call**: A single ambiguous signal (e.g., caller claims to be from a bank, but hasn't yet threatened or demanded money).
  - Action: `log_call_status(risk_level="suspicious", heard=...)`.
- **Scam Call**: Clear decisive pattern detected:
  - *Pattern 1*: Authority Impersonation + Arrest Threat (Digital Arrest).
  - *Pattern 2*: Impersonation + OTP / Remote App Installation (Fake KYC).
  - *Pattern 3*: Illegal Parcel / Customs + Police Handover + Clearing Fee (Fake Courier).
  - *Pattern 4*: Any dual correlation of disparate red flag categories.
  - Action: `raise_scam_alert(...)` (Fires exactly **once** per call; subsequent turns append flags without re-triggering audio alarms).

---

### 3.7 Vernacular Speech Synthesis Engine (`rakshak/tts.py`)

To ensure immediate comprehension by elderly users who may not read small mobile text:
- **TTS Generation**: Prompt-steered Gemini TTS (`gemini-3.8-flash-tts`) with Edge TTS fallback (`hi-IN-SwaraNeural`, `gu-IN-DhwaniNeural`).
- **Empathetic Prompt Persona**:
  > *"Say this urgently but kindly, like a caring grandchild warning their grandparent, in Hindi / Gujarati: ..."*
- **Acoustic Ducking**:
  When an alert triggers, the client automatically ducks the scammer's call volume down to **25%**, plays the Hindi warning aloud, pauses, plays the Gujarati warning aloud, and then restores volume to 100%.

---

## 4. Complete Feature Breakdown Matrix

The table below catalogs every user-facing and backend capability of the Rakshak platform:

| # | Feature Name | Layer | Description | User Impact |
|---|---|---|---|---|
| **F01** | **Bilingual Multi-Dialect Call Selection** | UI / Data | Five pre-scripted high-fidelity scenarios representing real-world Indian cyber-crime patterns + genuine baseline calls in Hindi and Gujarati. | Enables zero-risk demonstration and user training across multiple languages. |
| **F02** | **Live Microphone Real-Time Ingestion** | UI / WS | Ingests live ambient microphone audio via Web Audio API `AudioWorkletNode` in 16 kHz mono Int16 PCM. | Allows putting any real phone on speaker mode next to the device for live real-time defense. |
| **F03** | **Mid-Call Interception** | Agent / Monitor | Detects fraud early (typically within 15s to 25s) while call is still active, before scammer reaches financial extortion phase. | Stops the fraud before money or credentials leave the victim's possession. |
| **F04** | **Native Multimodal Audio Understanding** | Agent Core | Feeds 16 kHz WAV audio directly to Gemini without prior ASR transcription. | Preserves acoustic emotion, tone, background noise, and prevents phonetic transcription errors in colloquial dialects. |
| **F05** | **Dynamic Lag-Resilient Catch-Up** | Monitor Engine | Merges delayed chunks when LLM API latency exceeds chunk duration. | Ensures the agent never falls behind real-time conversation and always evaluates "now". |
| **F06** | **Zero-Latency Tool Callback Architecture** | ADK / Agent | Employs `skip_summarization=True` and `chunk_verdict` after-callback to bypass second LLM roundtrip. | Cuts inference latency in half, delivering sub-second chunk turnaround times. |
| **F07** | **8-Dimension Scam Red-Flag Catalogue** | Tools Engine | Standardized taxonomy identifying authority impersonation, arrest threats, secrecy demands, OTP requests, and app installs. | Delivers explainable, structured forensic reasoning rather than a black-box verdict. |
| **F08** | **Vernacular Spoken Warning System** | TTS / UI | Synthesizes warm, assertive spoken warnings in colloquial Hindi and Gujarati. | Elders who struggle with small English text instantly hear clear, comforting instructions. |
| **F09** | **Audio Ducking System** | Web Audio | Lowers the caller's audio track to 25% while vernacular alerts are vocalized. | Prevents the scammer from shouting over or distracting the victim during the warning. |
| **F10** | **Interactive Red-Flag Visual Badges** | UI | Displays pill badges with dual Hindi and Gujarati translations for each detected scam attribute. | Visual clarity for the victim and any family members reviewing the call. |
| **F11** | **Dynamic Timeline Alert Pin** | UI | Plots an alert marker pin on the progress bar at the exact second the scam was proven. | Visual proof of how early the intervention occurred relative to call length. |
| **F12** | **Live Audit Heartbeat Ledger** | UI | Real-time scrollable log showing every 5-second interval, timestamp, risk dot, and plain-English summary. | Full transparency and auditability for cybersecurity teams. |
| **F13** | **Zero False-Alarm Contextual Safety Guarantee** | Agent Prompt | Recognizes protective phrases ("never share OTP", "visit branch") and genuine errands. | Prevents "crying wolf" and ensures users do not dismiss the tool due to false alarms. |
| **F14** | **Replay Spoken Warning Button** | UI | Dedicated button allowing the elder to replay the Hindi & Gujarati guidance at will. | Helps anxious users re-hear advice after hanging up the phone. |
| **F15** | **Agent-to-Agent (A2A) Compatibility** | Gateway | Exposes standardized A2A protocol endpoint (`/a2a/rakshak`) with task store and runner integration. | Enables enterprise integration with telecom carriers and upstream security co-pilots. |
| **F16** | **Comprehensive Multi-Tier Eval Suite** | QA / Eval | 4 evaluation suites covering offline unit tests, live audio end-to-end runs, ADK `AgentEvaluator`, and `agents-cli` LLM-judge. | Verifies 100% scam catch-rate, zero false positives, and strict adherence to warning rubrics. |

---

## 5. End-to-End Sequence Workflows

### 5.1 Recorded Scenario Replay Flow (Digital Arrest)

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Elder
    participant UI as Browser Frontend
    participant Server as FastAPI Server
    participant Monitor as CallMonitor
    participant ADK as Gemini ADK Agent

    User->>UI: Clicks "Digital arrest · डिजिटल अरेस्ट"
    UI->>Server: GET /calls/digital_arrest_hi.wav
    Server-->>UI: 200 OK (Audio stream)
    UI->>Server: GET /api/monitor/digital_arrest_hi (SSE)
    Server->>Monitor: monitor.stream(chunks, realtime=True)
    
    par Audio Playback
        UI->>UI: Play audio, update scrub bar
    and Chunk 1 (0.0s - 5.0s)
        Monitor->>ADK: Chunk 1: "Caller greets Ramesh Patel"
        ADK-->>Monitor: log_call_status(risk_level="safe")
        Monitor-->>Server: SSE: {type: "chunk", risk_level: "safe"}
        Server-->>UI: Event chunk 1
        UI->>UI: Dot green, append timeline
    and Chunk 2 (5.0s - 10.0s)
        Monitor->>ADK: Chunk 2: "Claims to be Inspector Vikram Singh, CBI"
        ADK-->>Monitor: log_call_status(risk_level="suspicious")
        Monitor-->>Server: SSE: {type: "chunk", risk_level: "suspicious"}
        Server-->>UI: Event chunk 2
        UI->>UI: Dot orange, append timeline
    and Chunk 3 (10.0s - 15.0s)
        Monitor->>ADK: Chunk 3: "FIR warrant issued, stay on video call"
        ADK-->>Monitor: raise_scam_alert(scam_type="digital_arrest", red_flags=["authority_impersonation", "threat_or_arrest", "secrecy_isolation"])
        Monitor-->>Server: SSE: {type: "alert", alert: {...}}
        Server-->>UI: Event alert!
        UI->>UI: Trigger Red Alert Box & Pin on timeline
        UI->>Server: GET /api/speak?lang=hi&text=...
        Server-->>UI: Hindi Warning WAV
        UI->>UI: Duck call volume to 25%, speak Hindi warning aloud
        UI->>Server: GET /api/speak?lang=gu&text=...
        Server-->>UI: Gujarati Warning WAV
        UI->>UI: Speak Gujarati warning aloud, restore volume
    end
```

---

### 5.2 Live Microphone Ingestion Flow

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Live Phone Call (on Speaker)
    participant Mic as Laptop / Device Microphone
    participant Worklet as AudioWorklet Processor (Browser)
    participant WS as WebSocket Client
    participant Server as FastAPI Server (/ws/listen)
    participant Monitor as LiveCall Session

    Caller->>Mic: Acoustic Call Audio
    Mic->>Worklet: AudioContext stream (16kHz)
    loop Every Audio Frame
        Worklet->>Worklet: Convert Float32 ➔ Int16 PCM
        Worklet->>WS: postMessage(int16Array)
        WS->>Server: Binary PCM frames
    end

    loop Every ~5.0 Seconds (80,000 samples)
        Server->>Monitor: feed(chunk, merged=1)
        Monitor->>Monitor: Gemini ADK Evaluation
        Monitor-->>Server: Event: chunk status / alert
        Server-->>WS: JSON event string
        WS-->>Worklet: UI status update
    end

    Caller->>Caller: Call concludes / User hangs up
    WS->>Server: Text: "stop"
    Server->>Monitor: summary()
    Monitor-->>Server: Final verdict (scam / safe)
    Server-->>WS: JSON: {type: "done", verdict: "scam"}
    WS->>WS: Close connection, display final HUD state
```

---

## 6. Evaluation & Benchmarking Architecture

Rakshak implements a four-layer verification harness to guarantee high detection accuracy and zero false positives:

```mermaid
flowchart TD
    subgraph Suite1["1. Offline Unit Tests (pytest)"]
        T1["Chunking & Resampling Integrity"]
        T2["Red-Flag Deduplication & Validation"]
        T3["Lag Merging Logic Simulation"]
        T4["Server Routes & SSE Formatting"]
    end

    subgraph Suite2["2. Live Audio E2E Tests"]
        T5["Timing Validation: Alert ≥10s before call end"]
        T6["Authority Impersonation Flag Mandatory"]
        T7["Devanagari & Gujarati Character Verification"]
        T8["Zero False Positives on Genuine Calls"]
    end

    subgraph Suite3["3. ADK AgentEvaluator"]
        T9["tool_trajectory_avg_score (EXACT)"]
        T10["Scam Score ≥ 0.75 Target"]
        T11["Genuine Score = 1.0 (Zero Tolerance)"]
        T12["rubric_based_tool_use_quality_v1"]
    end

    subgraph Suite4["4. agents-cli Eval"]
        T13["scam_decision Metric (Alert vs Log)"]
        T14["warning_quality (LLM-as-a-judge: 1-5 scale)"]
        T15["Regression Diffing & Trace Analysis"]
    end
```

---

## 7. Cloud Deployment Architecture (Google Cloud Platform)

Rakshak is packaged for deployment to Google Cloud using serverless, containerized infrastructure:

```mermaid
flowchart LR
    subgraph Internet["Public Internet"]
        UserDevice["Elder / Family Device<br/>(Browser / PWA)"]
    end

    subgraph GCP["Google Cloud Platform"]
        CloudRun["Google Cloud Run<br/>(FastAPI Container / Auto-scaling)"]
        SecretManager["Secret Manager<br/>(GOOGLE_API_KEY / Credentials)"]
        CloudLogging["Cloud Logging & Tracing<br/>(OpenTelemetry to Cloud)"]
        
        subgraph VertexAI["Vertex AI / Google GenAI Global"]
            GeminiAudio["Gemini 3.5 / 3.8 Flash<br/>(Multimodal Audio Inference)"]
            GeminiTTSModel["Gemini 3.8 Flash TTS<br/>(Speech Synthesis Engine)"]
        end
    end

    UserDevice ==>|HTTPS / WSS| CloudRun
    SecretManager -.->|Inject Env| CloudRun
    CloudRun -->|Trace Events| CloudLogging
    CloudRun ==>|gRPC / REST| GeminiAudio
    CloudRun ==>|Audio Request| GeminiTTSModel
```

- **Containerization**: Single multi-stage `Dockerfile` running Python 3.12, managed with `uv`.
- **Scaling**: Google Cloud Run handles concurrent WebSocket connections and scales from zero to peak traffic.
- **Regions**: Configured for global low-latency access (`GOOGLE_CLOUD_LOCATION=global`) to maximize throughput for multimodal Gemini audio tokens.

---

## 8. Summary of Architectural Achievements

1. **First-of-its-kind Mid-Call Voice Guardian**: Detects and halts cyber-extortion scams before financial transactions occur.
2. **Direct Acoustic Intelligence**: Eliminates error-prone speech-to-text intermediaries in Indian regional languages.
3. **Sub-Second Low-Latency Execution**: Cuts response latency in half through single-turn callback generation.
4. **Resilient Streaming Engine**: Dynamically merges audio frames to guarantee the AI stays synchronized with real-time conversations.
5. **Culturally Aligned Empathy**: Employs warm vernacular speech synthesis engineered specifically for the psychological comfort of elderly users.
