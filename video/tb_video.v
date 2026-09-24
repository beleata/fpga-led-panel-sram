`timescale 1ns/1ps
module tb_video;
    reg CLK=0, RX=1;
    always #5 CLK=~CLK;
    wire TX,R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2;
    wire [17:0] sram_a;
    tri [7:0] sram_d;
    wire sram_we_n,sram_oe_n,sram_cs_n;
    video #(.HALF_TICKS(4),.HOLD_CLOCKS(256)) dut(.*);
    defparam dut.protocol.TIMEOUT=25000;
    reg [7:0] ram[0:16383];
    reg [5:0] seed[0:1023];
    reg inject_error=0;
    assign #10 sram_d=(!sram_cs_n && !sram_oe_n && sram_we_n) ?
                      (ram[sram_a[13:0]] ^ {7'b0,inject_error}) : 8'hzz;
    always @(posedge sram_we_n) if(!sram_cs_n) begin
        if(!sram_oe_n || sram_d===8'hzz || (^sram_d)===1'bx)
            $fatal(1,"Invalid SRAM write bus");
        ram[sram_a[13:0]]=sram_d;
    end
    always @(negedge sram_oe_n) if(!sram_we_n || dut.memory.drive)
        $fatal(1,"SRAM bus contention");

    integer scan_bits=0, p, addr;
    reg [15:0] expected_word;
    reg [5:0] expected_rgb;
    always @(posedge SCLK) if(dut.scan.state==9 && dut.scan.configured) begin
        for(p=0;p<6;p=p+1) begin
            addr=(dut.bank ? 8192:0)+p*1024+dut.word_address;
            expected_word=ram[addr]==255 ? 16'h0100 : {8'b0,ram[addr]};
            expected_rgb[p]=expected_word[15-dut.scan.count[3:0]];
        end
        if({B2,G2,R2,B1,G1,R1} !== expected_rgb)
            $fatal(1,"Scan mismatch word=%d bit=%d actual=%b expected=%b",dut.word_address,dut.scan.count[3:0],{B2,G2,R2,B1,G1,R1},expected_rgb);
        scan_bits=scan_bits+1;
    end

    reg [7:0] replies[0:255];
    integer reply_count=0, b;
    reg [7:0] tx_byte;
    always @(negedge TX) begin
        #750;
        for(b=0;b<8;b=b+1) begin tx_byte[b]=TX; #500; end
        if(TX!==1) $fatal(1,"TX stop bit");
        replies[reply_count]=tx_byte; reply_count=reply_count+1;
    end
    task send_byte(input [7:0] value);
        integer j;
        begin
            RX=0; #500;
            for(j=0;j<8;j=j+1) begin RX=value[j]; #500; end
            RX=1; #500;
        end
    endtask
    reg [15:0] crc;
    task body_byte(input [7:0] value);
        integer j;
        begin
            send_byte(value); crc=crc ^ (value<<8);
            for(j=0;j<8;j=j+1) crc=crc[15] ? (crc<<1)^16'h1021 : crc<<1;
        end
    endtask
    function [7:0] sample(input integer index, input integer variant);
        sample=(index*37+(index/1024)*19+variant*73) & 255;
    endfunction
    task send_packet(input [7:0] command, seq, input integer variant, input bad_crc);
        integer i;
        reg [15:0] final_crc;
        begin
            send_byte(8'h56); send_byte(8'h52); crc=16'hffff;
            body_byte(command); body_byte(seq);
            if(command==1) for(i=0;i<6144;i=i+1) body_byte(sample(i,variant));
            final_crc=crc ^ bad_crc;
            send_byte(final_crc[15:8]); send_byte(final_crc[7:0]);
        end
    endtask
    task check_reply(input integer start, input [7:0] seq, status);
        integer i;
        reg [7:0] sum;
        begin
            wait(reply_count>=start+9); #1000; sum=0;
            for(i=start;i<start+9;i=i+1) sum=sum ^ replies[i];
            if(sum || replies[start]!=8'ha5 || replies[start+1]!=8'h5a ||
               replies[start+2]!=seq || replies[start+3]!=status)
                $fatal(1,"Bad reply start=%d status=%d expected=%d",start,replies[start+3],status);
        end
    endtask
    integer i, n;
    initial begin
        $readmemh("pattern.hex",seed);
        #123;
        wait(dut.boot_done);
        if(dut.boot_error) $fatal(1,"Boot SRAM failure");
        for(i=0;i<6144;i=i+1)
            if(ram[i] !== (seed[i%1024][i/1024] ? 8'hff : 8'h00)) $fatal(1,"Seed mismatch %d",i);
        $display("PASS boot SRAM readback, all 6144 bytes");
        wait(dut.stable); #1000;
        send_packet(2,8'd90,0,0); check_reply(0,90,0);
        $display("PASS status and exact 2 Mbaud RX/TX");
        send_packet(1,1,1,0); check_reply(9,1,0);
        if(!dut.bank || !dut.stable) $fatal(1,"No frame commit");
        for(i=0;i<6144;i=i+1)
            if(ram[8192+i] !== sample(i,1)) $fatal(1,"Payload mismatch %d",i);
        $display("PASS frame 1, all SRAM bytes and serialized panel grayscale bits");
        send_packet(1,1,1,0); check_reply(18,1,0);
        if(!dut.bank) $fatal(1,"Duplicate flipped bank");
        send_packet(1,2,2,1); check_reply(27,2,2);
        if(!dut.bank) $fatal(1,"Bad CRC committed");
        $display("PASS duplicate retry and CRC rejection");
        send_byte(8'h56); send_byte(8'h52); send_byte(1); send_byte(2);
        repeat(37) send_byte(8'hff);
        #1100000;
        if(!dut.bank || !dut.stable) $fatal(1,"Partial frame changed display");
        send_packet(2,91,0,0); check_reply(36,91,0);
        $display("PASS partial frame timeout, previous frame retained");
        inject_error=1;
        send_packet(1,2,2,0); check_reply(45,2,3);
        inject_error=0;
        if(!dut.bank) $fatal(1,"SRAM error committed");
        $display("PASS injected SRAM readback error rejected");
        send_packet(1,2,2,0); check_reply(54,2,0);
        if(dut.bank) $fatal(1,"Second frame not committed");
        for(i=0;i<6144;i=i+1)
            if(ram[i] !== sample(i,2)) $fatal(1,"Second payload mismatch %d",i);
        $display("PASS second bank swap; checked %d panel bit clocks",scan_bits);
        // A break in the middle of a packet must not leave it locked in payload state.
        send_byte(8'h56); send_byte(8'h52); send_byte(1); send_byte(3);
        RX=0; #15000; RX=1; #10000;
        send_packet(2,92,0,0); check_reply(63,92,0);
        $display("PASS break recovery; ALL TESTS PASSED");
        $finish;
    end
    initial begin #500000000; $fatal(1,"Simulation timeout state=%d",dut.protocol.state); end
endmodule
