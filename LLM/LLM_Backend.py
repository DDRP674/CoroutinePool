import json
import openai, os, logging
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_helper import func_name
from settings import settings
from LLM.prompts import * 

class LLM:
    def __init__(self):
        with open(settings["api_path"], "r", encoding="utf-8") as f: self.settings = json.load(f)["LLM_Backend"]

    def req(self, messagelist: list[dict]) -> dict:
        """调用OpenAI兼容的API,输入为openai格式的messagelist以及settings字典(见settings.json)
        \n返回结果为 { "role": "assistant", "content": "..."} 格式的字典
        \n如果指定json输出则content是字典
        \n如果调用失败则返回空字典{}"""
        logging.debug(f"{messagelist}")
        try:
            client = openai.OpenAI(api_key=self.settings["api_key"], base_url=self.settings["api_base"])
            if self.settings.get("response_format", False):
                completion = client.chat.completions.create(
                    model=self.settings["model"],
                    messages=messagelist,
                    temperature=self.settings.get("temperature", 1.0),
                    response_format=self.settings["response_format"]
                )
            else:
                completion = client.chat.completions.create(
                    model=self.settings["model"],
                    messages=messagelist,
                    temperature=self.settings.get("temperature", 1.0)
                )
        except Exception as e:
            logging.error(f"{func_name()}: {e}")
            return {}
        content = completion.choices[0].message.content
        logging.debug(content)
        if "response_format" in self.settings and type(content) == type(""):
            content = content.strip("`").strip("json").strip("Json")
            try: content = json.loads(content)
            except: pass
        return { "role": "assistant", "content": content }

    def question(self, questions: list[dict], robotstate_json: dict) -> list[dict]: 
        FormattedSTM = ""
        for message in robotstate_json.get("STM", []):
            if message["role"] == "assistant": FormattedSTM += "你："+message["content"]
            elif message["role"] == "user": FormattedSTM += "用户："+message["content"]
            FormattedSTM += "\n"
        if not FormattedSTM.strip(): FormattedSTM = "目前暂无对话"

        info = robotstate_json.get("info", [])
        if not info: info = "暂无"

        time = robotstate_json.get("time", "未知")

        messagelist = [{"role": "system", "content": PROMPT_Q.format(
            FormattedSTM=FormattedSTM,
            info=str(info),
            time=time,
            questions=str(questions)
        )}]

        ret_list = self.req(messagelist)
        result = []
        for ret in ret_list:
            if type(ret) == dict:
                if ret and ret.get("id", False) and (type(ret.get("answer", "")) == bool): result.append(ret)
        return result

    def cp_update(self, coroutine_json: dict, robotstate_json: dict) -> list[dict]:
        FormattedSTM = ""
        for message in robotstate_json.get("STM", []):
            if message["role"] == "assistant": FormattedSTM += "你："+message["content"]
            elif message["role"] == "user": FormattedSTM += "用户："+message["content"]
            FormattedSTM += "\n"
        if not FormattedSTM.strip(): FormattedSTM = "目前暂无对话"

        info = robotstate_json.get("info", [])
        if not info: info = "暂无"

        time = robotstate_json.get("time", "未知")

        messagelist = [{"role": "system", "content": PROMPT_CP.format(
            Character=robotstate_json.get("Character", "未指定"),
            FormattedSTM=FormattedSTM,
            info=str(info),
            State=str(robotstate_json.get("State", 0.0)),
            time=time,
            CoroutinePool=str(coroutine_json)
        )}]

        ret_list = self.req(messagelist)
        result = []
        for ret in ret_list:
            operation = ret.get("operation", None)
            if operation == "add":
                if ret.get("new_coroutine", {}): result.append(ret)
            if operation == "delete":
                if type(ret.get("id", None)) == str: result.append(ret)
        return result
