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

import hippo
import gtk
import time
import logging
import telepathy
import telepathy.client

from dbus import Interface
from dbus.service import method, signal
from dbus.gobject_service import ExportedGObject

from sugar.activity.activity import Activity, ActivityToolbox
from sugar.presence import presenceservice

# will eventually be imported from sugar
from sugar.presence.tubeconn import TubeConnection

#For socket code
import threading
import thread
import socket

#import socket_test as arange
import arange

SERVICE = "org.laptop.AcousticMeasure"
IFACE = SERVICE
PATH = "/org/laptop/AcousticMeasure"


class AcousticMeasureActivity(Activity):
    """AcousticMeasure Activity as specified in activity.info"""
    
    _message_dict = {}
    
    def __init__(self, handle):
        """Set up the AcousticMeasure activity."""
        Activity.__init__(self, handle)
        self.set_title('AcousticMeasure Activity')
        self._logger = logging.getLogger('acousticmeasure-activity')

        # top toolbar with share and close buttons:
        toolbox = ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        # Hippo Canvas:
        hbox = hippo.CanvasBox(spacing=4,
            orientation=hippo.ORIENTATION_HORIZONTAL)

        self.main_panel = hippo.CanvasBox(spacing=4,
            orientation=hippo.ORIENTATION_VERTICAL)
        self._message_dict['unshared'] = "To measure the distance between two laptops, you must first share this Activity."
        self._message_dict['ready'] = "Press this button to measure the distance to another laptop"
        self._message_dict['preparing'] = "Preparing to measure distance"
        self._message_dict['waiting'] = "Ready to make a measurement.  Waiting for partner to be ready."
        self._message_dict['playing'] = "Measuring distance between the laptops."
        self._message_dict['processing'] = "Processing measurement data"
        self._message_dict['done'] = self._message_dict['ready']
        
        self.button = gtk.Button(label=self._message_dict['unshared'])
        self.button.connect('clicked',self._button_clicked)
        self.button.set_sensitive(False)
        self.text = gtk.Label()
        self.text.set_selectable(True)
        self.main_panel.append(hippo.CanvasWidget(widget=self.button))
        self.main_panel.append(hippo.CanvasWidget(widget=self.text))
        hbox.append(self.main_panel, hippo.PACK_EXPAND)

        canvas = hippo.Canvas()
        canvas.set_root(hbox)
        self.set_canvas(canvas)
        self.show_all()

        self.hellotube = None  # Shared session

        # get the Presence Service
        self.pservice = presenceservice.get_instance()
        name, path = self.pservice.get_preferred_connection()
        self.tp_conn_name = name
        self.tp_conn_path = path
        self.conn = telepathy.client.Connection(name, path)
        self.initiating = None
        
        self.connect('shared', self._shared_cb)

        # Buddy object for you
        owner = self.pservice.get_owner()
        self.owner = owner

        if self._shared_activity:
            # we are joining the activity
            self.connect('joined', self._joined_cb)
            self._shared_activity.connect('buddy-joined',
                                          self._buddy_joined_cb)
            self._shared_activity.connect('buddy-left',
                                          self._buddy_left_cb)
            if self.get_shared():
                # we've already joined
                self._joined_cb()
                
    def _button_clicked(self, button):
        thread.start_new_thread(self._do_sockets,())
    
    def _do_sockets(self):
        self.button.set_sensitive(False)
        self._logger.debug("initiating socket_test")
        dt = arange.measure_dt_seq(self.hellotube, self.initiating, self._change_button_label)
        x = dt * arange.speed_of_sound() - arange.OLPC_OFFSET
        mes = "Distance is %(num).2f meters.\n" % {'num': dt}
        self._logger.debug("socket_test: " + mes)
        self.text.set_label(mes + self.text.get_label())
        self.button.set_sensitive(True)
    
    def _change_button_label(self,signal):
        self.button.set_label(self._message_dict[signal])

    def _shared_cb(self, activity):
        self._logger.debug('My activity was shared')
        self.initiating = True
        self._setup()

        for buddy in self._shared_activity.get_joined_buddies():
            self._logger.debug('Buddy %s is already in the activity' %
                buddy.props.nick)

        self._shared_activity.connect('buddy-joined', self._buddy_joined_cb)
        self._shared_activity.connect('buddy-left', self._buddy_left_cb)

        self._logger.debug('This is my activity: making a tube...')
#        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
#            telepathy.TUBE_TYPE_DBUS, SERVICE, {})
        id = self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferDBusTube(
            SERVICE, {})

    def _setup(self):
        if self._shared_activity is None:
            self._logger.error('Failed to share or join activity')
            return

        bus_name, conn_path, channel_paths =\
            self._shared_activity.get_channels()

        # Work out what our room is called and whether we have Tubes already
        room = None
        tubes_chan = None
        text_chan = None
        for channel_path in channel_paths:
            channel = telepathy.client.Channel(bus_name, channel_path)
            htype, handle = channel.GetHandle()
            if htype == telepathy.HANDLE_TYPE_ROOM:
                self._logger.debug('Found our room: it has handle#%d "%s"',
                    handle, self.conn.InspectHandles(htype, [handle])[0])
                room = handle
                ctype = channel.GetChannelType()
                if ctype == telepathy.CHANNEL_TYPE_TUBES:
                    self._logger.debug('Found our Tubes channel at %s', channel_path)
                    tubes_chan = channel
                elif ctype == telepathy.CHANNEL_TYPE_TEXT:
                    self._logger.debug('Found our Text channel at %s', channel_path)
                    text_chan = channel

        if room is None:
            self._logger.error("Presence service didn't create a room")
            return
        if text_chan is None:
            self._logger.error("Presence service didn't create a text channel")
            return

        # Make sure we have a Tubes channel - PS doesn't yet provide one
        if tubes_chan is None:
            self._logger.debug("Didn't find our Tubes channel, requesting one...")
            tubes_chan = self.conn.request_channel(telepathy.CHANNEL_TYPE_TUBES,
                telepathy.HANDLE_TYPE_ROOM, room, True)

        self.tubes_chan = tubes_chan
        self.text_chan = text_chan

        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal('NewTube',
            self._new_tube_cb)

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)
        

    def _list_tubes_error_cb(self, e):
        self._logger.error('ListTubes() failed: %s', e)

    def _joined_cb(self, activity):
        if not self._shared_activity:
            return

        # Find out who's already in the shared activity:
        for buddy in self._shared_activity.get_joined_buddies():
            self._logger.debug('Buddy %s is already in the activity' % buddy.props.nick)

        self._logger.debug('Joined an existing shared activity')
        self.initiating = False
        self._setup()

        self._logger.debug('This is not my activity: waiting for a tube...')
        self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _new_tube_cb(self, id, initiator, type, service, params, state):
        self._logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                     'params=%r state=%d', id, initiator, type, service,
                     params, state)
        if (type == telepathy.TUBE_TYPE_DBUS and
            service == SERVICE):
            if state == telepathy.TUBE_STATE_LOCAL_PENDING:
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES].AcceptDBusTube(id)
            tube_conn = TubeConnection(self.conn,
                self.tubes_chan[telepathy.CHANNEL_TYPE_TUBES],
                id, group_iface=self.text_chan[telepathy.CHANNEL_INTERFACE_GROUP])
            self.hellotube = HelloTube(tube_conn, self.initiating, self._get_buddy)
            self.button.set_sensitive(True)
            self.button.set_label(self._message_dict['ready'])

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
            logger.debug('non-CS handle %u belongs to itself', handle)
            # XXX: deal with failure to get the handle owner
            assert handle != 0
        return self.pservice.get_buddy_by_telepathy_handle(self.tp_conn_name,
                self.tp_conn_path, handle)

class HelloTube(ExportedGObject):
    """The bit that talks over the TUBES!!!"""

    def __init__(self, tube, is_initiator, get_buddy):
        super(HelloTube, self).__init__(tube, PATH)
        self._logger = logging.getLogger('acousticmeasure-activity.HelloTube')
        self.tube = tube
        self.is_initiator = is_initiator
        self.entered = False  # Have we set up the tube?
        self.helloworld = False  # Trivial "game state"
        self._get_buddy = get_buddy  # Converts handle to Buddy object
        self.tube.watch_participants(self.participant_change_cb)

    def participant_change_cb(self, added, removed):
        self._logger.debug('Adding participants: %r' % added)
        self._logger.debug('Removing participants: %r' % type(removed))
        for handle, bus_name in added:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Buddy %s was added' % buddy.props.nick)
        for handle in removed:
            buddy = self._get_buddy(handle)
            if buddy is not None:
                self._logger.debug('Buddy %s was removed' % buddy.props.nick)
        if not self.entered:
            if self.is_initiator:
                self._logger.debug("I'm initiating the tube, will "
                    "watch for hellos.")
                self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
                    path=PATH, sender_keyword='sender')
            else:
                self._logger.debug('Hello, everyone! What did I miss?')
                self.Hello()
        self.entered = True

    @signal(dbus_interface=IFACE, signature='')
    def Hello(self):
        """Say Hello to whoever else is in the tube."""
        self._logger.debug('I said Hello.')

    @method(dbus_interface=IFACE, in_signature='s', out_signature='', sender_keyword='sender')
    def World(self, game_state, sender=None):
        """To be called on the incoming XO after they Hello."""
        if not self.helloworld:
            self._logger.debug('Somebody said World.')
            self.helloworld = game_state
            # now I can World others
#            self.add_hello_handler()
            self.tube.add_signal_receiver(self.hello_cb, 'Hello', IFACE,
                path=PATH, sender_keyword='sender')
            self._remote_socket = self.tube.get_object(sender, PATH)
            self._remote_socket_waiter.set()             
        else:
            self._logger.debug("I've already been welcomed, doing nothing")

    def hello_cb(self, sender=None):
        """Somebody Helloed me. World them."""
        if sender == self.tube.get_unique_name():
            # sender is my bus name, so ignore my own signal
            return
        self._logger.debug('Newcomer %s has joined', sender)
        self._logger.debug('Welcoming newcomer and sending them the game state')
        game_state = str(time.time())  # Something to send for demo
        self._remote_socket = self.tube.get_object(sender, PATH)
        self._remote_socket_waiter.set()
        self._remote_socket.World(game_state, dbus_interface=IFACE)
    
    def _noop(self, *args):
        pass
    
    #### Begin socket section
    _buffer = ''
    _buff_waiter = threading.Event()
    
    _timeout = None
    
    family = socket.AF_UNIX
    type = socket.SOCK_STREAM
    proto = -1
    
    _recv_allowed = True
    _send_allowed = True
    
    _remote_socket = None
    _remote_socket_waiter = threading.Event()

    @method(dbus_interface = IFACE, in_signature = 'ay', out_signature = '')
    def _handle_incoming(self, message):
        self._logger.debug("_handle_incoming: " + message)
        if self._recv_allowed:
            self._buffer += message
            if len(self._buffer) > 0:
                self._buff_waiter.set()
    
    def recv(self, bufsize):
        self._logger.debug("recv")
        self._logger.debug("buff_waiter.isSet: " + str(self._buff_waiter.isSet()))
        self._logger.debug("buffer: " + self._buffer)
        self._buff_waiter.wait(self._timeout)
        if len(self._buffer) == 0:
            raise 'error: buffer is empty'
        retval = self._buffer[:bufsize]
        self._buffer = self._buffer[bufsize:]
        if len(self._buffer) == 0:
            self._buff_waiter.clear()
        self._logger.debug("received: " + retval)
        return retval
    
    def recvfrom(self, bufsize):
        return (self.recv(bufsize), self.getpeername())
    
    def send(self, string, flags=0):
        self.sendall(string)
    
    def sendall(self, string, flags=0):
        if self._send_allowed:
            self._logger.debug("sendall")
            self._remote_socket_waiter.wait(self._timeout)
            self._logger.debug("sendall: " + string)
            self._remote_socket._handle_incoming(string)
            self._logger.debug("sendall; sent")
            return len(string)
        else:
            self._logger.debug("sendall not allowed")
            return 0
        
    def setblocking(self, flag):
        if flag == 0:
            self._timeout = 0
        else:
            self._timeout = None
            self.button.set_sensitive(False)
        if self.initiating:
            self._logger.debug("initiating socket_test")
            self._logger.debug("socket_test: " + socket_test.server(self.hellotube))
        else:
            self._logger.debug("initiating socket_test")
            self._logger.debug("socket_test: " + socket_test.client(self.hellotube))
        self.button.set_sensitive(True)
    def settimeout(self, value):
        self._timeout = value
    
    def gettimeout(self, ):
        return self._timeout
    
    def close(self):
        self.tube.close()
    
    def _unimplemented(self):
        raise "error: unimplemented"
        
    def fileno(self):
        return self.tube.get_unix_fd()
        
    def getpeername(self):
        return self.tube.get_peer_unix_process_id()
    
    def getsockname(self):
        return self.tube.get_unique_name()
    
    def getsockopt(self):
        return 0
    
    def setsockopt(self, level,optname,value):
        pass
    
    def shutdown(self, how):
        if how == socket.SHUT_RD or how == socket.SHUT_RDWR:
            self._recv_allowed = False
        if how == socket.SHUT_WR or how == socket.SHUT_RDWR:
            self._send_allowed = False
        if (not self._recv_allowed) and (not self._send_allowed):
            self.close()
        
        
    accept = _unimplemented
    bind = _unimplemented
    connect = _unimplemented
    connect_ex = _unimplemented
    listen = _unimplemented
    makefile = _unimplemented
    sendto = _unimplemented

