"""Smoke test: Pipecat's AWSPollyTTSService end-to-end.

Checks whether run_tts actually yields audio bytes at 24 kHz. If it yields zero
frames, that explains why we hear nothing in the full pipeline.
"""

import asyncio
import os
import wave

import boto3
from dotenv import load_dotenv
from pipecat.frames.frames import StartFrame, TTSAudioRawFrame
from pipecat.services.aws.tts import AWSPollyTTSService

OUT_RATE = 24000


async def main() -> None:
    load_dotenv()
    region = os.environ.get("AWS_REGION", "us-east-1")
    frozen = boto3.Session(region_name=region).get_credentials().get_frozen_credentials()

    tts = AWSPollyTTSService(
        region=region,
        aws_access_key_id=frozen.access_key,
        api_key=frozen.secret_key,
        aws_session_token=frozen.token,
        sample_rate=OUT_RATE,
        settings=AWSPollyTTSService.Settings(voice="Zhiyu", engine="neural"),
    )

    # start() is needed so sample_rate / task_manager are initialized.
    # TTSService.start expects a PipelineTask-issued StartFrame — but in isolation
    # we can set sample_rate manually. Let's just call start and see.
    from pipecat.utils.asyncio.task_manager import TaskManager
    tm = TaskManager()
    await tm.set_event_loop(asyncio.get_running_loop())
    tts.set_task_manager(tm)

    await tts.start(
        StartFrame(audio_in_sample_rate=OUT_RATE, audio_out_sample_rate=OUT_RATE)
    )

    total_bytes = 0
    frame_count = 0
    async for frame in tts.run_tts("你好，这是一个Polly的测试。", context_id="smoke"):
        if isinstance(frame, TTSAudioRawFrame):
            frame_count += 1
            total_bytes += len(frame.audio)
            print(f"frame#{frame_count} size={len(frame.audio)} sr={frame.sample_rate}")

    print(f"\nTotal frames: {frame_count}, bytes: {total_bytes}")

    if total_bytes > 0:
        out_path = os.path.join(os.path.dirname(__file__), "polly_output.wav")
        # write an empty pcm (we didn't collect bytes — just check yield)
        print(f"OK (audio flowing). Would write to {out_path} if we collected pcm.")
    else:
        print("FAIL: run_tts yielded no audio. Likely resampler issue.")


if __name__ == "__main__":
    asyncio.run(main())
