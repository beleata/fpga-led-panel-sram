(* techmap_celltype = "$_ORNOT_" *)
module map_ornot(input A, B, output Y);
    \$lut #(.WIDTH(2), .LUT(4'b1011)) cell_lut(.A({B,A}), .Y(Y));
endmodule
(* techmap_celltype = "$_ANDNOT_" *)
module map_andnot(input A, B, output Y);
    \$lut #(.WIDTH(2), .LUT(4'b0010)) cell_lut(.A({B,A}), .Y(Y));
endmodule
