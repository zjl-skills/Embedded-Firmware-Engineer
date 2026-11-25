#ifndef TELEMETRY_H
#define TELEMETRY_H

#include "os/os_mailbox.h"

mailbox_status_t telemetry_publish(const os_mailbox_t *mailbox, uint8_t sample);

#endif
