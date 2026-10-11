from openai import OpenAI
import os, sys, json, uuid
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import func_name
from settings import settings

PROMPT_1 = """
你的人设：{Character}

一些辅助信息：{info}

当前时间：{time}

你的心情：{State}

现在根据已有信息和对话，生成对用户的新一轮回复。
你的回复应该简短，只有1-2句话。如果你认为不需要说话，可以直接输出空字符串。
"""

class LLM:
    def __init__(self):
        with open(settings["api_path"], "r", encoding="utf-8") as f: self.settings = json.load(f)["LLM_Frontend"]
        self.client = OpenAI(api_key=self.settings["api_key"], base_url=self.settings["api_base"])
        self.start_signal = "[Start]"
        self.end_signal = "[End]"

    def StreamCall(self, messagelist: list[dict], stream_queue=None) -> dict: 
        stream = self.client.chat.completions.create(
            model=self.settings["model"],
            messages=messagelist,
            temperature=self.settings.get("temperature", 1.0),
            stream=True,
            max_tokens=1000
        )
        full_content = ""
        uid = str(uuid.uuid4())
        stream_queue.put({"id": uid, "content": self.start_signal})
        for chunk in stream:
            c = chunk.choices[0].delta.content or ""
            if stream_queue != None: stream_queue.put({"id": uid, "content": c})
            full_content += c
        stream_queue.put({"id": uid, "content": self.end_signal})
        return {"role": "assistant", "content": full_content}
    
    def Chat(self, robotstate: dict, stream_queue=None, memories: list[dict] = []) -> dict:
        """新消息将存在于robotstate，因而不需要传参\n
        memories格式：[{ "id": , "score": , "values": , "metadata": }]\n
        记忆还未实装。这个项目应该用不到"""

        # formatted_memories = ""
        # memories += formatted_robotstate.get("memories", [])
        # for i in range(len(memories)): formatted_memories += f"{i+1}: "+memories[i]["metadata"]["content"]+"\n"
        # if not formatted_memories: formatted_memories = "无相关记忆"

        system_message = [{"role": "system", "content": PROMPT_1.format(
            Character=robotstate["Character"],
            # memory=formatted_memories,
            info=str(robotstate["info"]),
            time=robotstate["time"],
            State=str(robotstate["State_tachie_name"]) # 这里之后要能与立绘对上
        )}]

        messagelist = system_message+robotstate.get("STM", [])

        return self.StreamCall(messagelist, stream_queue)
    

if __name__ == "__main__":
    a = LLM()
    import queue
    q = queue.Queue()
    res = a.StreamCall([{"role": "system", "content": PROMPT_1}, {"role": "user", "content": "可以讲个笑话吗？"}], q)
    print(res)
    while not q.empty(): print(q.get())