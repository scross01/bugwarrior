import re
import datetime

import pytz
import responses

from bugwarrior.collect import TaskConstructor
from bugwarrior.services.activecollab2 import ActiveCollab2Service

from .base import ServiceTest, AbstractServiceTest


class TestActiveCollab2Issue(AbstractServiceTest, ServiceTest):
    SERVICE_CONFIG = {
        'service': 'activecollab2',
        'url': 'http://hello',
        'key': 'howdy',
        'user_id': 0,
        'projects': {1: 'one', 2: 'two'},
    }

    arbitrary_due_on = (
        datetime.datetime.now() - datetime.timedelta(hours=1)
    ).replace(tzinfo=pytz.UTC)
    arbitrary_created_on = (
        datetime.datetime.now() - datetime.timedelta(hours=2)
    ).replace(tzinfo=pytz.UTC)
    arbitrary_issue = {
        'project': 'something',
        'priority': 2,
        'due_on': arbitrary_due_on.isoformat(),
        'permalink': 'http://wherever/',
        'ticket_id': 10,
        'project_id': 20,
        'type': 'Ticket',
        'created_on': arbitrary_created_on.isoformat(),
        'created_by_id': '10',
        'body': 'Ticket Body',
        'name': 'Anonymous',
        'assignees': [
            {'user_id': SERVICE_CONFIG['user_id'],
             'is_owner': True}
        ],
        'description': 'Further detail.',
    }

    def setUp(self):
        super().setUp()
        self.service = self.get_mock_service(ActiveCollab2Service)

    def test_to_taskwarrior(self):

        issue = self.service.get_issue_for_record(self.arbitrary_issue)

        expected_output = {
            'project': self.arbitrary_issue['project'],
            'priority': issue.PRIORITY_MAP[self.arbitrary_issue['priority']],
            'due': self.arbitrary_due_on,

            issue.PERMALINK: self.arbitrary_issue['permalink'],
            issue.TICKET_ID: self.arbitrary_issue['ticket_id'],
            issue.PROJECT_ID: self.arbitrary_issue['project_id'],
            issue.TYPE: self.arbitrary_issue['type'],
            issue.CREATED_ON: self.arbitrary_created_on,
            issue.CREATED_BY_ID: self.arbitrary_issue['created_by_id'],
            issue.BODY: self.arbitrary_issue['body'],
            issue.NAME: self.arbitrary_issue['name'],
        }
        actual_output = issue.to_taskwarrior()

        self.assertEqual(actual_output, expected_output)

    @responses.activate
    def test_issues(self):
        self.add_response(
            re.compile(
                r'http://hello/\?(?=.*token=howdy)(?=.*path_info=\%2Fprojects\%2F[1-2]\%2Fuser-tasks)(?=.*format=json)'),  # noqa: E501
            json=[self.arbitrary_issue])
        self.add_response(
            re.compile(
                r'http://hello/\?(?=.*token=howdy)(?=.*path_info=\%2Fprojects\%2F20\%2Ftickets\%2F10)(?=.*format=json)'),  # noqa: E501
            json=self.arbitrary_issue)

        issue = next(self.service.issues())

        expected = {
            'ac2body': 'Ticket Body',
            'ac2createdbyid': '10',
            'ac2createdon': self.arbitrary_created_on,
            'ac2name': 'Anonymous',
            'ac2permalink': 'http://wherever/',
            'ac2projectid': 20,
            'ac2ticketid': 10,
            'ac2type': 'Ticket',
            'description': '(bw)Is#10 - Anonymous .. http://wherever/',
            'due': self.arbitrary_due_on,
            'priority': 'H',
            'project': 'something',
            'tags': []}

        self.assertEqual(TaskConstructor(issue).get_taskwarrior_record(), expected)
