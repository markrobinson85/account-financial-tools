# -*- coding: utf-8 -*-

import base64
import json
from lxml import etree
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from openerp import api, fields, models, _
from openerp.tools import float_is_zero, float_compare, DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.misc import formatLang

from openerp.exceptions import UserError, RedirectWarning, ValidationError

import openerp.addons.decimal_precision as dp
import logging

_logger = logging.getLogger(__name__)


class AccountMoveRecurring(models.Model):
    _name = "account.move.recurring"
    _inherit = ['mail.thread']
    _description = 'Recurring Journal Entry'

    name = fields.Char('Number', readonly=True, default=lambda self: self.env['ir.sequence'].next_by_code('account.move.recurring'))

    partner_id = fields.Many2one('res.partner', compute='_compute_partner_id', string="Partner", store=True, readonly=True, track_visibility='onchange')

    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, required=True, track_visibility='onchange',)

    # active = fields.Boolean('Active', track_visibility='onchange', default=True)

    date_last = fields.Date('Date Last Posted', readonly=True)

    date_next = fields.Date('Next Entry Date', track_visibility='onchange', help='The date of the next recurring journal entry')

    state = fields.Selection([('draft', 'Draft'), ('scheduled', 'Scheduled')], track_visibility='onchange', string='Status',required=True, readonly=True, copy=False, default='draft',
                             help='Recurring entries in draft state are inactive.')

    frequency = fields.Selection(
        [('monthly', 'Monthly'),
         ('weekly', 'Weekly'),
         ('biweekly', 'Bi-Weekly'),
         ('daily', 'Daily'),
         ('yearly', 'Yearly')
         ], string='Recurring Frequency', required=True)

    post_first_of_month = fields.Boolean("Post on first of month", help='Only usable when frequency is monthly or yearly')

    # company_id = fields.Many2one(
    #     comodel_name='res.company',
    #     string='Company'
    # )
    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Company', store=True,
                                 readonly=True,
                                 default=lambda self: self.env.user.company_id)

    create_drafts = fields.Boolean('Create Draft Entries', help='If enabled, generated journal entries will '
                                                                'be left in the Draft state, and not Posted.')

    narration = fields.Text(string='Internal Note')

    ref = fields.Char(string='Reference', store=True, copy=False, index=True)

    journal_id = fields.Many2one('account.journal', string='Journal', required=True, index=True, store=True, copy=False)

    line_ids = fields.One2many('account.move.recurring.line', 'recurring_id', string='Journal Items', copy=True, required=True)

    move_ids = fields.One2many('account.move', 'recurring_id', string='Posted Entries', copy=False, readonly=True)

    @api.multi
    @api.depends('line_ids.partner_id')
    def _compute_partner_id(self):
        for recurring_id in self:
            partner = recurring_id.line_ids.mapped('partner_id')
            recurring_id.partner_id = partner.id if len(partner) == 1 else False

    @api.multi
    def button_schedule(self):
        for recurring_id in self:
            recurring_id.write({'state': 'scheduled'})

    @api.multi
    def button_cancel(self):
        for recurring_id in self:
            recurring_id.write({'state': 'draft'})

    @api.multi
    def reschedule(self):
        for recurring_id in self:
            self.date_last = fields.Date.context_today(self)
            if recurring_id.post_first_of_month and recurring_id.frequency in ['monthly', 'yearly']:
                if recurring_id.frequency == 'monthly':
                    recurring_id.date_next = fields.Date.to_string(fields.Date.from_string(self.date_last) + relativedelta(months=+1, day=1))
                if recurring_id.frequency == 'yearly':
                    recurring_id.date_next = fields.Date.to_string(fields.Date.from_string(self.date_last) + relativedelta(years=+1, day=1))
            else:
                if recurring_id.frequency == 'monthly':
                    recurring_id.date_next = fields.Date.from_string(self.date_last) + relativedelta(months=+1)
                elif recurring_id.frequency == 'weekly':
                    recurring_id.date_next = fields.Date.from_string(self.date_last) + relativedelta(weeks=+1)
                elif recurring_id.frequency == 'biweekly':
                    recurring_id.date_next = fields.Date.from_string(self.date_last) + relativedelta(weeks=+2)
                elif recurring_id.frequency == 'yearly':
                    recurring_id.date_next = fields.Date.from_string(self.date_last) + relativedelta(years=+1)
                elif recurring_id.frequency == 'daily':
                    recurring_id.date_next = fields.Date.from_string(self.date_last) + relativedelta(days=+1)

    @api.multi
    def button_test_entry(self):
        for recurring in self:
            recurring.process_recurring_queue()

    @api.model
    def process_recurring_queue(self):
        # Find recurring entries scheduled to post today or that were missed on the last run.
        # schedulers = self.search(['|', ('date_next', '<=', datetime.strftime(fields.datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)), ('date_next', '=', False)])
        today = date.today()
        schedulers = self.search(['|', '&', ('date_next', '<=', today.strftime(DEFAULT_SERVER_DATE_FORMAT)), ('date_next', '=', False), ('state', '=', 'scheduled')])

        for schedule_id in schedulers:
            if schedule_id.date_next is not False and fields.Date.from_string(schedule_id.date_next) > today:
                continue

            # TODO: Add way to catch errors.
            if schedule_id.post():
                schedule_id.reschedule()

    @api.multi
    def post(self):
        account_move = self.env['account.move']
        # today = date.today()
        context = self._context or {}
        for recurring_id in self:
            new_move = account_move.create({
                'ref': recurring_id.ref,
                # 'date': today.strftime(DEFAULT_SERVER_DATE_FORMAT),
                'date': recurring_id.date_next,
                'journal_id': recurring_id.journal_id.id,
                'narration': recurring_id.narration,
                'recurring_id': recurring_id.id,
                'line_ids': [(0, 0, {
                    'partner_id': x.partner_id.id,
                    'account_id': x.account_id.id,
                    'name': x.name,
                    'analytic_account_id': x.analytic_account_id.id,
                    'amount_currency': x.amount_currency,
                    'currency_id': x.currency_id.id,
                    'debit': x.debit,
                    'credit': x.credit,
                }) for x in recurring_id.line_ids]
            })
            if new_move and recurring_id.create_drafts is False and context.get('test_recurring', False) is False:
                new_move.post()
            account_move |= new_move
        if account_move:
            return True
        return False

    @api.multi
    def assert_balanced(self):
        if not self.ids:
            return True
        prec = self.env['decimal.precision'].precision_get('Account')

        self._cr.execute("""\
                SELECT      recurring_id
                FROM        account_move_recurring_line
                WHERE       recurring_id in %s
                GROUP BY    recurring_id
                HAVING      abs(sum(debit) - sum(credit)) > %s
                """, (tuple(self.ids), 10 ** (-max(5, prec))))
        if len(self._cr.fetchall()) != 0:
            raise UserError(_("Cannot create unbalanced journal entry."))
        return True

    @api.multi
    def write(self, vals):
        if 'line_ids' in vals:
            res = super(AccountMoveRecurring, self.with_context(check_move_validity=False)).write(vals)
            self.assert_balanced()
        else:
            res = super(AccountMoveRecurring, self).write(vals)
        return res

    @api.model
    def create(self, vals):
        move = super(AccountMoveRecurring, self.with_context(check_move_validity=False, partner_id=vals.get('partner_id'))).create(vals)
        move.assert_balanced()
        return move


class AccountMoveRecurringLine(models.Model):
    _name = "account.move.recurring.line"

    name = fields.Char(required=True, string="Label")
    debit = fields.Monetary(default=0.0, currency_field='company_currency_id')
    credit = fields.Monetary(default=0.0, currency_field='company_currency_id')
    amount_currency = fields.Monetary(default=0.0,
                                      help="The amount expressed in an optional other currency if it is a multi-currency entry.")
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True,
                                          help='Utility field to express amount currency', store=True)

    @api.model
    def _get_currency(self):
        currency = False
        context = self._context or {}
        if context.get('default_journal_id', False):
            currency = self.env['account.journal'].browse(context['default_journal_id']).currency_id
        return currency

    currency_id = fields.Many2one('res.currency', string='Currency', default=_get_currency,
                                  help="The optional other currency if it is a multi-currency entry.")
    account_id = fields.Many2one('account.account', string='Account', required=True, index=True,
                                 ondelete="cascade")
    recurring_id = fields.Many2one('account.move.recurring', string='Recurring Journal Entry', ondelete="cascade",
                                   index=True, required=True, auto_join=True)
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='restrict')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one('res.company', related='account_id.company_id', string='Company', store=True)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True,
                                          help='Utility field to express amount currency', store=True)

