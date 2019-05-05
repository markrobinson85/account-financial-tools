# -*- coding: utf-8 -*-
# Copyright 2019 Mark Robinson
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

{
    'name': "Account Move - Recurring Entries",
    'version': '9.0',
    'category': 'Accounting',
    'summary': "Schedule automatic journal entries",
    'author': "Odoo Community Association (OCA), Mark Robinson",
    'website': 'https://github.com/OCA/account-financial-tools',
    'license': 'AGPL-3',
    'depends': ['base', 'account', 'analytic'],
    'data': [
        'data/account_move_recurring.xml',
        'data/account_move_recurring_cron.xml',
        'security/ir.model.access.csv',
        'views/account_move.xml',
        'views/account_move_recurring.xml',
    ],
    'test': [
    ],
    'installable': True,
}
