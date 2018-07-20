from __future__ import absolute_import

import mock
import pytest
import pytz
from datetime import datetime

from sentry.eventstream.kafka.relay import (
    InvalidPayload,
    InvalidVersion,
    join,
    parse_event_message,
)
from sentry.utils import json


def test_join():
    consumer = mock.MagicMock()

    message = mock.Mock()
    message.error.return_value = None

    consumer.poll.side_effect = [None, None, message]

    joined_consumer = join([consumer])
    assert next(joined_consumer) == (consumer, message)

    assert consumer.poll.mock_calls == [
        mock.call(0.0),  # not throttled
        mock.call(0.1),  # throttled, no return value
        mock.call(0.1),  # throttled, returned message
    ]


def test_parse_event_message_invalid_payload():
    with pytest.raises(InvalidPayload):
        parse_event_message('{"format": "invalid"}')


def test_parse_event_message_invalid_version():
    with pytest.raises(InvalidVersion):
        parse_event_message(json.dumps([0, 'insert', {}]))


def test_parse_event_message_version_1():
    event_data = {
        'project_id': 1,
        'group_id': 2,
        'event_id': '00000000000010008080808080808080',
        'message': 'message',
        'platform': 'python',
        'datetime': '2018-07-20T21:04:27.600640Z',
        'data': {},
        'extra': {},
        'primary_hash': '49f68a5c8493ec2c0bf489821c21fc3b',
    }

    task_state = {
        'is_new': True,
        'is_sample': False,
        'is_regression': False,
        'is_new_group_environment': True,
    }

    kwargs = parse_event_message(json.dumps([1, 'insert', event_data, task_state]))
    event = kwargs.pop('event')
    assert event.project_id == 1
    assert event.group_id == 2
    assert event.event_id == '00000000000010008080808080808080'
    assert event.message == 'message'
    assert event.platform == 'python'
    assert event.datetime == datetime(2018, 7, 20, 21, 4, 27, 600640, tzinfo=pytz.utc)
    assert dict(event.data) == {}

    assert kwargs.pop('primary_hash') == '49f68a5c8493ec2c0bf489821c21fc3b'

    assert kwargs.pop('is_new') is True
    assert kwargs.pop('is_sample') is False
    assert kwargs.pop('is_regression') is False
    assert kwargs.pop('is_new_group_environment') is True

    assert not kwargs, 'unexpected values remaining: {!r}'.format(kwargs)


def test_parse_event_message_version_1_unsupported_operation():
    assert parse_event_message(json.dumps([1, 'delete', {}, {}])) is None
