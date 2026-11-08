# Demo: write 10 numbers to memory, bubble sort them in place (ascending,
# signed), then compute the checksum sum(a[i] * (i+1)) as a0.
    li   s0, 0x80            # array base
    li   s1, 10              # n
    li   t1, 9
    sw   t1, 0(s0)
    li   t1, -3
    sw   t1, 4(s0)
    li   t1, 27
    sw   t1, 8(s0)
    li   t1, 0
    sw   t1, 12(s0)
    li   t1, 14
    sw   t1, 16(s0)
    li   t1, -40
    sw   t1, 20(s0)
    li   t1, 5
    sw   t1, 24(s0)
    li   t1, 5
    sw   t1, 28(s0)
    li   t1, 1000
    sw   t1, 32(s0)
    li   t1, -1
    sw   t1, 36(s0)
    addi s2, s1, -1          # outer passes
outer:
    mv   t2, s0
    mv   t3, s2
    li   s3, 0               # swapped flag
inner:
    lw   t4, 0(t2)
    lw   t5, 4(t2)
    ble  t4, t5, noswap
    sw   t5, 0(t2)
    sw   t4, 4(t2)
    li   s3, 1
noswap:
    addi t2, t2, 4
    addi t3, t3, -1
    bnez t3, inner
    beqz s3, sorted
    addi s2, s2, -1
    bnez s2, outer
sorted:
    li   a0, 0
    mv   t2, s0
    li   t3, 1
check:
    lw   t4, 0(t2)
    mv   t5, t3              # t4 * t3 by repeated addition
    li   t6, 0
mul:
    add  t6, t6, t4
    addi t5, t5, -1
    bnez t5, mul
    add  a0, a0, t6
    addi t2, t2, 4
    addi t3, t3, 1
    ble  t3, s1, check
    ebreak
