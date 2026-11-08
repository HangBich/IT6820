# All R-type and I-type ALU instructions, including edge values.
    li   t0, 0x7FFFFFFF      # largest positive
    li   t1, -1              # 0xFFFFFFFF
    li   t2, 0x80000000      # most negative
    li   t3, 5
    add  a0, t0, t3          # overflow wraps
    sub  a1, t3, t0
    and  a2, t0, t1
    or   a3, t2, t3
    xor  a4, t1, t3
    slt  a5, t2, t3          # signed: -2^31 < 5 -> 1
    sltu a6, t2, t3          # unsigned: 0x80000000 < 5 -> 0
    slt  a7, t3, t2
    sltu s2, t3, t2
    sll  s3, t3, t3          # 5 << 5
    srl  s4, t2, t3          # logical
    sra  s5, t2, t3          # arithmetic keeps sign
    li   s6, 35              # shift amount uses only the low 5 bits (35 -> 3)
    sll  s7, t3, s6
    addi s8, t3, -6
    andi s9, t1, 0x0F0
    ori  s10, t3, -2048
    xori s11, t3, 0x7FF
    slti t4, t2, 0
    sltiu t5, t3, -1         # imm sign-extends to 0xFFFFFFFF
    slli t6, t3, 31
    srli t0, t2, 4
    srai t1, t2, 4
    lui  a0, 0xABCDE
    auipc a1, 0x1            # pc + 0x1000
    add  zero, t3, t3        # writes to x0 are ignored
    addi a2, zero, 0
    ebreak
