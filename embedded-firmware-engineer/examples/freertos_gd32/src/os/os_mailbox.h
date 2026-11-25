#ifndef OS_MAILBOX_H
#define OS_MAILBOX_H

#include <stdint.h>

typedef struct {
    void *native_handle;
} os_mailbox_t;

typedef enum {
    MAILBOX_OK,
    MAILBOX_BUSY,
    MAILBOX_INVALID
} mailbox_status_t;

mailbox_status_t os_mailbox_try_send(const os_mailbox_t *mailbox, uint8_t item);
mailbox_status_t os_mailbox_try_receive(const os_mailbox_t *mailbox, uint8_t *item);

#endif
