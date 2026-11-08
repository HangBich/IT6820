# Every branch type taken and not taken, jal/jalr calls, a jump table.
    li   s0, 0               # bit mask of taken branches
    li   t0, -5
    li   t1, 3
    beq  t0, t0, b1
    addi s0, s0, 1000        # skipped
b1: ori  s0, s0, 1
    beq  t0, t1, bad
    bne  t0, t1, b2
    addi s0, s0, 1000
b2: ori  s0, s0, 2
    bne  t1, t1, bad
    blt  t0, t1, b3          # signed -5 < 3
    addi s0, s0, 1000
b3: ori  s0, s0, 4
    blt  t1, t0, bad
    bge  t1, t0, b4
    addi s0, s0, 1000
b4: ori  s0, s0, 8
    bge  t0, t1, bad
    bltu t1, t0, b5          # unsigned 3 < 0xFFFFFFFB
    addi s0, s0, 1000
b5: ori  s0, s0, 16
    bltu t0, t1, bad
    bgeu t0, t1, b6
    addi s0, s0, 1000
b6: ori  s0, s0, 32
    bgeu t1, t0, bad
    # backwards branch loop: count down
    li   t2, 6
    li   s1, 0
loop:
    addi s1, s1, 2
    addi t2, t2, -1
    bnez t2, loop
    # function calls
    li   a0, 7
    call double              # jal ra, double
    mv   s2, a0              # 14
    call double
    mv   s3, a0              # 28
    jal  t3, after           # link in another register
    addi s0, s0, 1000
after:
    la   t4, target          # auipc + addi
    jalr t5, 0(t4)           # indirect jump, link in t5
    addi s0, s0, 1000
target:
    la   t6, back
    addi t6, t6, 1           # odd target address: jalr clears bit 0
    jalr ra, t6, 0
    addi s0, s0, 1000
back:
    sw   s0, 0(zero)
    j    end
double:
    add  a0, a0, a0
    ret
bad:
    li   s0, -1
end:
    ebreak
