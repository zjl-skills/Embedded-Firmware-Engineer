#ifndef WIRE_H
#define WIRE_H

#include "bsp/uart_port.h"

uart_status_t wire_send_sample(uart_port_t *port, uint8_t sample);

#endif
