"""
Monkey-patch browser_use typing to be more human-like.

Adds per-character delays and small natural pauses while typing into
elements or the focused page. Controlled by env vars:

- HUMAN_TYPE_ENABLED: 'true'|'false' (default 'true')
- HUMAN_TYPE_CHAR_DELAY_MS_MIN: e.g., '55' (default 60)
- HUMAN_TYPE_CHAR_DELAY_MS_MAX: e.g., '120' (default 120)
- HUMAN_TYPE_SPACE_EXTRA_MS: extra pause after spaces (default 60)
- HUMAN_TYPE_PUNCT_EXTRA_MS: extra pause after punctuation (default 90)

Import and call apply() once before starting the browser session.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Callable


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip().lower()
    return val in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def apply() -> None:
    if not _get_bool("HUMAN_TYPE_ENABLED", True):
        return

    try:
        # Import lazily so we don't require browser_use if not installed
        from browser_use.browser.watchdogs.default_action_watchdog import (
            DefaultActionWatchdog,
        )
        from browser_use.dom.service import EnhancedDOMTreeNode  # type: ignore
    except Exception:
        # If browser_use isn't available yet, silently skip
        return

    min_ms = max(0, _get_int("HUMAN_TYPE_CHAR_DELAY_MS_MIN", 60))
    max_ms = max(min_ms, _get_int("HUMAN_TYPE_CHAR_DELAY_MS_MAX", 120))
    space_extra_ms = max(0, _get_int("HUMAN_TYPE_SPACE_EXTRA_MS", 60))
    punct_extra_ms = max(0, _get_int("HUMAN_TYPE_PUNCT_EXTRA_MS", 90))

    punctuation = set(",.;:!?()[]{}-–—_/\\'\"@#$%^&*+<>=|`~")

    def next_delay_sec(ch: str) -> float:
        base = random.uniform(min_ms, max_ms)
        if ch == " ":
            base += space_extra_ms
        elif ch in punctuation:
            base += punct_extra_ms
        # Convert to seconds
        return base / 1000.0

    # Keep references in case needed
    _orig_type_to_page = DefaultActionWatchdog._type_to_page
    _orig_input_text = DefaultActionWatchdog._input_text_element_node_impl

    async def _type_to_page_human(self, text: str):  # type: ignore[override]
        if not text:
            return await _orig_type_to_page(self, text)

        try:
            cdp_session = await self.browser_session.get_or_create_cdp_session(target_id=None, focus=True)
            await cdp_session.cdp_client.send.Target.activateTarget(params={"targetId": cdp_session.target_id})

            for ch in text:
                # keydown
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={"type": "keyDown", "key": ch},
                    session_id=cdp_session.session_id,
                )
                # text
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={"type": "char", "text": ch},
                    session_id=cdp_session.session_id,
                )
                # keyup
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={"type": "keyUp", "key": ch},
                    session_id=cdp_session.session_id,
                )

                await asyncio.sleep(next_delay_sec(ch))
        except Exception as e:  # pragma: no cover
            # Fallback to original behavior if anything goes wrong
            return await _orig_type_to_page(self, text)

    async def _input_text_element_node_impl_human(
        self, element_node: "EnhancedDOMTreeNode", text: str, clear_existing: bool = True
    ) -> dict | None:  # type: ignore[override]
        if not text:
            # Let original handle focusing/clearing semantics for empty text
            return await _orig_input_text(self, element_node, text, clear_existing)

        try:
            # Get a CDP session for the element's frame/context
            cdp_session = await self.browser_session.cdp_client_for_node(element_node)
            cdp_client = cdp_session.cdp_client

            # Ensure element in view
            try:
                await cdp_client.send.DOM.scrollIntoViewIfNeeded(
                    params={"backendNodeId": element_node.backend_node_id},
                    session_id=cdp_session.session_id,
                )
                await asyncio.sleep(0.01)
            except Exception:
                pass

            # Resolve to object id
            result = await cdp_client.send.DOM.resolveNode(
                params={"backendNodeId": element_node.backend_node_id},
                session_id=cdp_session.session_id,
            )
            object_id: str | None = result.get("object", {}).get("objectId")
            if not object_id:
                raise RuntimeError("Could not resolve element objectId for typing")

            # Compute coordinates metadata
            meta: dict | None = None
            if element_node.absolute_position:
                ap = element_node.absolute_position
                meta = {"input_x": ap.x + ap.width / 2, "input_y": ap.y + ap.height / 2}

            # Focus the element
            try:
                await cdp_client.send.DOM.focus(
                    params={"backendNodeId": element_node.backend_node_id},
                    session_id=cdp_session.session_id,
                )
            except Exception:
                # fallback to click focus from original helper
                try:
                    await self._focus_element_simple(
                        backend_node_id=element_node.backend_node_id,
                        object_id=object_id,
                        cdp_session=cdp_session,
                        input_coordinates=meta,
                    )
                except Exception:
                    pass

            # Clear if requested
            if clear_existing:
                try:
                    await self._clear_text_field(object_id=object_id, cdp_session=cdp_session)
                except Exception:
                    pass

            # Type characters with realistic pacing
            for ch in text:
                modifiers, vk_code, base_key = self._get_char_modifiers_and_vk(ch)
                key_code = self._get_key_code_for_char(base_key)

                # keyDown
                await cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyDown",
                        "key": base_key,
                        "code": key_code,
                        "modifiers": modifiers,
                        "windowsVirtualKeyCode": vk_code,
                    },
                    session_id=cdp_session.session_id,
                )

                # small short delay to mimic keydown->char
                await asyncio.sleep(0.004)

                # char text
                await cdp_client.send.Input.dispatchKeyEvent(
                    params={"type": "char", "text": ch, "key": ch},
                    session_id=cdp_session.session_id,
                )

                # keyUp
                await cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyUp",
                        "key": base_key,
                        "code": key_code,
                        "modifiers": modifiers,
                        "windowsVirtualKeyCode": vk_code,
                    },
                    session_id=cdp_session.session_id,
                )

                # Human-like inter-character delay
                await asyncio.sleep(next_delay_sec(ch))

            return meta

        except Exception:  # pragma: no cover
            # Fallback to original behavior if anything goes wrong
            return await _orig_input_text(self, element_node, text, clear_existing)

    # Apply monkey patches
    DefaultActionWatchdog._type_to_page = _type_to_page_human  # type: ignore[assignment]
    DefaultActionWatchdog._input_text_element_node_impl = _input_text_element_node_impl_human  # type: ignore[assignment]

