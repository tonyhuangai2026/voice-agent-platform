"""Smoke test: AWS Bedrock LLM via Pipecat service (one-shot, no pipeline)."""

import asyncio
import os

from dotenv import load_dotenv
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.settings import LLMSettings


async def main() -> None:
    load_dotenv()
    region = os.environ.get("AWS_REGION", "us-east-1")
    model = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")

    llm = AWSBedrockLLMService(
        aws_region=region,
        settings=LLMSettings(
            model=model,
            system_instruction="You are a friendly voice assistant. Keep replies to one sentence.",
            max_tokens=128,
        ),
    )

    ctx = LLMContext()
    ctx.add_message({"role": "user", "content": "Say hi in Chinese in one short sentence."})

    reply = await llm.run_inference(ctx)
    print(f"\n=== Bedrock ({model}) reply ===\n{reply}\n")


if __name__ == "__main__":
    asyncio.run(main())
