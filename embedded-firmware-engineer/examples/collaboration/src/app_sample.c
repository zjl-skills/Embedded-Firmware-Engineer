#include "serial_link.h"

serial_status_t app_send_sample(serial_slot_t *slot, uint8_t sample)
{
    return serial_try_send(slot, (uint8_t)(sample ^ 0xA5u));
}
