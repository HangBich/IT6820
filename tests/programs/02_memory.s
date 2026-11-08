# Stores and loads with positive/negative offsets, then sums an array.
    li   s0, 0x100           # base address
    li   t0, 11
    li   t1, -22
    li   t2, 0x12345678
    sw   t0, 0(s0)
    sw   t1, 4(s0)
    sw   t2, 8(s0)
    addi s1, s0, 16
    sw   t2, -4(s1)          # 0x10C
    lw   a0, 0(s0)
    lw   a1, 4(s0)
    lw   a2, 8(s0)
    lw   a3, -4(s1)
    lw   a4, 0x10C(zero)
    # array[i] = i*i for i = 0..9, then sum it
    li   t0, 0
    li   t3, 10
    addi t4, s0, 0x40
fill:
                             # t5 = t0*t0 by repeated addition
    li   t5, 0
    li   t6, 0
sq: beq  t6, t0, sq_done
    add  t5, t5, t0
    addi t6, t6, 1
    j    sq
sq_done:
    sw   t5, 0(t4)
    addi t4, t4, 4
    addi t0, t0, 1
    blt  t0, t3, fill
    li   a5, 0
    addi t4, s0, 0x40
    li   t0, 0
sum:
    lw   t5, 0(t4)
    add  a5, a5, t5
    addi t4, t4, 4
    addi t0, t0, 1
    bne  t0, t3, sum
    sw   a5, 0(zero)         # 285
    ebreak
