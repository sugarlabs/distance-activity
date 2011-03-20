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

import gtk
import gobject
import arange
import locale
from gettext import gettext

class TempToolbar(gtk.Toolbar):
    _speed = 0

    def __init__(self):
        gtk.Toolbar.__init__(self)
        
        temp_label = gtk.Label(gettext("Temperature (C): "))
        self._temp_field = gtk.Entry()
        self._temp_field.set_max_length(6)
        self._temp_field.set_width_chars(6)
        self._temp_field.connect("changed", self._update_cb)

        temp_group = gtk.HBox()
        temp_group.pack_start(temp_label, expand=False, fill=False)
        temp_group.pack_end(self._temp_field, expand=False,fill=False)
        
        humid_label = gtk.Label(gettext("Relative Humidity (%): "))
        self._humid_field = gtk.Entry()
        self._humid_field.set_max_length(5)
        self._humid_field.set_width_chars(5)
        self._humid_field.connect("changed", self._update_cb)
        
        humid_group = gtk.HBox()
        humid_group.pack_start(humid_label, expand=False, fill=False)
        humid_group.pack_end(self._humid_field, expand=False, fill=False)
        
        result_label = gtk.Label(gettext("Speed of Sound (m/s): "))
        self._result = gtk.Label()
        
        result_group = gtk.HBox()
        result_group.pack_start(result_label, expand=False, fill=False)
        result_group.pack_end(self._result, expand=False, fill=False)
        
        self.bigbox = gtk.HBox()
        
        self.bigbox.pack_start(temp_group, expand=False, fill=False)
        self.bigbox.pack_start(humid_group, expand=True, fill=False)
        self.bigbox.pack_end(result_group, expand=False, fill=False)
        
        self.set_temp(25)
        self.set_humid(60)
        self.update_speed()

        tool_item = gtk.ToolItem()
        tool_item.add(self.bigbox)
        tool_item.set_expand(True)
        self.insert(tool_item, 0)
        tool_item.show()
        
        
    def get_temp(self):
        try:
            t = locale.atof(self._temp_field.get_text())
        except:
            t = None
        finally:
            return t
        
    def set_temp(self, t):
        try:
            self._temp_field.set_text(locale.str(t))
            return True
        except:
            return False
    
    def get_humid(self):
        try:
            t = locale.atof(self._humid_field.get_text())
        except:
            t = None
        finally:
            return t
        
    def set_humid(self, h):
        try:
            self._humid_field.set_text(locale.str(max(0,min(100,h))))
            return True
        except:
            return False
    
    def get_speed(self):
        return self._speed
        
    def _set_speed(self, s):
        self._speed = s
        try:
            self._result.set_text(locale.format('%.2f',s))
            return True
        except:
            return False
            
    def _update_cb(self, widget=None):
        gobject.idle_add(self.update_speed)
    
    def update_speed(self):
        t = self.get_temp()
        h = self.get_humid()
        
        if (t is not None) and (h is not None):
            s = arange.speed_of_sound(t, h/100)
            self._set_speed(s)
        return False
