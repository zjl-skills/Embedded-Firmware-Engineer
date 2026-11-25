#include "heartbeat.h"

bool heartbeat_poll(heartbeat_t *heartbeat, board_io_t *board, uint32_t now, uint32_t interval)
{
    /* 在计数周期内用无符号差值处理回绕。 */
    if (interval == 0U || (uint32_t)(now - heartbeat->last_transition) < interval) {
        return false;
    }
    heartbeat->last_transition = now;
    heartbeat->asserted = !heartbeat->asserted;
    board_io_write(board, heartbeat->asserted);
    return true;
}
