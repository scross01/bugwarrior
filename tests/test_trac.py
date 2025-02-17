from bugwarrior.collect import TaskConstructor
from bugwarrior.services.trac import TracService

from .base import ServiceTest, AbstractServiceTest


class FakeTracTicket:
    @staticmethod
    def changeLog(issuenumber):
        return []


class FakeTracServer:
    ticket = FakeTracTicket()


class FakeTracLib:
    server = FakeTracServer()

    def __init__(self, record):
        self.record = record

    @staticmethod
    def query_tickets(query):
        return ['something']

    def get_ticket(self, ticket):
        return (1, None, None, self.record)


class TestTracIssue(AbstractServiceTest, ServiceTest):
    SERVICE_CONFIG = {
        'service': 'trac',
        'base_uri': 'ljlkajsdfl.com',
        'username': 'something',
        'password': 'somepwd',
    }
    arbitrary_issue = {
        'url': 'http://some/url.com/',
        'summary': 'Some Summary',
        'number': 204,
        'priority': 'critical',
        'component': 'testcomponent',
    }

    def setUp(self):
        super().setUp()
        self.service = self.get_mock_service(TracService)

    def get_mock_service(self, *args, **kwargs):
        service = super().get_mock_service(*args, **kwargs)
        service.trac = FakeTracLib(self.arbitrary_issue)
        return service

    def test_to_taskwarrior(self):
        arbitrary_extra = {
            'annotations': [
                'alpha',
                'beta',
            ],
            'project': 'some project',
        }

        issue = self.service.get_issue_for_record(
            self.arbitrary_issue,
            arbitrary_extra,
        )

        expected_output = {
            'project': arbitrary_extra['project'],
            'priority': issue.PRIORITY_MAP[self.arbitrary_issue['priority']],
            'annotations': arbitrary_extra['annotations'],
            issue.URL: self.arbitrary_issue['url'],
            issue.SUMMARY: self.arbitrary_issue['summary'],
            issue.NUMBER: self.arbitrary_issue['number'],
            issue.COMPONENT: self.arbitrary_issue['component'],
        }
        actual_output = issue.to_taskwarrior()

        self.assertEqual(actual_output, expected_output)

    def test_issues(self):
        issue = next(self.service.issues())

        expected = {
            'annotations': [],
            'description':
                '(bw)Is#1 - Some Summary .. https://ljlkajsdfl.com/ticket/1',
            'priority': 'H',
            'project': 'unspecified',
            'tags': [],
            'tracnumber': 1,
            'tracsummary': 'Some Summary',
            'tracurl': 'https://ljlkajsdfl.com/ticket/1',
            'traccomponent': 'testcomponent'}

        self.assertEqual(TaskConstructor(issue).get_taskwarrior_record(), expected)
