# ICND1065L LED Panel: FPGA SRAM and RP2040 Pico

64x32 ICND1065L RGB LED panel drivers: Olimex iCE40HX1K FPGA with SRAM video
memory, and a YD-RP2040 / Raspberry Pi Pico PIO + DMA display implementation
with USB frame streaming. Wiring, initialization protocol, source, tests and
ready-to-flash firmware are included.

## Custom Controller PCB (Draft)

Самостоятелна двуслойна платка **88 x 46.1 mm** с RP2040, 8 MiB flash,
вертикална USB-C, RS-485 и W5500 Ethernet с вертикална RJ45.

**НЕ Е ГОТОВА ЗА ПРОИЗВОДСТВО.** Публикувани са схемата, 103 компонента,
ръчната подредба и пробно трасиране. След корекциите: 0 DRC нарушения,
но остава 1 неопроводена връзка QSPI_D1. Сигналната цялост и захранването
още не са квалифицирани. Това не променя статуса на работещия Pico модул.

- [PCB files, current status and documentation](hardware/pico-panel/README.md)
- [Пробно трасиране и ограничения](hardware/pico-panel/routing-trial/README_BG.md)

## RP2040 Pico

Потвърден работещ вариант с **YD-RP2040 2022-V1.3, 8 MiB flash**:
правилна геометрична фигура и стабилна картина. PIO и DMA изпълняват
проверената FPGA последователност при SCLK **1.5625 MHz**.

- [Свързване, компилиране и инструкции](pico/README_BG.md)
- [Готов firmware за YD-RP2040 8 MiB](pico/pico_panel.uf2)
- [Изходен код и тестове](pico/)

Добавен е USB CDC приемник с два RGB888 буфера във вътрешната SRAM на Pico.
PC декодира GIF и изпраща кадрите; Pico пази последния кадър при спиране
на изпращането. [USB видео: инструкции и протокол](pico/USB_VIDEO_BG.md).
Новият [USB firmware](pico/pico_panel_usb.uf2) е отделен от стария статичен UF2.
Измерени са 13,49 кадъра/s при 70 последователни кадъра, без PIO/DMA грешки;
визуалната проверка на новата анимация предстои.

## FPGA SRAM

Работещ проект за **Olimex iCE40HX1K-EVB**, RGB LED панел **64 x 32** с
ICND1065L драйвери и външна SRAM видео памет. Изображенията се изпращат от
компютър през OLIMEXINO-32U4 по UART **2 Mbaud**. Два SRAM буфера, CRC16 и
проверка чрез прочит след запис пазят активната картина при недовършен или
повреден пакет. Последната приета картина се показва без допълнителен трафик.

## Потвърдено На Реален Хардуер

- Правилна геометрия, цветове и стабилна статична картина.
- Приемане и показване на изображение от външния SRAM.
- Отхвърляне на грешна CRC и непълен кадър; безопасно повторение на пакет.
- Шест различни кадъра, 18 успешни прехвърляния: **3.16 кадъра/секунда**
  през текущия USB мост. Това не е физическият максимум на UART/SRAM.
- Потребителят потвърди картината и поиска непрекъсната анимация.

Проверки, хешове и ограничения: [video/VERIFICATION.md](video/VERIFICATION.md).
SRAM е енергозависима: след изключване или FPGA reset се връща началната
геометрична фигура, а не последният изпратен потребителски кадър.

## Бърз Старт

Текущата среда е Windows/PowerShell, Python 3.13, OSS CAD Suite в
`C:\oss-cad-suite`, Arduino AVR core 1.8.8. Инсталирайте Python зависимостите:

```powershell
python -m pip install -r requirements.txt
.\video\test.ps1
.\video\build.ps1
python program_panel.py video/video.bin --port COM18
python video/send_image.py --image C:\images\picture.png --port COM18
```

Картинката е 64 x 32; `--resize` разрешава преоразмеряване, `--rotate 180`
обръща изображението. Пиновете и безопасното свързване са описани в
[video/README_BG.md](video/README_BG.md). Не свързвайте 5 V към FPGA GPIO.
OLIMEXINO трябва да използва 3.3 V логически нива. GPIO1 пин 34 **не е земя**.
`HARDWARE.md` е историческа бележка и съдържа стари предположения; водещи
са актуалната документация, `.pcf` файловете и потвърдените резултати.

Анимация и спиране след текущия кадър:

```powershell
python video/animate.py --cycles 3
.\video\start_animation.ps1
.\video\stop_animation.ps1
```

Фоновата анимация държи COM18 отворен. Спрете я преди друга команда към
платката. Изпращането на изображения не презаписва FPGA flash.

## Съдържание

| Път | Предназначение |
|---|---|
| `video/` | Текущ SRAM драйвер, UART протокол, клиенти, тестове и bitstream |
| `pico/` | Потвърден RP2040 PIO/DMA статичен драйвер, UF2, свързване и тестове |
| `panel/` | Потвърдена стабилна статична версия за възстановяване |
| `link_test/` | UART диагностика и измервания на скоростта |
| `programmer-fw/` | OLIMEXINO USB/SPI/UART програматор и готов firmware |
| `backups/` | Работещи етапи, резервни копия и хешове |
| `logs/` | Запазени резултати от синтез, програмиране и тестове |
| `reference/` | Външни източници, фиксирани като Git submodules |
| `PANEL_PROTOCOL_BG.md` | Подробен протокол за управление на ICND1065L |
| `program_panel.py` | Двоен backup read, запис, проверка и CDONE |
| `iceprog.py` | Клиент за USB протокола на програматора |

Архивите `stable-panel-20260924.zip` и `video-sram-20260924.zip` пазят
самостоятелни работещи снимки на проекта. Текущите файлове извън архивите
може да съдържат по-нови помощни скриптове и документация.

## Референтни Източници

При клониране използвайте `git clone --recurse-submodules <repository-url>`.
За вече клонирано хранилище: `git submodule update --init --recursive`.
Основният FPGA build не изисква компилация на тези референтни проекти.

- [board707/DMD_STM32](https://github.com/board707/DMD_STM32),
  commit `398ec1d8636bce866709fbe9c3f0035c90645e7a`.
- [OLIMEX/iCE40HX1K-EVB](https://github.com/OLIMEX/iCE40HX1K-EVB),
  commit `91f3b5aff50258ddb40c021a21d4fd871633fc80`.
- [kingdo9/rpi-rgb-led-matrix_pwm_experiment](https://github.com/kingdo9/rpi-rgb-led-matrix_pwm_experiment),
  commit `5da13cb3b0d38d66bb5201f03704b5bef9e4446b`.

Външните проекти запазват собствените си лицензи и авторство. Това
хранилище не добавя нов общ лиценз върху техния код или хардуерни проекти.
