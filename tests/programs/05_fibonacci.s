# Demo: first 20 Fibonacci numbers stored to data memory at 0x000..0x04C.
    li   t0, 0               # fib(i)
    li   t1, 1               # fib(i+1)
    li   t2, 0               # address
    li   t3, 20              # count
loop:
    sw   t0, 0(t2)
    add  t4, t0, t1
    mv   t0, t1
    mv   t1, t4
    addi t2, t2, 4
    addi t3, t3, -1
    bnez t3, loop
    lw   a0, -4(t2)          # fib(19) = 4181
    ebreak
