import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

const RECORDING_BUCKET = process.env.RECORDING_BUCKET || '';
const AWS_REGION = process.env.AWS_REGION || 'us-west-2';

const s3 = RECORDING_BUCKET ? new S3Client({ region: AWS_REGION }) : null;

/**
 * Buffers customer (inbound) and AI (outbound) PCM audio during a call,
 * then mixes both sides into a mono 8 kHz / 16-bit WAV and uploads to S3.
 *
 * Memory usage: ~38 MB max for a 20-minute call (two 16-bit 8 kHz streams).
 */
export class AudioRecorder {
  private customerChunks: Buffer[] = [];
  private aiChunks: Buffer[] = [];
  private customerBytes = 0;
  private aiBytes = 0;
  private callSid: string;
  private finalized = false;

  constructor(callSid: string) {
    this.callSid = callSid;
  }

  /** Append decoded PCM from the customer (inbound) side */
  appendCustomerAudio(pcm: Buffer): void {
    if (this.finalized) return;
    this.customerChunks.push(pcm);
    this.customerBytes += pcm.length;
  }

  /**
   * Append decoded PCM from the AI (Bedrock outbound) side.
   * Pads with silence to stay time-aligned with the customer stream,
   * which arrives continuously and serves as the time reference.
   */
  appendAiAudio(pcm: Buffer): void {
    if (this.finalized) return;

    // Customer audio streams continuously from RTP (even during silence),
    // so customerBytes reflects the true elapsed time of the call.
    // AI audio only arrives in bursts when the AI speaks.
    // Pad the AI buffer with silence to align to the current time position.
    const gap = this.customerBytes - this.aiBytes;
    if (gap > 0) {
      this.aiChunks.push(Buffer.alloc(gap)); // zeros = silence
      this.aiBytes += gap;
    }

    this.aiChunks.push(pcm);
    this.aiBytes += pcm.length;
  }

  /**
   * Mix both sides into mono WAV, upload to S3, and return the S3 key.
   * Returns null if recording is disabled or there's no audio.
   */
  async finalizeAndUpload(): Promise<string | null> {
    if (this.finalized) return null;
    this.finalized = true;

    if (!s3 || !RECORDING_BUCKET) {
      console.log(`[AudioRecorder] Recording disabled (no RECORDING_BUCKET), skipping upload for ${this.callSid}`);
      return null;
    }

    if (this.customerBytes === 0 && this.aiBytes === 0) {
      console.log(`[AudioRecorder] No audio captured for ${this.callSid}, skipping`);
      return null;
    }

    try {
      const customerPcm = Buffer.concat(this.customerChunks);
      const aiPcm = Buffer.concat(this.aiChunks);

      // Free memory early
      this.customerChunks = [];
      this.aiChunks = [];

      const mixed = mixToMono(customerPcm, aiPcm);
      const wav = createWavBuffer(mixed, 8000, 16, 1);

      const s3Key = `recordings/${this.callSid}.wav`;
      await s3.send(new PutObjectCommand({
        Bucket: RECORDING_BUCKET,
        Key: s3Key,
        Body: wav,
        ContentType: 'audio/wav',
      }));

      console.log(`[AudioRecorder] Uploaded ${s3Key} (${wav.length} bytes) to ${RECORDING_BUCKET}`);
      return s3Key;
    } catch (err) {
      console.error(`[AudioRecorder] Failed to finalize/upload for ${this.callSid}:`, err);
      return null;
    }
  }
}

/**
 * Mix two 16-bit PCM buffers into a single mono buffer.
 * If one track is shorter, it's padded with silence.
 * Samples are averaged and clamped to [-32768, 32767].
 */
function mixToMono(a: Buffer, b: Buffer): Buffer {
  const samplesA = Math.floor(a.length / 2);
  const samplesB = Math.floor(b.length / 2);
  const maxSamples = Math.max(samplesA, samplesB);

  const out = Buffer.alloc(maxSamples * 2);

  for (let i = 0; i < maxSamples; i++) {
    const sA = i < samplesA ? a.readInt16LE(i * 2) : 0;
    const sB = i < samplesB ? b.readInt16LE(i * 2) : 0;
    // Average both channels; clamp to int16 range
    let mixed = Math.round((sA + sB) / 2);
    if (mixed > 32767) mixed = 32767;
    if (mixed < -32768) mixed = -32768;
    out.writeInt16LE(mixed, i * 2);
  }
  return out;
}

/**
 * Wrap raw PCM data in a WAV header.
 */
function createWavBuffer(pcm: Buffer, sampleRate: number, bitsPerSample: number, channels: number): Buffer {
  const byteRate = sampleRate * channels * (bitsPerSample / 8);
  const blockAlign = channels * (bitsPerSample / 8);
  const header = Buffer.alloc(44);

  // RIFF header
  header.write('RIFF', 0);
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write('WAVE', 8);

  // fmt sub-chunk
  header.write('fmt ', 12);
  header.writeUInt32LE(16, 16);        // sub-chunk size
  header.writeUInt16LE(1, 20);         // PCM format
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);

  // data sub-chunk
  header.write('data', 36);
  header.writeUInt32LE(pcm.length, 40);

  return Buffer.concat([header, pcm]);
}
