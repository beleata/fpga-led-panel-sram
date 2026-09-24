module link_diag(
    input CLK, RX,
    output TX,
    output R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2
);
    wire unused_tx, panel_led1, panel_led2;
    panel display(.CLK(CLK), .R1(R1), .G1(G1), .B1(B1), .R2(R2),
        .G2(G2), .B2(B2), .A(A), .B(B), .C(C), .SCLK(SCLK), .LAT(LAT),
        .OE(OE), .LED1(panel_led1), .LED2(panel_led2), .TX(unused_tx));
    reg [1:0] div = 0;
    always @(posedge CLK) div <= div + 1'b1;
    wire clk;
`ifdef SIMULATION
    assign clk = div[1];
`else
    SB_GB buffer_clock(.USER_SIGNAL_TO_GLOBAL_BUFFER(div[1]), .GLOBAL_BUFFER_OUTPUT(clk));
`endif
    wire trained, error;
    uart_probe probe(.clk(clk), .rx(RX), .tx(TX), .trained(trained), .error(error));
    assign LED1 = trained;
    assign LED2 = error | panel_led2;
endmodule

// 25 MHz. A >= 12 ms low break rearms training. Send 0x55, wait >= 20 ms,
// then every received byte is returned XOR 0xA5. No spontaneous UART traffic.
module uart_probe #(
    parameter BREAK_CLOCKS = 250000,
    parameter BEACON_CLOCKS = 6250000
)(input clk, rx, output tx, output trained, output reg error = 0);
    reg rx_meta = 1, rx_sync = 1;
    always @(posedge clk) begin
        rx_meta <= rx;
        rx_sync <= rx_meta;
    end
    reg [23:0] beacon_count = 0;
    reg beacon = 1;
    always @(posedge clk) begin
        if (beacon_count == BEACON_CLOCKS-1) begin
            beacon_count <= 0;
            beacon <= ~beacon;
        end else beacon_count <= beacon_count + 1'b1;
    end
    reg [18:0] low_count = 0;
    reg [2:0] train_state = 0;
    reg [15:0] measure = 0, baud_div = 5208;
    reg [19:0] guard_count = 0;
    wire reset_link = train_state != 3;
    assign trained = train_state == 3;
    wire uart_out;
    assign tx = trained ? uart_out : beacon;
    always @(posedge clk) begin
        if (rx_sync) low_count <= 0;
        else if (low_count < BREAK_CLOCKS) low_count <= low_count + 1'b1;
        if (low_count == BREAK_CLOCKS) begin
            train_state <= 4;
            measure <= 0;
        end else case (train_state)
            0: if (!rx_sync) begin train_state <= 1; measure <= 1; end
            1: if (rx_sync) begin
                if (measure >= 8) begin
                    baud_div <= measure;
                    guard_count <= {measure,4'b0000};
                    train_state <= 2;
                end else train_state <= 0;
            end else if (measure == 65535) train_state <= 4;
            else measure <= measure + 1'b1;
            2: if (guard_count == 0) train_state <= 3;
               else guard_count <= guard_count - 1'b1;
            4: if (rx_sync) train_state <= 0;
        endcase
    end
    wire [7:0] rx_data;
    wire rx_valid, rx_error, tx_busy;
    reg tx_start = 0;
    reg [7:0] tx_data = 0;
    diag_uart_rx receiver(.clk(clk), .rst(reset_link), .rx(rx_sync),
        .divisor(baud_div), .data(rx_data), .valid(rx_valid), .bad_stop(rx_error));
    diag_uart_tx transmitter(.clk(clk), .rst(reset_link), .divisor(baud_div),
        .start(tx_start), .data(tx_data), .tx(uart_out), .busy(tx_busy));
    reg [7:0] fifo [0:255];
    reg [7:0] wr_ptr = 0, rd_ptr = 0;
    wire fifo_full = (wr_ptr + 8'd1) == rd_ptr;
    always @(posedge clk) begin
        tx_start <= 0;
        if (reset_link) begin
            wr_ptr <= 0; rd_ptr <= 0; error <= 0;
        end else begin
            if (rx_error) error <= 1;
            if (rx_valid) begin
                if (fifo_full) error <= 1;
                else begin fifo[wr_ptr] <= rx_data ^ 8'ha5; wr_ptr <= wr_ptr + 1'b1; end
            end
            if (!tx_busy && !tx_start && rd_ptr != wr_ptr) begin
                tx_data <= fifo[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
                tx_start <= 1;
            end
        end
    end
endmodule

module diag_uart_rx(input clk, rst, rx, input [15:0] divisor,
    output reg [7:0] data = 0, output reg valid = 0, output reg bad_stop = 0);
    reg [1:0] state = 0;
    reg [15:0] timer = 0;
    reg [2:0] bit_index = 0;
    reg [7:0] shift = 0;
    always @(posedge clk) begin
        valid <= 0; bad_stop <= 0;
        if (rst) begin state <= 0; timer <= 0; end
        else case (state)
            0: if (!rx) begin state <= 1; timer <= (divisor >> 1)-1'b1; end
            1: if (timer != 0) timer <= timer-1'b1;
               else if (rx) state <= 0;
               else begin state <= 2; timer <= divisor-1'b1; bit_index <= 0; end
            2: if (timer != 0) timer <= timer-1'b1;
               else begin
                   shift[bit_index] <= rx;
                   timer <= divisor-1'b1;
                   if (bit_index == 7) state <= 3;
                   else bit_index <= bit_index+1'b1;
               end
            3: if (timer != 0) timer <= timer-1'b1;
               else begin
                   data <= shift; valid <= rx; bad_stop <= !rx; state <= 0;
               end
        endcase
    end
endmodule

module diag_uart_tx(input clk, rst, start, input [15:0] divisor,
    input [7:0] data, output tx, output reg busy = 0);
    reg [9:0] shift = 10'h3ff;
    reg [15:0] timer = 0;
    reg [3:0] bit_index = 0;
    assign tx = busy ? shift[0] : 1'b1;
    always @(posedge clk) begin
        if (rst) begin busy <= 0; shift <= 10'h3ff; end
        else if (!busy) begin
            if (start) begin
                shift <= {1'b1,data,1'b0}; timer <= divisor-1'b1;
                bit_index <= 0; busy <= 1;
            end
        end else if (timer != 0) timer <= timer-1'b1;
        else begin
            timer <= divisor-1'b1;
            shift <= {1'b1,shift[9:1]};
            if (bit_index == 9) busy <= 0;
            else bit_index <= bit_index+1'b1;
        end
    end
endmodule
