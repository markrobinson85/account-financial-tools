# -*- coding: utf-8 -*-

from openerp import api, fields, models, _


class AccountMoveRecurring(models.Model):
    _inherit = "account.move"

    recurring_id = fields.Many2one('account.move.recurring', string='Recurring Entry', copy=False, readonly=True,
                                   help='This journal entry was created automatically from a Recurring Journal Entry.')

