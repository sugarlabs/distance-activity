# Copyright 2007 Benjamin M. Schwartz
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

import gi
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
import arange
import locale
from gettext import gettext as _


def _label_factory(label, toolbar):
    ''' Factory for adding a label to a toolbar '''
    my_label = Gtk.Label(label=label)
    my_label.set_line_wrap(False)
    my_label.show()
    _toolitem = Gtk.ToolItem()
    _toolitem.add(my_label)
    toolbar.insert(_toolitem, -1)
    _toolitem.show()
    return my_label


def _entry_factory(length, toolbar, callback):
    ''' Factory for adding a text enrty to a toolbar '''
    my_entry = Gtk.Entry()
    my_entry.set_max_length(length)
    my_entry.set_width_chars(length)
    my_entry.connect('changed', callback)
    my_entry.show()
    _toolitem = Gtk.ToolItem()
    _toolitem.add(my_entry)
    toolbar.insert(_toolitem, -1)
    _toolitem.show()
    return my_entry


def _separator_factory(toolbar, expand=False, visible=False):
    """ add a separator to a toolbar """
    _separator = Gtk.SeparatorToolItem()
    _separator.props.draw = visible
    _separator.set_expand(expand)
    toolbar.insert(_separator, -1)
    _separator.show()


class TempToolbar(Gtk.Toolbar):
    _speed = 0

    def __init__(self):
        GObject.GObject.__init__(self)

        temp_label = _label_factory(_("Temperature (C): "), self)
        self._temp_field = _entry_factory(6, self, self._update_cb)

        _separator_factory(self)

        humid_label = _label_factory(_("Relative Humidity (%): "), self)
        self._humid_field = _entry_factory(5, self, self._update_cb)
        
        _separator_factory(self)

        results_label = _label_factory(_("Speed of Sound (m/s): "), self)
        self._result = _label_factory('', self)
        
        self.set_temp(25)
        self.set_humid(60)
        self.update_speed()

    def get_temp(self):
        try:
            t = locale.atof(self._temp_field.get_text())
        except:
            return None
        if t > 70:
            return None
        if t < -20:
            return None
        return t

    def set_temp(self, t):
        try:
            self._temp_field.set_text(locale.str(max(-20, min(70, t))))
            return True
        except:
            return False

    def get_humid(self):
        try:
            t = locale.atof(self._humid_field.get_text())
        except:
            return None
        if t > 100:
            return None
        if t < 0:
            return None
        return t

    def set_humid(self, h):
        try:
            self._humid_field.set_text(locale.str(max(0, min(100, h))))
            return True
        except:
            return False
    
    def get_speed(self):
        return self._speed
        
    def _set_speed(self, s):
        self._speed = s
        try:
            self._result.set_text(locale.format('%.2f', s))
            return True
        except:
            return False
            
    def _update_cb(self, widget=None):
        GObject.idle_add(self.update_speed)
    
    def update_speed(self):
        t = self.get_temp()
        h = self.get_humid()

        if (t is not None) and (h is not None):
            s = arange.speed_of_sound(t, h / 100)
            self._set_speed(s)
        else:
            self._result.set_text('')

        return False
