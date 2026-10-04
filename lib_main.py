import robotstate
from lib_helper import func_name
import json, os, logging, queue, time, uuid
import LLM.LLM_Frontend, LLM.LLM_Backend
from TTS.TTS_manager import manager as TTS
from CPLib.main import manager, processor

class main:
    def __init__(self):
        self.running = False
        self.storage_path = "robotstate_persistent.json"
        rs_json = {}
        if os.path.isfile(self.storage_path): 
            with open(self.storage_path, "r", encoding="utf-8") as f:
                try: 
                    rs_json = json.load(f) 
                    if type(rs_json) != dict:
                        logging.warning(f"{func_name()}: RobotState持久化Json非字典")
                        rs_json = {}
                except json.decoder.JSONDecodeError or json.JSONDecodeError: logging.warning(f"{func_name()}: RobotState持久化Json解析错误")

        self.CP_processor_output_queue: queue.PriorityQueue[dict] = queue.PriorityQueue()
        self.speaker_queue: queue.Queue[dict] = queue.Queue() # { "id": uuid, "content": str }

        self.RS = robotstate.RobotState.from_dict(rs_json)
        self.LLMF = LLM.LLM_Frontend.LLM()
        self.LLMB = LLM.LLM_Backend.LLM()
        self.TTS = TTS()
        self.STT = None
        self.VisualHandler = None

        self.CP_manager = manager()
        self.CP_manager.coroutine_set(rs_json.get("CoroutinePool", {}))
        self.CP_processor = processor()


    def stop(self) -> None:
        self.running = False
        obj = self.RS.to_dict()
        obj["CoroutinePool"] = self.CP_manager.coroutine_get()
        with open(self.storage_path, "w+", encoding="utf-8") as f: json.dump(obj, f, indent=3)

    def run(self) -> None:
        self.running = True

    # 线程

    def CP_message_parsing_thread(self): # 待完成
        """解析并路由协程池的输出，同时负责processor.exit对协程池的更新"""
        while self.running:
            while self.CP_processor_output_queue.empty(): 
                time.sleep(0.5)
                if not self.running: return
            message: dict = self.CP_processor_output_queue.get()
            message_type = message.get("type", None)
            if message_type == "speak": 
                content = message.get("content", "")
                if content: self.speaker_queue.put({"id": str(uuid.uuid4()), "content": content})
            elif message_type == "frontend_reply": pass # 待完成
            elif message_type == "question": pass # 待完成
            elif message_type == "exit": self.CP_manager.coroutine_exit(message.get("id", None))

    def CP_iter_thread(self):
        """运行协程池"""
        while self.running:
            self.CP_processor.Iter(self.CP_manager.coroutine_get(), self.RS, self.CP_processor_output_queue)
            time.sleep(0.5)

    def LLMB_thread(self): # 待完成
        """使用LLMB维护协程池并回答问题"""

    def LLMF_input_thread(self): # 待完成
        """LLMF输入"""

    def LLMF_output_thread(self): # 待完成
        """LLMF输出"""

    def Visualization_output_thread(self): # 待完成
        """State视觉输出"""

    def STT_thread(self): # 待完成
        """STT"""

    def TTS_thread(self): # 待完成
        """TTS"""
        while self.running:
            while self.speaker_queue.empty(): 
                time.sleep(0.5)
                if not self.running: return
            self.TTS.speak_stream(self.speaker_queue.get())