#include "board_io.h"

void board_io_write(board_io_t *board, bool asserted)
{
    board->led = asserted;
}
