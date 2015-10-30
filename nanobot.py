import xml.etree.ElementTree as ET
import urllib
from collections import OrderedDict


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
    _region_string = "{region} has {writers} writers averaging {avg} words each for a total of {count} words!"

    _user_api = 'http://nanowrimo.org/wordcount_api/wc/{user}'
    _user_string = "{user} has written {count} words!"

    @botcmd
    def word_count(self, mess, args):
        """Get word count information

        With no arguments, this command returns word count information for the
        Alaska regions (Anchorage, Fairbanks, and Elsewhere); you can instead
        supply a NaNoWriMo username to get the word count for that user."""

        yield "Please wait while I look that up..."

        if not args:
            data = self._get_region_word_counts()

            for region in data:
                yield self._region_string.format(**data[region])
        else:
            try:
                count = self._get_user_word_count(args)
                yield self._user_string.format(user=args, count=count)
            except NanoApiError as e:
                self.log.info("NanoApiError: {}".format(e))
                yield "Something went wrong, perhaps {} isn't a NaNoWriMo username?".format(args)

    def _get_region_word_counts(self):
        counts = OrderedDict()

        for region in self._regions:
            root = self._get_api_xml(self._region_api, region=region)
            data = dict()

            key = root.find('rname').text.split(None)[-1]
            data['region'] = key
            data['count'] = root.find('region_wordcount').text
            data['avg'] = root.find('average').text
            data['writers'] = root.find('count').text

            counts[key] = data

        return counts

    def _get_user_word_count(self, user):
        root = self._get_api_xml(self._user_api, user=user)

        try:
            return root.find('user_wordcount').text
        except AttributeError as e:
            raise NanoApiError("Could not find user: {}".format(e))

    def _get_api_xml(self, url, **kwargs):
        """Format the API URL, then return the XML fetched from it."""
        url = url.format(**kwargs)
        xml = urllib.request.urlopen(url).read()

        root = ET.fromstring(xml)

        return root

