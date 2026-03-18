# -*- coding: utf-8 -*-
##############################################################################
#
#    MoviTrack
#    Copyright (C) 2020-TODAY MoviTrack.
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    GENERAL PUBLIC LICENSE (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import fields, models


class CountryState(models.Model):
    _name = 'res.country.state'
    _inherit = 'res.country.state'
    _description = "Country states"

    municipality_ids = fields.One2many('res.country.state.municipality', 'state_id',
                                       string='Municipalities in this state')
    ubigeo = fields.Char(string='ubigeo code', size=2)


class StateMunicipality(models.Model):
    _name = 'res.country.state.municipality'
    _description = "State municipalities"

    state_id = fields.Many2one('res.country.state', string='Estado', required=True,
                               help='Name of the State to which the municipality belongs')
    name = fields.Char('Municipio', required=True, help='Municipality name')
    parish_ids = fields.One2many('res.country.state.municipality.parish', 'municipality_id',
                                 string='Parishes in this municipality')
    ubigeo = fields.Char(string='ubigeo code', size=4)


class MunicipalityParish(models.Model):
    _name = 'res.country.state.municipality.parish'
    _description = "Municipality parishes"

    municipality_id = fields.Many2one('res.country.state.municipality', string='Municipio',
                                      help='Name of the Municipality to which the parish belongs')
    name = fields.Char('Parroquia', required=True, help='Parish name')
    ubigeo = fields.Char(string='ubigeo code', size=6)
