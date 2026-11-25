#include "wire.h"

uart_status_t wire_send_sample(uart_port_t *port, uint8_t sample)
{
    return uart_port_try_write(port, (uint8_t)(sample ^ 0xA5U));
}
