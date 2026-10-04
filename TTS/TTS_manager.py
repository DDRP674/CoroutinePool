# 每个不同的会话会有独立的uuid作为id，注意识别防止串线

class manager:
    def __init__(self):
        self.engine = None

    def speak_stream(self, chunk: dict): pass
        # 如果是LLMF则流式传输，如果是直接speak则不用流式传输。注意不要串线
        