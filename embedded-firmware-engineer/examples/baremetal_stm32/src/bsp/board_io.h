#ifndef BOARD_IO_H
#define BOARD_IO_H

#include <stdbool.h>

typedef struct {
    bool led;
} board_io_t;

void board_io_write(board_io_t *board, bool asserted);

#endif
