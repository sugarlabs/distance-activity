# Copyright 2009 Benjamin M. Schwartz
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

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

import arange
import locale
from gettext import gettext


class CalibrationToolbar(Gtk.Toolbar):

    def __init__(self):
        GObject.GObject.__init__(self)
        
        offset_label = Gtk.Label(label=gettext("Calibration Offset (meters): "))
        self._offset_field = Gtk.Entry()
        self._offset_field.set_max_length(10)
        self._offset_field.set_width_chars(10)
        
        bigbox = Gtk.Box(orientation = Gtk.Orientation.HORIZONTAL)
        
        bigbox.pack_start(offset_label, expand=False, fill=False)
        bigbox.pack_end(self._offset_field, expand=False, fill=False)
        
        self.set_offset(arange.OLPC_OFFSET)

        tool_item = Gtk.ToolItem()
        tool_item.add(bigbox)
        tool_item.set_expand(False)
        self.insert(tool_item, 0)
        tool_item.show()
        
    def get_offset(self):
        try:
            t = locale.atof(self._offset_field.get_text())
        except:
            t = 0
        finally:
            return t
        
    def set_offset(self, t):
        try:
            self._offset_field.set_text(locale.str(t))
            return True
        except:
            return False
