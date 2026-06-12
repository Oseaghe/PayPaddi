import asyncio
import os
import tempfile
import httpx
import whisper

_model = None


def _ensure_ffmpeg():
    """Add bundled imageio ffmpeg to PATH if the system ffmpeg is missing."""
    import shutil
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _get_model():
    global _model
    if _model is None:
        _ensure_ffmpeg()
        _model = whisper.load_model("base")
    return _model


async def transcribe_voice_note(media_id: str, access_token: str) -> str:
    """Download a WhatsApp audio message and transcribe it with local Whisper."""
    async with httpx.AsyncClient() as client:
        meta_resp = await client.get(
            f"https://graph.facebook.com/v18.0/{media_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        meta_resp.raise_for_status()
        audio_url = meta_resp.json()["url"]

        audio_resp = await client.get(
            audio_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        audio_resp.raise_for_status()
        audio_bytes = audio_resp.content

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: _get_model().transcribe(tmp_path, fp16=False))
        return result["text"].strip()
    finally:
        os.unlink(tmp_path)
