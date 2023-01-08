## Configuration

When you start Holidays Google node server for the first time, it will require to authenticate your Google account. 

Google authenitcation is not working right now so as a temporary workaround, token needs to be generated using a desktop.

* Save file https://raw.githubusercontent.com/UniversalDevicesInc-PG3/holidays-google-poly/master/holidays-auth.py to your desktop computer with browser.
* Install python3 and pip3
* Run *pip3 install google_auth_oauthlib* or *pip3 install --user google_auth_oauthlib* if having issues with permissions. Either will work.
* Run *python3 holidays-auth.py*
* Copy and paste token into *token* parameter into HolidaysGoogle config in PG3.

Holidays Google node server accepts a list of calendars in your account to check for holidays. It will poll holidays changes every long poll (default is 60 seconds). In order for event to be considered as a holiday, it needs to be *full day event* AND it needs to *show time as free*.

Two nodes will be created for each configured calendar - today and tomorrow.

**DO NOT CHANGE RELATIVE ORDER OF CONFIGURED CALENDAR NAMES.** Doing this will change underlying ISY nodes to the new configuration, potentially requiring you to change ISY programs.
