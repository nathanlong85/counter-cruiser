"""Push notification providers (ntfy.sh, Pushover) and the alert handler."""

from __future__ import annotations

import logging
from typing import Protocol

import requests

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.config.models import NotificationConfig

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0


class NotificationProvider(Protocol):
    """Protocol for a push-notification transport."""

    def send(self, message: str) -> None:
        """Deliver *message*. Must not raise on network/HTTP failure."""
        ...  # pragma: no cover


class NtfyProvider:
    """Posts a plaintext message to an ntfy.sh topic (no account required)."""

    def __init__(self, topic: str, timeout: float = _TIMEOUT_SECONDS) -> None:
        """Store the target topic and per-request timeout."""
        self._topic = topic
        self._timeout = timeout

    def send(self, message: str) -> None:
        """POST *message* to the configured ntfy.sh topic."""
        url = f'https://ntfy.sh/{self._topic}'
        try:
            response = requests.post(
                url, data=message.encode('utf-8'), timeout=self._timeout
            )
        except requests.RequestException:
            logger.exception('ntfy delivery failed: network error')
            return
        if response.status_code >= 400:
            logger.warning('ntfy delivery failed: status %d', response.status_code)


class PushoverProvider:
    """Posts a message via the Pushover API using a user key + API token."""

    def __init__(
        self, user_key: str, api_token: str, timeout: float = _TIMEOUT_SECONDS
    ) -> None:
        """Store Pushover credentials and per-request timeout."""
        self._user_key = user_key
        self._api_token = api_token
        self._timeout = timeout

    def send(self, message: str) -> None:
        """POST *message* to the Pushover messages API."""
        url = 'https://api.pushover.net/1/messages.json'
        payload = {
            'token': self._api_token,
            'user': self._user_key,
            'message': message,
        }
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException:
            logger.exception('Pushover delivery failed: network error')
            return
        if response.status_code >= 400:
            logger.warning('Pushover delivery failed: status %d', response.status_code)


class NotificationHandler:
    """Selects a configured provider and sends a message identifying zones."""

    def __init__(self, config: NotificationConfig) -> None:
        """Build the configured provider, or None if config is incomplete."""
        self._config = config
        self._provider = self._build_provider(config)

    @staticmethod
    def _build_provider(config: NotificationConfig) -> NotificationProvider | None:
        if config.provider == 'ntfy':
            if not config.ntfy_topic:
                logger.warning(
                    'Notification provider ntfy configured without ntfy_topic'
                )
                return None
            return NtfyProvider(topic=config.ntfy_topic)
        if config.provider == 'pushover':
            if not (config.pushover_user_key and config.pushover_api_token):
                logger.warning(
                    'Notification provider pushover configured without credentials'
                )
                return None
            return PushoverProvider(
                user_key=config.pushover_user_key,
                api_token=config.pushover_api_token,
            )
        return None

    def _build_message(self, context: AlertContext) -> str:
        zones = ', '.join(sorted(context.triggered_zones)) or 'unknown zone'
        return f'Dog detected in zone(s): {zones}'

    def trigger(self, context: AlertContext) -> None:
        """Send a notification identifying the triggered zones, if configured."""
        if self._provider is None:
            logger.warning('No provider configured; skipping notification')
            return
        self._provider.send(self._build_message(context))

    def cleanup(self) -> None:
        """No resources to release; HTTP is stateless per-call."""
