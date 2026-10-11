"""Thread-safe, UUID-isolated streaming text-to-speech manager.

Input protocol::

    {"id": "uuid", "content": "[Start]"}
    {"id": "uuid", "content": "one or more text chunks"}
    {"id": "uuid", "content": "[End]"}

Chinese and English sentences are sent to edge-tts as soon as ending
punctuation arrives. A UUID keeps exclusive ownership of the playback worker
until ``[End]``, so another UUID cannot be inserted between its sentences.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence


LOGGER = logging.getLogger(__name__)
_STOP = object()
_SESSION_END = object()
_SENTENCE_END = re.compile(
    r"(?:[。！？；.!?;]+[”’\"'）)\]】》〉」』]*|\n+)"
)


def _split_complete_sentences(text: str) -> tuple[list[str], str]:
    """Return punctuation-terminated sentences and the unfinished tail."""
    sentences: list[str] = []
    consumed = 0
    for match in _SENTENCE_END.finditer(text):
        sentence = text[consumed:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        consumed = match.end()
    return sentences, text[consumed:]


class _StreamingEngine(Protocol):
    sample_rate: Optional[int]

    def stream(self, text: str) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class _AudioSink(Protocol):
    def play(self, chunks: Iterable[bytes], sample_rate: Optional[int]) -> None: ...

    def close(self) -> None: ...


class _EdgeTTSEngine:
    """Synchronous wrapper around edge-tts's streamed MP3 response."""

    sample_rate = None  # edge-tts returns encoded MP3, not raw PCM.

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        *,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        proxy: Optional[str] = None,
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self.proxy = proxy

    def stream(self, text: str) -> Iterable[bytes]:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("缺少 edge-tts：pip install edge-tts") from exc

        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
            proxy=self.proxy,
        )
        for chunk in communicate.stream_sync():
            if chunk.get("type") == "audio" and chunk.get("data"):
                yield chunk["data"]

    def close(self) -> None:
        pass


class _StreamingPlayerSink:
    """Pipe edge-tts MP3 chunks to mpv or ffplay as they arrive."""

    def __init__(self, command: Optional[Sequence[str]] = None) -> None:
        self.command = list(command) if command else None
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._process_lock = threading.Lock()

    @staticmethod
    def _default_command() -> list[str]:
        mpv = shutil.which("mpv")
        if mpv:
            return [
                mpv,
                "--no-video",
                "--really-quiet",
                "--cache=no",
                "--audio-buffer=0.1",
                "--demuxer-lavf-format=mp3",
                "-",
            ]
        ffplay = shutil.which("ffplay")
        if ffplay:
            return [
                ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
            ]
        raise RuntimeError(
            "流式播放 edge-tts 音频需要 mpv 或 ffplay，并且播放器必须位于 PATH 中"
        )

    def play(self, chunks: Iterable[bytes], sample_rate: Optional[int]) -> None:
        del sample_rate  # MP3 contains its own audio format information.
        command = self.command or self._default_command()
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        with self._process_lock:
            self._process = process
        try:
            if process.stdin is None:
                raise RuntimeError("无法打开音频播放器的标准输入")
            for chunk in chunks:
                process.stdin.write(chunk)
                process.stdin.flush()
            process.stdin.close()
            return_code = process.wait()
            if return_code:
                raise RuntimeError(f"音频播放器异常退出，状态码：{return_code}")
        finally:
            with self._process_lock:
                self._process = None
            if process.poll() is None:
                process.terminate()
                process.wait()

    def close(self) -> None:
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()


@dataclass
class _TextSession:
    session_id: str
    buffer: str = ""
    segments: Queue[Any] = field(default_factory=Queue)
    queued: bool = False


class manager:
    """Split UUID-tagged text into sentences and stream sessions serially."""

    def __init__(
        self,
        *,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        proxy: Optional[str] = None,
        player_command: Optional[Sequence[str]] = None,
        engine_factory: Optional[Callable[[], _StreamingEngine]] = None,
        audio_sink_factory: Optional[Callable[[], _AudioSink]] = None,
    ) -> None:
        self.speak_start_signal = "[Start]"
        self.speak_end_signal = "[End]"

        self._engine_factory = engine_factory or (
            lambda: _EdgeTTSEngine(
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
                proxy=proxy,
            )
        )
        self._audio_sink_factory = audio_sink_factory or (
            lambda: _StreamingPlayerSink(player_command)
        )

        self.engine: Optional[_StreamingEngine] = None
        self._sink: Optional[_AudioSink] = None
        self._sessions: dict[str, _TextSession] = {}
        self._session_lock = threading.Lock()
        self._jobs: Queue[Any] = Queue()
        self._idle_condition = threading.Condition()
        self._pending_jobs = 0
        self._accepting = True
        self.last_error: Optional[BaseException] = None

        self._worker = threading.Thread(
            target=self._playback_loop,
            name="TTS-playback",
            daemon=True,
        )
        self._worker.start()

    def speak_stream(self, chunk: dict) -> bool:
        """Accept one protocol message; return whether it was accepted."""
        if not isinstance(chunk, dict):
            return False
        session_id = chunk.get("id")
        content = chunk.get("content")
        if not isinstance(session_id, str) or not session_id:
            return False
        if not isinstance(content, str):
            return False

        with self._session_lock:
            if not self._accepting:
                return False
            if content == self.speak_start_signal:
                previous = self._sessions.get(session_id)
                if previous is not None:
                    LOGGER.warning("UUID %s 重复开始；已丢弃此前未完成的文本", session_id)
                    if previous.queued:
                        previous.segments.put(_SESSION_END)
                self._sessions[session_id] = _TextSession(session_id=session_id)
                return True

            session = self._sessions.get(session_id)
            if session is None:
                LOGGER.warning("忽略没有 [Start] 的 TTS 消息：%s", session_id)
                return False

            if content != self.speak_end_signal:
                session.buffer += content
                sentences, session.buffer = _split_complete_sentences(session.buffer)
                for sentence in sentences:
                    self._enqueue_segment(session, sentence)
                return True

            self._sessions.pop(session_id)
            remainder = session.buffer.strip()
            if remainder:
                self._enqueue_segment(session, remainder)
            if session.queued:
                session.segments.put(_SESSION_END)
            return True

    def _enqueue_segment(self, session: _TextSession, text: str) -> None:
        if not session.queued:
            session.queued = True
            with self._idle_condition:
                self._pending_jobs += 1
            self._jobs.put(session)
        session.segments.put(text)

    def _session_audio(self, session: _TextSession) -> Iterable[bytes]:
        while True:
            segment = session.segments.get()
            try:
                if segment is _SESSION_END:
                    return
                try:
                    if self.engine is None:
                        self.engine = self._engine_factory()
                    yield from self.engine.stream(segment)
                except Exception as exc:
                    self.last_error = exc
                    LOGGER.exception("TTS 会话 %s 合成失败", session.session_id)
            finally:
                session.segments.task_done()

    def _playback_loop(self) -> None:
        while True:
            session = self._jobs.get()
            try:
                if session is _STOP:
                    return
                try:
                    if self._sink is None:
                        self._sink = self._audio_sink_factory()
                    self._sink.play(self._session_audio(session), None)
                except Exception as exc:
                    self.last_error = exc
                    LOGGER.exception("TTS 会话 %s 播放失败", session.session_id)
                finally:
                    with self._idle_condition:
                        self._pending_jobs -= 1
                        self._idle_condition.notify_all()
            finally:
                self._jobs.task_done()

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        """Wait until every submitted session has finished playback."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle_condition:
            while self._pending_jobs:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._idle_condition.wait(remaining)
            return True

    def stop(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Reject new input and finish all already-submitted sessions."""
        with self._session_lock:
            if not self._accepting:
                return
            self._accepting = False
            for session in self._sessions.values():
                if session.queued:
                    session.segments.put(_SESSION_END)
            self._sessions.clear()
            self._jobs.put(_STOP)

        if wait:
            self._worker.join(timeout)
        if self._worker.is_alive() and self._sink is not None:
            self._sink.close()
        if self.engine is not None:
            self.engine.close()

    close = stop

    def __enter__(self) -> "manager":
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()


TTSManager = manager
