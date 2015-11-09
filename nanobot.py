import xml.etree.ElementTree as ET
import urllib
from socket import timeout
from collections import OrderedDict
import datetime
import calendar


from errbot import BotPlugin, botcmd


class NanoApiError(Exception):
    pass


class NanoBot(BotPlugin):
    """Integrate Err with NaNoWriMo's word count API"""
    min_err_version = '3.0.5' # Optional, but recommended

    _region_api = 'http://nanowrimo.org/wordcount_api/wcregion/{region}'
    _regions = (
            'usa-alaska-anchorage',
            'usa-alaska-fairbanks',
            'usa-alaska-elsewhere',
            )
    _region_string = "{region} has {writers:,} writers averaging {avg:,.2f} words for a total of {count:,} words!"

    _user_api = 'http://nanowrimo.org/wordcount_api/wc/{user}'
    _user_string = "{user} has written {count:,} words!"

    @botcmd
    def word_count(self, mess, args):
        """Get word count information

        With no arguments, this command returns word count information for the
        Alaska regions (Anchorage, Fairbanks, and Elsewhere); you can instead
        supply a NaNoWriMo username to get the word count for that user."""

        yield "Please wait while I look that up..."

        try:
            if not args:
                data = self._get_region_word_counts()

                response = []

                for region in data:
                    response.append(self._region_string.format(**data[region]))

                yield "\n".join(response)
            else:
                try:
                    user, count = self._get_user_word_count(args)
                    yield self._user_string.format(user=user, count=count)
                except NanoApiError as e:
                    self.log.info("NanoApiError: {}".format(e))
                    yield "Something went wrong, perhaps {} isn't a NaNoWriMo username?".format(args)

        except (timeout, urllib.error.URLError) as e:
            self.log.info("Failed to get word count (args: '{}'): {}".format(args, e))
            yield "I'm sorry, the NaNoWriMo website isn't talking to me right now. Maybe try again later."

    @botcmd
    def word_goal(self, mess, args):
        """Find out where you *should* be with your word count

        With no additional argument, this command assumes the NaNoWriMo default
        goal of 50,000 words. For over-achievers, or for Young Writers with
        their own goals, simply supply your goal after the command, e.g.
        "word goal 75000", to have the bot use that goal in calculations.

        The bot makes no assumptions that you constrain yourself only to the
        month of November, so this command can be used for NaNoWriMo, Camp
        NaNoWriMo, or your own personal adventures in writing. The calculations
        always take into account the actual number of days in the current month.
        """

        if args:
            # People like to use commas; remove them
            goal = args.replace(',', '')
            # Support shorthand like "10k" or "10K"
            goal = goal.lower().replace('k', '000')
            # Convert it to an actual number, truncating if necessary
            goal = int(float(goal))
        else:
            goal = 50000

        date = datetime.date.today()

        # Returns (weekday of the 1st, last day) for the given month
        # We only want the last day, aka the number of days
        days = calendar.monthrange(date.year, date.month)[1]

        # Calculate how much progress per day, times how many days elapsed
        par = round(goal / days * date.day)

        # TODO: (Configurable?) locale, and use the 'n' option instead of ','
        return "To reach {goal:,} words, you should be at {par:,} words today".format(goal=goal, par=par)

    def _get_region_word_counts(self):
        counts = OrderedDict()

        for region in self._regions:
            root = self._get_api_xml(self._region_api, region=region)
            data = dict()

            key = root.find('rname').text.split(None)[-1]
            data['region'] = key
            data['count'] = int(root.find('region_wordcount').text)
            data['avg'] = float(root.find('average').text)
            data['writers'] = int(root.find('count').text)

            counts[key] = data

        return counts

    def _get_user_word_count(self, user):
        user = user.replace(' ', '-')
        root = self._get_api_xml(self._user_api, user=user)

        uname = root.find('uname').text
        wcount = int(root.find('user_wordcount').text)

        try:
            return (uname, wcount)
        except AttributeError as e:
            raise NanoApiError("Could not find user: {}".format(e))

    def _get_api_xml(self, url, **kwargs):
        """Format the API URL, then return the XML fetched from it."""
        url = url.format(**kwargs)
        xml = urllib.request.urlopen(url, timeout=5).read()

        root = ET.fromstring(xml)

        return root

