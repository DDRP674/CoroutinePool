import json
import re
import os
import sys

def func_name(depth=2):
    frame = sys._getframe(1)
    name = frame.f_code.co_name
    while frame.f_back is not None and depth > 1: 
        frame = frame.f_back
        name = frame.f_code.co_name+"."+name
        depth -= 1
    return name

def get_filename(dir):
    """获取一个路径下的所有文件名，单层的"""
    files = []
    with os.scandir(dir) as entries:
        for entry in entries:
            if entry.is_file():
                files.append(entry.name)
    return files

def regulate_text(text):
    # 去除方括号及其内容
    text = re.sub(r'\[.*?\]', '', text)
    # 去除星号及其内容
    text = re.sub(r'\*.*?\*', '', text)
    # 去除圆括号及其内容
    text = re.sub(r'\(.*?\)', '', text)
    # 去除剩余的单独括号、星号、减号
    text = re.sub(r'[\[\]*()-]', '', text)
    return text

def load_json_with_comments(*_) -> dict:
    """读取带有注释的JSON文件，用于加载settings.json。\n
    这个函数被淘汰了，现在改用python文件存储设置"""
    if os.path.exists("./settings.json"): file_path = "./settings.json"
    elif os.path.exists(".../settings.json"): file_path = ".../settings.json"
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    zhanweifu1 = "#占位符1#"
    zhanweifu2 = "#占位符2#"
    content = content.replace("https://", zhanweifu1)
    content = content.replace("http://", zhanweifu2)
    #print(content)
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = content.replace(zhanweifu1, "https://")
    content = content.replace(zhanweifu2, "http://")
    #print(content)
    data = json.loads(content)
    return data