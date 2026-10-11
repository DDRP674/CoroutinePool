import json
import threading
import unittest

from backup.coroutine_pool import CoroutinePool


class CoroutinePoolTests(unittest.TestCase):
    def test_true_condition_executes_then_action(self):
        executed = []
        completed = threading.Event()

        def execute(action, observation, coroutine_id):
            executed.append((action, observation, coroutine_id))
            completed.set()

        pool = CoroutinePool(
            condition_evaluator=lambda condition, observation: observation["matched"],
            action_executor=execute,
        )
        self.addCleanup(pool.stop)
        pool.add({"id": "reply", "if": {"kind": "matched"}, "then": {"type": "reply"}, "else": {"type": "ignore"}})
        pool.start()

        pool.publish({"matched": True, "text": "hello"})

        self.assertTrue(completed.wait(1), "the coroutine did not react to the observation")
        self.assertEqual(
            executed,
            [({"type": "reply"}, {"matched": True, "text": "hello"}, "reply")],
        )

    def test_false_condition_executes_else_action(self):
        executed = []
        completed = threading.Event()

        def execute(action, observation, coroutine_id):
            executed.append(action)
            completed.set()

        pool = CoroutinePool(
            condition_evaluator=lambda condition, observation: False,
            action_executor=execute,
        )
        self.addCleanup(pool.stop)
        pool.add({"id": 1, "if": {}, "then": {"type": "yes"}, "else": {"type": "no"}})
        pool.start()

        pool.publish({"value": 1})

        self.assertTrue(completed.wait(1), "the coroutine did not execute its else action")
        self.assertEqual(executed, [{"type": "no"}])

    def test_one_observation_is_broadcast_to_every_coroutine(self):
        executed_ids = []
        completed = threading.Event()
        lock = threading.Lock()

        def execute(action, observation, coroutine_id):
            with lock:
                executed_ids.append(coroutine_id)
                if len(executed_ids) == 2:
                    completed.set()

        pool = CoroutinePool(
            condition_evaluator=lambda condition, observation: True,
            action_executor=execute,
        )
        self.addCleanup(pool.stop)
        pool.add({"id": "first", "if": {}, "then": {"type": "record"}})
        pool.add({"id": "second", "if": {}, "then": {"type": "record"}})
        pool.start()

        pool.publish({"event": "user_message"})

        self.assertTrue(completed.wait(1), "not every coroutine received the observation")
        self.assertCountEqual(executed_ids, ["first", "second"])

    def test_pool_rejects_duplicate_ids_and_more_than_max_size(self):
        pool = CoroutinePool(lambda condition, observation: True, lambda action, observation, coroutine_id: None, max_size=1)
        self.addCleanup(pool.stop)
        pool.add({"id": "only", "if": {}, "then": {}})

        with self.assertRaisesRegex(ValueError, "already exists"):
            pool.add({"id": "only", "if": {}, "then": {}})

        with self.assertRaisesRegex(ValueError, "full"):
            pool.add({"id": "extra", "if": {}, "then": {}})

    def test_snapshot_contains_only_json_serializable_definitions(self):
        pool = CoroutinePool(lambda condition, observation: True, lambda action, observation, coroutine_id: None)
        self.addCleanup(pool.stop)
        definition = {"id": "saved", "if": {"field": "text"}, "then": {"type": "reply"}}
        pool.add(definition)
        pool.start()

        snapshot = pool.to_dict()

        self.assertEqual(snapshot, {"max_size": 10, "coroutines": [definition]})
        self.assertIsInstance(json.dumps(snapshot), str)

    def test_removed_coroutine_no_longer_receives_observations(self):
        executed = []
        pool = CoroutinePool(
            lambda condition, observation: True,
            lambda action, observation, coroutine_id: executed.append(coroutine_id),
        )
        self.addCleanup(pool.stop)
        pool.add({"id": "temporary", "if": {}, "then": {"type": "record"}})
        pool.start()

        removed = pool.remove("temporary")
        pool.publish({"event": "after_removal"})

        self.assertEqual(removed["id"], "temporary")
        self.assertEqual(executed, [])
        self.assertEqual(pool.to_dict()["coroutines"], [])

    def test_pool_can_be_restored_from_a_snapshot(self):
        snapshot = {
            "max_size": 3,
            "coroutines": [
                {"id": "restored", "if": {"ready": True}, "then": {"type": "reply"}}
            ],
        }

        pool = CoroutinePool.from_dict(
            snapshot,
            condition_evaluator=lambda condition, observation: True,
            action_executor=lambda action, observation, coroutine_id: None,
        )
        self.addCleanup(pool.stop)

        self.assertEqual(pool.to_dict(), snapshot)


if __name__ == "__main__":
    unittest.main()
