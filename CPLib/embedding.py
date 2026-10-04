import logging, sys, os
import numpy as np
import torch, threading
from transformers import AutoTokenizer, AutoModel
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import func_name

class Embedder: 
    def __init__(self, model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        """提前加载模型，先检查显存"""
        self.lock = threading.Lock()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logging.info(f"{func_name()}: 使用设备: {self.device}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name).to(self.device)
            self.model.eval()
            logging.info(f"{func_name()}: 成功加载模型: {model_name}")
            self.shape = self.embed(["This is a test"]).shape
        except Exception as e:
            logging.error(f"{func_name()}: 模型加载失败: {e}")
            raise

    def get_shape(self) -> tuple: return self.shape

    def embed(self, texts: list[str]|str) -> np.array:
        """将文本列表转换为嵌入向量"""
        if isinstance(texts, str): texts = [texts]
        with self.lock:
            with torch.no_grad():
                inputs = self.tokenizer(texts, padding=True, truncation=True, 
                                    max_length=512, return_tensors="pt").to(self.device)
                outputs = self.model(**inputs)
                embeddings = self.mean_pooling(outputs, inputs['attention_mask'])
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                return embeddings.cpu().numpy()

    def mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

if __name__ == "__main__":
    e = Embedder()
    a = e.embed(["hi", "hello"])
    print(a.shape)
    print(type(a), type(a[0]))
    a = a.tolist()
    print(type(a), type(a[0]))