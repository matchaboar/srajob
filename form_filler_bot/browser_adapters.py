from __future__ import annotations

from typing import List

from .planner import FillAction


class BrowserAdapter:
    def open(self):
        raise NotImplementedError

    def goto(self, url: str):
        raise NotImplementedError

    def apply_actions(self, actions: List[FillAction]):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class BrowserUseAdapter(BrowserAdapter):
    def __init__(self):
        # Lazy import here to avoid hard dependency during planning
        try:
            # Placeholder import — adjust when browser-use is installed
            import browser_use  # type: ignore  # noqa: F401
        except Exception as e:
            raise RuntimeError(
                "browser-use is not installed. Install with `uv add browser-use` "
                "and ensure Playwright/browser dependencies are set up."
            ) from e

        # NOTE: The browser-use public API can evolve. We intentionally keep
        # this adapter thin and provide an execution placeholder below.
        self._initialized = False

    def open(self):
        # Real implementation would initialize browser-use agent or session
        self._initialized = True

    def goto(self, url: str):
        if not self._initialized:
            raise RuntimeError("Adapter not opened. Call open() first.")
        # TODO: Implement with browser-use navigate API
        # e.g., agent.run([{"action": "goto", "url": url}])
        pass

    def apply_actions(self, actions: List[FillAction]):
        if not self._initialized:
            raise RuntimeError("Adapter not opened. Call open() first.")
        # TODO: Translate FillAction list into browser-use tasks.
        # For example (pseudo):
        # for a in actions:
        #   if a.op == 'type': agent.type(selector=a.selector, text=a.value or '')
        #   elif a.op == 'select': agent.select(selector=a.selector, value=a.value)
        #   elif a.op == 'check': agent.check(selector=a.selector, value=bool(a.value))
        #   elif a.op == 'upload': agent.upload(selector=a.selector, file_path=a.value)
        pass

    def close(self):
        # Close session if needed
        self._initialized = False

