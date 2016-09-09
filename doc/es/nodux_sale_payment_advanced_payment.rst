Venta
=============
Anticipo de Cliente
===============

En caso de que el cliente al que se le realiza una venta, cuente
con un anticipo, el valor aparecerá en el pago, dando al usuario vendedor
la posibilidad de utilizar el anticipo.
Se han considerado los siquientes casos:

1. El anticipo es igual al monto de la venta: al seleccionar "Utilizar anticipo"
el monto a cancelar quedará en cero, la venta quedará realizada y la factura 
pagada al término del proceso.

2. El anticipo es menor al monto de venta:  al seleccionar "Utilizar anticipo"
el monto a cancelar se calcurá automaticamente (total venta - anticipo), 
la venta quedará realizada y la factura pagada al cerrar el estado de cuenta en 
el que consta el pago.

3. El anticipo es mayor al monto de venta:  al seleccionar "Utilizar anticipo"
el monto a cancelar será cero, la venta quedará realizada y la factura pagada al 
terminar el proceso.
Se creará un nuevo anticipo con el valor del restante (anticipo - total venta)


