"""Smoke test: AWS Transcribe via Pipecat's WebSocket STT service.

Feeds minimax_output.wav through a tiny Pipeline and prints transcripts.
No microphone / transport needed.
"""

import asyncio
import os
import wave

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.aws.stt import AWSTranscribeSTTService
from pipecat.transcriptions.language import Language


class Printer(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            print(f"[final]   {frame.text}")
        elif isinstance(frame, InterimTranscriptionFrame):
            print(f"[partial] {frame.text}")
        await self.push_frame(frame, direction)


async def main() -> None:
    load_dotenv()
    region = os.environ.get("AWS_REGION", "us-east-1")
    wav_path = os.path.join(os.path.dirname(__file__), "minimax_output.wav")

    with wave.open(wav_path, "rb") as wf:
        src_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    # Transcribe streaming supports 8000 or 16000 Hz; resample if needed.
    if src_rate != 16000:
        import audioop
        raw, _ = audioop.ratecv(raw, 2, 1, src_rate, 16000, None)
    sample_rate = 16000

    import boto3
    frozen = boto3.Session(region_name=region).get_credentials().get_frozen_credentials()

    stt = AWSTranscribeSTTService(
        region=region,
        aws_access_key_id=frozen.access_key,
        api_key=frozen.secret_key,
        aws_session_token=frozen.token,
        settings=AWSTranscribeSTTService.Settings(language=Language.ZH_CN),
    )

    pipeline = Pipeline([stt, Printer()])
    task = PipelineTask(pipeline)

    async def feed():
        # Let the pipeline start + websocket connect.
        await asyncio.sleep(1.5)
        chunk = 3200  # 100ms @ 16kHz 16-bit mono
        for i in range(0, len(raw), chunk):
            await task.queue_frame(
                InputAudioRawFrame(
                    audio=raw[i : i + chunk],
                    sample_rate=sample_rate,
                    num_channels=1,
                )
            )
            await asyncio.sleep(0.08)
        # Give Transcribe time to flush final results before ending.
        await asyncio.sleep(3.0)
        await task.queue_frame(EndFrame())

    await asyncio.gather(PipelineRunner(handle_sigint=False).run(task), feed())


if __name__ == "__main__":
    asyncio.run(main())
