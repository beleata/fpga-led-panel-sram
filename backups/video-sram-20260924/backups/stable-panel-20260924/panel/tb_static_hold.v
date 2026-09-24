`timescale 1ns/1ps
module tb_static_hold;
    reg CLK = 0;
    always #5 CLK = ~CLK;
    wire R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2,TX;
    panel #(.HALF_TICKS(2), .HOLD_CLOCKS(256)) dut(.*);
    integer uploads = 0, old_state = -1, hold_clocks = 0;
    integer previous_phase = 0, previous_row = 0;
    integer row_clocks [0:7];
    integer oe_clocks [0:7];
    integer i;
    reg holding = 0;
    time previous_edge = 0;
    initial begin
        for (i = 0; i < 8; i = i + 1) begin
            row_clocks[i] = 0;
            oe_clocks[i] = 0;
        end
        #100000000;
        $fatal(1, "Timeout before continuous scan verification");
    end
    always @(posedge SCLK) begin
        if (dut.state == 9 && old_state != 9) uploads = uploads + 1;
        old_state = dut.state;
        if (dut.state == 11 && dut.visible_uploads == 2 && !holding) begin
            if (uploads != 24) $fatal(1, "Expected 22 blank and two visible uploads");
            holding = 1;
        end
        if (holding) begin
            if (dut.state != 11 || dut.visible_uploads != 2)
                $fatal(1, "Static hold restarted the frame");
            if (LAT || {B2,G2,R2,B1,G1,R1} != 0)
                $fatal(1, "Unexpected latch or data during static hold");
            if ({C,B,A} !== dut.scan_row[2:0]) $fatal(1, "Row address mismatch");
            if (OE !== (dut.phase >= 100 && dut.phase < 104))
                $fatal(1, "OE pulse timing changed");
            if (hold_clocks > 0) begin
                if ($time - previous_edge != 160) $fatal(1, "Clock gap during hold");
                if (dut.phase != ((previous_phase + 1) % 128))
                    $fatal(1, "Scan phase discontinuity");
                if (dut.scan_row != ((previous_row + (previous_phase == 111)) % 8))
                    $fatal(1, "Scan row discontinuity");
            end
            previous_edge = $time;
            previous_phase = dut.phase;
            previous_row = dut.scan_row;
            row_clocks[dut.scan_row] = row_clocks[dut.scan_row] + 1;
            if (OE) oe_clocks[dut.scan_row] = oe_clocks[dut.scan_row] + 1;
            hold_clocks = hold_clocks + 1;
            if (hold_clocks == 8192) begin
                for (i = 0; i < 8; i = i + 1) begin
                    if (row_clocks[i] != 1024 || oe_clocks[i] != 32)
                        $fatal(1, "Unequal row dwell/OE: row=%0d clocks=%0d OE=%0d",
                               i, row_clocks[i], oe_clocks[i]);
                end
                $display("PASS: 24 uploads, then 8192 uninterrupted clocks; equal dwell for all rows; unchanged OE; no LAT/data/reinitialization");
                $finish;
            end
        end
    end
endmodule
