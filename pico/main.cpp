#include <cstdio>
#include <cstdint>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "hardware/regs/pio.h"
#include "panel_wave.pio.h"
#include "wave_data.h"

static constexpr uint BASE_PIN = 2;
static constexpr uint PIN_COUNT = 12;
static constexpr uint LED_PIN = 25;
struct alignas(16) DmaBlock {
    uint32_t read_address, write_address, count, control;
};
static DmaBlock blocks[PLAN_COUNT];
static uint32_t hold_address;

int main() {
    // Match the FPGA's 320 ns half-clock exactly, without overclocking.
    set_sys_clock_khz(125000, true);
    stdio_init_all();
    bi_decl(bi_program_description("YD-RP2040 ICND1065L static FPGA-protocol port"));
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
        blocks[i] = {uint32_t(uintptr_t(startup_plan[i].samples)),
                     uint32_t(uintptr_t(&pio->txf[sm])), startup_plan[i].count,
                     channel_config_get_ctrl_value(&dc)};
    }

    // Four-word descriptors update READ_ADDR/WRITE_ADDR/COUNT/CTRL_TRIG.
    dma_channel_config cc = dma_channel_get_default_config(control);
    channel_config_set_transfer_data_size(&cc, DMA_SIZE_32);
    channel_config_set_read_increment(&cc, true);
    channel_config_set_write_increment(&cc, true);
    channel_config_set_ring(&cc, true, 4);
    channel_config_set_high_priority(&cc, true);
    dma_channel_configure(control, &cc, &dma_hw->ch[data].read_addr, blocks, 4, false);

    // The last descriptor switches to a hardware-only, unbounded scan loop.
    hold_address = uint32_t(uintptr_t(wave_hold));
    dma_channel_config lc = dma_channel_get_default_config(loop);
    channel_config_set_transfer_data_size(&lc, DMA_SIZE_32);
    channel_config_set_read_increment(&lc, false);
    channel_config_set_write_increment(&lc, false);
    channel_config_set_high_priority(&lc, true);
    dma_channel_configure(loop, &lc, &dma_hw->ch[data].al3_read_addr_trig, &hold_address, 1, false);

    dma_start_channel_mask(1u << control);
    while (!pio_sm_is_tx_fifo_full(pio, sm)) tight_loop_contents();
    pio->fdebug = 1u << (PIO_FDEBUG_TXSTALL_LSB + sm);
    pio_sm_set_enabled(pio, sm, true);
    bool led = false;
    uint32_t stalls = 0;
    while (true) {
        sleep_ms(1000);
        bool stalled = (pio->fdebug & (1u << (PIO_FDEBUG_TXSTALL_LSB + sm))) != 0;
        if (stalled) {
            ++stalls;
            pio->fdebug = 1u << (PIO_FDEBUG_TXSTALL_LSB + sm);
        }
        uint32_t errors = dma_hw->ch[data].ctrl_trig & (DMA_CH0_CTRL_TRIG_AHB_ERROR_BITS |
                           DMA_CH0_CTRL_TRIG_READ_ERROR_BITS | DMA_CH0_CTRL_TRIG_WRITE_ERROR_BITS);
        led = !led;
        gpio_put(LED_PIN, stalls || errors || led);
        printf("PICO_PANEL static clock=%lu sclk=1562500 txstall=%lu dma_error=%08lx hold=%u\n",
               (unsigned long)clock_get_hz(clk_sys),(unsigned long)stalls,(unsigned long)errors,
               ((dma_hw->ch[data].ctrl_trig & DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS) >> DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB) == unsigned(loop));
    }
}
