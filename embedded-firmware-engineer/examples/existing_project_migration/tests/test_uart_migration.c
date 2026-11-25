#include <assert.h>
#include <stdio.h>

#include "service/wire.h"

int main(void)
{
    uart_port_t port = {false, 0U, 0U};

    assert(wire_send_sample(&port, 0x31U) == UART_BUSY);
    assert(port.sent_count == 0U);
    port.ready = true;
    assert(wire_send_sample(&port, 0x31U) == UART_OK);
    assert(port.sent_count == 1U);
    assert(port.last_byte == 0x94U);
    assert(wire_send_sample(NULL, 0U) == UART_INVALID);
    puts("PASS migration: busy, encoded byte, retry, invalid handle");
    return 0;
}
