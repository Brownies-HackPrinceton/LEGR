from __future__ import annotations

import os
from typing import Optional


class SpectrumClient:
    """
    Thin wrapper so the codebase can run even if Spectrum isn't installed.

    If you have Photon Spectrum available, install it and this will auto-enable.
    """

    def __init__(self) -> None:
        self.server_url = os.getenv("IMESSAGE_SERVER_URL")
        self.api_key = os.getenv("IMESSAGE_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.server_url and self.api_key)

    def _get_sdk(self):
        # Import lazily so local dev/test works without the dependency.
        from photon_spectrum import Spectrum  # type: ignore

        return Spectrum(server_url=self.server_url, api_key=self.api_key)

    async def send_text(self, *, to: str, text: str) -> None:
        sdk = self._get_sdk()
        await sdk.imessage.send(to=to, text=text)

    async def send_poll(self, *, to: str, question: str, options: list[str]) -> None:
        sdk = self._get_sdk()
        await sdk.imessage.send_poll(to=to, question=question, options=options)


def get_founder_phone() -> Optional[str]:
    return os.getenv("IMESSAGE_FOUNDER_PHONE")

