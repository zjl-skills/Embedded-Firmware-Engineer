#include "serial_link.h"

#include <stdio.h>
#include <stdlib.h>

#define CHECK(condition)                                                \
    do {                                                                \
        if (!(condition)) {                                             \
            fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); \
            return false;                                               \
        }                                                               \
    } while (0)

static bool test_serial_try_send(void)
{
    serial_slot_t slot = {.occupied = false, .byte = 0x7E};

    CHECK(serial_try_send(&slot, 0x00) == SERIAL_OK);
    CHECK(slot.occupied && slot.byte == 0x00);

    CHECK(serial_try_send(&slot, 0xFF) == SERIAL_BUSY);
    CHECK(slot.occupied && slot.byte == 0x00);

    slot.occupied = false;
    CHECK(serial_try_send(&slot, 0xFF) == SERIAL_OK);
    CHECK(slot.occupied && slot.byte == 0xFF);

    CHECK(serial_try_send(NULL, 0x31) == SERIAL_INVALID);
    return true;
}

static bool test_app_send_sample(void)
{
    serial_slot_t slot = {.occupied = false, .byte = 0x00};

    CHECK(app_send_sample(&slot, 0x31) == SERIAL_OK);
    CHECK(slot.occupied && slot.byte == 0x94);

    CHECK(app_send_sample(&slot, 0x5A) == SERIAL_BUSY);
    CHECK(slot.occupied && slot.byte == 0x94);

    slot.occupied = false;
    CHECK(app_send_sample(&slot, 0x5A) == SERIAL_OK);
    CHECK(slot.occupied && slot.byte == 0xFF);

    CHECK(app_send_sample(NULL, 0x31) == SERIAL_INVALID);
    return true;
}

int main(void)
{
    if (!test_serial_try_send() || !test_app_send_sample()) {
        return EXIT_FAILURE;
    }

    puts("PASS serial collaboration");
    return EXIT_SUCCESS;
}
