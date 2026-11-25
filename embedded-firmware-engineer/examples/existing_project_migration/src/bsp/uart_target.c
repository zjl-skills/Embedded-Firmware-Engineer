#include "uart_port.h"

#include <stddef.h>

static bool target_submit(uart_port_t *port, uint8_t value)
{
    if (!port->ready) {
        return false;
    }
    port->last_byte = value;
    ++port->sent_count;
    return true;
}

uart_status_t uart_port_try_write(uart_port_t *port, uint8_t value)
{
    if (port == NULL) {
        return UART_INVALID;
    }
    return target_submit(port, value) ? UART_OK : UART_BUSY;
}
