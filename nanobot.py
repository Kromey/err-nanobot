from socket import timeout
import datetime
import calendar


from errbot import BotPlugin, botcmd
from pynano import User, Region


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
    _region_donations_string = "{region} has donated ${donations:,.2f}!"

    _user_api = 'http://nanowrimo.org/wordcount_api/wc/{user}'
    _user_string = "{user} has written {count:,} words!"
    _user_string_today = "{user} has written {today:,} words today for a total of {count:,} words!"

    _real_jid = {}

    def activate(self):
        if self._bot.mode == 'xmpp':
            #XMPP: Listen for MUC Presence stanzas so we can get real JIDs of occupants
            self._bot.conn.add_event_handler('groupchat_presence', self.update_jid_index)
            self.log.info('Attached groupchat_presence listener')
        super().activate()

    def deactivate(self):
        if self._bot.mode == 'xmpp':
            #XMPP: Deactivating the plugin, remove our listener
            self._bot.conn.del_event_handler('groupchat_presence', self.update_jid_index)
            self.log.info('Removed groupchat_presence listener')
        super().deactivate()

    def update_jid_index(self, event):
        """Update the index of real JIDs

        Each time we get a Presence stanza from a MUC, we want to extract the
        real JID from it and store it in our index. We can then later look up an
        occupant JID in our index to find their real JID.
        """
        try:
            occupant = event['from'].full #Full JID identifies the user; bare is just the room
            real_jid = event['muc']['jid'].bare #Bare JID here in case of multiple connections
            evt_type = event['type']

            if not real_jid:
                #We couldn't get the real JID from this stanza, probably because
                #room is anonymous and we don't have the necessary privileges
                self.log.warning('Unable to get real JID from {}'.format(event))
                return

            if evt_type == 'unavailable':
                #User is no longer available (e.g. left room, changing nick)
                #Remove from our index
                try:
                    del(self._real_jid[occupant])
                except KeyError:
                    pass
            else:
                #Add the user to our index
                self._real_jid[occupant] = real_jid

            self.log.debug('Updated real JID index from {}'.format(event))
        except:
            self.log.exception('Failed to process event {}'.format(event))

    @botcmd
    def real_jid(self, mess, args):
        try:
            return self._real_jid[mess.frm.person]
        except KeyError:
            return "I'm sorry, I don't know who you really are"

    @botcmd(admin_only=True)
    def jid_index(self, mess, args):
        return str(self._real_jid)

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
                    response.append(self._region_string.format(**region))

                yield "\n".join(response)
            else:
                try:
                    user, count, today = self._get_user_word_count(args)
                    if today:
                        yield self._user_string_today.format(user=user, count=count, today=today)
                    else:
                        yield self._user_string.format(user=user, count=count)
                except NanoApiError as e:
                    self.log.info("NanoApiError: {}".format(e))
                    yield "Something went wrong, perhaps {} isn't a NaNoWriMo username?".format(args)

        except timeout as e:
            self.log.info("Failed to get word count (args: '{}'): {}".format(args, e))
            yield "I'm sorry, the NaNoWriMo website isn't talking to me right now. Maybe try again later."

    @botcmd
    def donations(self, mess, args):
        yield "Please wait while I look that up..."

        donations = []
        for region in self._regions:
            r = Region(region)
            donations.append({
                'region': r.name.split(' :: ')[-1],
                'donations': r.donations,
                })

        donations.sort(key=lambda region: region['donations'], reverse=True)

        response = []
        total = 0
        for donation in donations:
            total += float(donation['donations'])
            response.append(self._region_donations_string.format(**donation))

        yield "\n".join(response)

        if total:
            yield "That's ${total:,.2f} donated. Commendable!".format(total=total)

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
        counts = []

        for region in self._regions:
            r = Region(region)
            data = {}

            data['region'] = r.name.split(' :: ')[-1]
            data['count'] = r.wordcount
            data['avg'] = r.average
            data['writers'] = r.writers

            counts.append(data)

        counts.sort(key=lambda region: region['avg'], reverse=True)
        return counts

    def _get_user_word_count(self, user):
        user = User(user)

        try:
            try:
                today = user.history[datetime.date.today().day-1].wordcount
            except:
                today = None
            uname = user.name
            wcount = user.wordcount

            return (uname, wcount, today)
        except KeyError as e:
            raise NanoApiError("Could not find user: {}".format(e))

