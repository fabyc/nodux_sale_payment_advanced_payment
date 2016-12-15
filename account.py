#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, MatchMixin, fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Configuration']
__metaclass__ = PoolMeta


class Configuration:
    'Account Configuration'
    __name__ = 'account.configuration'

    default_account_advanced = fields.Many2One('account.account', 'Default Account Advanced Payment')

    default_account_return = fields.Many2One('account.account', 'Default Account for the return of Advanced')

    default_account_e = fields.Many2One('account.account', 'Default Account Cash')

    default_account_c = fields.Many2One('account.account', 'Default Account Check')

    default_account_t = fields.Many2One('account.account', 'Default Account Transfer')

    default_account_t_c = fields.Many2One('account.account', 'Default Account Credit Card')

    default_account_d = fields.Many2One('account.account', 'Default Account Deposit')

    default_account_wf = fields.Many2One('account.account', 'Default Account Withholding F')

    default_account_wi = fields.Many2One('account.account', 'Default Account Withholding IVA')

    sequence_advanced = fields.Integer('Sequence advanced')
