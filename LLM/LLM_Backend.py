import json
import openai, os, logging
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import func_name
from settings import settings

class LLM:
    def __init__(self):
        with open(settings["api_path"], "r", encoding="utf-8") as f: self.settings = json.load(f)["LLM_Backend"]

    def req(self, messagelist: list[dict], settings: dict) -> dict:
        """调用OpenAI兼容的API,输入为openai格式的messagelist以及settings字典(见settings.json)
        \n返回结果为 { "role": "assistant", "content": "..."} 格式的字典
        \n如果指定json输出则content是字典
        \n如果调用失败则返回空字典{}"""
        logging.debug(f"{messagelist}")
        try:
            client = openai.OpenAI(api_key=settings["api_key"], base_url=settings["api_base"])
            if settings.get("response_format", False):
                completion = client.chat.completions.create(
                    model=settings["model"],
                    messages=messagelist,
                    temperature=settings.get("temperature", 1.0),
                    response_format=settings["response_format"]
                )
            else:
                completion = client.chat.completions.create(
                    model=settings["model"],
                    messages=messagelist,
                    temperature=settings.get("temperature", 1.0)
                )
        except Exception as e:
            logging.error(f"{func_name()}: {e}")
            return {}
        content = completion.choices[0].message.content
        logging.debug(content)
        if "response_format" in settings and type(content) == type(""):
            content = content.strip("`").strip("json").strip("Json")
            try: content = json.loads(content)
            except: pass
        return { "role": "assistant", "content": content }
