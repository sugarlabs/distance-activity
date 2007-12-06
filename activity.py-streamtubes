# Copyright 2007 Collabora Ltd.
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

"""AcousticMeasure Activity: Uses sound propagation delay to measure distance"""

import gobject
import gtk
import gtk.gdk
import time
import logging
import telepathy
import telepathy.client
import pango
import locale

from dbus import Interface
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

import sugar.activity.activity
from sugar.activity.activity import Activity, ActivityToolbox
from sugar.presence import presenceservice

from gettext import gettext

# will eventually be imported from sugar
from sugar.presence.tubeconn import TubeConnection

#For socket code
import threading
import thread
import socket
import base64
import os
import dbus

#import socket_test as arange
import arange
import atm_toolbars

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
    gobject.idle_add(helper, retval, func, args, ev)
    ev.wait()
    return retval[0]

class AcousticMeasureActivity(Activity):
    """AcousticMeasure Activity as specified in activity.info"""
    
    _message_dict = {}
    _button_dict = {}
    
    def __init__(self, handle):
        """Set up the Acoustic Tape Measure activity."""
        Activity.__init__(self, handle)
        gobject.threads_init()
        #self.set_title(gettext('Acoustic Tape Measure Activity'))
        self._logger = logging.getLogger('acousticmeasure-activity')

        self._logger.debug("locale: " + locale.setlocale(locale.LC_ALL, ''))

        # top toolbar with share and close buttons:
        toolbox = ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        self._t_h_bar = atm_toolbars.TempToolbar()
        toolbox.add_toolbar(gettext("Atmosphere"), self._t_h_bar)
        
        #worker thread
        self._button_event = threading.Event()
        thread.start_new_thread(self._helper_thread, ())

        # Main Panel GUI
        self.main_panel = gtk.VBox()
        self._message_dict['unshared'] = gettext("To measure the distance between two laptops, you must first share this Activity.")
        self._message_dict['ready'] = gettext("Press the button to measure the distance to another laptop")
        self._message_dict['preparing'] = gettext("Preparing to measure distance")
        self._message_dict['waiting'] = gettext("Ready to make a measurement.  Waiting for partner to be ready.")
        self._message_dict['playing'] = gettext("Recording sound from each laptop.")
        self._message_dict['processing'] = gettext("Processing recorded audio.")
        self._message_dict['done'] = self._message_dict['ready']
        self._message_dict['full'] = gettext("This activity already has two participants, so you cannot join.")
        
        self._button_dict['waiting'] = gettext("Begin Measuring Distance")
        self._button_dict['going'] = gettext("Stop Measuring Distance")
        
        self.button = gtk.ToggleButton(label=self._button_dict['waiting'])
        self.button.connect('clicked',self._button_clicked)
        self.button.set_sensitive(False)
        check = gtk.Image()
        check.set_from_file('check.svg')
        self.button.set_image(check)
        
        self.message = gtk.Label(self._message_dict['unshared'])
        self.message.set_selectable(True)
        self.message.set_single_line_mode(True)

        img = gtk.Image()
        pb = gtk.gdk.pixbuf_new_from_file(sugar.activity.activity.get_bundle_path() + '/dist.svg')
        img.set_from_pixbuf(pb)

        self.value = gtk.Label()
        self.value.set_selectable(True)
        thread.start_new_thread(self._update_distance, (0,))
        
        valuefont = pango.FontDescription()
        valuefont.set_family("monospace")
        valuefont.set_absolute_size(300*pango.SCALE)
        
        self.value.modify_font(valuefont)
        self.value.set_single_line_mode(True)
        self.value.set_width_chars(6)

        eb = gtk.EventBox()
        eb.add(self.value)
        eb.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("white"))
        
        fr = gtk.Frame(gettext("Measured Distance in Meters"))
        fr.set_label_align(0.5,0.5)
        fr.add(eb)

        self.main_panel.pack_start(self.button, expand=False, padding=6)
        self.main_panel.pack_start(self.message, expand=False)
        self.main_panel.pack_start(img, expand=True, fill=False)
        self.main_panel.pack_start(fr, expand=True, fill=False, padding=10)

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
                
    def _button_clicked(self, button):
        if button.get_active():
            self._button_event.set()
            self._logger.debug("button_clicked: self._button_event.isSet(): " + str(self._button_event.isSet()))
            button.set_label(self._button_dict['going'])
        else:
            self._button_event.clear()
            button.set_label(self._button_dict['waiting'])
            
    def _helper_thread(self):
        self._logger.debug("helper_thread starting")
        while True:
            self._logger.debug("helper_thread: button_event.isSet(): " + str(self._button_event.isSet()))
            self._button_event.wait()
            self._logger.debug("initiating measurement")
            dt = arange.measure_dt_seq(self.main_socket, self.initiating, self._change_message)
            x = dt * self._t_h_bar.get_speed() - arange.OLPC_OFFSET
            self._update_distance(x)
    
    def _update_distance(self, x):
        mes = locale.format("%.2f", x)
        gobject_idle_do(self.value.set_text, mes)

    def read_file(self, file_path):
        f = open(file_path, 'r')
        L = f.readlines()
        f.close()
        text = L[0][:-1] #Strip trailing "\n"
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
    
    def _change_message(self,signal):
        self._logger.debug("_change_message got signal: " + signal)
        gobject_idle_do(self.message.set_text, self._message_dict[signal])

    def _shared_cb(self, activity):
        self._logger.debug('My activity was shared')
        self.initiating = True
        self._sharing_setup()

        self._logger.debug('This is my activity: making a tube...')
        
        f = os.tempnam()
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(f)
        
        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferStreamTube(
            SERVICE, {}, telepathy.SOCKET_ADDRESS_TYPE_UNIX, dbus.ByteArray(f),
            telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, "")
        
        thread.start_new_thread(self.watch_for_join, ())
    
    def watch_for_join(self):
        self.server_socket.listen(1)
        (self.main_socket, self.main_socket_addr) = self.server_socket.accept()
        self.main_socket.setblocking(1)
        #self.server_socket.close() #don't know if this works with Telepathy's pseudosockets
        
        self._make_ready()   

    def _sharing_setup(self):
        if self._shared_activity is None:
            self._logger.error('Failed to share or join activity')
            return
        
        self.conn = self._shared_activity.telepathy_conn
        self.tubes_chan = self._shared_activity.telepathy_tubes_chan
        self.text_chan = self._shared_activity.telepathy_text_chan
        
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'NewTube', self._new_tube_cb)
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal(
            'TubeStateChanged', self._tube_state_cb)
        
        self._shared_activity.connect('buddy-joined', self._buddy_joined_cb)
        self._shared_activity.connect('buddy-left', self._buddy_left_cb)
        
        # Optional - included for example:
        # Find out who's already in the shared activity:
        for buddy in self._shared_activity.get_joined_buddies():
            self._logger.debug('Buddy %s is already in the activity',
                               buddy.props.nick)

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        self._logger.error('ListTubes() failed: %s', e)

    def _joined_cb(self, activity):
        if not self._shared_activity:
            return

        # Find out who's already in the shared activity:
        n = 0
        for buddy in self._shared_activity.get_joined_buddies():
            n += 1
            self._logger.debug('Buddy %s is already in the activity' % buddy.props.nick)

        if n <= 2:
            self._logger.debug('Joined an existing shared activity')
            self.initiating = False
            self._sharing_setup()

            self._logger.debug('This is not my activity: waiting for a tube...')
            self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
                reply_handler=self._list_tubes_reply_cb,
                error_handler=self._list_tubes_error_cb)
        else:
            self._logger.debug("There are already two people, not joining")
            self._shared_activity.leave()
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
                    self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptStreamTube(id,
                    telepathy.SOCKET_ADDRESS_TYPE_UNIX,
                    telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, "", byte_arrays=True))
    
    def _tube_state_cb(self, tube_id, tube_state):
        if (self.main_socket is None) and \
            (tube_state == telepathy.TUBE_STATE_OPEN) and \
            (tube_id == self.main_tube_id):

            self.main_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.main_socket.setblocking(1)
            self.main_socket.connect(self.main_socket_addr)
            thread.start_new_thread(self._make_ready, ())
            
    def _make_ready(self):
            gobject_idle_do(self.button.set_sensitive, True)
            self._change_message('ready')

    def _buddy_joined_cb (self, activity, buddy):
        self._logger.debug('Buddy %s joined' % buddy.props.nick)

    def _buddy_left_cb (self, activity, buddy):
        self._logger.debug('Buddy %s left' % buddy.props.nick)

    def _get_buddy(self, cs_handle):
        """Get a Buddy from a channel specific handle."""
        self._logger.debug('Trying to find owner of handle %u...', cs_handle)
        group = self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP]
        my_csh = group.GetSelfHandle()
        self._logger.debug('My handle in that group is %u', my_csh)
        if my_csh == cs_handle:
            handle = self.conn.GetSelfHandle()
            self._logger.debug('CS handle %u belongs to me, %u', cs_handle, handle)
        elif group.GetGroupFlags() & telepathy.CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
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
        self._logger.debug("key press: " + gtk.gdk.keyval_name(event.keyval)+ " " + str(event.keyval))
        if event.keyval == 65436:
            self.button.clicked()
        return False
