# Copyright 2007-9 Benjamin M. Schwartz
# Copyright 2007 Collabora Ltd.
# Copyright 2011 Walter Bender
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging
import telepathy
import telepathy.client
import locale

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Pango
from gi.repository import GdkPixbuf

# directory exists if powerd is running.  create a file here,
# named after our pid, to inhibit suspend.
POWERD_INHIBIT_DIR = '/var/run/powerd-inhibit-suspend'

import sugar3
from sugar3.activity import activity
from sugar3.presence import presenceservice

from gettext import gettext as _

#For socket code
import threading
import thread
import socket
import os
import os.path
import dbus

#import socket_test as arange
import arange
import atm_toolbars
import smoot_toolbar

SERVICE = "org.laptop.AcousticMeasure"
IFACE = SERVICE
PATH = "/org/laptop/AcousticMeasure"


def gobject_idle_do(func, *args):
    ev = threading.Event()
    retval = []

    def helper(r, f, a, e):
        r.append(f(*a))
        e.set()
        return False

    GObject.idle_add(helper, retval, func, args, ev)
    ev.wait()
    return retval[0]


class AcousticMeasureActivity(activity.Activity):
    '''AcousticMeasure Activity: Uses sound propagation delay to
    measure distance'''

    _message_dict = {}
    _button_dict = {}

    def __init__(self, handle):
        '''Set up the Acoustic Tape Measure activity.'''
        super(AcousticMeasureActivity, self).__init__(handle)

        #self.set_title(_('Acoustic Tape Measure Activity'))
        self._logger = logging.getLogger('acousticmeasure-activity')

        GObject.threads_init()
        
        try:
            self._logger.debug("locale: " + locale.setlocale(locale.LC_ALL,
                                                             ''))
        except locale.Error:
            self._logger.error("setlocale failed")

        # top toolbar with share and close buttons:

        from sugar3.graphics.toolbarbox import ToolbarBox
        from sugar3.graphics.toolbarbox import ToolbarButton
        from sugar3.activity.widgets import ShareButton
        from sugar3.activity.widgets import StopButton
        from sugar3.activity.widgets import ActivityButton
        from sugar3.activity.widgets import TitleEntry

        toolbar_box = ToolbarBox()
        activity_button = ActivityButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()

        title_entry = TitleEntry(self)
        toolbar_box.toolbar.insert(title_entry, -1)
        title_entry.show()

        try:
                from sugar3.activity.widgets import DescriptionItem
                description_item = DescriptionItem(self)
                toolbar_box.toolbar.insert(description_item, -1)
                description_item.show()
        except:
                pass

        share_button = ShareButton(self)
        toolbar_box.toolbar.insert(share_button, -1)
        share_button.show()

        separator = Gtk.SeparatorToolItem()
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        self._t_h_bar = atm_toolbars.TempToolbar()
        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._t_h_bar.show_all()
        adj_button = ToolbarButton(page=self._t_h_bar,
                                       icon_name='preferences-system')
        toolbar_box.toolbar.insert(adj_button, -1)
        adj_button.show()

        self._smoot_bar = smoot_toolbar.SmootToolbar(self)
        self._smoot_bar.show_all()
        custom_button = ToolbarButton(page=self._smoot_bar,
                                          icon_name='view-source')
        toolbar_box.toolbar.insert(custom_button, -1)
        custom_button.show()

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()
        toolbar = toolbar_box.toolbar

        if not self.powerd_running():
            try:
                bus = dbus.SystemBus()
                proxy = bus.get_object('org.freedesktop.ohm',
                                       '/org/freedesktop/ohm/Keystore')
                self.ohm_keystore = dbus.Interface(
                    proxy, 'org.freedesktop.ohm.Keystore')
            except dbus.DBusException, e:
                self._logger.warning("Error setting OHM inhibit: %s" % e)
                self.ohm_keystore = None

        #distance in meters
        self.current_distance = 0.0

        #worker thread
        self._button_event = threading.Event()
        thread.start_new_thread(self._helper_thread, ())

        # Main Panel GUI
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_panel = vbox
        self._message_dict['unshared'] = _("To measure the distance between \
two laptops, you must first share this Activity.")
        self._message_dict['ready'] = _("Press the button to measure the \
distance to another laptop")
        self._message_dict['preparing'] = _("Preparing to measure distance")
        self._message_dict['waiting'] = _("Ready to make a measurement.  \
Waiting for partner to be ready.")
        self._message_dict['playing'] = _("Recording sound from each laptop.")
        self._message_dict['processing'] = _("Processing recorded audio.")
        self._message_dict['done'] = self._message_dict['ready']
        self._message_dict['full'] = _("This activity already has two \
participants, so you cannot join.")

        self._button_dict['waiting'] = _("Begin Measuring Distance")
        self._button_dict['going'] = _("Stop Measuring Distance")

        self.button = Gtk.ToggleButton(label=self._button_dict['waiting'])
        self.button.connect('clicked', self._button_clicked)
        self.button.set_sensitive(False)
        check = Gtk.Image()
        check.set_from_file('check.svg')
        self.button.set_image(check)

        self.message = Gtk.Label(label=self._message_dict['unshared'])
        self.message.set_selectable(True)
        self.message.set_single_line_mode(True)

        img = Gtk.Image()
        pb = GdkPixbuf.Pixbuf.new_from_file(
            sugar3.activity.activity.get_bundle_path() + '/dist.svg')
        img.set_from_pixbuf(pb)

        self.value = Gtk.Label()
        self.value.set_selectable(True)
        thread.start_new_thread(self._update_distance, (0, ))

        valuefont = Pango.FontDescription()
        valuefont.set_family("monospace")
        valuefont.set_absolute_size(100 * Pango.SCALE)

        self.value.modify_font(valuefont)
        self.value.set_single_line_mode(True)
        self.value.set_width_chars(6)

        eb = Gtk.EventBox()
        eb.add(self.value)
        eb.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("white"))
        eb.set_margin_left(10)
        eb.set_margin_right(10)
        eb.set_margin_top(10)

        self.fr = Gtk.Frame()
        self.fr.set_label(_('Measured distance in %s') % _('meters'))
        self.fr.set_label_align(0.5, 0.5)
        self.fr.add(eb)

        self.main_panel.pack_start(self.button, expand=False, fill=False, padding=6)
        self.main_panel.pack_start(self.message, expand=False, fill=True, padding=0)
        self.main_panel.pack_start(img, expand=True, fill=False, padding=0)
        self.main_panel.pack_start(self.fr, expand=False, fill=False, padding=10)

        self.set_canvas(self.main_panel)
        self.show_all()

        self.server_socket = None
        self.main_socket = None
        self.main_socket_addr = None
        self.main_tube_id = None
        self.initiating = False

        # get the Presence Service
        self.pservice = presenceservice.get_instance()

        # Buddy object for you
        owner = self.pservice.get_owner()
        self.owner = owner

        self.connect('shared', self._shared_cb)
        self.connect('joined', self._joined_cb)

        self.connect('key-press-event', self._keypress_cb)

    def powerd_running(self):
        self.using_powerd = os.access(POWERD_INHIBIT_DIR, os.W_OK)
        self._logger.debug("using_powerd: %d" % self.using_powerd)
        return self.using_powerd

    def _inhibit_suspend(self):
        if self.using_powerd:
            fd = open(POWERD_INHIBIT_DIR + "/%u" % os.getpid(), 'w')
            self._logger.debug("inhibit_suspend file is %s" % \
                                   POWERD_INHIBIT_DIR + "/%u" % os.getpid())
            fd.close()
            return True

        if self.ohm_keystore is not None:
            try:
                self.ohm_keystore.SetKey('suspend.inhibit', 1)
                return self.ohm_keystore.GetKey('suspend.inhibit')
            except dbus.exceptions.DBusException:
                self._logger.debug("failed to inhibit suspend")
                return False
        else:
            return False

    def _allow_suspend(self):
        if self.using_powerd:
            os.unlink(POWERD_INHIBIT_DIR + "/%u" % os.getpid())
            self._logger.debug("allow_suspend unlinking %s" % \
                                   POWERD_INHIBIT_DIR + "/%u" % os.getpid())
            return True

        if self.ohm_keystore is not None:
            try:
                self.ohm_keystore.SetKey('suspend.inhibit', 0)
                return self.ohm_keystore.GetKey('suspend.inhibit')
            except dbus.exceptions.DBusException:
                self._logger.debug("failed to allow suspend")
                return False
        else:
            return False

    def _button_clicked(self, button):
        if button.get_active():
            self._inhibit_suspend()
            self._button_event.set()
            self._logger.debug("button_clicked: self._button_event.isSet(): " \
                                   + str(self._button_event.isSet()))
            button.set_label(self._button_dict['going'])
        else:
            self._button_event.clear()
            self._allow_suspend()
            button.set_label(self._button_dict['waiting'])

    def _helper_thread(self):
        self._logger.debug("helper_thread starting")
        while True:
            self._logger.debug("helper_thread: button_event.isSet(): " \
                                   + str(self._button_event.isSet()))
            self._button_event.wait()
            self._logger.debug("initiating measurement")
            dt = arange.measure_dt_seq(self.main_socket, self.initiating,
                                       self._change_message)
            x = dt * self._t_h_bar.get_speed() - arange.OLPC_OFFSET
            self.current_distance = x
            self._update_distance(x)

    def _update_distance(self, x):
        scale = self._smoot_bar.get_scale()
        mes = locale.format("%.2f", x * scale)
        gobject_idle_do(self.value.set_text, mes)

    def read_file(self, file_path):
        f = open(file_path, 'r')
        L = f.readlines()
        f.close()
        text = L[0][:-1]  # Strip trailing "\n"
        t = locale.atof(L[1][:-1])
        h = locale.atof(L[2][:-1])
        self.value.set_text(text)
        self._t_h_bar.set_temp(t)
        self._t_h_bar.set_humid(h)

    def write_file(self, file_path):
        self.metadata['mime_type'] = 'text/plain'
        text = self.value.get_text()
        t = locale.str(self._t_h_bar.get_temp())
        h = locale.str(self._t_h_bar.get_humid())
        self.metadata['fulltext'] = text

        f = open(file_path, 'w')
        f.writelines([text + "\n", t + "\n", h + "\n"])
        f.close()

    def _change_message(self, signal):
        self._logger.debug("_change_message got signal: " + signal)
        gobject_idle_do(self.message.set_text, self._message_dict[signal])

    def _shared_cb(self, activity):
        self._logger.debug('My activity was shared')
        self.initiating = True
        self._sharing_setup()

        self._logger.debug('This is my activity: making a tube...')

        #f = os.tempnam()
        # The filename cannot be in $TMP, because this directory is not
        # visible to Telepathy.
        f = sugar3.activity.activity.get_activity_root() \
            + '/instance/my_socket'
        if os.path.exists(f):
            os.unlink(f)
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(f)

        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferStreamTube(
            SERVICE, {}, telepathy.SOCKET_ADDRESS_TYPE_UNIX,
            dbus.ByteArray(f), telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, "")

        thread.start_new_thread(self.watch_for_join, ())

    def watch_for_join(self):
        self.server_socket.listen(1)
        (self.main_socket, self.main_socket_addr) = self.server_socket.accept()
        self.main_socket.setblocking(1)
        # don't know if this works with Telepathy's pseudosockets
        #self.server_socket.close()

        self._make_ready()

    def _sharing_setup(self):
        if self.shared_activity is None:
            self._logger.error('Failed to share or join activity')
            return

        self.conn = self.shared_activity.telepathy_conn
        self.tubes_chan = self.shared_activity.telepathy_tubes_chan
        self.text_chan = self.shared_activity.telepathy_text_chan

        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'TubeStateChanged', self._tube_state_cb)

        self.shared_activity.connect('buddy-joined', self._buddy_joined_cb)
        self.shared_activity.connect('buddy-left', self._buddy_left_cb)

        # Optional - included for example:
        # Find out who's already in the shared activity:
        for buddy in self.shared_activity.get_joined_buddies():
            self._logger.debug('Buddy %s is already in the activity',
                               buddy.props.nick)

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        self._logger.error('ListTubes() failed: %s', e)

    def _joined_cb(self, activity):
        if not self.shared_activity:
            return

        # Find out who's already in the shared activity:
        n = 0
        for buddy in self.shared_activity.get_joined_buddies():
            n += 1
            self._logger.debug('Buddy %s is already in the activity' % \
                                   buddy.props.nick)

        if n <= 2:
            self._logger.debug('Joined an existing shared activity')
            self.initiating = False
            self._sharing_setup()

            self._logger.debug(
                'This is not my activity: waiting for a tube...')
            self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
                reply_handler=self._list_tubes_reply_cb,
                error_handler=self._list_tubes_error_cb)
        else:
            self._logger.debug("There are already two people, not joining")
            self.shared_activity.leave()
            thread.start_new_thread(self._change_message, ('full',))

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        self._logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                           'params=%r state=%d', id, initiator, type, service,
                           params, state)
        if (type == telepathy.TUBE_TYPE_STREAM and
            service == SERVICE and self.main_tube_id is None):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.main_tube_id = id
                self.main_socket_addr = str(
                    self.tubes_chan[
                        telepathy.CHANNEL_TYPE_TUBES].AcceptStreamTube(
                        id, telepathy.SOCKET_ADDRESS_TYPE_UNIX,
                        telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, "",
                        byte_arrays=True))

    def _tube_state_cb(self, tube_id, tube_state):
        if (self.main_socket is None) and \
            (tube_state == telepathy.TUBE_STATE_OPEN) and \
            (tube_id == self.main_tube_id):

            self.main_socket = socket.socket(
                socket.AF_UNIX, socket.SOCK_STREAM)
            self.main_socket.setblocking(1)
            self.main_socket.connect(self.main_socket_addr)
            thread.start_new_thread(self._make_ready, ())

    def _make_ready(self):
        gobject_idle_do(self.button.set_sensitive, True)
        self._change_message('ready')

    def _buddy_joined_cb(self, activity, buddy):
        self._logger.debug('Buddy %s joined' % buddy.props.nick)

    def _buddy_left_cb(self, activity, buddy):
        self._logger.debug('Buddy %s left' % buddy.props.nick)

    def _get_buddy(self, cs_handle):
        '''Get a Buddy from a channel specific handle.'''
        self._logger.debug('Trying to find owner of handle %u...', cs_handle)
        group = self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP]
        my_csh = group.GetSelfHandle()
        self._logger.debug('My handle in that group is %u', my_csh)
        if my_csh == cs_handle:
            handle = self.conn.GetSelfHandle()
            self._logger.debug('CS handle %u belongs to me, %u',
                               cs_handle, handle)
        elif group.GetGroupFlags() & \
                telepathy.CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
            handle = group.GetHandleOwners([cs_handle])[0]
            self._logger.debug('CS handle %u belongs to %u', cs_handle, handle)
        else:
            handle = cs_handle
            self._logger.debug('non-CS handle %u belongs to itself', handle)
            # XXX: deal with failure to get the handle owner
            assert handle != 0
        return self.pservice.get_buddy_by_telepathy_handle(
            self.conn.service_name, self.conn.object_path, handle)

    # KP_End == check gamekey = 65436
    # KP_Page_Down == X gamekey = 65435
    # KP_Home == box gamekey = 65429
    # KP_Page_Up == O gamekey = 65434
    def _keypress_cb(self, widget, event):
        self._logger.debug("key press: " + Gdk.keyval_name(event.keyval) \
                               + " " + str(event.keyval))
        if event.keyval == 65436:
            self.button.clicked()
        return False
