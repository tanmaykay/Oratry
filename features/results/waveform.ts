/**
 * Produces display peaks from decoded PCM samples. These are intentionally
 * derived from the recording at review time rather than a decorative preset.
 */
export function buildWaveformPeaks(channels: Float32Array[], barCount = 128): number[] {
  const sampleCount = Math.max(...channels.map(channel => channel.length), 0);
  if (!sampleCount || !channels.length || barCount < 1) return [];

  const blockSize = Math.max(1, Math.ceil(sampleCount / barCount));
  return Array.from({ length: Math.ceil(sampleCount / blockSize) }, (_, barIndex) => {
    const start = barIndex * blockSize;
    const end = Math.min(sampleCount, start + blockSize);
    let peak = 0;
    for (const channel of channels) {
      for (let index = start; index < Math.min(end, channel.length); index += 1) peak = Math.max(peak, Math.abs(channel[index] ?? 0));
    }
    // Square-root scaling makes quiet, real sections visible without changing
    // where the signal's peaks and troughs occur.
    return Math.max(0.035, Math.sqrt(peak));
  });
}
