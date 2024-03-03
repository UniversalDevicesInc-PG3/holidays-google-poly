#!/usr/bin/env python3

import datetime
import dateutil.parser
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
import pytz
import udi_interface
from udi_interface import LOGGER


class CalendarService(udi_interface.OAuth):

    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

    #pylint: disable=unused-argument, too-many-branches
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.poly = polyglot
        self.config_calendar_list = []
        self.service = None
        self.credentials = None
        self.calendars = None
        self.controller = None
        self.client_id = None
        self.client_secret = None
        self.refresh_token = None

        polyglot.subscribe(polyglot.CUSTOMNS, self.custom_ns_handler)
        polyglot.subscribe(polyglot.OAUTH, self.oauth_handler)
        polyglot.subscribe(polyglot.CUSTOMTYPEDDATA, self.parameter_handler)
        polyglot.subscribe(polyglot.CONFIGDONE, self.config_done_handler)

        udi_interface.Custom(polyglot, "customtypedparams").load([
            {
                'name': 'calendarName',
                'title': 'Calendar Name',
                'desc': 'Name of the calendar in Google Calendar',
                'isRequired': True,
                'isList': True
            },
            {
                'name': 'clientID',
                'title': 'Client ID',
                'desc': 'Optional client ID when using your own authentications',
            },
            {
                'name': 'clientSecret',
                'title': 'Client Secret',
                'desc': 'Optional client secret when using your own authentications',
            },
        ], True)

    def open_service(self):
        self.service = build('calendar', 'v3', credentials=self.credentials)
        LOGGER.debug('Google API Connection opened')

    def oauth_handler(self, token):
        super().oauthHandler(token)
        self.refresh_token = token['refresh_token']
        self.config_done_handler()

    def custom_ns_handler(self, key, data):
        super().customNsHandler(key, data)
        if key == 'oauth':
            self.client_id = data['client_id']
            self.client_secret = data['client_secret']
        elif key == 'oauthTokens':
            self.refresh_token = data['refresh_token']

    def parameter_handler(self, params):
        if params is not None:
            self.config_calendar_list = params.get('calendarName')

            client_id = params.get('clientID')
            client_secret = params.get('clientSecret')
            if client_id and client_secret:
                LOGGER.debug('Overwriting oauth information')
                self.updateOauthSettings({'client_id': client_id, 'client_secret': client_secret})

    def ask_auth(self):
        self.poly.Notices['auth'] = 'Not authenticated or invalid authentication'

    def config_done_handler(self):
        self.poly.Notices.clear()

        if len(self.config_calendar_list) == 0:
            LOGGER.debug('No calendars are defined in the configuration.')

        try:
            token = self.getAccessToken()
        except ValueError:
            LOGGER.error('Token is not set')
            self.ask_auth()
            return

        auth = {
            'token': token,
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        try:
            self.credentials = Credentials.from_authorized_user_info(auth, scopes=Controller.SCOPES)
            if not self.credentials or not self.credentials.valid:
                if (self.credentials and self.credentials.expired and self.credentials.refresh_token):
                    LOGGER.debug('Refreshing credentials')
                    self.credentials.refresh(Request())
                else:
                    LOGGER.warning('Credentials invalid')
                    self.ask_auth()
                    return
        except RefreshError:
            LOGGER.error('Error refreshing token')
            self.ask_auth()
            return

        self.open_service()

        LOGGER.debug('Reading calendar configuration')
        self.calendars = []

        calendars = {}
        page_token = None
        while True:
            calendar_list = self.service.calendarList().list(pageToken=page_token).execute()
            for list_entry in calendar_list['items']:
                LOGGER.debug('Found calendar %s %s', list_entry["summary"], list_entry)
                calendars[list_entry['summary']] = list_entry
                page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break

        for calendar_name in self.config_calendar_list:
            calendar = calendars.get(calendar_name)
            if calendar is None:
                LOGGER.error('Cannot find configured calendar name %s', calendar_name)
            else:
                self.calendars.append(calendar)

        config_data = self.poly.getMarkDownData('POLYGLOT_CONFIG.md')
        data = '<h3>Configured Calendars</h3><ul>'
        for calendar_name in calendars:
            data += '<li>' + calendar_name + '</li>'
        data += '</ul>'
        config_data += data
        self.poly.setCustomParamsDoc(config_data)

        self.controller.config_done()


class Controller(udi_interface.Node):

    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

    #pylint: disable=unused-argument, too-many-branches, too-many-arguments
    def __init__(self, polyglot, primary, address, name, service):
        super().__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.service = service
        self.is_started = False
        self.calendars = None
        self.service.controller = self

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.POLL, self.poll)

        polyglot.ready()
        polyglot.addNode(self, conn_status="ST")

    def discover(self, *args, **kwargs):
        self.refresh()

    def start(self):
        self.poly.updateProfile()
        self.poly.setCustomParamsDoc()
        self.setDriver('ST', 1)
        LOGGER.info('Started HolidayGoogle Server')

    def poll(self, pollflag):
        if 'longPoll' in pollflag:
            try:
                self.refresh()
            except Exception as e:
                LOGGER.error('Error refreshing calendars: %s', e)

    def refresh(self):
        if not self.is_started:
            return

        for entry in self.calendars:
            calendar = entry.calendar
            LOGGER.debug(f'Checking calendar {calendar["summary"]}')
            today_date = datetime.datetime.now(pytz.timezone(calendar['timeZone']))
            today_date = today_date.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_date = today_date + datetime.timedelta(days=1)
            end_date = today_date + datetime.timedelta(days=2)
            entry.today_node.set_date(today_date)
            entry.tomorrow_node.set_date(tomorrow_date)
            result = self.service.service.events().list(calendarId=calendar['id'],
                                                        timeMin=today_date.isoformat(),
                                                        singleEvents=True,
                                                        timeMax=end_date.isoformat()).execute()
            for event in result.get('items', []):
                if self.is_holiday(event):
                    LOGGER.debug(f'Event found {event["summary"]}')
                    date = dateutil.parser.parse(event['start']['date']).date()

                    if date == today_date.date():
                        entry.today_node.set_future_state()
                    else:
                        entry.tomorrow_node.set_future_state()
            entry.today_node.refresh()
            entry.tomorrow_node.refresh()

    def is_holiday(self, event):
        return (event.get('transparency') == 'transparent' and 'date' in event['start'] and 'date' in event['end'])

    def config_done(self):
        calendar_index = 0
        self.calendars = []
        for calendar in self.service.calendars:
            entry = CalendarEntry(
                calendar, DayNode(self.poly, self.address, 'today' + str(calendar_index),
                                  calendar['summary'] + ' Today'),
                DayNode(self.poly, self.address, 'tmrow' + str(calendar_index), calendar['summary'] + ' Tomorrow'))
            self.calendars.append(entry)
            self.poly.addNode(entry.today_node)
            self.poly.addNode(entry.tomorrow_node)

            calendar_index += 1

        self.is_started = True
        self.refresh()

    id = 'controller'
    commands = {'DISCOVER': discover, 'QUERY': udi_interface.Node.query}
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 25}]


class CalendarEntry:

    def __init__(self, calendar, today_node, tomorrow_node):
        self.calendar = calendar
        self.today_node = today_node
        self.tomorrow_node = tomorrow_node


class DayNode(udi_interface.Node):

    def __init__(self, primary, controller_address, address, name):
        super().__init__(primary, controller_address, address, name)
        self.future_state = False
        self.current_date = None

    def set_date(self, date):
        if self.current_date != date:
            self.current_date = date
            self.setDriver('GV0', date.month)
            self.setDriver('GV1', date.day)
            self.setDriver('GV2', date.year)

    def set_future_state(self):
        self.future_state = True

    def refresh(self):
        if self.future_state:
            self.set_state(True)
            self.future_state = False
        else:
            self.set_state(False)

    def set_state(self, state):
        self.setDriver('ST', 1 if state else 0)

    def query(self):
        self.reportDrivers()

    drivers = [{
        'driver': 'ST',
        'value': 0,
        'uom': 2
    }, {
        'driver': 'GV0',
        'value': 0,
        'uom': 47
    }, {
        'driver': 'GV1',
        'value': 0,
        'uom': 9
    }, {
        'driver': 'GV2',
        'value': 0,
        'uom': 77
    }]

    id = 'daynode'


def holidays_server():
    polyglot = udi_interface.Interface([])
    polyglot.start("3.0.1")
    service = CalendarService(polyglot)
    Controller(polyglot, "controller", "controller", "Holidays Google Controller", service)
    polyglot.runForever()


if __name__ == '__main__':
    holidays_server()
