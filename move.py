#This file is part of the nodux_account_voucher_ec module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from decimal import Decimal
from trytond.model import fields
from trytond.pool import Pool, PoolMeta

__all__ = ['Move', 'Line']
__metaclass__ = PoolMeta


class Move:
    __name__ = 'account.move'

    @classmethod
    def __setup__(cls):
        super(Move, cls).__setup__()
        cls._check_modify_exclude = ['state', 'description', 'lines']

    @classmethod
    def _get_origin(cls):
        return super(Move, cls)._get_origin() + ['sale.sale', 'sale.advanced']


class Line:
    __name__ = 'account.move.line'

    @classmethod
    def __setup__(cls):
        super(Line, cls).__setup__()
        cls._check_modify_exclude = {'reconciliation', 'debit', 'credit', 'state'}
