from __future__ import annotations

import asyncio
import random
import threading
import re
from pathlib import Path
from typing import List, Optional, Tuple
import base64
import time

from .planner import FillAction


class BrowserAdapter:
    def open(self):
        raise NotImplementedError

    def goto(self, url: str, wait_seconds: float = 0.0):
        raise NotImplementedError

    def apply_actions(self, actions: List[FillAction], delay_seconds: float = 0.0):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class BrowserUseAdapter(BrowserAdapter):
    """Adapter that executes FillActions using the browser-use library (headful).

    Notes:
    - Requires a GUI environment (non-headless). On Windows/PowerShell this
      opens a visible Chromium/Chrome window. On headless Linux containers it
      will likely fail; run locally if you need to see the browser.
    - Uses the event-driven BrowserSession API to navigate and interact.
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        window_size: Optional[Tuple[int, int]] = None,
        highlight: Optional[bool] = None,
        cross_origin_iframes: Optional[bool] = None,
        debug: bool = False,
        screenshots: bool = True,
        screenshot_dir: Optional[str] = None,
        screenshot_every: int = 1,
    ):
        # Lazy imports here; raise a helpful error if missing
        try:
            from browser_use import BrowserSession  # type: ignore
            from browser_use.dom.service import DomService  # type: ignore
            from browser_use.browser.events import (  # type: ignore
                NavigateToUrlEvent,
                TypeTextEvent,
                ClickElementEvent,
                SelectDropdownOptionEvent,
                UploadFileEvent,
                GetDropdownOptionsEvent,
            )
        except Exception as e:
            raise RuntimeError(
                "browser-use is not installed. Install with `uv add browser-use` "
                "and ensure Playwright/Chromium dependencies are set up."
            ) from e

        # Stash imported symbols on self to avoid re-imports
        self._BrowserSession = BrowserSession  # type: ignore[attr-defined]
        self._DomService = DomService  # type: ignore[attr-defined]
        self._NavigateToUrlEvent = NavigateToUrlEvent  # type: ignore[attr-defined]
        self._TypeTextEvent = TypeTextEvent  # type: ignore[attr-defined]
        self._ClickElementEvent = ClickElementEvent  # type: ignore[attr-defined]
        self._SelectDropdownOptionEvent = SelectDropdownOptionEvent  # type: ignore[attr-defined]
        self._UploadFileEvent = UploadFileEvent  # type: ignore[attr-defined]
        self._GetDropdownOptionsEvent = GetDropdownOptionsEvent  # type: ignore[attr-defined]

        import os

        # Resolve headless preference: default to headful unless explicitly overridden
        if headless is None:
            headless = False
        self._headless = bool(headless)

        # Window and visual options
        try:
            # Allow env overrides for size
            import os

            env_w = int(os.getenv("BROWSER_WINDOW_WIDTH", "1200"))
            env_h = int(os.getenv("BROWSER_WINDOW_HEIGHT", "800"))
        except Exception:
            env_w, env_h = 1200, 800
        if window_size:
            self._win_w, self._win_h = window_size
        else:
            self._win_w, self._win_h = env_w, env_h

        if highlight is None:
            try:
                highlight = os.getenv("BROWSER_HIGHLIGHT", "1").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            except Exception:
                highlight = True
        self._highlight = bool(highlight)

        if cross_origin_iframes is None:
            try:
                cross_origin_iframes = os.getenv("BROWSER_CROSS_IFRAMES", "1").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            except Exception:
                cross_origin_iframes = True
        self._coi = bool(cross_origin_iframes)

        self._debug = bool(debug)
        self._screenshots = bool(screenshots)
        self._screenshot_every = max(1, int(screenshot_every or 1))
        self._screenshot_dir = Path(
            screenshot_dir or "form_filler_bot/test_pages/screenshots"
        ).resolve()

        self._session = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Human-like key delay configuration (ms)
        try:
            import os

            self._key_delay_min_ms = max(0, int(os.getenv("BROWSER_KEY_DELAY_MS_MIN", "25")))
            self._key_delay_max_ms = max(
                self._key_delay_min_ms, int(os.getenv("BROWSER_KEY_DELAY_MS_MAX", "85"))
            )
        except Exception:
            self._key_delay_min_ms, self._key_delay_max_ms = 25, 85

        # Typing mode: 'keystrokes' (page-level keys) or 'node' (element-scoped typing)
        try:
            import os
            tm = (os.getenv("BROWSER_TYPING_MODE", "node").strip().lower() or "node")
        except Exception:
            tm = "node"
        if tm not in {"keystrokes", "node"}:
            tm = "node"
        self._typing_mode = tm

    # -------------------- logging and screenshots --------------------
    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"LOG: {msg}")

    # -------------------- low-level CDP helpers --------------------
    async def _css_for_node(self, node) -> Optional[str]:
        try:
            attrs = getattr(node, "attributes", {}) or {}
            id_ = attrs.get("id")
            name_ = attrs.get("name")
            tag = (getattr(node, "node_name", None) or "").lower() or "input"
            if id_:
                return f"#{id_}"
            if name_:
                return f'{tag}[name="{name_}"]'
            return None
        except Exception:
            return None

    async def _eval_js_in_node_context(self, node, script: str):
        """Evaluate JS in the node's browsing context and return the value if any.

        Note: we use this only for passive checks (e.g., verifying focus), not for
        setting values directly, to avoid bot-detection heuristics.
        """
        try:
            cdp = await self._session.cdp_client_for_node(node)  # type: ignore[union-attr]
            res = await cdp.cdp_client.send.Runtime.evaluate(
                params={
                    "expression": script,
                    "includeCommandLineAPI": True,
                    "awaitPromise": False,
                    "returnByValue": True,
                },
                session_id=cdp.session_id,
            )
            try:
                return res.get("result", {}).get("value", None)
            except Exception:
                return None
        except Exception as e:
            self._log(f"eval_js failed: {e}")
            return None

    # JS set/select helpers removed; only passive checks remain.

    async def _screenshot(self, label: str) -> Optional[Path]:
        if not self._screenshots or not self._session:
            return None
        try:
            # Lazy import
            from browser_use.browser.events import ScreenshotEvent  # type: ignore
        except Exception:
            return None

        # Ensure directory
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        ts = int(time.time() * 1000)
        safe_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)[:50]
        out = self._screenshot_dir / f"{ts}_{safe_label}.png"
        try:
            ev = self._session.event_bus.dispatch(ScreenshotEvent(full_page=True))  # type: ignore[union-attr]
            await ev
            data = await ev.event_result(raise_if_any=True, raise_if_none=False)
            # Event returns base64 string
            if isinstance(data, str):
                with open(out, "wb") as f:
                    f.write(base64.b64decode(data))
                print(f"SCREENSHOT: {out}")
                return out
        except Exception as e:
            self._log(f"screenshot failed: {e}")
        return None

    async def _scroll_node_into_view(self, node) -> None:
        try:
            sel = await self._css_for_node(node)
            if not sel:
                return
            js = (
                "(() => {"
                f" const el = document.querySelector({repr(sel)});"
                " if (!el) return false;"
                " try { el.scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'}); } catch (e) {}"
                " return true;"
                "})()"
            )
            await self._eval_js_in_node_context(node, js)
            await self._human_sleep(40, 90)
        except Exception:
            pass

    async def _is_node_focused(self, node) -> bool:
        """Return True if document.activeElement matches the node.

        Uses CSS path derived from node attributes to compare against activeElement.
        If we can't build a selector, we best-effort assume focus is fine.
        """
        try:
            sel = await self._css_for_node(node)
            if not sel:
                return True
            js = (
                "(() => {"
                f" const el = document.querySelector({repr(sel)});"
                " if (!el) return false;"
                " return document.activeElement === el;"
                "})()"
            )
            val = await self._eval_js_in_node_context(node, js)
            return bool(val)
        except Exception:
            return True

    async def _find_label_for(self, dom, input_node) -> Optional["EnhancedDOMTreeNode"]:
        """Best-effort: find a <label for="..."> that references the input node's id."""
        try:
            attrs = getattr(input_node, "attributes", {}) or {}
            nid = attrs.get("id")
            if not nid:
                return None
            # Look through selector map for matching label
            sm = await self._session.get_selector_map()  # type: ignore[union-attr]
            nodes = list(sm.values()) if isinstance(sm, dict) else []
            for n in nodes:
                try:
                    if (getattr(n, "node_name", "") or "").lower() == "label":
                        if (getattr(n, "attributes", {}) or {}).get("for") == nid:
                            return n
                except Exception:
                    continue
        except Exception:
            return None
        return None

    async def _human_sleep(
        self, min_ms: Optional[int] = None, max_ms: Optional[int] = None
    ) -> None:
        try:
            lo = self._key_delay_min_ms if min_ms is None else int(min_ms)
            hi = self._key_delay_max_ms if max_ms is None else int(max_ms)
            if hi < lo:
                hi = lo
            delay = random.uniform(lo / 1000.0, hi / 1000.0)
            await asyncio.sleep(delay)
        except Exception:
            # Best-effort sleep fallback
            try:
                await asyncio.sleep(0.04)
            except Exception:
                pass

    async def _type_text_human(self, text: str) -> None:
        """Type text as individual keystrokes with human-like delays.

        Assumes the desired element is already focused (we click before calling).
        """
        if not text:
            return
        try:
            from browser_use.browser.events import SendKeysEvent  # type: ignore
        except Exception:
            return
        for ch in text:
            try:
                ev = self._session.event_bus.dispatch(SendKeysEvent(keys=str(ch)))  # type: ignore[union-attr]
                await ev
                await ev.event_result(raise_if_any=True, raise_if_none=False)
            except Exception:
                # Continue best-effort
                pass
            await self._human_sleep()

    async def _type_text_once(self, text: str) -> None:
        """Type text in one go via keystrokes (no per-char delays)."""
        if not text:
            return
        try:
            from browser_use.browser.events import SendKeysEvent  # type: ignore
        except Exception:
            return
        ev = self._session.event_bus.dispatch(SendKeysEvent(keys=str(text)))  # type: ignore[union-attr]
        await ev
        await ev.event_result(raise_if_any=True, raise_if_none=False)

    # Removed key-event specific helpers to avoid accidental form submits.

    async def _type_text_node(self, node, text: str) -> None:
        """Type text directly into the node using element-scoped typing (clear existing)."""
        if not text:
            return
        tev = self._session.event_bus.dispatch(  # type: ignore[union-attr]
            self._TypeTextEvent(node=node, text=str(text), clear_existing=True)
        )
        await tev
        await tev.event_result(raise_if_any=True, raise_if_none=False)

    # Node-bound typing helper removed; keystrokes-only strategy.

    # -------------------- loop management --------------------
    def _ensure_loop(self):
        if self._loop and self._thread and self._thread.is_alive():
            return
        self._loop = asyncio.new_event_loop()

        def _run_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, args=(self._loop,), daemon=True)
        self._thread.start()

    def _run(self, coro, timeout: float = 120):
        self._ensure_loop()
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # -------------------- public API --------------------
    def open(self):
        """Launch a headful browser session."""
        if self._session is not None:
            return

        async def _run():
            # Allow headless in CI via flag/env; devtools optional
            self._log(
                f"opening browser: headless={self._headless} size=({self._win_w}x{self._win_h}) highlight={self._highlight} cross_iframes={self._coi}"
            )
            # Fresh screenshots directory each run (if enabled)
            if self._screenshots:
                try:
                    import shutil

                    if self._screenshot_dir.exists():
                        shutil.rmtree(self._screenshot_dir, ignore_errors=True)
                    self._screenshot_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._log(f"screenshot dir cleanup failed: {e}")
            session = self._BrowserSession(
                headless=self._headless,
                devtools=False,
                window_size={"width": self._win_w, "height": self._win_h},
                viewport={"width": self._win_w, "height": self._win_h},
                highlight_elements=self._highlight,
                cross_origin_iframes=self._coi,
                minimum_wait_page_load_time=1.0,
                wait_for_network_idle_page_load_time=1.5,
            )
            await session.start()
            try:
                # Try to get existing selector map without forcing an update
                sm = await session.get_selector_map()
                size = len(sm) if isinstance(sm, dict) else 0
                self._log(f"open: selector_map size={size}")
            except Exception as e:
                self._log(f"open: unable to get selector_map: {e}")
            return session

        self._session = self._run(_run())

    def goto(self, url: str, wait_seconds: float = 0.0):
        if not self._session:
            raise RuntimeError("Adapter not opened. Call open() first.")

        # Allow local file navigation for offline HTML snapshots
        def _to_uri(u: str) -> str:
            if re.match(r"^https?://", u, re.I):
                return u
            if re.match(r"^file://", u, re.I):
                return u
            if u:
                p = Path(u)
                return p.resolve().as_uri()
            return u

        target = _to_uri(url)
        self._log(f"goto: requested={url} resolved={target}")

        async def _run():
            # Use session helper (wraps event bus)
            await self._session.navigate_to(target)  # type: ignore[union-attr]
            if wait_seconds and wait_seconds > 0:
                try:
                    await asyncio.sleep(wait_seconds)
                except Exception:
                    pass
            try:
                # Read existing selector map (may be empty until watchdogs run)
                sm = await self._session.get_selector_map()  # type: ignore[union-attr]
                size = len(sm) if isinstance(sm, dict) else 0
                # Basic tag histogram for quick visibility into the DOM
                tag_counts = {}
                if isinstance(sm, dict):
                    for n in sm.values():
                        try:
                            tag = (getattr(n, "node_name", None) or "").lower()
                            if tag:
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                        except Exception:
                            pass
                # Only log top tags (keep concise)
                top = ", ".join(
                    f"{k}:{v}"
                    for k, v in list(
                        sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)
                    )[:6]
                )
                self._log(f"after_goto: selector_map size={size} tags=[{top}]")
            except Exception as e:
                self._log(f"after_goto: get_selector_map failed: {e}")
            await self._screenshot("after_goto")

        self._run(_run())

    def apply_actions(self, actions: List[FillAction], delay_seconds: float = 0.0):
        if not self._session:
            raise RuntimeError("Adapter not opened. Call open() first.")

        async def _apply():
            # Get a DOM service for querying elements
            dom = self._DomService(self._session)  # type: ignore[arg-type]
            try:
                sm = await self._session.get_selector_map()  # type: ignore[union-attr]
                size = len(sm) if isinstance(sm, dict) else 0
                self._log(f"apply: selector_map size at start={size}")
            except Exception as e:
                self._log(f"apply: unable to read selector_map: {e}")

            for idx, a in enumerate(actions, start=1):
                # Optional per-action delay for visibility
                if delay_seconds and delay_seconds > 0:
                    try:
                        await asyncio.sleep(delay_seconds)
                    except Exception:
                        pass
                lbl_slug = "".join(
                    c if (c.isalnum() or c in ("-", "_", " ")) else "_"
                    for c in str(a.field.label or a.field.name or a.field.id or "")[:80]
                ).strip().replace(" ", "-").lower()
                self._log(
                    f"action {idx}: op={a.op} selector={a.selector} tag={a.field.tag} type={a.field.type} label={a.field.label or ''} value={(a.value or '')[:40]}"
                )
                # Pre-action screenshot for visibility
                if self._screenshots:
                    try:
                        suffix = f"_{lbl_slug}" if lbl_slug else ""
                        await self._screenshot(f"before_action_{idx}{suffix}")
                    except Exception:
                        pass
                node = await self._find_node_by_selector(dom, a.selector, a.field.tag, a.field.type)
                if node is None:
                    self._log(f"action {idx}: node not found; will try selector fallback")
                    if self._screenshots:
                        try:
                            suffix = f"_{lbl_slug}" if lbl_slug else ""
                            await self._screenshot(f"action_{idx}_node_not_found{suffix}")
                        except Exception:
                            pass
                else:
                    try:
                        attrs = getattr(node, "attributes", {}) or {}
                        nid = attrs.get("id")
                        nname = attrs.get("name")
                        ntype = attrs.get("type")
                        ntag = (getattr(node, "node_name", None) or "").lower()
                        vis = getattr(node, "is_visible", None)
                        self._log(
                            f"action {idx}: node resolved tag={ntag} id={nid} name={nname} type={ntype} visible={vis}"
                        )
                    except Exception:
                        pass

                # Skip hidden inputs to avoid no-op typing
                try:
                    if (a.field.type or "").lower() == "hidden":
                        self._log(f"action {idx}: skipping hidden field")
                        continue
                except Exception:
                    pass

                if a.op == "type":
                    # Click to focus, then wait and verify focus before human-like keystrokes.
                    # Justification: Real users click into a field and type. We avoid any
                    # programmatic focus or value-setting to better emulate human behavior and
                    # reduce bot-detection risk. We use only a passive focus check.
                    try:
                        if node is None:
                            self._log(f"action {idx}: type skipped - node not found")
                        else:
                            # Scroll into view then focus by clicking
                            await self._scroll_node_into_view(node)
                            cev = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                            await cev
                            await cev.event_result(raise_if_any=True, raise_if_none=False)
                            # Small settle delay to allow focus to settle
                            await self._human_sleep(80, 140)
                            # Verify focus; we do not click labels or use JS focus, only passive check
                            focused = await self._is_node_focused(node)
                            if not focused:
                                lbl = a.field.label or a.field.name or a.field.id or ""
                                self._log(
                                    f"action {idx}: field not focused after click; continuing with element-scoped typing (label='{lbl}', selector='{a.selector}')"
                                )
                            expected = a.value or ""
                            if self._typing_mode == "node":
                                # Element-scoped typing (more reliable on complex sites)
                                await self._type_text_node(node, expected)
                                self._log(
                                    f"action {idx}: typed via node (clear_existing) result=None"
                                )
                            else:
                                # Human-like keystrokes to currently-focused element
                                await self._type_text_human(expected)
                                self._log(
                                    f"action {idx}: typed via keys (focused element) result=None"
                                )
                            # Allow a brief settle before verifying typed value
                            await self._human_sleep(60, 120)
                            # Verify text was entered; descriptive error if mismatch
                            try:
                                sel = await self._css_for_node(node)
                                js_val = (
                                    "(() => {"
                                    f" const el = document.querySelector({repr(sel)});"
                                    " if (!el) return null;"
                                    " return (el.value ?? el.textContent ?? '').toString();"
                                    "})()"
                                )
                                current = await self._eval_js_in_node_context(node, js_val)
                                if not isinstance(current, str) or (expected and current.strip() != expected.strip()):
                                    # Special-case: Datadog/Greenhouse resume textarea is hidden until 'enter manually' clicked
                                    try:
                                        if (sel and ("resume_text" in sel or "resume" in (a.field.label or '').lower())):
                                            self._log(
                                                f"action {idx}: attempting to reveal resume textarea via paste toggle before retyping"
                                            )
                                            _ = await self._eval_js_in_node_context(
                                                node,
                                                "(() => { const b = document.querySelector(\"button[data-source='paste']\"); if (b) { b.click(); return true;} return false; })()",
                                            )
                                            await self._human_sleep(100, 180)
                                    except Exception:
                                        pass
                                    # One more keystroke-only attempt: re-click + type all at once
                                    self._log(
                                        f"action {idx}: first verify failed (have={current!r}); retrying keys in one batch"
                                    )
                                    cev3 = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                                    await cev3
                                    await cev3.event_result(raise_if_any=True, raise_if_none=False)
                                    await self._human_sleep(60, 100)
                                    await self._type_text_once(expected)
                                    await self._human_sleep(60, 120)
                                    current = await self._eval_js_in_node_context(node, js_val)
                                    if not isinstance(current, str) or (expected and current.strip() != expected.strip()):
                                        # Final fallback for hidden/JS-driven controls (e.g., Greenhouse resume_text): set via JS
                                        try:
                                            if sel and ("resume_text" in sel or "resume" in (a.field.label or '').lower()):
                                                js_set = (
                                                    "(() => {"
                                                    f" const el = document.querySelector({repr(sel)});"
                                                    " if (!el) return null;"
                                                    f" el.value = {repr(expected)};"
                                                    " el.dispatchEvent(new Event('input', {bubbles: true}));"
                                                    " return el.value;"
                                                    "})()"
                                                )
                                                _ = await self._eval_js_in_node_context(node, js_set)
                                                await self._human_sleep(60, 120)
                                                current = await self._eval_js_in_node_context(node, js_val)
                                        except Exception:
                                            pass
                                        if not isinstance(current, str) or (expected and current.strip() != expected.strip()):
                                            lbl = a.field.label or a.field.name or a.field.id or ""
                                            raise RuntimeError(
                                                f"Keystrokes did not apply to field (label='{lbl}', selector='{a.selector}', expected='{expected}', got='{current}')"
                                            )
                            except RuntimeError:
                                # Bubble up after taking a targeted screenshot
                                if self._screenshots:
                                    try:
                                        suffix = f"_{(a.field.label or a.field.name or a.field.id or '').strip().replace(' ', '-').lower()}"
                                        await self._screenshot(f"action_{idx}_type_verify_failed{suffix}")
                                    except Exception:
                                        pass
                                raise
                    except Exception as e:
                        self._log(f"action {idx}: type failed: {e}")
                        if self._screenshots:
                            try:
                                suffix = f"_{lbl_slug}" if lbl_slug else ""
                                await self._screenshot(f"action_{idx}_type_error{suffix}")
                            except Exception:
                                pass
                        raise

                elif a.op == "select":
                    # Prefer event-based selection to avoid accidental form submits from Enter.
                    select_text = a.value or ""
                    if select_text:
                        # For native <select>, avoid clicking (watchdog disallows); just scroll into view
                        try:
                            if node is None:
                                self._log(f"action {idx}: select skipped - node not found")
                            else:
                                await self._scroll_node_into_view(node)
                                await self._human_sleep(25, 55)
                        except Exception:
                            pass

                        # Try selecting by provided text directly
                        try:
                            if node is not None:
                                ev = self._session.event_bus.dispatch(
                                    self._SelectDropdownOptionEvent(node=node, text=select_text)
                                )
                                await ev
                                res = await ev.event_result(raise_if_any=True, raise_if_none=False)
                                self._log(
                                    f"action {idx}: select by text ok result={type(res).__name__ if res is not None else 'None'}"
                                )
                                # Done
                                continue
                        except Exception as e:
                            self._log(f"action {idx}: select by text failed: {e}")

                        # Fallback: fetch options and map value -> label, then select by label
                        try:
                            gev = None
                            if node is not None:
                                gev = self._session.event_bus.dispatch(
                                    self._GetDropdownOptionsEvent(node=node)
                                )
                            await gev
                            data = await gev.event_result(
                                raise_if_any=True, raise_if_none=False
                            )
                            self._log(
                                f"action {idx}: select fetched options: has_data={data is not None}"
                            )
                            if isinstance(data, dict) and "options" in data:
                                opts = data.get("options") or []
                                label = None
                                for opt in opts:
                                    if not isinstance(opt, dict):
                                        continue
                                    if str(opt.get("value", "")).strip() == select_text:
                                        label = str(opt.get("text", select_text))
                                        break
                                if label:
                                    if node is not None:
                                        ev2 = self._session.event_bus.dispatch(
                                            self._SelectDropdownOptionEvent(
                                                node=node, text=label
                                            )
                                        )
                                    await ev2
                                    res2 = await ev2.event_result(
                                        raise_if_any=True, raise_if_none=False
                                    )
                                    self._log(
                                        f"action {idx}: select by mapped label ok result={type(res2).__name__ if res2 is not None else 'None'}"
                                    )
                                    continue
                        except Exception as e:
                            self._log(f"action {idx}: select fallback failed: {e}")
                            if self._screenshots:
                                try:
                                    suffix = f"_{lbl_slug}" if lbl_slug else ""
                                    await self._screenshot(f"action_{idx}_select_error{suffix}")
                                except Exception:
                                    pass
                            # As a last resort, try keystrokes without Enter to avoid submission
                            try:
                                if node is not None:
                                    # focus again then type text; do not press Enter
                                    await self._scroll_node_into_view(node)
                                    cev2 = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                                    await cev2
                                    await cev2.event_result(raise_if_any=True, raise_if_none=False)
                                    await self._human_sleep(25, 55)
                                    await self._type_text_human(select_text)
                            except Exception:
                                pass

                elif a.op == "check":
                    # Best-effort: focus + spacebar to toggle; also click as reinforcement
                    truthy = str(a.value).strip().lower() in {"1", "true", "yes", "on"}
                    if truthy:
                        try:
                            if node is None:
                                self._log(f"action {idx}: check skipped - node not found")
                            else:
                                await self._scroll_node_into_view(node)
                                cev = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                                await cev
                                await cev.event_result(raise_if_any=True, raise_if_none=False)
                                await self._human_sleep(15, 45)
                                from browser_use.browser.events import SendKeysEvent  # type: ignore

                                kev = self._session.event_bus.dispatch(SendKeysEvent(keys=" "))
                                await kev
                                res = await kev.event_result(raise_if_any=True, raise_if_none=False)
                                self._log(
                                    f"action {idx}: check via space result={type(res).__name__ if res is not None else 'None'}"
                                )
                        except Exception as e:
                            self._log(f"action {idx}: check keystroke failed: {e}")
                            # Still attempt a direct click as fallback
                            try:
                                if node is not None:
                                    await self._scroll_node_into_view(node)
                                    ev = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                                    await ev
                                    res2 = await ev.event_result(
                                        raise_if_any=True, raise_if_none=False
                                    )
                                    self._log(
                                        f"action {idx}: check/click fallback result={type(res2).__name__ if res2 is not None else 'None'}"
                                    )
                            except Exception:
                                pass
                            if self._screenshots:
                                try:
                                    suffix = f"_{lbl_slug}" if lbl_slug else ""
                                    await self._screenshot(f"action_{idx}_check_error{suffix}")
                                except Exception:
                                    pass
                            raise

                elif a.op == "upload":
                    if a.value:
                        # Ensure absolute path for file upload
                        p = Path(a.value)
                        file_path = str(p if p.is_absolute() else p.resolve())
                        try:
                            if node is None:
                                self._log(f"action {idx}: upload skipped - node not found")
                            else:
                                await self._scroll_node_into_view(node)
                                ev = self._session.event_bus.dispatch(self._UploadFileEvent(node=node, file_path=file_path))
                                await ev
                                res = await ev.event_result(raise_if_any=True, raise_if_none=False)
                                self._log(
                                    f"action {idx}: upload ok result={type(res).__name__ if res is not None else 'None'}"
                                )
                        except Exception as e:
                            self._log(f"action {idx}: upload failed: {e}")
                            if self._screenshots:
                                try:
                                    suffix = f"_{lbl_slug}" if lbl_slug else ""
                                    await self._screenshot(f"action_{idx}_upload_error{suffix}")
                                except Exception:
                                    pass
                            raise

                elif a.op == "click":
                    try:
                        if node is None:
                            self._log(f"action {idx}: click skipped - node not found")
                        else:
                            await self._scroll_node_into_view(node)
                            ev = self._session.event_bus.dispatch(self._ClickElementEvent(node=node))
                            await ev
                            res = await ev.event_result(raise_if_any=True, raise_if_none=False)
                            self._log(
                                f"action {idx}: click ok result={type(res).__name__ if res is not None else 'None'}"
                            )
                    except Exception as e:
                        self._log(f"action {idx}: click failed: {e}")
                        if self._screenshots:
                            try:
                                suffix = f"_{lbl_slug}" if lbl_slug else ""
                                await self._screenshot(f"action_{idx}_click_error{suffix}")
                            except Exception:
                                pass
                        raise

                # Screenshot after every action
                if self._screenshots:
                    suffix = f"_{lbl_slug}" if lbl_slug else ""
                    await self._screenshot(f"after_action_{idx}{suffix}")

        self._run(_apply())

    def close(self):
        async def _stop():
            if self._session is not None:
                try:
                    await self._session.stop()
                finally:
                    self._session = None

        try:
            self._run(_stop(), timeout=60)
        finally:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=10)
            self._loop = None
            self._thread = None

    # -------------------- helpers --------------------
    async def _find_node_by_selector(
        self,
        dom: "DomService",
        selector: str,
        tag_hint: Optional[str] = None,
        type_hint: Optional[str] = None,
    ) -> Optional["EnhancedDOMTreeNode"]:
        """Find an EnhancedDOMTreeNode using a simple CSS selector or best-effort heuristics.

        Supported selectors from our planner:
        - #id
        - tag[name="..."]
        - tag (fallback to first visible of that tag)
        """

        # Pull the selector map once per call, fallback to full DOM traversal if empty
        nodes = []
        try:
            selector_map = await self._session.get_selector_map()  # type: ignore[union-attr]
            if isinstance(selector_map, dict) and selector_map:
                nodes = list(selector_map.values())
        except Exception:
            pass
        if not nodes:
            try:
                # Build from DOM tree if cache not available
                info = await self._session.get_current_target_info()  # type: ignore[union-attr]
                target_id = info.get("targetId") if isinstance(info, dict) else None
                if target_id:
                    root = await dom.get_dom_tree(target_id)
                    # Flatten tree
                    stack = [root]
                    while stack:
                        n = stack.pop()
                        nodes.append(n)
                        try:
                            cs = getattr(n, "children_nodes", None) or []
                            for c in cs:
                                stack.append(c)
                            # include shadow roots and content_document
                            sr = getattr(n, "shadow_roots", None) or []
                            for s in sr:
                                stack.append(s)
                            cd = getattr(n, "content_document", None)
                            if cd is not None:
                                stack.append(cd)
                        except Exception:
                            pass
                else:
                    self._log("find: no current target id available")
            except Exception as e:
                self._log(f"find: dom traversal failed: {e}")

        # Try #id
        m = re.match(r"^#([A-Za-z_][\w\-:]*)$", selector)
        if m:
            id_ = m.group(1)
            self._log(f"find: by_id id={id_}")
            for n in nodes:
                try:
                    if n.attributes.get("id") == id_:
                        self._log("find: by_id matched")
                        return n
                except Exception:
                    continue

        # Try tag[name="..."]
        m = re.match(r"^([a-zA-Z0-9]+)\[name=\"([^\"]+)\"\]$", selector)
        if m:
            tag = m.group(1).lower()
            name = m.group(2)
            self._log(f"find: by_tag_name tag={tag} name={name}")
            for n in nodes:
                try:
                    if (n.node_name or "").lower() == tag and n.attributes.get("name") == name:
                        self._log("find: by_tag_name matched")
                        return n
                except Exception:
                    continue

        # Fallback: by tag and type hints, pick first visible
        tag = (tag_hint or "").lower() or None
        type_ = (type_hint or "").lower() or None
        if tag:
            self._log(f"find: by_tag_fallback tag={tag} type={type_}")
            for n in nodes:
                try:
                    if (n.node_name or "").lower() != tag:
                        continue
                    if type_ and (n.attributes.get("type", "").lower() != type_):
                        continue
                    # Prefer visible nodes
                    if getattr(n, "is_visible", None) is False:
                        continue
                    self._log("find: by_tag_fallback matched")
                    return n
                except Exception:
                    continue

        # Nothing found
        self._log("find: no match")
        return None
