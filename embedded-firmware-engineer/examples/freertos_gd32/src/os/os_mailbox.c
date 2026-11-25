#include "os_mailbox.h"

#include <stddef.h>

#include "FreeRTOS.h"
#include "queue.h"

mailbox_status_t os_mailbox_try_send(const os_mailbox_t *mailbox, uint8_t item)
{
    if (mailbox == NULL || mailbox->native_handle == NULL) {
        return MAILBOX_INVALID;
    }
    /* 任务上下文采用零等待，满时由服务处理背压。 */
    return xQueueSend(mailbox->native_handle, &item, 0U) == pdPASS ? MAILBOX_OK : MAILBOX_BUSY;
}

mailbox_status_t os_mailbox_try_receive(const os_mailbox_t *mailbox, uint8_t *item)
{
    if (mailbox == NULL || mailbox->native_handle == NULL || item == NULL) {
        return MAILBOX_INVALID;
    }
    return xQueueReceive(mailbox->native_handle, item, 0U) == pdPASS ? MAILBOX_OK : MAILBOX_BUSY;
}
