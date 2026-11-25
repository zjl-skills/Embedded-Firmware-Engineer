#ifndef UART_PORT_H
#define UART_PORT_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool ready;
    uint8_t last_byte;
    unsigned int sent_count;
} uart_port_t;

typedef enum {
    UART_OK,
    UART_BUSY,
    UART_INVALID
} uart_status_t;

uart_status_t uart_port_try_write(uart_port_t *port, uint8_t value);

#endif
