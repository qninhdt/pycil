# FSRS Learning Engine — Thiết kế thuật toán

**Trạng thái:** đề xuất (design note, chưa triển khai)
**Ngày:** 2026-07-04
**Phạm vi:** thay lớp lập lịch ELO hiện tại bằng FSRS nguyên bản + router câu hỏi mỏng.

---

## 1. Mục tiêu & nguyên tắc

Dùng **FSRS-4.5 nguyên bản** (đã được benchmark 10 năm, không tự chế toán học mới).
Mọi yêu cầu riêng của sản phẩm được giải bằng một lớp **ánh xạ vào/ra mỏng**, không thêm mô hình:

- Engine chỉ nhận nhãn nhị phân **Đúng / Sai** (không có "gần đúng", không response-time, không self-rating).
- Câu hỏi phụ thuộc **cấp độ mastery**, có xác suất ra câu **dễ hơn** nhưng **cấm** ra câu khó hơn cấp hiện tại.
- **Không** tối ưu tham số theo từng user (no nightly fit). Dùng trọng số FSRS mặc định cho mọi người.
- Engine **luôn** đề xuất được một bộ câu hỏi tại bất kỳ thời điểm nào, kể cả chưa tới hạn ôn.

### Cố tình KHÔNG làm (chống overengineering)
IRT/3PL · θ per-user · ELO per-question · embedding/semantic graph · response-time · chấm điểm liên tục ·
per-user nightly fit / optimizer · review-log để replay · reschedule toàn deck.

---

## 2. Trạng thái bộ nhớ (mỗi cặp user × sense)

| Trường | Ý nghĩa |
|---|---|
| `S` | stability — số ngày để xác suất nhớ tụt về 0.9 |
| `D` | difficulty ∈ [1,10] |
| `last_review` | thời điểm ôn gần nhất (tính `elapsed`) |

`R` (xác suất nhớ) **không lưu**, luôn tính lại từ đồng hồ khi cần.

---

## 3. Chấm nhị phân → grade FSRS

Engine chỉ nhận 2 nhãn. Ánh xạ vào 4 grade của FSRS:

```
Đúng  → Good  (grade 3)
Sai   → Again (grade 1)
```

- **Hard (2) và Easy (4) không dùng.** Các trọng số gắn với chúng (w1, w3, w15, w16) trở thành hằng số chết.
- Chính sách "đúng như thế nào" (exact match, typo Levenshtein ≤ 1, LLM-judge yes/no) nằm ở **tầng chấm**, ngoài engine. Engine chỉ thấy true/false.
- Mỗi term trong một session **chỉ ghi nhận lần thử ĐẦU TIÊN**. Các lần drill lại trong cùng session là relearning step, không đụng vào `S`.

---

## 4. Cập nhật trí nhớ — FSRS-4.5 nguyên bản

Bộ 17 trọng số mặc định công bố (`w0..w16`), **hardcode, không bao giờ fit**.

**Đường cong quên (power-law):**
```
R(t) = (1 + (19/81) · t/S) ^ (-0.5)          # R = 0.9 đúng khi t = S
```

**Khởi tạo (lần ôn đầu tiên):**
```
S0 = w2   nếu Đúng
S0 = w0   nếu Sai
D0 = w4 - exp(w5 · (grade - 1)) + 1     (clamp [1,10])
```

**Ôn thành công (Đúng):**
```
S' = S · (1 + exp(w8) · (11 - D) · S^(-w9) · (exp(w10·(1 - R)) - 1))
```

**Ôn thất bại (Sai):**
```
S' = min( S,  w11 · D^(-w12) · ((S + 1)^w13 - 1) · exp(w14·(1 - R)) )
```

**Difficulty:** chỉ tăng khi Sai; khi Đúng hồi quy nhẹ về trung bình (mean reversion chuẩn FSRS, chống "ease hell").

**Hẹn lịch kế tiếp:**
```
interval = S            # tại retention mục tiêu 0.9
clamp [30 phút, 365 ngày]
```

> Tham chiếu công thức: xem tài liệu FSRS chính thức (Expertium — "A technical explanation of FSRS")
> và bản mẫu "Implementing FSRS in 100 lines". Có thể dùng thẳng lib chính thức
> `go-fsrs` (Go) / `py-fsrs` / `ts-fsrs`, chỉ cần map Đúng→Good, Sai→Again.

---

## 5. Mastery rời rạc [0-100]

```
mastery = round( 100 · S / (S + 30) )
```

Hàm bão hòa, đơn điệu theo `S`, có nghĩa vật lý ("nhớ được bao lâu"):

| S (ngày) | 1 | 7 | 30 | 90 | 365 |
|---|---|---|---|---|---|
| mastery | 3 | 19 | 50 | 75 | 92 |

Không dùng `R` làm mastery (R dao động theo giờ, không ổn định để hiển thị).

---

## 6. Router câu hỏi (bất đối xứng: được ra dễ hơn, cấm khó hơn)

Mastery quy định **cấp trần** (cap). Sample 1 câu từ dòng tương ứng — theo cấu trúc bảng thì **không bao giờ vượt cap**, không cần điều kiện chặn.

| Mastery | Cap | MCQ | Điền khuyết | Gõ tự do |
|---|---|---|---|---|
| `< 30`  | 0 | 100% | — | — |
| `30–65` | 1 | 20% | 80% | — |
| `> 65`  | 2 | 10% | 20% | 70% |

**Vì sao bất đối xứng đúng về mặt tín hiệu:** engine nhị phân không phân biệt được
"quên từ" với "format quá khó". Fail oan trên câu quá khó sẽ phạt `S` sai lệch;
còn cho làm câu dễ hơn chỉ gây nhiễu nhẹ theo chiều an toàn.

Router trả `recommended_type` cho frontend ở bước lấy câu hỏi kế tiếp.

---

## 7. Luôn có bộ câu hỏi (kể cả chưa tới hạn)

Xếp hạng **mọi** thẻ theo `R` tăng dần:
- Thẻ quá hạn → `R` thấp nhất → lên đầu hàng đợi.
- Thẻ chưa tới hạn → `R` cao hơn nhưng **vẫn xếp được** → hàng đợi **không bao giờ rỗng**.
- Trộn từ mới theo tỉ lệ cố định (ví dụ 2 mới / 10 ôn).

**Ôn sớm không phá lịch:** khi `R` còn cao, thừa số `exp(w10·(1−R)) − 1 ≈ 0` ⇒ `S` gần như không tăng.
FSRS tự chống cram, không cần chặn thủ công.

---

## 8. Trade-off đã chấp nhận có chủ đích

- **MCQ đoán mò trúng 25% được tính Good.** Mọi hệ nhị phân đều dính. Ảnh hưởng nhỏ vì MCQ
  chủ yếu xuất hiện ở mastery thấp, nơi interval còn ngắn nên lỗi tự được sửa nhanh ở lần ôn kế.
- **Trọng số dùng chung cho mọi user** (không cá nhân hóa). Đổi lại: đơn giản, không cần cron/optimizer/review-log.
- **Bỏ Easy grade.** Không có tín hiệu (RT / self-rating) để phân biệt "nhớ chật vật" với "nhớ tức thì".

---

## 9. Điểm chạm với codebase hiện tại (tham khảo khi triển khai)

- Tầng chấm **đã nhị phân** (`responses.is_correct`, LLM-judge trong worker trả yes/no) → worker gần như không sửa.
- `user_term_stats` đã có `last_review_date`, `next_review_date`, `interval_seconds`, `mastery_level`
  → migration chỉ thêm ~3 cột: `stability`, `difficulty`, `mastery`.
- SQL chọn từ hiện tại (due > new > upcoming) đã phủ toàn deck, không bao giờ rỗng
  → chỉ tinh chỉnh `ORDER BY` theo `R` nếu muốn.
- Việc chính: thay ruột `computeELOUpdate` (~40 dòng), xóa 3 file ELO
  (`elo.go`, `intervals.go`, `mastery_levels.go`), thêm router ~15 dòng, trả `recommended_type` cho FE.

**Ước lượng:** ~1.5–2 ngày dev; phần toán chỉ chiếm ~nửa ngày, còn lại là rewiring + sửa test hiện có.

---

## 10. Câu hỏi mở

1. Ngưỡng "đúng" ở tầng chấm cho FILL/WRITE: exact-only hay cho phép typo (Levenshtein ≤ 1)?
2. Tỉ lệ trộn từ mới / từ ôn mỗi session — cố định bao nhiêu?
3. Có giữ lại cột `mastery_level` (0-10) cho tương thích FE cũ, song song với `mastery` (0-100) không?
