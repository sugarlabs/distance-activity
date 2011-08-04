# Copyright 2007 Benjamin M. Schwartz
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

import gtk
from gettext import gettext as _

from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox

METERS = 0
CENTIMETERS = 1
INCHES = 2
FEET = 3
YARDS = 4
CUSTOM = 5
UNITS = [_('meters'), _('centimeters'),
         # TRANS: English units of measure
         _('inches'), _('feet'), _('yards'),
         _('custom units')]
UNIT_DICTIONARY = {METERS: (_('meters'), 1.0),
                   CENTIMETERS: (_('centimeters'), 10.0),
                   INCHES: (_('inches'), 39.37),
                   FEET: (_('feet'), 3.28),
                   YARDS: (_('yards'), 1.09),
                   CUSTOM: (_('custom units'), None)}


def _label_factory(label, toolbar):
    ''' Factory for adding a label to a toolbar '''
    my_label = gtk.Label(label)
    my_label.set_line_wrap(True)
    my_label.show()
    _toolitem = gtk.ToolItem()
    _toolitem.add(my_label)
    toolbar.insert(_toolitem, -1)
    _toolitem.show()
    return my_label


def _combo_factory(combo_array, default, tooltip, callback, toolbar):
    '''Factory for making a toolbar combo box'''
    my_combo = ComboBox()
    if hasattr(my_combo, 'set_tooltip_text'):
        my_combo.set_tooltip_text(tooltip)

    my_combo.connect('changed', callback)

    for i, s in enumerate(combo_array):
        my_combo.append_item(i, s, None)

    toolbar.insert(ToolComboBox(my_combo), -1)

    my_combo.set_active(default)

    return my_combo


class SmootToolbar(gtk.Toolbar):
    ''' Defines a toolbar for specifying units of measure '''

    def __init__(self, parent):
        gtk.Toolbar.__init__(self)

        self._parent = parent
        self._unit_name = _('meters')
        # Conversion factor between meters and custom units
        self._unit_scale = 1.0

        label = _label_factory(_('Choose a unit of measure:'), self)
        label.show()

        self._unit_combo = _combo_factory(UNITS, METERS, _('select units'),
                                          self._unit_combo_cb, self)
        self._unit_combo.show()

        self._factor_label = _label_factory(' ', self)
        self._factor_label.show()

    def get_name(self):
        return self._unit_name

    def set_name(self, name):
        self._unit_name = name
        if hasattr(self._parent, 'fr'):
            self._parent.fr.set_label(
                _('Measured distance in %s') % (self._unit_name))
        if name == _('meters'):
            self._factor_label.set_label(' ')
        else:
            self._factor_label.set_label(_('%0.2f %s per meter') % (
                    self._unit_scale, name))

    def get_scale(self):
        return self._unit_scale

    def set_scale(self, scale):
        if scale is None:
            if self._parent.current_distance > 0:
                self._unit_scale = (1.0 / self._parent.current_distance)
            else:
                self._unit_scale = 1.0
        else:
            self._unit_scale = scale

    def _unit_combo_cb(self, arg=None):
        ''' Read value of predefined conversion factors from combo box '''
        try:
            self.set_scale(
                UNIT_DICTIONARY[self._unit_combo.get_active()][1])
            self.set_name(
                UNIT_DICTIONARY[self._unit_combo.get_active()][0])
        except KeyError:
            pass
