from collections import deque
from settings import settings
import threading
from datetime import datetime

# CoroutinePool不在这里存储

class RobotState:
    def __init__(self):
        self.lock = threading.Lock()

        with open(settings["Character_path"], "r", encoding="utf-8") as f: self.Character = f.read()
        self.STM = deque(maxlen=settings.get("STM_maxlen", 30))
        
        self.State = 0.0
        self.info = []

    def to_dict(self) -> dict:
        # 类变成json，一般prompt和退出保存时使用。带锁
        out = {}
        with self.lock:
            out["Character"] = self.Character
            out["State"] = self.State
            out["info"] = self.info
            out["STM"] = list(self.STM)
        out["State_tachie_name"] = self.state_tachie_get()
        out["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return out
            
    @classmethod
    def from_dict(cls, d: dict):
        # json便乘类，一般加载时使用
        obj = cls()
        obj.STM = deque(d.get("STM", []), maxlen=settings.get("STM_maxlen", 30))
        obj.State = d.get("State", 0.0)
        obj.info = d.get("info", [])
        return obj

    # 短期记忆

    def STM_append(self, new_memory: dict) -> None:
        """带锁"""
        with self.lock: 
            if new_memory.get("content", "").strip(): self.STM.append(new_memory)

    def STM_get_last_user(self) -> str|None:
        """获取最新的用户回复，如果没有则返回None。带锁"""
        with self.lock:
            size = len(self.STM)
            for i in range(size):
                if self.STM[size-i-1].get("role", "") == "user": return self.STM[size-i-1].get("content", None)
        return None

    # 信息通道

    def info_append(self, new_info: str) -> None:
        """带锁"""
        with self.lock: self.info.append(new_info)

    def info_clear(self) -> None:
        """一般每次对话（LLMF运行一次）要清空一次。带锁"""
        with self.lock: self.info = []

    # State相关

    def state_set(self, set_to: float) -> None:
        """将state设置为一个值，带锁"""
        with self.lock: 
            self.State = set_to
            if self.State > 100: self.State = 100
            if self.State < -100: self.State = -100

    def state_add(self, delta: float) -> None:
        """改变多少state，带锁"""
        with self.lock: 
            self.State += delta
            if self.State > 100: self.State = 100
            if self.State < -100: self.State = -100

    def state_get(self) -> float:
        """获取state，带锁"""
        with self.lock: return self.State

    def state_tachie_get(self) -> str:
        """获取state对应的tachie的文件名，不带后缀。带锁"""
        with self.lock: 
            Visualization_map = settings["Visualization_map"]
            Visualization_map = dict(sorted(Visualization_map.items(), key=lambda x: x[1]))
            for name in Visualization_map:
                if self.State <= Visualization_map[name]: return name

if __name__ == "__main__":
    a = RobotState()
    ad = a.to_dict()
    ad["State"] = 1.0