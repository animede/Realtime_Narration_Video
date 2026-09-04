# Development History and Measurement Record

English | [日本語](development-notes.md)

Last updated: September 4, 2026

This document records the experiments and decisions made while improving response latency, continuous playback, and mouth motion for photorealistic characters. All numbers are observations from the development environment and vary with GPU load, backend state, input image, utterance, and TTS load.

## 1. Pipeline under test

1. Receive a streaming response from an OpenAI-compatible LLM.
2. Finalize clauses during reception and run TTS tasks concurrently.
3. Send completed WAV files to LTX-2.5 Audio-to-Video.
4. Continue synthesizing later clauses while video generation runs.
5. Replace LTX-generated audio with the original TTS audio.
6. Preload completed videos in the browser and play them in order.

The LLM and TTS are fast enough that LTX video generation is the main wait. Video jobs are effectively serial on one GPU.

## 2. Initial timeline

The initial representative run used input “Good morning,” produced two chunks, and used 384×512, 16 fps, 81 frames, and the equivalent of eight steps.

| Elapsed | Event |
|---:|---|
| 0.000 s | LLM started |
| 0.291 s | First LLM text received |
| 0.319 s | First TTS started |
| 0.426 s | Second TTS started |
| 0.442 s | LLM response completed |
| 1.282 s | First audio completed |
| 1.283 s | First video generation started |
| 2.758 s | Second audio completed |
| 5.239 s | First video completed |
| 9.248 s | Second video completed |

The second video completed approximately 0.99 seconds before first-video playback would end. LLM reception and TTS were already concurrent; video generation was the bottleneck.

## 3. Latency improvements

### 3.1 Streaming segmentation

The first implementation waited for a Japanese full stop, delaying TTS for long responses. The stream chunker was changed to finalize clauses from punctuation and character count while the response is arriving.

Naive character-count splitting created several problems:

- isolating a short question ending, equivalent to “can｜you?”
- splitting Japanese verb inflections
- breaking semantic units such as “try checking｜the forecast”
- inserting the silent remainder of a five-second clip before the continuation

The current chunker favors punctuation, waits until roughly 22–26 Japanese characters where appropriate, and protects common inflectional endings such as forms corresponding to “is doing,” “will do,” “is done,” and “can you.”

Immediately emitting an introductory comma clause improves first response but can leave a long pause before its semantic continuation. Waiting improves rhythm but delays first speech. This remains an explicit latency/naturalness tradeoff.

### 3.2 Concurrent TTS

TTS starts for every finalized unit without waiting for the complete LLM response. Multiple TTS tasks run concurrently and prepare subsequent audio during video generation.

Passing a short WAV directly to LTX caused audio-range errors. Only the LTX conditioning copy is padded with silence beyond video duration; the final MP4 receives the original TTS waveform.

### 3.3 Job polling

Gateway polling was reduced from 0.5 seconds to 0.1 seconds.

- Theoretical mean detection improvement: approximately 0.20 s
- Theoretical maximum detection improvement: approximately 0.40 s

Runtime variation in generation was too large to isolate this change clearly. Push completion was considered but not adopted because its expected average gain over 0.1-second polling was only about 0.05 seconds.

## 4. Resolution comparison

The first clip of a turn was reduced to 288×384 and compared with 384×512 at four steps. Early application measurements were uncontrolled across time of day, GPU load, cache/allocator state, and LLM-generated prompts.

### 4.1 Initial application observation (reference only)

| Metric | 384×512, 4-step mean | 288×384, 4-step mean | Difference |
|---|---:|---:|---:|
| Audio ready | 1.066 s | 0.972 s | -0.094 s |
| Total video processing | 3.613 s | 3.677 s | +0.064 s |
| Server generation | 3.299 s | 3.358 s | +0.059 s |
| Submission to video completion | 4.679 s | 4.650 s | -0.029 s |

This suggested no resolution benefit, but the same configuration varied from 2.4 to 4.5 seconds. The observed difference was well inside that noise, so this table was not used to decide performance.

### 4.2 Controlled server measurement

The server alternated five runs at each resolution in two sets, holding seed, audio, four steps, and 81 frames constant.

| Stage | 384×512 | 288×384 | Difference |
|---|---:|---:|---:|
| Total | 3.457 s | 3.108 s | -0.349 s |
| Pipeline, including denoise | 2.622 s | 2.270 s | -0.352 s |
| Text encode | 0.134 s | 0.134 s | ±0 s |
| MP4 encode | 0.400 s | 0.400 s | ±0 s |
| A2V preprocessing | 0.100 s | 0.104 s | +0.004 s |

Under control, 288×384 was approximately 0.35 seconds or 10% faster. Nearly all savings came from the pipeline/denoise stage through fewer spatial tokens.

The apparent reversal in the app came primarily from comparing averages across different GPU and cache states. Prompt-length changes added tens of milliseconds. A roughly 44% pixel reduction did have an effect; the early test could not separate a sub-0.11-second observation from larger runtime variance. After visual review, the app temporarily returned to 384×512, then reinstated 288×384 for only the first clip after controlled and in-app A/B measurements.

### 4.3 In-application A/B measurement

This test reused the same recent character and conditioning audio through the same Gateway client as the app. LLM and TTS were excluded. Seed 1004, four steps, 81 frames, and no modality scale were fixed. Five A and five B runs were interleaved, reversing start order.

| Metric | A: 384×512 | B: 288×384 | B difference |
|---|---:|---:|---:|
| Request to detected completion, mean | 3.466 s | 3.175 s | -0.291 s |
| Request to detected completion, median | 3.457 s | 3.167 s | -0.290 s |
| Server generation, mean | 3.357 s | 3.069 s | -0.288 s |
| Server generation, median | 3.356 s | 3.062 s | -0.294 s |

The app measurement reproduced an approximately 0.29-second or 8% advantage for 288×384.

In a preliminary set, only the first 384×512 run took 17.317 seconds; later runs were around three seconds. This was backend cold start, not an A/B effect. The accepted table uses the next set after both resolutions were prepared. Startup latency must be measured separately from warm latency.

`scripts/benchmark_resolution.py` reproduces the test and saves individual values, means, and medians under `data/benchmarks`. Requests are serial to avoid queue wait and HTTP 409 conflicts.

## 5. Step reduction

Only the first clip was reduced from eight to six and then four steps. Follow-up clips remain at eight.

### 5.1 Representative six-step result

| Metric | Value |
|---|---:|
| LLM first text | 0.141 s |
| Audio completed | 1.018 s |
| Server generation | 3.520 s |
| Total video processing | 3.917 s |
| Submission to completion | 4.935 s |

### 5.2 Four-step result

At 384×512 and four steps, first completion was 4.842 and 4.516 seconds, averaging 4.679 seconds. Video processing improved approximately 0.3–0.6 seconds against the representative six-step run. Visual inspection found no objectionable loss, so four steps was adopted for the first clip. Eight-step follow-ups still had approximately 1.2–1.7 seconds of headroom before first-clip playback ended in those tests.

## 6. Video-server improvements

The server received preprocessing, encoding, and queue improvements. Denoising occupied approximately two seconds, and eight steps were close to kernel-launch limited.

CUDA Graphs and `torch.compile` remain promising but were deferred because they require graph management per resolution/frame count, can worsen cold start through compilation, may retrace or fail, consume additional VRAM, and exceeded the low-risk scope of this iteration.

### 6.1 Results after the steps parameter became effective

Until the morning of September 4, 2026, the server ignored client `steps` on a fixed distilled eight-step path. Earlier apparent four-step improvements mixed changes to the LLM, TTS, server, and runtime conditions. The corrected server subsamples the distilled sigma sequence; `distilled sigma subsample: 4/8 steps` confirms activation.

Server measurements at 288×384 and 81 frames:

| Steps | Server generation | Versus 8 steps |
|---:|---:|---:|
| 8 | 3.20 s | Baseline |
| 6 | 2.68 s | -16% |
| 4 | 2.19 s | -31% |
| 4 + `modality_scale=1.3` | Approximately 2.9 s | Strong-mouth mode |

Four-step first clips became the largest first-response improvement. Follow-ups retain eight steps for temporal quality.

## 7. Photorealistic articulation experiments

### 7.1 3D versus photorealistic inputs

All chunks moved their mouths with a 3D character. With photorealistic images, the same A2V path sometimes changed expression and blinking while keeping the mouth closed. This suggested that upload, TTS, A2V mode, and audio replacement were intact, while image-identity conditioning overpowered audio conditioning for realistic faces.

### 7.2 Speech prompt

The exact utterance was moved to the beginning of the prompt as quoted dialogue, followed by explicit instructions for visible lips, teeth, and jaw movement for every syllable. This helped but did not guarantee photorealistic articulation.

### 7.3 Seed experiments

Seeds including 1001 and 1004 were compared. Seed 1004 produced clear articulation repeatedly, but also failed in a later run, proving that seed alone cannot guarantee success. Photorealistic modes default to the most reliable observed seed, 1004, and apply the UI-selected seed to every chunk; Standard varies each chunk from the selected base seed.

### 7.4 Final-frame chaining

Initially, each clip began from the previous clip's final frame within a turn. In photorealistic output, a closed mouth from the padded silent tail was inherited strongly and later chunks failed more often.

Removing chaining and generating every chunk from one reference improved later articulation, while transitions within a turn were not objectionable. Photorealistic modes now reuse the registration-time speaking anchor. Standard mode retains chaining for 3D/illustrated visual continuity.

### 7.5 Audio-conditioning strength

| Setting | Generation | Assessment |
|---|---:|---|
| Default 1.0 | 3.16 s | Adequate headroom |
| `audio_modality_scale=1.3` | 4.84 s | Initially mistaken as effective; no-op in A2V |
| `audio_guidance_scale=1.3` | 5.16 s | Suspected ineffective for A2V; rejected |
| Both at 1.5 | 6.78 s | Extra cost only; rejected |

Later server tests showed bit-identical output because A2V freezes audio and `audio_modality_scale` only affects audio prediction. Video-side `modality_scale` is the parameter that actually affects the mouth region. The app no longer sends ineffective audio scales.

| Mode | Scale | Seed | Reference | Purpose |
|---|---:|---:|---|---|
| Standard (illustration/3D) | None | Variable | Chained final frame | Speed and continuity |
| Photorealistic/Fast | `modality_scale=1.3` during preparation only | UI-selected (default 1004) | Speaking anchor every time | Initial speed and continuity |
| Photorealistic/Strong Lip Motion | 1.3 during conversation too | UI-selected (default 1004) | Speaking anchor every time | Higher articulation reliability |

### 7.6 Registration-time speaking anchor

Photorealistic reference mouth shape strongly constrains output. Registration therefore preloads LTX with `nvfp4-fast`, generates a preparation video from the uploaded image and a fixed sustained-vowel recording at the selected native resolution and eight steps, and extracts the stable open-mouth frame at 0.75 seconds as `character-speaking.png`. The preparation generation also warms model loading and inference paths.

The early reduced-resolution four-step version took 19.9 seconds after backend restart, including 17.0 seconds for generation, and approximately 3.2–3.6 seconds while warm. It was replaced with selected-resolution eight-step generation to protect the anchor reused by every later clip. At 384×512, generation measured 4.94 seconds. Four steps failed to open the mouth in one trial; eight steps produced a clear open mouth. Accurate FFmpeg seeking places `-ss` after the input to avoid returning to the first keyframe.

In practical 384×512 testing, the full-resolution anchor improved facial, mouth, and hair detail and maintained articulation. First completion after conversation start was 2.618 seconds and follow-up headroom was 1.496 seconds, with no conversational latency penalty from higher-quality offline preparation. Selected-resolution, eight-step anchors were consequently adopted for all 11 profiles.

One post-preparation E2E test using 288×384, four steps, and `modality_scale=1.3` reported 2.805-second server generation, substantially faster than approximately 4.2–4.8 seconds with the former ineffective audio scale.

Fast became the default to test whether the anchor alone sustains speech. Preparation still uses `modality_scale=1.3`, while conversation omits it. Strong Lip Motion is available for comparison.

In a Fast-mode E2E test, first-clip server generation was 2.174 seconds and app processing 2.469 seconds at 288×384/four steps. The 384×512/eight-step follow-up measured 3.427 and 3.640 seconds respectively. Frame inspection confirmed clear mouth opening and closing in both clips, with approximately 1.36 seconds of five-second playback headroom.

## 8. UI and playback improvements

### Dynamic removal of fixed-duration silence

Because LTX clips are approximately five seconds, a 1.45-second utterance originally left roughly 3.5 seconds of silence. That was useful generation headroom, but waiting for the end even after the next clip completed made conversation unnatural.

Playback now skips the remainder once `speech_duration` has elapsed and the following chunk is `playable`. If it is pending, the current clip remains visible and switches immediately on its completion notification. This applies at every boundary, enabling continuous third and later utterances when ready.

Other UI changes:

- Drag-and-drop character images and TXT files
- Chat input below the video; Enter submits and Shift+Enter inserts a newline
- Two alternating video elements preload the next clip
- The original image is shown while initial generation runs and fades when playback starts
- The original image also covers residue from the prior turn
- The waiting image uses the same centered crop as the video frame
- Editing settings re-enables the Update Settings button
- Photorealistic workarounds are user-selectable and do not add unnecessary 3D latency
- Japanese/English UI selection is persisted in the browser
- Conversation language is independent of UI language; Auto/Japanese/English select the LLM prompt and segmentation rules

## 9. Major defects encountered

### HTTP 409

Unmanaged backend processes and conflicting generation requests caused HTTP 409. Backend ownership was unified under the Gateway.

### Short-audio range error

Resolved by padding only the conditioning WAV to the duration required by LTX.

### Frame extraction failure

`ffmpeg -sseof -0.08` sometimes produced no frame for short video. The extraction point and output-existence checks were corrected.

### HTTP 422 from 101 frames at 20 fps

A removed three-/five-second comparison calculated `seconds × fps + 1`, producing 101 frames for 20 fps and violating LTX's `8n+1` constraint. Profiles now use the defined 97 frames.

## 10. Adopted configuration

- Start TTS while the LLM response is streaming
- Run TTS tasks concurrently and pipeline later TTS with video generation
- Generate approximately five-second clips
- Four steps for the first clip; eight for later clips
- Reduced first-clip resolution for every profile; selected resolution thereafter
- 100 ms Gateway polling
- User-selected character policy
- Photorealistic/Fast default: 288×384 first, 384×512 follow-ups for that selected profile, UI-selected seed (default 1004), no conversation scale, speaking anchor every time
- Photorealistic/Strong: same plus conversation `modality_scale=1.3`
- Standard: selected profile, variable seed, scale 1.0/default, final-frame chaining within a turn
- Replace generated audio with original TTS audio

### 10.1 Startup resolutions for all profiles

Anchors use each selected profile's native resolution and eight steps because they are reused. Only the first clip uses the nearest lower resolution divisible by 32 and four steps; fps and frame count remain unchanged.

| Selected/anchor profile | First clip |
|---|---:|
| 640×352 at 16 fps | 480×256 |
| 512×384 at 16 fps | 384×288 |
| 640×384 at 16 fps | 480×288 |
| 576×384 at 16 fps | 480×320 |
| 384×512 at 16 fps | 288×384 |
| 384×640 at 16 fps | 288×480 |
| 576×320 at 20 fps | 480×256 |
| 512×384 at 20 fps | 384×288 |
| 512×288 at 24 fps | 448×256 |
| 480×320 at 24 fps | 384×256 |
| 288×512 at 24 fps | 256×448 |

Aspect ratios that cannot be scaled exactly in multiples of 32 use the nearest ratio that limits the visible transition. Appearance and speed still require practical validation per profile.

## 11. Final latency summary

The September 4, 2026 configuration combined:

1. AivisSpeech on GPU 1 with post-startup warmup.
2. LTX loading and warmup during character registration.
3. A generated open-mouth speaking anchor for photorealistic images.
4. Removal of ineffective A2V audio scales.
5. `modality_scale=1.3` only for anchor preparation in Fast mode.
6. Effective four-step inference for the first clip.
7. Lower first-clip resolution across profiles.
8. Ahead-of-time follow-up TTS and video generation during playback.

Representative E2E results for Photorealistic/Fast with 384×512 selected (288×384/four-step first clip, 384×512/eight-step follow-up):

| Metric | Mid-optimization | Final run 1 | Final run 2 |
|---|---:|---:|---:|
| LLM first text | 0.160 s | 0.115 s | 0.139 s |
| First TTS | 0.703 s | 0.231 s | 0.224 s |
| First server generation | 4.451 s | 2.170 s | 2.057 s |
| Submission to first completion | 5.657 s | 2.734 s | 2.657 s |
| Follow-up server generation | 5.009 s | 3.359 s | 3.292 s |
| Follow-up headroom at first end | -0.206 s | 1.436 s | 1.507 s |

The final first video completed in approximately 2.7 seconds, and follow-ups completed about 1.4–1.5 seconds before nominal first-clip end. Mouth motion was visually confirmed in both runs. A slightly open mouth during silence was accepted as less harmful than closed-mouth speech.

In a fixed-input test outside the app, a no-conversation-scale first clip reported 2.174-second server generation and 2.469-second app processing. The approximately 0.19–0.30 seconds outside server generation comprises conditioning-audio upload, HTTP round trips, 100 ms polling, MP4 download, and audio-replacement muxing.

Preparation was verified for 16 fps landscape, 20 fps landscape, 24 fps landscape, and 24 fps portrait profiles. Warm registration took approximately 3.2–3.5 seconds.

## 12. Remaining work

- LTX alone cannot guarantee exact lip sync for photorealistic input.
- `modality_scale=1.3` costs approximately 0.7 seconds at four steps in exchange for stronger mouth motion.
- GPU queue variance can still exhaust the buffer in long conversations.
- Japanese character-count segmentation is less robust than morphological analysis.
- Guaranteed photorealistic lip sync requires a dedicated post-generation lip-sync stage.
- CUDA Graphs and `torch.compile` are candidates for the next performance iteration.
- Semantic emotion, expression, and gesture generation from LLM text is future work.

## 13. Interpreting measurements

`session.json` records LLM start/first text/completion, TTS start/audio completion, video start/completion, server generation time, profile, steps, seed, frames, and scales.

Evaluate separately:

- time to first LLM text
- TTS duration
- audio-ready to video-ready duration
- server-reported generation
- download and mux postprocessing
- interval between first and later video completion
- buffered headroom at the end of the first clip

Do not directly compare values that mix server revisions, steps, resolutions, or scales. Repeat tests under identical conditions. When an effect is smaller than runtime variance, fix the input and alternate variants; averages from different time periods are useful only as directional observations.
