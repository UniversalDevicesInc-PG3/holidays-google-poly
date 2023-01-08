#!/usr/bin/env python3

import base64
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

data = 'gASVmAEAAAAAAAB9lIwDd2VilH2UKIwJY2xpZW50X2lklIxIOTk1MjA4MDUyMzQ3LXZhMHJkMjlxMm45MGxqazM0bTJwdXNzM3V1dnRuNW83LmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29tlIwKcHJvamVjdF9pZJSME2FwcGxpZWQtZmxhZy0yMzA5MDCUjAhhdXRoX3VyaZSMKWh0dHBzOi8vYWNjb3VudHMuZ29vZ2xlLmNvbS9vL29hdXRoMi9hdXRolIwJdG9rZW5fdXJplIwjaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW6UjBthdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmyUjCpodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9vYXV0aDIvdjEvY2VydHOUjA1jbGllbnRfc2VjcmV0lIwjR09DU1BYLTZvUkZteWd5R3hzemVRZDU2RmNTZkFnX2NNR0WUjA1yZWRpcmVjdF91cmlzlF2UjBBodHRwOi8vbG9jYWxob3N0lGF1cy4='

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

flow = InstalledAppFlow.from_client_config(
    pickle.loads(base64.b64decode(data)), SCOPES)
creds = flow.run_local_server(prompt='consent')
print(
    f'Save the following into \'token\' parameter of HolidayGoogle node server\n{creds.to_json()}'
)
