# Realtime Narration Video Technical Guide

English | [日本語](technical-guide.md)

Last updated: September 4, 2026

## 1. Purpose

Realtime Narration Video is a proof-of-concept application that converts streaming responses from an OpenAI-compatible LLM into speech with AivisSpeech, generates approximately five-second clips with LTX-2.5 Audio-to-Video, and plays them in sequence.

The primary metric is latency from user submission until the first video becomes playable. Later videos are generated during playback and should complete before the current five-second clip ends.

## 2. Architecture

| Component | Responsibility |
|---|---|
| FastAPI application | Sessions, streaming orchestration, metrics, and file delivery |
| OpenAI-compatible LLM | Streaming Japanese responses with conversation history |
| AivisSpeech Engine | Sentence- and clause-level WAV synthesis |
| diffusers-movie-server Gateway | Exclusive LTX backend management, assets, and generation jobs |
| LTX-2.5 | Video generation from a reference image and audio |
| FFmpeg | Muxing the original TTS audio and extracting speaking-reference frames |
| Browser | SSE updates, video preloading, and switching between two video elements |

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
./run.sh
```

Default endpoints use localhost. Keep credentials and deployment addresses only in `.env`; never commit them.

## 4. Character registration

`POST /api/sessions` accepts a multipart character image and settings.

| Field | Value |
|---|---|
| `character` | PNG, JPEG, or WebP |
| `character_mode` | `standard` or `photoreal` |
| `lip_sync_mode` | `fast` or `strong` |
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
  "preset": "nvfp4-fast"
}
```

This is a no-op when the same configuration is already active. Otherwise, model initialization is moved into registration instead of delaying the first conversational generation.

### 4.1 Speaking anchor for photorealistic characters

The mouth shape in a photorealistic input image strongly constrains generation. A closed-mouth reference can be interpreted as a listening person even when audio is present.

Registration therefore performs the following preparation:

1. Synthesize the fixed Japanese utterance “Ah, ah, ah, ah” with AivisSpeech.
2. Pad the conditioning WAV with silence to 5.1 seconds.
3. Generate a preparation video at the selected profile's native resolution.
4. Prefer reference quality and successful mouth opening by using eight steps, the UI-selected seed (default 1004), and `modality_scale=1.3`.
5. Extract the reliably open-mouth frame at 0.75 seconds with FFmpeg.
6. Save it as `character-speaking.png` in the session.

Place FFmpeg's `-ss` after the input. Fast seeking before the input can return to the first frame for short MP4 files with sparse keyframes.

The waiting screen shows the original uploaded image. The speaking anchor is only an internal LTX input. Because it is reused by full-resolution follow-up clips, it is not generated at the reduced startup resolution. This policy applies to all 11 public profiles: anchor preparation uses the selected profile; only the first conversational clip uses its startup profile.

In a 384×512 test, the full-resolution anchor improved facial, mouth, and hair detail over a low-resolution anchor while retaining mouth motion and an approximately 2.6-second first response.

## 5. Conversation pipeline

`POST /api/sessions/{id}/messages` starts a turn:

1. Send conversation history and the system prompt to the LLM.
2. Finalize speakable units from punctuation and character count while streaming.
3. Start a TTS task immediately for each unit.
4. Assemble approximately five-second video chunks using actual WAV durations.
5. Pad only the LTX conditioning WAV to video duration plus 0.1 seconds.
6. Preserve audio completion order and enqueue chunks for video generation.
7. After LTX generation, mux the complete original TTS waveform into the final MP4 without truncation.
8. Announce `playable` over SSE so the browser can preload and play it.

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
  "preset": "nvfp4-fast"
}
```

Strong Lip Motion adds the following to `extra`:

```json
{"modality_scale": 1.3}
```

### 6.1 Scale caveats

- `modality_scale` affects video prediction and strengthens movement around the mouth.
- `audio_modality_scale` only affects audio prediction. Audio is frozen in A2V, making it a no-op.
- `audio_guidance_scale` is not used for A2V.
- `modality_scale>1.0` adds inference cost.
- Fast mode relies on the speaking anchor and omits scale during conversational generation.

## 7. Steps and resolution

The first clip of each turn uses four steps for minimum initial latency. Later clips use eight steps for temporal quality. The server log line `distilled sigma subsample: 4/8 steps` confirms that four steps were applied.

| Selected/anchor resolution (8 steps) | First-clip resolution (4 steps) | fps | Frames |
|---|---:|---:|---:|
| 640×352 | 480×256 | 16 | 81 |
| 512×384 | 384×288 | 16 | 81 |
| 640×384 | 480×288 | 16 | 81 |
| 576×384 | 480×320 | 16 | 81 |
| 384×512 | 288×384 | 16 | 81 |
| 384×640 | 288×480 | 16 | 81 |
| 576×320 | 480×256 | 20 | 97 |
| 512×384 | 384×288 | 20 | 97 |
| 512×288 | 448×256 | 24 | 121 |
| 480×320 | 384×256 | 24 | 121 |
| 288×512 | 256×448 | 24 | 121 |

LTX spatial dimensions must be at least 256 and divisible by 32. Frame counts must satisfy `8n+1`. Duration is `(frames-1)/fps`.

## 8. Character modes

| Setting | Reference | Seed | Conversation scale | Intended use |
|---|---|---:|---|---|
| Standard | Previous clip's final frame within a turn | 1000 + chunk index | None | Illustration/3D and visual continuity |
| Photorealistic/Fast | `character-speaking.png` for every clip | UI-selected (default 1004) | None | Initial latency and continuous playback |
| Photorealistic/Strong Lip Motion | `character-speaking.png` for every clip | UI-selected (default 1004) | 1.3 | Fallback when the mouth does not move |

The speaking anchor can leave the mouth slightly open during silence in photorealistic fast mode. This is a deliberate tradeoff against generating speech with a fully closed mouth.

## 9. Client playback

The browser alternates two video elements:

- Preload the following MP4 during playback.
- When `currentTime` reaches `speech_duration` and the next clip is `playable`, skip the remaining fixed-duration silence.
- If the next clip is pending, continue the current clip and switch when its completion notification arrives.
- Load a newly playable clip into the hidden player.
- Switch immediately on `ended` as a fallback.
- Cover the previous turn with the original character image at the start of a new turn.
- Display the measured player-switch time.

If total follow-up generation remains under five seconds, no inter-video availability gap should occur in principle.

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

Representative warm measurements with a photorealistic character, the 384×512 selected profile, Fast mode, and GPU TTS:

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
