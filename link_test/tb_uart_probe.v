`timescale 1ns/1ps
module tb_uart_probe;
    reg clk=0, rx=1;
    always #20 clk=~clk;
    wire tx, trained, error;
    uart_probe dut(.*);
    integer divisor, rate, n;
    reg [7:0] received;
    task send_byte(input [7:0] value);
        integer b;
        begin
            @(negedge clk); rx=0; repeat(divisor) @(negedge clk);
            for(b=0;b<8;b=b+1) begin rx=value[b]; repeat(divisor) @(negedge clk); end
            rx=1; repeat(divisor) @(negedge clk);
        end
    endtask
    task receive_byte(output [7:0] value);
        integer b;
        begin
            @(negedge tx);
            #(divisor*60);
            for(b=0;b<8;b=b+1) begin value[b]=tx; #(divisor*40); end
            if(tx!==1) $fatal(1,"Invalid transmitted stop bit");
        end
    endtask
    initial begin
        for(rate=0;rate<5;rate=rate+1) begin
            case(rate)
                0: divisor=5208;
                1: divisor=2604;
                2: divisor=217;
                3: divisor=50;
                4: divisor=25;
            endcase
            rx=0; repeat(250020) @(negedge clk);
            rx=1; repeat(100) @(negedge clk);
            send_byte(8'h55); repeat(divisor*20) @(negedge clk);
            if(!trained || dut.baud_div!=divisor) $fatal(1,"Training failed %0d %0d",divisor,dut.baud_div);
            fork
                begin
                    for(integer i=0;i<32;i=i+1) send_byte((i*73+19)&255);
                end
                begin
                    for(integer i=0;i<32;i=i+1) begin
                        receive_byte(received);
                        if(received!==(((i*73+19)&255)^8'ha5))
                            $fatal(1,"Echo mismatch %0d: %02x",i,received);
                    end
                end
            join
            if(error) $fatal(1,"UART/FIFO error");
            $display("PASS: divisor %0d, baud ~%0d, 32 bytes",divisor,25000000/divisor);
        end
        $finish;
    end
    initial begin #1000000000; $fatal(1,"Timeout"); end
endmodule
