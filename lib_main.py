import robotstate
from lib_helper import func_name
import json, os, logging, queue, time, uuid, threading
import LLM.LLM_Frontend, LLM.LLM_Backend
from TTS.TTS_manager import manager as TTS
from Display.display import manager as Display, publish_robot_state
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
        self.question_list: list[dict] = [] # { "id": "", "content": "" }
        self.question_list_lock = threading.Lock()
        self.LLMF_input_queue: queue.Queue[int] = queue.Queue() # 看有没有东西，有东西就直接走流程，没有就卡住

        self.RS = robotstate.RobotState.from_dict(rs_json)
        self.LLMF = LLM.LLM_Frontend.LLM()
        self.LLMB = LLM.LLM_Backend.LLM()
        self.TTS = TTS()
        self.STT = None
        self.VisualHandler = Display()

        self.CP_manager = manager()
        self.CP_manager.coroutine_set(rs_json.get("CoroutinePool", {}))
        self.CP_processor = processor()


    def stop(self) -> None:
        self.running = False
        self.VisualHandler.stop()
        self.TTS.stop()
        obj = self.RS.to_dict()
        obj["CoroutinePool"] = self.CP_manager.coroutine_get()
        with open(self.storage_path, "w+", encoding="utf-8") as f: json.dump(obj, f, indent=3)

    def run(self) -> None:
        self.running = True
        self.VisualHandler.start()
        threading.Thread(target=self.STT_thread, daemon=True).start()
        threading.Thread(target=self.TTS_thread, daemon=True).start()
        threading.Thread(target=self.LLMB_thread, daemon=True).start()
        threading.Thread(target=self.LLMF_thread, daemon=True).start()
        threading.Thread(target=self.CP_iter_thread, daemon=True).start()
        threading.Thread(target=self.CP_message_parsing_thread, daemon=True).start()
        threading.Thread(target=self.Visualization_output_thread, daemon=True).start()

    # 线程

    def CP_message_parsing_thread(self): 
        """解析并路由协程池的输出，同时负责processor.exit对协程池的更新"""
        while self.running:
            while self.CP_processor_output_queue.empty(): 
                time.sleep(0.5)
                if not self.running: return
            message: dict = self.CP_processor_output_queue.get()[1]
            message_type = message.get("type", None)
            if message_type == "speak": 
                content = message.get("content", "")
                if content: 
                    uid = str(uuid.uuid4())
                    self.speaker_queue.put({"id": uid, "content": self.TTS.speak_start_signal})
                    self.speaker_queue.put({"id": uid, "content": content})
                    self.speaker_queue.put({"id": uid, "content": self.TTS.speak_end_signal})
            elif message_type == "frontend_reply": 
                content = message.get("content", "")
                if content: self.RS.info_append(content) # 这里frontend_reply的instruction直接进info通道
                self.LLMF_input_queue.put(1)
            elif message_type == "question":
                content = message.get("content", None)
                id = message.get("id", None)
                if content and id:
                    question = {"id": id, "content": content}
                    with self.question_list_lock: 
                        if question not in self.question_list: self.question_list.append(question)
            elif message_type == "exit": self.CP_manager.coroutine_exit(message.get("id", None))

    def CP_iter_thread(self):
        """运行协程池"""
        while self.running:
            self.CP_processor.Iter(self.CP_manager.coroutine_get(), self.RS, self.CP_processor_output_queue)
            time.sleep(0.5)

    def LLMB_thread(self): 
        """使用LLMB维护协程池并回答问题"""
        while self.running:
            cp_update_data = self.LLMB.cp_update(self.CP_manager.coroutine_get(), self.RS.to_dict())
            self.CP_manager.coroutine_update(cp_update_data)
            with self.question_list_lock: questions = self.question_list[:]
            if not questions: 
                time.sleep(2)
                continue
            answers = self.LLMB.question(questions, self.RS.to_dict())
            for answer in answers: 
                self.CP_processor.inbox_input(answer)
                with self.question_list_lock: 
                    answer_id = answer.get("id")
                    if answer_id is not None: self.question_list = [ q for q in self.question_list if q.get("id") != answer_id ]

    def LLMF_thread(self): 
        """LLMF"""
        while self.running:
            while self.LLMF_input_queue.empty(): 
                time.sleep(0.5)
                if not self.running: return
            while not self.LLMF_input_queue.empty(): self.LLMF_input_queue.get()
            self.RS.STM_append(self.LLMF.Chat(self.RS.to_dict(), self.speaker_queue))
            self.RS.info_clear()

    def Visualization_output_thread(self):
        """State视觉输出"""
        while self.running:
            try:
                publish_robot_state(self.RS, self.VisualHandler)
            except (TypeError, ValueError) as e:
                logging.warning(f"{func_name()}: {e}")
            time.sleep(0.25)

    def STT_thread(self): # 待完成
        """STT"""
        while self.running: 
            self.RS.STM_append({"role": "user", "content": input(">>> ").strip()})
            self.LLMF_input_queue.put(1)

    def TTS_thread(self):
        """TTS"""
        while self.running:
            while self.speaker_queue.empty(): 
                time.sleep(0.5)
                if not self.running: return
            self.TTS.speak_stream(self.speaker_queue.get())
