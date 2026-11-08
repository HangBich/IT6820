# CPU RISC-V RV32I 32-bit trên Logisim-evolution

Project gồm hai phiên bản CPU trong cùng file `project.circ`:

| Mạch | Mô tả |
|---|---|
| `SingleCycleCPU` | CPU đơn chu kỳ, mỗi lệnh 1 chu kỳ |
| `PipelineCPU` (main) | Pipeline 5 tầng IF → ID → EX → MEM → WB, có forwarding, stall khi load-use, flush khi rẽ nhánh/nhảy |

Cả hai chạy chương trình nạp trong ROM lệnh `IMEM`. Không cần chỉnh tay giá trị thanh ghi.

## 1. Mở project

1. Cài Logisim-evolution 4.1.0 (cần Java 21).
2. Mở `project.circ`. Mạch chính là `PipelineCPU`. Chọn `SingleCycleCPU` ở khung bên trái để xem bản đơn chu kỳ.
3. Khi mới mở, ROM đã có sẵn chương trình demo `tests/programs/05_fibonacci.s`.

## 2. Chạy mô phỏng trong giao diện

- `Simulate → Reset Simulation` (Ctrl+R) để đưa PC, thanh ghi và RAM về 0.
- Chạy từng chu kỳ bằng `Simulate → Tick Full Cycle` (F9). Chạy liên tục bằng `Simulate → Auto-Tick Enabled` (Ctrl+K).
- Các chỗ có thể quan sát:
  - **Thanh ghi:** double-click khối `RegisterFile` để vào trong. Mỗi thanh ghi `x1`…`x31` hiển thị giá trị hiện tại.
  - **Bộ nhớ dữ liệu:** vào khối `Memory`, RAM `DMEM` hiển thị nội dung. Right-click → `Edit Contents` để xem toàn bộ.
  - **Pipeline:** các pin output bên phải `PipelineCPU`:
    - `if_instr`, `id_instr`, `ex_instr`, `mem_instr`, `wb_instr`: lệnh đang nằm ở từng tầng;
    - `stall`, `flush`: tín hiệu xử lý hazard;
    - `wb_en`/`wb_rd`/`wb_data`: lệnh ghi thanh ghi;
    - `mem_we`/`mem_addr`/`mem_wdata`: lệnh ghi bộ nhớ;
    - `cycle`: số chu kỳ đã chạy.
  - Bên trong các khối `IF_ID`, `ID_EX`, `EX_MEM`, `MEM_WB` có từng trường của thanh ghi pipeline.
- Lệnh `ebreak` (hoặc `ecall`) dừng CPU: pin `halt` lên 1, PC và pipeline đứng yên.

## 3. Viết và nạp chương trình

Viết assembly RV32I (xem các ví dụ trong `tests/programs/`), rồi dịch và nạp vào **cả hai** CPU:

```sh
python3 tools/asm/rvasm.py chuong_trinh.s --circ project.circ --list
```

Lệnh này tạo `chuong_trinh.hex` (ảnh bộ nhớ Logisim) và ghi chương trình vào mọi ROM có nhãn `IMEM`. Sau đó mở lại file trong Logisim. Cách khác: right-click ROM `IMEM` → `Load Image…` → chọn file `.hex`.

- Nếu chương trình có `.data`, assembler tạo thêm `chuong_trinh.data.hex`. Nạp nó vào RAM `DMEM` bằng right-click → `Load Image…`.
- Chạy thử trên mô hình tham chiếu Python để biết kết quả mong đợi:

  ```sh
  python3 tools/asm/rvsim.py chuong_trinh.s
  ```

**Lệnh được hỗ trợ:**
- **Số học / logic:** `add sub and or xor slt sltu sll srl sra` và `addi andi ori xori slti sltiu slli srli srai`.
- **Bộ nhớ:** `lw sw`.
- **Rẽ nhánh và nhảy:** `beq bne blt bge bltu bgeu jal jalr`.
- **Khác:** `lui auipc`, và `ecall`/`ebreak` (dừng CPU).
- **Lệnh giả:** `nop li la mv not neg seqz snez j jr ret call beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu`.

**Bộ nhớ:**
- **Lệnh:** 1024 word (4 KiB), bắt đầu từ địa chỉ 0.
- **Dữ liệu:** 1024 word (4 KiB). Đây là bộ nhớ riêng (kiến trúc Harvard), cũng bắt đầu từ 0, đánh địa chỉ theo `Address[11:2]`.

## 4. Chạy test

Cần Java 21 (`JAVA=/đường/dẫn/java` nếu `java` mặc định là bản cũ) và Python 3.

```sh
# Test từng module bằng test vector của Logisim (15 module, ~2000 vector)
tests/modules/run_module_tests.sh

# Test toàn CPU: chạy mọi chương trình trên cả hai CPU, so với mô hình tham chiếu
python3 tests/cpu/run_cpu_tests.py
```

**Test module:**
- File `.vec` nằm trong `tests/modules/`, sinh bởi `gen_vectors.py` từ mô hình Python của đặc tả.
- Có thể chạy trong giao diện: chọn mạch → `Simulate → Test Vector…` → mở file `.vec` cùng tên.
- Mạch tuần tự (RegisterFile, Memory, các thanh ghi pipeline) dùng cột `<SET>`/`<SEQ>` để test theo chuỗi chu kỳ.

**Test toàn CPU:**
- Logisim chạy headless (`--tty table`) cho tới khi `halt` = 1.
- Script đọc chuỗi lệnh ghi thanh ghi (`wb_*`) và ghi bộ nhớ (`mem_*`) theo từng chu kỳ, rồi so khớp từng sự kiện với `rvsim.py`.
- Kết quả hiện tại:

| Chương trình | Nội dung | Đơn chu kỳ | Pipeline |
|---|---|---|---|
| `01_alu` | mọi lệnh ALU, giá trị biên | PASS, CPI 1.00 | PASS, CPI 1.12 |
| `02_memory` | lw/sw, offset âm, mảng | PASS, CPI 1.00 | PASS, CPI 1.50 |
| `03_branch_jump` | 6 loại branch, jal/jalr, call/ret | PASS, CPI 1.00 | PASS, CPI 1.69 |
| `04_hazards` | forwarding, load-use, flush, bypass | PASS, CPI 1.00 | PASS, CPI 1.42 |
| `05_fibonacci` | demo | PASS, CPI 1.00 | PASS, CPI 1.29 |
| `06_bubble_sort` | demo | PASS, CPI 1.00 | PASS, CPI 1.45 |

`04_hazards` đã được kiểm chứng bằng cách cố ý tắt từng cơ chế: tắt forwarding, tắt stall, tắt flush hoặc tắt bypass WB→ID đều làm test FAIL.

## 5. Kiến trúc

### Các module (mạch con)

| Mạch | Chức năng |
|---|---|
| `InstructionDecode` | Tách lệnh thành OP, rd, funct3 (`ext3`), rs1, rs2, funct7 |
| `MainControl` | Từ opcode sinh: RegWrite, MemRead, MemWrite, Branch, Jal, Jalr, ALUSrcA (0=rs1, 1=PC, 2=0), ALUSrcB (0=rs2, 1=imm), ALUOp, ImmSel (0=I, 1=S, 2=B, 3=U, 4=J), WBSel (0=ALU, 1=Mem, 2=PC+4), Halt |
| `ALUControl` | Từ ALUOp + funct3 + funct7 sinh mã ALU: 0 ADD, 1 SUB, 2 AND, 3 OR, 4 XOR, 5 SLL, 6 SRL, 7 SRA, 8 SLT, 9 SLTU |
| `ALU` | 10 phép toán 32-bit |
| `ImmGen` | Immediate có dấu cho các kiểu I/S/B/U/J |
| `RegisterFile` | 32×32 bit, x0 luôn bằng 0, 2 cổng đọc tổ hợp, ghi ở sườn lên |
| `BranchUnit` | So sánh rs1/rs2 theo funct3 (BEQ BNE BLT BGE BLTU BGEU) |
| `Memory` | RAM dữ liệu 1024×32, ghi ở sườn lên, đọc tổ hợp |
| `HazardUnit` | `stall = ID/EX.MemRead ∧ ID/EX.rd≠0 ∧ (ID/EX.rd = IF/ID.rs1 ∨ IF/ID.rs2)` |
| `ForwardingUnit` | fwd = 2 lấy từ EX/MEM, 1 lấy từ MEM/WB, 0 lấy từ thanh ghi. Lệnh mới hơn được ưu tiên; không forward x0 |
| `WBBypass` | Tầng ID đọc đúng giá trị đang được ghi ở WB trong cùng chu kỳ |
| `IF_ID`, `ID_EX`, `EX_MEM`, `MEM_WB` | Thanh ghi pipeline. `en`=0 thì giữ nguyên (stall); `flush`=1 thì nạp toàn 0, tức một bubble (opcode 0 không có tín hiệu điều khiển nào) |

### Đơn chu kỳ

```
PC → IMEM → Decode/Control → RegisterFile → ALU → Memory → WB mux → RegisterFile
```

PC kế tiếp chọn giữa PC+4, PC+imm (branch được lấy hoặc JAL), và (rs1+imm) & ~1 (JALR).

### Pipeline 5 tầng

- **Data hazard:**
  - forwarding EX/MEM→EX và MEM/WB→EX cho cả hai toán hạng ALU, toán hạng so sánh branch, và dữ liệu cần store;
  - bypass WB→ID trong register file;
  - load-use: stall 1 chu kỳ (giữ PC và IF/ID, chèn bubble vào ID/EX).
- **Control hazard:** branch, JAL và JALR được quyết định ở tầng EX. CPU đoán "không nhảy"; khi nhảy thì flush IF/ID và ID/EX (mất 2 chu kỳ).
- **Halt:** `ebreak` đi tới WB thì dừng. Mọi lệnh trước nó đã hoàn tất, và lệnh sau nó không được ghi bộ nhớ.

## 6. Cấu trúc thư mục

```
project.circ               CPU (được sinh lại bằng tools/gen/build_project.py)
Lab1.circ                  bản gốc
tools/asm/rvasm.py         assembler → .hex / nạp vào ROM
tools/asm/rvsim.py         mô hình tham chiếu ISA
tools/gen/                 script sinh project.circ (lgen.py: thư viện sinh mạch Logisim)
tools/portdump/            đọc toạ độ chân linh kiện bằng chính Logisim (dùng khi sinh mạch)
tools/render/              xuất ảnh PNG của các mạch
tests/modules/             test vector cho từng module
tests/programs/            chương trình test / demo
tests/cpu/                 test toàn CPU
```

### Quan hệ với Lab1

- `ALU`, `ALUControl` và `InstructionDecode` được giữ nguyên từ Lab1. Riêng ALU sửa 2 lỗi:
  - SRA đang dùng phép dịch logic, đã đổi sang dịch số học;
  - SLT trả về -1 thay vì 1, đã đổi Bit Extender sang mở rộng không dấu.
- Các mạch sau được làm lại, giữ tên mạch và tên chân:
  - `RegisterFile`: cổng đọc rs2 nối lệch thanh ghi, x31 không ghi được;
  - `Memory`: đọc ra giá trị không xác định;
  - `ImmGen`: thiếu immediate kiểu J, kiểu B và U sai;
  - `BranchUnit`: mới có BEQ/BNE;
  - `MainControl`: thiếu tín hiệu cho JAL/JALR/LUI/AUIPC và WBSel.

### Sinh lại project.circ

```sh
python3 tools/gen/build_project.py
```

Lệnh này cần biên dịch `tools/portdump/PortDump.java` trước bằng `javac -cp <logisim.jar> PortDump.java`.
# IT6820
