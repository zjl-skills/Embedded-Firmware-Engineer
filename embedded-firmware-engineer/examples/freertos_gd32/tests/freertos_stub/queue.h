#ifndef HOST_STUB_QUEUE_H
#define HOST_STUB_QUEUE_H

#include "FreeRTOS.h"

typedef struct test_queue *QueueHandle_t;

BaseType_t xQueueSend(QueueHandle_t queue, const void *item, TickType_t ticks_to_wait);
BaseType_t xQueueReceive(QueueHandle_t queue, void *item, TickType_t ticks_to_wait);

#endif
