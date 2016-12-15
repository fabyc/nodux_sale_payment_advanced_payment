# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .sale import *
from .move import *
from .account import *

def register():
    Pool.register(
        ListAdvanced,
        Advanced,
        SalePaymentForm,
        Move,
        Line,
        Configuration,
        module='nodux_sale_payment_advanced_payment', type_='model')
    Pool.register(
        WizardSalePayment,
        module='nodux_sale_payment_advanced_payment', type_='wizard')
    Pool.register(
        AdvancedReport,
        ListAdvancedReport,
        module='nodux_sale_payment_advanced_payment', type_='report')
