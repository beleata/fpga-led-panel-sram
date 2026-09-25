#pragma once
#include <stdint.h>
#include <stddef.h>

namespace video {
constexpr size_t FRAME_BYTES = 6144;
constexpr size_t WAVE_SAMPLES = 32768;
constexpr uint16_t CLOCK = 1u << 9, LAT = 1u << 10, OE = 1u << 11;

inline uint16_t crc_byte(uint16_t crc, uint8_t value) {
    crc ^= uint16_t(value) << 8;
    for (unsigned i = 0; i < 8; ++i)
        crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    return crc;
}

// Six 1024-byte planes, in the same physical order as the FPGA video port.
// Preserve its brightness ceiling: 255 -> 0x0100, 0..254 unchanged.
inline void render(const uint8_t *frame, uint16_t *wave) {
    for (unsigned word = 0; word < 1024; ++word) {
        uint16_t levels[6];
        for (unsigned lane = 0; lane < 6; ++lane) {
            uint8_t level = frame[lane * 1024 + word];
            levels[lane] = level == 255 ? 256 : level;
        }
        for (unsigned bit = 0; bit < 16; ++bit) {
            unsigned clock = word * 16 + bit;
            unsigned phase = clock % 128;
            uint16_t mask = (((clock + 16) / 128) % 8) << 6;
            if (phase >= 100 && phase < 104) mask |= OE;
            if (phase == 127) mask |= LAT;
            for (unsigned lane = 0; lane < 6; ++lane)
                mask |= ((levels[lane] >> (15 - bit)) & 1u) << lane;
            wave[clock * 2] = mask;
            wave[clock * 2 + 1] = mask | CLOCK;
        }
    }
}
}
