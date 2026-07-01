"""Tests for push notification providers and the NotificationHandler."""

from __future__ import annotations

import requests
import requests_mock

from counter_cruiser.client.alerts.context import AlertContext
from counter_cruiser.client.alerts.notifications import (
    NotificationHandler,
    NtfyProvider,
    PushoverProvider,
)
from counter_cruiser.config.models import NotificationConfig


def _context() -> AlertContext:
    return AlertContext(
        frame=None, detections=[], zones=[], triggered_zones={'counter'}, frame_id=1
    )


class TestMessageBuilding:
    def test_message_identifies_triggered_zones(self) -> None:
        handler = NotificationHandler(NotificationConfig(enabled=True))
        message = handler._build_message(_context())
        assert 'counter' in message


class TestNtfyProvider:
    def test_posts_message_to_configured_topic(self) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/my-topic', status_code=200)
            NtfyProvider(topic='my-topic').send('Dog on counter!')
        assert m.last_request.text == 'Dog on counter!'


class TestPushoverProvider:
    def test_posts_message_with_user_key_and_token(self) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://api.pushover.net/1/messages.json', status_code=200)
            PushoverProvider(user_key='u1', api_token='t1').send('Dog on counter!')
        sent = m.last_request.json() if False else m.last_request.text
        assert 'u1' in sent
        assert 't1' in sent
        assert 'Dog on counter!' in sent


class TestFailureTolerance:
    def test_network_error_is_logged_and_does_not_raise(self, caplog) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/topic', exc=requests.ConnectionError)
            with caplog.at_level('ERROR'):
                NtfyProvider(topic='topic').send('hi')  # must not raise
        assert 'network error' in caplog.text

    def test_non_success_status_is_logged_and_does_not_raise(self, caplog) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/topic', status_code=500)
            with caplog.at_level('WARNING'):
                NtfyProvider(topic='topic').send('hi')  # must not raise
        assert 'status 500' in caplog.text

    def test_pushover_network_error_is_logged_and_does_not_raise(self, caplog) -> None:
        with requests_mock.Mocker() as m:
            m.post(
                'https://api.pushover.net/1/messages.json', exc=requests.ConnectionError
            )
            with caplog.at_level('ERROR'):
                PushoverProvider(user_key='u', api_token='t').send(
                    'hi'
                )  # must not raise
        assert 'network error' in caplog.text

    def test_pushover_non_success_status_is_logged_and_does_not_raise(
        self, caplog
    ) -> None:
        with requests_mock.Mocker() as m:
            m.post('https://api.pushover.net/1/messages.json', status_code=500)
            with caplog.at_level('WARNING'):
                PushoverProvider(user_key='u', api_token='t').send(
                    'hi'
                )  # must not raise
        assert 'status 500' in caplog.text

    def test_missing_topic_logs_and_skips_delivery(self, caplog) -> None:
        config = NotificationConfig(enabled=True, provider='ntfy', ntfy_topic=None)
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'ntfy_topic' in caplog.text

    def test_missing_pushover_credentials_logs_and_skips_delivery(self, caplog) -> None:
        config = NotificationConfig(enabled=True, provider='pushover')
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'pushover' in caplog.text.lower()

    def test_no_provider_configured_logs_and_skips_delivery(self, caplog) -> None:
        config = NotificationConfig(enabled=True, provider=None)
        with caplog.at_level('WARNING'):
            handler = NotificationHandler(config)
            handler.trigger(_context())  # must not raise
        assert 'no provider' in caplog.text.lower()


class TestNotificationHandlerDelegation:
    def test_ntfy_provider_selected_and_invoked(self) -> None:
        config = NotificationConfig(
            enabled=True, provider='ntfy', ntfy_topic='my-topic'
        )
        with requests_mock.Mocker() as m:
            m.post('https://ntfy.sh/my-topic', status_code=200)
            handler = NotificationHandler(config)
            handler.trigger(_context())
        assert m.called

    def test_pushover_provider_selected_and_invoked(self) -> None:
        config = NotificationConfig(
            enabled=True,
            provider='pushover',
            pushover_user_key='u1',
            pushover_api_token='t1',
        )
        with requests_mock.Mocker() as m:
            m.post('https://api.pushover.net/1/messages.json', status_code=200)
            handler = NotificationHandler(config)
            handler.trigger(_context())
        assert m.called

    def test_cleanup_is_a_noop(self) -> None:
        handler = NotificationHandler(NotificationConfig())
        handler.cleanup()  # must not raise
