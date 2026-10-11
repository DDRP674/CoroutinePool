import logging
from typing import Type
import assemblyai as aai
from assemblyai.streaming.v3 import (
    BeginEvent,
    StreamingClient,
    StreamingClientOptions,
    StreamingError,
    StreamingEvents,
    StreamingParameters,
    StreamingSessionParameters,
    TerminationEvent,
    TurnEvent,
)

class StreamingTranscriber:
    def __init__(self, settings: dict):
        self.api_key = settings["api_key"]
        self.api_host = settings["api_host"]
        self.settings = settings
        self.output_queue = None
        self._client = None
        self._stream = None

    def on_begin(self, client: Type[StreamingClient], event: BeginEvent):
        logging.info(f"STT.aai: Session started: {event.id}")

    def on_turn(self, client: Type[StreamingClient], event: TurnEvent):
        if event.end_of_turn: 
            if event.transcript.strip(): self.output_queue.put(event.transcript)

    def on_terminated(self, client: Type[StreamingClient], event: TerminationEvent):
        logging.info(f"STT.aai: Session terminated: {event.audio_duration_seconds} seconds of audio processed")

    def on_error(self, client: Type[StreamingClient], error: StreamingError):
        logging.error(f"Error occurred: {error}")

    def stop(self):
        """停止音频流和连接"""
        if hasattr(self, '_stream') and self._stream: self._stream = None
        if hasattr(self, '_client') and self._client:
            try: self._client.disconnect(terminate=True)
            except Exception as e: logging.warning(f"STT.aai: Error disconnecting client: {e}")
            finally: self._client = None

    def run(self, output_queue):
        """阻塞"""
        self.output_queue = output_queue
        client = StreamingClient(StreamingClientOptions(api_key=self.api_key, api_host=self.api_host,))
        self._client = client  # 保存client引用
        
        client.on(StreamingEvents.Begin, self.on_begin)
        client.on(StreamingEvents.Turn, self.on_turn)
        client.on(StreamingEvents.Termination, self.on_terminated)
        client.on(StreamingEvents.Error, self.on_error)
        
        client.connect(StreamingParameters(
            sample_rate=16000, 
            format_turns=False, 
            min_end_of_turn_silence_when_confident=self.settings["min_end_of_turn_silence_when_confident"], # 当足够置信说话停止时，过几秒才判断说话真的停止
        ))
        
        try: 
            stream = aai.extras.MicrophoneStream(sample_rate=16000)
            self._stream = stream
            client.stream(stream)
        finally: client.disconnect(terminate=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    import queue, threading
    output_queue = queue.Queue()
    def test():
        while True: print(output_queue.get())
    threading.Thread(target=test, daemon=True).start()
    ST = StreamingTranscriber({})
    threading.Thread(target=ST.run, args=(output_queue,), daemon=True).start()
    input()
    ST.stop()

