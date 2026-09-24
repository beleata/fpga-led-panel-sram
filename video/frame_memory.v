// Uses the low byte of the board's 256K x 16 asynchronous SRAM.
// Bank 0: 0000..17FF; bank 1: 2000..37FF. Six 1024-byte color planes.
module frame_memory(input clk, bank, fetch, input [9:0] word_address,
    output reg [47:0] colors=0,
    input write_request, input [12:0] write_address, input [7:0] write_data,
    output write_accept, output reg write_error=0,
    output reg boot_done=0, output reg boot_error=0,
    output reg [17:0] sram_a=0, inout [7:0] sram_d,
    output reg sram_we_n=1, output reg sram_oe_n=1, output sram_cs_n);
    reg [5:0] seed [0:1023];
    reg [5:0] seed_data=0;
    reg [12:0] boot_address=0;
    initial $readmemh("pattern.hex",seed);
    always @(posedge clk) seed_data<=seed[boot_address[9:0]];
    reg [4:0] state=0;
    reg boot_write=0, drive=0;
    reg [7:0] data_out=0, pending_data=0;
    reg [9:0] cache_address=0;
    reg cache_valid=0, cache_bank=0;
    reg [2:0] plane=0;
    assign sram_cs_n=0;
    assign sram_d=drive ? data_out : 8'hzz;
    assign write_accept=state==0 && boot_done && write_request;
    always @(posedge clk) begin
        write_error<=0;
        case(state)
            0: begin
                sram_we_n<=1; sram_oe_n<=1; drive<=0;
                if(!boot_done) begin
                    sram_a<={5'b0,boot_address}; boot_write<=1; state<=1;
                end else if(write_request) begin
                    sram_a<={4'b0,~bank,write_address}; pending_data<=write_data;
                    boot_write<=0; state<=1;
                end else if(fetch && (!cache_valid || cache_address!=word_address || cache_bank!=bank)) begin
                    cache_address<=word_address; cache_bank<=bank; plane<=0;
                    cache_valid<=0; sram_a<={4'b0,bank,3'b0,word_address};
                    state<=16;
                end
            end
            1: begin
                data_out<=boot_write ? (seed_data[boot_address[12:10]] ? 8'hff : 0) : pending_data;
                drive<=1; state<=2;
            end
            2: begin sram_we_n<=0; state<=3; end
            3: state<=4;
            4: begin sram_we_n<=1; state<=5; end
            5: begin drive<=0; state<=6; end
            6: begin sram_oe_n<=0; state<=7; end
            7: state<=8;
            8: begin
                if(sram_d!=data_out) begin
                    if(boot_write) boot_error<=1;
                    else write_error<=1;
                end
                sram_oe_n<=1; state<=9;
            end
            9: begin
                if(boot_write) begin
                    if(boot_address==6143) boot_done<=1;
                    else boot_address<=boot_address+1'b1;
                end
                state<=0;
            end
            16: begin sram_oe_n<=0; state<=17; end
            17: state<=18;
            18: begin
                colors[plane*8 +: 8]<=sram_d;
                sram_oe_n<=1;
                if(plane==5) begin cache_valid<=1; state<=0; end
                else begin
                    plane<=plane+1'b1;
                    sram_a<={4'b0,cache_bank,plane+3'd1,cache_address}; state<=16;
                end
            end
        endcase
    end
endmodule
