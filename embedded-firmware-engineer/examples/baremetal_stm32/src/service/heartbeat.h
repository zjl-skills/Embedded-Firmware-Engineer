#ifndef HEARTBEAT_H
#define HEARTBEAT_H

#include <stdint.h>

#include "bsp/board_io.h"

typedef struct {
    uint32_t last_transition;
    bool asserted;
} heartbeat_t;

bool heartbeat_poll(heartbeat_t *heartbeat, board_io_t *board, uint32_t now, uint32_t interval);

#endif
