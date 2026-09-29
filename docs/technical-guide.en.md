# Realtime Narration Video Technical Guide

English | [日本語](technical-guide.md)

Last updated: September 28, 2026

## 1. Purpose

Realtime Narration Video is a proof-of-concept application that converts streaming responses from an OpenAI-compatible LLM into speech with AivisSpeech, generates approximately five-second clips with LTX-2.5 Audio-to-Video, and plays them in sequence.

The primary metric is latency from user submission until the first video becomes playable. Later videos are generated during playback and should complete before the current five-second clip ends.

## 2. Architecture

| Component | Responsibility |
|---|---|
| FastAPI application | Sessions, streaming orchestration, metrics, and file delivery |
| OpenAI-compatible LLM | Streaming Japanese or English responses with conversation history |
| AivisSpeech Engine | Sentence- and clause-level WAV synthesis |
| diffusers-movie-server Gateway | Exclusive LTX backend management, assets, and generation jobs |
| LTX-2.5 | Video generation from a reference image and audio |
| FFmpeg | Muxing the original TTS audio and extracting speaking-reference frames |
| Browser | SSE updates, preloading speech/idle video, and double-buffered playback |

```text
LLM stream ──→ clause finalized ──→ TTS ──→ audio chunk ──→ LTX ──→ mux ──→ playback
                    ├──── synthesize the next clause concurrently ────┘
                    └──── enqueue subsequent audio ahead of video generation
```

Video jobs are serial on one GPU. The LLM, multiple TTS tasks, and preparation of subsequent audio run concurrently.

## 3. Requirements and startup

- Python 3.11 or newer
- FFmpeg
- Running diffusers-movie-server Gateway
- AivisSpeech Engine
- OpenAI-compatible Chat Completions API

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
PATH="$PWD/.venv/bin:$PATH" ./run.sh
```

Open `http://localhost:8782` in a browser. Default endpoints use localhost. Keep credentials and deployment addresses only in `.env`; never commit them. `GATEWAY_PRESET` defaults to `nvfp4-fast`; use `nvfp4-32gb` when the server is configured for the 32 GB profile. For a GUI hosted on another origin, set comma-separated `CORS_ORIGINS` (default `*`).

## 4. Character registration

`POST /api/sessions` accepts a multipart character image and settings.

| Field | Value |
|---|---|
| `character` | PNG, JPEG, or WebP |
| `character_mode` | `standard` or `photoreal` |
| `lip_sync_mode` | `natural`, `balanced`, `medium`, `medium_strong`, or `strong` |
| `idle_motion_profile` | `closeup`, `upper_body`, or `wide` (default) |
| `idle_liveliness` | `lively` (default) or `calm` |
| `idle_pool_size` | 3–7 (default 5); setup always generates only the first three |
| `turn_anchor_mode` | `speaking` (default) or `idle_frame` |
| `turn_end_mode` | `free` (default) or `return_idle` |
| `camera_lock_enabled` | Border-referenced ECC camera lock (default `false`) |
| `video_seed` / `video_steps` | Seed 0–2147483647 (default 1004); steps 1–12 (default 4) |
| `modality_scale_enabled` | Toggle conversation-time `modality_scale=1.3` for photorealistic mode (default `false`) |
| `ui_language` | `ja` or `en`; controls display text |
| `conversation_language` | `auto`, `ja`, or `en`; controls LLM output and segmentation |
| `video_profile` | Public profile selected in the UI |
| `voice_id` | AivisSpeech speaker ID |
| `target_chunk_seconds` | 3.5–5.0 seconds |
| `startup_buffer_chunks` | Number of playable clips required before playback starts |

Registration asks the Gateway to preload LTX:

```json
{
  "backend": "ltx25",
  "preset": "<GATEWAY_PRESET>",
  "strategy": "coresident"
}
```

This is a no-op when the same configuration is already active. `coresident` keeps other backends such as H3 loaded while adding the LTX weights. Otherwise, model initialization is moved into registration instead of delaying the first conversational generation.

### 4.1 Idle video and speaking anchors for photorealistic characters

The mouth shape in a photorealistic input image strongly constrains generation. A closed-mouth reference can be interpreted as a listening person even when audio is present.

Every mode creates idle video (step 5). Photorealistic mode also prepares speaking anchors (steps 1–4 and 6–7):

1. Synthesize a fixed utterance with AivisSpeech: “Ah. Ah. Ah. Ah.” when `conversation_language=en`, and the Japanese equivalent otherwise.
2. Pad the conditioning WAV with silence to 5.1 seconds.
3. Generate a preparation video at the selected profile's native resolution.
4. Prefer reference quality and successful mouth opening by using eight steps, the UI-selected seed (default 1004), and `modality_scale=1.3`.
5. The idle loop has two switchable modes. Lively (default) joins an outbound clip to an FLF-anchored return to the input image. Calm uses one clip anchored to the input image at both ends. Translation snaps (>5 px/frame) trigger up to three retries with shifted seeds, and the optional border-referenced ECC camera lock can correct visible background drift. The closed-mouth start is saved as `character-neutral.png`. The configured pool size is 3–7 (default 5), but setup always generates only three clips to limit registration time. The browser adds one clip per pool cycle until the target is reached, then rotates the newest N clips; pools of six or seven play in randomized order. Refresh generation pauses in hidden tabs and after five minutes without user input. Idle additions are rejected while any session is generating conversation, and incoming chat/narration interrupts all in-flight idle jobs across sessions.
6. Extract mild and wide articulation frames at 0.12 and 0.75 seconds.
7. Save four progressively stronger articulation reference frames.

Place FFmpeg's `-ss` after the input. Fast seeking before the input can return to the first frame for short MP4 files with sparse keyframes.

The waiting screen shows a seamless idle loop generated during setup. Speaking anchors are only internal LTX inputs. Because they are reused by full-resolution follow-up clips, they are not generated at the reduced startup resolution. This policy applies to all 24 public profiles: anchor preparation uses the selected profile; only the first conversational clip uses its startup profile.

In a 384×512 test, the full-resolution anchor improved facial, mouth, and hair detail over a low-resolution anchor while retaining mouth motion and an approximately 2.6-second first response.

## 5. Conversation pipeline

`POST /api/sessions/{id}/messages` starts a turn:

1. Send conversation history and the system prompt to the LLM.
2. Finalize speakable units at sentence endings, line breaks, colons, and natural Japanese clause boundaries while streaming.
3. Start a TTS task immediately for each unit.
4. Assemble approximately five-second video chunks using actual WAV durations.
5. Pad only the LTX conditioning WAV to video duration plus 0.1 seconds.
6. Preserve audio completion order and enqueue chunks for video generation.
7. After LTX generation, mux the complete original TTS waveform into the final MP4 without truncation.
8. Announce `playable` over SSE so the browser can preload and play it.

Consecutive leading `[video directions]` are removed from spoken text and applied with priority only to that turn's video prompt. `POST /api/sessions/{id}/narrations` bypasses the LLM and sends supplied text through the same TTS → LTX pipeline.

UI and conversation languages are independent. The UI language is stored in browser `localStorage` and survives reloads. `auto` instructs the LLM to answer in the language of the latest user message. English segmentation recognizes periods and word boundaries and uses longer character limits than Japanese. English pronunciation quality in AivisSpeech depends on the selected speaker.

LTX still treats a short first utterance as a five-second video. Its silent tail gives the next job time to finish. Once the next clip is playable, the browser skips the rest of the current clip and advances. When speech exceeds five seconds, the final video frame remains visible while the complete original TTS audio finishes before advancing. This applies at every chunk boundary, not only between the first two clips.

## 6. LTX generation parameters

A typical fast-mode request is:

```json
{
  "backend": "ltx25",
  "mode": "a2v",
  "params": {
    "prompt": "<prompt containing the exact utterance>",
    "width": 288,
    "height": 384,
    "num_frames": 81,
    "fps": 16,
    "steps": 4,
    "guidance_scale": 3.0,
    "seed": 1004
  },
  "extra": {
    "upscale": false,
    "decoder": "vae",
    "audio_start": 0
  },
  "asset_ids": ["<audio ID>", "<image ID>"],
  "auto_load": true,
  "preset": "<GATEWAY_PRESET>"
}
```

Enabling Mouth Motion Emphasis for a photorealistic character adds the following to `extra`:

```json
{"modality_scale": 1.3}
```

### 6.1 Scale caveats

- `modality_scale` affects video prediction and strengthens movement around the mouth.
- `audio_modality_scale` only affects audio prediction. Audio is frozen in A2V, making it a no-op.
- `audio_guidance_scale` is not used for A2V.
- `modality_scale>1.0` adds inference cost.
- The default relies on the speaking anchor and omits scale during conversational generation.

## 7. Steps and resolution

Conversation steps are configurable from 1 to 12 (default 4). The first clip uses `min(4, video_steps)` to protect initial latency; later clips use `video_steps` unchanged. Photorealistic speaking-anchor and idle generation always use eight steps for quality.

| Selected/anchor resolution | First-clip resolution | fps | Frames |
|---|---:|---:|---:|
| 512×384 | 384×288 | 16 | 81 |
| 640×384 | 480×288 | 16 | 81 |
| 576×384 | 480×320 | 16 | 81 |
| 384×512 | 288×384 | 16 | 81 |
| 384×640 | 288×480 | 16 | 81 |
| 416×672 | 320×512 | 16 | 81 |
| 416×704 | 320×544 | 16 | 81 |
| 480×640 | 288×384 | 16 | 81 |
| 480×800 | 352×576 | 16 | 81 |
| 800×480 | 576×352 | 16 | 81 |
| 672×416 | 512×320 | 16 | 81 |
| 704×416 | 544×320 | 16 | 81 |
| 640×480 | 384×288 | 16 | 81 |
| 512×384 | 384×288 | 20 | 97 |
| 416×704 | 320×544 | 20 | 97 |
| 480×640 | 288×384 | 20 | 97 |
| 704×416 | 544×320 | 20 | 97 |
| 640×480 | 384×288 | 20 | 97 |
| 480×320 | 384×256 | 24 | 121 |
| 288×512 | 256×448 | 24 | 121 |
| 384×640 | 288×480 | 24 | 121 |
| 416×704 | 320×544 | 24 | 121 |
| 640×384 | 480×288 | 24 | 121 |
| 704×416 | 544×320 | 24 | 121 |

LTX spatial dimensions must be at least 256 and divisible by 32. Frame counts must satisfy `8n+1`. Duration is `(frames-1)/fps`.

### 7.1 Low-resolution first chunk (the lever that sets conversational responsiveness)

What determines perceived latency is the time from submitting a message to the first video and audio coming out. Every chunk after the first can be generated behind the playback of the previous one, so its generation time is hidden — but **the first chunk has nothing to hide behind**. Its generation time is exactly what the user waits.

So the first chunk of each turn uses a lower resolution in the same aspect family, rounded to multiples of 32 (the "First-clip resolution" column above), together with `min(4, video_steps)`. Generation cost scales roughly with the spatial pixel count, so halving the pixels cuts the first chunk's generation time substantially.

Crucially, **fps and frame count stay exactly as the selected profile defines them**. Keeping the time axis uniform across all chunks means audio sync, chunk concatenation, and player switching never need to know that resolutions differ. Only spatial resolution and steps change.

The paired decision is that **speaking anchors are never low-resolution** (section 4.1). Anchors are re-referenced by every subsequent chunk, so any softness in the anchor propagates into all of them; in practice a low-resolution anchor visibly degraded face, mouth, and hair detail. Anchors therefore always use the selected resolution at eight steps. The disposable first chunk is allowed to be coarse; the anchor everyone references must be high quality.

In real use at 384×512, this configuration delivered the first completed chunk about 2.6 seconds after the message, with roughly 1.5 seconds of playback margin on subsequent chunks (history and measurements in the [development notes](development-notes.en.md)). Detail dips only for the first moment of a turn and returns to the selected resolution from the second chunk on.

## 8. Character modes

| Setting | Reference | Seed | Conversation scale | Intended use |
|---|---|---:|---|---|
| Standard | Previous clip's final frame within a turn | UI-selected + chunk index | None | Illustration/3D and visual continuity |
| Photorealistic/Natural | `character-neutral.png` for every clip | UI-selected (default 1004) | Optional 1.3 | Prefer natural closure |
| Photorealistic/Balanced | `character-speaking-balanced.png` for every clip | UI-selected (default 1004) | Optional 1.3 | Mild opening with reliable motion |
| Photorealistic/Intermediate 1 | `character-speaking-medium.png` for every clip | UI-selected (default 1004) | Optional 1.3 | Moderately stronger than Balanced |
| Photorealistic/Intermediate 2 | `character-speaking-medium-strong.png` for every clip | UI-selected (default 1004) | Optional 1.3 | Closer to the Strong setting |
| Photorealistic/Strong | `character-speaking.png` for every clip | UI-selected (default 1004) | Optional 1.3 | Last-resort articulation strength |

The legacy `fast` value remains accepted for saved-session compatibility and uses the wide anchor without conversation scale.

With turn start set to `idle_frame`, the browser captures the idle frame at submission and uses it as the first clip's reference. With turn end set to `return_idle`, the final clip is FLF-anchored to the original character image. Enabling both prioritizes pose continuity across idle → speech → idle. The defaults, `speaking` / `free`, prioritize articulation and unconstrained motion.

`POST /api/presets` saves a tuned character together with settings, the idle pool, and speaking anchors. `POST /api/presets/{id}/restore` copies those files into a new session, so restoration requires no regeneration. Presets live under `NARRATION_DATA/presets/`.

## 9. Client playback

The browser alternates two video elements:

- Preload the following MP4 during playback.
- When `currentTime` reaches `speech_duration`, always skip the remaining fixed-duration silence.
- If the next clip is pending, show the closed-mouth idle loop until its completion notification arrives.
- Load a newly playable clip into the hidden player.
- Switch immediately on `ended` as a fallback.
- Cover the previous turn with idle video or a captured idle frame at the start of a new turn.
- Predecode idle clips in a second video element and hard-cut at their shared input pose.
- Offer per-chunk MP4 and WAV downloads.
- Store the session ID in `localStorage` and restore state after reload.
- Display the measured player-switch time.

If total follow-up generation remains under five seconds, no inter-video availability gap should occur in principle.

During a conversation turn, the app holds a best-effort Gateway realtime lease (60-second TTL, renewed every 20 seconds) to prevent long H3 jobs from slipping in. Older Gateways without the lease API continue to work with legacy scheduling. If the SSE watcher count remains zero for five seconds, an active turn is automatically cancelled at the next chunk boundary.

## 10. Metrics

Each `session.json` records:

- LLM start, first delta, and completion
- TTS start and audio readiness
- Video start and readiness
- Generation time reported by the server
- Profile, steps, seed, frames, and modality scale
- Speech duration and timeline position

```text
LLM first-token latency = llm_first_delta_at - llm_started_at
TTS duration            = audio_ready_at - tts_started_at
Video processing        = video_ready_at - video_started_at
First-video completion  = first.video_ready_at - llm_started_at
Follow-up headroom       = previous.video_ready_at + previous.duration - next.video_ready_at
```

Positive headroom means the next video completed before the prior five-second clip ended; a negative value is the shortage. Use `scripts/benchmark_resolution.py` for resolution comparisons. Hold the image, audio, prompt, seed, steps, frames, and scale constant, and alternate which variant runs first.

## 11. Representative performance

These are September 4, 2026 warm measurements with a photorealistic character, the 384×512 selected profile, four steps for the first clip, eight for follow-ups, and GPU TTS. The current default also uses four steps for follow-ups; these numbers remain as a regression reference.

| Metric | Run 1 | Run 2 |
|---|---:|---:|
| LLM first delta | 0.115 s | 0.139 s |
| First TTS | 0.231 s | 0.224 s |
| First server generation | 2.170 s | 2.057 s |
| First video completed | 2.734 s | 2.657 s |
| Follow-up server generation | 3.359 s | 3.292 s |
| Follow-up playback headroom | 1.436 s | 1.507 s |

Results vary with GPU load, model state, input image, audio length, and prompt length. Evaluate cold-start and steady-state performance separately. These measurements are observations, not latency guarantees.

## 12. Operational notes

### HTTP 409

An unmanaged backend, an exclusive backend transition, or a conflicting request can cause HTTP 409. Manage LTX/H3 only through the Gateway.

### Cold start

Even when the LTX process exists, the model may load lazily on first generation. Photorealistic character preparation absorbs this cost. Standard mode only requests backend loading, so some configurations can retain a first-generation lazy-load delay.

### AivisSpeech GPU execution

In addition to `--use_gpu`, verify that the ONNX Runtime CUDA Provider can load cuDNN. The API may report CUDA support while missing libraries cause CPU fallback. Confirm that the process appears in `nvidia-smi` and that the CUDA Provider and `libcudnn.so.9` load successfully.

The first synthesis after GPU startup may initialize models. Warm up with one short sentence. Steady-state short-utterance synthesis measured approximately 0.18–0.23 seconds in the development environment.

### A photorealistic mouth does not move

Check, in order:

1. `character-speaking.png` actually shows an open mouth.
2. Conversation requests reference that anchor.
3. The server honors `steps`.
4. Select Strong Lip Motion if Fast mode fails.
5. The audio asset and A2V mode are correct.

### The mouth stays slightly open during silence

This is a side effect of the speaking anchor. The current system prioritizes avoiding closed-mouth speech. Compare Fast and Strong modes, adjust the anchor extraction time, or evaluate silent-tail post-processing if necessary.

## 13. Tests and release hygiene

```bash
.venv/bin/pytest -q
```

Before publishing, verify that `.env`, generated data, real IP addresses, local absolute paths, models, and model weights are not tracked by Git.
