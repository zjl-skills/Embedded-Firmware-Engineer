#include <assert.h>
#include <stdio.h>

#include "service/heartbeat.h"

int main(void)
{
    board_io_t board = {false};
    heartbeat_t heartbeat = {UINT32_MAX - 3U, false};

    assert(!board.led);
    assert(!heartbeat_poll(&heartbeat, &board, UINT32_MAX, 4U));
    assert(heartbeat_poll(&heartbeat, &board, 0U, 4U));
    assert(board.led);
    assert(!heartbeat_poll(&heartbeat, &board, 3U, 0U));
    assert(heartbeat_poll(&heartbeat, &board, 4U, 4U));
    assert(!board.led);
    puts("PASS heartbeat: timing, wraparound, invalid period");
    return 0;
}
