"""LLM Backend 协程协议的完整 JSON 示例集合。

本文件中的常量都是由 dict/list/str/int/float/bool/None 组成的 JSON
兼容数据，可以直接传给 ``json.dumps``。它们仅用于展示数据结构，处理器
不应依赖示例中的具体 id、文字或数值。
"""


# ---------------------------------------------------------------------------
# 数据结构模板
# ---------------------------------------------------------------------------

COROUTINE_SCHEMA = {
    "id": "stable_unique_id",
    "description": "用一句简短中文描述这个协程的用途",
    "priority": 50,
    "if": {
        "type": "semantic_match | state_compare | question",
    },
    "then": [],
    "else": [],
}

BACKEND_OUTPUT_SCHEMA = [
    {
        "operation": "add",
        "new_coroutine": COROUTINE_SCHEMA,
    },
    {
        "operation": "delete",
        "id": "existing_coroutine_id",
    },
]


# ---------------------------------------------------------------------------
# 条件：semantic_match
# ---------------------------------------------------------------------------

CONDITION_SEMANTIC_MATCH_GTE = {
    "type": "semantic_match",
    "text": "用户在向 Agent 打招呼",
    "operator": "gte",
    "threshold": 0.75,
}

CONDITION_SEMANTIC_MATCH_LT = {
    "type": "semantic_match",
    "text": "用户希望结束当前对话",
    "operator": "lt",
    "threshold": 0.40,
}


# ---------------------------------------------------------------------------
# 条件：state_compare 的全部 operator
# ---------------------------------------------------------------------------

CONDITION_STATE_EQ = {
    "type": "state_compare",
    "operator": "eq",
    "value": 0.5,
}

CONDITION_STATE_NOT_EQ = {
    "type": "state_compare",
    "operator": "not_eq",
    "value": 0.0,
}

CONDITION_STATE_GT = {
    "type": "state_compare",
    "operator": "gt",
    "value": 0.8,
}

CONDITION_STATE_GTE = {
    "type": "state_compare",
    "operator": "gte",
    "value": 0.7,
}

CONDITION_STATE_LT = {
    "type": "state_compare",
    "operator": "lt",
    "value": 0.3,
}

CONDITION_STATE_LTE = {
    "type": "state_compare",
    "operator": "lte",
    "value": 0.2,
}


# ---------------------------------------------------------------------------
# 条件：question
# ---------------------------------------------------------------------------

CONDITION_QUESTION = {
    "type": "question",
    "question": "用户现在是否希望 Agent 主动继续这个话题？",
}


# 所有当前合法条件示例。
ALL_CONDITION_EXAMPLES = [
    CONDITION_SEMANTIC_MATCH_GTE,
    CONDITION_SEMANTIC_MATCH_LT,
    CONDITION_STATE_EQ,
    CONDITION_STATE_NOT_EQ,
    CONDITION_STATE_GT,
    CONDITION_STATE_GTE,
    CONDITION_STATE_LT,
    CONDITION_STATE_LTE,
    CONDITION_QUESTION,
]


# ---------------------------------------------------------------------------
# 动作：speak
# ---------------------------------------------------------------------------

ACTION_SPEAK = {
    "type": "speak",
    "text": "我在听。",
}


# ---------------------------------------------------------------------------
# 动作：set_state 的全部 mode
# ---------------------------------------------------------------------------

ACTION_SET_STATE_SET = {
    "type": "set_state",
    "mode": "set",
    "value": 0.5,
}

ACTION_SET_STATE_ADD = {
    "type": "set_state",
    "mode": "add",
    "value": 0.1,
}

ACTION_SET_STATE_SUBTRACT = {
    "type": "set_state",
    "mode": "add",
    "value": -0.1,
}


# ---------------------------------------------------------------------------
# 动作：append_info
# ---------------------------------------------------------------------------

ACTION_APPEND_INFO = {
    "type": "append_info",
    "content": "用户当前可能希望得到简短而直接的回答。",
}


# ---------------------------------------------------------------------------
# 动作：frontend_reply 的全部 instruction 变体
# ---------------------------------------------------------------------------

ACTION_FRONTEND_REPLY = {
    "type": "frontend_reply",
    "instruction": None,
}

ACTION_FRONTEND_REPLY_WITH_INSTRUCTION = {
    "type": "frontend_reply",
    "instruction": "主动延续刚才的话题，回复保持简短自然。",
}


# ---------------------------------------------------------------------------
# 动作：exit
# ---------------------------------------------------------------------------

ACTION_EXIT = {
    "type": "exit",
}


# 所有当前合法动作示例。
ALL_ACTION_EXAMPLES = [
    ACTION_SPEAK,
    ACTION_SET_STATE_SET,
    ACTION_SET_STATE_ADD,
    ACTION_SET_STATE_SUBTRACT,
    ACTION_APPEND_INFO,
    ACTION_FRONTEND_REPLY,
    ACTION_FRONTEND_REPLY_WITH_INSTRUCTION,
    ACTION_EXIT,
]


# ---------------------------------------------------------------------------
# 完整协程示例
# ---------------------------------------------------------------------------

# semantic_match + 单个 then 动作 + 空 else。
COROUTINE_SEMANTIC_SPEAK = {
    "id": "greet_immediately",
    "description": "用户打招呼时立即回应",
    "priority": 70,
    "if": {
        "type": "semantic_match",
        "text": "用户在向 Agent 打招呼",
        "operator": "gte",
        "threshold": 0.75,
    },
    "then": [
        {
            "type": "speak",
            "text": "你好，我在。",
        }
    ],
    "else": [],
}

# semantic_match 的 lt 分支。
COROUTINE_SEMANTIC_LT = {
    "id": "continue_when_not_ending",
    "description": "用户没有表现出结束意图时保留继续交流的提示",
    "priority": 30,
    "if": {
        "type": "semantic_match",
        "text": "用户希望结束当前对话",
        "operator": "lt",
        "threshold": 0.40,
    },
    "then": [
        {
            "type": "append_info",
            "content": "用户暂时没有表现出结束对话的意图。",
        }
    ],
    "else": [],
}

# state_compare + then/else 都包含动作。
COROUTINE_STATE_WITH_ELSE = {
    "id": "react_to_high_state",
    "description": "State 足够高时主动回复，否则逐渐恢复 State",
    "priority": 60,
    "if": {
        "type": "state_compare",
        "operator": "gte",
        "value": 0.8,
    },
    "then": [
        {
            "type": "frontend_reply",
            "instruction": "自然地发起一轮简短交流。",
        },
        {
            "type": "set_state",
            "mode": "set",
            "value": 0.3,
        },
    ],
    "else": [
        {
            "type": "set_state",
            "mode": "add",
            "value": 0.05,
        }
    ],
}

# question + 多个 then 动作。
COROUTINE_QUESTION_MULTI_ACTION = {
    "id": "comfort_when_needed",
    "description": "判断用户是否需要安慰，并组合多个简单动作",
    "priority": 80,
    "if": {
        "type": "question",
        "question": "根据当前对话，用户现在是否明显需要安慰？",
    },
    "then": [
        {
            "type": "append_info",
            "content": "用户现在可能需要安慰，下一轮回复应温和且避免说教。",
        },
        {
            "type": "set_state",
            "mode": "add",
            "value": 0.1,
        },
        {
            "type": "frontend_reply",
            "instruction": "主动安慰用户，只说一到两句话。",
        },
    ],
    "else": [],
}


# 一次性协程：执行 exit 后结束并从协程池移除自己。
COROUTINE_ONE_SHOT_EXIT = {
    "id": "one_shot_reminder",
    "description": "用户提到提醒内容时回应一次，然后自动退出",
    "priority": 70,
    "if": {
        "type": "semantic_match",
        "text": "用户提到了之前约定的一次性提醒",
        "operator": "gte",
        "threshold": 0.75,
    },
    "then": [
        {
            "type": "speak",
            "text": "记得我们刚才约定的事情。",
        },
        {
            "type": "exit",
        },
    ],
    "else": [],
}


ALL_COROUTINE_EXAMPLES = [
    COROUTINE_SEMANTIC_SPEAK,
    COROUTINE_SEMANTIC_LT,
    COROUTINE_STATE_WITH_ELSE,
    COROUTINE_QUESTION_MULTI_ACTION,
    COROUTINE_ONE_SHOT_EXIT,
]


# ---------------------------------------------------------------------------
# LLM Backend 的全部维护操作输出示例
# ---------------------------------------------------------------------------

# 不需要维护。
OUTPUT_NO_CHANGE = []

# 添加一个协程。
OUTPUT_ADD = [
    {
        "operation": "add",
        "new_coroutine": COROUTINE_SEMANTIC_SPEAK,
    }
]

# 使用相同 id 的 add 完整覆盖已有协程，即修改协程。
OUTPUT_OVERWRITE = [
    {
        "operation": "add",
        "new_coroutine": {
            "id": "greet_immediately",
            "description": "用户打招呼时立即作出更自然的回应",
            "priority": 75,
            "if": {
                "type": "semantic_match",
                "text": "用户在向 Agent 打招呼或呼唤 Agent",
                "operator": "gte",
                "threshold": 0.72,
            },
            "then": [
                {
                    "type": "frontend_reply",
                    "instruction": "简短回应用户的招呼。",
                }
            ],
            "else": [],
        },
    }
]

# 删除一个协程。
OUTPUT_DELETE = [
    {
        "operation": "delete",
        "id": "greet_immediately",
    }
]

# 一次返回多个按顺序执行的维护操作。
OUTPUT_MULTIPLE_OPERATIONS = [
    {
        "operation": "delete",
        "id": "obsolete_behavior",
    },
    {
        "operation": "add",
        "new_coroutine": COROUTINE_QUESTION_MULTI_ACTION,
    },
    {
        "operation": "add",
        "new_coroutine": COROUTINE_STATE_WITH_ELSE,
    },
]


ALL_BACKEND_OUTPUT_EXAMPLES = [
    OUTPUT_NO_CHANGE,
    OUTPUT_ADD,
    OUTPUT_OVERWRITE,
    OUTPUT_DELETE,
    OUTPUT_MULTIPLE_OPERATIONS,
]
