#include <assert.h>
#include <stdbool.h>
#include <stdio.h>

#include "queue.h"
#include "service/telemetry.h"

struct test_queue {
    bool occupied;
    uint8_t item;
};

BaseType_t xQueueSend(QueueHandle_t queue, const void *item, TickType_t ticks_to_wait)
{
    assert(ticks_to_wait == 0U);
    if (queue->occupied) {
        return pdFAIL;
    }
    queue->item = *(const uint8_t *)item;
    queue->occupied = true;
    return pdPASS;
}

BaseType_t xQueueReceive(QueueHandle_t queue, void *item, TickType_t ticks_to_wait)
{
    assert(ticks_to_wait == 0U);
    if (!queue->occupied) {
        return pdFAIL;
    }
    *(uint8_t *)item = queue->item;
    queue->occupied = false;
    return pdPASS;
}

int main(void)
{
    struct test_queue queue = {false, 0U};
    os_mailbox_t mailbox = {&queue};
    uint8_t sample = 0U;

    assert(os_mailbox_try_receive(&mailbox, &sample) == MAILBOX_BUSY);
    assert(telemetry_publish(&mailbox, 77U) == MAILBOX_OK);
    assert(telemetry_publish(&mailbox, 88U) == MAILBOX_BUSY);
    assert(os_mailbox_try_receive(&mailbox, &sample) == MAILBOX_OK);
    assert(sample == 77U);
    assert(telemetry_publish(&mailbox, 88U) == MAILBOX_OK);
    assert(os_mailbox_try_receive(&mailbox, &sample) == MAILBOX_OK);
    assert(sample == 88U);
    assert(telemetry_publish(NULL, 1U) == MAILBOX_INVALID);
    puts("PASS telemetry: zero wait, backpressure, recovery");
    return 0;
}
