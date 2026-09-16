/** Plays a /speak-stream response (raw PCM16LE mono chunks, sample rate in
 * an X-Sample-Rate header - see api/routes/chat.py) progressively via the
 * Web Audio API, scheduling each chunk back-to-back as it arrives instead
 * of waiting for the whole response to buffer into one Blob first - the
 * whole point of the backend streaming the audio out in the first place
 * (see llm/tts.py's synthesize_stream). No <audio> element/Blob URL
 * involved: raw PCM has no container an <audio> tag can decode on its own.
 *
 * `levelRef`, if given, is written on every scheduled chunk with that
 * chunk's RMS amplitude (0..1, exponentially smoothed) - the same shape as
 * useWavRecorder's own mic levelRef, so HeroOrb's reactive pulse (see
 * VoiceCallPage) can drive off either one identically. It's the caller's
 * ref, not one this module creates, because VoiceCallPage keeps a single
 * stable playback-level ref across every segment's own player instance. */
export interface PcmStreamPlayer {
  /** Resolves once every chunk that was ever scheduled has finished
   * playing, or stop() was called. */
  ended: Promise<void>;
  /** Stops playback immediately (mid-chunk if necessary) and releases the
   * AudioContext - call on unmount/navigation-away so voice mode doesn't
   * keep talking after the user has left the screen. */
  stop: () => void;
}

export function playPcmStream(response: Response, levelRef?: { current: number }): PcmStreamPlayer {
  const sampleRate = Number(response.headers.get("X-Sample-Rate")) || 24000;
  // {sampleRate} is a hint some browsers honor for the context's own
  // native rate - not load-bearing either way, since each AudioBuffer
  // below carries its own true sample rate and the Web Audio API
  // resamples automatically during playback if the two ever differ.
  const ctx = new AudioContext({ sampleRate });

  const activeSources = new Set<AudioBufferSourceNode>();
  let nextStartTime = 0;
  let pendingChunks = 0;
  let readerDone = false;
  let stopped = false;
  let resolveEnded!: () => void;
  const ended = new Promise<void>((resolve) => {
    resolveEnded = resolve;
  });

  function checkEnded() {
    if ((readerDone && pendingChunks === 0) || stopped) resolveEnded();
  }

  function scheduleChunk(bytes: Uint8Array) {
    const sampleCount = bytes.length >> 1;
    if (sampleCount === 0) return;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const samples = new Float32Array(sampleCount);
    let sumSquares = 0;
    for (let i = 0; i < sampleCount; i++) {
      const s = view.getInt16(i * 2, true) / 32768;
      samples[i] = s;
      sumSquares += s * s;
    }
    if (levelRef) {
      const rms = Math.sqrt(sumSquares / sampleCount);
      const target = Math.min(1, rms * 3);
      levelRef.current += (target - levelRef.current) * 0.6;
    }

    const buffer = ctx.createBuffer(1, sampleCount, sampleRate);
    buffer.copyToChannel(samples, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const startAt = Math.max(nextStartTime, ctx.currentTime);
    source.start(startAt);
    nextStartTime = startAt + buffer.duration;

    pendingChunks++;
    activeSources.add(source);
    source.onended = () => {
      activeSources.delete(source);
      pendingChunks--;
      checkEnded();
    };
  }

  async function pump() {
    // Resume close to the call site, not in a later microtask - some
    // browsers only honor a freshly-created AudioContext's resume this
    // close to the user gesture (ultimately handleMicTap's tap, or the
    // read-aloud button's click) that led here.
    await ctx.resume().catch(() => {});
    const reader = response.body?.getReader();
    if (!reader) {
      readerDone = true;
      checkEnded();
      return;
    }
    try {
      while (!stopped) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && value.length > 0) scheduleChunk(value);
      }
    } catch {
      // A network/stream error mid-playback - best-effort, same as every
      // other TTS failure mode in voice mode: stop cleanly rather than
      // leaving `ended` unresolved forever.
    } finally {
      readerDone = true;
      checkEnded();
    }
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    for (const source of activeSources) {
      try {
        source.stop();
      } catch {
        // Already stopped/ended - fine.
      }
    }
    activeSources.clear();
    ctx.close().catch(() => {});
    resolveEnded();
  }

  pump();

  return { ended, stop };
}
