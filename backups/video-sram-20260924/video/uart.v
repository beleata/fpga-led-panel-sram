// 2 Mbaud at 25 MHz: alternate 12/13-clock bit periods, no autobaud needed.
module video_uart_rx(input clk, rx, output reg [7:0] data = 0,
    output reg valid = 0, output reg bad_stop = 0);
    reg meta=1, sync=1;
    always @(posedge clk) begin meta<=rx; sync<=meta; end
    reg [1:0] state=0;
    reg [4:0] timer=0;
    reg [2:0] bit_index=0;
    reg [7:0] shift=0;
    always @(posedge clk) begin
        valid<=0; bad_stop<=0;
        case(state)
            0: if(!sync) begin state<=1; timer<=12; end
            1: if(timer>2) timer<=timer-2;
               else if(sync) state<=0;
               else begin state<=2; timer<=timer+23; bit_index<=0; end
            2: if(timer>2) timer<=timer-2;
               else begin
                   shift[bit_index]<=sync; timer<=timer+23;
                   if(bit_index==7) state<=3;
                   else bit_index<=bit_index+1'b1;
               end
            3: if(timer>2) timer<=timer-2;
               else begin data<=shift; valid<=sync; bad_stop<=!sync; state<=0; end
        endcase
    end
endmodule

module video_uart_tx(input clk, start, input [7:0] data,
    output tx, output reg busy=0);
    reg [9:0] shift=10'h3ff;
    reg [4:0] timer=0;
    reg [3:0] bit_index=0;
    assign tx=busy ? shift[0] : 1'b1;
    always @(posedge clk) begin
        if(!busy) begin
            if(start) begin
                shift<={1'b1,data,1'b0}; timer<=25; bit_index<=0; busy<=1;
            end
        end else if(timer>2) timer<=timer-2;
        else begin
            timer<=timer+23; shift<={1'b1,shift[9:1]};
            if(bit_index==9) busy<=0;
            else bit_index<=bit_index+1'b1;
        end
    end
endmodule
