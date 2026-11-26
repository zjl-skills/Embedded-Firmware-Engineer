#include "serial_link.h"

#include <stddef.h>

serial_status_t serial_try_send(serial_slot_t *slot, uint8_t value)
{
    if (slot == NULL) {
        return SERIAL_INVALID;
    }

    if (slot->occupied) {
        return SERIAL_BUSY;
    }

    slot->byte = value;
    slot->occupied = true;
    return SERIAL_OK;
}
