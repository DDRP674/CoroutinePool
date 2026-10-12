import queue
import sys
import threading
import types
import unittest
from collections import deque


# Loading the real embedding model is external and slow.  These tests exercise
# the real coroutine processor while replacing only that boundary.
embedding_module = types.ModuleType("CPLib.embedding")
embedding_module.Embedder = object
sys.modules.setdefault("CPLib.embedding", embedding_module)

from CPLib.main import manager, processor
from robotstate import RobotState


class _Vector:
    def __init__(self, similarity):
        self.similarity = similarity

    def __matmul__(self, other):
        return self.similarity


class _Embedder:
    def __init__(self, similarity=0.8):
        self.similarity = similarity

    def embed(self, text):
        return _Vector(self.similarity)


class _RobotState:
    def __init__(self, state=0, user_text="hello", user_revision=1):
        self.state = state
        self.user_text = user_text
        self.user_revision = user_revision
        self.info = []

    def state_get(self):
        return self.state

    def state_set(self, value):
        self.state = value

    def state_add(self, value):
        self.state += value

    def STM_get_last_user(self):
        return self.user_text

    def STM_get_last_user_event(self):
        return self.user_revision, self.user_text

    def info_append(self, content):
        self.info.append(content)


def _processor(similarity=0.8):
    instance = processor.__new__(processor)
    instance.lock = threading.Lock()
    instance.embedder = _Embedder(similarity)
    instance.inbox = deque(maxlen=32)
    instance._condition_observations = {}
    instance._pending_questions = {}
    instance._output_sequence = iter(range(1_000_000))
    return instance


def _branch_coroutine(condition):
    return {
        "id": "condition",
        "priority": 50,
        "if": condition,
        "then": [{"type": "speak", "text": "then"}],
        "else": [{"type": "speak", "text": "else"}],
    }


class ProcessorTests(unittest.TestCase):
    def test_equal_priority_actions_are_queued_in_action_order(self):
        output = queue.PriorityQueue()

        _processor().action(
            [
                {"type": "speak", "text": "first"},
                {"type": "speak", "text": "second"},
            ],
            _RobotState(),
            output,
            50,
            "same-priority",
        )

        self.assertEqual(output.get_nowait()[1]["content"], "first")
        self.assertEqual(output.get_nowait()[1]["content"], "second")

    def test_state_compare_uses_state_as_the_left_operand_for_every_operator(self):
        cases = [
            ("eq", 60, "then"),
            ("not_eq", 50, "then"),
            ("gt", 50, "then"),
            ("gte", 60, "then"),
            ("lt", 70, "then"),
            ("lte", 60, "then"),
            ("gt", 70, "else"),
            ("lt", 50, "else"),
        ]

        for operator, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                output = queue.PriorityQueue()
                _processor().Iter(
                    {"condition": _branch_coroutine({
                        "type": "state_compare",
                        "operator": operator,
                        "value": value,
                    })},
                    _RobotState(state=60),
                    output,
                )
                self.assertEqual(output.get_nowait()[1]["content"], expected)

    def test_semantic_compare_keeps_similarity_as_the_left_operand(self):
        for operator, threshold, expected in (
            ("gt", 0.7, "then"),
            ("gte", 0.8, "then"),
            ("lt", 0.9, "then"),
            ("lte", 0.8, "then"),
            ("gt", 0.9, "else"),
            ("lt", 0.7, "else"),
        ):
            with self.subTest(operator=operator, threshold=threshold):
                output = queue.PriorityQueue()
                _processor(similarity=0.8).Iter(
                    {"condition": _branch_coroutine({
                        "type": "semantic_match",
                        "operator": operator,
                        "text": "target",
                        "threshold": threshold,
                    })},
                    _RobotState(),
                    output,
                )
                self.assertEqual(output.get_nowait()[1]["content"], expected)

    def test_unanswered_question_waits_without_running_else_or_requeueing(self):
        instance = _processor()
        state = _RobotState(state=10)
        output = queue.PriorityQueue()
        coroutine = {
            "question": {
                "id": "question",
                "priority": 50,
                "if": {"type": "question", "question": "Is this true?"},
                "then": [{"type": "set_state", "mode": "add", "value": 5}],
                "else": [{"type": "set_state", "mode": "add", "value": -5}],
            }
        }

        instance.Iter(coroutine, state, output)
        instance.Iter(coroutine, state, output)

        self.assertEqual(state.state, 10)
        self.assertEqual(output.qsize(), 1)
        self.assertEqual(output.get_nowait()[1]["type"], "question")

    def test_false_question_answer_runs_else_once(self):
        instance = _processor()
        state = _RobotState(state=10)
        output = queue.PriorityQueue()
        coroutine = {
            "question": {
                "id": "question",
                "priority": 50,
                "if": {"type": "question", "question": "Is this true?"},
                "then": [],
                "else": [{"type": "set_state", "mode": "add", "value": -5}],
            }
        }

        instance.Iter(coroutine, state, output)
        output.get_nowait()
        instance.inbox_input({"id": "question", "answer": False})
        instance.Iter(coroutine, state, output)
        instance.Iter(coroutine, state, output)

        self.assertEqual(state.state, 5)
        self.assertTrue(output.empty())

    def test_semantic_condition_runs_once_per_user_message_revision(self):
        instance = _processor()
        state = _RobotState(user_text="same words", user_revision=1)
        output = queue.PriorityQueue()
        coroutine = {
            "semantic": _branch_coroutine({
                "type": "semantic_match",
                "operator": "gte",
                "text": "target",
                "threshold": 0.75,
            })
        }

        instance.Iter(coroutine, state, output)
        instance.Iter(coroutine, state, output)
        self.assertEqual(output.qsize(), 1)

        state.user_revision = 2
        instance.Iter(coroutine, state, output)
        self.assertEqual(output.qsize(), 2)


class ManagerTests(unittest.TestCase):
    def test_coroutine_get_returns_an_independent_nested_snapshot(self):
        pool = manager()
        pool.coroutine_set({
            "one": {"id": "one", "if": {"type": "state_compare", "value": 0}}
        })

        snapshot = pool.coroutine_get()
        snapshot["one"]["if"]["value"] = 99
        snapshot["two"] = {"id": "two"}

        self.assertEqual(pool.coroutine_get(), {
            "one": {"id": "one", "if": {"type": "state_compare", "value": 0}}
        })


class RobotStateTests(unittest.TestCase):
    def test_identical_user_text_still_gets_a_new_event_revision(self):
        state = RobotState.__new__(RobotState)
        state.lock = threading.Lock()
        state.STM = deque(maxlen=30)
        state._user_revision = 0

        state.STM_append({"role": "assistant", "content": "same words"})
        state.STM_append({"role": "user", "content": "same words"})
        state.STM_append({"role": "user", "content": "same words"})

        self.assertEqual(state.STM_get_last_user_event(), (2, "same words"))


if __name__ == "__main__":
    unittest.main()
