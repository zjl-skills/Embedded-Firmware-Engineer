#ifndef SERIAL_LINK_H
#define SERIAL_LINK_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool occupied;
    uint8_t byte;
} serial_slot_t;

typedef enum { SERIAL_OK, SERIAL_BUSY, SERIAL_INVALID } serial_status_t;

/* 忙态保持槽内原值，空对象返回参数错误。 */
serial_status_t serial_try_send(serial_slot_t *slot, uint8_t value);
/* 用 0xA5 编码采样，返回公共发送状态。 */
serial_status_t app_send_sample(serial_slot_t *slot, uint8_t sample);

#endif
