#include <cstdio>
#include <cstdint>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "pico/stdio_usb.h"
#include "pico/stdio/driver.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "hardware/regs/pio.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#include "video_frame.h"
#include "panel_wave.pio.h"
#include "wave_data.h"

static constexpr uint BASE_PIN = 2;
static constexpr uint PIN_COUNT = 12;
static constexpr uint LED_PIN = 25;
struct alignas(16) DmaBlock {
    uint32_t read_address, write_address, count, control;
};
static DmaBlock blocks[PLAN_COUNT];
static DmaBlock idle_plan[1], update_plan[38];
static uint32_t next_plan;
static uint8_t frames[2][video::FRAME_BYTES];
static int data_channel;
// Only the DMA IRQ writes STARTUP -> IDLE, QUEUED -> RUNNING -> COMPLETE.
enum Phase { STARTUP, IDLE, QUEUED, RUNNING, COMPLETE };
static volatile Phase phase = STARTUP;

static void __not_in_flash_func(dma_complete)() {
    dma_channel_acknowledge_irq0(data_channel);
    if (phase == STARTUP) phase = IDLE;
    else if (phase == QUEUED) {
        next_plan = uint32_t(uintptr_t(idle_plan));
        __dmb();
        phase = RUNNING;
    } else if (phase == RUNNING) phase = COMPLETE;
}

int main() {
    // Match the FPGA's 320 ns half-clock exactly, without overclocking.
    set_sys_clock_khz(125000, true);
    stdio_init_all();
    bi_decl(bi_program_description("YD-RP2040 ICND1065L USB video RAM"));
    bi_decl(bi_1pin_with_name(11, "Panel SCLK"));
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    PIO pio = pio0;
    uint sm = pio_claim_unused_sm(pio, true);
    uint offset = pio_add_program(pio, &panel_wave_program);
    pio_sm_config config = panel_wave_program_get_default_config(offset);
    sm_config_set_out_pins(&config, BASE_PIN, PIN_COUNT);
    sm_config_set_out_shift(&config, true, true, 16);
    sm_config_set_fifo_join(&config, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&config, 1.0f);
    for (uint pin=BASE_PIN; pin<BASE_PIN+PIN_COUNT; ++pin) {
        pio_gpio_init(pio, pin);
        gpio_set_drive_strength(pin, GPIO_DRIVE_STRENGTH_4MA);
        gpio_set_slew_rate(pin, GPIO_SLEW_RATE_SLOW);
    }
    pio_sm_init(pio, sm, offset, &config);
    pio_sm_set_pins_with_mask(pio, sm, 0, ((1u<<PIN_COUNT)-1)<<BASE_PIN);
    pio_sm_set_consecutive_pindirs(pio, sm, BASE_PIN, PIN_COUNT, true);

    int data = dma_claim_unused_channel(true);
    data_channel = data;
    int control = dma_claim_unused_channel(true);
    int loop = dma_claim_unused_channel(true);
    dma_channel_config dc = dma_channel_get_default_config(data);
    channel_config_set_transfer_data_size(&dc, DMA_SIZE_16);
    channel_config_set_read_increment(&dc, true);
    channel_config_set_write_increment(&dc, false);
    channel_config_set_dreq(&dc, pio_get_dreq(pio, sm, true));
    channel_config_set_high_priority(&dc, true);
    channel_config_set_chain_to(&dc, control);
    for (size_t i=0; i<PLAN_COUNT; ++i) {
        if (i == PLAN_COUNT-1) channel_config_set_chain_to(&dc, loop);
        channel_config_set_irq_quiet(&dc, i != PLAN_COUNT-1);
        blocks[i] = {uint32_t(uintptr_t(startup_plan[i].samples)),
                     uint32_t(uintptr_t(&pio->txf[sm])), startup_plan[i].count,
                     channel_config_get_ctrl_value(&dc)};
    }

    auto descriptor = [&](const uint16_t *samples, uint32_t count, bool last, bool interrupt) {
        channel_config_set_chain_to(&dc, last ? loop : control);
        channel_config_set_irq_quiet(&dc, !interrupt);
        return DmaBlock{uint32_t(uintptr_t(samples)), uint32_t(uintptr_t(&pio->txf[sm])),
                        count, channel_config_get_ctrl_value(&dc)};
    };
    idle_plan[0] = descriptor(wave_hold, 2048, true, false);
    // Match the proven FPGA refresh: gap, init0, upload, 32768 hold clocks,
    // gap, init1, upload. The old image remains stored while USB receives.
    unsigned n = 0;
    update_plan[n++] = descriptor(wave_gap, 625, false, false);
    update_plan[n++] = descriptor(wave_init_0, 1414, false, true);
    update_plan[n++] = descriptor(wave_visible, video::WAVE_SAMPLES, false, false);
    for (unsigned i = 0; i < 32; ++i)
        update_plan[n++] = descriptor(wave_hold, 2048, false, false);
    update_plan[n++] = descriptor(wave_gap, 625, false, false);
    update_plan[n++] = descriptor(wave_init_1, 1414, false, false);
    update_plan[n++] = descriptor(wave_visible, video::WAVE_SAMPLES, true, true);
    hard_assert(n == 38);

    // Four-word descriptors update READ_ADDR/WRITE_ADDR/COUNT/CTRL_TRIG.
    dma_channel_config cc = dma_channel_get_default_config(control);
    channel_config_set_transfer_data_size(&cc, DMA_SIZE_32);
    channel_config_set_read_increment(&cc, true);
    channel_config_set_write_increment(&cc, true);
    channel_config_set_ring(&cc, true, 4);
    channel_config_set_high_priority(&cc, true);
    dma_channel_configure(control, &cc, &dma_hw->ch[data].read_addr, blocks, 4, false);

    // The hardware loop selects a complete descriptor plan at a scan boundary.
    next_plan = uint32_t(uintptr_t(idle_plan));
    dma_channel_config lc = dma_channel_get_default_config(loop);
    channel_config_set_transfer_data_size(&lc, DMA_SIZE_32);
    channel_config_set_read_increment(&lc, false);
    channel_config_set_write_increment(&lc, false);
    channel_config_set_high_priority(&lc, true);
    dma_channel_configure(loop, &lc, &dma_hw->ch[control].al3_read_addr_trig, &next_plan, 1, false);
    irq_set_exclusive_handler(DMA_IRQ_0, dma_complete);
    dma_channel_set_irq0_enabled(data, true);
    irq_set_enabled(DMA_IRQ_0, true);

    dma_start_channel_mask(1u << control);
    while (!pio_sm_is_tx_fifo_full(pio, sm)) tight_loop_contents();
    pio->fdebug = 1u << (PIO_FDEBUG_TXSTALL_LSB + sm);
    pio_sm_set_enabled(pio, sm, true);
    uint32_t stalls = 0, errors = 0, committed = 0;
    unsigned front = 0, rx_state = 0, position = 0;
    uint8_t command = 0, sequence = 0;
    uint16_t crc = 0xffff, received_crc = 0;
    uint64_t last_byte = 0;
    char usb_bytes[256];
    int usb_count = 0, usb_offset = 0;
    auto reply = [&](const char *status) {
        printf("PICO_VIDEO %s seq=%u crc=%04x frames=%lu txstall=%lu dma_error=%08lx\n",
               status, sequence, crc, (unsigned long)committed,
               (unsigned long)stalls, (unsigned long)errors);
    };
    while (true) {
        bool stalled = (pio->fdebug & (1u << (PIO_FDEBUG_TXSTALL_LSB + sm))) != 0;
        if (stalled) {
            ++stalls;
            pio->fdebug = 1u << (PIO_FDEBUG_TXSTALL_LSB + sm);
        }
        errors |= dma_hw->ch[data].ctrl_trig & (DMA_CH0_CTRL_TRIG_AHB_ERROR_BITS |
                           DMA_CH0_CTRL_TRIG_READ_ERROR_BITS | DMA_CH0_CTRL_TRIG_WRITE_ERROR_BITS);
        gpio_put(LED_PIN, stalls || errors || ((time_us_64() / 500000) & 1));
        if (phase == COMPLETE) {
            // Completion is DMA-to-FIFO; allow the final queued GPIO samples out.
            sleep_us(10);
            front ^= 1;
            ++committed;
            phase = IDLE;
            reply("ACK");
        }
        if (phase != IDLE) { tight_loop_contents(); continue; }
        if (rx_state && time_us_64() - last_byte > 1000000) {
            rx_state = 0;
            reply("TIMEOUT");
        }
        if (usb_offset == usb_count) {
            usb_count = stdio_usb.in_chars(usb_bytes, sizeof(usb_bytes));
            usb_offset = 0;
            if (usb_count <= 0) { usb_count = 0; tight_loop_contents(); continue; }
        }
        uint8_t value = uint8_t(usb_bytes[usb_offset++]);
        last_byte = time_us_64();
        switch (rx_state) {
        case 0: if (value == 'P') rx_state = 1; break;
        case 1: rx_state = value == 'V' ? 2 : (value == 'P' ? 1 : 0); break;
        case 2:
            command = value;
            crc = video::crc_byte(0xffff, value);
            rx_state = (command == 1 || command == 2) ? 3 : 0;
            break;
        case 3:
            sequence = value;
            crc = video::crc_byte(crc, value);
            position = 0;
            rx_state = command == 1 ? 4 : 5;
            break;
        case 4:
            frames[front ^ 1][position++] = value;
            crc = video::crc_byte(crc, value);
            if (position == video::FRAME_BYTES) rx_state = 5;
            break;
        case 5: received_crc = uint16_t(value) << 8; rx_state = 6; break;
        case 6:
            received_crc |= value;
            rx_state = 0;
            if (received_crc != crc) reply("CRC_ERROR");
            else if (command == 2) reply("STATUS");
            else {
                // No DMA reader uses wave_visible while the idle plan scans.
                video::render(frames[front ^ 1], wave_visible);
                phase = QUEUED;
                __dmb();
                next_plan = uint32_t(uintptr_t(update_plan));
            }
            break;
        }
    }
}
