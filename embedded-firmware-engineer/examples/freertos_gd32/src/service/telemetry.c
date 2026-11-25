#include "telemetry.h"

mailbox_status_t telemetry_publish(const os_mailbox_t *mailbox, uint8_t sample)
{
    return os_mailbox_try_send(mailbox, sample);
}
