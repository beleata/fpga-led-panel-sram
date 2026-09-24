/*
 * iceprog2 - iCE40 SPI-flash programmer for the OLIMEXINO-32U4 (ATmega32u4).
 *
 * Replaces Olimex's iceprog.ino, whose frame parser is off by one:
 *   readSerialFrame() returns whatever readBytesUntil() managed to collect and
 *   decodeFrame() then does rxframe[0] = rxframe[1], so a minimal <CMD><FCS>FEND
 *   frame puts the checksum in the command slot, the checksum never balances and
 *   the board answers nothing at all. Diagnostics confirmed the USB CDC link and
 *   the sketch itself were fine - only the parsing was broken.
 *
 * This sketch parses framing byte by byte, so it does not care how the host
 * chunks its writes. It talks to the W25Q16 directly over SPI instead of going
 * through the SPIFlash library - fewer moving parts, and the whole flash
 * protocol fits in a page of code.
 *
 * Wire format, both directions:
 *   FEND CMD <escaped data...> FCS FEND
 *   FCS chosen so (CMD + data + FCS) & 0xFF == 0xFF
 *   FEND/FESC inside data escaped as FESC TFEND / FESC TFESC
 *
 * Commands (same opcodes as the Olimex tool, but a full 3-byte flash address):
 *   0xEE ENTER     -> READY          hold CRESET low so the FPGA becomes an SPI
 *                                    pass-through to the flash; CDONE must read 0
 *   0xEF EXIT      -> READY          release CRESET, FPGA boots from flash
 *   0x9F READ_ID   -> READ_ID mfr mem cap
 *   0xC7 BULK_ERASE-> READY 0xC7
 *   0xD8 SEC_ERASE a_hi a_mid a_lo                  -> READY 0xC7
 *   0x02 PROG      a_hi a_mid a_lo <up to 256 bytes> -> READY 0xC7
 *   0x03 READ      a_hi a_mid a_lo  -> READ page_hi page_lo <256 bytes>
 *
 * The flash is NOT wired to PGM1 directly: PGM1 pin 7/8/9/10 are the FPGA's SPI
 * pins, and the configuration logic only forwards them to the flash while the
 * FPGA is held in reset (CRESET low). Talking to the flash with CRESET high
 * yields FF FF FF for every byte.
 *
 * Host side: ../../../iceprog.py
 */

#include <SPI.h>

#define CS      13              // flash chip select on the PGM1 / UEXT bus
#define CDONE    3
#define RESET    2

#define FEND  0xC0
#define FESC  0xDB
#define TFEND 0xDC
#define TFESC 0xDD

#define C_READ_ID    0x9F
#define C_BULK_ERASE 0xC7
#define C_SEC_ERASE  0xD8
#define C_PROG       0x02
#define C_READ       0x03
#define C_ENTER      0xEE
#define C_EXIT       0xEF
#define C_PING       0xF0
#define C_DRIVE      0xF1
#define C_LISTEN     0xF2
#define C_SAMPLE     0xF3
#define C_SPI        0xF4
#define C_BITBANG    0xF5
#define C_UARTRX     0xF6
#define C_STATUS     0xF7
#define C_UART1      0xF8
#define C_SEND1      0xF9
#define C_PARK       0xFA
#define C_BLINK2     0xFB
#define C_PINS       0xFC
#define C_WATCH      0xFD
#define C_UARTCFG    0xE0
#define C_UARTXFER   0xE1

#define R_READY    0x44
#define R_READ     0x03
#define R_READ_ID  0x9F
#define R_ERROR    0x45
#define R_PONG     0xF0
#define R_UART     0xF2
#define R_SAMPLE   0xF3
#define R_SPI      0xF4
#define R_BITBANG  0xF5
#define R_UARTRX   0xF6
#define R_STATUS   0xF7
#define R_UART1    0xF8

// ---- software UART receiver on MISO / D14 (PB3 = ACO) -----------------------
//
// The FPGA transmits on PGM1 pin 8, which is the same wire the ATmega calls MISO.
// The hardware USART cannot be pointed at PB3 (its RX pin is PD2) and Timer3
// belongs to the USB stack, so Timer1 provides the sampling clock.
//
// The link is slow on purpose: 15 cm of unshielded IDC ribbon between two boards,
// with no ground between the signal wires. SPI at 2 MHz and even hand-bitbanging
// came back corrupted; 9600 baud (104 us per bit) is what the cable tolerates.
// The link is slow on purpose: 15 cm of unshielded IDC ribbon between two boards,
// with no ground between the signal wires. SPI at 2 MHz and even hand-bitbanging
// came back corrupted; 9600 baud (104 us per bit) is what the cable tolerates.
//
// One sample per bit, right in the middle. The ISR must stay tiny: Timer1 fires
// every 104 us and the USB stack needs its share of the CPU. An earlier attempt
// used 457 kHz for 3x oversampling and wedged the board completely.
//
//   bit period = 1667 clocks at 16 MHz, so OCR1A = 1666
#define UART_TICKS_PER_BIT 1667
#define UART_RX_MAX 96

static volatile uint8_t  urx_buf[UART_RX_MAX];
static volatile uint8_t  urx_len = 0;
static volatile uint8_t  urx_bit = 0;       // 0 = hunting for a start bit
static volatile uint8_t  urx_shift = 0;
static volatile bool     urx_active = false;
static volatile bool     urx_done = false;

ISR(TIMER1_COMPA_vect) {
  if (!urx_active) return;

  if (urx_bit == 0) {
    // idle: a low level is a start bit
    if ((PINB & _BV(PB3)) == 0) {
      urx_bit = 1;
      urx_shift = 0;
    }
    return;
  }

  if (urx_bit <= 8) {
    if (PINB & _BV(PB3)) urx_shift |= _BV(urx_bit - 1);   // LSB first
    urx_bit++;
    return;
  }

  // the stop bit ends the byte
  if (urx_len < UART_RX_MAX) urx_buf[urx_len++] = urx_shift;
  urx_bit = 0;
  if (urx_len >= UART_RX_MAX) { urx_active = false; urx_done = true; }
}

#define PAGE_SIZE 256

static uint8_t rxbuf[PAGE_SIZE + 8];
static uint8_t txbuf[2 * (PAGE_SIZE + 8)];
static uint16_t txlen;

// ---------------------------------------------------------------- SPI helpers

static inline void csLow()  { digitalWrite(CS, LOW); }
static inline void csHigh() { digitalWrite(CS, HIGH); }

static uint8_t spiXfer(uint8_t b) { return SPI.transfer(b); }

static void flashPowerUp() {
  csLow();
  spiXfer(0xAB);            // release power-down / read device ID
  spiXfer(0x00); spiXfer(0x00); spiXfer(0x00);
  csHigh();
  delayMicroseconds(50);
}

static uint8_t flashStatus() {
  csLow();
  spiXfer(0x05);            // read status register 1
  uint8_t s = spiXfer(0x00);
  csHigh();
  return s;
}

static void flashWaitReady() {
  uint32_t guard = 0;
  while ((flashStatus() & 0x01) && guard++ < 6000000UL) { }
}

static void flashWriteEnable() {
  csLow();
  spiXfer(0x06);
  csHigh();
}

static uint32_t flashJedecId() {
  csLow();
  spiXfer(0x9F);
  uint32_t id = (uint32_t)spiXfer(0x00) << 16;
  id |= (uint32_t)spiXfer(0x00) << 8;
  id |= (uint32_t)spiXfer(0x00);
  csHigh();
  return id;
}

static void flashBulkErase() {
  flashWriteEnable();
  csLow();
  spiXfer(0xC7);
  csHigh();
  flashWaitReady();
}

static void flashSectorErase(uint32_t addr) {
  flashWriteEnable();
  csLow();
  spiXfer(0x20);            // 4 kB sector erase
  spiXfer((addr >> 16) & 0xFF);
  spiXfer((addr >> 8) & 0xFF);
  spiXfer(addr & 0xFF);
  csHigh();
  flashWaitReady();
}

static void flashPageProgram(uint32_t addr, const uint8_t *data, uint16_t len) {
  flashWriteEnable();
  csLow();
  spiXfer(0x02);
  spiXfer((addr >> 16) & 0xFF);
  spiXfer((addr >> 8) & 0xFF);
  spiXfer(addr & 0xFF);
  for (uint16_t i = 0; i < len; i++) spiXfer(data[i]);
  csHigh();
  flashWaitReady();
}

static void flashRead(uint32_t addr, uint8_t *out, uint16_t len) {
  csLow();
  spiXfer(0x03);
  spiXfer((addr >> 16) & 0xFF);
  spiXfer((addr >> 8) & 0xFF);
  spiXfer(addr & 0xFF);
  for (uint16_t i = 0; i < len; i++) out[i] = spiXfer(0x00);
  csHigh();
}

// -------------------------------------------------------------- frame sending

static void txReset(uint8_t cmd) {
  txbuf[0] = FEND;
  txbuf[1] = cmd;
  txlen = 2;
}

static void txByte(uint8_t b) {
  if (b == FEND) {
    txbuf[txlen++] = FESC;
    txbuf[txlen++] = TFEND;
  } else if (b == FESC) {
    txbuf[txlen++] = FESC;
    txbuf[txlen++] = TFESC;
  } else {
    txbuf[txlen++] = b;
  }
}

static void txSend(uint8_t fcs) {
  txByte((uint8_t)(0xFF - fcs));
  txbuf[txlen++] = FEND;
  Serial.write(txbuf, txlen);
}

static void sendReady() {
  txReset(R_READY);
  txSend(R_READY);
}

static void sendError() {
  txReset(R_ERROR);
  txSend(R_ERROR);
}

static void sendId(uint32_t id) {
  txReset(R_READ_ID);
  uint8_t s = R_READ_ID;
  txByte((id >> 16) & 0xFF); s += (id >> 16) & 0xFF;
  txByte((id >> 8) & 0xFF);  s += (id >> 8) & 0xFF;
  txByte(id & 0xFF);         s += id & 0xFF;
  txSend(s);
}

// ------------------------------------------------------------- frame receiving

// Parser state is kept across calls: a 260-byte PROG frame does not arrive in one
// go over USB CDC, and the stock sketch's "start from scratch every time" approach
// lost everything that had already been read.
static uint16_t rxlen;
static bool rxInFrame;
static bool rxEscaped;

// Consumes whatever is in the serial buffer. When a complete, checksum-valid frame
// has been assembled it lands in rxbuf (rxbuf[0] = command) and true is returned.
static bool pollFrame() {
  while (Serial.available()) {
    uint8_t b = Serial.read();

    if (b == FEND) {
      if (rxInFrame && rxlen > 1) {
        uint8_t sum = 0;
        for (uint16_t i = 0; i < rxlen; i++) sum += rxbuf[i];
        if (sum == 0xFF) {
          rxlen--;                 // drop the checksum byte, keep cmd+data
          rxInFrame = false;       // next FEND starts a fresh frame
          return true;
        }
      }
      rxlen = 0;
      rxInFrame = true;
      rxEscaped = false;
      continue;
    }

    if (!rxInFrame) continue;      // wait for the opening FEND

    if (b == FESC) { rxEscaped = true; continue; }
    if (rxEscaped) {
      b = (b == TFEND) ? FEND : (b == TFESC) ? FESC : b;
      rxEscaped = false;
    }
    if (rxlen < sizeof(rxbuf)) rxbuf[rxlen++] = b;
  }
  return false;
}

// ---------------------------------------------------------------------- setup

void setup() {
  pinMode(CDONE, INPUT);
  pinMode(RESET, OUTPUT);
  pinMode(CS, OUTPUT);
  csHigh();

  Serial.begin(230400);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 4000) { }

  SPI.begin();
  SPI.setClockDivider(SPI_CLOCK_DIV2);   // 8 MHz
  SPI.setDataMode(SPI_MODE0);

  // D1 is the console transmit line towards the FPGA. Park it as an output at the
  // idle level from the very start: left as an input it floats, and a floating wire
  // into the FPGA yields nothing but noise - which showed up as both status LEDs
  // blinking slowly for no reason.
  pinMode(1, OUTPUT);
  digitalWrite(1, HIGH);

  // Leave the FPGA alone: it boots from flash on its own. The host opens the SPI
  // pass-through with ENTER when it actually wants to talk to the flash.
  csHigh();
  digitalWrite(RESET, HIGH);
  delay(50);
}

// ---- console line watcher ---------------------------------------------------
// Samples D0 and D1 every 2 ms and records every change, so a test run that lasts
// as long as the operator likes can be read back in slices without missing
// anything. The host polls it and timestamps each batch as it arrives.
#define WATCH_MAX 512
static uint8_t  watch_buf[WATCH_MAX];
static uint16_t watch_len = 0;
static bool     watch_on = false;
static uint8_t  watch_last = 0xFF;
static unsigned long watch_last_ms = 0;

static void watch_poll() {
  if (!watch_on) return;
  unsigned long now = millis();
  if (now - watch_last_ms < 2) return;
  watch_last_ms = now;

  uint8_t now_levels = (uint8_t)((PIND >> 2) & 0x03);   // bit0 = D0, bit1 = D1
  if (now_levels != watch_last) {
    watch_last = now_levels;
    if (watch_len < WATCH_MAX) watch_buf[watch_len++] = now_levels;
  }
}

// ----------------------------------------------------------------------- loop

// Bring up the hardware USART on D0 (receive) and D1 (transmit) once, and leave it
// running. Both console commands share this: two independent bring-ups meant the
// second one reset the direction that was already working.
static bool uart1_up = false;
static void uart1_ensure() {
  if (uart1_up && (UCSR1B & _BV(RXEN1)) && (UCSR1B & _BV(TXEN1))) return;
  SPI.end();
  pinMode(SCK, INPUT);
  pinMode(MOSI, INPUT);
  pinMode(MISO, INPUT);
  pinMode(0, INPUT);          // D0 = PD2 = RXD1
  digitalWrite(0, LOW);       // no pull-up on the receive line
  Serial1.begin(4800);
  uart1_up = true;
  delay(10);
}

void loop() {
  watch_poll();       // record any change on D0/D1 while a test is running

  if (!pollFrame()) { delayMicroseconds(200); return; }

  uint16_t n = rxlen;
  uint8_t cmd = rxbuf[0];

  switch (cmd) {
    case C_UARTCFG: {
      if (n != 5) { sendError(); break; }
      uint32_t baud = ((uint32_t)rxbuf[1] << 24) | ((uint32_t)rxbuf[2] << 16)
                    | ((uint32_t)rxbuf[3] << 8) | rxbuf[4];
      if (baud < 1200 || baud > 2000000UL) { sendError(); break; }
      watch_on = false;
      Serial1.end();
      pinMode(0, INPUT); digitalWrite(0, LOW);
      pinMode(1, OUTPUT); digitalWrite(1, LOW);
      delay(20);  // Break rearms the FPGA auto-baud receiver.
      digitalWrite(1, HIGH); delay(2);
      Serial1.begin(baud); uart1_up = true;
      Serial1.write(0x55); Serial1.flush(); delay(25);
      while (Serial1.available()) Serial1.read();
      txReset(C_UARTCFG);
      uint8_t hi = UBRR1H, lo = UBRR1L, fast = (UCSR1A & _BV(U2X1)) ? 1 : 0;
      txByte(hi); txByte(lo); txByte(fast);
      txSend((uint8_t)(C_UARTCFG + hi + lo + fast));
      break;
    }

    case C_UARTXFER: {
      // Keep the complete echo below Arduino's 64-byte RX ring capacity.
      uint8_t count = n > 1 ? n - 1 : 0;
      if (!uart1_up || count == 0 || count > 48) { sendError(); break; }
      while (Serial1.available()) Serial1.read();
      Serial1.write(rxbuf + 1, count);
      Serial1.flush();
      uint8_t got[48], used = 0;
      unsigned long start = millis();
      while (used < count && millis() - start < 250) {
        if (Serial1.available()) got[used++] = Serial1.read();
      }
      txReset(C_UARTXFER);
      uint8_t fcs = C_UARTXFER + used;
      txByte(used);
      for (uint8_t i = 0; i < used; ++i) { txByte(got[i]); fcs += got[i]; }
      txSend(fcs);
      break;
    }

    case C_PING:
      txReset(R_PONG);
      txSend(R_PONG);
      break;

    case C_DRIVE: {
      // Hardware probe support: drive the PGM1 lines and let an FPGA design
      // observe them. Payload: seconds(1) then a sequence of
      //   line(1) value(1) ms(1)
      // Lines: 0 = SCK (D15), 1 = MOSI/SDI (D16). SS_B (D13) is left alone:
      // it doubles as the flash chip select and is only safe to move while the
      // flash is idle.
      if (n < 2) { sendError(); break; }

      uint8_t seconds = rxbuf[1];
      uint16_t idx = 2;
      while (idx + 2 < n) {
        uint8_t line = rxbuf[idx];
        uint8_t val = rxbuf[idx + 1] ? HIGH : LOW;
        uint8_t ms = rxbuf[idx + 2];
        idx += 3;

        uint8_t pin = (line == 0) ? SCK : MOSI;
        pinMode(pin, OUTPUT);
        digitalWrite(pin, val);
        delay(ms);
      }

      // leave the lines low and hand them back to the SPI peripheral
      pinMode(SCK, OUTPUT);  digitalWrite(SCK, LOW);
      pinMode(MOSI, OUTPUT); digitalWrite(MOSI, LOW);
      SPI.begin();
      delay((uint16_t)seconds * 1000);
      sendReady();
      break;
    }

    case C_SAMPLE: {
      // Sample the MISO line (PB3) repeatedly and report the levels, so a line
      // that is stuck can be told apart from one that is actually toggling.
      // Payload: count(1) delay_ms(1) line(1)  - line 0 = MISO/D14, 1 = MOSI/D16
      uint8_t count = (n >= 2) ? rxbuf[1] : 16;
      uint8_t delay_ms = (n >= 3) ? rxbuf[2] : 100;
      uint8_t line = (n >= 4) ? rxbuf[3] : 0;
      if (count == 0) count = 16;
      if (count > 32) count = 32;

      SPI.end();
      pinMode(SCK, INPUT);
      pinMode(MOSI, INPUT);
      pinMode(MISO, INPUT);
      pinMode(CS, INPUT);               // D13 = PB7, wired to PGM1 pin 10
      digitalWrite(MISO, LOW);
      digitalWrite(MOSI, LOW);
      digitalWrite(CS, LOW);

      uint8_t buf[32];
      uint8_t levels = 0;
      for (uint8_t i = 0; i < count; i++) {
        uint8_t v;
        // line selects which wire to look at:
        //   0 = D14 (PB3), the host's MISO   -> PGM1 pin 8 (FPGA pin 45)
        //   1 = D16 (PB2), the host's MOSI   -> PGM1 pin 7 (FPGA pin 46)
        //   2 = D13 (PB7), the flash CS      -> PGM1 pin 10 (FPGA pin 49)
        //   3 = D15 (PB1), the host's SCK    -> PGM1 pin 9 (FPGA pin 48)
        //   4 = D1  (PD3), the console TX    -> GPIO1 pin 14 (FPGA pin 37)
        if      (line == 0) v = (PINB & _BV(PB3)) ? 1 : 0;
        else if (line == 1) v = (PINB & _BV(PB2)) ? 1 : 0;
        else if (line == 2) v = (PINB & _BV(PB7)) ? 1 : 0;
        else if (line == 3) v = (PINB & _BV(PB1)) ? 1 : 0;
        else                v = (PIND & _BV(PD3)) ? 1 : 0;
        buf[i] = v;
        if (v) levels |= _BV(i % 8);
        // delay_ms == 0 means "as fast as possible", which is what catching a
        // 9600 baud frame (104 us per bit) needs
        if (delay_ms) delay(delay_ms);
        else delayMicroseconds(20);
      }

      txReset(R_SAMPLE);
      uint8_t fcs = R_SAMPLE;
      txByte(count); fcs += count;
      txByte(levels); fcs += levels;
      for (uint8_t i = 0; i < count; i++) { txByte(buf[i]); fcs += buf[i]; }
      txSend(fcs);

      SPI.begin();
      break;
    }

    case C_STATUS: {
      // Report the strap pins so a silent line can be told apart from a silent
      // FPGA: CDONE high means the bitstream was accepted and the design is
      // running, so whatever it drives is its own business.
      uint8_t cdone = digitalRead(CDONE) ? 1 : 0;
      uint8_t reset = digitalRead(RESET) ? 1 : 0;
      uint8_t miso  = (PINB & _BV(PB3)) ? 1 : 0;
      txReset(R_STATUS);
      uint8_t fcs = R_STATUS;
      txByte(cdone); fcs += cdone;
      txByte(reset); fcs += reset;
      txByte(miso);  fcs += miso;
      txSend(fcs);
      break;
    }

    case C_SEND1: {
      // Send bytes out of the hardware USART on D1 (PD3 = TXD1) towards the FPGA.
      // Payload: the bytes to send. Receiver is brought up once and left running,
      // for the same reason as in C_UART1.
      uart1_ensure();

      for (uint8_t i = 1; i < n; i++) Serial1.write(rxbuf[i]);
      Serial1.flush();

      sendReady();
      break;
    }

    case C_PARK: {
      // Drive the console transmit line to a fixed level, bypassing the USART.
      // Payload: level(1). Reading the level back at the other end of the wire
      // separates a wiring fault from a UART fault: if the far end follows this,
      // the connection is sound and any remaining problem is in the framing.
      uint8_t lvl = (n >= 2) ? rxbuf[1] : 0;
      Serial1.end();
      pinMode(1, OUTPUT);
      digitalWrite(1, lvl ? HIGH : LOW);
      sendReady();
      break;
    }

    case C_WATCH: {
      // Payload: cmd(1)
      //   0 = start watching (D0 and D1 become inputs, buffer cleared)
      //   1 = read out everything recorded so far (buffer is cleared)
      //   2 = stop
      uint8_t sub = (n >= 2) ? rxbuf[1] : 0;

      if (sub == 0) {
        Serial1.end();
        pinMode(0, INPUT);
        pinMode(1, INPUT);
        digitalWrite(0, LOW);        // no pull-ups: the FPGA drives these
        digitalWrite(1, LOW);
        watch_len = 0;
        watch_last = (uint8_t)((PIND >> 2) & 0x03);
        watch_last_ms = millis();
        watch_on = true;
        sendReady();
        break;
      }

      if (sub == 2) {
        watch_on = false;
        sendReady();
        break;
      }

      // sub == 1: hand over the recording
      uint8_t count = (watch_len > 120) ? 120 : (uint8_t)watch_len;
      txReset(R_SAMPLE);
      uint8_t fcs = R_SAMPLE;
      txByte(count); fcs += count;
      for (uint8_t i = 0; i < count; i++) { txByte(watch_buf[i]); fcs += watch_buf[i]; }
      txSend(fcs);

      // shift the remainder down
      for (uint16_t i = count; i < watch_len; i++) watch_buf[i - count] = watch_buf[i];
      watch_len -= count;
      break;
    }

    case C_PINS: {
      // Report the raw port D registers around the console pins.
      //   DDD2 = 1 means D0 is configured as an output
      //   PORTD bit 2 is what we are asking it to drive
      //   PIND bit 2 is what the pin actually reads
      // That separates "the pin is still an input" from "the pin is driven but
      // something on the board is holding it".
      // Payload: mode(1) - 0 report, 1 both low, 2 both high,
      //                   3 D0 high + D1 low, 4 D0 low + D1 high
      uint8_t mode = (n >= 2) ? rxbuf[1] : 0;
      if (mode) {
        Serial1.end();
        pinMode(0, OUTPUT);
        pinMode(1, OUTPUT);
        switch (mode) {
          case 1:  digitalWrite(0, LOW);  digitalWrite(1, LOW);  break;
          case 2:  digitalWrite(0, HIGH); digitalWrite(1, HIGH); break;
          case 3:  digitalWrite(0, HIGH); digitalWrite(1, LOW);  break;
          case 4:  digitalWrite(0, LOW);  digitalWrite(1, HIGH); break;
          default: break;
        }
        delay(5);
      }

      txReset(R_STATUS);
      uint8_t fcs = R_STATUS;
      txByte(DDRD);  fcs += DDRD;
      txByte(PORTD); fcs += PORTD;
      txByte(PIND);  fcs += PIND;
      txSend(fcs);
      break;
    }

    case C_BLINK2: {
      // Drive D0 and D1 as plain outputs and blink them one after the other.
      // With the wire2 design in the FPGA - nothing but two wires to the LEDs -
      // this is the simplest possible end-to-end check: D0 blinking lights LED1,
      // D1 blinking lights LED2. Whichever one stays dark points at the wire or
      // the pin responsible.
      Serial1.end();
      pinMode(0, OUTPUT);
      pinMode(1, OUTPUT);
      digitalWrite(0, LOW);
      digitalWrite(1, LOW);

      sendReady();                  // answer first, then perform the show

      for (uint8_t round = 0; round < 3; round++) {
        for (uint8_t i = 0; i < 5; i++) {       // five blinks on D0
          digitalWrite(0, HIGH); delay(200);
          digitalWrite(0, LOW);  delay(200);
        }
        delay(800);
        for (uint8_t i = 0; i < 5; i++) {       // five blinks on D1
          digitalWrite(1, HIGH); delay(200);
          digitalWrite(1, LOW);  delay(200);
        }
        delay(800);
      }
      break;
    }

    case C_UART1: {
      // Hardware USART receive on D0 (PD2 = RXD1), which is far more reliable than
      // the software receiver above: the ATmega32u4 samples and frames in hardware,
      // so there is no timing budget to blow. Needs one wire from the FPGA to D0.
      //
      // Payload: milliseconds as two bytes. Short windows matter - the hardware
      // receive buffer holds only 64 bytes, so a long listen while the FPGA talks
      // continuously overruns it and silently drops characters. The host asks for
      // small slices and reassembles them.
      uint16_t ms = 3000;
      if (n >= 3)      ms = ((uint16_t)rxbuf[1] << 8) | rxbuf[2];
      else if (n >= 2) ms = (uint16_t)rxbuf[1] * 1000;

      // Bring the USART up once and leave it running. Two separate flags used to
      // exist here, one per direction, and whichever command ran second
      // re-initialised the port and wiped the other one's state.
      uart1_ensure();

      uint8_t got[160];
      uint8_t cnt = 0;
      unsigned long t0 = millis();
      while ((millis() - t0) < (unsigned long)ms) {
        while (Serial1.available() && cnt < 160) {
          got[cnt++] = (uint8_t)Serial1.read();
        }
      }

      txReset(R_UART1);
      uint8_t fcs = R_UART1;
      txByte(cnt); fcs += cnt;
      for (uint8_t i = 0; i < cnt; i++) { txByte(got[i]); fcs += got[i]; }
      txSend(fcs);

      SPI.begin();
      break;
    }

    case C_UARTRX: {
      // Listen to the FPGA's UART on MISO / D14 and report everything that
      // arrived. Payload: seconds(1) - how long to listen.
      uint8_t seconds = (n >= 2) ? rxbuf[1] : 3;

      SPI.end();
      pinMode(SCK, INPUT);              // D15
      pinMode(MOSI, INPUT);             // D16
      pinMode(MISO, INPUT);             // D14 - the FPGA drives this
      digitalWrite(MISO, LOW);          // no pull-up, the FPGA owns the line

      urx_len = 0;
      urx_bit = 0;
      urx_active = true;
      urx_done = false;

      noInterrupts();
      TCCR1A = 0;
      TCCR1B = _BV(WGM12) | _BV(CS10);          // CTC, prescaler 1
      OCR1A  = (uint16_t)(UART_TICKS_PER_BIT - 1);
      TCNT1  = 0;
      TIMSK1 |= _BV(OCIE1A);
      interrupts();

      unsigned long t0 = millis();
      while ((millis() - t0) < (unsigned long)seconds * 1000UL && !urx_done) { }

      noInterrupts();
      TIMSK1 &= ~_BV(OCIE1A);
      urx_active = false;
      interrupts();

      txReset(R_UARTRX);
      uint8_t fcs = R_UARTRX;
      txByte(urx_len); fcs += urx_len;
      for (uint8_t i = 0; i < urx_len; i++) { txByte(urx_buf[i]); fcs += urx_buf[i]; }
      txSend(fcs);

      SPI.begin();
      break;
    }

    case C_LISTEN: {
      // legacy 115200 listener kept for probing; same idea, no oversampling
      uint8_t seconds = (n >= 2) ? rxbuf[1] : 3;
      SPI.end();
      pinMode(SCK, INPUT);
      pinMode(MOSI, INPUT);
      pinMode(MISO, INPUT);
      digitalWrite(MISO, LOW);

      urx_len = 0;
      urx_bit = 0;
      urx_active = true;
      urx_done = false;

      noInterrupts();
      TCCR1A = 0;
      TCCR1B = _BV(WGM12) | _BV(CS10);
      OCR1A  = (uint16_t)((F_CPU / 115200UL) - 1);
      TCNT1  = 0;
      TIMSK1 |= _BV(OCIE1A);
      interrupts();

      unsigned long t0 = millis();
      while ((millis() - t0) < (unsigned long)seconds * 1000UL && !urx_done) { }

      noInterrupts();
      TIMSK1 &= ~_BV(OCIE1A);
      urx_active = false;
      interrupts();

      txReset(R_UART);
      uint8_t fcs = R_UART;
      txByte(urx_len); fcs += urx_len;
      for (uint8_t i = 0; i < urx_len; i++) { txByte(urx_buf[i]); fcs += urx_buf[i]; }
      txSend(fcs);

      SPI.begin();
      break;
    }

    case C_BITBANG: {
      // Drive MOSI/SCK slowly by hand and watch MISO after each step. No SPI
      // peripheral, no library, nothing that can be misconfigured - this
      // separates "the cable or the pins are wrong" from "the SPI setup is wrong".
      // Payload: MSB-first bit pattern (1 byte) to clock out.
      uint8_t pattern = (n >= 2) ? rxbuf[1] : 0xA5;

      SPI.end();
      pinMode(CS, OUTPUT); digitalWrite(CS, HIGH);   // keep the flash off the bus
      pinMode(SCK, OUTPUT);  digitalWrite(SCK, LOW);
      pinMode(MOSI, OUTPUT); digitalWrite(MOSI, LOW);
      pinMode(MISO, INPUT);  digitalWrite(MISO, LOW);

      uint8_t miso_bits = 0;
      for (int8_t b = 7; b >= 0; b--) {
        digitalWrite(MOSI, (pattern >> b) & 1);
        delayMicroseconds(100);
        digitalWrite(SCK, HIGH);
        delayMicroseconds(100);
        // read the port register directly: digitalRead() is ~5 us on AVR and the
        // line is only stable for as long as we hold SCK
        if (PINB & _BV(PB3)) miso_bits |= _BV(b);
        delayMicroseconds(50);
        digitalWrite(SCK, LOW);
        delayMicroseconds(100);
      }

      txReset(R_BITBANG);
      uint8_t fcs = R_BITBANG;
      txByte(pattern);   fcs += pattern;
      txByte(miso_bits); fcs += miso_bits;
      txSend(fcs);

      digitalWrite(MOSI, LOW);
      digitalWrite(SCK, LOW);
      SPI.begin();
      break;
    }

    case C_SPI: {
      // Talk to an FPGA design over the PGM1 SPI lines. Payload is a list of
      // bytes to clock out; the FPGA's replies come back on MISO and are
      // returned in order.
      //
      // SS_B (D13) stays high: it doubles as the flash chip select and pulls low
      // would put the flash on the same bus. An FPGA design that samples SCK or
      // MOSI does not need SS at all.
      SPI.begin();
      SPI.setClockDivider(SPI_CLOCK_DIV8);      // 2 MHz
      SPI.setDataMode(SPI_MODE0);
      digitalWrite(CS, HIGH);
      pinMode(CS, OUTPUT);

      uint8_t nbytes = (n > 1) ? (n - 1) : 0;
      if (nbytes > 32) nbytes = 32;

      txReset(R_SPI);
      uint8_t fcs = R_SPI;
      txByte(nbytes); fcs += nbytes;
      for (uint8_t i = 0; i < nbytes; i++) {
        uint8_t r = SPI.transfer(rxbuf[1 + i]);
        txByte(r); fcs += r;
      }
      txSend(fcs);
      break;
    }

    case C_ENTER:
      // hold the FPGA in reset: only then does its SPI reach the flash
      digitalWrite(RESET, LOW);
      delay(20);
      if (digitalRead(CDONE) != LOW) {
        sendError();          // FPGA still running - the pass-through is not open
      } else {
        flashPowerUp();
        sendReady();
      }
      break;

    case C_EXIT:
      csHigh();
      digitalWrite(RESET, HIGH);   // release reset, FPGA boots from flash
      delay(100);
      sendReady();
      break;

    case C_READ_ID:
      sendId(flashJedecId());
      break;

    case C_BULK_ERASE:
      flashBulkErase();
      sendReady();
      break;

    case C_SEC_ERASE: {
      uint32_t addr = ((uint32_t)rxbuf[1] << 16) | ((uint32_t)rxbuf[2] << 8) | rxbuf[3];
      flashSectorErase(addr);
      sendReady();
      break;
    }

    case C_PROG: {
      uint32_t addr = ((uint32_t)rxbuf[1] << 16) | ((uint32_t)rxbuf[2] << 8) | rxbuf[3];
      uint16_t len = (n > 4) ? (n - 4) : 0;
      if (len > PAGE_SIZE) len = PAGE_SIZE;
      flashPageProgram(addr, &rxbuf[4], len);
      sendReady();
      break;
    }

    case C_READ: {
      uint32_t addr = ((uint32_t)rxbuf[1] << 16) | ((uint32_t)rxbuf[2] << 8) | rxbuf[3];
      uint16_t pageOnes = (addr >> 8) & 0xFF;        // page number, echoed back
      uint8_t page[PAGE_SIZE];
      flashRead(addr, page, PAGE_SIZE);
      txReset(R_READ);
      uint8_t s = R_READ;
      txByte((pageOnes >> 8) & 0xFF); s += (pageOnes >> 8) & 0xFF;
      txByte(pageOnes & 0xFF);        s += pageOnes & 0xFF;
      for (uint16_t i = 0; i < PAGE_SIZE; i++) { txByte(page[i]); s += page[i]; }
      txSend(s);
      break;
    }

    default:
      sendReady();
      break;
  }
}
