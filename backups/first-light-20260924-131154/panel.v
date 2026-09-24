// ICND1065L bring-up. See NOTES.md for sources and unverified panel geometry.
module panel #(
    parameter SCAN = 16,
    parameter CHIPS = 4,
    parameter ROW_MODE = 2,
    parameter HALF_TICKS = 8,
    parameter ROW_PERIOD = 128,
    parameter OE_START = 100,
    parameter ROW_START = 112,
    parameter PIXEL = 16'h0100,
    parameter HOLD_CLOCKS = 32768
) (
    input CLK,
    output R1, G1, B1, R2, G2, B2,
    output reg A, B, C,
    output reg SCLK, LAT, OE,
    output LED1, LED2,
    output TX
);
    initial begin
        A=0; B=0; C=0; SCLK=0; LAT=0; OE=0;
    end
    // Dedicated global clock buffer for the /4 clock, 25 MHz from 100 MHz.
    reg [1:0] div = 0;
    always @(posedge CLK) div <= div + 1'b1;
    wire clk;
`ifdef SIMULATION
    assign clk = div[1];
`else
    SB_GB clock_buffer(.USER_SIGNAL_TO_GLOBAL_BUFFER(div[1]),
                       .GLOBAL_BUFFER_OUTPUT(clk));
`endif
    reg [26:0] heartbeat = 0;
    reg configured = 0;
    always @(posedge clk) heartbeat <= heartbeat + 1'b1;
    assign LED2 = heartbeat[23];
    assign LED1 = configured;
    // Hardware UART test byte 'U', 4800 baud, repeated with an idle gap.
    reg [12:0] uart_div = 0;
    reg [4:0] uart_bit = 0;
    always @(posedge clk) begin
        if (uart_div == 5207) begin
            uart_div <= 0;
            uart_bit <= uart_bit + 1'b1;
        end else uart_div <= uart_div + 1'b1;
    end
    assign TX = (uart_bit == 0) ? 1'b0 :
                (uart_bit < 9) ? uart_bit[0] : 1'b1;

    localparam REG_CLOCKS = CHIPS * 16;
    localparam DATA_CLOCKS = SCAN * 16 * REG_CLOCKS;
    localparam GAP = 10;
    reg [3:0] state = 0;
    reg [15:0] count = 0;
    reg [4:0] config_index = 0;
    reg [1:0] color = 0;
    reg [7:0] phase = 0;
    reg [5:0] scan_row = 0;
    reg [7:0] tick_div = 0;
    reg [2:0] rgb = 0;
    assign {B2,G2,R2,B1,G1,R1} = {rgb,rgb};

    // DMD_STM32 ICND1065 defaults; scan field adapted by its documented rule.
    // All chips receive the SAME address/value word, one new word per frame.
    reg [15:0] config_word;
    always_comb begin
        case (config_index)
             0: config_word = 16'h0000;
             1: config_word = 16'h0200 | (SCAN - 1);
             2: config_word = 16'h0335;
             3: config_word = 16'h0412;
             4: config_word = 16'h0500;
             5: config_word = 16'h0601;
             6: config_word = 16'h0720;
             7: config_word = 16'h0c18;
             8: config_word = 16'h0d01;
             9: config_word = 16'h0e86;
            10: config_word = 16'h0f01;
            11: config_word = 16'h1040;
            12: config_word = 16'h1127;
            13: config_word = 16'h1800;
            14: config_word = 16'h1906;
            15: config_word = 16'h1c60;
            16: config_word = 16'h1dca;
            17: config_word = 16'h1e73;
            18: config_word = 16'h2000;
            19: config_word = 16'h2100;
            20: config_word = 16'h2300;
            default: config_word = 16'h74a0;
        endcase
    end
    reg [15:0] word;
    reg [15:0] length;
    always_comb begin
        case (state)
            0: length = 16;  // LAT 3, spacer 12, final clock (reference helper)
            1: length = 15;  // LAT 11, spacer 3, final clock
            2: length = 24;  // LAT 14, spacer 9, final clock
            8: length = 12;
            9: length = DATA_CLOCKS;
            GAP: length = 625; // 200 us at 3.125 MHz; scaled with clock setting
            11: length = HOLD_CLOCKS;
            default: length = REG_CLOCKS;
        endcase
        case (state)
            3: word = 16'h00aa;
            4: word = 16'h01aa;
            5: word = config_word;
            6: word = 16'h0055;
            7: word = 16'h0155;
            default: word = 0;
        endcase
    end

    // Controls update while CLK is LOW, a full half-period before sampling.
    // Upload counters and row-scan counters are independent: one latch per
    // channel across the chain, 16 channels per row, 16 grayscale bits each.
    always @(posedge clk) begin
        if (tick_div == HALF_TICKS - 1) begin
            tick_div <= 0;
            if (!SCLK && state != GAP) begin
                SCLK <= 1;
            end else begin
                SCLK <= 0;
                if (count == length - 1) begin
                    count <= 0;
                    if (state == 9) state <= 11;
                    else if (state == 11) state <= GAP;
                    else if (state == GAP) begin
                        state <= 0;
                        phase <= 0;
                        scan_row <= 0;
                        color <= heartbeat[26:25];
                        if (config_index == 21) begin
                            config_index <= 0;
                            configured <= 1;
                        end else config_index <= config_index + 1'b1;
                    end else state <= state + 1'b1;
                end else count <= count + 1'b1;

                if (state == 9 || state == 11) begin
                    if (phase == ROW_PERIOD - 1) phase <= 0;
                    else phase <= phase + 1'b1;
                    if (phase == ROW_START - 1) begin
                        if (scan_row == SCAN - 1) scan_row <= 0;
                        else scan_row <= scan_row + 1'b1;
                    end
                end
            end
        end else tick_div <= tick_div + 1'b1;
    end

    // Register these outputs shortly after state changes, still in CLK-low.
    always @(posedge clk) begin
        if (!SCLK) begin
            rgb <= 0;
            LAT <= 0;
            OE <= 0;
            A <= 0; B <= 0; C <= 0;
            case (state)
                0: LAT <= count < 3;
                1: LAT <= count < 11;
                2: LAT <= count < 14;
                3,4,5,6,7: begin
                    rgb <= {3{word[15-count[3:0]]}};
                    LAT <= count >= REG_CLOCKS - 5;
                end
                8: OE <= 1;
                9,11: begin
                    OE <= phase >= OE_START && phase < OE_START + 4;
                    if (ROW_MODE == 0) begin
                        {C,B,A} <= scan_row[2:0];
                    end else begin
                        A <= phase >= ROW_START + 2 && phase < ROW_START + 4;
                        B <= phase >= ROW_START && phase < ROW_START + 4;
                        C <= scan_row == 0 && phase >= ROW_START && phase < ROW_START + 4;
                    end
                    if (state == 9) begin
                        LAT <= (count % REG_CLOCKS) == REG_CLOCKS - 1;
                        if (configured && PIXEL[15-count[3:0]]) begin
                            case (color)
                                0: rgb <= 3'b001;
                                1: rgb <= 3'b010;
                                2: rgb <= 3'b100;
                                3: rgb <= 3'b000;
                            endcase
                        end
                    end
                end
            endcase
        end
    end
endmodule
