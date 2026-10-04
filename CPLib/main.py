import os, sys, queue, logging, threading
from collections import deque
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from robotstate import RobotState
from lib_helper import func_name
from CPLib.embedding import Embedder



class manager:
    """用于接收LLMB与processor.exit的信息，以更新协程池。它可以直接接收LLMB输出的json"""

    def __init__(self):
        self.lock = threading.Lock()
        self.coroutines: dict[str: dict] = {} # { "id": "", "coroutine": "" }

    def coroutine_exit(self, id: str): 
        """根据processor.exit的信息来退出协程，带锁"""
        with self.lock:
            if id in self.coroutines: del self.coroutines[id]

    def coroutine_update(self, update_data_list: list[dict]): 
        """根据协程维护LLMB的输出来更新协程池，update_data来自LLMB，带锁"""
        with self.lock:
            for update_data in update_data_list:
                update_type = update_data.get("operation", None)
                if update_type == "add":
                    new_coroutine: dict = update_data.get("new_coroutine", {})
                    id = new_coroutine.get("id", None)
                    if id: self.coroutines[id] = new_coroutine
                elif update_type == "delete":
                    id = update_data.get("id", None)
                    if id in self.coroutines: del self.coroutines[id]

    def coroutine_get(self) -> dict[str: dict]:
        """获取协程池，带锁"""
        with self.lock: return self.coroutines

    def coroutine_set(self, coroutine_json: dict[str: dict]):
        """加载协程池，带锁"""
        with self.lock: self.coroutines = coroutine_json



class processor:
    """用于执行协程。\n
    输出协议：\n
    speak: { "type": "speak", "content": "", "priority": 0 }\n
    frontend_reply: { "type": "frontend_reply", "content": "", "priority": 0 }\n
    exit: { "type": "exit", "id": id }\n
    question: { "type": "question", "content": "", "id": "", "priority": 0 }
    输入协议：\n
    question: { "type": "question", "answer": True/False, "id": "" }"""
    
    def __init__(self): 
        self.lock = threading.Lock()
        self.embedder = Embedder()
        self.inbox: deque[dict] = deque(maxlen=32)

    def Iter(self, coroutine_dict: dict[str: dict], robotstate_object: RobotState, output_queue: queue.PriorityQueue) -> None:
        """运行时，协程内容被注册进来。把这个函数套进一个循环中吧。\n
        coroutine_dict是manager那里存储的数据结构\n
        这个函数通过queue和robotstate与外界交流，output_queue是优先级队列"""
        for id, coroutine_json in coroutine_dict.items():
            if_content = coroutine_json.get("if", {})
            then_content: list[dict] = coroutine_json.get("then", [])
            else_content: list[dict] = coroutine_json.get("else", [])
            priority = coroutine_json.get("priority", 0)


            # if
            if_type = if_content.get("type", "")
            go_to_then = False

            if if_type == "semantic_match":
                op = if_content.get("operator", "")
                target_content = if_content.get("text", "")
                threshold = if_content.get("threshold", None)
                content = robotstate_object.STM_get_last_user()
                if (content and target_content) and (threshold is not None):
                    similarity = self.embedder.embed(content) @ self.embedder.embed(target_content)
                    if op == "eq": 
                        if similarity == threshold: go_to_then = True
                    elif op == "not_eq": 
                        if similarity != threshold: go_to_then = True
                    elif op == "gt": 
                        if similarity > threshold: go_to_then = True
                    elif op == "gte": 
                        if similarity >= threshold: go_to_then = True
                    elif op == "lt": 
                        if similarity < threshold: go_to_then = True
                    elif op == "lte": 
                        if similarity <= threshold: go_to_then = True
                
            elif if_type == "state_compare":
                op = if_content.get("operator", "")
                value = if_content.get("value", None)
                if value is None: pass
                else:
                    try:
                        if op == "eq": 
                            if value == robotstate_object.state_get(): go_to_then = True
                        elif op == "not_eq": 
                            if value != robotstate_object.state_get(): go_to_then = True
                        elif op == "gt": 
                            if value > robotstate_object.state_get(): go_to_then = True
                        elif op == "gte": 
                            if value >= robotstate_object.state_get(): go_to_then = True
                        elif op == "lt": 
                            if value < robotstate_object.state_get(): go_to_then = True
                        elif op == "lte": 
                            if value <= robotstate_object.state_get(): go_to_then = True
                    except TypeError: logging.warning(f"{func_name()}: state修改值类型为{type(value)}")

            elif if_type == "question": 
                answers = self.inbox_search(id)
                if answers: 
                    answer = answers[0].get("answer", False)
                    if type(answer) == bool: go_to_then = answer
                if not go_to_then: 
                    question_content = if_content.get("question", None)
                    if question_content: output_queue.put((-priority, {"type": "question", "content": question_content, "id": id, "priority": priority}))


            # then & else
            if go_to_then: self.action(then_content, robotstate_object, output_queue, priority, id)
            else: self.action(else_content, robotstate_object, output_queue, priority, id)

    # 辅助函数

    def action(self, action_content_list: list[dict], robotstate_object: RobotState, output_queue: queue.PriorityQueue, priority: int, id: str) -> None:
        for action_content in action_content_list:
            action_type = action_content.get("type", "")
            if action_type == "set_state":
                mode = action_content.get("mode", "")
                value = action_content.get("value", None)
                if isinstance(value, (float, int)):
                    if mode == "add": robotstate_object.state_add(value)
                    elif mode == "set": robotstate_object.state_get(value)
            elif action_type == "speak":
                if not isinstance(priority, (float, int)): priority = 0
                content = action_content.get("text", "")
                if content and (type(content) == str): output_queue.put((-priority, {"type": "speak", "content": content.strip()}))
            elif action_type == "append_info": 
                newinfo = action_content.get("text", "").strip()
                if newinfo: robotstate_object.info_append(newinfo)
            elif action_type == "frontend_reply":
                if not isinstance(priority, (float, int)): priority = 0
                content = action_content.get("instruction", "")
                if content is not None:
                    if content.strip(): output_queue.put((-priority, {"type": "frontend_reply", "content": content}))
            elif action_type == "exit":
                if id is not None: output_queue.put((-1024, {"type": "exit", "id": id}))
                break

    def inbox_input(self, message: dict):
        """用于从外界输入消息，带锁"""
        with self.lock: self.inbox.append(message)

    def inbox_search(self, id: str) -> list[dict]:
        """根据协程id搜索输入的所有符合id的消息并弹出。带锁"""
        results = []
        with self.lock: 
            for message in self.inbox:
                if message.get("id", None) == id: 
                    results.append(message)
                    self.inbox.remove(message)
        return results