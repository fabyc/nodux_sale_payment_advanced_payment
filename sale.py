# This file is part of the sale_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
#! -*- coding: utf8 -*-
from decimal import Decimal
from trytond.model import ModelView, fields, ModelSQL, Workflow
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval, Not, If, PYSONEncoder, Id
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

conversor = None
try:
    from numword import numword_es
    conversor = numword_es.NumWordES()
except:
    print("Warning: Does not possible import numword module!")
    print("Please install it...!")

__all__ = [ 'SalePaymentForm',  'WizardSalePayment']
__metaclass__ = PoolMeta
_ZERO = Decimal('0.0')
PRODUCT_TYPES = ['goods']

class SalePaymentForm():
    'Sale Payment Form'
    __name__ = 'sale.payment.form'

    anticipo = fields.Numeric('Anticipo', readonly = True)

    utilizar_anticipo = fields.Boolean('Utilizar anticipo')

    lineas_anticipo = fields.Char('Lineas de Anticipo')

    restante = fields.Numeric('Anticipo restante', readonly = True, states={
        'invisible': ~Eval('utilizar_anticipo', True)
    })

    @classmethod
    def __setup__(cls):
        super(SalePaymentForm, cls).__setup__()

    @staticmethod
    def default_restante():
        return Decimal(0.0)

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
        user = User(Transaction().user)
        sale_device = sale.sale_device or user.sale_device or False
        Date = pool.get('ir.date')
        Statement=pool.get('account.statement')

        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
        amount_a = Decimal(0.0)
        account_types = ['receivable']

        lines_credits = []

        move_lines = MoveLine.search([
            ('party', '=', sale.party),
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
            if date == Date.today():
                if amount < 0 :
                    amount *=-1
                payment_amount = amount
            else:
                payment_amount = Decimal(0.0)
                credito = True
        if sale.paid_amount:
            amount = sale.total_amount - sale.paid_amount
        else:
            amount = sale.total_amount

        if payment_amount < amount:
            to_pay = payment_amount
        elif payment_amount > amount:
            to_pay = amount

        else:
            to_pay = amount

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
        pool = Pool()
        Date = pool.get('ir.date')
        Sale = pool.get('sale.sale')
        Statement = pool.get('account.statement')
        StatementLine = pool.get('account.statement.line')
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
            self.raise_user_error('La factura supera los $200 de importe total, por cuanto no puede ser emitida a nombre de CONSUMIDOR FINAL')

        if form.credito == True and form.payment_amount == sale.total_amount:
            self.raise_user_error('No puede pagar el monto total %s en una venta a credito', form.payment_amount)

        if form.credito == False and form.payment_amount < sale.total_amount:
            self.raise_user_warning('not_credit%s' % sale.id,
                   u'Esta seguro que desea abonar $%s '
                'del valor total $%s, de la venta al CONTADO.', (form.payment_amount, sale.total_amount))

        if form.tipo_p == 'cheque':
            sale.tipo_p = form.tipo_p
            sale.banco = form.banco
            sale.numero_cuenta = form.numero_cuenta
            sale.fecha_deposito= form.fecha_deposito
            sale.titular = form.titular
            sale.numero_cheque = form.numero_cheque
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'deposito':
            sale.tipo_p = form.tipo_p
            sale.banco_deposito = form.banco_deposito
            sale.numero_cuenta_deposito = form.numero_cuenta_deposito
            sale.fecha_deposito = form.fecha_deposito
            sale.numero_deposito= form.numero_deposito
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'tarjeta':
            sale.tipo_p = form.tipo_p
            sale.numero_tarjeta = form.numero_tarjeta
            sale.lote = form.lote
            sale.tarjeta = form.tarjeta
            sale.sale_date = date
            sale.save()

        if form.tipo_p == 'efectivo':
            sale.tipo_p = form.tipo_p
            sale.recibido = form.recibido
            sale.cambio = form.cambio_cliente
            sale.sale_date = date
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
                date=Date.today(),
                amount=form.payment_amount,
                party=sale.party.id,
                account=account,
                description=sale.reference,
                sale=active_id
                )
            payment.save()

        if sale.acumulativo != True:
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
                account_types = ['receivable']

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
                if form.restante > Decimal(0.0):
                    Journal = pool.get('account.journal')
                    journal_r = Journal.search([('type', '=', 'revenue')])
                    for j in journal_r:
                        journal_sale = j.id
                    pago_en_cero = True
                    utiliza_anticipo_venta = True
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
                        'account': 326,
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
