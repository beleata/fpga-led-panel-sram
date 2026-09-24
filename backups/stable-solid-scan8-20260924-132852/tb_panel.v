`timescale 1ns/1ps
module tb_panel;
    reg CLK = 0;
    always #5 CLK = ~CLK;
    wire R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2,TX;
    panel #(.HALF_TICKS(2), .HOLD_CLOCKS(256)) dut(.*);
    integer clocks = 0, frames = 0, latch_count = 0, config_bits = 0;
    integer old_state = -1, n;
    reg [15:0] shift_word = 0;
    reg [15:0] first_word = 0;
    reg [21:0] seen = 0;
    reg [7:0] rows_seen = 0;
    reg [15:0] expected [0:21];
    initial begin
        expected[0]=16'h0000; expected[1]=16'h0207;
        expected[2]=16'h0335; expected[3]=16'h0412;
        expected[4]=16'h0500; expected[5]=16'h0601;
        expected[6]=16'h0720; expected[7]=16'h0c18;
        expected[8]=16'h0d01; expected[9]=16'h0e86;
        expected[10]=16'h0f01; expected[11]=16'h1040;
        expected[12]=16'h1127; expected[13]=16'h1800;
        expected[14]=16'h1906; expected[15]=16'h1c60;
        expected[16]=16'h1dca; expected[17]=16'h1e73;
        expected[18]=16'h2000; expected[19]=16'h2100;
        expected[20]=16'h2300; expected[21]=16'h74a0;
        #100000000;
        $fatal(1,"Timeout state=%0d count=%0d frames=%0d config=%0d SCLK=%b",dut.state,dut.count,frames,dut.config_index,SCLK);
    end
    always @(posedge SCLK) begin
        if ({R1,G1,B1} !== {R2,G2,B2}) $fatal(1,"RGB halves differ");
        if (old_state != dut.state) begin
            if (frames == 0) $display("state=%0d t=%0t count=%0d",dut.state,$time,dut.count);
            if (old_state == 9) begin
                if (clocks != 16384 || latch_count != 128)
                    $fatal(1,"Incomplete upload: clocks=%0d latches=%0d",clocks,latch_count);
                frames = frames + 1;
                if (frames == 23) begin
                    if (seen !== 22'h3fffff) $fatal(1,"Missing configuration words");
                    if (!LED1) $fatal(1,"Configuration completion indicator missing");
                    if (rows_seen != 8'hff) $fatal(1,"Not all binary row addresses scanned");
                    $display("PASS: 22 register words broadcast to all eight chips; 23 full 16-bit frames; 128 latches/frame; all 8 binary addresses");
                    $finish;
                end
            end
            clocks = 0; latch_count = 0; shift_word = 0;
            old_state = dut.state;
        end
        clocks = clocks + 1;
        if (LAT) latch_count = latch_count + 1;
        if (dut.state >= 3 && dut.state <= 7) begin
            if (LAT !== (clocks > 123)) $fatal(1,"Register latch window");
            shift_word = {shift_word[14:0],R1};
            if ((clocks % 16) == 0) begin
                if (clocks == 16) first_word = shift_word;
                else if (shift_word != first_word) $fatal(1,"Register differs across chips");
                if (dut.state == 5 && shift_word != expected[dut.config_index])
                    $fatal(1,"Wrong config word");
                if (dut.state == 5) seen[dut.config_index] = 1;
            end
        end
        if (dut.state == 9) begin
            if (LAT !== ((clocks % 128) == 0)) $fatal(1,"Grayscale latch interval");
            if ({C,B,A} !== dut.scan_row[2:0]) $fatal(1,"Wrong binary address");
            rows_seen[{C,B,A}] = 1;
            if (!dut.configured && {R1,G1,B1} != 0) $fatal(1,"Pixels before full initialization");
            if (dut.configured && dut.color == 0 && R1 !== (dut.count[3:0] == 7))
                $fatal(1,"Expected 0x0100 grayscale");
        end
    end
endmodule
