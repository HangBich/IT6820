# Test Register File (`modules/regfile.circ`)

Test thủ công trong Logisim Evolution, dùng công cụ Poke (bàn tay).

Quy ước:
- Luôn để `clk` = 0 khi đổi các ngõ vào khác.
- "Bấm clock" = đổi `clk` 0 → 1 → 0. Dữ liệu được ghi ở cạnh lên (0 → 1).
- Phần đọc là mạch tổ hợp: đổi `rs1`/`rs2` là `ReadData1`/`ReadData2` đổi ngay, không cần clock.

| # | Thao tác | Kết quả mong đợi | Kiểm tra | Kết quả |
|---|---|---|---|---|
| 1 | `reset` = 1 rồi về 0 | Tất cả thanh ghi = 0 | Reset hoạt động | PASS |
| 2 | `RegWrite` = 1, `rd` = 3, `WriteData` = 5, bấm clock | Thanh ghi x3 = 5 | Ghi ở cạnh lên | PASS |
| 3 | `rs1` = 3 | `ReadData1` = 5 | Cổng đọc 1 | PASS |
| 4 | `rd` = 7, `WriteData` = 9, bấm clock; `rs2` = 7 | `ReadData2` = 9, `ReadData1` vẫn = 5 | Cổng đọc 2, đọc 2 thanh ghi cùng lúc | PASS |
| 5 | `rd` = 0, `WriteData` = 12, bấm clock; `rs1` = 0 | `ReadData1` = 0 | x0 luôn bằng 0 | PASS |
| 6 | `RegWrite` = 0, `rd` = 3, `WriteData` = 8, bấm clock | x3 vẫn = 5 | RegWrite = 0 thì không ghi | PASS |
| 7 | `RegWrite` = 1, `rd` = 31, `WriteData` = 1, bấm clock; `rs1` = 31 | `ReadData1` = 1 | Thanh ghi cuối cùng | PASS |
| 8 | Ghi x12 = 12, x16 = 16, x17 = 17, x21 = 21; đọc lại từng cái qua cả `rs1` và `rs2` | Mỗi thanh ghi đúng giá trị của nó, không thanh ghi nào khác bị đổi | Không nhầm tên Tunnel giữa các thanh ghi | |

## Ghi chú

- Lỗi đã gặp ở test 4: phải bấm clock thêm một lần mới đọc ra 9. Nguyên nhân là `clk` đang ở mức 1 từ bước trước, nên lần bấm đầu là 1 → 0 (không có cạnh lên, không ghi). Cách tránh: luôn đưa `clk` về 0 trước khi đặt dữ liệu.
- Test 5 không cần clock để đọc ra 0 vì ngõ 0 của cả hai MUX đọc nối thẳng với hằng 0.