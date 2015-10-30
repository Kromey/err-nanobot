import xml.etree.ElementTree as ET
import urllib


from errbot import BotPlugin, botcmd


class NanoBot(BotPlugin):
    """Integrate Err with NaNoWriMo's word count API"""
    min_err_version = '3.0.5' # Optional, but recommended

    _region_api = 'http://nanowrimo.org/wordcount_api/wcregion/{}'
    _regions = (
            'usa-alaska-anchorage',
            'usa-alaska-fairbanks',
            'usa-alaska-elsewhere',
            )
    _region_string = "{region} has {writers} writers averaging {avg} words each for a total of {count} words!"

    @botcmd
    def word_count(self, mess, args):
        """Get word count information

        With no arguments, this command returns word count information for the
        Alaska regions (Anchorage, Fairbanks, and Elsewhere); you can instead
        supply a NaNoWriMo username to get the word count for that user."""

        if not args:
            yield "Please wait while I look that up..."

            data = self._get_region_word_counts()

            for region in data:
                yield self._region_string.format(**data[region])
        else:
            yield "I'm sorry, I've not yet been implemented with per-user lookups"

    def _get_region_word_counts(self):
        counts = dict()

        for region in self._regions:
            url = self._region_api.format(region)
            xml = urllib.request.urlopen(url).read()

            root = ET.fromstring(xml)
            data = dict()

            key = root.find('rname').text.split(None)[-1]
            data['region'] = key
            data['count'] = root.find('region_wordcount').text
            data['avg'] = root.find('average').text
            data['writers'] = root.find('count').text

            counts[key] = data

        return counts

