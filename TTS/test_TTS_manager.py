import os
import threading
import types
import unittest
import uuid
from unittest.mock import patch

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from TTS import TTS_manager as tts_module
from TTS.TTS_manager import manager


class FakeEngine:
    sample_rate = 24_000

    def __init__(self):
        self.texts = []
        self.spoke = threading.Event()

    def stream(self, text):
        self.texts.append(text)
        self.spoke.set()
        yield f"audio:{text}"

    def close(self):
        pass


class RecordingSink:
    def __init__(self):
        self.sessions = []

    def play(self, chunks, sample_rate):
        self.sessions.append((list(chunks), sample_rate))


class TTSManagerTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.sink = RecordingSink()
        self.tts = manager(
            engine_factory=lambda: self.engine,
            audio_sink_factory=lambda: self.sink,
        )

    def tearDown(self):
        self.tts.stop()

    def send(self, session_id, content):
        return self.tts.speak_stream({"id": session_id, "content": content})

    def test_interleaved_sessions_never_mix_text_or_audio(self):
        self.send("a", "[Start]")
        self.send("a", "你")
        self.send("b", "[Start]")
        self.send("b", "Hello")
        self.send("a", "好")
        self.send("b", " world")
        self.send("b", "[End]")
        self.send("a", "[End]")

        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, ["Hello world", "你好"])
        self.assertEqual(
            self.sink.sessions,
            [(["audio:Hello world"], None), (["audio:你好"], None)],
        )

    def test_chunks_from_multiple_calling_threads_remain_isolated(self):
        barrier = threading.Barrier(2)

        def produce(session_id, first, second):
            self.send(session_id, "[Start]")
            self.send(session_id, first)
            barrier.wait()
            self.send(session_id, second)
            self.send(session_id, "[End]")

        first = threading.Thread(target=produce, args=("a", "A1", "A2"))
        second = threading.Thread(target=produce, args=("b", "B1", "B2"))
        first.start()
        second.start()
        first.join()
        second.join()

        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertCountEqual(self.engine.texts, ["A1A2", "B1B2"])
        self.assertNotIn("A1B1A2B2", self.engine.texts)

    def test_data_without_an_active_session_is_rejected(self):
        self.assertFalse(self.send("missing", "orphan text"))
        self.assertFalse(self.send("missing", "[End]"))
        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, [])

    def test_duplicate_start_discards_old_incomplete_content(self):
        self.send("same", "[Start]")
        self.send("same", "old")
        self.send("same", "[Start]")
        self.send("same", "new")
        self.send("same", "[End]")

        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, ["new"])

    def test_chinese_sentence_is_spoken_before_end_signal(self):
        self.send("a", "[Start]")
        self.send("a", "你好。还没说完")

        self.assertTrue(self.engine.spoke.wait(timeout=1))
        self.assertEqual(self.engine.texts, ["你好。"])

        self.send("a", "[End]")
        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, ["你好。", "还没说完"])

    def test_chinese_and_english_sentence_punctuation_are_supported(self):
        self.send("mixed", "[Start]")
        self.send("mixed", "Hello!你好？继续")
        self.send("mixed", "[End]")

        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, ["Hello!", "你好？", "继续"])

    def test_logs_each_sentence_that_is_sent_to_the_tts_engine(self):
        with self.assertLogs(level="INFO") as captured:
            self.send("logged", "[Start]")
            self.send("logged", "你好。还在继续")
            self.send("logged", "[End]")
            self.assertTrue(self.tts.wait_until_idle(timeout=1))

        output = "\n".join(captured.output)
        self.assertIn("TTS 正在朗读：你好。", output)
        self.assertIn("TTS 正在朗读：还在继续", output)

    def test_one_session_keeps_playback_until_all_its_segments_finish(self):
        self.send("a", "[Start]")
        self.send("a", "A first.")
        self.assertTrue(self.engine.spoke.wait(timeout=1))

        self.send("b", "[Start]")
        self.send("b", "B sentence.")
        self.send("b", "[End]")
        self.send("a", "A second!")
        self.send("a", "[End]")

        self.assertTrue(self.tts.wait_until_idle(timeout=1))
        self.assertEqual(self.engine.texts, ["A first.", "A second!", "B sentence."])

    def test_invalid_message_is_rejected(self):
        for message in (
            None,
            {},
            {"id": "", "content": "text"},
            {"id": "a", "content": None},
        ):
            with self.subTest(message=message):
                self.assertFalse(self.tts.speak_stream(message))

    def test_edge_tts_engine_yields_only_audio_chunks(self):
        calls = []

        class FakeCommunicate:
            def __init__(self, text, voice, **options):
                calls.append((text, voice, options))

            def stream_sync(self):
                yield {"type": "WordBoundary", "text": "hello"}
                yield {"type": "audio", "data": b"first"}
                yield {"type": "audio", "data": b"second"}

        fake_edge_tts = types.SimpleNamespace(Communicate=FakeCommunicate)
        with patch.dict("sys.modules", {"edge_tts": fake_edge_tts}):
            engine = tts_module._EdgeTTSEngine(
                voice="zh-CN-XiaoxiaoNeural",
                rate="+10%",
            )
            audio = list(engine.stream("你好。"))

        self.assertEqual(audio, [b"first", b"second"])
        self.assertEqual(
            calls,
            [("你好。", "zh-CN-XiaoxiaoNeural", {
                "rate": "+10%",
                "volume": "+0%",
                "pitch": "+0Hz",
                "proxy": None,
            })],
        )


@unittest.skipUnless(
    os.environ.get("RUN_TTS_AUDIO_TEST") == "1",
    "设置 RUN_TTS_AUDIO_TEST=1 才会运行真实语音播放测试",
)
class RealSpeechPlaybackTests(unittest.TestCase):
    """Requires internet, edge-tts, and mpv or ffplay; it really speaks."""

    def test_real_edge_tts_speaks_through_the_default_audio_device(self):
        tts = manager(voice="zh-CN-XiaoxiaoNeural")
        session_id = str(uuid.uuid4())
        try:
            self.assertTrue(tts.speak_stream({"id": session_id, "content": "[Start]"}))
            self.assertTrue(
                tts.speak_stream(
                    {
                        "id": session_id,
                        "content": "你好，这是协程池的真实语音测试。Hello from Edge TTS!",
                    }
                )
            )
            self.assertTrue(tts.speak_stream({"id": session_id, "content": "[End]"}))
            self.assertTrue(tts.wait_until_idle(timeout=60), "语音播放在 60 秒内未完成")
            self.assertIsNone(tts.last_error, f"语音合成或播放失败：{tts.last_error!r}")
        finally:
            tts.stop(timeout=5)


if __name__ == "__main__":
    unittest.main()
