`timescale 1ns/1ps
module tb_reference;
    reg CLK=0;
    always #5 CLK=~CLK;
    wire R1,G1,B1,R2,G2,B2,A,B,C,SCLK,LAT,OE,LED1,LED2,TX;
    // Accelerate only the half-clock. Counts and all protocol signals are unchanged.
    panel #(.HALF_TICKS(3)) dut(.*);
    integer fd, held=0, clocks=0;
    reg [15:0] mask;
    initial fd=$fopen("../pico/generated/fpga-reference.bin","wb");
    always @(posedge SCLK) begin
        mask={4'b0,OE,LAT,SCLK,C,B,A,B2,G2,R2,B1,G1,R1};
        $fwrite(fd,"%c%c",mask[7:0],mask[15:8]);
        clocks=clocks+1;
        if(dut.state==11 && dut.visible_uploads==2) begin
            held=held+1;
            if(held==1024) begin
                $fclose(fd);
                $display("FPGA reference complete: %d clocks",clocks);
                $finish;
            end
        end
    end
    initial begin #400000000; $fatal(1,"Reference timeout"); end
endmodule
