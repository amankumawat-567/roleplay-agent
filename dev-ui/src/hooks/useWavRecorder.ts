import { useRef, useState } from "react";
import type { RefObject } from "react";

/** Encodes raw Float32 PCM samples as a 16-bit mono WAV file - browsers'
 * MediaRecorder doesn't produce WAV directly (only webm/ogg-opus), and
 * section F3's audio-input path needs real WAV bytes (see
 * docs/ARCHITECTURE.md's "Voice mode": verified live against Ollama's
 * Gemma 4 audio support, which takes raw WAV). */
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(offset: number, text: string) {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate (mono, 16-bit)
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function flatten(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}

interface WavRecorder {
  recording: boolean;
  error: string | null;
  /** Resolves true once mic capture has actually started - false (with
   * `error` set) on permission denial or no available device. Returning a
   * value directly, rather than making the caller read `error` off this
   * same render's stale closure right after awaiting, is what makes it
   * safe to branch on immediately. `onAutoStop`, if given, fires exactly
   * once (with whether real speech was ever detected) when the built-in
   * energy-based endpointer above decides the user is done talking - see
   * the module-level VAD constants and the module docstring. */
  start: (onAutoStop?: (hadSpeech: boolean) => void) => Promise<boolean>;
  /** Stops capture and returns the recorded clip as a WAV Blob - null if
   * nothing was ever recording, or the clip was empty. */
  stop: () => Blob | null;
  /** Live 0..1 mic input amplitude, updated on every ~4096-sample buffer
   * (see onaudioprocess below) while recording - a ref, not React state,
   * since it's meant to be read every animation frame (VoiceCallPage's
   * HeroOrb reactive pulse) without forcing a re-render on every buffer.
   * Sits at 0 whenever not recording. */
  levelRef: RefObject<number>;
}

// Energy-based endpointing thresholds (VoiceCallPage's auto-listen mode -
// see docs/roadmap.md F3). Raw per-buffer RMS, not the smoothed/scaled
// `levelRef` above (that 0.6-smoothed, *6-scaled value is tuned for a
// pleasant-looking orb pulse, not for a crisp speech/silence decision).
// These are reasonable starting points, not live-tuned against real mic
// hardware/room noise - the first thing to adjust if auto-stop clips words
// (raise SILENCE_HANGOVER_MS or lower the RMS threshold) or lingers too
// long after the user stops talking (lower SILENCE_HANGOVER_MS).
const SPEECH_RMS_THRESHOLD = 0.02;
// Consecutive above-threshold buffers required before we count speech as
// having actually started - one ~90ms buffer's audio pop/click shouldn't
// arm the endpointer. 3 buffers is ~250-280ms, in line with the "ignore
// blips under 200-300ms" guidance VoiceCallPage's auto-stop is built from.
const MIN_SPEECH_BUFFERS = 3;
// How long a silence has to last after speech was detected before
// concluding the user is done talking - the single most important tunable
// here. Under ~400ms reads as the app cutting the user off mid-sentence;
// over ~1s starts feeling laggy. 800ms sits in the middle of that range.
const SILENCE_HANGOVER_MS = 800;
// If nothing ever crosses the speech threshold at all (mic opened but the
// user never spoke - e.g. they got distracted), give up and auto-close
// rather than holding the mic open indefinitely.
const NO_SPEECH_TIMEOUT_MS = 6000;
// Hard cap regardless of VAD state - a safety valve against a stuck-open
// mic if the endpointer's threshold/hangover logic ever fails to fire.
const MAX_RECORDING_MS = 45000;

/** Mic capture for voice mode (see docs/roadmap.md F3), auto-endpointed by
 * default: `start()` takes an optional `onAutoStop` callback that fires
 * once - with whether real speech was ever detected - when the energy-
 * based VAD above decides the user is done talking (or gave up), so a
 * caller doesn't have to run its own silence-detection loop; passing none
 * makes this a plain push-to-talk recorder (the caller decides when to
 * stop, as originally built - see docs/roadmap.md F3's now-superseded
 * "push-to-talk vs. always-listening" call). `onAutoStop` only ever
 * signals; it doesn't call stop() itself, so the caller stays in charge of
 * the actual teardown + when/whether to send the clip (see VoiceCallPage's
 * handleAutoStop). Uses a ScriptProcessorNode rather than an AudioWorklet -
 * deprecated, but universally supported with no separate worklet-module
 * bundling, and this app only ever has one capture running at a time. */
export function useWavRecorder(): WavRecorder {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const silentGainRef = useRef<GainNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const levelRef = useRef(0);
  // Endpointing state, reset per start() call - see the VAD constants
  // above and their use in onaudioprocess below.
  const onAutoStopRef = useRef<((hadSpeech: boolean) => void) | null>(null);
  const autoStopFiredRef = useRef(false);
  const hasSpeechRef = useRef(false);
  const speechBufferStreakRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const startedAtRef = useRef(0);

  async function start(onAutoStop?: (hadSpeech: boolean) => void): Promise<boolean> {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      // A ScriptProcessorNode only fires onaudioprocess once it's part of
      // a path that reaches the destination - routed through a zero-gain
      // node so the user never hears their own mic looped back to them.
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;

      chunksRef.current = [];
      levelRef.current = 0;
      onAutoStopRef.current = onAutoStop ?? null;
      autoStopFiredRef.current = false;
      hasSpeechRef.current = false;
      speechBufferStreakRef.current = 0;
      lastSpeechAtRef.current = 0;
      startedAtRef.current = performance.now();
      processor.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(data));

        let sumSquares = 0;
        for (let i = 0; i < data.length; i++) sumSquares += data[i] * data[i];
        const rms = Math.sqrt(sumSquares / data.length);
        // Ordinary mic speech RMS sits well under 1.0 - the *6 gets it into
        // a usable 0..1 range instead of barely nudging the orb, and the
        // exponential smoothing (rather than the raw per-buffer value)
        // keeps the reactive pulse from looking jittery between buffers.
        const target = Math.min(1, rms * 6);
        levelRef.current += (target - levelRef.current) * 0.6;

        if (!onAutoStopRef.current || autoStopFiredRef.current) return;
        const now = performance.now();
        if (rms >= SPEECH_RMS_THRESHOLD) {
          speechBufferStreakRef.current += 1;
          if (speechBufferStreakRef.current >= MIN_SPEECH_BUFFERS) hasSpeechRef.current = true;
          if (hasSpeechRef.current) lastSpeechAtRef.current = now;
        } else {
          speechBufferStreakRef.current = 0;
        }

        const elapsedSinceStart = now - startedAtRef.current;
        const shouldStop = hasSpeechRef.current
          ? now - lastSpeechAtRef.current >= SILENCE_HANGOVER_MS || elapsedSinceStart >= MAX_RECORDING_MS
          : elapsedSinceStart >= NO_SPEECH_TIMEOUT_MS;
        if (shouldStop) {
          autoStopFiredRef.current = true;
          onAutoStopRef.current(hasSpeechRef.current);
        }
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioCtx.destination);

      streamRef.current = stream;
      audioCtxRef.current = audioCtx;
      sourceRef.current = source;
      processorRef.current = processor;
      silentGainRef.current = silentGain;
      setRecording(true);
      return true;
    } catch (err) {
      const denied = err instanceof DOMException && err.name === "NotAllowedError";
      setError(
        denied
          ? "Microphone access is blocked - allow it for this site in your browser's address-bar or site settings, then tap the mic again."
          : "Couldn't reach a microphone - check that one is connected and not in use by another app, then tap the mic again.",
      );
      return false;
    }
  }

  function stop(): Blob | null {
    const audioCtx = audioCtxRef.current;
    const sampleRate = audioCtx?.sampleRate ?? 44100;

    // Belt-and-suspenders against a queued onaudioprocess callback firing
    // between disconnect() below and the node actually tearing down - stop()
    // is about to hand the caller a final answer, an auto-stop callback
    // firing after that would be a stale, meaningless second signal.
    autoStopFiredRef.current = true;
    onAutoStopRef.current = null;

    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    silentGainRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioCtx?.close();

    processorRef.current = null;
    sourceRef.current = null;
    silentGainRef.current = null;
    audioCtxRef.current = null;
    streamRef.current = null;
    setRecording(false);
    levelRef.current = 0;

    const samples = flatten(chunksRef.current);
    chunksRef.current = [];
    if (samples.length === 0) return null;
    return encodeWav(samples, sampleRate);
  }

  return { recording, error, start, stop, levelRef };
}
