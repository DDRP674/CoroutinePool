import sys
import types
import unittest

sys.modules.setdefault("openai", types.SimpleNamespace())

from LLM.LLM_Backend import LLM


class CoroutinePromptTests(unittest.TestCase):
    def test_cp_update_explains_current_state_range_and_frontend_meaning(self):
        captured_messages = []
        llm = LLM.__new__(LLM)

        def capture(messages):
            captured_messages.extend(messages)
            return []

        llm.req = capture

        self.assertEqual(
            llm.cp_update(
                {},
                {
                    "Character": "测试角色",
                    "State": 42.0,
                    "STM": [],
                    "info": [],
                    "time": "2026-10-11 12:00:00",
                },
            ),
            [],
        )

        prompt = captured_messages[0]["content"]
        self.assertIn("42.0", prompt)
        self.assertIn("-100", prompt)
        self.assertIn("100", prompt)
        self.assertIn("前端", prompt)
        self.assertIn("心情", prompt)
        self.assertIn("不得超出", prompt)


if __name__ == "__main__":
    unittest.main()
