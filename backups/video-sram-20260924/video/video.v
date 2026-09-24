module video #(parameter HALF_TICKS=8, HOLD_CLOCKS=32768)(
    input CLK, RX, output TX,
    output R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2,
    output [17:0] sram_a, inout [7:0] sram_d,
    output sram_we_n,sram_oe_n,sram_cs_n);
    reg [1:0] divider=0;
    always @(posedge CLK) divider<=divider+1'b1;
    wire clk;
`ifdef SIMULATION
    assign clk=divider[1];
`else
    SB_GB global_clock(.USER_SIGNAL_TO_GLOBAL_BUFFER(divider[1]), .GLOBAL_BUFFER_OUTPUT(clk));
`endif
    wire [7:0] rx_data, tx_data, write_data;
    wire rx_valid, rx_error, tx_start, tx_busy;
    wire boot_done,boot_error,bank,fetch,stable,refresh,refresh_taken;
    wire write_request,write_accept,write_error;
    wire [9:0] word_address;
    wire [12:0] write_address;
    wire [47:0] colors;
    wire initialized, heartbeat;
    assign LED1=stable && !boot_error;
    assign LED2=boot_error || heartbeat;
    video_uart_rx uart_rx(.clk(clk),.rx(RX),.data(rx_data),.valid(rx_valid),.bad_stop(rx_error));
    video_uart_tx uart_tx(.clk(clk),.start(tx_start),.data(tx_data),.tx(TX),.busy(tx_busy));
    frame_protocol protocol(.*);
    frame_memory memory(.*);
    panel_scan #(.HALF_TICKS(HALF_TICKS),.HOLD_CLOCKS(HOLD_CLOCKS)) scan(
        .clk(clk),.enable(boot_done && !boot_error),.refresh(refresh),.colors(colors),
        .word_address(word_address),.fetch_active(fetch),.stable(stable),
        .refresh_taken(refresh_taken),.R1(R1),.G1(G1),.B1(B1),.R2(R2),.G2(G2),.B2(B2),
        .A(A),.B(B),.C(C),.SCLK(SCLK),.LAT(LAT),.OE(OE),.LED1(initialized),.LED2(heartbeat));
endmodule
