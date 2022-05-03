#!/usr/bin/env python3

import click
import datetime
import dateutil.parser
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import os
import pickle
import udi_interface
from udi_interface import LOGGER, Custom
import pytz


class Controller(udi_interface.Node):

    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.calendars = []
        self.calendarList = []
        self.service = None
        self.credentials = None
        self.isStarted = False
        self.config = None

        self.TypedParameters = Custom(polyglot, "customtypedparams")

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.CUSTOMTYPEDDATA, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)

        self.TypedParameters.load( [
            {
                'name': 'calendarName',
                'title': 'Calendar Name',
                'desc': 'Name of the calendar in Google Calendar',
                'isRequired': True,
                'isList': True
            },
            {
                'name': 'token',
                'title': 'Google Authentication Token',
                'desc': 'Obtain token by visiting authentication URL'
            }
        ], True)

        polyglot.ready()
        polyglot.addNode(self, conn_status="ST")

    def discover(self, *args, **kwargs):
        self.refresh()

    def query(self):
        super(Controller, self).query()

    def start(self):
        self.poly.updateProfile()
        self.poly.setCustomParamsDoc()
        self.setDriver('ST', 1)
        LOGGER.info('Started HolidayGoogle Server')

        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                self.credentials = pickle.load(token)

        if not self.credentials or not self.credentials.valid:
            if (self.credentials and self.credentials.expired and
                self.credentials.refresh_token):
                self.credentials.refresh(Request())
            else:
                self.flow = Flow.from_client_secrets_file(
                    'credentials.json', Controller.SCOPES,
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob')

                authURL, _ = self.flow.authorization_url(prompt='consent')

                self.poly.Notices['auth'] = 'Authenticate by visiting <a href="{}">Authentication Link</a>'.format(authURL)
                self.isStarted = True
                return

        self.openService()
        self.isStarted = True

        '''
        FIXME: This forced processing of config (type parameters) data
        after start, do we need to do this?
        if self.config is not None:
            self.process_config(self.config)
            self.config = None
        '''
        self.refresh()

    def openService(self):
        self.service = build('calendar', 'v3', credentials=self.credentials)
        LOGGER.debug('Google API Connection opened')

    def poll(self, pollflag):
        if 'longPoll' in pollflag:
            try:
                self.refresh()
            except Exception as e:
                LOGGER.error('Error refreshing calendars: %s', e)

    def refresh(self):
        if not self.isStarted:
            return

        for entry in self.calendars:
            calendar = entry.calendar
            LOGGER.debug('Checking calendar %s', calendar['summary'])
            todayDate = datetime.datetime.now(pytz.timezone(calendar['timeZone']))
            todayDate = todayDate.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrowDate = todayDate + datetime.timedelta(days=1)
            endDate = todayDate + datetime.timedelta(days=2)
            entry.todayNode.setDate(todayDate)
            entry.tomorrowNode.setDate(tomorrowDate)
            result = self.service.events().list(calendarId=calendar['id'],
                timeMin=todayDate.isoformat(), singleEvents=True,
                timeMax=endDate.isoformat()).execute()
            for event in result.get('items', []):
                if self.is_holiday(event):
                    LOGGER.debug('Event found %s', event['summary'])
                    date = dateutil.parser.parse(event['start']['date']).date()

                    if date == todayDate.date():
                        entry.todayNode.setFutureState()
                    else:
                        entry.tomorrowNode.setFutureState()
            entry.todayNode.refresh()
            entry.tomorrowNode.refresh()

    def is_holiday(self, event):
        return (event.get('transparency') == 'transparent' and
            'date' in event['start'] and
            'date' in event['end'])

    def parameterHandler(self, params):
        '''
        FIXME: We can't really abort here if not started, if we do
        we won't get here again unless the user changes the config
        might need to save the params and move the process of the
        parameters to a separate method.  Or maybe it all works fine
        timing wise.
        if not self.isStarted:
            self.config = config
            return
        '''

        typedConfig = params
        if typedConfig is None:
            LOGGER.info('Config is not set')
            return

        if self.service is None:
            if len(typedConfig.get('token')) == 0:
                LOGGER.warn('Token is not set')
                return

            try:
                self.flow = Flow.from_client_secrets_file(
                    'credentials.json', Controller.SCOPES,
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob')
                self.flow.fetch_token(code=typedConfig.get('token'))
                with open('token.pickle', 'wb') as token:
                    pickle.dump(self.flow.credentials, token)
                self.credentials = self.flow.credentials
                self.openService()
                self.poly.Notices.clear()
            except Exception as e:
                LOGGER.error('Error getting credentials: %s', e)
                return

        LOGGER.debug('Reading calendar configuration')
        self.calendars = []

        calendarList = {}
        pageToken = None
        while True:
            list = self.service.calendarList().list(pageToken=pageToken).execute()
            for listEntry in list['items']:
                # LOGGER.debug('Found calendar %s %s', listEntry['summary'], listEntry)
                calendarList[listEntry['summary']] = listEntry
                pageToken = list.get('nextPageToken')
            if not pageToken:
                break

        list = typedConfig.get('calendarName')
        calendarIndex = 0
        if list is not None:
            for calendarName in list:
                calendar = calendarList.get(calendarName)
                if calendar is None:
                    LOGGER.error('Cannot find configured calendar name %s',
                        calendarName)
                else:
                    entry = CalendarEntry(calendar,
                        DayNode(self.poly, self.address,
                            'today' + str(calendarIndex),
                            calendar['summary'] + ' Today'),
                        DayNode(self.poly, self.address,
                            'tmrow' + str(calendarIndex),
                            calendar['summary'] + ' Tomorrow'))
                    self.calendars.append(entry)
                    self.poly.addNode(entry.todayNode)
                    self.poly.addNode(entry.tomorrowNode)

                    calendarIndex += 1

        if calendarList.keys() != self.calendarList:
            cfgdata = self.poly.getMarkDownData('POLYGLOT_CONFIG.md')
            self.calendarList = calendarList.keys()
            data = '<h3>Configured Calendars</h3><ul>'
            for calendarName in self.calendarList:
                data += '<li>' + calendarName + '</li>'
            data += '</ul>'
            cfgdata += data
            self.poly.setCustomParamsDoc(cfgdata)

        self.refresh()

    id = 'controller'
    commands = { 'DISCOVER': discover, 'QUERY': query }
    drivers = [{ 'driver': 'ST', 'value': 0, 'uom': 25 }]


class CalendarEntry(object):
    def __init__(self, calendar, todayNode, tomorrowNode):
        self.calendar = calendar
        self.todayNode = todayNode
        self.tomorrowNode = tomorrowNode


class DayNode(udi_interface.Node):
    def __init__(self, primary, controllerAddress, address, name):
        super(DayNode, self).__init__(primary, controllerAddress, address, name)
        self.futureState = False
        self.currentDate = None

    def setDate(self, date):
        if self.currentDate != date:
            self.currentDate = date
            self.setDriver('GV0', date.month)
            self.setDriver('GV1', date.day)
            self.setDriver('GV2', date.year)

    def setFutureState(self):
        self.futureState = True

    def refresh(self):
        if self.futureState:
            self.setState(True)
            self.futureState = False
        else:
            self.setState(False)

    def setState(self, state):
        self.setDriver('ST', 1 if state else 0)

    def query(self):
        self.reportDrivers()

    drivers = [
        { 'driver': 'ST', 'value': 0, 'uom': 2 },
        { 'driver': 'GV0', 'value': 0, 'uom': 47 },
        { 'driver': 'GV1', 'value': 0, 'uom': 9 },
        { 'driver': 'GV2', 'value': 0, 'uom': 77 }
    ]

    id = 'daynode'


@click.command()
def holidays_server():
    polyglot = udi_interface.Interface([])
    polyglot.start("1.0.2")
    Controller(polyglot, "controller", "controller", "Holidays Google Controller")
    polyglot.runForever()


if __name__ == '__main__':
    holidays_server()
