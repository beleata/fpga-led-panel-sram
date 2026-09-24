# OLIMEXINO: регулируема серийна връзка

На 24.09.2026 е записан `iceprog_link/iceprog_link.ino` с Arduino CLI,
платформа `arduino:avr:leonardo` / AVR core 1.8.8, с `upload --verify`.
Изходният код е копие на стария `iceprog2` плюс две диагностични команди.
Съществуващите flash команди и SLIP/FCS форматът са запазени.

HEX: `build-link/iceprog_link.ino.hex`, SHA256:
`bb7c525c9650fdedcbeb71a75a0b99a1dae4fba41bf5613ef19103e4c65e76ab`.
Компилация: 10254 bytes flash, 1744 bytes статична RAM.

Преди записа са прочетени два еднакви 32768-byte образа:
`../backups/programmer-20260924-163657/flash-read-1.bin` и `flash-read-2.bin`.
SHA256 на всеки: `c760cb3fd3da887b04448cdb0e21457ef1c57c968ab32d560b4615aa48a3461c`.
Първият опит за backup е по-къс, защото avrdude премахва trailing 0xFF;
валидният пълен backup е направен с `-A`.

В същата директория `application-28672.bin` е копие само на приложението,
без 4096-byte Caterina bootloader. При необходимост от възстановяване
използвайте този application-only файл, не пълния 32 KiB образ.
Bootloader се отваря с 1200-baud touch, както в `../link_test/backup_programmer.py`.
Avrdude за възстановяване през временния bootloader COM порт:

```text
avrdude -C <avrdude.conf> -p atmega32u4 -c avr109 -P <boot-COM> -b 57600 -D -U flash:w:<absolute-path-to-application-28672.bin>:r
```

Това е инструкция за възстановяване, не команда за ежедневна работа.
Възстановяването ще премахне новите E0/E1 команди.

## Нови команди

Командите са във външните USB SLIP кадри на `iceprog.py`, не сурови байтове
към FPGA. USB CDC се отваря на 230400 в клиентите; действителният UART baud
се избира отделно.

### 0xE0: избор и обучение

Payload: желан baud като 4-byte unsigned big-endian, 1200..2000000.
OLIMEXINO спира watcher-а, подава 20 ms break на D1, освобождава линията
за 2 ms, включва USART на зададената скорост, изпраща 0x55, чака 25 ms и
изчиства стартовите байтове от RX буфера.

Отговор 0xE0 с три байта: UBRR1H, UBRR1L, U2X (0/1).
При 16 MHz: actual_baud = 16000000 / ((U2X ? 8 : 16) * (UBRR+1)).
Някои номинални скорости се закръгляват: 460800 става 500000,
921600 става 1000000. Най-бързият делител UBRR=0, U2X=1 дава 2000000.

Тази команда е съобразена с тестовия FPGA autobaud протокол. При бъдещ
video-RAM драйвер трябва да се съгласува обучението или да се добави режим
за задаване на скорост без break/0x55.

### 0xE1: ограничен двупосочен тест

Payload: 1..48 байта. OLIMEXINO ги предава на FPGA, изчаква края на TX,
събира до същия брой върнати байтове с timeout 250 ms след flush.
Отговор 0xE1: count, следван от count байта. Клиентът проверява всеки
срещу изпратения XOR 0xA5. Размерът е под 64-byte RX ring на Arduino.

Новият `uart1_ensure()` проверява и действителните RXEN/TXEN битове, така
че WATCH -> UART не оставя USART изключен заради остарял локален флаг.
WATCH все още освобождава D0/D1 като входове; за тест отново изпратете E0.

Пинове: D0 е RX от GPIO1/13; D1 е TX към GPIO1/14. Първоначално бяха
разменени; потребителят ги размени и посоката е проверена с бавни импулси.

## Възпроизвеждане

От корена на проекта, с вече зареден `link_test/link_diag.bin`:

```powershell
python link_test/benchmark.py
python link_test/benchmark.py --rates 2000000 --bytes 1048576 --seed 15485863 --output logs/uart-2m-endurance.json
```

Тестовете мерят обмен на проверявани 48-byte пакети. Това не е проверка
за непрекъснат full-duplex поток без паузи или работа при всички възможни
кабели, смущения и температури. Полезният PC throughput включва USB и
командните паузи и е различен от UART baudrate.
