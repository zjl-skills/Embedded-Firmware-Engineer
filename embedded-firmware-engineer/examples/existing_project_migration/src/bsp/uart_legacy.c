#include "uart_port.h"

#include <stddef.h>

static int legacy_submit(uart_port_t *port, uint8_t value)
{
    if (!port->ready) {
        return 1;
    }
    port->last_byte = value;
    ++port->sent_count;
    return 0;
}

uart_status_t uart_port_try_write(uart_port_t *port, uint8_t value)
{
    if (port == NULL) {
        return UART_INVALID;
    }
    /* 旧替身约定返回 0 表示提交成功。 */
    return legacy_submit(port, value) == 0 ? UART_OK : UART_BUSY;
}
