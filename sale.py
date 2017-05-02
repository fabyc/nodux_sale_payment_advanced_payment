#! -*- coding: utf8 -*-
# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from decimal import Decimal
from trytond.model import ModelView, fields, ModelSQL, Workflow
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, Not, If, PYSONEncoder, Id, In
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button, StateAction
from trytond import backend
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from itertools import groupby, chain
from functools import partial
from trytond.report import Report
from trytond.transaction import Transaction
import os
import pytz
import time

conversor = None
try:
    from numword import numword_es
    conversor = numword_es.NumWordES()
except:
    print("Warning: Does not possible import numword module!")
    print("Please install it...!")

__all__ = ['ListAdvanced', 'Advanced', 'SalePaymentForm',  'WizardSalePayment',
 'AdvancedReport', 'ListAdvancedReport']
__metaclass__ = PoolMeta

_ZERO = Decimal('0.0')
PRODUCT_TYPES = ['goods']
_STATES = {
    'readonly': In(Eval('state'), ['posted']),
}

_PAY = [
    ('efectivo','Efectivo'),
    ('cheque', 'Cheque'),
    ('transferencia', u'Transferencia Electrónica'),
    ('tarjeta', u'Tarjeta de Crédito'),
    ('deposito', u'Depósito'),
    ('fuente', u'Retención en la Fuente'),
    ('iva', u'Retención del IVA')
]

class ListAdvanced(ModelSQL, ModelView):
    "List Advanced"
    __name__ = "sale.list_advanced"
    party = fields.Many2One('party.party', 'Party', states={
                'required': ~Eval('active', True),
                'readonly': In(Eval('state'), ['posted']),
            })
    lines = fields.One2Many('sale.advanced', 'advanced', 'Lines')
    advanced_inicial = fields.Numeric('Valor Anticipo', digits=(16, 2), states=_STATES)
    advanced_utilizado = fields.Function(fields.Numeric('Utilizado', digits=(16, 2), states=_STATES), 'get_utilizado')
    advanced_balance = fields.Function(fields.Numeric('Balance', digits=(16, 2), states=_STATES), 'get_balance')
    state = fields.Selection([
        ('posted', 'Posted'),
        ], 'State', select=True, readonly=True)

    @classmethod
    def __setup__(cls):
        super(ListAdvanced, cls).__setup__()

    @staticmethod
    def default_state():
        return 'posted'

    @staticmethod
    def default_advanced_inicial():
        return Decimal(0.0)

    @staticmethod
    def default_advanced_utilizado():
        return Decimal(0.0)

    @staticmethod
    def default_advanced_balance():
        return Decimal(0.0)

    @classmethod
    def get_utilizado(cls, advanceds, names):
        result = {n: {a.id: Decimal(0) for a in advanceds} for n in names}
        amount = Decimal(0.0)
        for name in names:
            for advanced in advanceds:
                amount = Decimal(0.0)
                for line in advanced.lines:
                    if line.utilizado:
                        amount += line.utilizado
                if amount:
                    result[name][advanced.id] = amount
                else:
                    result[name][advanced.id] = Decimal(0.0)
        return result

    @classmethod
    def get_balance(cls, advanceds, names):
        result = {n: {a.id: Decimal(0) for a in advanceds} for n in names}
        amount = Decimal(0.0)
        for name in names:
            for advanced in advanceds:
                amount = Decimal(0.0)
                for line in advanced.lines:
                    if line.balance:
                        amount += line.balance
                if amount:
                    result[name][advanced.id] = amount
                else:
                    result[name][advanced.id] = Decimal(0.0)
        return result

class ListAdvancedReport(Report):
    __name__ = 'sale.list_advanced_report'

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        User = pool.get('res.user')

        advanced = records[0]
        user = User(Transaction().user)

        if user.company.timezone:
            timezone = pytz.timezone(user.company.timezone)
            dt = datetime.now()
            hora = datetime.astimezone(dt.replace(tzinfo=pytz.utc), timezone)


        localcontext['user'] = user
        localcontext['company'] = user.company
        localcontext['hora'] = hora.strftime('%H:%M:%S')
        localcontext['fecha_im'] = hora.strftime('%d/%m/%Y')

        return super(ListAdvancedReport, cls).parse(report, records, data,
                localcontext=localcontext)

class Advanced(ModelSQL, ModelView):
    'Advanced'
    __name__ = 'sale.advanced'
    _rec_name = 'number'

    advanced = fields.Many2One('sale.list_advanced', 'List Advanced')
    number = fields.Char('Number', readonly=True, help="Advanced Number")
    party = fields.Many2One('party.party', 'Party', states=_STATES, required=True)
    date = fields.Date('Date', required=True, states=_STATES)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        states=_STATES)
    currency = fields.Many2One('currency.currency', 'Currency', states=_STATES)
    company = fields.Many2One('company.company', 'Company', states=_STATES)
    comment = fields.Char('Comment', states=_STATES)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ], 'State', select=True, readonly=True)
    employee = fields.Many2One('company.employee', 'Salesman',
        domain=[
            ('company', '=', Eval('company', -1)),
            ],
        states=_STATES,
        depends=['state', 'company'])

    amount = fields.Numeric('Payment', digits=(16, 2), states=_STATES)
    utilizado = fields.Numeric('Utilizado', digits=(16, 2), states=_STATES)
    balance = fields.Numeric('Balance', digits=(16, 2), states=_STATES)

    pay =  fields.Selection(_PAY, "Tipo", states=_STATES)

    reference = fields.Char('Reference', states={
        'invisible': Eval('pay') == 'efectivo',
    })

    bank = fields.Many2One('bank', 'Bank', states={
        'invisible': Eval('pay') == 'efectivo',
    })

    vencimiento = fields.Date('Date Out', states={
        'invisible': Eval('pay') == 'efectivo',
    })

    account = fields.Char('Account', states={
        'invisible': Eval('pay') == 'efectivo',
    })

    move = fields.Many2One('account.move', 'Move')

    @classmethod
    def __setup__(cls):
        super(Advanced, cls).__setup__()

        cls._buttons.update({
                'post': {
                    'invisible': Eval('state') != 'draft',
                    },
                })

        cls._order.insert(0, ('date', 'ASC'))
        #cls._order.insert(1, ('number', 'DESC'))

    @staticmethod
    def default_employee():
        User = Pool().get('res.user')

        if Transaction().context.get('employee'):
            return Transaction().context['employee']
        else:
            user = User(Transaction().user)
            if user.employee:
                return user.employee.id

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_pay():
        return 'efectivo'

    @staticmethod
    def default_amount():
        return Decimal(0.0)

    @staticmethod
    def default_utilizado():
        return Decimal(0.0)

    @staticmethod
    def default_balance():
        return Decimal(0.0)

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        company_id = Transaction().context.get('company')
        if company_id:
            return Company(company_id).currency.id

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_journal():
        pool = Pool()
        Journal = pool.get('account.journal')
        journal_r = Journal.search([('type', '=', 'revenue')])
        for j in journal_r:
            return j.id

    @staticmethod
    def default_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_vencimiento():
        Date = Pool().get('ir.date')
        return Date.today()

    def set_number(self):
        pool = Pool()
        Configuration = pool.get('account.configuration')
        sequence_advanced = None
        if Configuration(1).sequence_advanced:
                sequence_advanced = Configuration(1).sequence_advanced

        if sequence_advanced:
            if len(str(sequence_advanced)) == 1:
                number = '00000000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 2:
                number = '0000000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 3:
                number = '000000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 4:
                number = '00000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 5:
                number = '0000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 6:
                number = '000'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 7:
                number = '00'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 8:
                number = '0'+str(sequence_advanced)
            elif len(str(sequence_advanced)) == 9:
                number = +str(sequence_advanced)
            configuration = Configuration(1)
            configuration.sequence_advanced = sequence_advanced + 1
            configuration.save()
        else:
            number = '000000001'
            configuration = Configuration(1)
            configuration.sequence_advanced = 2
            configuration.save()

        vals = {'number': number}
        self.write([self], vals)

    def get_amount2words(self, value):
            if conversor:
                return (conversor.cardinal(int(value))).upper()
            else:
                return ''

    def prepare_move_lines(self):

        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        ListAdvanced = pool.get('sale.list_advanced')
        original = Decimal(0.0)
        unreconcilied = Decimal(0.0)
        paid_amount = Decimal(0.0)

        residual_amount = Decimal(0.0)
        name = None
        invoice_d = None
        listadvanced = ListAdvanced()

        if not self.amount > Decimal("0.0"):
            self.raise_user_error('No ha ingresado el monto del Anticipo')

        all_list_advanced = ListAdvanced.search([('party', '=', self.party)])

        if all_list_advanced:
            for list_advanced in all_list_advanced:
                listadvanced = list_advanced
        else:
            listadvanced.party = self.party
            listadvanced.save()

        listadvanced.advanced_inicial = listadvanced.advanced_inicial  + self.amount
        #listadvanced.advanced_balance = listadvanced.advanced_balance + self.amount
        listadvanced.save()

        self.advanced = listadvanced
        self.balance = self.amount
        self.save()

        Configuration = pool.get('account.configuration')

        if Configuration(1).default_account_advanced:
            account_advanced = Configuration(1).default_account_advanced
        else:
            self.raise_user_error('No ha configurado la cuenta por defecto para anticipos.'
            '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        if self.pay == "efectivo":
            if Configuration(1).default_account_e:
                account_pay = Configuration(1).default_account_e
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para efectivo.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "cheque":
            if Configuration(1).default_account_c:
                account_pay = Configuration(1).default_account_c
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para cheque.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "transferencia":
            if  Configuration(1).default_account_t:
                account_pay = Configuration(1).default_account_t
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para transferencia.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "tarjeta":
            if  Configuration(1).default_account_t_c:
                account_pay = Configuration(1).default_account_t_c
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para transferencia.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "deposito":
            if  Configuration(1).default_account_d:
                account_pay = Configuration(1).default_account_d
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para deposito.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "fuente":
            if  Configuration(1).default_account_wf:
                account_pay = Configuration(1).default_account_wf
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para retencion en la fuente.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        elif self.pay == "iva":
            if  Configuration(1).default_account_wi:
                account_pay = Configuration(1).default_account_wi
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para retencion de IVA.'
                '\nDirijase a Financiero-Configuracion-Configuracion Contable')

        move_lines_new = []
        move, = Move.create([{
            'period': Period.find(self.company.id, date=self.date),
            'journal': self.journal,
            'date': self.date,
            'origin': str(self),
        }])

        move_lines_new.append({
            'description': "",
            'debit': self.amount,
            'credit': Decimal(0.0),
            'account': account_pay.id,
            'move': move.id,
            'journal': self.journal,
            'period': Period.find(self.company.id, date=self.date),
        })
        move_lines_new.append({
            'description': "",
            'debit': Decimal(0.0),
            'credit': self.amount,
            'account': account_advanced.id,
            'party' : self.party.id,
            'move': move.id,
            'journal': self.journal,
            'period': Period.find(self.company.id, date=self.date),
        })
        created_lines = MoveLine.create(move_lines_new)
        Move.post([move])

        self.move = move
        self.save()

    @classmethod
    @ModelView.button
    def post(cls, advanceds):
        for advanced in advanceds:
            advanced.prepare_move_lines()
            advanced.set_number()
        cls.write(advanceds, {'state': 'posted'})

class AdvancedReport(Report):
    __name__ = 'sale.advanced_report'

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        User = pool.get('res.user')
        advanced = records[0]
        fecha = advanced.date
        company = advanced.company
        if company.timezone:
            timezone = pytz.timezone(company.timezone)
            dt = datetime.now()
            hora = datetime.astimezone(dt.replace(tzinfo=pytz.utc), timezone)

        d = str(advanced.amount)
        if '.' in d:
            decimales = d[-2:]
            if decimales[0] == '.':
                 decimales = decimales[1]+'0'
        else:
            decimales = '00'

        if advanced.amount and conversor:
            amount_to_pay_words = advanced.get_amount2words(advanced.amount)


        user = User(Transaction().user)
        localcontext['user'] = user
        localcontext['company'] = user.company
        localcontext['fecha'] = fecha.strftime('%d/%m/%Y')
        localcontext['hora'] = hora.strftime('%H:%M:%S')
        localcontext['fecha_im'] = hora.strftime('%d/%m/%Y')
        localcontext['amount_to_pay_words'] = amount_to_pay_words
        localcontext['decimales'] = decimales

        return super(AdvancedReport, cls).parse(report, records, data,
                localcontext=localcontext)

class SalePaymentForm():
    'Sale Payment Form'
    __name__ = 'sale.payment.form'

    anticipo = fields.Numeric('Anticipo', readonly = True)

    utilizar_anticipo = fields.Boolean('Utilizar anticipo')

    lineas_anticipo = fields.Char('Lineas de Anticipo')

    restante = fields.Numeric('Anticipo restante', readonly = True, states={
        'invisible': ~Eval('utilizar_anticipo', True)
    })

    devolver_restante = fields.Boolean('Devolver valor restante', help="Devolver valor restante en efectivo")

    @classmethod
    def __setup__(cls):
        super(SalePaymentForm, cls).__setup__()

    @staticmethod
    def default_restante():
        return Decimal(0.0)

    @staticmethod
    def default_devolver_restante():
        return False

    @fields.depends('payment_amount', 'anticipo', 'utilizar_anticipo', 'restante')
    def on_change_utilizar_anticipo(self):
        result = {}
        a_pagar = Decimal(0.0)
        restante = Decimal(0.0)
        if self.anticipo and self.payment_amount:
            if self.anticipo > Decimal(0.0) and self.utilizar_anticipo == True:
                if self.anticipo <= self.payment_amount:
                    a_pagar = (self.payment_amount - self.anticipo)
                else:
                    a_pagar = Decimal(0.0)
                    restante = (self.anticipo - self.payment_amount)
                result['payment_amount'] = a_pagar
                result['restante'] = restante

            if self.utilizar_anticipo == False:
                result['payment_amount'] = self.payment_amount
        return result

class WizardSalePayment(Wizard):
    'Wizard Sale Payment'
    __name__ = 'sale.payment'
    print_ = StateAction('nodux_sale_payment.report_invoice_pos')

    @classmethod
    def __setup__(cls):
        super(WizardSalePayment, cls).__setup__()
        cls._error_messages.update({
                'not_tipo_p': ('No ha configurado el tipo de pago. \n-Seleccione el estado de cuenta en "Todos los estados de cuenta" \n-Seleccione forma de pago.'),
                })

    def default_start(self, fields):
        pool = Pool()
        Sale = pool.get('sale.sale')
        User = pool.get('res.user')
        SaleP = pool.get('sale.payment.form')
        sale = Sale(Transaction().context['active_id'])
        if not(sale.sale_date):
            self.raise_user_error('Ingrese fecha de venta')
        user = User(Transaction().user)
        sale_device = sale.sale_device or user.sale_device or False
        Date = pool.get('ir.date')
        Statement=pool.get('account.statement')

        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
        amount_a = Decimal(0.0)
        account_types = ['receivable', 'payable']

        lines_credits = []

        move_lines = MoveLine.search([
            ('party', '=', sale.party),
            ('description', '=', ""),
            ('account.kind', 'in', account_types),
            ('state', '=', 'valid'),
            ('reconciliation', '=', None),
            ('maturity_date', '=', None),
        ])
        for line in move_lines:
            invoice = InvoiceAccountMoveLine.search([
                ('line', '=', line.id),
            ])
            if invoice:
                continue
            if line.credit:
                if 'sale.advanced' in str(line.move.origin):
                    line_type = 'cr'
                    amount_a = amount_a + line.credit
                    lines_credits.append(str(line.id) +',')

        ModelData = pool.get('ir.model.data')
        User = pool.get('res.user')
        Group = pool.get('res.group')
        origin = str(sale)
        def in_group():

            group = Group(ModelData.get_id('nodux_sale_payment',
                    'group_stock_force'))
            transaction = Transaction()
            user_id = transaction.user
            if user_id == 0:
                user_id = transaction.context.get('user', user_id)
            if user_id == 0:
                return True
            user = User(user_id)
            return origin and group in user.groups

        if sale_device.journal:
            statement = Statement.search([('journal', '=', sale_device.journal.id), ('state', '=', 'draft')], order=[('date', 'DESC')])
        else:
            self.raise_user_error('No se ha definido un libro diario por defecto para %s', sale_device.name)

        if statement :
            for s in statement:
                tipo_p = s.tipo_pago
            if tipo_p :
                pass
            else:
                self.raise_user_error('not_tipo_p')
        else:
             self.raise_user_error('No ha creado un estado de cuenta para %s ', sale_device.name)

        if not sale.check_enough_stock():
            return

        Product = Pool().get('product.product')


        if sale.acumulativo == True:
            pass
        else:
            if sale.lines:
                # get all products
                products = []
                locations = [sale.warehouse.id]
                for line in sale.lines:
                    if not line.product or line.product.type not in PRODUCT_TYPES:
                        continue
                    if line.product not in products:
                        products.append(line.product)
                # get quantity
                with Transaction().set_context(locations=locations):
                    quantities = Product.get_quantity(
                        products,
                        sale.get_enough_stock_qty(),
                        )

                # check enough stock
                for line in sale.lines:
                    if line.product.type not in PRODUCT_TYPES:
                        continue
                    elif sale.total_amount < Decimal(0.0):
                        continue
                    else:
                        if line.product and line.product.id in quantities:
                            qty = quantities[line.product.id]
                        if qty < line.quantity:
                            if not in_group():
                                self.raise_user_error('No hay suficiente stock del producto: \n %s \n en la bodega %s', (line.product.name, sale.warehouse.name))

                            line.raise_user_warning('not_enough_stock_%s' % line.id,
                                   'No hay suficiente stock del producto: "%s"'
                                'en la bodega "%s", para realizar esta venta.', (line.product.name, sale.warehouse.name))
                            # update quantities
                            quantities[line.product.id] = qty - line.quantity

        if user.id != 0 and not sale_device:
            self.raise_user_error('not_sale_device')

        term_lines = sale.payment_term.compute(sale.total_amount, sale.company.currency,
            sale.sale_date)
        total = sale.total_amount
        if not term_lines:
            term_lines = [(Date.today(), total)]
        credito = False
        if sale.paid_amount:
            payment_amount = sale.total_amount - sale.paid_amount
        else:
            payment_amount = sale.total_amount

        if term_lines > 1:
            credito == True
        for date, amount in term_lines:
            #Se cambia menor o igual para PRUEBAS TONERS, y Date.today por sale_date
            #if date = Date.today()
            if sale.sale_date:
                if date <= sale.sale_date:
                    if amount < 0 :
                        amount *=-1
                    payment_amount = amount
                else:
                    payment_amount = Decimal(0.0)
                    credito = True
            else:
                self.raise_user_error('Ingrese la fecha de venta')
        if sale.paid_amount:
            amount = sale.total_amount - sale.paid_amount
        else:
            amount = sale.total_amount

        if sale.total_amount > Decimal(0.0):
            if payment_amount < amount:
                to_pay = payment_amount
            elif payment_amount > amount:
                to_pay = amount
            else:
                to_pay= amount
        else:
            to_pay = Decimal(0.0)
            sales = Sale.search([('description', '=', sale.description)])
            for sale in sales:
                if sale.total_amount > Decimal(0.0):
                    if sale.paid_amount:
                        if sale.paid_amount > Decimal(0.0) and sale.state != "done":
                            to_pay = sale.paid_amount * (-1)
                    else:
                        if sale.state == "done":
                            to_pay = sale.total_amount * (-1)
        return {
            'journal': sale_device.journal.id
                if sale_device.journal else None,
            'journals': [j.id for j in sale_device.journals],
            'payment_amount': to_pay,
            'currency_digits': sale.currency_digits,
            'party': sale.party.id,
            'tipo_p':tipo_p,
            'anticipo' : amount_a,
            'lineas_anticipo' : str(lines_credits),
            'credito' : credito,
            'amount': total
            }

    def transition_pay_(self):
        print "Ingresa aqui advanced"
        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')
        Sale = pool.get('sale.sale')
        Statement = pool.get('account.statement')
        StatementLine = pool.get('account.statement.line')
        move_lines = []
        line_move_ids = []
        form = self.start
        statements = Statement.search([
                ('journal', '=', form.journal),
                ('state', '=', 'draft'),
                ], order=[('date', 'DESC')])
        if not statements:
            self.raise_user_error('not_draft_statement', (form.journal.name,))

        active_id = Transaction().context.get('active_id', False)
        sale = Sale(active_id)
        if sale.self_pick_up == False:
            sale.create_shipment('out')
            sale.set_shipment_state()
        date = Pool().get('ir.date')
        date = date.today()
        if form.payment_amount == 0 and form.party.vat_number == '9999999999999':
            self.raise_user_error('No se puede dar credito a consumidor final, monto a pagar no puede ser %s', form.payment_amount)

        if sale.total_amount > 200 and form.party.vat_number == '9999999999999':
            self.raise_user_error('La factura supera los $200 de importe total, no puede ser emitida a nombre de CONSUMIDOR FINAL')

        if form.credito == True and form.payment_amount == sale.total_amount:
            self.raise_user_error('No puede pagar el monto total %s en una venta a credito', form.payment_amount)

        if form.credito == False and form.payment_amount < sale.total_amount:
            self.raise_user_warning('not_credit%s' % sale.id,
                   u'Esta seguro que desea abonar $%s '
                'del valor total $%s, de la venta al CONTADO.', (form.payment_amount, sale.total_amount))

        if form.restante > Decimal(0.0) and form.devolver_restante == True:
            self.raise_user_warning('devolucion%s' % sale.id,
                   u'Esta seguro que desea devolver $%s '
                'en efectivo.', (form.restante))

        if form.restante > Decimal(0.0) and form.devolver_restante == False:
            self.raise_user_warning('anticipo%s' % sale.id,
                   u'Esta seguro que desea dejar $%s '
                'como anticipo del Cliente %s.', (form.restante, sale.party.name))

        if form.tipo_p == 'cheque':
            sale.tipo_p = form.tipo_p
            sale.bancos = form.bancos
            sale.numero_cuenta = form.numero_cuenta
            sale.fecha_deposito= form.fecha_deposito
            sale.titular = form.titular
            sale.numero_cheque = form.numero_cheque
            move, = Move.create([{
                'period': Period.find(sale.company.id, date=sale.sale_date),
                'journal': 1,
                'date': sale.sale_date,
                'origin': str(sale),
                'description': str(sale.id),
            }])

            postdated_lines = None
            Configuration = pool.get('account.configuration')
            if Configuration(1).default_account_check:
                account_check = Configuration(1).default_account_check
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para Cheques. \nDirijase a Financiero-Configuracion-Configuracion Contable')

            move_lines.append({
                'description' : str(sale.id),
                'debit': form.payment_amount,
                'credit': Decimal(0.0),
                'account': account_check,
                'move': move.id,
                'journal': 1,
                'period': Period.find(sale.company.id, date=sale.sale_date),
            })
            move_lines.append({
                'description': str(sale.id),
                'debit': Decimal(0.0),
                'credit': form.payment_amount,
                'account': sale.party.account_receivable.id,
                'move': move.id,
                'journal': 1,
                'period': Period.find(sale.company.id, date=sale.sale_date),
                'date': sale.sale_date,
                'party': sale.party.id,
            })

            postdated_lines = []
            if form.bancos:
                pass
            else:
                self.raise_user_error('Ingrese el banco')

            if form.numero_cheque:
                pass
            else:
                self.raise_user_error('Ingrese el numero de cheque')

            if form.numero_cuenta:
                pass
            else:
                self.raise_user_error('Ingrese el numero de cuenta')

            postdated_lines.append({
                'reference': str(sale.id),
                'name': str(sale.id),
                'amount': Decimal(form.payment_amount),
                'account': account_check,
                'date_expire': sale.sale_date,
                'date': sale.sale_date,
                'num_check' : form.numero_cheque,
                'num_account' : form.numero_cuenta,
            })

            if postdated_lines != None:
                Postdated = pool.get('account.postdated')
                postdated = Postdated()
                for line in postdated_lines:
                    date = line['date']
                    postdated.postdated_type = 'check'
                    postdated.reference = str(sale.id)
                    postdated.party = sale.party
                    postdated.post_check_type = 'receipt'
                    postdated.journal = 1
                    postdated.lines = postdated_lines
                    postdated.state = 'draft'
                    postdated.date = sale.sale_date
                    postdated.save()
            #sale.sale_date = date
            sale.save()

        if form.tipo_p == 'deposito':
            sale.tipo_p = form.tipo_p
            sale.banco_deposito = form.banco_deposito
            sale.numero_cuenta_deposito = form.numero_cuenta_deposito
            sale.fecha_deposito = form.fecha_deposito
            sale.numero_deposito= form.numero_deposito
            #sale.sale_date = date
            sale.save()

        if form.tipo_p == 'tarjeta':
            sale.tipo_p = form.tipo_p
            sale.numero_tarjeta = form.numero_tarjeta
            sale.lote = form.lote
            sale.tarjeta = form.tarjeta
            #sale.sale_date = date

            move, = Move.create([{
                'period': Period.find(sale.company.id, date=sale.sale_date),
                'journal': 1,
                'date': sale.sale_date,
                'origin': str(sale),
                'description': str(sale.id),
            }])
            Configuration = pool.get('account.configuration')
            if Configuration(1).default_account_card:
                account_card = Configuration(1).default_account_card
            else:
                self.raise_user_error('No ha configurado la cuenta por defecto para Tarjetas. \nDirijase a Financiero-Configuracion-Configuracion Contable')

            move_lines.append({
                'description' : str(sale.id),
                'debit': form.payment_amount,
                'credit': Decimal(0.0),
                'account': account_card,
                'move': move.id,
                'journal': 1,
                'period': Period.find(sale.company.id, date=sale.sale_date),
            })
            move_lines.append({
                'description': str(sale.id),
                'debit': Decimal(0.0),
                'credit': form.payment_amount,
                'account': sale.party.account_receivable.id,
                'move': move.id,
                'journal': 1,
                'period': Period.find(sale.company.id, date=sale.sale_date),
                'date': sale.sale_date,
                'party': sale.party.id,
            })
            postdated_lines = []
            if form.numero_tarjeta:
                pass
            else:
                self.raise_user_error('Ingrese el numero de Tarjeta')

            if form.tarjeta:
                pass
            else:
                self.raise_user_error('Ingrese la Tarjeta')

            if form.lote:
                pass
            else:
                self.raise_user_error('Ingrese el no. de lote de la tarjeta')

            postdated_lines.append({
                'reference': str(sale.id),
                'name': str(sale.id),
                'amount': Decimal(form.payment_amount),
                'account': account_card,
                'date_expire': sale.sale_date,
                'date': sale.sale_date,
                'num_check' : form.numero_tarjeta,
                'num_account' : form.lote,
            })

            if postdated_lines != None:
                Postdated = pool.get('account.postdated')
                postdated = Postdated()
                for line in postdated_lines:
                    date = line['date']
                    postdated.postdated_type = 'card'
                    postdated.reference = str(sale.id)
                    postdated.party = sale.party
                    postdated.post_check_type = 'receipt'
                    postdated.journal = 1
                    postdated.lines = postdated_lines
                    postdated.state = 'draft'
                    postdated.date = sale.sale_date
                    postdated.save()
            sale.save()

        if form.tipo_p == 'efectivo':
            sale.tipo_p = form.tipo_p
            sale.recibido = form.recibido
            sale.cambio = form.cambio_cliente
            #sale.sale_date = date
            sale.save()

        if not sale.reference:
            Sale.set_reference([sale])

        account = (sale.party.account_receivable
            and sale.party.account_receivable.id
            or self.raise_user_error('party_without_account_receivable',
                error_args=(sale.party.name,)))

        if form.payment_amount:
            payment = StatementLine(
                statement=statements[0].id,
                #date=Date.today(),
                date=sale.sale_date,
                amount=form.payment_amount,
                party=sale.party.id,
                account=account,
                description=sale.reference,
                sale=active_id
                )
            payment.save()

        if sale.acumulativo != True:
            if sale.total_amount < Decimal(0.0):
                move_lines_dev= []
                line_move__dev_ids = []
                reconcile_lines_dev_advanced = []

                journal_r = Journal.search([('type', '=', 'revenue')])
                for j in journal_r:
                    journal_sale = j.id

                move_dev, = Move.create([{
                    'period': Period.find(sale.company.id, date=sale.sale_date),
                    'journal': journal_sale,
                    'date': sale.sale_date,
                    'origin': str(sale),
                    'description': 'ajustes '+ str(sale.description),
                }])

                move_lines_dev.append({
                    'description': 'ajustes '+ str(sale.description),
                    'debit': Decimal(0.0),
                    'credit': sale.total_amount * (-1),
                    'account': sale.party.account_receivable.id,
                    'move': move_dev.id,
                    'party': sale.party.id,
                    'journal': journal_sale,
                    'period': Period.find(sale.company.id, date=sale.sale_date),
                })

                move_lines_dev.append({
                    'description':  'ajustes '+ str(sale.description),
                    'debit': sale.total_amount * (-1),
                    'credit': Decimal(0.0),
                    'account': sale.party.account_receivable.id,
                    'move': move_dev.id,
                    'party': sale.party.id,
                    'journal': journal_sale,
                    'period': Period.find(sale.company.id, date=sale.sale_date),
                })

                created_lines_dev = MoveLine.create(move_lines_dev)
                Move.post([move_dev])

                sale.devolucion = True
                sales_d = Sale.search([('description', '=', sale.description)])
                for sale_d in sales_d:
                    sale_d.devolucion = True
                    sale_d.referencia_de_factura = sale.description
                    sale_d.save()

            pago_en_cero = False
            utiliza_anticipo_venta = False
            sale.formas_pago_sri = form.tipo_pago_sri
            sale.save()
            Sale.workflow_to_end([sale])
            Invoice = Pool().get('account.invoice')
            invoices = Invoice.search([('description','=',sale.reference)])
            lote = False
            modules = None
            Module = pool.get('ir.module.module')
            modules = Module.search([('name', '=', 'nodux_sale_payment_advanced_payment'), ('state', '=', 'installed')])

            if modules:
                move_invoice = None
                for i in invoices:
                    move_invoice = i.move
                    invoice_advanced = i
                #agregado para asientos de anticipos
                Period = pool.get('account.period')
                Move = pool.get('account.move')
                Invoice = pool.get('account.invoice')
                MoveLine = pool.get('account.move.line')
                InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
                amount_a = Decimal(0.0)
                account_types = ['receivable', 'payable']
                """
                move_lines = MoveLine.search([
                    ('party', '=', sale.party),
                    ('account.kind', 'in', account_types),
                    ('state', '=', 'valid'),
                    ('reconciliation', '=', None),
                    ('maturity_date', '=', None),
                ])

                for line in move_lines:
                    lineas_anticipo_conciliar = (form.lineas_anticipo.replace("[", "").replace("]","").replace("'", "").replace("'", "")).split(",")
                    for l in lineas_anticipo_conciliar:
                        if str(line.id) == l:
                            description = sale.reference
                            new_advanced = form.anticipo-form.restante
                            line.credit = Decimal(new_advanced)
                            line.save()
                            move = line.move
                            move.description = description
                            for m in move.lines:
                                if m.debit > Decimal(0.0):
                                    m.debit = Decimal(new_advanced)
                                    m.save()
                            move.save()
                """

                Configuration = pool.get('account.configuration')

                if form.utilizar_anticipo == True:

                    utiliza_anticipo_venta = True
                    if Configuration(1).default_account_return:
                        account_advanced = Configuration(1).default_account_advanced

                    pool = Pool()
                    ListAdvanced = pool.get('sale.list_advanced')
                    all_list_advanced = ListAdvanced.search([('party', '=', sale.party)])
                    move_lines_new_advanced = []
                    if form.restante == Decimal(0.0):
                        pagar = form.anticipo
                        if all_list_advanced:
                            for list_advanced in all_list_advanced:
                                for line in list_advanced.lines:
                                    if line.amount != line.utilizado:
                                        if pagar > line.balance and line.balance > Decimal(0.0) and pagar > Decimal(0.0):
                                            monto_balance = line.balance
                                            line.utilizado = line.utilizado + monto_balance
                                            line.balance = line.balance - monto_balance
                                            line.save()
                                            pagar = pagar - monto_balance
                                            for linem in line.move.lines:
                                                if linem.party and linem.credit > Decimal(0.0) and linem.reconciliation == None and linem.description == "":
                                                    linem.description = "used"+str(sale.reference)
                                                    linem.save()
                                            move = line.move
                                            move.description = sale.reference
                                            move.save()

                                        elif pagar < line.balance and line.balance > Decimal(0.0) and pagar > Decimal(0.0):
                                            monto_balance = pagar
                                            line.utilizado = line.utilizado + monto_balance
                                            line.balance = line.balance - monto_balance
                                            line.save()
                                            pagar = pagar - monto_balance

                                            for linem in move.lines:
                                                if linem.party and linem.credit > Decimal(0.0) and linem.reconciliation == None and linem.description == "":
                                                    linem.credit = linem.credit - monto_balance
                                                    linem.save()
                                            move = line.move
                                            move.description = sale.reference
                                            move.save()

                                            move_lines_new_advanced.append({
                                                'description': "used"+str(sale.reference),
                                                'debit': Decimal(0.0),
                                                'credit': monto_balance,
                                                'account': account_advanced.id,
                                                'party' : sale.party.id,
                                                'move': line.move.id,
                                                'journal': line.move.journal.id,
                                                'period': Period.find(sale.company.id, date=sale.sale_date),
                                            })
                                            created_lines = MoveLine.create(move_lines_new_advanced)
                                            Move.post([line.move])

                                        elif pagar == line.balance and line.balance > Decimal(0.0) and pagar > Decimal(0.0):
                                            monto_balance = line.balance
                                            line.utilizado = line.utilizado + monto_balance
                                            line.balance = line.balance - monto_balance
                                            line.save()
                                            pagar = pagar - monto_balance
                                            for linem in line.move.lines:
                                                if linem.party and linem.credit > Decimal(0.0) and linem.reconciliation == None and linem.description == "":
                                                    linem.description = "used"+str(sale.reference)
                                                    linem.save()
                                            move = line.move
                                            move.description = sale.reference
                                            move.save()

                    if form.restante > Decimal(0.0) and form.devolver_restante == False:
                        pago_en_cero = True
                        restante = form.restante
                        pagar = form.anticipo - form.restante
                        if all_list_advanced:
                            for list_advanced in all_list_advanced:
                                for line in list_advanced.lines:
                                    if line.amount != line.utilizado:
                                        if pagar > line.balance and line.balance > Decimal(0.0) and pagar > Decimal(0.0):
                                            monto_balance = line.balance
                                            line.utilizado = line.utilizado + monto_balance
                                            line.balance = line.balance - monto_balance
                                            line.save()
                                            pagar = pagar - monto_balance
                                            for linem in line.move.lines:
                                                if linem.party and linem.credit > Decimal(0.0) and linem.reconciliation == None and linem.description == "":
                                                    linem.description = "used"+str(sale.reference)
                                                    linem.save()
                                            move = line.move
                                            move.description = sale.reference
                                            move.save()

                                        elif pagar < line.balance and line.balance > Decimal(0.0) and pagar > Decimal(0.0):
                                            monto_balance = pagar
                                            line.utilizado = line.utilizado + monto_balance
                                            line.balance = line.balance - monto_balance
                                            line.save()
                                            pagar = pagar - monto_balance

                                            for linem in line.move.lines:
                                                if linem.party and linem.credit > Decimal(0.0) and linem.reconciliation == None and linem.description == "":
                                                    linem.credit = linem.credit - monto_balance
                                                    linem.save()

                                            move_lines_new_advanced.append({
                                                'description': "used"+str(sale.reference),
                                                'debit': Decimal(0.0),
                                                'credit': monto_balance,
                                                'account': account_advanced.id,
                                                'party' : sale.party.id,
                                                'move': line.move.id,
                                                'journal': line.move.journal.id,
                                                'period': Period.find(sale.company.id, date=sale.sale_date),
                                            })
                                            created_lines = MoveLine.create(move_lines_new_advanced)
                                            Move.post([line.move])
                                            move = line.move
                                            move.description = sale.reference
                                            move.save()


                    if form.restante > Decimal(0.0) and form.devolver_restante == True:
                        if Configuration(1).default_account_return:
                            account_return = Configuration(1).default_account_return
                        else:
                            self.raise_user_error('No ha configurado la cuenta para devolucion de anticipos.'
                            '\nDirijase a Financiero-Configuracion-Configuracion Contable')

                        Journal = pool.get('account.journal')
                        journal_r = Journal.search([('type', '=', 'revenue')])
                        for j in journal_r:
                            journal_sale = j.id
                        pago_en_cero = True
                        #crear_nuevo_asiento
                        move_lines_new = []
                        line_move_ids = []
                        reconcile_lines_advanced = []
                        move, = Move.create([{
                            'period': Period.find(sale.company.id, date=sale.sale_date),
                            'journal': journal_sale,
                            'date': sale.sale_date,
                            'origin': str(sale),
                        }])
                        move_lines_new.append({
                            'description': invoice_advanced.number,
                            'debit': Decimal(0.0),
                            'credit': form.restante,
                            'account': invoice_advanced.party.account_receivable.id,
                            'move': move.id,
                            'party': sale.party.id,
                            'journal': journal_sale,
                            'period': Period.find(sale.company.id, date=sale.sale_date),
                        })
                        move_lines_new.append({
                            'description': invoice_advanced.number,
                            'debit': form.restante,
                            'credit': Decimal(0.0),
                            'account': account_return.id,
                            'move': move.id,
                            'journal': journal_sale,
                            'period': Period.find(sale.company.id, date=sale.sale_date),
                        })
                        created_lines = MoveLine.create(move_lines_new)
                        Move.post([move])


            if sale.shop.lote != None:
                lote = sale.shop.lote

            if invoices:
                for i in invoices:
                    invoice = i
                invoice.formas_pago_sri = form.tipo_pago_sri
                invoice.save()
                if sale.comment:
                    invoice.comment = sale.comment
                    invoice.save()

            if sale.fisic_invoice == True :
                invoice.number = sale.number_invoice
                invoice.fisic_invoice = True
                invoice.save()
            else:
                if lote == False:
                    invoice.get_invoice_element()
                    invoice.get_tax_element()
                    invoice.generate_xml_invoice()
                    invoice.get_detail_element()
                    invoice.action_generate_invoice()
                    invoice.connect_db()

            sale.description = sale.reference
            sale.save()
            if (pago_en_cero == True and utiliza_anticipo_venta == True) | (form.utilizar_anticipo == True and form.restante == Decimal(0.0)):
                Line = pool.get('account.move.line')
                account = sale.party.account_receivable
                lines = []
                amount = Decimal('0.0')
                for invoice in sale.invoices:
                    for line in invoice.lines_to_pay:
                        if not line.reconciliation:
                            lines.append(line)
                            amount += line.debit - line.credit
                moves = Move.search([('description', '=', sale.reference)])
                for move in moves:
                    if not move:
                        continue
                    for line in move.lines:
                        if (not line.reconciliation and
                                line.account.id == account.id):
                            lines.append(line)
                            amount += line.debit - line.credit
                if lines and amount == Decimal('0.0'):
                    Line.reconcile(lines)

            if sale.total_amount == sale.paid_amount:
                #return 'print_'
                return 'end'

            if sale.total_amount != sale.paid_amount:
                #return 'print_'
                return 'end'

            if sale.state != 'draft':
                #return 'print_'
                return 'end'
        else:
            if sale.total_amount != sale.paid_amount:
                return 'end'
            if (sale.total_amount == sale.paid_amount) | (sale.state != draft):
                Invoice = Pool().get('account.invoice')
                invoices = Invoice.search([('description','=',sale.reference)])
                for i in invoices:
                    invoice= i
                invoice.get_invoice_element()
                invoice.get_tax_element()
                invoice.generate_xml_invoice()
                invoice.get_detail_element()
                invoice.action_generate_invoice()
                invoice.connect_db()
                sale.description = sale.reference
                sale.save()
                return 'end'

        return 'end'
