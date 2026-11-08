# Pipeline hazards. Every result is checked by the test bench against the
# reference model, so a missing forward/stall/flush shows up as a wrong write.
    # EX/MEM -> EX forwarding (distance 1), both operands
    li   t0, 3
    add  t1, t0, t0          # t0 from EX/MEM
    add  t2, t1, t0          # t1 from EX/MEM, t0 from MEM/WB
    sub  t3, t2, t1          # chain
    # MEM/WB -> EX forwarding (distance 2)
    li   a0, 100
    nop
    add  a1, a0, a0
    # WB -> ID bypass (distance 3: written and read in the same cycle)
    li   a2, 7
    nop
    nop
    add  a3, a2, a2
    # newest value wins when both EX/MEM and MEM/WB hold the register
    li   s0, 1
    li   s0, 2
    add  s1, s0, s0          # must use 2
    # no forwarding from x0
    addi zero, zero, 55
    add  s2, zero, zero      # must stay 0
    # load-use: one stall, then MEM/WB forward
    li   s3, 0x200
    li   t4, 41
    sw   t4, 0(s3)
    lw   t5, 0(s3)
    addi t6, t5, 1           # load-use on rs1
    lw   a4, 0(s3)
    add  a5, t0, a4          # load-use on rs2
    # load -> store data (store needs the loaded value)
    lw   a6, 0(s3)
    sw   a6, 4(s3)
    # store data forwarded from an ALU result
    addi a7, t0, 9
    sw   a7, 8(s3)
    # store address forwarded
    addi s4, s3, 12
    sw   t0, 0(s4)
    # branch operands forwarded from ALU and from a load
    li   s5, 5
    addi s6, s5, 0
    beq  s5, s6, ok1         # taken, operands from EX/MEM and MEM/WB
    li   s7, -1              # flushed
    li   s7, -1              # flushed
ok1:
    lw   s8, 0(s3)
    bne  s8, t4, bad         # load-use into a branch, not taken
    # taken branch flushes the two younger instructions
    li   s9, 0
    beq  zero, zero, ok2
    addi s9, s9, 1
    addi s9, s9, 1
ok2:
    # jal link value forwarded to the next instruction
    jal  ra, f1
f1: addi s10, ra, 0
    # jalr base forwarded from the previous instruction
    la   t0, f2
    jalr t1, 0(t0)
    li   s11, -1
f2: addi s11, t1, 0
    # loop with a load-use and a dependent branch every iteration
    li   t0, 0
    li   t2, 0
    li   t3, 5
loop:
    sw   t0, 16(s3)
    lw   t1, 16(s3)
    add  t2, t2, t1
    addi t0, t0, 1
    blt  t0, t3, loop
    sw   t2, 20(s3)
    j    end
bad:
    li   s0, -1
end:
    ebreak
