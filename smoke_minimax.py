"""Smoke test: MiniMax TTS via raw HTTP (same payload Pipecat sends).

Verifies the API key + endpoint + voice without spinning up a Pipecat pipeline.
Writes minimax_output.wav next to this script.
"""

import asyncio
import json
import os
import wave

import aiohttp
from dotenv import load_dotenv

SAMPLE_RATE = 24000


async def main() -> None:
    load_dotenv()
    api_key = os.environ["MINIMAX_API_KEY"]
    group_id = os.environ.get("MINIMAX_GROUP_ID", "")
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.chat/v1/t2a_v2")
    model = os.environ.get("MINIMAX_MODEL", "speech-02-turbo")
    voice = os.environ.get("MINIMAX_VOICE", "Calm_Woman")
    language_boost = os.environ.get("MINIMAX_LANGUAGE_BOOST")

    url = f"{base_url}?GroupId={group_id}" if group_id else base_url

    payload = {
        "stream": True,
        "model": model,
        "text": "你好,我系粤语语音助手,测试一下 MiniMax 嘅广东话合成效果。",
        "voice_setting": {"voice_id": voice, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {
            "bitrate": 128000,
            "format": "pcm",
            "channel": 1,
            "sample_rate": SAMPLE_RATE,
        },
    }
    if language_boost:
        payload["language_boost"] = language_boost

    headers = {
        "accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    pcm = bytearray()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            print(f"HTTP {resp.status}")
            if resp.status != 200:
                body = await resp.text()
                raise SystemExit(f"MiniMax error: {body[:500]}")

            buf = bytearray()
            async for chunk in resp.content.iter_chunked(4096):
                if not chunk:
                    continue
                buf.extend(chunk)
                while b"data:" in buf:
                    start = buf.find(b"data:")
                    nxt = buf.find(b"data:", start + 5)
                    if nxt == -1:
                        if start > 0:
                            buf = buf[start:]
                        break
                    block = bytes(buf[start:nxt])
                    buf = buf[nxt:]
                    try:
                        data = json.loads(block[5:].decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if "extra_info" in data:
                        print("Received final chunk with extra_info:", data.get("extra_info"))
                        continue
                    audio_hex = (data.get("data") or {}).get("audio")
                    if audio_hex:
                        pcm.extend(bytes.fromhex(audio_hex))

    if not pcm:
        raise SystemExit("No audio returned")

    out = os.path.join(os.path.dirname(__file__), "minimax_output.wav")
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(pcm))
    print(f"OK: wrote {len(pcm)} PCM bytes -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
