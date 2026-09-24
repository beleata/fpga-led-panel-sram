// UART: 'VR', command, sequence, payload, CRC16-CCITT big-endian.
// Command 1: six 1024-byte planes. Command 2: status, no payload.
// CRC starts FFFF and covers command+sequence+payload (not 'VR').
module frame_protocol #(parameter TIMEOUT=25000000)(
    input clk, input [7:0] rx_data, input rx_valid, rx_error,
    input boot_done, boot_error, stable, refresh_taken,
    output reg bank=0, output reg refresh=0,
    output reg write_request=0, output reg [12:0] write_address=0,
    output reg [7:0] write_data=0, input write_accept, write_error,
    output reg tx_start=0, output reg [7:0] tx_data=0, input tx_busy);
    reg [3:0] state=0;
    reg [7:0] command=0, frame_sequence=0, last_sequence=0;
    reg [15:0] crc=16'hffff, received_crc=0, last_crc=0;
    reg [3:0] crc_steps=0;
    wire [15:0] crc_next=(crc<<1) ^ (crc[15] ? 16'h1021 : 16'h0000);
    reg [12:0] offset=0;
    reg accepted=0, memory_bad=0;
    reg have_last=0;
    reg [24:0] idle_ticks=0;
    reg [7:0] status=0;
    reg [3:0] reply_index=0;
    reg [7:0] reply_xor=0;
    wire [7:0] flags={4'b0,boot_error,bank,boot_done,stable};
    wire [7:0] next_reply = reply_index==0 ? 8'ha5 :
        reply_index==1 ? 8'h5a : reply_index==2 ? frame_sequence :
        reply_index==3 ? status : reply_index==4 ? flags :
        reply_index==5 ? last_sequence : reply_index==6 ? last_crc[15:8] :
        reply_index==7 ? last_crc[7:0] : reply_xor;
    always @(posedge clk) begin
        tx_start<=0;
        if(write_accept) write_request<=0;
        if(write_error) memory_bad<=1;
        if(crc_steps!=0) begin crc<=crc_next; crc_steps<=crc_steps-1'b1; end
        if(state>=2 && state<=6) begin
            if(rx_valid) idle_ticks<=0;
            else idle_ticks<=idle_ticks+1'b1;
            if(rx_error || idle_ticks==TIMEOUT-1) begin
                state<=0; idle_ticks<=0; crc_steps<=0;
            end
        end else idle_ticks<=0;

        if(state==7 && crc_steps==0 && !write_request) begin
            reply_index<=0; reply_xor<=0;
            state<=10;
            if(crc!=0) status<=2;
            else if(command==2) status<=boot_error ? 3 : 0;
            else if(!accepted) status<=1;
            else if(memory_bad) status<=3;
            else if(have_last && received_crc==last_crc && frame_sequence==last_sequence) status<=0;
            else begin
                bank<=~bank; refresh<=1;
                last_crc<=received_crc; last_sequence<=frame_sequence;
                have_last<=1;
                state<=8;
            end
        end
        if(state==8 && refresh_taken) begin refresh<=0; state<=9; end
        if(state==9 && stable) begin
            state<=10; reply_index<=0; reply_xor<=0; status<=0;
        end
        if(state==10 && !tx_busy && !tx_start) begin
            tx_data<=next_reply; tx_start<=1;
            reply_xor<=reply_xor ^ next_reply;
            if(reply_index==8) state<=11;
            else reply_index<=reply_index+1'b1;
        end
        if(state==11 && !tx_busy && !tx_start) state<=0;

        if(rx_valid && !(rx_error || idle_ticks==TIMEOUT-1)) begin
            if(state>=2 && state<=6) begin
                crc<=crc ^ {rx_data,8'b0}; crc_steps<=8;
            end
            case(state)
                0: if(rx_data==8'h56) state<=1;
                1: if(rx_data==8'h52) begin state<=2; crc<=16'hffff; end
                   else if(rx_data!=8'h56) state<=0;
                2: if(rx_data==1 || rx_data==2) begin
                       command<=rx_data; state<=3; memory_bad<=0;
                       accepted<=boot_done && !boot_error && stable;
                   end else state<=0;
                3: begin
                    frame_sequence<=rx_data; offset<=0;
                    state<=command==1 ? 4 : 5;
                end
                4: begin
                    if(accepted) begin
                        if(write_request && !write_accept) memory_bad<=1;
                        write_request<=1; write_address<=offset; write_data<=rx_data;
                    end
                    if(offset==6143) state<=5;
                    else offset<=offset+1'b1;
                end
                5: begin received_crc[15:8]<=rx_data; state<=6; end
                6: begin received_crc[7:0]<=rx_data; state<=7; end
            endcase
        end
    end
endmodule
