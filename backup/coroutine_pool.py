"""A small pool of independent, single-if/else behavior threads.

This module only provides scheduling.  The meanings of conditions and actions
belong to the caller and are supplied through two callback functions.
"""

from __future__ import annotations

from copy import deepcopy
from queue import Queue
from threading import Lock, Thread
from typing import Any, Callable


ConditionEvaluator = Callable[[dict, dict], bool]
ActionExecutor = Callable[[dict, dict, Any], None]


class _CoroutineRuntime:
    _STOP = object()

    def __init__(
        self,
        definition: dict,
        condition_evaluator: ConditionEvaluator,
        action_executor: ActionExecutor,
    ) -> None:
        self.definition = definition
        self._condition_evaluator = condition_evaluator
        self._action_executor = action_executor
        self._inbox: Queue = Queue()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(
            target=self._run,
            name=f"coroutine-{self.definition['id']}",
            daemon=True,
        )
        self._thread.start()

    def publish(self, observation: dict) -> None:
        self._inbox.put(observation)

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._inbox.put(self._STOP)
        thread.join()
        self._thread = None

    def _run(self) -> None:
        while True:
            observation = self._inbox.get()
            if observation is self._STOP:
                return

            matched = self._condition_evaluator(
                self.definition["if"], observation
            )
            action = self.definition["then"] if matched else self.definition.get("else")
            if action is not None:
                self._action_executor(action, observation, self.definition["id"])


class CoroutinePool:
    """Owns a limited number of event-driven behavior threads.

    Definitions are plain dictionaries so an LLM can generate them and callers
    can persist :meth:`to_dict` as JSON. Runtime objects are never serialized.
    """

    def __init__(
        self,
        condition_evaluator: ConditionEvaluator,
        action_executor: ActionExecutor,
        max_size: int = 10,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self.max_size = max_size
        self._condition_evaluator = condition_evaluator
        self._action_executor = action_executor
        self._runtimes: dict[Any, _CoroutineRuntime] = {}
        self._running = False
        self._lock = Lock()

    def add(self, definition: dict) -> None:
        definition = self._validate_and_copy(definition)
        coroutine_id = definition["id"]

        with self._lock:
            if coroutine_id in self._runtimes:
                raise ValueError(f"coroutine {coroutine_id!r} already exists")
            if len(self._runtimes) >= self.max_size:
                raise ValueError("coroutine pool is full")

            runtime = _CoroutineRuntime(
                definition,
                self._condition_evaluator,
                self._action_executor,
            )
            self._runtimes[coroutine_id] = runtime
            if self._running:
                runtime.start()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            for runtime in self._runtimes.values():
                runtime.start()

    def remove(self, coroutine_id: Any) -> dict:
        with self._lock:
            try:
                runtime = self._runtimes.pop(coroutine_id)
            except KeyError as error:
                raise KeyError(f"unknown coroutine: {coroutine_id!r}") from error

        runtime.stop()
        return deepcopy(runtime.definition)

    def publish(self, observation: dict) -> None:
        with self._lock:
            if not self._running:
                raise RuntimeError("coroutine pool is not running")
            runtimes = list(self._runtimes.values())

        for runtime in runtimes:
            runtime.publish(observation)

    def stop(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._running = False

        for runtime in runtimes:
            runtime.stop()

    def to_dict(self) -> dict:
        with self._lock:
            definitions = [
                deepcopy(runtime.definition) for runtime in self._runtimes.values()
            ]
        return {"max_size": self.max_size, "coroutines": definitions}

    @classmethod
    def from_dict(
        cls,
        data: dict,
        condition_evaluator: ConditionEvaluator,
        action_executor: ActionExecutor,
    ) -> "CoroutinePool":
        if not isinstance(data, dict):
            raise TypeError("coroutine pool data must be a dictionary")
        pool = cls(
            condition_evaluator=condition_evaluator,
            action_executor=action_executor,
            max_size=data.get("max_size", 10),
        )
        definitions = data.get("coroutines", [])
        if not isinstance(definitions, list):
            raise TypeError("coroutines must be a list")
        for definition in definitions:
            pool.add(definition)
        return pool

    @staticmethod
    def _validate_and_copy(definition: dict) -> dict:
        if not isinstance(definition, dict):
            raise TypeError("coroutine definition must be a dictionary")
        missing = {"id", "if", "then"} - definition.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"coroutine definition is missing: {names}")
        try:
            hash(definition["id"])
        except TypeError as error:
            raise TypeError("coroutine id must be hashable") from error
        return deepcopy(definition)
