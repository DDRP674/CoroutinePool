import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import load_json_with_comments

# 所有启动默认叫self.engine.run且默认阻塞，所有停止默认叫self.engine.stop

class STT_app:
    def __init__(self):
        self.settings = load_json_with_comments("./settings.json")["stt"]
        self.engine_name = self.settings["stt_engine"]
        if self.engine_name == "aai": 
            import STT.aai
            self.engine = STT.aai.StreamingTranscriber(self.settings[self.engine_name])
    
    def run(self, output_queue): self.engine.run(output_queue)

    def stop(self): self.engine.stop()
        