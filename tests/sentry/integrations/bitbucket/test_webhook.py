from __future__ import absolute_import

from datetime import datetime
from django.utils import timezone
from sentry.models import Commit, CommitAuthor, Repository
from sentry.testutils import APITestCase, TestCase


from sentry.integrations.bitbucket.webhook import parse_raw_user_email, parse_raw_user_name, PROVIDER_NAME
from .testutils import PUSH_EVENT_EXAMPLE

BAD_IP = '109.111.111.10'
BITBUCKET_IP_IN_RANGE = '104.192.143.10'
BITBUCKET_IP = '34.198.178.64'


class UtilityFunctionTest(TestCase):
    def test_parse_raw_user_email(self):
        assert parse_raw_user_email('Max Bittker <max@getsentry.com>') == 'max@getsentry.com'

        assert parse_raw_user_email('Jess MacQueen@JessMacqueen') is None

    def parse_raw_user_name(self):
        assert parse_raw_user_name('Max Bittker <max@getsentry.com>') == 'Max Bittker'


class WebhookTest(APITestCase):

    def setUp(self):
        super(WebhookTest, self).setUp()
        project = self.project  # force creation
        self.url = '/extensions/bitbucket/organizations/%s/webhook/' % project.organization_id

    def test_get_request_fails(self):
        response = self.client.get(self.url)
        assert response.status_code == 405

    def test_unregistered_event(self):
        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE,
            content_type='application/json',
            HTTP_X_EVENT_KEY='UnregisteredEvent',
            REMOTE_ADDR=BITBUCKET_IP,
        )

        assert response.status_code == 204

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE,
            content_type='application/json',
            HTTP_X_EVENT_KEY='UnregisteredEvent',
            REMOTE_ADDR=BITBUCKET_IP_IN_RANGE,
        )

        assert response.status_code == 204

    def test_invalid_signature_ip(self):
        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE,
            content_type='application/json',
            HTTP_X_EVENT_KEY='repo:push',
            REMOTE_ADDR=BAD_IP,
        )

        assert response.status_code == 401


class PushEventWebhookTest(APITestCase):
    def setUp(self):
        super(PushEventWebhookTest, self).setUp()
        project = self.project  # force creation
        self.url = '/extensions/bitbucket/organizations/%s/webhook/' % project.organization.id

    def test_simple(self):
        Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id='{c78dfb25-7882-4550-97b1-4e0d38f32859}',
            provider=PROVIDER_NAME,
            name='maxbittker/newsdiffs',
        )

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE,
            content_type='application/json',
            HTTP_X_EVENT_KEY='repo:push',
            REMOTE_ADDR=BITBUCKET_IP,
        )

        assert response.status_code == 204

        commit_list = list(
            Commit.objects.filter(
                organization_id=self.project.organization_id,
            ).select_related('author').order_by('-date_added')
        )

        assert len(commit_list) == 1

        commit = commit_list[0]

        assert commit.key == 'e0e377d186e4f0e937bdb487a23384fe002df649'
        assert commit.message == u'README.md edited online with Bitbucket'
        assert commit.author.name == u'Max Bittker'
        assert commit.author.email == 'max@getsentry.com'
        assert commit.author.external_id is None
        assert commit.date_added == datetime(2017, 5, 24, 1, 5, 47, tzinfo=timezone.utc)

    def test_anonymous_lookup(self):
        Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id='{c78dfb25-7882-4550-97b1-4e0d38f32859}',
            provider=PROVIDER_NAME,
            name='maxbittker/newsdiffs',
        )

        CommitAuthor.objects.create(
            external_id='bitbucket:baxterthehacker',
            organization_id=self.project.organization_id,
            email='baxterthehacker@example.com',
            name=u'baxterthehacker',
        )

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE,
            content_type='application/json',
            HTTP_X_EVENT_KEY='repo:push',
            REMOTE_ADDR=BITBUCKET_IP,
        )

        assert response.status_code == 204

        commit_list = list(
            Commit.objects.filter(
                organization_id=self.project.organization_id,
            ).select_related('author').order_by('-date_added')
        )

        # should be skipping the #skipsentry commit
        assert len(commit_list) == 1

        commit = commit_list[0]

        assert commit.key == 'e0e377d186e4f0e937bdb487a23384fe002df649'
        assert commit.message == u'README.md edited online with Bitbucket'
        assert commit.author.name == u'Max Bittker'
        assert commit.author.email == 'max@getsentry.com'
        assert commit.author.external_id is None
        assert commit.date_added == datetime(2017, 5, 24, 1, 5, 47, tzinfo=timezone.utc)